"""Junction Edge Cell process entry (live mode)."""
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
from robotics_ws.junction_edge_cell.jec import JunctionEdgeCellAgent   # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--jec", required=True)
    ap.add_argument("--map", default=None)
    ap.add_argument("--config", default=None)
    ap.add_argument("--seed", type=int, default=0)
    args = ap.parse_args()

    cfg = load_fleet_config(args.config)
    wmap = load_map(args.map)

    async def run():
        runtime = AsyncioRuntime(t0=0.0, scale=float(os.environ.get("SIM_SCALE", "1.0")))
        import random
        rng = random.Random(args.seed)
        backend = make_backend(cfg["transport"]["backend"])
        plane = MessagePlane(backend, args.jec,
                             range_m=cfg["fleet"]["radio_range_jec"],
                             profile=ImpairProfile(**cfg.get("impairment", {})),
                             rng=rng, scheduler=runtime.call_later)
        agent = JunctionEdgeCellAgent(args.jec, runtime, plane, wmap=wmap,
                                      cfg=cfg, seed=args.seed)
        agent.start()
        print(f"[{args.jec}] started at junction {agent.junction}", flush=True)
        await asyncio.Event().wait()

    asyncio.run(run())


if __name__ == "__main__":
    main()
