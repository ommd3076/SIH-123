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
    spawn = {s["rid"]: s["node"] for s in wmap.spawn}

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
