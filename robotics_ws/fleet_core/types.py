"""Core domain types for the Distributed Predictive Fleet Graph.

All coordination messages are plain JSON-serialisable dicts exchanged on the
message plane under `fleet/...` key namespaces. Dataclasses below define the
canonical in-process representations plus `to_msg()` / `from_msg()` helpers.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

# ---------------------------------------------------------------------------
# Reservation states (build prompt §7)
RESV_REQUESTED = "REQUESTED"
RESV_GRANTED = "GRANTED"
RESV_ACTIVE = "ACTIVE"
RESV_RELEASED = "RELEASED"
RESV_EXPIRED = "EXPIRED"
RESV_REJECTED = "REJECTED"

# Context event types (build prompt §12)
EV_AISLE_BLOCKED = "AISLE_BLOCKED"
EV_AISLE_CLEARED = "AISLE_CLEARED"
EV_HUMAN_ACTIVITY = "HUMAN_ACTIVITY"
EV_ROBOT_FAILED = "ROBOT_FAILED"
EV_ROBOT_RECOVERED = "ROBOT_RECOVERED"
EV_BATTERY_CRITICAL = "BATTERY_CRITICAL"
EV_CONGESTION_SPIKE = "CONGESTION_SPIKE"
EV_JEC_OFFLINE = "JEC_OFFLINE"
EV_JEC_ONLINE = "JEC_ONLINE"

# Coordination experiment modes (build prompt §20)
MODE_STOP_WAIT = "STOP_AND_WAIT"
MODE_REACTIVE = "SHORTEST_PATH_REACTIVE"
MODE_INTENT_P2P = "INTENT_P2P"
MODE_FULL = "FULL_DISTRIBUTED_PREDICTIVE"
ALL_MODES = [MODE_STOP_WAIT, MODE_REACTIVE, MODE_INTENT_P2P, MODE_FULL]


@dataclass
class Reservation:
    """Space-time reservation slot for a shared resource (junction / gate)."""
    resource: str
    robot: str
    start: float
    end: float
    priority: float
    state: str = RESV_REQUESTED
    lease: float = 4.0
    resv_id: str = ""
    created: float = 0.0

    def to_msg(self) -> Dict[str, Any]:
        return {
            "resv_id": self.resv_id, "resource": self.resource, "robot": self.robot,
            "start": round(self.start, 3), "end": round(self.end, 3),
            "priority": round(self.priority, 3), "state": self.state, "lease": self.lease,
        }

    @staticmethod
    def from_msg(m: Dict[str, Any]) -> "Reservation":
        return Reservation(
            resource=m["resource"], robot=m["robot"], start=m["start"], end=m["end"],
            priority=m.get("priority", 0.0), state=m.get("state", RESV_REQUESTED),
            lease=m.get("lease", 4.0), resv_id=m.get("resv_id", ""),
            created=m.get("created", 0.0),
        )

    def overlaps(self, other: "Reservation", margin: float = 0.0) -> bool:
        return (self.start - margin) < other.end and other.start < (self.end + margin)


@dataclass
class Intent:
    """Trajectory intent published by each robot (build prompt §3 'graph of futures')."""
    robot: str
    t: float
    route: List[Dict[str, Any]] = field(default_factory=list)   # [{edge, dir, eta_in, eta_out}]
    targets: List[Dict[str, Any]] = field(default_factory=list)  # [{resource, eta, dur}]
    pos: Tuple[float, float] = (0.0, 0.0)
    speed: float = 0.0
    urgency: float = 0.0
    confidence: float = 1.0
    task_id: str = ""
    state: str = "IDLE"

    def to_msg(self) -> Dict[str, Any]:
        return {
            "robot": self.robot, "t": round(self.t, 3), "route": self.route,
            "targets": self.targets, "pos": [round(self.pos[0], 2), round(self.pos[1], 2)],
            "speed": round(self.speed, 2), "urgency": round(self.urgency, 2),
            "confidence": self.confidence, "task_id": self.task_id, "state": self.state,
        }

    @staticmethod
    def from_msg(m: Dict[str, Any]) -> "Intent":
        return Intent(
            robot=m["robot"], t=m["t"], route=m.get("route", []),
            targets=m.get("targets", []), pos=tuple(m.get("pos", (0, 0))),
            speed=m.get("speed", 0.0), urgency=m.get("urgency", 0.0),
            confidence=m.get("confidence", 1.0), task_id=m.get("task_id", ""),
            state=m.get("state", "IDLE"),
        )


@dataclass
class ContextEvent:
    """Distributed contextual memory entry with TTL (build prompt §12)."""
    ev_type: str
    value: str
    reporter: str
    t: float
    confidence: float = 1.0
    ttl: float = 20.0
    affected: List[str] = field(default_factory=list)
    seq: int = 0

    def to_msg(self) -> Dict[str, Any]:
        return {
            "type": self.ev_type, "value": self.value, "reporter": self.reporter,
            "t": round(self.t, 3), "confidence": self.confidence, "ttl": self.ttl,
            "affected": self.affected, "seq": self.seq,
        }

    @staticmethod
    def from_msg(m: Dict[str, Any]) -> "ContextEvent":
        return ContextEvent(
            ev_type=m["type"], value=m["value"], reporter=m["reporter"], t=m["t"],
            confidence=m.get("confidence", 1.0), ttl=m.get("ttl", 20.0),
            affected=m.get("affected", []), seq=m.get("seq", 0),
        )

    def expired(self, now: float) -> bool:
        return (now - self.t) > self.ttl


@dataclass
class Task:
    task_id: str
    kind: str            # PICK_DROP | REPOSITION | CHARGE | URGENT
    pickup: str
    drop: str
    created: float
    deadline: Optional[float] = None
    urgency: float = 0.0
    state: str = "PENDING"   # PENDING | ANNOUNCED | ASSIGNED | DONE | FAILED
    assigned: Optional[str] = None

    def to_msg(self) -> Dict[str, Any]:
        return {
            "task_id": self.task_id, "kind": self.kind, "pickup": self.pickup,
            "drop": self.drop, "created": round(self.created, 3),
            "deadline": self.deadline, "urgency": self.urgency, "state": self.state,
            "assigned": self.assigned,
        }

    @staticmethod
    def from_msg(m: Dict[str, Any]) -> "Task":
        return Task(
            task_id=m["task_id"], kind=m["kind"], pickup=m["pickup"], drop=m["drop"],
            created=m["created"], deadline=m.get("deadline"), urgency=m.get("urgency", 0.0),
            state=m.get("state", "PENDING"), assigned=m.get("assigned"),
        )


def sim_time() -> float:
    """Wall-clock seconds — replaced by virtual time inside the DES runtime."""
    return time.time()
