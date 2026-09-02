"""Robot Edge Agent (build prompt §2.A).

One instance per simulated AMR. Runs the full local stack:

    localization (simulated state)
      -> route generation (A* + k-alternatives + prosocial social cost)
      -> local intent publishing (graph of futures)
      -> conflict awareness (peer intents + JEC state)
      -> reservation logic (JEC-managed junctions/gates, P2P fallback)
      -> deterministic safety check (veto layer)
      -> movement execution

The robot never depends on the bridge, the allocator or (for safety) on JECs:
if a JEC disappears, coordination for its resources degrades to P2P intent
negotiation; if the allocator disappears, robots simply receive no new tasks.

Experiment modes (§20):
    STOP_AND_WAIT            — no intents, no reservations; any occupied next
                               edge blocks movement (ultra-conservative)
    SHORTEST_PATH_REACTIVE   — selfish A*, capacity sensing, no coordination
    INTENT_P2P               — intents shared, P2P conflicts/gates, no JEC,
                               selfish routing (externality weight = 0)
    FULL_DISTRIBUTED_PREDICTIVE — everything: JEC reservations, gates,
                               prosocial routing, congestion prediction
"""
from __future__ import annotations

import math
import random
from typing import Any, Dict, List, Optional, Tuple

from ..fleet_core import routing as R
from ..fleet_core import safety as S
from ..fleet_core.fairness import (FairnessConfig, FairnessState,
                                   effective_priority, is_starving)
from ..fleet_core.social import SocialWeights, choose_route, evaluate_route
from ..fleet_core.types import (RESV_ACTIVE, RESV_GRANTED, ContextEvent, Intent,
                                Task)
from .base_agent import BaseAgent

RobotState = str  # IDLE / TO_PICKUP / DOCK / TO_DROP / TO_CHARGE / CHARGING / FAILED

HEARTBEAT_HZ = 2
INTENT_HZ = 2
REPLAN_INTERVAL = 1.5
JEC_OFFLINE_AFTER = 2.5
PEER_TTL = 3.0


class ModeFlags:
    def __init__(self, mode: str):
        self.mode = mode
        self.share_intent = mode in ("INTENT_P2P", "FULL_DISTRIBUTED_PREDICTIVE")
        self.use_jec = mode == "FULL_DISTRIBUTED_PREDICTIVE"
        self.prosocial = mode == "FULL_DISTRIBUTED_PREDICTIVE"
        self.stop_and_wait = mode == "STOP_AND_WAIT"
        self.reactive_only = mode == "SHORTEST_PATH_REACTIVE"


