"""Unit tests for fleet_core: map, routing, capacity, social cost, safety, fairness."""
import os
import sys

import pytest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, ROOT)

from robotics_ws.fleet_core.warehouse import WarehouseMap          # noqa: E402
from robotics_ws.fleet_core.routing import (astar, k_alternatives,  # noqa: E402
                                            route_length, route_from_position,
                                            step_arrival_times)
from robotics_ws.fleet_core.social import SocialWeights, evaluate_route, choose_route  # noqa: E402
from robotics_ws.fleet_core.safety import (SafetyConfig, PeerView,  # noqa: E402
                                           separation_check, next_cell_capacity,
                                           narrow_direction_check, right_of_way,
                                           collision_prediction, validate_step)
from robotics_ws.fleet_core.fairness import (FairnessState, FairnessConfig,  # noqa: E402
                                             effective_priority, is_starving)
from robotics_ws.fleet_core.types import Reservation, ContextEvent  # noqa: E402

MAP = WarehouseMap.load(os.path.join(ROOT, "configs", "warehouse_map.json"))


# --------------------------------------------------------------- map
class TestMap:
    def test_loads(self):
        assert len(MAP.nodes) >= 60
        assert len(MAP.edges) >= 80

    def test_connected(self):
        ids = list(MAP.nodes)
        adj = {i: set() for i in ids}
        for e in MAP.edges.values():
            adj[e.u].add(e.v)
            adj[e.v].add(e.u)
        seen = set()
        stack = [ids[0]]
        while stack:
            n = stack.pop()
            if n in seen:
                continue
            seen.add(n)
            stack.extend(adj[n] - seen)
        coverage = len(seen) / max(1, len(ids))
        assert coverage >= 0.95
        assert len(set(ids) - seen) <= 2

    def test_jec_specs(self):
        assert len(MAP.jecs) >= 6
        assert MAP.jec_for_junction("J21") == "JEC-01"
        assert MAP.jec_for_junction("J01") is None
        assert MAP.jec_for_gate("NA2") == "JEC-07"
        assert MAP.jec_for_gate("UNKNOWN") is None

    def test_geometry(self):
        x, y = MAP.world_pos("SA1", 0.0, 1)
        assert (x, y) == (4.0, 4.0)
        x, y = MAP.world_pos("SA1", 6.0, 1)
        assert (x, y) == (10.0, 4.0)
        # reverse direction
        x, y = MAP.world_pos("SA1", 6.0, -1)
        assert (x, y) == (4.0, 4.0)
        # lane offset on wide aisle shifts laterally
        x1, y1 = MAP.world_pos("SA1", 3.0, 1, lane_offset=0.5)
        x2, y2 = MAP.world_pos("SA1", 3.0, -1, lane_offset=0.5)
        assert abs(x1 - x2) < 1e-6
        assert abs(y1 - y2) - 1.0 < 1e-6

    def test_narrow_aisle_membership(self):
        assert MAP.edge_to_gate("NA2b") == "NA2"
        assert MAP.edge_to_gate("SA1") is None


# --------------------------------------------------------------- routing
class TestRouting:
    def test_astar_basic(self):
        r = astar(MAP, "J01", "J09")
        assert r is not None
        assert route_length(MAP, r) == pytest.approx(42.0, abs=0.01)

    def test_astar_same_node(self):
        assert astar(MAP, "J01", "J01") == []

    def test_astar_unreachable_when_blocked(self):
        # block all edges around J19's component? Instead: block target edges
        MAP.edges["SP1"].blocked = True
        MAP.edges["SP2"].blocked = True
        try:
            r = astar(MAP, "J06", "J15")   # spine blocked, must go around
            assert r is not None
            assert "SP1" not in [s["edge"] for s in r]
            assert "SP2" not in [s["edge"] for s in r]
            # alternate route exists (via east connector or rack aisles)
            assert route_length(MAP, r) > 18.0
        finally:
            MAP.edges["SP1"].blocked = False
            MAP.edges["SP2"].blocked = False

    def test_alternatives_exist(self):
        alts = k_alternatives(MAP, "J02", "J22")
        assert len(alts) >= 2
        keys = {tuple(s["edge"] for s in r) for r in alts}
        assert len(keys) == len(alts)   # distinct

    def test_arrival_times_monotonic(self):
        r = astar(MAP, "J01", "J09")
        w = step_arrival_times(MAP, r, start_s=2.0)
        assert all(w[i][2] <= w[i + 1][1] + 1e-9 for i in range(len(w) - 1))

    def test_route_from_position_mid_edge(self):
        pos = {"edge": "SA1", "s": 2.0, "dir": 1}
        r = route_from_position(MAP, pos, "J12")
        assert r is not None
        assert r[0]["edge"] == "SA1"
        # going forward to J02 then up rack aisle NA1 is one valid option
        end = MAP.node_of_edge_end(r[-1]["edge"], r[-1]["dir"])
        assert end == "J12"


