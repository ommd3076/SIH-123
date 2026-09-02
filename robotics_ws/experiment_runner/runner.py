"""Experiment runner (build prompt §20, §21, §33).

Runs coordination modes A-D on identical seeded scenarios and persists REAL
measurements to results/ (CSV + JSON). Also runs the chaos experiment set
(JEC kill, robot failure, network impairment).

    python -m robotics_ws.experiment_runner.runner                 # full suite
    python -m robotics_ws.experiment_runner.runner --modes D --seeds 7 --duration 120
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import time
from typing import Any, Dict, List

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from robotics_ws.fleet_core.types import ALL_MODES                    # noqa: E402
from robotics_ws.fleet_core.config import project_path               # noqa: E402
from robotics_ws.fleet_transport.base import ImpairProfile           # noqa: E402
from robotics_ws.sim_runner.des_fleet import DesFleet                # noqa: E402
from robotics_ws.task_allocator.scenario import (Scenario,           # noqa: E402
                                                 ensure_scenario_files,
                                                 surge_scenario)

MODE_LABELS = {
    "STOP_AND_WAIT": "A: stop-and-wait",
    "SHORTEST_PATH_REACTIVE": "B: shortest-path reactive",
    "INTENT_P2P": "C: intent P2P",
    "FULL_DISTRIBUTED_PREDICTIVE": "D: full distributed predictive",
}


def run_one(mode: str, seed: int, scenario: Dict, duration: float,
            chaos: List[Dict] = None, impairment: ImpairProfile = None,
            tag: str = None) -> Dict:
    sc = Scenario.from_json(scenario, seed=seed)
    fleet = DesFleet(mode, sc, seed=seed, duration=duration,
                     impairment=impairment)
    if chaos:
        fleet.chaos_script = chaos
    t0 = time.perf_counter()
    summary = fleet.run()
    summary["mode"] = mode
    summary["mode_label"] = MODE_LABELS[mode]
    summary["seed"] = seed
    summary["scenario"] = sc.name
    summary["wall_s"] = round(time.perf_counter() - t0, 2)
    if tag:
        summary["tag"] = tag
    # fairness extras
    summary["robot_progress_m"] = {
        r.id: round(r.counters["distance_m"], 1) for r in fleet.robots}
    summary["yields_total"] = sum(r.counters["yields"] for r in fleet.robots)
    return summary


def write_results(results: List[Dict], out_dir: str) -> str:
    os.makedirs(out_dir, exist_ok=True)
    ts = time.strftime("%Y%m%d-%H%M%S")
    run_dir = os.path.join(out_dir, f"run-{ts}")
    os.makedirs(run_dir, exist_ok=True)
    # per-run JSON
    for i, r in enumerate(results):
        name = f"{r['mode']}_s{r['seed']}" + (f"_{r.get('tag')}" if r.get("tag") else "")
        with open(os.path.join(run_dir, f"{name}.json"), "w") as f:
            json.dump(r, f, indent=2)
    # aggregate CSV + summary
    fields = ["mode", "mode_label", "seed", "scenario", "tag", "tasks_done",
              "tasks_per_hour", "tasks_failed", "tasks_reassigned", "mean_wait_s",
              "p95_wait_s", "max_wait_s", "total_distance_m", "energy_j",
              "vetoes", "replans", "collisions", "near_misses", "deadlocks",
              "stalled_robots", "mean_queue_len", "reservation_grants",
              "reservation_denials", "jec_utilization", "messages_per_s",
              "bytes_per_s", "conflict_cells_formed", "wall_s"]
    csv_path = os.path.join(run_dir, "summary.csv")
    with open(csv_path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        w.writerows(results)
    # aggregate per mode
    agg: Dict[str, Dict] = {}
    for r in results:
        key = r["mode"]
        agg.setdefault(key, {"runs": 0})
        agg[key]["runs"] += 1
        for k, v in r.items():
            if isinstance(v, (int, float)) and k not in ("seed", "wall_s"):
                agg[key].setdefault(k, [])
                agg[key][k].append(v)
    agg_out = {
        mode: {k: (round(sum(v) / len(v), 3) if isinstance(v, list) else v)
               for k, v in d.items()}
        for mode, d in agg.items()}
    with open(os.path.join(run_dir, "aggregate.json"), "w") as f:
        json.dump(agg_out, f, indent=2)
    with open(os.path.join(out_dir, "latest.json"), "w") as f:
        json.dump({"run_dir": run_dir, "aggregate": agg_out,
                   "runs": [r for r in results]}, f, indent=2)
    print(f"results written: {run_dir}")
    return run_dir


def full_suite(seeds=(7, 42, 99), duration: float = 200.0,
               modes: List[str] = None, out_root: str = None) -> List[Dict]:
    ensure_scenario_files()
    out_root = out_root or project_path("results")
    baseline = json.load(open(project_path("scenarios", "baseline.json")))
    surge = surge_scenario()
    results: List[Dict] = []
    modes = modes or ALL_MODES
    for scen in (baseline, surge):
        for mode in modes:
            for seed in seeds:
                print(f"running {MODE_LABELS[mode]} seed={seed} scen={scen['name']} ...")
                r = run_one(mode, seed, scen, duration, tag=scen["name"])
                results.append(r)
                print(f"   tasks={r['tasks_done']} p95_wait={r['p95_wait_s']}s "
                      f"collisions={r['collisions']} vetoes={r['vetoes']}")
    # chaos experiments (mode D)
    chaos_specs = [
        ("jec-kill", [{"t": 40.0, "cmd": "KILL_JEC", "args": {"jec": "JEC-J19"}},
                      {"t": 70.0, "cmd": "RESTART_JEC", "args": {"jec": "JEC-J19"}}]),
        ("robot-fail", [{"t": 40.0, "cmd": "FAIL_ROBOT", "args": {"robot": "R04"}}]),
        ("network-degraded", None),
    ]
    for tag, chaos in chaos_specs:
        for seed in seeds[:2]:
            imp = ImpairProfile(latency_ms=350.0, jitter_ms=150.0, loss_pct=12.0) \
                if tag == "network-degraded" else None
            print(f"running chaos={tag} seed={seed} ...")
            r = run_one("FULL_DISTRIBUTED_PREDICTIVE", seed, baseline, duration,
                        chaos=chaos, impairment=imp, tag=tag)
            results.append(r)
            print(f"   tasks={r['tasks_done']} p95_wait={r['p95_wait_s']}s "
                  f"collisions={r['collisions']}")
    write_results(results, out_root)
    return results


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--modes", default=",".join(ALL_MODES))
    ap.add_argument("--seeds", default="7,42,99")
    ap.add_argument("--duration", type=float, default=200.0)
    ap.add_argument("--out", default=None)
    args = ap.parse_args()
    full_suite(seeds=tuple(int(s) for s in args.seeds.split(",")),
               duration=args.duration,
               modes=[m for m in args.modes.split(",") if m],
               out_root=args.out)