class RobotAgent(BaseAgent):
    kind = "robot"

    def __init__(self, rid: str, runtime, plane, wmap=None, cfg=None, seed: int = 0,
                 mode: str = "FULL_DISTRIBUTED_PREDICTIVE", start_node: str = "O1",
                 battery: float = None):
        super().__init__(rid, runtime, plane, wmap, cfg, seed)
        self.flags = ModeFlags(mode)
        self.range_m = float(cfg["fleet"].get("radio_range_robot", 18.0))
        self.plane.range_m = self.range_m
        self.weights = SocialWeights.from_cfg(cfg.get("social_weights", {}))
        if not self.flags.prosocial:
            self.weights.externality = 0.0
            self.weights.congestion *= 0.5
        self.fair_cfg = FairnessConfig.from_cfg(cfg.get("fairness", {}))
        self.safety_cfg = S.SafetyConfig.from_cfg(cfg.get("safety", {}))
        self.horizon = float(cfg["fleet"].get("prediction_horizon_s", 5.0))

        # ---- own state
        self.state: RobotState = "IDLE"
        self.node: Optional[str] = start_node
        self.edge: Optional[str] = None
        self.s = 0.0
        self.dir = 1
        self.speed = 0.0
        self.route: R.Route = []
        self.task: Optional[Dict] = None
        self.task_phase = None            # pickup | drop
        self.dwell_until = 0.0
        self.battery = battery if battery is not None else self.rng.uniform(
            *cfg.get("battery", {}).get("start_pct", [72, 96]))
        self.fairness = FairnessState(base_priority=1.0 + (self.rng.random() * 0.5))
        # explicit spawn position (zones are queueing spurs, not rings)
        spawn = {sp["rid"]: sp for sp in self.wmap.spawn}
        self.spawn_pos = tuple(spawn.get(rid, {}).get("pos", [0.0, 0.0]))
        self.last_edge: Optional[str] = None
        self.entry_dir: int = 1

        # ---- world model from messages only
        self.peers: Dict[str, Dict] = {}           # rid -> heartbeat dict (with t)
        self.intents: Dict[str, Dict] = {}         # rid -> intent msg
        self.jec_states: Dict[str, Dict] = {}      # jec_id -> state msg (with t)
        self.jec_last_hb: Dict[str, float] = {}
        self.gate_claims: Dict[str, List[Dict]] = {}   # gate -> claims seen
        self.reservations: Dict[str, Dict] = {}    # resource -> grant dict
        self.resv_pending: Dict[str, float] = {}   # resource -> last request t
        self.conflict_cells: Dict[str, Dict] = {}  # cell_id -> cell state

        # ---- counters (real measurements, published in telemetry)
        self.counters = {
            "distance_m": 0.0, "waiting_s": 0.0, "yields": 0, "denials": 0,
            "vetoes": 0, "replans": 0, "tasks_done": 0, "collisions": 0,
            "idle_s": 0.0, "move_s": 0.0, "charge_s": 0.0, "energy_j": 0.0,
        }
        self._hb_accum = 0.0
        self._intent_accum = 0.0
        self._replan_accum = 0.0
        self._last_pos = (0.0, 0.0)
        self._veto_reasons: List[Dict] = []
        self._min_gap_seen = math.inf
        self._collision_latched: set = set()
        self._nearmiss_latched: set = set()
        self._stuck_since: Optional[float] = None
        self._reversing: bool = False
        self._rev_started: Optional[float] = None
        self._vacate_since: Optional[float] = None
        self._veto_active: set = set()
        self._last_yield_reg: Dict[str, float] = {}

    # ------------------------------------------------------------------
    def position(self) -> Tuple[float, float]:
        if self.node is not None:
            n = self.wmap.nodes[self.node]
            if n.is_zone and self.last_edge and self.last_edge in self.wmap.edges:
                # zone queueing: parked robots line up along their entry edge,
                # offset 0.9m laterally so the travel lane stays clear
                slot = self._zone_slot()
                e = self.wmap.edges[self.last_edge]
                park_s = max(0.15, e.length - 0.75 * (slot + 1))
                return self.wmap.world_pos(self.last_edge, park_s, self.entry_dir, 0.9)
            if n.is_zone and self.spawn_pos != (0.0, 0.0):
                return self.spawn_pos
            x, y = self.wmap.node_pos(self.node)
            return (x, y)      # junctions/bays: transient crossing at centre
        if self.edge is not None:
            off = self.wmap.lane_offset_for(self.edge)
            return self.wmap.world_pos(self.edge, self.s, self.dir, off)
        return (0.0, 0.0)

    def _wire(self) -> None:
        self.plane.subscribe("fleet/robot/*/heartbeat", self._on_heartbeat)
        self.plane.subscribe("fleet/robot/*/intent", self._on_intent)
        self.plane.subscribe("fleet/jec/*/state", self._on_jec_state)
        self.plane.subscribe("fleet/jec/*/heartbeat", self._on_jec_hb)
        self.plane.subscribe("fleet/jec/*/resv/" + self.id, self._on_resv_reply)
        self.plane.subscribe("fleet/gate/*/claim", self._on_gate_claim)
        self.plane.subscribe("fleet/allocator/announce", self._on_announce)
        self.plane.subscribe("fleet/allocator/award", self._on_award)
        self.plane.subscribe("fleet/conflict/*", self._on_conflict)
        self.plane.subscribe("fleet/task/*", self._on_task_event)

    # ==================================================================
    # message handlers
    # ==================================================================
    def _on_heartbeat(self, key: str, m: Dict) -> None:
        if m.get("robot") == self.id:
            return
        m = dict(m)
        m["t_recv"] = self.t
        self.peers[m["robot"]] = m

    def _on_intent(self, key: str, m: Dict) -> None:
        if m.get("robot") == self.id or not self.flags.share_intent:
            return
        self.intents[m["robot"]] = dict(m)

    def _on_jec_hb(self, key: str, m: Dict) -> None:
        jid = m.get("jec", "")
        self.jec_last_hb[jid] = self.t
        if m.get("born") and jid in self.jec_states and self.jec_states[jid].get("_offline"):
            self.jec_states[jid]["_offline"] = False
            self.publish_context("JEC_ONLINE", jid, ttl=6.0, affected=[m.get("junction", "")])

    def _on_jec_state(self, key: str, m: Dict) -> None:
        jid = m.get("jec", "")
        m = dict(m)
        m["t_recv"] = self.t
        m["_offline"] = False
        self.jec_states[jid] = m
        self.jec_last_hb[jid] = self.t
        # adopt grants addressed to me
        for resv in m.get("reservations", []):
            if resv.get("robot") == self.id and resv.get("state") in (RESV_GRANTED, RESV_ACTIVE):
                self.reservations.setdefault(resv["resource"], {}).update(resv)
        # predicted occupancy for routing (congestion estimate)
        # stored on jec_states; routing reads them via congestion_view()

    def _on_resv_reply(self, key: str, m: Dict) -> None:
        res = m.get("resource", "")
        decision = m.get("decision", "")
        if decision in ("GRANTED", "ACTIVE"):
            self.reservations[res] = m.get("resv", {})
            self.fairness.stop_wait(self.t)
        elif decision in ("DENIED", "QUEUED"):
            self.counters["denials"] += 1
            self.fairness.register_denial()
            self.reservations.pop(res, None)

    def _on_gate_claim(self, key: str, m: Dict) -> None:
        if m.get("robot") == self.id:
            return
        gate = m.get("gate", "")
        self.gate_claims.setdefault(gate, []).append(dict(m, t_recv=self.t))

    def _on_conflict(self, key: str, m: Dict) -> None:
        cell = m.get("cell", "")
        if not cell:
            return
        if m.get("expired"):
            self.conflict_cells.pop(cell, None)
        else:
            self.conflict_cells[cell] = dict(m, t_recv=self.t)

    def _on_task_event(self, key: str, m: Dict) -> None:
        # task state transitions (for observability); no control action needed
        pass

    # ==================================================================
    # auction participation (§17)
    # ==================================================================
    def _on_announce(self, key: str, m: Dict) -> None:
        if self.state in ("FAILED", "CHARGING", "TO_CHARGE") or self.task is not None:
            return
        bat = self.battery
        if bat < self.cfg["battery"]["low_threshold"] and m.get("kind") != "CHARGE":
            return
        # bid = ETA to pickup + to drop + congestion + battery penalty
        route1 = R.route_from_position(self.wmap, self._pos_dict(), m["pickup"])
        route2 = R.astar(self.wmap, m["pickup"], m["drop"]) if route1 else None
        if route1 is None or route2 is None:
            return
        eta = R.route_time(self.wmap, route1) + R.route_time(self.wmap, route2)
        cong = self._route_congestion(route1) + self._route_congestion(route2)
        battery_pen = max(0.0, (self.cfg["battery"]["low_threshold"] - bat)) * 0.1
        bid = eta + cong + battery_pen
        self.plane.publish(f"fleet/robot/{self.id}/bid", {
            "robot": self.id, "task_id": m["task_id"], "bid": round(bid, 2),
            "eta": round(eta, 2), "battery": round(bat, 1),
            "congestion": round(cong, 2), "t": round(self.t, 3),
        })

    def _on_award(self, key: str, m: Dict) -> None:
        if m.get("robot") != self.id or self.task is not None:
            return
        self.task = dict(m)
        self.task_phase = "pickup"
        if self.state not in ("DOCK",):
            self.state = "TO_PICKUP"
        self._plan_route(self.task["pickup"])
        self.emit("task_accepted", {"task_id": m["task_id"], "phase": "pickup"})

    # ==================================================================
    # main tick
    # ==================================================================
    def tick(self) -> None:
        self.t = self.runtime.now()
        self._expire_peers()
        self._check_jec_online_status()
        self._battery_tick()
        self._heartbeat()
        self._intent_publish()
        self._dwell()
        self._replan_maybe()
        self._request_reservations()
        self._execute_movement()

    def _expire_peers(self) -> None:
        for rid in [r for r, m in self.peers.items() if self.t - m.get("t_recv", 0) > PEER_TTL]:
            del self.peers[rid]
        for rid in [r for r, m in self.intents.items()
                    if self.t - m.get("t", 0) > PEER_TTL * 2]:
            del self.intents[rid]
        for gate in list(self.gate_claims):
            self.gate_claims[gate] = [c for c in self.gate_claims[gate]
                                      if self.t - c.get("t_recv", 0) < 1.0]
            if not self.gate_claims[gate]:
                del self.gate_claims[gate]

    def _check_jec_online_status(self) -> None:
        for jid, last in list(self.jec_last_hb.items()):
            offline = (self.t - last) > JEC_OFFLINE_AFTER
            st = self.jec_states.get(jid)
            if offline and st and not st.get("_offline"):
                st["_offline"] = True
                self.publish_context("JEC_OFFLINE", jid, ttl=15.0,
                                     affected=self._jec_resources(jid))
            elif not offline and st and st.get("_offline"):
                st["_offline"] = False

    def _jec_resources(self, jid: str) -> List[str]:
        st = self.jec_states.get(jid, {})
        out = [st.get("junction", "")]
        if st.get("gate"):
            out.append(st["gate"])
        return [x for x in out if x]

    # ------------------------------------------------------------------
    def _battery_tick(self) -> None:
        bcfg = self.cfg["battery"]
        if self.state == "CHARGING":
            rate = self.wmap.nodes.get("C1", None)
            self.battery = min(100.0, self.battery + bcfg["charge_rate_pct_s"] * self.tick_period)
            self.counters["charge_s"] += self.tick_period
            if self.battery >= 85.0:
                self.state = "IDLE"
                self.emit("charge_done", {"battery": round(self.battery, 1)})
            return
        drain = bcfg["move_drain_pct_s"] if self.speed > 0.01 else bcfg["idle_drain_pct_s"]
        self.battery = max(0.0, self.battery - drain * self.tick_period)
        self.counters["energy_j"] += (0.6 if self.speed > 0.01 else 0.2) * self.tick_period
        if self.battery < bcfg["critical_threshold"] and self.state not in ("FAILED", "TO_CHARGE", "CHARGING"):
            self._abort_task_for_charge()
        elif self.battery < bcfg["low_threshold"] and self.task is None and self.state == "IDLE":
            self._goto_charge()

    def _abort_task_for_charge(self) -> None:
        if self.task is not None:
            self.emit("task_aborted", {"task_id": self.task["task_id"], "reason": "BATTERY"})
            self.plane.publish(f"fleet/task/{self.task['task_id']}", {
                "task_id": self.task["task_id"], "state": "ABORTED", "robot": self.id,
                "t": round(self.t, 3)})
            self.task = None
        self._goto_charge()
        self.publish_context("BATTERY_CRITICAL", self.id, ttl=10.0, affected=[self.id])

    def _goto_charge(self) -> None:
        self.state = "TO_CHARGE"
        self.task_phase = None
        self._plan_route(self.wmap.charge_node())

    def _zone_slot(self) -> int:
        """Deterministic parking slot at my current zone node (rid order)."""
        parked = [rid for rid, hb in self.peers.items()
                  if hb.get("node") == self.node]
        parked.append(self.id)
        parked = sorted(set(parked))
        return parked.index(self.id)

    def _stop_wait(self) -> None:
        dur = self.fairness.stop_wait(self.t)
        if dur > 0.2:
            self.emit("wait_episode", {"duration": round(dur, 2)})

    def _dwell(self) -> None:
        if self.state in ("DOCK", "CHARGING", "FAILED"):
            if self.state == "DOCK" and self.t >= self.dwell_until:
                self._finish_dock()

    def _finish_dock(self) -> None:
        target = self.task["pickup"] if self.task_phase == "pickup" else self.task["drop"]
        if self.node != target:
            return          # safety: never finish a dock we did not reach
        if self.task_phase == "pickup":
            self.task_phase = "drop"
            self.state = "TO_DROP"
            self._plan_route(self.task["drop"])
            self.emit("task_phase", {"task_id": self.task["task_id"], "phase": "drop"})
        else:
            self.counters["tasks_done"] += 1
            tid = self.task["task_id"]
            self.task = None
            self.task_phase = None
            self.state = "IDLE"
            self.plane.publish(f"fleet/task/{tid}", {
                "task_id": tid, "state": "DONE", "robot": self.id, "t": round(self.t, 3)})
            self.emit("task_done", {"task_id": tid})

    # ------------------------------------------------------------------
    def _pos_dict(self) -> Dict:
        if self.node is not None:
            return {"node": self.node}
        return {"edge": self.edge, "s": self.s, "dir": self.dir}

    def _congestion_view(self) -> Dict[str, float]:
        """Congestion estimate per resource: predicted occupancy from JEC states
        (which run the Edge-AI congestion predictor) + observed occupancy."""
        view: Dict[str, float] = {}
        for jid, st in self.jec_states.items():
            if st.get("_offline"):
                continue
            pred = st.get("predicted", {})
            for res, occ in pred.items():
                view[res] = max(view.get(res, 0.0), float(occ))
            cong = st.get("congestion", 0.0)
            j = st.get("junction", "")
            if j:
                view[j] = max(view.get(j, 0.0), float(cong))
        # observed occupancy (heartbeats) for edges without JEC coverage
        for eid in self.wmap.edges:
            view.setdefault(eid, self._edge_occupancy(eid))
        for gate in self.wmap.aisles:
            view.setdefault(gate, self._gate_occupancy(gate))
        return view

    def _edge_occupancy(self, eid: str) -> int:
        n = 0
        e = self.wmap.edges.get(eid)
        bay_nodes = {nb for nb in (e.u, e.v) if self.wmap.nodes[nb].is_bay} if e else set()
        for rid, hb in self.peers.items():
            if hb.get("state") == "FAILED":
                continue
            if hb.get("edge") == eid:
                n += 1
            elif e and e.is_narrow and hb.get("node") in bay_nodes:
                n += 1          # docked at a bay physically blocks the aisle
        return n

    def _gate_occupancy(self, gate: str) -> int:
        edges = self.wmap.gate_edges(gate)
        return sum(1 for rid, hb in self.peers.items()
                   if hb.get("edge") in edges and hb.get("state") != "FAILED")

    def _route_congestion(self, route: R.Route) -> float:
        """Estimated congestion cost along a route (for auction bids)."""
        if not route:
            return 0.0
        view = self._congestion_view()
        total = 0.0
        for st in route:
            e = self.wmap.edges[st["edge"]]
            total += view.get(e.id, 0.0) * (1.0 if e.capacity <= 2 else 0.5)
            if e.aisle:
                total += view.get(e.aisle, 0.0)
        return round(total, 2)

    def _blocked_edges(self) -> set:
        blocked = set()
        for ev in self.active_context("AISLE_BLOCKED"):
            blocked.update(ev.affected)
            if ev.value in self.wmap.edges:
                blocked.add(ev.value)
            if ev.value in self.wmap.aisles:
                blocked.update(self.wmap.gate_edges(ev.value))
        return blocked

    # ------------------------------------------------------------------
    def _check_route_invariant(self, where: str) -> None:
        """Debug invariant: route[0] must be enterable from where we are."""
        if self.node is not None:
            if self.route:
                st = self.route[0]
                e = self.wmap.edges[st["edge"]]
                start = e.u if st["dir"] > 0 else e.v
                if start != self.node:
                    self.emit("route_bug", {"where": where, "node": self.node,
                                            "route0": st["edge"],
                                            "route0_start": start})
        else:
            if self.route:
                head = self.wmap.node_of_edge_end(self.edge, self.dir)
                # route may start at head OR at tail (reversal handled at edge end)
                st = self.route[0]
                e = self.wmap.edges[st["edge"]]
                start = e.u if st["dir"] > 0 else e.v
                tail = self.wmap.node_of_edge_end(self.edge, -self.dir)
                if start not in (head, tail):
                    self.emit("route_bug", {"where": where, "edge": self.edge,
                                            "s": round(self.s, 2), "dir": self.dir,
                                            "route0": st["edge"],
                                            "route0_start": start})

    def _plan_route(self, goal: str) -> None:
        """Full planning: candidates -> prosocial choice -> route.

        Route convention: `self.route` lists steps AFTER the current edge
        (while mid-edge, route[0] is the edge entered next); at a node,
        route[0] is the edge about to be entered.
        """
        if self.node is None and self.edge is None:
            return
        congestion = self._congestion_view() if self.flags.prosocial else {}
        blocked = self._blocked_edges()
        others = self.intents if self.flags.prosocial else {}

        if self.node is not None:
            candidates = R.k_alternatives(self.wmap, self.node, goal, congestion, blocked)
            start_s = 0.0
            own_lead = 0.0
        else:
            e = self.wmap.edges[self.edge]
            head = self.wmap.node_of_edge_end(self.edge, self.dir)      # ahead
            tail = self.wmap.node_of_edge_end(self.edge, -self.dir)     # behind
            no_uturn = blocked | {self.edge}      # never re-enter own edge at once
            fwd = R.k_alternatives(self.wmap, head, goal, congestion, no_uturn)
            if not fwd:                             # fall back to allowing it
                fwd = R.k_alternatives(self.wmap, head, goal, congestion, blocked)
            rev = R.k_alternatives(self.wmap, tail, goal, congestion, blocked) \
                if not e.is_narrow else []          # never reverse inside racks
            start_s = 0.0
            own_lead = (e.length - self.s) / max(0.1, e.speed)   # reach head
            # choose direction: reversal wins only if clearly better
            # (hysteresis prevents oscillation)
            fwd_time = min((R.route_time(self.wmap, c) for c in fwd), default=1e9)
            rev_time = min((R.route_time(self.wmap, c) for c in rev), default=1e9)
            rev_lead = self.s / max(0.1, e.speed)                 # reverse to tail
            use_rev = bool(rev) and (not fwd or self.edge in blocked or
                                     rev_lead + rev_time < own_lead + fwd_time - 1.5)
            if use_rev:
                # execute the reversal: flip direction, s measured in new dir
                self.dir *= -1
                self.s = max(0.0, e.length - self.s)
                candidates = rev
                own_lead = rev_lead
                self.counters["replans"] += 1
                self.emit("reversal", {"edge": self.edge,
                                       "reason": "better_via_tail"})
            else:
                candidates = fwd
        if not candidates:
            self.route = []
            return

        best, cost, expl = choose_route(self.wmap, candidates, self.weights,
                                        others, congestion, horizon=self.horizon,
                                        start_s=start_s)
        # prepend current-edge remainder info to own cost for the explainer
        for e_expl in expl:
            e_expl["breakdown"]["own_cost"] = round(
                e_expl["breakdown"]["own_cost"] + own_lead, 2)
            e_expl["breakdown"]["total"] = round(
                e_expl["breakdown"]["total"] + self.weights.distance * own_lead, 2)
        cost.own += own_lead
        self.route = best
        self._check_route_invariant("plan")
        self.counters["replans"] += 1
        self.emit("decision", self._decision_payload(best, cost, expl, goal))

    def _decision_payload(self, best, cost, expl, goal) -> Dict:
        chosen = [st["edge"] for st in best]
        greedy = expl[0]["route"] if expl else chosen
        return {
            "goal": goal, "chosen": chosen, "candidates": expl,
            "greedy_route": greedy, "prosocial": self.flags.prosocial,
            "weights": vars(self.weights), "mode": self.flags.mode,
        }

    def _replan_maybe(self) -> None:
        if not self.route or not self.flags.prosocial:
            return
        self._replan_accum += self.tick_period
        if self._replan_accum < REPLAN_INTERVAL:
            return
        self._replan_accum = 0.0
        goal = self._current_goal()
        if goal is None:
            return
        # replan if any route resource is congested (predicted) or newly blocked
        congested = False
        view = self._congestion_view()
        for st in self.route[:4]:
            e = self.wmap.edges[st["edge"]]
            if view.get(e.id, 0) >= max(1, e.capacity) and e.capacity <= 2:
                congested = True
            if e.aisle and view.get(e.aisle, 0) >= 1:
                congested = True
        blocked = self._blocked_edges()
        route_edges = {st["edge"] for st in self.route}
        if congested or (blocked & route_edges):
            self._plan_route(goal)

    def _current_goal(self) -> Optional[str]:
        if self.task is not None:
            return self.task["pickup"] if self.task_phase == "pickup" else self.task["drop"]
        if self.state == "TO_CHARGE":
            return self.wmap.charge_node()
        return None

    # ==================================================================
    # reservations / gates
    # ==================================================================
    def _request_reservations(self) -> None:
        """Approaching shared resources: request JEC grants or P2P claims."""
        if self.state == "FAILED" or not self.route:
            return
        if self.flags.stop_and_wait or self.flags.reactive_only:
            return          # modes A/B: no reservations, no claims, no intents
        lead = self.cfg["reservation"]["request_lead_m"]
        resv_cfg = self.cfg["reservation"]

        # next step (mid-edge: current edge remainder; else route[0])
        if self.node is None and self.route:
            next_edge, next_dir = self.edge, self.dir
            dist_to_end = self.wmap.edges[self.edge].length - self.s
        elif self.route:
            next_edge, next_dir = self.route[0]["edge"], self.route[0]["dir"]
            dist_to_end = 0.0
        else:
            return

        approaching = (self.node is None and dist_to_end <= lead) or self.node is not None
        if not approaching:
            return

        # --- gate request for the NEXT aisle entry (route[0]'s gate — the
        # gate of the CURRENT edge is already held by us while traversing)
        gate_target_edge = self.route[0]["edge"] if self.route else next_edge
        gate = self.wmap.edge_to_gate(gate_target_edge)
        if gate:
            jec = self.wmap.jec_for_gate(gate)
            if jec and self.flags.use_jec and not self._jec_down(jec):
                self._request_jec_gate(jec, gate, self.route[0]["dir"])
            else:
                self._p2p_gate_claim(gate, self.route[0]["dir"])

        # --- junction request for the node we are about to cross
        next_node = self.wmap.node_of_edge_end(next_edge, next_dir)
        if self.wmap.nodes[next_node].is_junction:
            jec = self.wmap.jec_for_junction(next_node) if self.flags.use_jec else None
            if jec and not self._jec_down(jec):
                self._request_jec_reservation(jec, next_node, next_edge, next_dir)
            elif self.flags.share_intent:
                self._p2p_junction_check(next_node)

    def _gate_covered(self, gate: str) -> bool:
        """JEC-managed gate with a live JEC -> handled by JEC reservation flow."""
        jec = self.wmap.jec_for_gate(gate)
        return bool(jec and self.flags.use_jec and not self._jec_down(jec))

    def _request_jec_gate(self, jec: str, gate: str, dir_: int) -> None:
        """Request the narrow-aisle direction grant from the owning JEC."""
        have = self.reservations.get(gate)
        window = self._gate_window(gate)
        if have and have.get("state") in (RESV_GRANTED, RESV_ACTIVE) and have.get("dir") == dir_:
            return
        last_req = self.resv_pending.get(gate, -10)
        if self.t - last_req < 0.8:
            return
        self.resv_pending[gate] = self.t
        pr = effective_priority(self.fairness, self.fair_cfg, self.t)
        self.plane.publish(f"fleet/robot/{self.id}/resv_req", {
            "robot": self.id, "t": round(self.t, 3), "resource": gate,
            "start": round(window[0], 3), "end": round(window[1], 3),
            "priority": round(pr, 2), "lease": self.cfg["reservation"]["lease_s"],
            "dir": dir_, "jec": jec, "gate": True,
        })

    def _jec_down(self, jec: str) -> bool:
        st = self.jec_states.get(jec)
        if st is None:
            # never heard: allow 2.5s discovery grace from process start
            return (self.t > JEC_OFFLINE_AFTER) and (jec not in self.jec_last_hb)
        return bool(st.get("_offline"))

    def _request_jec_reservation(self, jec: str, junction: str,
                                 next_edge: str, next_dir: int) -> None:
        have = self.reservations.get(junction)
        eta = self._eta_to_node(next_edge, next_dir)
        service = self.cfg["reservation"]["junction_service_s"]
        start = self.t + eta
        end = start + service
        if have and have.get("state") in (RESV_GRANTED, RESV_ACTIVE) and have.get("end", 0) > self.t + 0.2:
            if abs(have.get("start", 0) - start) < 1.0:
                return                      # grant still valid
        last_req = self.resv_pending.get(junction, -10)
        if self.t - last_req < 0.8:
            return
        self.resv_pending[junction] = self.t
        pr = effective_priority(self.fairness, self.fair_cfg, self.t)
        self.plane.publish(f"fleet/robot/{self.id}/resv_req", {
            "robot": self.id, "t": round(self.t, 3), "resource": junction,
            "start": round(start, 3), "end": round(end, 3),
            "priority": round(pr, 2), "lease": self.cfg["reservation"]["lease_s"],
            "edge": next_edge, "dir": next_dir, "jec": jec,
        })

    def _eta_to_node(self, edge: str, dir_: int) -> float:
        e = self.wmap.edges[edge]
        remain = (e.length - self.s) if (self.node is None and edge == self.edge and dir_ == self.dir) else e.length
        return max(0.0, remain) / max(0.1, e.speed)

    def _p2p_gate_claim(self, gate: str, dir_: int) -> None:
        """P2P narrow-aisle direction claim (also the JEC-down fallback)."""
        last = self._last_gate_claim.get(gate, -10.0)
        if self.t - last < 1.0:
            return                          # claim cooldown: no flooding
        self._last_gate_claim[gate] = self.t
        pr = effective_priority(self.fairness, self.fair_cfg, self.t)
        window = self._gate_window(gate)
        self.plane.publish(f"fleet/gate/{gate}/claim", {
            "robot": self.id, "t": round(self.t, 3), "gate": gate, "dir": dir_,
            "priority": round(pr, 2), "start": round(window[0], 3),
            "end": round(window[1], 3),
        })
        self._gate_claim_sent = (gate, dir_, self.t)

    _gate_claim_sent: Tuple = ()
    _last_gate_claim: Dict[str, float] = {}

    def _gate_window(self, gate: str) -> Tuple[float, float]:
        edges = self.wmap.aisles[gate].edges
        total = sum(self.wmap.edges[e].length / self.wmap.edges[e].speed for e in edges)
        return (self.t, self.t + total)

    def _p2p_junction_check(self, junction: str) -> None:
        """P2P junctions: deterministic ordering by intents; emit conflict cell."""
        my_eta = self._eta_to_node(self.route[0]["edge"], self.route[0]["dir"]) if self.route else 0
        service = self.cfg["reservation"]["junction_service_s"]
        mine = (self.t + my_eta, self.t + my_eta + service)
        contenders = []
        for rid, intent in self.intents.items():
            for tgt in intent.get("targets", []):
                if tgt.get("resource") == junction:
                    t0 = self.t + max(0.0, tgt.get("eta", 0.0))
                    if t0 < mine[1] and (t0 + tgt.get("dur", 1.5)) > mine[0]:
                        contenders.append((rid, intent.get("urgency", 0.0)))
        my_pr = effective_priority(self.fairness, self.fair_cfg, self.t)
        i_win = True
        for rid, urg in contenders:
            other_pr = self.peers.get(rid, {}).get("effective_priority", 1.0)
            if (other_pr, [-ord(c) for c in rid]) > (my_pr, [-ord(c) for c in self.id]):
                i_win = False
                break
        if contenders:
            members = sorted([self.id] + [c[0] for c in contenders])
            cell = f"CC-{junction}-" + ",".join(members)
            if i_win or self.id == members[0]:
                self.plane.publish(f"fleet/conflict/{cell}", {
                    "cell": cell, "resource": junction, "members": members,
                    "t": round(self.t, 3), "emitter": self.id,
                    "mode": "P2P",
                })
        self._p2p_junction_win = i_win

    _p2p_junction_win: bool = True

    # ==================================================================
    # movement execution with deterministic safety vetoes
    # ==================================================================
    def _execute_movement(self) -> None:
        dt = self.tick_period
        if self.state == "FAILED":
            self.speed = 0.0
            return
        if self.state == "CHARGING" or self.state == "DOCK":
            self.speed = 0.0
            self._heartbeat_carry(dt)
            return
        if self.node is not None:
            self._at_node_transition()
            if self.state == "CHARGING" or self.state == "DOCK" or self.state == "FAILED":
                return
        if self.node is None and self.route:
            self._advance(dt)
        elif self.node is None and not self.route:
            # stuck mid-edge without a route (e.g. fully blocked) — creep to
            # the end node then idle there
            self._advance(dt)

    def _at_node_transition(self) -> None:
        """At a node: start next route step or complete phase."""
        # phase completion
        if self.task is not None and self.task_phase is not None and self.node == self._current_goal():
            self._enter_dock()
            return
        if self.state == "TO_CHARGE" and self.node == self.wmap.charge_node():
            cnode = self.wmap.nodes[self.node]
            occ = sum(1 for hb in self.peers.values()
                      if hb.get("node") == self.node and hb.get("state") == "CHARGING")
            if occ < cnode.capacity:
                self.state = "CHARGING"
                self.emit("charging", {"battery": round(self.battery, 1)})
            else:
                self.fairness.start_wait(self.t)
                self.counters["waiting_s"] += self.tick_period
                self._veto(S.VETO_CAPACITY, {"node": self.node, "zone": "charge"})
            return
        if not self.route:
            if self.state not in ("IDLE",):
                self.state = "IDLE"
            # housekeeping: idle robots vacate dock zones -> staging, so
            # queue slots free up for the next deliveries
            if (self.task is None and self.state == "IDLE"
                    and self.wmap.nodes[self.node].type in ("pickup", "drop")
                    and not self._vacate_since):
                self._vacate_since = self.t
            elif (self.task is None and self.state == "IDLE"
                    and self._vacate_since
                    and self.t - self._vacate_since > 4.0
                    and self.wmap.nodes[self.node].type in ("pickup", "drop")):
                staging = self.wmap.staging_nodes()[0] if self.wmap.staging_nodes() else None
                if staging and staging != self.node:
                    self._vacate_since = None
                    self._zone_depart_ok = True
                    self._plan_route(staging)
                    if self.route:
                        self.state = "MOVING"
                        self.emit("reposition", {"to": staging})
            return
        # parked at a node too long: replan (stale blocked route[0])
        if self.fairness.wait_since > 0 and \
                (self.t - self.fairness.wait_since) > 15.0:
            goal = self._current_goal()
            if goal is not None:
                self._replan_accum += self.tick_period
                if self._replan_accum > 1.0:
                    self._replan_accum = 0.0
                    self._plan_route(goal)
        st = self.route[0]
        eid, dirn = st["edge"], st["dir"]
        e = self.wmap.edges[eid]
        # departure clearance from zones: stagger departures so robots
        # leaving via different spurs never start overlapped
        if self.wmap.nodes[self.node].is_zone:
            cx, cy = self.wmap.node_pos(self.node)
            for rid, hb in self.peers.items():
                if hb.get("node") == self.node and hb.get("speed", 0) < 0.05:
                    continue          # co-parked robots at their own slots
                d = math.hypot(hb["pos"][0] - cx, hb["pos"][1] - cy)
                if d < 1.15:
                    self.fairness.start_wait(self.t)
                    self.counters["waiting_s"] += self.tick_period
                    self._veto(S.VETO_SEPARATION, {"peer": rid, "value": round(d, 2),
                                                   "detail": "zone_departure"})
                    return
        # blocked?
        if e.id in self._blocked_edges() or e.blocked:
            self.fairness.start_wait(self.t)
            self.counters["waiting_s"] += self.tick_period
            self._maybe_replan_blocked(eid)
            return
        # gate check
        gate = self.wmap.edge_to_gate(eid)
        gate_ok, gate_dir = self._gate_permission(gate, dirn) if gate else (True, None)
        # junction reservation check (JEC junctions only)
        next_node = self.wmap.node_of_edge_end(eid, dirn)
        need_resv = self.wmap.nodes[next_node].is_junction
        jec = self.wmap.jec_for_junction(next_node) if (need_resv and self.flags.use_jec) else None
        resv_ok = True
        if jec and not self._jec_down(jec):
            resv_ok = self.reservations.get(next_node, {}).get("state") in (RESV_GRANTED, RESV_ACTIVE) \
                or self._junction_empty_p2p(next_node)
            if not resv_ok:
                # safety-layer demo: bad entry rejected deterministically
                self._veto(S.VETO_RESERVATION, {"junction": next_node, "jec": jec})
        # occupancy of target edge (mode A: any occupant blocks)
        occ = self._edge_occupancy(eid)
        cap_ok = occ < e.capacity if not self.flags.stop_and_wait else occ == 0
        p2p_win = self._p2p_junction_win if need_resv and not jec else True

        if gate_ok and resv_ok and cap_ok and p2p_win:
            # enter edge
            self.node = None
            self.edge = eid
            self.s = 0.0
            self.dir = dirn
            self.route = self.route[1:]
            self._check_route_invariant("enter_edge")
            self._reversing = False
            self.state = self._moving_state()
            self._stop_wait()
            self._clear_vetoes()
            self._p2p_junction_win = True
        else:
            self.fairness.start_wait(self.t)
            self.counters["waiting_s"] += self.tick_period
            if not gate_ok:
                self._veto(S.VETO_DIRECTION, {"gate": gate, "gate_dir": gate_dir, "my_dir": dirn})
                now_last = self._last_yield_reg.get(gate, -10.0)
                if self.t - now_last > 1.0:
                    self._last_yield_reg[gate] = self.t
                    self.fairness.register_yield()
                    self.counters["yields"] += 1
            elif not cap_ok:
                self._veto(S.VETO_CAPACITY, {"edge": eid, "occupants": occ, "capacity": e.capacity})

    def _maybe_replan_blocked(self, eid: str) -> None:
        self._replan_accum += self.tick_period
        if self._replan_accum > 0.8:
            self._replan_accum = 0.0
            goal = self._current_goal() or self.node
            self._plan_route(goal)

    def _enter_dock(self) -> None:
        n = self.wmap.nodes[self.node]
        if n.capacity > 0:
            dock_edges = {eid for eid, _ in self.wmap.adj[self.node]}
            occ = sum(1 for hb in self.peers.values()
                      if (hb.get("node") == self.node) or
                      (hb.get("edge") in dock_edges and hb.get("state") in ("DOCK",)))
            if occ >= n.capacity:
                self.fairness.start_wait(self.t)
                self.counters["waiting_s"] += self.tick_period
                self._veto(S.VETO_CAPACITY, {"node": self.node, "zone": "dock"})
                return
        goal_kind = n.type
        dwell = (self.wmap.bay_dwell_pick if self.task_phase == "pickup"
                 else self.wmap.bay_dwell_drop)
        if goal_kind in ("pickup", "drop"):
            dwell = 2.0
        self.state = "DOCK"
        self.dwell_until = self.t + dwell
        self.route = []
        self.emit("docked", {"node": self.node, "phase": self.task_phase,
                             "dwell_s": dwell})

    def _moving_state(self) -> RobotState:
        if self.state == "TO_CHARGE":
            return "TO_CHARGE"
        if self.task is not None:
            return "TO_PICKUP" if self.task_phase == "pickup" else "TO_DROP"
        return "MOVING"

    # ------------------------------------------------------------------
    MAX_ACCEL = 0.8          # m/s^2 — realistic AMR acceleration limit

    def _advance(self, dt: float) -> None:
        e = self.wmap.edges[self.edge]
        nominal = e.speed
        # slow zone: within 3m of the edge end node, cap speed (junction care)
        remain = e.length - self.s
        end_node = self.wmap.node_of_edge_end(self.edge, self.dir)
        if remain < 3.0 and self.wmap.nodes[end_node].type in ("junction", "bay"):
            nominal = min(nominal, 0.8)
        if self._reversing:
            nominal = min(nominal, 0.5)      # cautious reverse
            if remain > 3.0 or (self.speed > 0 and self.t - (self._rev_started or self.t) > 3.0):
                self._reversing = False
            else:
                # peers in the reverse direction are 'leaders': never
                # sweep into them (cap speed, do NOT abort the tick)
                from ..fleet_core.safety import _heading
                try:
                    rh = _heading(self.wmap, self.edge, -self.dir)
                except KeyError:
                    rh = (0.0, 0.0)
                me = self.position()
                for rid, hb in self.peers.items():
                    dx = hb["pos"][0] - me[0]
                    dy = hb["pos"][1] - me[1]
                    d = math.hypot(dx, dy)
                    if d < 2.2 and (dx * rh[0] + dy * rh[1]) > 0:
                        nominal = max(0.0, min(nominal, (d - 1.4) * 1.0))
                        break
        v = self._desired_speed(nominal)
        # acceleration limit: never jump more than MAX_ACCEL*dt per tick
        dv = v - self.speed
        if dv > self.MAX_ACCEL * dt:
            v = self.speed + self.MAX_ACCEL * dt
        elif dv < -3.0 * self.MAX_ACCEL * dt:
            v = self.speed - 3.0 * self.MAX_ACCEL * dt   # brakes 3x stronger
        # safety validation
        vetoes = self._safety_vetoes(v)
        if vetoes:
            v = 0.0
            self.counters["vetoes"] += len(vetoes)
            self.fairness.start_wait(self.t)
            self.counters["waiting_s"] += self.tick_period
        # starvation watchdog: if starving, bump urgency (priority inversion)
        if is_starving(self.fairness, self.fair_cfg, self.t):
            self.fairness.urgency = min(3.0, self.fairness.urgency + 0.1)
        self.speed = v
        if v > 0:
            self._stuck_since = None          # moving: clear stuck timer
            self.s += v * dt
            moved = v * dt
            self.counters["distance_m"] += moved
            self.counters["move_s"] += dt
        # separation monitoring: collision (< 0.5m, robot bodies overlap) vs
        # near-miss (< 0.74m, unsafe proximity) — both edge-triggered per peer
        me = self.position()
        for rid, hb in self.peers.items():
            d = math.hypot(hb["pos"][0] - me[0], hb["pos"][1] - me[1])
            self._min_gap_seen = min(self._min_gap_seen, d)
            if d < 0.5 and rid not in self._collision_latched:
                self._collision_latched.add(rid)
                self.counters["collisions"] += 1
                self.emit("collision", {"peer": rid, "gap": round(d, 2),
                                        "my": [round(me[0], 2), round(me[1], 2)],
                                        "my_edge": self.edge, "my_s": round(self.s, 2),
                                        "my_dir": self.dir, "my_node": self.node,
                                        "peer_pos": hb["pos"], "peer_edge": hb.get("edge"),
                                        "peer_s": hb.get("s"), "peer_dir": hb.get("dir"),
                                        "peer_node": hb.get("node"),
                                        "peer_age": round(self.t - hb.get("t", self.t), 2)})
            elif d < 0.74 and rid not in self._nearmiss_latched:
                self._nearmiss_latched.add(rid)
                self.counters["near_misses"] = self.counters.get("near_misses", 0) + 1
                self.emit("collision_risk", {"peer": rid, "gap": round(d, 2)})
            elif d > 1.2:
                self._collision_latched.discard(rid)
                self._nearmiss_latched.discard(rid)
        # ---- generic stuck recovery: blocked > 8s on a WIDE edge (edge
        # capacity cycle) -> reverse and replan around
        if v == 0.0 and self.route and self.edge is not None:
            if self._stuck_since is None:
                self._stuck_since = self.t
            e_now = self.wmap.edges[self.edge]
            if not e_now.is_narrow:
                if self.t - self._stuck_since > 30.0 and self._rear_clear(5.0):
                    self.counters["deadlock_backouts"] = self.counters.get("deadlock_backouts", 0) + 1
                    self.emit("deadlock_backout", {"edge": self.edge, "opposing": False,
                                                   "reason": "edge_capacity_cycle"})
                    self._reversing = True
                    self._rev_started = self.t
                    self.dir *= -1
                    self.s = max(0.0, e_now.length - self.s)
                    entry = self.wmap.node_of_edge_end(self.edge, self.dir)
                    goal = self._current_goal() or entry
                    rest = R.astar(self.wmap, entry, goal) or []
                    self.route = rest
                    self._stuck_since = None
                    return
        # ---- narrow-aisle deadlock recovery (back out): opposing occupant
        # OR exit blocked while stuck inside the aisle
        if v == 0.0 and self.wmap.edge_to_gate(self.edge or ""):
            gate = self.wmap.edge_to_gate(self.edge)
            opposing = self._gate_occupant_dir(gate, exclude=self.id)
            my_dir_sign = 1 if (self.wmap.nodes[e.v].y - self.wmap.nodes[e.u].y) * self.dir > 0 else -1
            head_on = opposing is not None and opposing != my_dir_sign
            exit_blocked = bool(self.route) and self.t - (self._stuck_since or self.t) > 0
            if head_on or exit_blocked:
                if self._stuck_since is None:
                    self._stuck_since = self.t
                elif self.t - self._stuck_since > 6.0 and self._rear_clear(4.0):
                    self.counters["deadlock_backouts"] = self.counters.get("deadlock_backouts", 0) + 1
                    self.emit("deadlock_backout", {"edge": self.edge, "opposing": True})
                    self._reversing = True
                    self._rev_started = self.t
                    self.dir *= -1          # reverse out of the aisle
                    self.s = max(0.0, e.length - self.s)
                    entry = self.wmap.node_of_edge_end(self.edge, self.dir)
                    goal = self._current_goal() or entry
                    rest = R.astar(self.wmap, entry, goal) or []
                    self.route = rest
                    self._stuck_since = None
                    return

        # edge end?
        if self.s >= e.length:
            end_node = self.wmap.node_of_edge_end(self.edge, self.dir)
            self.last_edge = self.edge
            self.entry_dir = self.dir
            self.node = end_node
            self.edge = None
            self.s = 0.0
            # release junction reservation of the node we just crossed
            self._release_crossed_reservations(end_node)
            self._at_node_transition()

    def _rear_clear(self, radius: float = 2.6) -> bool:
        """No peer within `radius` behind my position (safe to reverse)."""
        from ..fleet_core.safety import _heading
        try:
            h = _heading(self.wmap, self.edge, -self.dir)   # reverse heading
        except KeyError:
            return True
        me = self.position()
        for rid, hb in self.peers.items():
            dx = hb["pos"][0] - me[0]
            dy = hb["pos"][1] - me[1]
            if math.hypot(dx, dy) < radius and (dx * h[0] + dy * h[1]) > 0:
                return False
        return True

    def _desired_speed(self, nominal: float) -> float:
        """Car-following: slow for the nearest leader ahead — same edge OR
        collinear adjacent edges through a junction (geometric following).
        Keeps a 1.2m standstill gap (heartbeat staleness headroom)."""
        me_pos = self.position()
        try:
            from ..fleet_core.safety import _heading
            h = _heading(self.wmap, self.edge, self.dir)
        except Exception:                     # noqa: BLE001
            h = (1.0, 0.0)
        best_gap = None
        for rid, hb in self.peers.items():
            pe = hb.get("edge") or ""
            if not pe or hb.get("state") == "FAILED":
                continue
            dx = hb["pos"][0] - me_pos[0]
            dy = hb["pos"][1] - me_pos[1]
            d = math.hypot(dx, dy)
            if d > 3.5:
                continue
            along = dx * h[0] + dy * h[1]          # >0: peer ahead of me
            if along <= 0.05:
                continue                            # peer behind/aside
            try:
                h2 = _heading(self.wmap, pe, hb.get("dir", 1))
            except Exception:                     # noqa: BLE001
                continue
            if h[0] * h2[0] + h[1] * h2[1] < 0.9:
                continue                            # crossing traffic, not a leader
            best_gap = d if best_gap is None else min(best_gap, d)
        if best_gap is not None and best_gap < self.safety_cfg.slow_separation_m * 1.6:
            return max(0.0, min(nominal, (best_gap - 1.2) * 1.2))
        return nominal

    def _safety_vetoes(self, v: float) -> List[Dict]:
        peers = [S.PeerView.from_heartbeat(hb) for hb in self.peers.values()]
        me = S.PeerView(rid=self.id, x=self.position()[0], y=self.position()[1],
                        speed=v, edge=self.edge or "", dir=self.dir,
                        urgency=self.fairness.urgency,
                        effective_priority=effective_priority(self.fairness, self.fair_cfg, self.t),
                        state=self.state)
        next_edge, next_dir = (self.edge, self.dir)
        occ = self._edge_occupancy(next_edge)
        gate = self.wmap.edge_to_gate(next_edge)
        _, gate_dir = self._gate_permission(gate, next_dir) if gate else (True, None)
        need_resv = False
        resv_ok = True
        nn = self.wmap.node_of_edge_end(next_edge, next_dir)
        if self.wmap.nodes[nn].is_junction:
            jec = self.wmap.jec_for_junction(nn) if self.flags.use_jec else None
            if jec and not self._jec_down(jec):
                need_resv = True
                resv_ok = self.reservations.get(nn, {}).get("state") in (RESV_GRANTED, RESV_ACTIVE)
                # grant OR backstop: junction physically empty (safety floor)
                if not resv_ok and self._junction_empty_p2p(nn):
                    resv_ok = True
                    need_resv = False
        vetoes = S.validate_step(self.wmap, me, peers, next_edge, next_dir, occ,
                                 gate_dir, need_resv, resv_ok, self.safety_cfg)
        # junction-cell admission BEFORE the box; once inside (committed),
        # right-of-way carries the crossing through
        if self.wmap.nodes[nn].is_junction:
            e_len = self.wmap.edges[next_edge].length
            box_r = self.wmap.junction_box * 1.1
            dist_to_end = (e_len - self.s) if next_edge == self.edge else e_len
            if box_r < dist_to_end < 2.5 and not self._junction_clear_for_arrival(nn):
                vetoes.append({"rule": S.VETO_CAPACITY, "junction": nn,
                               "detail": "junction_box_occupied"})
        # pre-admission for the NEXT edge: stop before the node when the next
        # edge cannot be entered (capacity / gate) — never park at a junction
        if self.route and next_edge == self.edge:
            e_len = self.wmap.edges[self.edge].length
            remain = e_len - self.s
            if remain < 1.6:
                nst = self.route[0]
                ne = self.wmap.edges.get(nst["edge"])
                if ne is not None:
                    occ_next = self._edge_occupancy(ne.id)
                    if occ_next >= ne.capacity:
                        vetoes.append({"rule": S.VETO_CAPACITY, "edge": ne.id,
                                       "occupants": occ_next, "capacity": ne.capacity,
                                       "detail": "next_edge_full"})
                    ngate = self.wmap.edge_to_gate(ne.id)
                    if ngate:
                        gok, gd = self._gate_permission(ngate, nst["dir"])
                        if not gok:
                            vetoes.append({"rule": S.VETO_DIRECTION, "gate": ngate,
                                           "gate_dir": gd, "my_dir": nst["dir"],
                                           "detail": "next_edge_gate"})
        for vt in vetoes:
            self._veto(vt["rule"], vt)
        return vetoes

    def _junction_clear_for_arrival(self, node: str) -> bool:
        """Deterministic junction-cell admission (checked BEFORE the box).

        A peer blocks my entry if it (a) is parked AT the junction node, (b)
        is a committed crosser INSIDE the box (moving, or stopped near the
        centre, or holding a stronger claim), or (c) is approaching this
        junction and holds an equal/stronger claim. My own lane leader
        (convoy) never blocks me.
        """
        from ..fleet_core.safety import _heading
        nx, ny = self.wmap.node_pos(node)
        box = self.wmap.junction_box * 1.1
        me_pr = effective_priority(self.fairness, self.fair_cfg, self.t)
        try:
            my_head = _heading(self.wmap, self.edge, self.dir) if self.edge else (0.0, 0.0)
        except KeyError:
            my_head = (0.0, 0.0)
        me_x, me_y = self.position()
        for rid, hb in self.peers.items():
            if hb.get("state") == "FAILED":
                continue
            if hb.get("node") == node:
                return False                      # parked at the junction node
            d = math.hypot(hb["pos"][0] - nx, hb["pos"][1] - ny)
            pe = hb.get("edge") or ""
            if pe and my_head != (0.0, 0.0):
                try:
                    h2 = _heading(self.wmap, pe, hb.get("dir", 1))
                    if my_head[0] * h2[0] + my_head[1] * h2[1] > 0.9:
                        dx = hb["pos"][0] - me_x
                        dy = hb["pos"][1] - me_y
                        if d < 3.5 and (dx * my_head[0] + dy * my_head[1]) > 0:
                            continue              # my lane leader (convoy)
                except KeyError:
                    pass
            if d < box:
                # is this peer still heading INTO my junction? (departing
                # crossers inside the box do not block arrivals)
                approaching_me = False
                if pe:
                    pd2 = hb.get("dir", 1)
                    try:
                        approaching_me = (self.wmap.node_of_edge_end(pe, pd2) == node)
                    except KeyError:
                        approaching_me = False
                moving = hb.get("speed", 0.0) > 0.05
                other_pr = hb.get("effective_priority", 1.0)
                if d < self.wmap.junction_box * 0.65:
                    return False                  # hard core: body overlap zone
                if approaching_me and moving:
                    return False                  # committed crosser owns the cell
                if approaching_me and (other_pr > me_pr + 1e-9 or
                                       (abs(other_pr - me_pr) < 1e-9 and rid < self.id)):
                    return False
            if not pe:
                continue
            pd = hb.get("dir", 1)
            try:
                end = self.wmap.node_of_edge_end(pe, pd)
                remain = self.wmap.edges[pe].length - hb.get("s", 0.0)
            except KeyError:
                continue
            if end == node and remain < 2.5 and d < box * 1.8:
                other_pr = hb.get("effective_priority", 1.0)
                if other_pr > me_pr + 1e-9 or (abs(other_pr - me_pr) < 1e-9 and rid < self.id):
                    return False
        return True

    def _junction_empty_p2p(self, node: str) -> bool:
        """When outbidding a JEC reservation: is the junction physically empty
        (heartbeat positions) — the deterministic safety backstop."""
        nx, ny = self.wmap.node_pos(node)
        for rid, hb in self.peers.items():
            if math.hypot(hb["pos"][0] - nx, hb["pos"][1] - ny) < self.wmap.junction_box:
                return False
        return True

    def _veto(self, rule: str, detail: Dict) -> None:
        self._veto_reasons.append({"t": round(self.t, 2), "rule": rule, **detail})
        if len(self._veto_reasons) > 40:
            self._veto_reasons = self._veto_reasons[-40:]
        # edge-triggered: count and publish only NEW veto episodes
        key = (rule, detail.get("edge") or detail.get("junction") or detail.get("gate") or detail.get("peer"))
        if key not in self._veto_active:
            self._veto_active.add(key)
            self.counters["veto_episodes"] = self.counters.get("veto_episodes", 0) + 1
            self.emit("safety_veto", {"rule": rule, **detail})

    def _clear_vetoes(self) -> None:
        """Called when movement resumes: veto episodes end."""
        self._veto_active.clear()

    # ------------------------------------------------------------------
    def _release_crossed_reservations(self, node: str) -> None:
        resv = self.reservations.pop(node, None)
        if resv:
            jec = resv.get("jec", "")
            self.plane.publish(f"fleet/robot/{self.id}/resv_release", {
                "robot": self.id, "resource": node, "t": round(self.t, 3),
                "jec": jec, "resv_id": resv.get("resv_id", ""),
            })

    # ------------------------------------------------------------------
    # gate permission resolution (P2P path)
    # ------------------------------------------------------------------
    def _gate_permission(self, gate: Optional[str], my_dir: int) -> Tuple[bool, Optional[int]]:
        """May I enter the gate's first edge travelling my_dir?

        Hard rule for ALL modes (deadlock prevention): never enter while an
        opposing-direction occupant is anywhere in the aisle.
        """
        if not gate:
            return (True, None)
        # occupancy-based opposing flow check (safety backstop, all modes)
        opposing = self._gate_occupant_dir(gate, exclude=self.id)
        if opposing is not None and opposing != my_dir:
            return (False, opposing)
        entry_edge = self._gate_entry_edge(gate, my_dir)
        if entry_edge and self._edge_occupancy(entry_edge) >= self.wmap.edges[entry_edge].capacity:
            return (False, opposing)
        if self.flags.stop_and_wait or self.flags.reactive_only:
            return (True, opposing)
        jec = self.wmap.jec_for_gate(gate)
        if jec and self.flags.use_jec and not self._jec_down(jec):
            st = self.jec_states.get(jec, {})
            if st.get("blocked") or self.context_affects("AISLE_BLOCKED", gate):
                return (False, None)
            g = st.get("gate_state") or {}
            gd = int(g.get("dir", 0))
            if gd == 0:
                grant = self.reservations.get(gate)
                ok = bool(grant and grant.get("state") in (RESV_GRANTED, RESV_ACTIVE))
                return (ok, 0)
            if gd == my_dir:
                return (True, gd)      # same-direction batch entry
            return (False, gd)
        # ---- P2P: claims + listen window
        claims = [c for c in self.gate_claims.get(gate, []) if c.get("dir") != my_dir]
        my_pr = effective_priority(self.fairness, self.fair_cfg, self.t)
        for c in claims:
            other_pr = c.get("priority", 1.0)
            if other_pr > my_pr + 1e-9 or (abs(other_pr - my_pr) < 1e-9 and c["robot"] < self.id):
                return (False, int(c.get("dir", 0)))
        # listen window after my own claim (hear counter-claims)
        sent = self._gate_claim_sent
        if sent and sent[0] == gate:
            listen = self.cfg["narrow_gate"].get("claim_listen_s", 0.5)
            if self.t - sent[2] < listen:
                return (False, 0)      # still listening
            return (True, my_dir)
        return (True, 0)

    def _gate_occupant_dir(self, gate: str, exclude: str = "") -> Optional[int]:
        """Direction of any current occupant of the gate (from heartbeats)."""
        edges = self.wmap.gate_edges(gate)
        for rid, hb in self.peers.items():
            if rid == exclude:
                continue
            if hb.get("edge") in edges and hb.get("state") not in ("FAILED",):
                if hb.get("node"):
                    continue
                e = self.wmap.edges[hb.get("edge")]
                d = hb.get("dir", 1)
                # direction sign from geometry: +1 northbound (increasing y)
                dy = (self.wmap.nodes[e.v].y - self.wmap.nodes[e.u].y) if d == 1 else \
                    (self.wmap.nodes[e.u].y - self.wmap.nodes[e.v].y)
                return 1 if dy > 0 else -1
        return None

    def _gate_entry_edge(self, gate: str, my_dir: int) -> Optional[str]:
        a = self.wmap.aisles[gate]
        if my_dir > 0:
            for eid in a.edges:
                e = self.wmap.edges[eid]
                if e.u == a.south or self.wmap.nodes[e.u].y < self.wmap.nodes[e.v].y:
                    return eid
        else:
            for eid in reversed(a.edges):
                e = self.wmap.edges[eid]
                if e.v == a.north or self.wmap.nodes[e.v].y > self.wmap.nodes[e.u].y:
                    return eid
        return a.edges[0] if a.edges else None

    def _gate_claim_rejected(self, gate: str, my_dir: int) -> bool:
        """True when an opposing holder outranks us (we should yield)."""
        ok, gd = self._gate_permission(gate, my_dir)
        return not ok

    # ==================================================================
    # outbound messages
    # ==================================================================
    def _heartbeat(self) -> None:
        self._hb_accum += self.tick_period
        hz = HEARTBEAT_HZ
        if self._hb_accum < 1.0 / hz:
            return
        self._hb_accum = 0.0
        pr = effective_priority(self.fairness, self.fair_cfg, self.t)
        pos = self.position()
        hb_edge = self.edge or ""
        hb_s = self.s
        hb_dir = self.dir
        if (self.node is not None and self.wmap.nodes[self.node].is_zone
                and self.last_edge and self.last_edge in self.wmap.edges):
            # parked in a zone queue: report the queue slot geometry
            e = self.wmap.edges[self.last_edge]
            hb_edge = self.last_edge
            hb_dir = self.entry_dir
            hb_s = max(0.15, e.length - 0.75 * (self._zone_slot() + 1))
        self.plane.publish(f"fleet/robot/{self.id}/heartbeat", {
            "robot": self.id, "t": round(self.t, 3), "pos": [round(pos[0], 2), round(pos[1], 2)],
            "edge": hb_edge, "dir": hb_dir, "s": round(hb_s, 2),
            "node": self.node or "", "speed": round(self.speed, 2),
            "battery": round(self.battery, 1), "state": self.state,
            "task_id": (self.task or {}).get("task_id", ""),
            "urgency": round(self.fairness.urgency, 2),
            "effective_priority": round(pr, 2),
            "waiting": self.fairness.wait_since > 0,
            "wait_s": round((self.t - self.fairness.wait_since), 2) if self.fairness.wait_since else 0.0,
            "yields": self.counters["yields"], "denials": self.counters["denials"],
            "route_head": [st["edge"] for st in self.route[:3]],
            "counters": {k: (round(v, 2) if isinstance(v, float) else v)
                         for k, v in self.counters.items()},
            "stats": self.plane.stats.to_msg(),
        })

    def _intent_publish(self) -> None:
        if not self.flags.share_intent:
            return
        self._intent_accum += self.tick_period
        if self._intent_accum < 1.0 / INTENT_HZ:
            return
        self._intent_accum = 0.0
        start_s = self.s if self.node is None else 0.0
        route = ([{"edge": self.edge, "dir": self.dir}] + self.route) if self.node is None else self.route
        route = route[:5]
        windows = R.step_arrival_times(self.wmap, route, start_s=start_s)
        route_msg = [{"edge": st["edge"], "dir": st["dir"],
                      "eta_in": round(tin, 2), "eta_out": round(tout, 2)} for st, tin, tout in windows]
        targets = []
        for st, tin, tout in windows:
            e = self.wmap.edges[st["edge"]]
            if e.aisle:
                targets.append({"resource": e.aisle, "eta": round(tin, 2),
                                "dur": round(tout - tin, 2)})
            node = self.wmap.node_of_edge_end(st["edge"], st["dir"])
            if self.wmap.nodes[node].is_junction and tin < self.horizon + 4:
                targets.append({"resource": node, "eta": round(tin, 2), "dur": 1.6})
        if self.node is not None and self.wmap.nodes[self.node].is_junction:
            targets.append({"resource": self.node, "eta": 0.0, "dur": 1.6})
        pos = self.position()
        intent = Intent(robot=self.id, t=self.t, route=route_msg, targets=targets,
                        pos=pos, speed=self.speed,
                        urgency=self.fairness.urgency,
                        confidence=0.9 if self.route else 0.5,
                        task_id=(self.task or {}).get("task_id", ""), state=self.state)
        self.plane.publish(f"fleet/robot/{self.id}/intent", intent.to_msg())

    def _heartbeat_carry(self, dt: float) -> None:
        pass

    # ==================================================================
    # chaos controls
    # ==================================================================
    def on_control(self, key: str, payload: Dict) -> None:
        super().on_control(key, payload)
        cmd = payload.get("cmd")
        if cmd == "FAIL_ROBOT" and payload.get("robot") == self.id:
            if self.state != "FAILED":
                self._fail()
        elif cmd == "RECOVER_ROBOT" and payload.get("robot") == self.id:
            if self.state == "FAILED":
                self.state = "IDLE"
                self.publish_context("ROBOT_RECOVERED", self.id, ttl=8.0, affected=[self.id])
                self.emit("recovered", {})
        elif cmd == "BATTERY_CRITICAL" and payload.get("robot") == self.id:
            self.battery = min(self.battery, 8.0)

    def _fail(self) -> None:
        self.state = "FAILED"
        self.speed = 0.0
        # release reservations
        for res in list(self.reservations):
            self._release_crossed_reservations(res)
        # report task as failed -> allocator reassigns
        if self.task is not None:
            self.plane.publish(f"fleet/task/{self.task['task_id']}", {
                "task_id": self.task["task_id"], "state": "ROBOT_FAILED",
                "robot": self.id, "t": round(self.t, 3)})
            self.task = None
        self.publish_context("ROBOT_FAILED", self.id, ttl=15.0, affected=[self.id])
        self.emit("failed", {})

    # ------------------------------------------------------------------
    def snapshot(self) -> Dict:
        pr = effective_priority(self.fairness, self.fair_cfg, self.t)
        return {
            "robot": self.id, "t": round(self.t, 3), "state": self.state,
            "pos": [round(self.position()[0], 2), round(self.position()[1], 2)],
            "node": self.node or "", "edge": self.edge or "", "s": round(self.s, 2),
            "dir": self.dir, "speed": round(self.speed, 2),
            "battery": round(self.battery, 1),
            "task": self.task, "phase": self.task_phase,
            "route": [st["edge"] for st in self.route],
            "effective_priority": round(pr, 2),
            "urgency": round(self.fairness.urgency, 2),
            "waiting": self.fairness.wait_since > 0,
            "wait_s": round((self.t - self.fairness.wait_since), 2) if self.fairness.wait_since else 0.0,
            "counters": {k: (round(v, 2) if isinstance(v, float) else v)
                         for k, v in self.counters.items()},
            "reservations": list(self.reservations.values()),
            "in_conflict": [c for c, m in self.conflict_cells.items()
                            if self.id in m.get("members", [])],
            "stats": self.plane.stats.to_msg(),
        }