# --------------------------------------------------------------- social
class TestSocialCost:
    def test_empty_intents_no_externality(self):
        r = astar(MAP, "J01", "J09")
        rc = evaluate_route(MAP, r, SocialWeights(), {}, {})
        assert rc.externality == 0.0
        assert rc.own == pytest.approx(42.0 / 1.6, abs=0.5)
        assert rc.total > 0

    def test_externality_grows_with_conflicting_intents(self):
        r = astar(MAP, "J01", "J09")
        # R02/R03 will occupy SA1 (my first edge) exactly when I arrive (t≈0-5s)
        others = {
            "R02": {"targets": [{"resource": "SA1", "eta": 0.5, "dur": 5.0}],
                    "route": [{"edge": "SA1"}]},
            "R03": {"targets": [{"resource": "SA1", "eta": 2.0, "dur": 4.0}],
                    "route": [{"edge": "SA1"}]},
        }
        empty = evaluate_route(MAP, r, SocialWeights(), {}, {})
        loaded = evaluate_route(MAP, r, SocialWeights(), others, {})
        assert loaded.externality > empty.externality

    def test_prosocial_choice_overrides_shortest(self):
        start, goal = "J02", "J12"
        alts = k_alternatives(MAP, start, goal)
        assert len(alts) >= 2
        baseline, _, _ = choose_route(MAP, alts, SocialWeights(externality=0.0), {}, {})
        contested = [s["edge"] for s in baseline[:2]]
        others = {
            f"R0{i}": {"targets": [{"resource": contested[0], "eta": 0.5 + 0.4 * i, "dur": 18.0}],
                       "route": [{"edge": contested[0]}]}
            for i in (5, 6, 7)
        }
        weights = SocialWeights(externality=1.0)
        best, _, expl = choose_route(MAP, alts, weights, others, {})
        contested_choice = [e for e in expl if contested[0] in e["route"]]
        assert contested_choice and contested_choice[0]["breakdown"]["externality"] > 0
        best_total = min(e["breakdown"]["total"] for e in expl)
        chosen_total = next(e["breakdown"]["total"] for e in expl if e["route"] == [s["edge"] for s in best])
        assert chosen_total == pytest.approx(best_total, abs=1e-6)
        assert len(expl) == len(alts)
        assert "externality" in expl[0]["breakdown"]

    def test_congestion_wait_term(self):
        r = astar(MAP, "J01", "J09")
        rc0 = evaluate_route(MAP, r, SocialWeights(), {}, {})
        rc1 = evaluate_route(MAP, r, SocialWeights(), {},
                             {"SA1": 2.0, "SA2": 2.0})   # wide edges saturated
        assert rc1.wait > rc0.wait
        assert rc1.congestion > rc0.congestion


