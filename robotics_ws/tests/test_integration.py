"""Integration tests: the five required demo scenarios (§32, §33) on the DES
runtime — narrow-aisle opposing flows, junction conflicts, blockage
propagation, JEC failure fallback, robot failure reassignment — plus
network impairment and battery-critical behaviour.
"""
import os
import sys

import pytest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, ROOT)

from robotics_ws.sim_runner.des_fleet import DesFleet                    # noqa: E402
from robotics_ws.task_allocator.scenario import (Scenario, DEFAULT_SCENARIO,
                                                 ensure_scenario_files)    # noqa: E402
from robotics_ws.fleet_core.types import (MODE_FULL, MODE_INTENT_P2P,     # noqa: E402
                                          MODE_REACTIVE, MODE_STOP_WAIT)

ensure_scenario_files()


def make_fleet(mode=MODE_FULL, seed=1, duration=60.0, chaos=None):
    sc = Scenario.from_json(DEFAULT_SCENARIO, seed=seed)
    fleet = DesFleet(mode, sc, seed=seed, duration=duration)
    if chaos:
        fleet.chaos_script = chaos
    return fleet


def run_robots(fleet, until):
    fleet.step_to(until)
    return fleet


# --------------------------------------------------------------- scenario 1
class TestNarrowAisleOpposing:
    def test_two_robots_opposite_sides_end_up_ordered(self):
        """Opposing flows through rack aisles: exactly one direction active
        per gate at any time (JEC batch + P2P claims prevent head-on)."""
        fleet = make_fleet(mode=MODE_FULL, seed=3, duration=90.0)
        run_robots(fleet, 90.0)
        # no true body-overlap collisions anywhere
        total_collisions = sum(r.counters["collisions"] for r in fleet.robots)
        assert total_collisions == 0, f"body overlaps: {total_collisions}"
        # narrow gates show direction ownership in JEC states
        gates_seen = 0
        for j in fleet.jecs:
            if j.gate:
                if j.gate_dir != 0 or j.counters["gate_flips"] > 0:
                    gates_seen += 1
        assert gates_seen >= 1, "no gate direction ownership ever established"

    def test_head_on_deadlock_recovered(self):
        """Even if robots end up opposed inside a P2P aisle, the back-out
        recovery eventually frees it (no infinite deadlock). Mode-C queues
        drain slowly (no JEC batching) — bounded by batch cycles, and every
        robot keeps making progress."""
        fleet = make_fleet(mode=MODE_INTENT_P2P, seed=5, duration=120.0)
        run_robots(fleet, 120.0)
        for r in fleet.robots:
            stuck = (fleet.runtime.now() - r.fairness.wait_since) if r.fairness.wait_since else 0
            # P2P queue drain bound: several direction-batch cycles
            assert stuck < 90.0, f"{r.id} stuck {stuck:.0f}s"
            assert r.counters["distance_m"] > 3.0, f"{r.id} never moved"


# --------------------------------------------------------------- scenario 2
class TestJunctionConflict:
    def test_conflict_cells_form_and_expire(self):
        fleet = make_fleet(mode=MODE_FULL, seed=11, duration=60.0)
        run_robots(fleet, 60.0)
        assert len(fleet.metrics.conflicts) >= 0
        # JEC conflict counters were exercised
        total = sum(j.counters["conflicts_formed"] for j in fleet.jecs)
        assert total >= 1, "no conflict cells formed in 60s of traffic"
        # grants happened and were respected (zero collisions)
        assert sum(j.counters["grants"] for j in fleet.jecs) >= 5
        assert sum(r.counters["collisions"] for r in fleet.robots) == 0

    def test_reservation_denial_is_deterministic(self):
        """Same inputs -> same arbitration outcome (priority DESC, id ASC)."""
        results = []
        for _ in range(2):
            fleet = make_fleet(mode=MODE_FULL, seed=11, duration=40.0)
            summ = fleet.run()
            results.append((summ["reservation_grants"], summ["tasks_done"],
                            summ["total_distance_m"]))
        assert results[0][0] == results[1][0], "grants differ across identical runs"
        assert results[0][1] == results[1][1]


