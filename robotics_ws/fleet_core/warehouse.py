"""Warehouse map: graph model, geometry and capacity semantics.

The warehouse is a node/edge graph (junctions, bays, zones) with per-edge
capacity, width class and speed. Movement happens along edges; junction
crossings and narrow-aisle entries are shared resources arbitrated by JECs
or P2P intent coordination. Geometry helpers convert (edge, s) coordinates
to world (x, y) with lane offsets for visual separation on wide aisles.
"""
from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple

NARROW = "aisle_narrow"
WIDE_TYPES = {"aisle_wide", "aisle_north", "bypass", "spine", "midspine", "connector"}
ZONE_TYPES = {"pickup", "drop", "charge", "staging"}
BAY = "bay"


@dataclass
class WNode:
    id: str
    type: str
    x: float
    y: float
    capacity: int = 1
    aisle: str = ""
    label: str = ""

    @property
    def is_junction(self) -> bool:
        return self.type == "junction"

    @property
    def is_zone(self) -> bool:
        return self.type in ZONE_TYPES

    @property
    def is_bay(self) -> bool:
        return self.type == BAY


@dataclass
class WEdge:
    id: str
    type: str
    u: str          # 'from' node
    v: str          # 'to' node
    capacity: int
    width: float
    speed: float
    aisle: str = ""
    length: float = 0.0
    blocked: bool = False
    preferred_dir: int = 0      # virtual traffic corridor: 0 = bidirectional

    @property
    def is_narrow(self) -> bool:
        return self.type == NARROW

    def other(self, node: str) -> str:
        return self.v if node == self.u else self.u


@dataclass
class NarrowAisle:
    id: str
    edges: List[str]
    south: str
    north: str
    jec: Optional[str] = None


@dataclass
class JecSpec:
    id: str
    junction: str
    gate: Optional[str] = None
    covers: List[str] = field(default_factory=list)  # adjacent edge ids


