"""Deterministic headless fleet (experiment runtime).

Assembles the SAME agent classes (RobotAgent / JEC / allocator) on the
discrete-event runtime with the in-process transport. Every coordination
message still flows through the message plane with sender latency,
receiver loss and radio range — only the clock differs from the live demo.
"""
from __future__ import annotations

import math
import random
from typing import Any, Dict, List, Optional, Tuple

from ..fleet_core.config import load_fleet_config, load_map, project_path
from ..fleet_core.types import ALL_MODES
from ..fleet_transport.base import ImpairProfile, MessagePlane
from ..fleet_transport.inproc_backend import InprocBackend
from ..fleet_transport.runtime import DESRuntime
from ..robot_agent.agent import RobotAgent
from ..junction_edge_cell.jec import JunctionEdgeCellAgent
from ..task_allocator.allocator import TaskAllocatorAgent
from ..task_allocator.scenario import Scenario


class FleetMetricsCollector:
    """Read-only observer (range=inf) computing the §21 metric set."""

    def __init__(self, wmap, plane: MessagePlane):
        self.wmap = wmap
        self.plane = plane
        self.robots: Dict[str, Dict] = {}
        self.jecs: Dict[str, Dict] = {}
        self.allocator: Dict = {}
        self.conflicts: Dict[str, Dict] = {}
        self.task_events: List[Dict] = []
        self.decisions: List[Dict] = []
        self.vetoes: List[Dict] = []
        self.context_events: List[Dict] = []
        self.collisions: List[Dict] = []
        self.gate_states: List[Dict] = []
        self.resv_decisions: List[Dict] = []
        self.wait_samples: List[float] = []
        self.queue_samples: List[float] = []
        self.completions: List[Dict] = []
        self.travel: Dict[str, float] = {}
        self._t = 0.0
        plane.subscribe("fleet/robot/*/heartbeat", self._on_hb)
        plane.subscribe("fleet/jec/*/state", self._on_jec)
        plane.subscribe("fleet/allocator/taskstate", self._on_task)
        plane.subscribe("fleet/conflict/*", self._on_conflict)
        plane.subscribe("fleet/telemetry/*", self._on_telemetry)
        plane.subscribe("fleet/gate/*/claim", lambda k, m: None)

    def _on_hb(self, key: str, m: Dict) -> None:
        self.robots[m["robot"]] = dict(m, t_recv=self._t)

    def _on_jec(self, key: str, m: Dict) -> None:
        self.jecs[m["jec"]] = dict(m)
        self.queue_samples.append(len(m.get("queue", [])))

    def _on_task(self, key: str, m: Dict) -> None:
        self.task_events.append(dict(m, t_recv=self._t))
        if m.get("state") == "DONE":
            self.completions.append({
                "task_id": m["task_id"], "robot": m.get("robot"),
                "t_done": round(self._t, 2),
            })

    def _on_conflict(self, key: str, m: Dict) -> None:
        cell = m.get("cell", "")
        if m.get("expired"):
            self.conflicts.pop(cell, None)
        else:
            self.conflicts[cell] = dict(m, t_recv=self._t)

    def _on_telemetry(self, key: str, m: Dict) -> None:
        t = m.get("type", "")
        if t == "decision":
            self.decisions.append(dict(m, t_recv=self._t))
        elif t == "safety_veto":
            self.vetoes.append(dict(m, t_recv=self._t))
        elif t in ("collision_risk", "collision"):
            self.collisions.append(dict(m, t_recv=self._t))
        elif t == "reservation_decision":
            self.resv_decisions.append(dict(m, t_recv=self._t))
        elif t == "wait_episode":
            self.wait_samples.append(m.get("duration", 0.0))
        elif t == "allocator_stats":
            self.allocator = dict(m)

    def tick(self, t: float) -> None:
        self._t = t

    # ------------------------------------------------------------------
    def summarize(self, duration: float, allocator: TaskAllocatorAgent) -> Dict:
        waits = sorted(w for w in self.wait_samples if w > 0)
        tasks_done = allocator.counters["completed"]
        hz = duration / 3600.0
        msgs_s = 0.0
        bytes_s = 0.0
        plane_stats = []
        for rid, rb in self.robots.items():
            st = rb.get("stats", {})
            msgs_s += st.get("sent", 0) / max(1e-9, duration)
            bytes_s += st.get("sent_bytes", 0) / max(1e-9, duration)
        for jid, j in self.jecs.items():
            st = j.get("stats", {})
            msgs_s += st.get("sent", 0) / max(1e-9, duration)
            bytes_s += st.get("sent_bytes", 0) / max(1e-9, duration)
        distance = sum(rb.get("counters", {}).get("distance_m", 0) for rb in self.robots.values())
        energy = sum(rb.get("counters", {}).get("energy_j", 0) for rb in self.robots.values())
        vetoes = sum(rb.get("counters", {}).get("veto_episodes", 0) for rb in self.robots.values())
        replans = sum(rb.get("counters", {}).get("replans", 0) for rb in self.robots.values())
        collisions = sum(rb.get("counters", {}).get("collisions", 0) for rb in self.robots.values())
        near_misses = sum(rb.get("counters", {}).get("near_misses", 0) for rb in self.robots.values())
        deadlock_backouts = sum(rb.get("counters", {}).get("deadlock_backouts", 0)
                                for rb in self.robots.values())
        # deadlock = wait episodes longer than 30s (stuck without progress)
        deadlocks = sum(1 for w in self.wait_samples if w > 30.0)
        stalled = [rid for rid, rb in self.robots.items()
                   if rb.get("wait_s", 0) > 12.0]
        queue_lengths = self.queue_samples or [len(j.get("queue", [])) for j in self.jecs.values()]
        denials = sum(j.get("counters", {}).get("denials", 0) for j in self.jecs.values())
        grants = sum(j.get("counters", {}).get("grants", 0) for j in self.jecs.values())
        utilization = [j.get("utilization", 0.0) for j in self.jecs.values()]
        p95 = waits[int(0.95 * len(waits))] if waits else 0.0
        return {
            "duration_s": round(duration, 1),
            "tasks_done": tasks_done,
            "tasks_per_hour": round(tasks_done / hz, 2) if hz > 0 else 0.0,
            "tasks_failed": allocator.counters["failed"],
            "tasks_reassigned": allocator.counters["reassigned"],
            "mean_wait_s": round(sum(waits) / len(waits), 2) if waits else 0.0,
            "p95_wait_s": round(p95, 2),
            "max_wait_s": round(max(waits), 2) if waits else 0.0,
            "total_distance_m": round(distance, 1),
            "energy_j": round(energy, 1),
            "vetoes": vetoes,
            "replans": replans,
            "collisions": collisions,
            "near_misses": near_misses,
            "deadlocks": deadlocks,
            "stalled_robots": len(stalled),
            "long_waits_over_30s": deadlocks,
            "deadlock_backouts": deadlock_backouts,
            "mean_queue_len": round(sum(queue_lengths) / len(queue_lengths), 2) if queue_lengths else 0.0,
            "reservation_denials": denials,
            "reservation_grants": grants,
            "jec_utilization": round(sum(utilization) / len(utilization), 3) if utilization else 0.0,
            "messages_per_s": round(msgs_s, 1),
            "bytes_per_s": round(bytes_s, 1),
            "conflict_cells_formed": len({d.get("cell") for d in self.conflicts.values()}),
            "decisions_logged": len(self.decisions),
        }


