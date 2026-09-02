"""Dataset generation: run scenarios on the DES runtime and log per-JEC
per-second features + the realised future occupancy (label).

Output: datasets/congestion_features.csv
"""
from __future__ import annotations

import csv
import os
import sys
from typing import Dict, List

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from robotics_ws.fleet_core.config import project_path          # noqa: E402
from robotics_ws.sim_runner.des_fleet import DesFleet           # noqa: E402
from robotics_ws.task_allocator.scenario import (Scenario,       # noqa: E402
                                                  ensure_scenario_files,
                                                  surge_scenario)

HORIZON_S = 5.0


def generate(seed: int, mode: str = "FULL_DISTRIBUTED_PREDICTIVE",
             scenario: Dict = None, duration: float = 180.0) -> List[Dict]:
    sc = Scenario.from_json(scenario or {}, seed=seed)
    fleet = DesFleet(mode, sc, seed=seed, duration=duration)
    fleet.step_to(duration)
    rows = []
    for jec in fleet.jecs:
        # JEC feature_log: [{t, features, predicted}]
        log = list(jec.feature_log)
        # realized occupancy from metrics collector heartbeats timeline:
        # rebuild occupancy at t+HORIZON from robot positions over time —
        # we approximate using the allocator snapshot loop; instead we use
        # the JEC's own later observations (telescoping labels)
        occ_at = {}
        for i, entry in enumerate(log):
            t = entry["t"]
            occ_at[round(t, 1)] = entry["features"]["occ_now"]
        for i, entry in enumerate(log):
            t = entry["t"]
            label_t = round(t + HORIZON_S, 1)
            # search nearest observation within 1s of t+H
            best = None
            for dt in (0.0, 0.5, -0.5, 1.0, -1.0):
                key = round(label_t + dt, 1)
                if key in occ_at:
                    best = occ_at[key]
                    break
            if best is None:
                continue
            row = {"jec": jec.id, "t": t, "label_occ": best, "horizon": HORIZON_S}
            row.update({k: entry["features"].get(k, 0.0) for k in
                        ("occ_now", "occ_prev", "occ_2ago", "approaching",
                         "queue_len", "intent_count", "downstream_occ",
                         "demand_factor", "blockage_active",
                         "recent_blockages", "resv_active")})
            rows.append(row)
    return rows


def run_dataset(seeds=(7, 42, 99, 123, 2024, 31, 55, 88), out_csv: str = None):
    ensure_scenario_files()
    import json as _json
    baseline = _json.load(open(project_path("scenarios", "baseline.json")))
    surge = surge_scenario()
    rows: List[Dict] = []
    for i, seed in enumerate(seeds):
        scen = baseline if i % 2 == 0 else surge
        rows += generate(seed, scenario=scen, duration=200.0)
        print(f"seed {seed} ({scen['name']}): total rows {len(rows)}")
    out_csv = out_csv or project_path("datasets", "congestion_features.csv")
    os.makedirs(os.path.dirname(out_csv), exist_ok=True)
    fields = list(rows[0].keys())
    with open(out_csv, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)
    print(f"dataset written: {out_csv} ({len(rows)} rows)")
    return out_csv


if __name__ == "__main__":
    run_dataset()
