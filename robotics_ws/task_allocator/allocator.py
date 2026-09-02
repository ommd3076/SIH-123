"""Task allocator / WMS interface (build prompt §17).

A lightweight auction dispatcher. IMPORTANT ARCHITECTURAL NOTE: this process
is the warehouse management SYSTEM interface — it announces tasks and awards
bids. It is NOT a traffic controller: it never plans routes, never grants
reservations and never commands motion. Movement coordination stays fully
distributed (robots + JECs + intents). If this process dies, robots keep
operating — they simply receive no new tasks.

Auction: announce -> bids (ETA + congestion + battery + load) -> award to the
lowest bid with deterministic tie-breaking by robot id. On robot failure the
unfinished task returns to the pool and is re-auctioned among nearby robots.
"""
from __future__ import annotations

import math
from collections import deque
from typing import Any, Dict, List, Optional, Tuple

from ..robot_agent.base_agent import BaseAgent
from .scenario import Scenario

ROBOT_TTL = 4.0


class TaskAllocatorAgent(BaseAgent):
    kind = "allocator"

    def __init__(self, agent_id: str, runtime, plane, wmap=None, cfg=None,
                 seed: int = 0, scenario: Scenario = None):
        super().__init__(agent_id, runtime, plane, wmap, cfg, seed)
        self.range_m = math.inf          # WMS on the wired backbone
        self.plane.range_m = math.inf
        self.tick_period = 0.2
        self.scenario = scenario
        self.tasks: Dict[str, Dict] = {}
        self.task_queue: List[Dict] = []      # pending announcements
        self.bids: Dict[str, List[Dict]] = {}  # task_id -> bids
        self.robots: Dict[str, Dict] = {}      # rid -> heartbeat
        self.counters = {
            "announced": 0, "awarded": 0, "completed": 0, "failed": 0,
            "reassigned": 0, "expired": 0,
        }
        self._auction_timer: Dict[str, float] = {}
        self._next_t = 0.0
        self._drain_t: Optional[float] = None
        self._task_events: deque = deque(maxlen=200)

    # ------------------------------------------------------------------
    def _wire(self) -> None:
        self.plane.subscribe("fleet/robot/*/heartbeat", self._on_heartbeat)
        self.plane.subscribe("fleet/robot/*/bid", self._on_bid)
        self.plane.subscribe("fleet/task/*", self._on_task_event)

    def position(self) -> Tuple[float, float]:
        return (0.0, 0.0)     # backbone — no radio range semantics

    # ------------------------------------------------------------------
    def _on_heartbeat(self, key: str, m: Dict) -> None:
        rid = m.get("robot")
        if rid:
            self.robots[rid] = dict(m, t_recv=self.t)

    def _on_bid(self, key: str, m: Dict) -> None:
        tid = m.get("task_id")
        if tid in self.bids:
            self.bids[tid].append(dict(m))

    def _on_task_event(self, key: str, m: Dict) -> None:
        tid = m.get("task_id", "")
        st = m.get("state", "")
        if not tid or tid not in self.tasks:
            return
        task = self.tasks[tid]
        task["state"] = st
        robot = m.get("robot", task.get("assigned"))
        if st == "DONE":
            task["assigned"] = robot
            self.counters["completed"] += 1
            self._task_events.append({"t": round(self.t, 2), "task_id": tid,
                                      "event": "done", "robot": robot})
        elif st in ("ROBOT_FAILED", "ABORTED"):
            self.counters["failed"] += 1
            self._task_events.append({"t": round(self.t, 2), "task_id": tid,
                                      "event": st.lower(), "robot": robot})
            # task returns to the pool (distributed reassignment §17)
            task["state"] = "PENDING"
            task["assigned"] = None
            task["created"] = self.t + 0.1      # re-announce soon
            self.task_queue.append(task)
            self.counters["reassigned"] += 1
        self.plane.publish(f"fleet/allocator/taskstate", {**m, "t": round(self.t, 3)})

    # ------------------------------------------------------------------
    def tick(self) -> None:
        self.t = self.runtime.now()
        self._scenario_inject()
        self._announce_due()
        self._resolve_auctions()
        self._expire_stale_bids()
        self._watch_failed_robots()
        self._publish_stats()

    def _scenario_inject(self) -> None:
        if self.scenario is None:
            return
        if not getattr(self, "_injected", False):
            self._injected = True
            for task in self.scenario.generate_tasks(self.wmap):
                tid = task["task_id"]
                if tid not in self.tasks:
                    self.tasks[tid] = task
                    self.task_queue.append(task)
        elif self._pool_drained():
            # continuous operations: the WMS re-issues the seeded schedule
            # under fresh task ids so the demo fleet never idles
            self._round = getattr(self, "_round", 0) + 1
            for task in self.scenario.generate_tasks(self.wmap):
                new = dict(task)
                new["task_id"] = f"{task['task_id']}-r{self._round}"
                new["created"] = self.t + max(0.0, task["created"] - 0.0)
                if new["task_id"] not in self.tasks:
                    self.tasks[new["task_id"]] = new
                    self.task_queue.append(new)

    def _pool_drained(self) -> bool:
        """True when nothing is pending/announced/assigned for a while."""
        busy = (self.task_queue
                or any(t.get("state") in ("ANNOUNCED", "ASSIGNED", "PENDING")
                       for t in self.tasks.values()))
        if busy:
            self._drain_t = None
            return False
        if self._drain_t is None:
            self._drain_t = self.t
        return (self.t - self._drain_t) > 12.0
        # demand context broadcast (schedule prior for congestion forecasting)
        level = self.scenario.demand_factor_at(self.t)
        self.publish_context("DEMAND_LEVEL", f"{level:.2f}", ttl=6.0,
                             affected=[], confidence=1.0)

    def _announce_due(self) -> None:
        still: List[Dict] = []
        for task in self.task_queue:
            if task.get("created", 0) <= self.t and task.get("state", "PENDING") == "PENDING":
                self._announce(task)
            else:
                still.append(task)
        self.task_queue = still

    def _announce(self, task: Dict) -> None:
        task["state"] = "ANNOUNCED"
        self.counters["announced"] += 1
        self.bids[task["task_id"]] = []
        self._auction_timer[task["task_id"]] = self.t + self.cfg["allocator"]["bid_window_s"]
        self.plane.publish("fleet/allocator/announce", {
            **task, "t": round(self.t, 3),
        })
        self._task_events.append({"t": round(self.t, 2), "task_id": task["task_id"],
                                  "event": "announced"})

    def _resolve_auctions(self) -> None:
        for tid, timer in list(self._auction_timer.items()):
            if self.t < timer:
                continue
            del self._auction_timer[tid]
            bids = self.bids.pop(tid, [])
            task = self.tasks.get(tid)
            if task is None or task.get("state") != "ANNOUNCED":
                continue
            if not bids:
                # no bidders: re-queue with backoff
                task["state"] = "PENDING"
                task["_retries"] = task.get("_retries", 0) + 1
                delay = min(12.0, 1.0 * (2 ** min(5, task["_retries"])))
                task["created"] = self.t + delay
                self.task_queue.append(task)
                continue
            bids.sort(key=lambda b: (b.get("bid", 1e9), b.get("robot", "")))
            winner = None
            # admission control: cap concurrent tasks targeting one pickup
            # AND one drop zone (dock capacity + 2 approaching) — WMS flow
            # control keeps dock queues from saturating
            def zone_cap(zone_id):
                zn = self.wmap.nodes.get(zone_id, None)
                return (zn.capacity + 2) if zn else 4
            saturated = False
            for zone_key in ("pickup", "drop"):
                zone_id = task.get(zone_key, "")
                active_zone = sum(1 for t in self.tasks.values()
                                  if t.get("state") == "ASSIGNED"
                                  and t.get(zone_key) == zone_id)
                if active_zone >= zone_cap(zone_id):
                    saturated = True
                    break
            if saturated:
                task["state"] = "PENDING"
                # exponential backoff to avoid announcement storms
                task["_retries"] = task.get("_retries", 0) + 1
                delay = min(15.0, 1.5 * (2 ** min(6, task["_retries"])))
                task["created"] = self.t + delay
                self.task_queue.append(task)
                continue
            winner = bids[0]
            task["state"] = "ASSIGNED"
            task["_retries"] = 0
            task["assigned"] = winner["robot"]
            self.counters["awarded"] += 1
            self.plane.publish("fleet/allocator/award", {
                "task_id": tid, "robot": winner["robot"],
                "bid": winner.get("bid"), "t": round(self.t, 3),
                **{k: task[k] for k in ("kind", "pickup", "drop", "urgency", "deadline")
                   if k in task},
            })
            self._task_events.append({"t": round(self.t, 2), "task_id": tid,
                                      "event": "awarded", "robot": winner["robot"],
                                      "bid": winner.get("bid")})

    def _expire_stale_bids(self) -> None:
        for tid in list(self._auction_timer):
            pass
        for rid in [r for r, m in self.robots.items()
                    if self.t - m.get("t_recv", 0) > ROBOT_TTL]:
            del self.robots[rid]

    def _watch_failed_robots(self) -> None:
        """Heartbeat-loss reassignment: robots that vanish return unfinished
        tasks to the pool."""
        for tid, task in list(self.tasks.items()):
            assigned = task.get("assigned")
            if task.get("state") == "ASSIGNED" and assigned:
                hb = self.robots.get(assigned)
                if hb is None:
                    # robot lost: requeue task
                    task["state"] = "PENDING"
                    task["assigned"] = None
                    task["created"] = self.t + 0.5
                    self.task_queue.append(task)
                    self.counters["reassigned"] += 1
                    self._task_events.append({"t": round(self.t, 2), "task_id": tid,
                                              "event": "reassigned", "reason": "heartbeat_loss"})

    def _publish_stats(self) -> None:
        self.emit("allocator_stats", {
            "pending": len(self.task_queue),
            "active": sum(1 for t in self.tasks.values() if t.get("state") == "ASSIGNED"),
            "done": self.counters["completed"],
            "counters": dict(self.counters),
        })

    # ------------------------------------------------------------------
    def burst_tasks(self, zone: str, n: int) -> List[Dict]:
        """Chaos control: inject a task burst into a zone."""
        import random as _r
        rng = _r.Random(int(self.t * 1000) & 0xFFFF)
        bays = self.wmap.bays()
        pickups = self.wmap.pickups()
        drops = self.wmap.drops()
        made = []
        base = len(self.tasks)
        for i in range(n):
            tid = f"TB{base + i:04d}"
            if zone == "B":
                pickup, drop = rng.choice(bays), rng.choice(drops)
            elif zone == "A":
                pickup, drop = rng.choice(pickups), rng.choice(bays)
            else:
                pickup, drop = rng.choice(pickups), rng.choice(drops)
            task = {"task_id": tid, "kind": "PICK_DROP", "pickup": pickup,
                    "drop": drop, "created": self.t, "urgency": 0.0,
                    "deadline": None, "state": "PENDING"}
            self.tasks[tid] = task
            self.task_queue.append(task)
            made.append(task)
        return made

    def on_control(self, key: str, payload: Dict) -> None:
        super().on_control(key, payload)
        cmd = payload.get("cmd")
        if cmd == "TASK_BURST":
            zone = payload.get("zone", "B")
            n = int(payload.get("count", 6))
            made = self.burst_tasks(zone, n)
            self.emit("task_burst", {"zone": zone, "count": len(made),
                                     "task_ids": [t["task_id"] for t in made]})

    # ------------------------------------------------------------------
    def snapshot(self) -> Dict:
        return {
            "allocator": self.id, "t": round(self.t, 3),
            "pending": len(self.task_queue),
            "active": sum(1 for t in self.tasks.values() if t.get("state") == "ASSIGNED"),
            "done": self.counters["completed"],
            "failed": self.counters["failed"],
            "reassigned": self.counters["reassigned"],
            "announced": self.counters["announced"],
            "awarded": self.counters["awarded"],
            "tasks": [t for t in self.tasks.values()],
            "events": list(self._task_events)[-40:],
        }
