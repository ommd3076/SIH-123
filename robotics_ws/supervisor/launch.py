"""Live fleet supervisor: spawns robot / JEC / allocator OS processes on the
Zenoh coordination plane, monitors them, and handles infrastructure chaos
commands (KILL_JEC / RESTART_JEC really terminate / respawn processes).

    python -m robotics_ws.supervisor [--scenario baseline] [--seed 7]
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import signal
import subprocess
import sys
import time
from typing import Any, Dict, List, Optional

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from robotics_ws.fleet_core.config import (load_fleet_config, load_map,   # noqa: E402
                                           project_path)
from robotics_ws.fleet_transport.base import (ImpairProfile, MessagePlane)  # noqa: E402
from robotics_ws.fleet_transport.runtime import AsyncioRuntime          # noqa: E402
from robotics_ws.fleet_transport.zenoh_backend import make_backend     # noqa: E402
from robotics_ws.robot_agent.base_agent import BaseAgent               # noqa: E402

PY = sys.executable
ROOT = project_path()


class SupervisorAgent(BaseAgent):
    """Infrastructure monitor: subscribes control commands; samples child
    process CPU/memory from /proc; publishes supervisor telemetry."""

    kind = "supervisor"

    def __init__(self, runtime, plane, wmap, cfg, children: Dict[str, subprocess.Popen]):
        super().__init__("SUP", runtime, plane, wmap, cfg, seed=0)
        self.range_m = float("inf")
        self.plane.range_m = float("inf")
        self.plane.infra = True
        self.tick_period = 1.0
        self.children = children
        self._cpu_prev: Dict[str, tuple] = {}

    def _wire(self) -> None:
        pass

    def on_control(self, key: str, payload: Dict) -> None:
        super().on_control(key, payload)
        cmd = payload.get("cmd")
        if cmd == "KILL_JEC":
            jid = payload.get("jec")
            proc = self.children.get(jid)
            if proc and proc.poll() is None:
                proc.terminate()
                self.emit("jec_killed", {"jec": jid})
        elif cmd == "RESTART_JEC":
            self.respawn_jec(payload.get("jec"))

    def respawn_jec(self, jid: Optional[str]) -> None:
        if not jid:
            return
        proc = self.children.get(jid)
        if proc and proc.poll() is None:
            return
        cfg = self.cfg
        p = subprocess.Popen(
            [PY, "-m", "robotics_ws.junction_edge_cell", "--jec", jid,
             "--map", project_path("configs", "warehouse_map.json"),
             "--seed", "0"],
            cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.children[jid] = p
        self.emit("jec_restarted", {"jec": jid, "pid": p.pid})

    # ------------------------------------------------------------------
    def _proc_stats(self, pid: int) -> Dict:
        try:
            with open(f"/proc/{pid}/stat") as f:
                parts = f.read().split()
            utime, stime = int(parts[13]), int(parts[14])
            with open(f"/proc/{pid}/statm") as f:
                rss_pages = int(f.read().split()[1])
            return {"ticks": utime + stime, "rss_mb": round(rss_pages * 4096 / 1e6, 1)}
        except (OSError, IndexError, ValueError):
            return {"ticks": 0, "rss_mb": 0.0}

    def tick(self) -> None:
        procs = []
        hz = os.sysconf("SC_CLK_TCK")
        for name, p in self.children.items():
            alive = p.poll() is None
            st = self._proc_stats(p.pid) if alive else {"ticks": 0, "rss_mb": 0.0}
            prev = self._cpu_prev.get(name)
            cpu_pct = 0.0
            if prev and st["ticks"] > prev[0]:
                cpu_pct = round(100.0 * (st["ticks"] - prev[0]) / hz, 1)
            self._cpu_prev[name] = (st["ticks"],)
            procs.append({"name": name, "alive": alive, "pid": p.pid,
                          "cpu_pct": cpu_pct, "rss_mb": st["rss_mb"]})
        self.emit("supervisor_stats", {"processes": procs})


async def main_async(args):
    cfg = load_fleet_config(args.config)
    wmap = load_map(args.map)
    from robotics_ws.task_allocator.scenario import Scenario, ensure_scenario_files
    ensure_scenario_files()
    scen_data = json.load(open(args.scenario or project_path("scenarios", "baseline.json")))

    children: Dict[str, subprocess.Popen] = {}
    common = ["--map", args.map or project_path("configs", "warehouse_map.json")]

    def spawn():
        # robots
        for i in range(cfg["fleet"]["robot_count"]):
            rid = f"R{i + 1:02d}"
            children[rid] = subprocess.Popen(
                [PY, "-m", "robotics_ws.robot_agent", "--rid", rid,
                 "--mode", args.mode, *common, "--seed", str(args.seed)],
                cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        # JECs
        for jid in wmap.jecs:
            children[jid] = subprocess.Popen(
                [PY, "-m", "robotics_ws.junction_edge_cell", "--jec", jid,
                 *common, "--seed", "0"],
                cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        # allocator
        children["ALLOC"] = subprocess.Popen(
            [PY, "-m", "robotics_ws.task_allocator", "--scenario",
             args.scenario or project_path("scenarios", "baseline.json"),
             *common, "--seed", str(args.seed)],
            cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    spawn()
    print(f"[supervisor] spawned {len(children)} processes "
          f"(10 robots, {len(wmap.jecs)} JECs, allocator)", flush=True)

    # supervisor agent (owns process monitoring + chaos commands)
    runtime = AsyncioRuntime(t0=0.0, scale=1.0)
    import random
    backend = make_backend(cfg["transport"]["backend"])
    plane = MessagePlane(backend, "SUP", range_m=float("inf"), infra=True,
                         profile=ImpairProfile(latency_ms=0.0, jitter_ms=0.0, loss_pct=0.0),
                         rng=random.Random(1), scheduler=runtime.call_later)
    sup = SupervisorAgent(runtime, plane, wmap, cfg, children)
    sup.start()
    print("[supervisor] monitoring (subscribes fleet/control/cmd)", flush=True)

    try:
        await asyncio.Event().wait()
    except (KeyboardInterrupt, asyncio.CancelledError):
        pass
    finally:
        print("[supervisor] shutting down fleet ...", flush=True)
        for name, p in children.items():
            if p.poll() is None:
                p.terminate()
        time.sleep(0.8)
        for name, p in children.items():
            if p.poll() is None:
                p.kill()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--scenario", default=None)
    ap.add_argument("--map", default=None)
    ap.add_argument("--config", default=None)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--mode", default="FULL_DISTRIBUTED_PREDICTIVE")
    args = ap.parse_args()
    try:
        asyncio.run(main_async(args))
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