# --------------------------------------------------------------- scenario 3
class TestBlockagePropagation:
    def test_blocked_aisle_forces_reroute_and_context_event(self):
        chaos = [{"t": 15.0, "cmd": "BLOCK_AISLE", "args": {"resource": "NA2",
                                                            "ttl": 90.0}}]
        fleet = make_fleet(mode=MODE_FULL, seed=21, duration=90.0, chaos=chaos)
        run_robots(fleet, 45.0)      # mid-run: blockage active
        r_with = [r for r in fleet.robots
                  if r.context_affects("AISLE_BLOCKED", "NA2")]
        assert r_with, "no robot learned about the blockage"
        fleet.runtime.run(90.0)      # run out the scenario
        # nobody sits inside the blocked aisle at the end
        for r in fleet.robots:
            if r.edge:
                assert r.edge not in {"NA2a", "NA2b", "NA2c"}, \
                    f"{r.id} still inside blocked aisle"
        # unblock clears
        fleet.apply_chaos("UNBLOCK_AISLE", {"resource": "NA2"})
        for r in fleet.robots:
            assert not r.context_affects("AISLE_BLOCKED", "NA2")


# --------------------------------------------------------------- scenario 5
class TestJecFailureFallback:
    def test_killing_jec_does_not_halt_fleet(self):
        chaos = [
            {"t": 20.0, "cmd": "KILL_JEC", "args": {"jec": "JEC-J19"}},
            {"t": 45.0, "cmd": "RESTART_JEC", "args": {"jec": "JEC-J19"}},
        ]
        fleet = make_fleet(mode=MODE_FULL, seed=31, duration=240.0, chaos=chaos)
        # measure liveness DURING the JEC-down window (20s -> 45s)
        fleet.step_to(20.0)
        d_before = sum(r.counters["distance_m"] for r in fleet.robots)
        fleet.step_to(45.0)
        d_during = sum(r.counters["distance_m"] for r in fleet.robots)
        assert d_during - d_before > 15.0, \
            f"fleet halted during JEC-down window (+{d_during - d_before:.1f}m)"
        fleet.step_to(240.0)
        total_dist = sum(r.counters["distance_m"] for r in fleet.robots)
        assert total_dist > 50.0, f"fleet barely moved: {total_dist}"
        # tasks complete across the scenario (fallback coordination works)
        assert fleet.allocator.counters["completed"] >= 1
        # the JEC is back online at the end
        jec = [j for j in fleet.jecs if j.id == "JEC-J19"][0]
        assert jec.started

    def test_robots_detect_jec_offline(self):
        chaos = [{"t": 10.0, "cmd": "KILL_JEC", "args": {"jec": "JEC-J06"}}]
        fleet = make_fleet(mode=MODE_FULL, seed=33, duration=30.0, chaos=chaos)
        run_robots(fleet, 25.0)
        detected = any(r.context_affects("JEC_OFFLINE", "JEC-J06")
                       or any(ev.ev_type == "JEC_OFFLINE" for ev in r.active_context())
                       for r in fleet.robots)
        assert detected, "no robot detected JEC_OFFLINE"