class WarehouseMap:
    def __init__(self, data: Dict):
        self.meta = data["meta"]
        self.bounds = tuple(self.meta["bounds"])
        self.junction_box = self.meta.get("junction_box", 0.9)
        self.bay_dwell_pick = self.meta.get("bay_dwell_pick_s", 3.0)
        self.bay_dwell_drop = self.meta.get("bay_dwell_drop_s", 2.5)

        self.nodes: Dict[str, WNode] = {}
        for n in data["nodes"]:
            self.nodes[n["id"]] = WNode(
                id=n["id"], type=n["type"], x=float(n["x"]), y=float(n["y"]),
                capacity=int(n.get("capacity", 1)), aisle=n.get("aisle", ""),
                label=n.get("label", ""),
            )
        self.edges: Dict[str, WEdge] = {}
        for e in data["edges"]:
            length = self._dist(e["from"], e["to"])
            self.edges[e["id"]] = WEdge(
                id=e["id"], type=e["type"], u=e["from"], v=e["to"],
                capacity=int(e.get("capacity", 2)), width=float(e.get("width", 3.0)),
                speed=float(e.get("speed", 1.2)), aisle=e.get("aisle", ""), length=length,
                preferred_dir=int(e.get("preferred_dir", 0)),
            )
        self.aisles: Dict[str, NarrowAisle] = {}
        for a in data.get("narrow_aisles", []):
            self.aisles[a["id"]] = NarrowAisle(
                id=a["id"], edges=a["edges"], south=a["south"], north=a["north"],
                jec=a.get("jec"),
            )

        # adjacency: node -> [(edge_id, neighbor)]  (needed by JEC coverage)
        self.adj: Dict[str, List[Tuple[str, str]]] = {nid: [] for nid in self.nodes}
        for e in self.edges.values():
            self.adj[e.u].append((e.id, e.v))
            self.adj[e.v].append((e.id, e.u))

        self.jecs: Dict[str, JecSpec] = {}
        for j in data.get("jecs", []):
            jid = j["id"]
            self.jecs[jid] = JecSpec(
                id=jid, junction=j["junction"], gate=j.get("gate"),
                covers=self._edges_touching(j["junction"]),
            )
            for gate_id in j.get("aisle_ids", []):
                if gate_id in self.aisles:
                    self.aisles[gate_id].jec = jid
        self.zones_roles: Dict[str, str] = {k: v["role"] for k, v in data.get("zones", {}).items()}
        self.spawn: List[Dict] = data.get("spawn", [])

    # ------------------------------------------------------------------
    @classmethod
    def load(cls, path: str) -> "WarehouseMap":
        with open(path) as f:
            return cls(json.load(f))

    def _dist(self, a: str, b: str) -> float:
        na, nb = self.nodes[a], self.nodes[b]
        return math.hypot(na.x - nb.x, na.y - nb.y)

    def _edges_touching(self, node: str) -> List[str]:
        return [eid for eid, _ in self.adj[node]]

    # ------------------------------------------------------------------
    # Resource ownership
    def jec_for_junction(self, junction: str) -> Optional[str]:
        for j in self.jecs.values():
            if j.junction == junction:
                return j.id
        return None

    def jec_for_gate(self, gate: str) -> Optional[str]:
        return self.aisles[gate].jec if gate in self.aisles else None

    def edge_to_gate(self, edge_id: str) -> Optional[str]:
        e = self.edges.get(edge_id)
        return e.aisle if e and e.aisle else None

    def gate_edges(self, gate: str) -> Set[str]:
        return set(self.aisles[gate].edges) if gate in self.aisles else set()

    def node_of_edge_end(self, edge_id: str, direction: int) -> str:
        """End node reached when travelling along the edge in given direction."""
        e = self.edges[edge_id]
        return e.v if direction > 0 else e.u

    # ------------------------------------------------------------------
    # Geometry
    def edge_geometry(self, edge_id: str) -> Tuple[Tuple[float, float], Tuple[float, float]]:
        e = self.edges[edge_id]
        nu, nv = self.nodes[e.u], self.nodes[e.v]
        return (nu.x, nu.y), (nv.x, nv.y)

    def world_pos(self, edge_id: str, s: float, direction: int, lane_offset: float = 0.0) -> Tuple[float, float]:
        """Convert (edge, s metres, direction) to world coords with a lateral lane offset.

        Lane offset is applied to the traveller's right-hand side (right-hand traffic).
        direction=+1 travels u->v, -1 travels v->u.
        """
        e = self.edges[edge_id]
        nu, nv = self.nodes[e.u], self.nodes[e.v]
        dx, dy = nv.x - nu.x, nv.y - nu.y
        L = e.length or 1e-9
        ux, uy = dx / L, dy / L          # unit along edge (u->v)
        t = s if direction > 0 else L - s
        # right-hand normal of travel direction
        if direction > 0:
            rx, ry = -uy, ux
        else:
            rx, ry = uy, -ux
        x = nu.x + ux * t + rx * lane_offset
        y = nu.y + uy * t + ry * lane_offset
        return x, y

    def node_pos(self, node_id: str) -> Tuple[float, float]:
        n = self.nodes[node_id]
        return n.x, n.y

    def lane_offset_for(self, edge_id: str) -> float:
        """Visual lane offset: wide aisles offset right, narrow aisles centreline."""
        e = self.edges[edge_id]
        if e.is_narrow:
            return 0.0
        return min(0.55, max(0.25, (e.width - 1.6) * 0.25))

    # ------------------------------------------------------------------
    def pickups(self) -> List[str]:
        return [n.id for n in self.nodes.values() if n.type == "pickup"]

    def drops(self) -> List[str]:
        return [n.id for n in self.nodes.values() if n.type == "drop"]

    def bays(self) -> List[str]:
        return [n.id for n in self.nodes.values() if n.type == BAY]

    def charge_node(self) -> str:
        for n in self.nodes.values():
            if n.type == "charge":
                return n.id
        raise KeyError("no charge node")

    def staging_nodes(self) -> List[str]:
        return [n.id for n in self.nodes.values() if n.type == "staging"]

    def to_frontend(self) -> Dict:
        """Serialise a render-ready map for the dashboard."""
        return {
            "meta": self.meta,
            "nodes": [
                {"id": n.id, "type": n.type, "x": n.x, "y": n.y, "label": n.label,
                 "capacity": n.capacity, "aisle": n.aisle}
                for n in self.nodes.values()
            ],
            "edges": [
                {"id": e.id, "type": e.type, "u": e.u, "v": e.v, "capacity": e.capacity,
                 "width": e.width, "speed": e.speed, "length": round(e.length, 2),
                 "preferred_dir": e.preferred_dir}
                for e in self.edges.values()
            ],
            "aisles": {a.id: {"edges": a.edges, "south": a.south, "north": a.north, "jec": a.jec}
                       for a in self.aisles.values()},
            "jecs": {j.id: {"junction": j.junction, "gate": j.gate, "covers": j.covers}
                     for j in self.jecs.values()},
            "zones_roles": self.zones_roles,
            "spawn": self.spawn,
        }
