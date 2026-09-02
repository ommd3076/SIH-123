"""Seeded scenario generation (build prompt §16, §18).

Tasks are generated deterministically from (scenario, seed): every run with
the same seed produces the same task stream, so experiment modes A-D are
apples-to-apples. A warehouse operations schedule provides demand context
(09:00 inbound spike, 11:00 outbound surge, 14:00 normal load) that acts as
a prior for congestion forecasting — it never dictates routes.
"""
from __future__ import annotations

import json
import os
import random
from typing import Any, Dict, List, Optional, Tuple

from ..fleet_core.config import project_path

TASK_KINDS = ("PICK_DROP", "REPOSITION", "URGENT")


class Scenario:
    def __init__(self, name: str, duration_s: float, schedule: List[Dict],
                 seed: int = 0):
        self.name = name
        self.duration_s = duration_s
        self.schedule = schedule      # [{t, zone, rate, dur, kind}]
        self.seed = seed

    @staticmethod
    def from_json(data: Dict, seed: int) -> "Scenario":
        return Scenario(data["name"], data["duration_s"], data["schedule"], seed)

    @staticmethod
    def load(path: str, seed: int) -> "Scenario":
        with open(path) as f:
            return Scenario.from_json(json.load(f), seed)

    # ------------------------------------------------------------------
    def generate_tasks(self, wmap) -> List[Dict]:
        """Deterministic task stream from the schedule + seed."""
        rng = random.Random(self.seed)
        tasks: List[Dict] = []
        bays = wmap.bays()
        pickups = wmap.pickups()
        drops = wmap.drops()
        staging = wmap.staging_nodes()
        n = 0
        for ev in self.schedule:
            t0 = ev["t"]
            rate = ev.get("rate", 0.2)
            dur = ev.get("dur", 30.0)
            kind = ev.get("kind", "PICK_DROP")
            zone = ev.get("zone", "A")
            n_events = int(rate * dur)
            for _ in range(n_events):
                n += 1
                t = t0 + rng.random() * dur
                if kind == "PICK_DROP":
                    if zone == "A":        # inbound: dock -> storage
                        pickup = rng.choice(pickups)
                        drop = rng.choice(bays)
                    elif zone == "B":      # outbound: storage -> drop
                        pickup = rng.choice(bays)
                        drop = rng.choice(drops)
                    else:                  # cross-dock
                        pickup = rng.choice(pickups)
                        drop = rng.choice(drops)
                elif kind == "URGENT":
                    pickup = rng.choice(pickups)
                    drop = rng.choice(drops)
                else:                      # REPOSITION
                    pickup = rng.choice(bays + pickups + drops)
                    drop = rng.choice(staging + bays)
                task = {
                    "task_id": f"T{n:04d}",
                    "kind": "URGENT" if kind == "URGENT" else kind,
                    "pickup": pickup, "drop": drop,
                    "created": round(t, 3),
                    "urgency": 2.5 if kind == "URGENT" else 0.0,
                    "deadline": round(t + 90.0, 3) if kind == "URGENT" else None,
                }
                tasks.append(task)
        tasks.sort(key=lambda x: x["created"])
        return tasks

    def demand_factor_at(self, t: float) -> float:
        """Scheduled demand multiplier at time t (context prior)."""
        level = 1.0
        for ev in self.schedule:
            if ev["t"] <= t < ev["t"] + ev.get("dur", 30.0):
                level = max(level, 1.0 + 0.6 * ev.get("rate", 0.2))
        return level


# ---------------------------------------------------------------------------
DEFAULT_SCENARIO = {
    "name": "baseline",
    "duration_s": 180.0,
    "schedule": [
        {"t": 0.0, "zone": "A", "rate": 0.22, "dur": 40.0, "kind": "PICK_DROP"},
        {"t": 55.0, "zone": "B", "rate": 0.22, "dur": 40.0, "kind": "PICK_DROP"},
        {"t": 100.0, "zone": "C", "rate": 0.10, "dur": 60.0, "kind": "PICK_DROP"},
        {"t": 120.0, "zone": "B", "rate": 0.06, "dur": 40.0, "kind": "URGENT"},
        {"t": 20.0, "zone": "C", "rate": 0.05, "dur": 50.0, "kind": "REPOSITION"},
    ],
}


def ensure_default_scenario_file() -> str:
    path = project_path("scenarios", "baseline.json")
    if not os.path.exists(path):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as f:
            json.dump(DEFAULT_SCENARIO, f, indent=2)
    return path


def surge_scenario() -> Dict:
    """Outbound surge in zone B (demand-surge demo scenario)."""
    return {
        "name": "surge",
        "duration_s": 180.0,
        "schedule": [
            {"t": 0.0, "zone": "B", "rate": 0.5, "dur": 50.0, "kind": "PICK_DROP"},
            {"t": 55.0, "zone": "B", "rate": 0.35, "dur": 60.0, "kind": "PICK_DROP"},
            {"t": 120.0, "zone": "A", "rate": 0.12, "dur": 50.0, "kind": "PICK_DROP"},
        ],
    }


def ensure_scenario_files() -> List[str]:
    paths = [ensure_default_scenario_file()]
    surge_path = project_path("scenarios", "surge.json")
    if not os.path.exists(surge_path):
        with open(surge_path, "w") as f:
            json.dump(surge_scenario(), f, indent=2)
    paths.append(surge_path)
    return paths
