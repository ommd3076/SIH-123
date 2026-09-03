"""Prosocial social-cost function (build prompt §8).

route_cost = w_dist * own_travel_time
           + w_wait * expected_wait
           + w_energy * estimated_energy
           + w_cong * congestion_cost
           + w_ext  * externality (delay imposed on local fleet)
           + w_risk * safety/risk cost

The externality term only considers robots within the local prediction
horizon whose intents overlap the candidate route's resources.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Tuple

from .warehouse import WarehouseMap
from .routing import Route, route_length, route_time, step_arrival_times


@dataclass
class SocialWeights:
    distance: float = 1.0
    wait: float = 1.0
    energy: float = 0.05
    congestion: float = 0.6
    externality: float = 0.8
    risk: float = 0.4

    @staticmethod
    def from_cfg(cfg: Dict[str, Any]) -> "SocialWeights":
        return SocialWeights(**{k: float(v) for k, v in cfg.items()})


@dataclass
class RouteCost:
    own: float = 0.0
    wait: float = 0.0
    energy: float = 0.0
    congestion: float = 0.0
    externality: float = 0.0
    risk: float = 0.0
    total: float = 0.0
    detail: Dict[str, float] = field(default_factory=dict)

    def breakdown(self) -> Dict[str, float]:
        return {
            "own_cost": round(self.own, 2), "expected_wait": round(self.wait, 2),
            "energy": round(self.energy, 2), "congestion": round(self.congestion, 2),
            "externality": round(self.externality, 2), "risk": round(self.risk, 2),
            "total": round(self.total, 2),
        }


def _resource_service(wmap: WarehouseMap, edge_id: str) -> float:
    e = wmap.edges[edge_id]
    if e.is_narrow:
        return e.length / e.speed          # whole-aisle contention matters
    return 1.6                              # junction-ish service time


def evaluate_route(wmap: WarehouseMap, route: Route,
                   weights: SocialWeights,
                   others_intents: Dict[str, Dict[str, Any]],
                   congestion: Dict[str, float],
                   horizon: float = 5.0,
                   start_s: float = 0.0,
                   speed_scale: float = 1.0) -> RouteCost:
    """Compute the social cost of a candidate route.

    others_intents: {robot_id: {"targets": [{"resource":..., "eta":..., "dur":...}],
                                 "route": [{"edge":...}]}}
    congestion: {resource_id: predicted occupancy ratio (0..n)}
    """
    if not route:
        return RouteCost()

    own_time = route_time(wmap, route, speed_scale)
    length = route_length(wmap, route)

    windows = step_arrival_times(wmap, route, start_s, speed_scale)

    # ---- wait expectation: resources I will use whose predicted occupancy
    # already exceeds capacity while I am there.
    wait = 0.0
    for st, t_in, t_out in windows:
        e = wmap.edges[st["edge"]]
        res = e.id
        pred = congestion.get(res, 0.0)
        cap = e.capacity
        if pred > cap - 1 + 1e-9 and t_in < horizon:
            wait += _resource_service(wmap, res) * 0.6
        if e.aisle:
            gate_pred = congestion.get(e.aisle, 0.0)
            if gate_pred >= 1.0 and t_in < horizon:
                wait += e.length / max(0.1, e.speed) * 0.5

    # ---- congestion cost (predicted, from JEC congestion estimates)
    cong = 0.0
    for st, t_in, t_out in windows:
        if t_in > horizon:
            break
        e = wmap.edges[st["edge"]]
        cong += congestion.get(e.id, 0.0) * _resource_service(wmap, e.id) * 0.5
        if e.aisle:
            cong += congestion.get(e.aisle, 0.0) * 1.0

    # ---- externality: delay imposed on others whose intents overlap my
    # resources within the horizon.
    my_res_windows: List[Tuple[str, float, float]] = []
    for st, t_in, t_out in windows:
        e = wmap.edges[st["edge"]]
        my_res_windows.append((e.id, t_in, t_out))
        if e.aisle:
            my_res_windows.append((e.aisle, t_in, t_out))

    externality = 0.0
    for rid, intent in others_intents.items():
        if rid == "":
            continue
        targets = intent.get("targets", [])
        route_edges = {r.get("edge") for r in intent.get("route", [])}
        for res, r_eta, r_dur in [(t.get("resource", ""), t.get("eta", 0.0), t.get("dur", 0.0)) for t in targets]:
            if not res:
                continue
            for my_res, t_in, t_out in my_res_windows:
                if my_res != res and not (
                        my_res in route_edges and res in {st["edge"] for st in route}):
                    continue
                # time overlap that begins within the (extended) horizon?
                if (max(t_in, r_eta) < min(t_out, r_eta + r_dur)
                        and max(t_in, r_eta) < horizon + 2.0):
                    if my_res in wmap.aisles:
                        # whole-aisle contention: blocking an opposing robot
                        # costs it the full traversal time
                        a = wmap.aisles[my_res]
                        service = sum(wmap.edges[eid].length / wmap.edges[eid].speed
                                      for eid in a.edges)
                        externality += service * 0.7
                    else:
                        e = wmap.edges.get(my_res)
                        if e is None:
                            externality += 1.2 * 0.7
                        else:
                            service = _resource_service(wmap, my_res)
                            if e.capacity <= 1 or e.is_narrow:
                                externality += service * 0.7
                            else:
                                externality += service * 0.25
                    break

    # ---- risk: narrow-aisle opposing-flow risk + blocked proximity
    risk = 0.0
    for st, t_in, t_out in windows:
        e = wmap.edges[st["edge"]]
        if e.is_narrow:
            risk += 0.3

    energy = length * 0.01

    rc = RouteCost(
        own=own_time, wait=wait, energy=energy, congestion=cong,
        externality=externality, risk=risk,
    )
    rc.total = (weights.distance * rc.own + weights.wait * rc.wait +
                weights.energy * rc.energy + weights.congestion * rc.congestion +
                weights.externality * rc.externality + weights.risk * rc.risk)
    return rc


def choose_route(wmap: WarehouseMap, candidates: List[Route],
                 weights: SocialWeights,
                 others_intents: Dict[str, Dict[str, Any]],
                 congestion: Dict[str, float],
                 horizon: float = 5.0,
                 start_s: float = 0.0) -> Tuple[Route, RouteCost, List[Dict[str, Any]]]:
    """Pick the candidate with minimum social cost; return explanation per candidate."""
    evaluated: List[Tuple[Route, RouteCost]] = []
    for r in candidates:
        rc = evaluate_route(wmap, r, weights, others_intents, congestion, horizon, start_s)
        evaluated.append((r, rc))
    if not evaluated:
        raise ValueError("no candidate routes")
    evaluated.sort(key=lambda x: (x[1].total, route_length(wmap, x[0])))
    best, best_cost = evaluated[0]
    explanations = [
        {"route": [st["edge"] for st in r], "breakdown": rc.breakdown()}
        for r, rc in evaluated
    ]
    return best, best_cost, explanations
