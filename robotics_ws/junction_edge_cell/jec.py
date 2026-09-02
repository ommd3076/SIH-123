"""Junction Edge Cell (JEC) — local coordination accelerator (build prompt §2.B).

A JEC is an infrastructure process placed at a contested junction. It knows
ONLY its local area: the junction cell, the adjacent edge halves and (for
rack-aisle JECs) one narrow-aisle direction gate. It:

  * maintains local occupancy / predicted occupancy (runs the Edge-AI
    congestion predictor inference every second)
  * grants space-time reservations for its junction (deterministic
    arbitration: effective priority DESC, robot id ASC) with leases
  * manages narrow-aisle direction ownership with hysteresis (min ownership
    window, quiet-release) enabling same-direction batching
  * forms and expires CONFLICT CELLS from overlapping trajectory intents
  * publishes local state at 2 Hz + heartbeat at 1 Hz
  * never commands motion and is never required for robot safety: robots
    detect JEC_OFFLINE via heartbeat timeout and fall back to P2P claims.
"""
from __future__ import annotations

import math
from collections import deque
from typing import Any, Dict, List, Optional, Tuple

from ..fleet_core.types import (RESV_ACTIVE, RESV_EXPIRED, RESV_GRANTED,
                                RESV_REJECTED, Reservation)
from ..robot_agent.base_agent import BaseAgent

JEC_STATE_HZ = 2
JEC_HB_HZ = 1
PREDICT_HZ = 1