# --------------------------------------------------------------- safety
class TestSafety:
    def test_separation_veto(self):
        cfg = SafetyConfig()
        me = (5.0, 4.0)
        peers = [PeerView(rid="R02", x=5.4, y=4.0, speed=0.0, effective_priority=0.0)]
        v = separation_check(me, peers, cfg)
        assert v is not None and v[0] == "SEPARATION" and v[2] < 0.9

    def test_separation_safe(self):
        cfg = SafetyConfig()
        peers = [PeerView(rid="R02", x=9.0, y=4.0)]
        assert separation_check((5.0, 4.0), peers, cfg) is None

    def test_capacity_veto_narrow(self):
        v = next_cell_capacity(MAP, "NA1a", 1, "J02")
        assert v == "NEXT_CELL_CAPACITY"
        assert next_cell_capacity(MAP, "NA1a", 0, "J02") is None

    def test_capacity_ok_wide(self):
        assert next_cell_capacity(MAP, "SA1", 1, "J01") is None
        assert next_cell_capacity(MAP, "SA1", 2, "J01") == "NEXT_CELL_CAPACITY"

    def test_direction_check(self):
        assert narrow_direction_check(1, -1) == "NARROW_DIRECTION"
        assert narrow_direction_check(1, 1) is None
        assert narrow_direction_check(None, -1) is None

    def test_right_of_way_deterministic(self):
        a = PeerView(rid="R01", effective_priority=2.0)
        b = PeerView(rid="R02", effective_priority=3.0)
        assert right_of_way(a, b) is False
        assert right_of_way(b, a) is True
        # tie -> lower id
        a2 = PeerView(rid="R07", effective_priority=2.0)
        b2 = PeerView(rid="R03", effective_priority=2.0)
        assert right_of_way(a2, b2) is False
        assert right_of_way(b2, a2) is True
        # identical inputs -> deterministic
        assert right_of_way(a2, b2) == right_of_way(a2, b2)

    def test_collision_prediction_resolves_one_side(self):
        cfg = SafetyConfig()
        me = PeerView(rid="R01", x=0.0, y=0.0, speed=1.0, effective_priority=1.0)
        peer = PeerView(rid="R02", x=2.0, y=0.0, speed=1.0, effective_priority=1.0)
        # closing head-on; tie priority -> R01 (lower id) has right of way
        assert collision_prediction(me, [peer], cfg) is None
        # R02 lacks right of way -> vetoes
        assert collision_prediction(peer, [me], cfg) is not None

    def test_validate_step_multi_veto(self):
        cfg = SafetyConfig()
        me = PeerView(rid="R09", x=5.0, y=4.0, speed=1.0, effective_priority=0.0)
        peers = [PeerView(rid="R01", x=5.2, y=4.0, speed=0.0, effective_priority=1.0)]
        vetoes = validate_step(MAP, me, peers, "NA1a", 1, 1, -1, True, False, cfg)
        rules = {v["rule"] for v in vetoes}
        assert "NARROW_DIRECTION" in rules
        assert "NEXT_CELL_CAPACITY" in rules
        assert "RESERVATION_OWNERSHIP" in rules


# --------------------------------------------------------------- fairness
class TestFairness:
    def test_aging_increases_priority(self):
        cfg = FairnessConfig()
        st = FairnessState()
        st.start_wait(10.0)
        p_low = effective_priority(st, cfg, 10.0)
        p_high = effective_priority(st, cfg, 22.0)
        assert p_high > p_low

    def test_yield_and_denial_bonuses(self):
        cfg = FairnessConfig()
        st = FairnessState()
        st.register_yield(); st.register_yield(); st.register_denial()
        p = effective_priority(st, cfg, 0.0)
        assert p >= 1.0 + 2 * 0.8 + 0.5 - 1e-9

    def test_priority_capped(self):
        cfg = FairnessConfig(max_effective_priority=5.0)
        st = FairnessState(yields=100, denials=100)
        assert effective_priority(st, cfg, 0.0) == 5.0

    def test_starvation_detector(self):
        cfg = FairnessConfig(starvation_wait_s=12.0)
        st = FairnessState()
        st.start_wait(100.0)
        assert is_starving(st, cfg, 113.0) is True
        assert is_starving(st, cfg, 104.0) is False

    def test_wait_accumulation(self):
        st = FairnessState()
        st.start_wait(5.0)
        assert st.stop_wait(7.5) == 2.5
        assert st.accumulated_wait == 2.5
        assert st.wait_since == 0.0


# --------------------------------------------------------------- types
class TestTypes:
    def test_reservation_overlap(self):
        a = Reservation(resource="J19", robot="R01", start=1.0, end=3.0, priority=1)
        b = Reservation(resource="J19", robot="R02", start=2.5, end=4.0, priority=1)
        c = Reservation(resource="J19", robot="R03", start=3.5, end=5.0, priority=1)
        assert a.overlaps(b)
        assert not a.overlaps(c)
        assert a.overlaps(c, margin=0.75)

    def test_reservation_roundtrip(self):
        r = Reservation(resource="J05", robot="R07", start=1.2, end=2.4, priority=3.3,
                        state="GRANTED", lease=4.0, resv_id="r1")
        r2 = Reservation.from_msg(r.to_msg())
        assert r2.resource == r.resource and r2.state == "GRANTED"
        assert r2.priority == 3.3

    def test_context_event_ttl(self):
        ev = ContextEvent(ev_type="AISLE_BLOCKED", value="NA3", reporter="R04",
                          t=100.0, ttl=20.0)
        assert ev.expired(115.0) is False
        assert ev.expired(121.0) is True

    def test_context_roundtrip(self):
        ev = ContextEvent(ev_type="JEC_OFFLINE", value="JEC-J19", reporter="R01",
                          t=1.0, confidence=0.9, ttl=5.0, affected=["J19"], seq=3)
        m = ev.to_msg()
        ev2 = ContextEvent.from_msg(m)
        assert ev2.ev_type == "JEC_OFFLINE" and ev2.seq == 3
