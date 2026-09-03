"""Routing: A* over the warehouse graph + k-alternative route generation.

Routes are lists of steps: {"edge": id, "dir": +1/-1}. Candidate routes are
generated with different cost biases (distance / congestion / externality
avoidance) so the prosocial planner can choose among genuine alternatives.
"""
from __future__ import annotations

import heapq
import math
from typing import Callable, Dict, List, Optional, Tuple

from .warehouse import WarehouseMap

Route = List[Dict]  # [{"edge": str, "dir": int}]

# virtual traffic geometry: travelling against a preferred corridor adds
# this cost (seconds-equivalent) — soft directionality, never a hard ban
AGAINST_FLOW_PENALTY = 9.0


def route_length(wmap: WarehouseMap, route: Route) -> float:
    return sum(wmap.edges[st["edge"]].length for st in route)


def route_time(wmap: WarehouseMap, route: Route, speed_scale: float = 1.0) -> float:
    return sum(wmap.edges[st["edge"]].length / max(0.1, wmap.edges[st["edge"]].speed * speed_scale)
               for st in route)


def route_end_node(wmap: WarehouseMap, route: Route) -> str:
    if not route:
        raise ValueError("empty route")
    return wmap.node_of_edge_end(route[-1]["edge"], route[-1]["dir"])


def route_start_node(wmap: WarehouseMap, route: Route) -> str:
    st = route[0]
    e = wmap.edges[st["edge"]]
    return e.v if st["dir"] < 0 else e.u


def astar(wmap: WarehouseMap, start: str, goal: str,
          edge_cost: Optional[Callable] = None) -> Optional[Route]:
    """A* from node `start` to node `goal`.

    edge_cost(edge, direction) overrides length; direction-aware costs let
    callers express virtual traffic corridors (preferred flow directions).
    """
    if start == goal:
        return []

    def cost(e, direction: int) -> float:
        base = edge_cost(e, direction) if edge_cost is not None else e.length
        if e.preferred_dir and direction != e.preferred_dir:
            base += AGAINST_FLOW_PENALTY
        return base

    goal_n = wmap.nodes[goal]

    def h(nid: str) -> float:
        n = wmap.nodes[nid]
        return math.hypot(n.x - goal_n.x, n.y - goal_n.y)

    dist = {start: 0.0}
    prev: Dict[str, Tuple[str, int]] = {}   # node -> (edge_id, dir)
    heap = [(h(start), 0.0, start)]
    while heap:
        _, d, cur = heapq.heappop(heap)
        if cur == goal:
            break
        if d > dist.get(cur, math.inf) + 1e-9:
            continue
        for eid, nb in wmap.adj[cur]:
            e = wmap.edges[eid]
            if e.blocked:
                continue
            direction = 1 if e.u == cur else -1
            nd = d + cost(e, direction)
            if nd < dist.get(nb, math.inf) - 1e-9:
                dist[nb] = nd
                prev[nb] = (eid, direction)
                heapq.heappush(heap, (nd + h(nb), nd, nb))
    if goal not in dist:
        return None
    route: Route = []
    cur = goal
    while cur != start:
        eid, direction = prev[cur]
        route.append({"edge": eid, "dir": direction})
        cur = wmap.edges[eid].other(cur)
    route.reverse()
    return route


def route_from_position(wmap: WarehouseMap, pos: Dict, goal: str,
                        edge_cost: Optional[Callable] = None) -> Optional[Route]:
    """Build a route starting at an (edge, s, dir) position.

    If the robot is mid-edge, the route may start with the remainder of the
    current edge in the current direction (only if that direction is on a
    path towards the goal), or a reversal.
    """
    if pos.get("node"):
        return astar(wmap, pos["node"], goal, edge_cost)
    eid = pos["edge"]
    cur_dir = pos["dir"]
    e = wmap.edges[eid]
    head = wmap.node_of_edge_end(eid, cur_dir)
    tail = wmap.node_of_edge_end(eid, -cur_dir)

    best: Optional[Route] = None
    for end, dir_ok in ((head, cur_dir), (tail, -cur_dir)):
        rest = astar(wmap, end, goal, edge_cost)
        if rest is None:
            continue
        route: Route = [{"edge": eid, "dir": dir_ok}] + rest
        if best is None or route_length(wmap, route) < route_length(wmap, best):
            best = route
    return best


def k_alternatives(wmap: WarehouseMap, start: str, goal: str,
                   congestion: Optional[Dict[str, float]] = None,
                   blocked_edges: Optional[set] = None) -> List[Route]:
    """Generate up to 3 distinct candidate routes (shortest / congestion-avoiding /
    detour-via-removal). Deduplicated by edge sequence."""
    congestion = congestion or {}
    blocked_edges = blocked_edges or set()

    def base_cost(e, direction):
        if e.id in blocked_edges or e.blocked:
            return math.inf
        return e.length

    def cong_cost(e, direction):
        if e.id in blocked_edges or e.blocked:
            return math.inf
        # penalise congested resources: predicted occupancy ratio of edge & its gate
        pen = 1.0 + 6.0 * min(1.5, congestion.get(e.id, 0.0))
        if e.aisle and e.aisle in congestion:
            pen += 4.0 * min(1.5, congestion[e.aisle])
        return e.length * pen

    r1 = astar(wmap, start, goal, base_cost)
    r2 = astar(wmap, start, goal, cong_cost)
    routes = []
    seen = set()
    for r in (r1, r2):
        if r is None:
            continue
        key = tuple(st["edge"] for st in r)
        if key not in seen:
            seen.add(key)
            routes.append(r)
    if routes:
        # third alternative: forbid the first edge of the best route to force a detour
        first_edge = routes[0][0]["edge"] if routes[0] else None
        if first_edge is not None:
            r3 = astar(wmap, start, goal, lambda e, d: math.inf if e.id == first_edge else base_cost(e, d))
            if r3 is not None:
                key = tuple(st["edge"] for st in r3)
                if key not in seen:
                    seen.add(key)
                    routes.append(r3)
    return routes


def step_arrival_times(wmap: WarehouseMap, route: Route, start_s: float = 0.0,
                       speed_scale: float = 1.0) -> List[Tuple[Dict, float, float]]:
    """ETA windows [(step, t_in, t_out)] for each route step from current progress."""
    out: List[Tuple[Dict, float, float]] = []
    t = 0.0
    first = True
    for st in route:
        e = wmap.edges[st["edge"]]
        v = max(0.1, e.speed * speed_scale)
        remain = e.length - start_s if first else e.length
        remain = max(0.0, remain)
        t_out = t + remain / v
        out.append((st, t, t_out))
        t = t_out
        first = False
    return out


def route_summary(wmap: WarehouseMap, route: Route) -> Dict:
    """Compact description used in intents and decision explainers."""
    return {
        "edges": [st["edge"] for st in route],
        "length": round(route_length(wmap, route), 2),
        "time": round(route_time(wmap, route), 2),
    }