class DesFleet:
    """Headless fleet on virtual time."""

    def __init__(self, mode: str, scenario: Scenario, seed: int = 0,
                 wmap=None, cfg: Dict = None, duration: float = None,
                 impairment: ImpairProfile = None):
        assert mode in ALL_MODES, f"unknown mode {mode}"
        self.mode = mode
        self.cfg = cfg or load_fleet_config()
        self.wmap = wmap if wmap is not None else load_map()
        self.runtime = DESRuntime(t0=0.0)
        self.backend = InprocBackend(self.runtime)
        self.scenario = scenario
        self.duration = duration if duration is not None else scenario.duration_s
        self.seed = seed

        base_rng = random.Random(seed)
        self.planes: List[MessagePlane] = []

        # agents
        self.robots: List[RobotAgent] = []
        spawn: Dict[str, str] = {}
        for i, sp in enumerate(self.wmap.spawn):
            rid = sp.get("rid") or f"R{i + 1:02d}"
            node = sp.get("node")
            if node in self.wmap.nodes:
                spawn[rid] = node
                continue
            if "x" in sp and "y" in sp:
                x, y = float(sp["x"]), float(sp["y"])
                nearest = min(
                    self.wmap.nodes.values(),
                    key=lambda n: (n.x - x) ** 2 + (n.y - y) ** 2,
                )
                spawn[rid] = nearest.id
        for i in range(self.cfg["fleet"]["robot_count"]):
            rid = f"R{i + 1:02d}"
            rng = random.Random(seed * 1000 + i)
            plane = MessagePlane(self.backend, rid,
                                 range_m=self.cfg["fleet"]["radio_range_robot"],
                                 profile=impairment or ImpairProfile(**self.cfg.get("impairment", {})),
                                 rng=rng, scheduler=self.runtime.call_later)
            self.planes.append(plane)
            battery = rng.uniform(*self.cfg.get("battery", {}).get("start_pct", [72, 96]))
            robot = RobotAgent(rid, self.runtime, plane, wmap=self.wmap, cfg=self.cfg,
                               seed=seed * 1000 + i, mode=mode,
                               start_node=spawn.get(rid, "O1"), battery=battery)
            self.robots.append(robot)

        self.jecs: List[JunctionEdgeCellAgent] = []
        if mode == "FULL_DISTRIBUTED_PREDICTIVE":
            for j, (jid, spec) in enumerate(self.wmap.jecs.items()):
                rng = random.Random(seed * 2000 + j)
                plane = MessagePlane(self.backend, jid,
                                     range_m=self.cfg["fleet"]["radio_range_jec"],
                                     profile=impairment or ImpairProfile(**self.cfg.get("impairment", {})),
                                     rng=rng, scheduler=self.runtime.call_later)
                self.planes.append(plane)
                self.jecs.append(JunctionEdgeCellAgent(jid, self.runtime, plane,
                                                       wmap=self.wmap, cfg=self.cfg,
                                                       seed=seed * 2000 + j))

        arng = random.Random(seed * 3000)
        aplane = MessagePlane(self.backend, "ALLOC",
                              range_m=math.inf, infra=True,
                              profile=impairment or ImpairProfile(**self.cfg.get("impairment", {})),
                              rng=arng, scheduler=self.runtime.call_later)
        self.planes.append(aplane)
        self.allocator = TaskAllocatorAgent("ALLOC", self.runtime, aplane,
                                            wmap=self.wmap, cfg=self.cfg,
                                            seed=seed, scenario=scenario)

        # metrics collector: read-only observer with its own plane (range=inf)
        mrng = random.Random(seed * 4000)
        mplane = MessagePlane(self.backend, "METRICS",
                              range_m=math.inf, infra=True,
                              profile=ImpairProfile(latency_ms=0, jitter_ms=0, loss_pct=0),
                              rng=mrng, scheduler=self.runtime.call_later)
        self.planes.append(mplane)
        self.metrics = FleetMetricsCollector(self.wmap, mplane)

    # ------------------------------------------------------------------
    def start(self) -> None:
        for agent in self.robots + self.jecs + [self.allocator]:
            agent.start()

    def run(self) -> Dict:
        self.start()
        self.step_to(self.duration)
        return self.metrics.summarize(self.duration, self.allocator)

    def step_to(self, t_end: float) -> None:
        """Advance virtual time including scripted chaos events."""
        if not getattr(self, "_started", False):
            self._started = True
            self.start()
        dt_sample = 0.25
        t = self.runtime.now()
        while t < t_end:
            self.runtime.run(min(t + dt_sample, t_end))
            t = min(t + dt_sample, t_end)
            self.metrics.tick(t)
            self._scenario_chaos(t)

    def _scenario_chaos(self, t: float) -> None:
        """Optional scripted chaos events (defined per experiment)."""
        for ev in getattr(self, "chaos_script", []):
            if not ev.get("_fired") and ev["t"] <= t:
                ev["_fired"] = True
                self.apply_chaos(ev["cmd"], ev.get("args", {}))

    def apply_chaos(self, cmd: str, args: Dict) -> None:
        """In-DES chaos injection (same effects as live control commands)."""
        if cmd == "KILL_JEC":
            jid = args.get("jec")
            for j in self.jecs:
                if j.id == jid:
                    j.stop()
        elif cmd == "RESTART_JEC":
            jid = args.get("jec")
            for j in self.jecs:
                if j.id == jid:
                    j.started = False
                    j.start()
                    j.runtime.call_later(0.0, lambda jj=j: jj.publish_context(
                        "JEC_ONLINE", jj.id, ttl=6.0, affected=[jj.junction]))
        elif cmd == "FAIL_ROBOT":
            for r in self.robots:
                if r.id == args.get("robot"):
                    r._fail()
        elif cmd == "RECOVER_ROBOT":
            for r in self.robots:
                if r.id == args.get("robot"):
                    r.state = "IDLE"
                    r.publish_context("ROBOT_RECOVERED", r.id, ttl=8.0, affected=[r.id])
        elif cmd == "BLOCK_AISLE":
            res = args.get("resource", "")
            from ..fleet_core.types import ContextEvent
            affected = [res]
            if res in self.wmap.aisles:
                affected = list(self.wmap.gate_edges(res))
            ev = ContextEvent(ev_type="AISLE_BLOCKED", value=res, reporter="CHAOS",
                              t=self.runtime.now(), ttl=args.get("ttl", 20.0),
                              confidence=0.96, affected=affected, seq=0)
            for agent in self.robots + self.jecs:
                agent._remember(ev)
            # JEC directly responsible marks blocked
            for j in self.jecs:
                if res in (j.junction, j.gate) or res in j.spec.covers:
                    j.blocked = True
        elif cmd == "UNBLOCK_AISLE":
            res = args.get("resource", "")
            for agent in self.robots + self.jecs:
                for kk in [k for k, e in agent.context.items()
                           if e.ev_type == "AISLE_BLOCKED" and (e.value == res or res in e.affected)]:
                    del agent.context[kk]
            for j in self.jecs:
                if res in (j.junction, j.gate) or res in j.spec.covers:
                    j.blocked = False
        elif cmd == "TASK_BURST":
            self.allocator.burst_tasks(args.get("zone", "B"), int(args.get("count", 6)))
        elif cmd == "SET_PROFILE":
            prof = ImpairProfile(**args)
            for p in self.planes:
                p.set_profile(prof)
        elif cmd == "BATTERY_CRITICAL":
            for r in self.robots:
                if r.id == args.get("robot"):
                    r.battery = 8.0

    # ------------------------------------------------------------------
    def snapshots(self) -> Dict:
        return {
            "robots": [r.snapshot() for r in self.robots],
            "jecs": [j.snapshot() for j in self.jecs],
            "allocator": self.allocator.snapshot(),
            "conflicts": list(self.metrics.conflicts.values()),
        }
