"""Robot edge agent process entry (live mode).

    python -m robotics_ws.robot_agent --rid R01 [--mode FULL_DISTRIBUTED_PREDICTIVE]
"""
import argparse
import asyncio
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from robotics_ws.fleet_core.config import load_fleet_config, load_map   # noqa: E402
from robotics_ws.fleet_transport.base import (ImpairProfile,           # noqa: E402
                                              MessagePlane)
from robotics_ws.fleet_transport.runtime import AsyncioRuntime          # noqa: E402
from robotics_ws.fleet_transport.zenoh_backend import make_backend     # noqa: E402
from robotics_ws.robot_agent.agent import RobotAgent                   # noqa: E402


def build_spawn_index(wmap) -> dict[str, str]:
    """Support both legacy {rid,node} and coordinate-only spawn entries."""
    index: dict[str, str] = {}
    spawns = list(wmap.spawn or [])
    for i, sp in enumerate(spawns):
        rid = sp.get("rid") or f"R{i + 1:02d}"
        node = sp.get("node")
        if node in wmap.nodes:
            index[rid] = node
            continue
        if "x" in sp and "y" in sp:
            x, y = float(sp["x"]), float(sp["y"])
            nearest = min(
                wmap.nodes.values(),
                key=lambda n: (n.x - x) ** 2 + (n.y - y) ** 2,
            )
            index[rid] = nearest.id
    return index


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--rid", required=True)
    ap.add_argument("--mode", default="FULL_DISTRIBUTED_PREDICTIVE")
    ap.add_argument("--map", default=None)
    ap.add_argument("--config", default=None)
    ap.add_argument("--seed", type=int, default=0)
    args = ap.parse_args()

    cfg = load_fleet_config(args.config)
    wmap = load_map(args.map)
    spawn = build_spawn_index(wmap)

    async def run():
        runtime = AsyncioRuntime(t0=0.0, scale=float(os.environ.get("SIM_SCALE", "1.0")))
        import random
        rng = random.Random(args.seed)
        backend = make_backend(cfg["transport"]["backend"])
        plane = MessagePlane(backend, args.rid,
                             range_m=cfg["fleet"]["radio_range_robot"],
                             profile=ImpairProfile(**cfg.get("impairment", {})),
                             rng=rng, scheduler=runtime.call_later)
        battery = rng.uniform(*cfg.get("battery", {}).get("start_pct", [72, 96]))
        agent = RobotAgent(args.rid, runtime, plane, wmap=wmap, cfg=cfg,
                           seed=args.seed, mode=args.mode,
                           start_node=spawn.get(args.rid, "O1"), battery=battery)
        agent.start()
        print(f"[robot {args.rid}] started (mode={args.mode})", flush=True)
        await asyncio.Event().wait()

    asyncio.run(run())


if __name__ == "__main__":
    main()