class JunctionEdgeCellAgent(BaseAgent):
    kind = "jec"

    def __init__(self, jec_id: str, runtime, plane, wmap=None, cfg=None, seed: int = 0):
        super().__init__(jec_id, runtime, plane, wmap, cfg, seed)
        self.spec = self.wmap.jecs[jec_id]
        self.junction = self.spec.junction
        self.gate = self.spec.gate
        self.range_m = float(cfg["fleet"].get("radio_range_jec", 30.0))
        self.plane.range_m = self.range_m
        # JEC downlink travels the wired backbone + facility AP: mark infra
        self.plane.infra = True

        # ---- local world state
        self.peers: Dict[str, Dict] = {}          # rid -> heartbeat
        self.intents: Dict[str, Dict] = {}        # rid -> intent (targets me)
        self.reservations: Dict[str, Reservation] = {}   # resv_id -> Reservation
        self.queue: List[Dict] = []               # waiting requests (denied)
        # gate state
        self.gate_dir = 0                         # 0 free, +1 northbound, -1 southbound
        self.gate_holders: List[str] = []
        self.gate_since = 0.0
        self.gate_last_demand = 0.0
        self.blocked = False

        # ---- predictor (Edge-AI inference at the edge node)
        from ..congestion_predictor.mlp import load_predictor
        self.predictor = load_predictor(cfg)
        self.predictor_kind = self.predictor.name
        self.predicted: Dict[str, float] = {}
        self.congestion = 0.0
        self.feature_log: deque = deque(maxlen=400)   # for dataset generation
        self._predict_accum = 0.0
        self._state_accum = 0.0
        self._hb_accum = 0.0

        # ---- counters
        self.counters = {
            "grants": 0, "denials": 0, "expired": 0, "conflicts_formed": 0,
            "busy_ticks": 0, "total_ticks": 0, "gate_flips": 0,
            "congestion_spikes": 0,
        }
        self._conflict_cells: Dict[str, Dict] = {}
        self._spike_armed = True

    # ------------------------------------------------------------------
    def position(self) -> Tuple[float, float]:
        return self.wmap.node_pos(self.junction)

    def _wire(self) -> None:
        self.plane.subscribe("fleet/robot/*/heartbeat", self._on_heartbeat)
        self.plane.subscribe("fleet/robot/*/intent", self._on_intent)
        self.plane.subscribe("fleet/robot/*/resv_req", self._on_resv_req)
        self.plane.subscribe("fleet/robot/*/resv_release", self._on_release)

    # ==================================================================
    # inbound
    # ==================================================================
    def _on_heartbeat(self, key: str, m: Dict) -> None:
        rid = m.get("robot")
        if not rid:
            return
        m = dict(m)
        m["t_recv"] = self.t
        self.peers[rid] = m

    def _on_intent(self, key: str, m: Dict) -> None:
        rid = m.get("robot")
        if not rid:
            return
        # JEC keeps ONLY intents relevant to its local resources
        relevant = False
        for tgt in m.get("targets", []):
            res = tgt.get("resource", "")
            if res == self.junction or res == self.gate or res in self.spec.covers:
                relevant = True
                break
        if not relevant:
            # also keep intents of robots currently near my junction
            pos = m.get("pos", [0, 0])
            jx, jy = self.position()
            if math.hypot(pos[0] - jx, pos[1] - jy) < 14.0:
                relevant = True
        if relevant:
            self.intents[rid] = dict(m)

    def _on_resv_req(self, key: str, m: Dict) -> None:
        res = m.get("resource", "")
        if res not in (self.junction, self.gate):
            return          # not my jurisdiction
        rid = m.get("robot", "")
        req = Reservation(
            resource=res, robot=rid, start=float(m.get("start", 0)),
            end=float(m.get("end", 0)), priority=float(m.get("priority", 0)),
            lease=float(m.get("lease", 4.0)), state=RESV_GRANTED,
            resv_id=f"{self.id}-{rid}-{res}-{int(self.t * 1000)}",
            created=self.t,
        )
        if res == self.gate:
            self._gate_request(rid, req, int(m.get("dir", 0)))
            return
        self._junction_request(rid, req)

    def _junction_request(self, rid: str, req: Reservation) -> None:
        margin = 0.6      # safety margin for box traversal
        conflict = None
        for r in self.reservations.values():
            if r.resource == req.resource and r.robot != rid and \
                    r.state in (RESV_GRANTED, RESV_ACTIVE) and req.overlaps(r, margin):
                conflict = r
                break
        if conflict is None:
            req.state = RESV_GRANTED
            self.reservations[req.resv_id] = req
            self.counters["grants"] += 1
            self._reply(rid, req, "GRANTED")
        else:
            # deterministic arbitration: higher effective priority wins;
            # ties broken by robot id ASC. Loser is queued (fairness ages).
            if (req.priority, [-ord(c) for c in rid]) > \
                    (conflict.priority, [-ord(c) for c in conflict.robot]):
                # preempt: expire the weaker existing grant
                conflict.state = RESV_EXPIRED
                self.counters["expired"] += 1
                self._reply(conflict.robot, conflict, "PREEMPTED")
                req.state = RESV_GRANTED
                self.reservations[req.resv_id] = req
                self.counters["grants"] += 1
                self._reply(rid, req, "GRANTED")
            else:
                req.state = RESV_REJECTED
                self.counters["denials"] += 1
                qpos = 1 + sum(1 for q in self.queue if q["resource"] == req.resource)
                self.queue.append({"resource": req.resource, "robot": rid,
                                   "priority": req.priority, "t": self.t})
                self._reply(rid, req, "DENIED", queue_pos=qpos)

    def _gate_request(self, rid: str, req: Reservation, dir_: int) -> None:
        if self.blocked:
            self._reply(rid, req, "DENIED", reason="GATE_BLOCKED")
            self.counters["denials"] += 1
            return
        occupants = self._gate_occupants()
        opposing = [o for o in occupants if o["dir"] != dir_]
        if opposing:
            self._reply(rid, req, "DENIED", reason="OPPOSING_FLOW")
            self.counters["denials"] += 1
            self.queue.append({"resource": self.gate, "robot": rid,
                               "priority": req.priority, "t": self.t, "dir": dir_})
            return
        # same-direction batch or free gate
        if self.gate_dir != 0 and self.gate_dir != dir_:
            # direction held opposite by claims/holders but aisle empty:
            # honour ownership until quiet window passes (hysteresis)
            self._reply(rid, req, "DENIED", reason="DIRECTION_HELD")
            self.counters["denials"] += 1
            self.queue.append({"resource": self.gate, "robot": rid,
                               "priority": req.priority, "t": self.t, "dir": dir_})
            return
        if self.gate_dir == 0:
            self.gate_dir = dir_
            self.gate_since = self.t
            self.gate_holders = []
            self.counters["gate_flips"] += 1
        self.gate_last_demand = self.t
        if rid not in self.gate_holders:
            self.gate_holders.append(rid)
        req.state = RESV_GRANTED
        req.dir = dir_                 # type: ignore[attr-defined]
        self.reservations[req.resv_id] = req
        self.counters["grants"] += 1
        self._reply(rid, req, "GRANTED")

    def _reply(self, rid: str, resv: Reservation, decision: str,
               queue_pos: int = 0, reason: str = "") -> None:
        self.plane.publish(f"fleet/jec/{self.id}/resv/{rid}", {
            "jec": self.id, "robot": rid, "t": round(self.t, 3),
            "decision": decision, "reason": reason, "queue_pos": queue_pos,
            "resource": resv.resource, "resv": resv.to_msg(),
        })
        self.emit("reservation_decision", {
            "robot": rid, "resource": resv.resource, "decision": decision,
            "reason": reason, "queue_pos": queue_pos,
            "window": [resv.start, resv.end],
        })

    def _on_release(self, key: str, m: Dict) -> None:
        res = m.get("resource", "")
        rid = m.get("robot", "")
        if res not in (self.junction, self.gate):
            return
        for r in list(self.reservations.values()):
            if r.resource == res and r.robot == rid:
                r.state = "RELEASED"
                del self.reservations[r.resv_id]
        if res == self.gate:
            self.gate_holders = [h for h in self.gate_holders if h != rid]

    # ==================================================================
    # tick
    # ==================================================================
    def tick(self) -> None:
        self.t = self.runtime.now()
        self.counters["total_ticks"] += 1
        self._expire_stale()
        self._update_gate_release()
        self._update_occupancy()
        self._predict_step()
        self._publish_conflict_cells()
        self._heartbeat()
        self._state_publish()
        if self.queue or any(r.state in (RESV_GRANTED, RESV_ACTIVE)
                             for r in self.reservations.values()):
            self.counters["busy_ticks"] += 1

    def _expire_stale(self) -> None:
        for r in list(self.reservations.values()):
            horizon = r.end + r.lease
            if r.state in (RESV_GRANTED, RESV_ACTIVE) and self.t > horizon:
                r.state = RESV_EXPIRED
                self.counters["expired"] += 1
                del self.reservations[r.resv_id]
                if r.resource == self.gate:
                    self.gate_holders = [h for h in self.gate_holders if h != r.robot]
                self.emit("reservation_expired", {
                    "robot": r.robot, "resource": r.resource,
                    "window": [r.start, r.end],
                })
        # expire queue entries older than 6s (robots re-request)
        self.queue = [q for q in self.queue if self.t - q["t"] < 6.0]

    def _update_gate_release(self) -> None:
        """Direction ownership hysteresis: keep direction while any occupant
        or recent same-direction demand exists; release after quiet window."""
        if self.gate_dir == 0:
            return
        occupants = self._gate_occupants()
        same_dir = [o for o in occupants if o["dir"] == self.gate_dir]
        # demand from pending queue entries with same dir
        pending_same = any(q.get("dir", 0) == self.gate_dir for q in self.queue)
        opposing = [q for q in self.queue if q.get("dir", 0) == -self.gate_dir]
        pending_opposing = bool(opposing)
        held = self.t - self.gate_since
        min_own = self.cfg["narrow_gate"]["min_ownership_s"]
        quiet = self.cfg["narrow_gate"]["release_quiet_s"]
        # starvation prevention: an aged opposing claim (priority >= 6 via
        # fairness aging) forces a direction release after 2x min ownership
        starved_opposing = any(q.get("priority", 0) >= 6.0 for q in opposing)
        quiet_ok = (self.t - self.gate_last_demand) > quiet
        force = starved_opposing and held > min_own * 2.0
        release = False
        if not same_dir and held > min_own:
            if pending_opposing and (force or (quiet_ok and not pending_same)):
                release = True          # serve the opposing (possibly starved) flow
            elif not pending_opposing and not pending_same and quiet_ok:
                release = True          # idle gate returns to free
        if release and self.gate_dir != 0:
            self.gate_dir = 0
            self.gate_holders = []
            self.counters["gate_flips"] += 1
            self.emit("gate_released", {"gate": self.gate,
                                        "held_s": round(held, 1),
                                        "forced": force})

    def _gate_occupants(self) -> List[Dict]:
        out = []
        gate_edges = self.wmap.gate_edges(self.gate) if self.gate else set()
        if not gate_edges:
            return out
        for rid, hb in self.peers.items():
            if hb.get("edge") in gate_edges and hb.get("state") != "FAILED":
                e = self.wmap.edges[hb.get("edge")]
                d = hb.get("dir", 1)
                dy = (self.wmap.nodes[e.v].y - self.wmap.nodes[e.u].y) if d == 1 \
                    else (self.wmap.nodes[e.u].y - self.wmap.nodes[e.v].y)
                out.append({"robot": rid, "dir": 1 if dy > 0 else -1})
        return out

    def _update_occupancy(self) -> None:
        # drop stale peers (3s)
        for rid in [r for r, m in self.peers.items() if self.t - m.get("t_recv", 0) > 3.0]:
            del self.peers[rid]
        for rid in [r for r, m in self.intents.items() if self.t - m.get("t", 0) > 6.0]:
            del self.intents[rid]

    # ------------------------------------------------------------------
    # Edge-AI congestion prediction (inference at this edge node)
    # ------------------------------------------------------------------
    def _features(self) -> Dict[str, float]:
        jx, jy = self.position()
        occupancy = 0
        for hb in self.peers.values():
            p = hb.get("pos", [0, 0])
            if math.hypot(p[0] - jx, p[1] - jy) < self.wmap.junction_box * 1.6:
                occupancy += 1
        approaching = 0
        for intent in self.intents.values():
            for tgt in intent.get("targets", []):
                if tgt.get("resource") == self.junction and 0.0 < tgt.get("eta", 99) < self.horizon():
                    approaching += 1
        queue_len = len([q for q in self.queue if q["resource"] == self.junction])
        downstream = 0
        for eid in self.spec.covers:
            e = self.wmap.edges[eid]
            for hb in self.peers.values():
                if hb.get("edge") == eid:
                    downstream += 1
        demand = self._demand_factor()
        blockages = len([ev for ev in self.active_context("AISLE_BLOCKED")
                         if self.junction in ev.affected or eid in ev.affected])
        return {
            "occ_now": float(occupancy), "approaching": float(approaching),
            "queue_len": float(queue_len), "intent_count": float(len(self.intents)),
            "downstream_occ": float(downstream), "demand_factor": demand,
            "blockage_active": float(1.0 if self.blocked else 0.0),
            "recent_blockages": float(blockages), "hour": float(self.t % 3600),
            "resv_active": float(sum(1 for r in self.reservations.values()
                                     if r.state in (RESV_GRANTED, RESV_ACTIVE))),
        }

    def horizon(self) -> float:
        return float(self.cfg["predictor"].get("horizon_s", 5.0))

    def _demand_factor(self) -> float:
        # schedule-driven demand prior (from allocator schedule broadcast)
        evs = self.active_context("DEMAND_LEVEL")
        if evs:
            try:
                return float(evs[-1].value)
            except ValueError:
                return 1.0
        return 1.0

    def _predict_step(self) -> None:
        self._predict_accum += self.tick_period
        if self._predict_accum < 1.0 / PREDICT_HZ:
            return
        self._predict_accum = 0.0
        feats = self._features()
        # heuristic persistence+inflow baseline (or learned model if enabled)
        pred = self._predict(feats)
        self.predicted = {self.junction: round(pred, 3)}
        if self.gate:
            gate_pred = self._predict_gate()
            self.predicted[self.gate] = round(gate_pred, 3)
        self.congestion = min(2.0, pred / 2.0)      # junction capacity ~2 flows
        self.feature_log.append({"t": round(self.t, 3), "features": feats,
                                 "predicted": round(pred, 3)})
        # congestion spike context event (once per episode)
        if self.congestion > 1.2 and self._spike_armed:
            self._spike_armed = False
            self.counters["congestion_spikes"] += 1
            self.publish_context("CONGESTION_SPIKE", self.junction, ttl=8.0,
                                 affected=[self.junction] + self.spec.covers,
                                 confidence=round(min(0.95, 0.5 + self.congestion / 4), 2))
        elif self.congestion < 0.7:
            self._spike_armed = True

    def _predict(self, feats: Dict[str, float]) -> float:
        """Edge-AI inference: learned MLP if configured, else heuristic."""
        if self.predictor is not None:
            try:
                return self.predictor(feats)
            except Exception:  # noqa: BLE001
                pass
        # heuristic: persistence + inflow estimate, clipped
        inflow = feats["approaching"] + 0.3 * feats["queue_len"]
        outflow = 0.5 * feats["occ_now"]
        pred = feats["occ_now"] + 0.8 * (inflow - outflow)
        return max(0.0, pred)

    def _predict_gate(self) -> float:
        return float(len(self._gate_occupants()))

    # ------------------------------------------------------------------
    # conflict cells (§4)
    # ------------------------------------------------------------------
    def _publish_conflict_cells(self) -> None:
        """Group robots whose intent windows overlap on my junction or gate."""
        groups: Dict[str, List[Dict]] = {}
        for rid, intent in self.intents.items():
            for tgt in intent.get("targets", []):
                res = tgt.get("resource", "")
                if res in (self.junction, self.gate):
                    eta = tgt.get("eta", 99)
                    dur = tgt.get("dur", 1.6)
                    key = res
                    groups.setdefault(key, []).append(
                        {"robot": rid, "eta": eta, "end": eta + dur})
        active: Dict[str, Dict] = {}
        for res, members in groups.items():
            # pairwise overlap -> union robots (small n^2, n<=10)
            overlapping: List[str] = []
            for i, a in enumerate(members):
                for b in members[i + 1:]:
                    if a["eta"] < b["end"] and b["eta"] < a["end"]:
                        for m in (a["robot"], b["robot"]):
                            if m not in overlapping:
                                overlapping.append(m)
            if len(overlapping) >= 2:
                members_sorted = sorted(overlapping)
                cell_id = f"CC-{res}-" + ",".join(members_sorted)
                active[cell_id] = {
                    "cell": cell_id, "resource": res, "members": members_sorted,
                    "t": round(self.t, 3), "emitter": self.id, "mode": "JEC",
                }
                if cell_id not in self._conflict_cells:
                    self.counters["conflicts_formed"] += 1
        # expire cells that are gone
        for cell_id in list(self._conflict_cells):
            if cell_id not in active:
                self.plane.publish(f"fleet/conflict/{cell_id}", {
                    "cell": cell_id, "expired": True, "t": round(self.t, 3),
                    "emitter": self.id,
                })
        self._conflict_cells = active
        for cell_id, cell in active.items():
            self.plane.publish(f"fleet/conflict/{cell_id}", cell)

    # ------------------------------------------------------------------
    # outbound
    # ----------------------------------------------------------------=
    def _heartbeat(self) -> None:
        self._hb_accum += self.tick_period
        if self._hb_accum < 1.0 / JEC_HB_HZ:
            return
        self._hb_accum = 0.0
        self.plane.publish(f"fleet/jec/{self.id}/heartbeat", {
            "jec": self.id, "t": round(self.t, 3), "junction": self.junction,
            "gate": self.gate or "", "alive": True,
        })

    def _state_publish(self) -> None:
        self._state_accum += self.tick_period
        if self._state_accum < 1.0 / JEC_STATE_HZ:
            return
        self._state_accum = 0.0
        state = {
            "jec": self.id, "t": round(self.t, 3), "junction": self.junction,
            "gate": self.gate or "", "alive": True,
            "blocked": self.blocked,
            "occupancy": self.predicted.get(self.junction, 0.0),
            "predicted": dict(self.predicted),
            "congestion": round(self.congestion, 3),
            "queue": [q for q in self.queue],
            "reservations": [r.to_msg() for r in self.reservations.values()],
            "gate_state": {
                "dir": self.gate_dir, "holders": list(self.gate_holders),
                "since": round(self.gate_since, 2),
                "occupants": self._gate_occupants() if self.gate else [],
            },
            "conflicts": list(self._conflict_cells.values()),
            "approaching": [
                {"robot": rid, "eta": min((t.get("eta", 99) for t in intent.get("targets", [])
                                           if t.get("resource") == self.junction), default=99)}
                for rid, intent in self.intents.items()
                if any(t.get("resource") == self.junction for t in intent.get("targets", []))
            ],
            "stats": self.plane.stats.to_msg(),
            "counters": dict(self.counters),
            "predictor": self.predictor_kind,
            "utilization": round(self.counters["busy_ticks"] /
                                 max(1, self.counters["total_ticks"]), 3),
        }
        self.plane.publish(f"fleet/jec/{self.id}/state", state)

    predictor_kind = "heuristic"

    # ------------------------------------------------------------------
    # chaos
    # ------------------------------------------------------------------
    def on_control(self, key: str, payload: Dict) -> None:
        super().on_control(key, payload)
        cmd = payload.get("cmd")
        if cmd == "BLOCK_AISLE":
            target = payload.get("resource", "")
            if target in (self.junction, self.gate) or target in self.spec.covers \
                    or target in self.wmap.gate_edges(self.gate or ""):
                self.blocked = True
                # the JEC is the local reporter: broadcast the blockage to
                # nearby actors so they can replan around it
                affected = [target]
                if target in self.wmap.aisles:
                    affected = list(self.wmap.gate_edges(target))
                self.publish_context("AISLE_BLOCKED", target,
                                     ttl=float(payload.get("ttl", 20.0)),
                                     confidence=0.96, affected=affected)
        elif cmd == "UNBLOCK_AISLE":
            target = payload.get("resource", "")
            if target in (self.junction, self.gate) or target in self.spec.covers:
                self.blocked = False
                self.publish_context("AISLE_CLEARED", target, ttl=8.0,
                                     affected=[target])
        elif cmd == "KILL_JEC" and payload.get("jec") == self.id:
            self.stop()

    # ------------------------------------------------------------------
    def snapshot(self) -> Dict:
        return {
            "jec": self.id, "t": round(self.t, 3), "junction": self.junction,
            "gate": self.gate or "", "alive": self.started,
            "blocked": self.blocked, "occupancy": self.predicted.get(self.junction, 0.0),
            "predicted": dict(self.predicted), "congestion": round(self.congestion, 3),
            "queue": list(self.queue),
            "reservations": [r.to_msg() for r in self.reservations.values()],
            "gate_state": {"dir": self.gate_dir, "holders": list(self.gate_holders)},
            "conflicts": list(self._conflict_cells.values()),
            "counters": dict(self.counters), "stats": self.plane.stats.to_msg(),
            "predictor": self.predictor_kind,
            "utilization": round(self.counters["busy_ticks"] /
                                 max(1, self.counters["total_ticks"]), 3),
        }