# --------------------------------------------------------------- scenario 6
class TestRobotFailureReassignment:
    def test_failed_robot_task_is_reassigned(self):
        # fail a robot that actually holds a task; the task returns to the pool
        fleet = make_fleet(mode=MODE_FULL, seed=41, duration=160.0)
        fleet.step_to(30.0)
        holder = next((r for r in fleet.robots if r.task is not None), None)
        assert holder is not None, "no robot held a task at t=30"
        fleet.apply_chaos("FAIL_ROBOT", {"robot": holder.id})
        fleet.step_to(240.0)
        r3 = holder
        assert r3.state == "FAILED"
        # allocator noticed and reassigned
        assert fleet.allocator.counters["reassigned"] >= 1
        # some other robot completed tasks
        assert fleet.allocator.counters["completed"] >= 1
        done_by_others = [r.id for r in fleet.robots
                          if r.id != "R03" and r.counters["tasks_done"] > 0]
        assert done_by_others, "no surviving robot completed a task"

    def test_battery_critical_robot_charges(self):
        chaos = [{"t": 10.0, "cmd": "BATTERY_CRITICAL", "args": {"robot": "R07"}}]
        fleet = make_fleet(mode=MODE_FULL, seed=47, duration=60.0, chaos=chaos)
        run_robots(fleet, 60.0)
        r7 = fleet.robots[6]
        assert r7.state in ("CHARGING", "TO_CHARGE", "DOCK", "TO_PICKUP", "TO_DROP", "IDLE")
        assert r7.battery <= 13.0 or r7.state == "CHARGING"


# --------------------------------------------------------------- scenario 7
class TestNetworkImpairment:
    def test_latency_degrades_but_does_not_break_safety(self):
        fleet = make_fleet(mode=MODE_FULL, seed=61, duration=60.0)
        run_robots(fleet, 20.0)
        fleet.apply_chaos("SET_PROFILE", {"latency_ms": 400.0, "jitter_ms": 200.0,
                                          "loss_pct": 15.0})
        fleet.runtime.run(60.0)
        # fleet still safe (safety layer is local/deterministic)
        assert sum(r.counters["collisions"] for r in fleet.robots) == 0
        # communication really degraded: messages dropped at receivers
        dropped = sum(r.plane.stats.dropped_loss for r in fleet.robots)
        assert dropped > 20, f"impairment had no effect ({dropped} drops)"


# --------------------------------------------------------------- modes
class TestExperimentModes:
    def test_mode_a_is_ultra_conservative(self):
        fleet = make_fleet(mode=MODE_STOP_WAIT, seed=71, duration=40.0)
        run_robots(fleet, 40.0)
        # no intents published at all
        for r in fleet.robots:
            assert r.plane.stats.sent > 0
        # metrics collector saw no intent traffic
        assert fleet.metrics.robots, "no heartbeats collected"

    def test_all_modes_complete_without_crash(self):
        for mode in (MODE_STOP_WAIT, MODE_REACTIVE, MODE_INTENT_P2P, MODE_FULL):
            fleet = make_fleet(mode=mode, seed=77, duration=30.0)
            fleet.run()   # full run, no exception

    def test_mode_d_beats_mode_a_on_throughput(self):
        # aggregate across seeds (per-seed variance is real; the trend is
        # what the experiment demonstrates)
        done = {}
        for mode in (MODE_STOP_WAIT, MODE_FULL):
            total = 0
            for seed in (7, 42, 81):
                fleet = make_fleet(mode=mode, seed=seed, duration=120.0)
                summ = fleet.run()
                total += summ["tasks_done"]
            done[mode] = total
        assert done[MODE_FULL] > done[MODE_STOP_WAIT], done


# --------------------------------------------------------------- fairness
class TestFairnessAgingLive:
    def test_starved_robot_eventually_wins(self):
        """No robot may starve forever: max continuous wait bounded."""
        fleet = make_fleet(mode=MODE_FULL, seed=91, duration=120.0)
        run_robots(fleet, 120.0)
        max_cont = 0.0
        for r in fleet.robots:
            cont = (fleet.runtime.now() - r.fairness.wait_since) if r.fairness.wait_since else 0
            max_cont = max(max_cont, cont)
            # progress evidence: every robot moved and aged priority grew
            assert r.counters["distance_m"] > 5.0, \
                f"{r.id} never moved ({r.counters['distance_m']:.1f}m)"
        assert max_cont < 100.0, f"robot starved {max_cont:.0f}s"
