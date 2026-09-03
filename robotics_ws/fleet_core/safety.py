"""Deterministic safety layer (build prompt §11).

AI predicts; algorithms coordinate; safety logic vetoes. This module contains
PURE functions used by every robot before movement execution. It never issues
motion — it only validates and, if a rule fails, vetoes the step with a reason.

Rules:
  1. minimum robot separation (emergency stop threshold)
  2. next-cell occupancy vs capacity
  3. narrow-aisle direction ownership
  4. reservation ownership for controlled junction crossing
  5. collision prediction over a short horizon (constant-velocity extrapolation)
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from .warehouse import WarehouseMap


@dataclass
class SafetyConfig:
    min_separation_m: float = 0.9
    slow_separation_m: float = 1.5
    collision_horizon_s: float = 2.0
    emergency_stop_gap_m: float = 0.75

    @staticmethod
    def from_cfg(cfg: Dict) -> "SafetyConfig":
        return SafetyConfig(
            min_separation_m=cfg.get("min_separation_m", 0.9),
            slow_separation_m=cfg.get("slow_separation_m", 1.5),
            collision_horizon_s=cfg.get("collision_horizon_s", 2.0),
            emergency_stop_gap_m=cfg.get("emergency_stop_gap_m", 0.75),
        )


# Veto reasons (surfaced in telemetry as safety_veto events)
VETO_SEPARATION = "SEPARATION"
VETO_CAPACITY = "NEXT_CELL_CAPACITY"
VETO_DIRECTION = "NARROW_DIRECTION"
VETO_RESERVATION = "RESERVATION_OWNERSHIP"
VETO_COLLISION_PREDICTION = "COLLISION_PREDICTION"


@dataclass
class PeerView:
    """Another robot as seen through heartbeats/intents (message-derived only)."""
    rid: str
    x: float = 0.0
    y: float = 0.0
    speed: float = 0.0
    edge: str = ""
    dir: int = 0
    s: float = 0.0
    uncertainty: float = 0.0
    urgency: float = 0.0
    effective_priority: float = 0.0
    state: str = "IDLE"

    @staticmethod
    def from_heartbeat(m: Dict) -> "PeerView":
        p = m.get("pos", [0, 0])
        return PeerView(
            rid=m["robot"], x=float(p[0]), y=float(p[1]), speed=float(m.get("speed", 0.0)),
            edge=m.get("edge", ""), dir=int(m.get("dir", 0)), s=float(m.get("s", 0.0)),
            urgency=float(m.get("urgency", 0.0)),
            effective_priority=float(m.get("effective_priority", 0.0)),
            state=m.get("state", "IDLE"),
        )


def separation_check(me: Tuple[float, float], peers: List[PeerView],
                     cfg: SafetyConfig) -> Optional[Tuple[str, str, float]]:
    """Rule 1. Returns (veto_reason, peer_id, distance) or None if safe."""
    closest: Optional[Tuple[str, float]] = None
    for p in peers:
        d = math.hypot(me[0] - p.x, me[1] - p.y)
        if closest is None or d < closest[1]:
            closest = (p.rid, d)
    if closest and closest[1] < cfg.min_separation_m:
        return (VETO_SEPARATION, closest[0], round(closest[1], 2))
    return None


def right_of_way(me: PeerView, other: PeerView) -> bool:
    """Deterministic right-of-way between two robots (used to break symmetric stops).

    Order: effective priority DESC, then robot id ASC. True => `me` proceeds.
    """
    if me.effective_priority > other.effective_priority + 1e-9:
        return True
    if other.effective_priority > me.effective_priority + 1e-9:
        return False
    return me.rid < other.rid


def next_cell_capacity(wmap: WarehouseMap, next_edge: str,
                       occupants: int, entering_from_node: str) -> Optional[str]:
    """Rule 2. occupants = robots currently ON the next edge (incl. queue head)."""
    e = wmap.edges.get(next_edge)
    if e is None:
        return VETO_CAPACITY
    if e.blocked:
        return VETO_CAPACITY
    if occupants >= e.capacity:
        return VETO_CAPACITY
    return None


def narrow_direction_check(gate_dir: Optional[int], my_dir: int) -> Optional[str]:
    """Rule 3. gate_dir: +1 south->north flow, -1 north->south, None = free."""
    if gate_dir is not None and gate_dir != 0 and gate_dir != my_dir:
        return VETO_DIRECTION
    return None


def reservation_check(required: bool, granted: bool) -> Optional[str]:
    """Rule 4. `required` = entering JEC-controlled junction or gate."""
    if required and not granted:
        return VETO_RESERVATION
    return None


def collision_prediction(me: PeerView, peers: List[PeerView],
                         cfg: SafetyConfig) -> Optional[Tuple[str, float]]:
    """Rule 5. Constant-velocity extrapolation over the horizon.

    Returns (peer_id, t_conflict) for the earliest conflict where the PEER has
    right of way, else None. Symmetric conflicts resolve by right_of_way so
    exactly one robot of a pair stops (deterministic).
    """
    t_conf: Optional[Tuple[str, float]] = None
    for p in peers:
        if p.state in ("FAILED", "CHARGING", "DOCKED"):
            continue
        # relative approach speed
        dx, dy = p.x - me.x, p.y - me.y
        dist = math.hypot(dx, dy)
        if dist < 1e-6:
            continue
        rel_vx = 0.0  # speeds are scalar along unknown headings; use worst-case closing
        closing = max(0.0, (me.speed + p.speed) * 0.5)
        if dist > cfg.collision_horizon_s * (me.speed + p.speed):
            continue
        # coarse check: distance shrinks below min separation within horizon?
        t_hit = (dist - cfg.min_separation_m) / (me.speed + p.speed) if (me.speed + p.speed) > 0 else math.inf
        if t_hit < cfg.collision_horizon_s:
            # deterministic: only the robot WITHOUT right of way vetoes
            if not right_of_way(me, p):
                if t_conf is None or t_hit < t_conf[1]:
                    t_conf = (p.rid, t_hit)
    return (VETO_COLLISION_PREDICTION, round(t_conf[1], 2)) if t_conf else None


def _heading(wmap: WarehouseMap, edge: str, dir_: int) -> Tuple[float, float]:
    e = wmap.edges[edge]
    dx = wmap.nodes[e.v].x - wmap.nodes[e.u].x
    dy = wmap.nodes[e.v].y - wmap.nodes[e.u].y
    L = math.hypot(dx, dy) or 1e-9
    ux, uy = dx / L, dy / L
    return (ux, uy) if dir_ > 0 else (-ux, -uy)


def _following(wmap: WarehouseMap, me: PeerView, other: PeerView) -> bool:
    """Car-following pair: same edge & direction, OR same heading on
    collinear adjacent edges with the peer close behind me.

    Physical order rules (the robot behind slows for the robot ahead) —
    priority never inverts following order, so these pairs are excluded
    from separation / collision-prediction vetoes.
    """
    if not me.edge or not other.edge:
        return False
    if me.edge == other.edge and me.dir == other.dir:
        return True
    try:
        h1 = _heading(wmap, me.edge, me.dir)
        h2 = _heading(wmap, other.edge, other.dir)
    except KeyError:
        return False
    if h1[0] * h2[0] + h1[1] * h2[1] < 0.9:      # headings differ -> not following
        return False
    dx, dy = other.x - me.x, other.y - me.y
    d = math.hypot(dx, dy)
    if d > 3.5:
        return False
    # peer BEHIND me along my heading -> I am the leader
    return (dx * h1[0] + dy * h1[1]) < 0.0


def validate_step(wmap: WarehouseMap, me: PeerView, peers: List[PeerView],
                  next_edge: str, next_dir: int, occupants_next: int,
                  gate_dir: Optional[int], reservation_required: bool,
                  reservation_granted: bool, cfg: SafetyConfig
                  ) -> List[Dict]:
    """Run all rules; return list of veto dicts (empty = movement allowed)."""
    vetoes: List[Dict] = []
    traffic = [p for p in peers if not _following(wmap, me, p)]

    sep = separation_check((me.x, me.y), traffic, cfg)
    if sep and not right_of_way(me, next(
            (p for p in traffic if p.rid == sep[1]), me)):
        vetoes.append({"rule": VETO_SEPARATION, "peer": sep[1], "value": sep[2]})

    cap = next_cell_capacity(wmap, next_edge, occupants_next, "")
    if cap:
        vetoes.append({"rule": cap, "edge": next_edge, "occupants": occupants_next})

    d = narrow_direction_check(gate_dir, next_dir)
    if d:
        vetoes.append({"rule": d, "gate_dir": gate_dir, "my_dir": next_dir})

    r = reservation_check(reservation_required, reservation_granted)
    if r:
        vetoes.append({"rule": r})

    cp = collision_prediction(me, traffic, cfg)
    if cp:
        vetoes.append({"rule": VETO_COLLISION_PREDICTION, "peer": cp[0], "t": cp[1]})

    return vetoes
