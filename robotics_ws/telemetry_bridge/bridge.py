"""Telemetry bridge: Zenoh mesh -> WebSocket (socket.io) + REST.

Observability only: the bridge is a full-range SNIFFER on the coordination
plane plus a control-command injector (operator console). Robots, JECs and
the allocator never depend on it — killing the bridge does not affect the
fleet.

REST:
  GET  /api/map                 render-ready warehouse map
  GET  /api/snapshot            current fleet state
  GET  /api/metrics             live aggregate metrics
  GET  /api/predictor           congestion predictor evaluation report
  POST /api/control             chaos control commands
  GET  /api/experiments         list experiment runs
  POST /api/experiments         launch an experiment (subprocess)
  GET  /api/experiments/{id}    experiment status
  GET  /api/results/latest      latest results bundle

Socket.io events (5 Hz snapshot / 1 Hz metrics / on-event telemetry):
  snapshot, metrics, event
"""
from __future__ import annotations

import asyncio
import json
import math
import os
import signal
import subprocess
import sys
import time
import uuid
from collections import deque
from typing import Any, Dict, List, Optional

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

import socketio                                                   # noqa: E402
from aiohttp import web                                           # noqa: E402

from robotics_ws.fleet_core.config import (load_fleet_config, load_map,   # noqa: E402
                                           project_path)
from robotics_ws.fleet_transport.base import (ImpairProfile, key_matches,
                                              MessagePlane)
from robotics_ws.fleet_transport.runtime import AsyncioRuntime       # noqa: E402
from robotics_ws.fleet_transport.zenoh_backend import make_backend  # noqa: E402
from robotics_ws.robot_agent.base_agent import BaseAgent             # noqa: E402

PY = sys.executable
ROOT = project_path()
PORT = int(os.environ.get("BRIDGE_PORT", "8010"))

HEARTBEAT_TTL = 3.0
JEC_TTL = 3.0


class BridgeAgent(BaseAgent):
    """Full-range observer + operator console on the mesh."""

    kind = "bridge"

    def __init__(self, runtime, plane, wmap, cfg):
        super().__init__("BRIDGE", runtime, plane, wmap, cfg, seed=0)
        self.range_m = float("inf")
        self.plane.range_m = float("inf")
        self.plane.infra = True
        self.tick_period = 0.2

        self.robots: Dict[str, Dict] = {}
        self.intents: Dict[str, Dict] = {}
        self.jecs: Dict[str, Dict] = {}
        self.alloc: Dict = {}
        self.conflicts: Dict[str, Dict] = {}
        self.gate_claims: Dict[str, List[Dict]] = {}
        self.events: deque = deque(maxlen=600)
        self.decisions: deque = deque(maxlen=200)
        self.vetoes: deque = deque(maxlen=200)
        self.context_events: deque = deque(maxlen=200)
        self.task_feed: deque = deque(maxlen=300)
        self.supervisor: Dict = {}
        self.metrics_history: deque = deque(maxlen=240)
        self.wait_samples: List[float] = []
        self._sio = None

    def _wire(self) -> None:
        self.plane.subscribe("fleet/robot/*/heartbeat", self._on_hb)
        self.plane.subscribe("fleet/robot/*/intent", self._on_intent)
        self.plane.subscribe("fleet/jec/*/state", self._on_jec)
        self.plane.subscribe("fleet/jec/*/resv/*", self._on_resv)
        self.plane.subscribe("fleet/allocator/taskstate", self._on_task)
        self.plane.subscribe("fleet/conflict/*", self._on_conflict)
        self.plane.subscribe("fleet/gate/*/claim", self._on_claim)
        self.plane.subscribe("fleet/telemetry/*", self._on_telemetry)
        self.plane.subscribe("fleet/events/context", self._on_context)

    def attach_socketio(self, sio) -> None:
        self._sio = sio

    # ------------------------------------------------------------------
    def _on_hb(self, key: str, m: Dict) -> None:
        rid = m.get("robot")
        if rid:
            self.robots[rid] = dict(m, t_recv=self.t)

    def _on_intent(self, key: str, m: Dict) -> None:
        rid = m.get("robot")
        if rid:
            self.intents[rid] = dict(m, t_recv=self.t)

    def _on_jec(self, key: str, m: Dict) -> None:
        jid = m.get("jec")
        if jid:
            self.jecs[jid] = dict(m, t_recv=self.t)

    def _on_resv(self, key: str, m: Dict) -> None:
        self.events.append({"kind": "reservation", "t": round(self.t, 2), **{
            k: m.get(k) for k in ("jec", "robot", "decision", "reason",
                                  "resource", "queue_pos")}})

    def _on_task(self, key: str, m: Dict) -> None:
        self.task_feed.append({"t": round(self.t, 2),
                               "task_id": m.get("task_id"),
                               "state": m.get("state"),
                               "robot": m.get("robot")})

    def _on_conflict(self, key: str, m: Dict) -> None:
        cell = m.get("cell", "")
        if not cell:
            return
        if m.get("expired"):
            self.conflicts.pop(cell, None)
        else:
            self.conflicts[cell] = dict(m, t_recv=self.t)

    def _on_claim(self, key: str, m: Dict) -> None:
        gate = m.get("gate", "")
        self.gate_claims.setdefault(gate, []).append(dict(m, t_recv=self.t))

    def _on_context(self, key: str, m: Dict) -> None:
        self.context_events.append({"t": round(self.t, 2),
                                    "type": m.get("type"),
                                    "value": m.get("value"),
                                    "reporter": m.get("reporter"),
                                    "ttl": m.get("ttl")})

    def _on_telemetry(self, key: str, m: Dict) -> None:
        t = m.get("type", "")
        if t == "decision":
            self.decisions.append(dict(m, t_recv=self.t))
            self.events.append({"kind": "decision", "t": round(self.t, 2),
                                "robot": m.get("agent")})
        elif t == "safety_veto":
            self.vetoes.append(dict(m, t_recv=self.t))
            self.events.append({"kind": "safety_veto", "t": round(self.t, 2),
                                "robot": m.get("agent"), "rule": m.get("rule")})
        elif t == "allocator_stats":
            self.alloc = dict(m)
        elif t == "supervisor_stats":
            self.supervisor = dict(m)
        elif t == "wait_episode":
            self.wait_samples.append(m.get("duration", 0.0))
            self.wait_samples = self.wait_samples[-4000:]
        elif t in ("collision", "collision_risk"):
            self.events.append({"kind": t, "t": round(self.t, 2),
                                "robot": m.get("agent"), "peer": m.get("peer"),
                                "gap": m.get("gap")})
        elif t in ("task_done", "task_phase", "task_accepted", "docked",
                   "charging", "gate_released", "deadlock_backout", "reversal",
                   "reservation_expired", "reservation_decision", "failed",
                   "recovered", "charge_done", "task_burst", "jec_killed",
                   "jec_restarted", "task_aborted"):
            self.events.append({"kind": t, "t": round(self.t, 2),
                                "robot": m.get("agent"), **{
                                    k: v for k, v in m.items()
                                    if k not in ("agent", "kind", "t", "type")}})

    # ------------------------------------------------------------------
    def tick(self) -> None:
        self._prune()
        if self._sio:
            try:
                snap = self.snapshot()
                asyncio.run_coroutine_threadsafe(
                    self._sio.emit("snapshot", snap), self._loop)
                if int(self.t * 5) % 5 == 0:
                    asyncio.run_coroutine_threadsafe(
                        self._sio.emit("metrics", self.metrics()), self._loop)
                evs = [e for e in list(self.events)[-8:]]
                if evs:
                    asyncio.run_coroutine_threadsafe(
                        self._sio.emit("event", evs), self._loop)
                self.events.clear()
            except Exception:  # noqa: BLE001
                pass

    def set_loop(self, loop) -> None:
        self._loop = loop

    _loop = None

    def _prune(self) -> None:
        for rid in [r for r, m in self.robots.items()
                    if self.t - m.get("t_recv", 0) > HEARTBEAT_TTL]:
            self.robots.pop(rid, None)
            self.intents.pop(rid, None)
        for jid in [j for j, m in self.jecs.items()
                    if self.t - m.get("t_recv", 0) > JEC_TTL]:
            m = self.jecs.pop(jid, None)
            if m:
                self.jecs[jid] = {**m, "alive": False}
        for g in list(self.gate_claims):
            self.gate_claims[g] = [c for c in self.gate_claims[g]
                                   if self.t - c.get("t_recv", 0) < 1.5]
            if not self.gate_claims[g]:
                del self.gate_claims[g]

    # ------------------------------------------------------------------
    def snapshot(self) -> Dict:
        return {
            "t": round(self.t, 2),
            "robots": [self._robot_view(r) for r in self.robots.values()],
            "jecs": [self._jec_view(j) for j in self.jecs.values()],
            "allocator": self.alloc,
            "conflicts": list(self.conflicts.values()),
            "gate_claims": {g: c[-3:] for g, c in self.gate_claims.items()},
            "decisions": list(self.decisions)[-12:],
            "task_feed": list(self.task_feed)[-25:],
            "context_events": list(self.context_events)[-20:],
            "supervisor": self.supervisor,
        }

    def _robot_view(self, m: Dict) -> Dict:
        rid = m.get("robot")
        intent = self.intents.get(rid, {})
        return {
            "robot": rid, "t": m.get("t"), "pos": m.get("pos"),
            "edge": m.get("edge"), "s": m.get("s"), "dir": m.get("dir"),
            "node": m.get("node"), "speed": m.get("speed"),
            "battery": m.get("battery"), "state": m.get("state"),
            "task_id": m.get("task_id"), "route_head": m.get("route_head"),
            "waiting": m.get("waiting"), "wait_s": m.get("wait_s"),
            "effective_priority": m.get("effective_priority"),
            "yields": m.get("yields"), "denials": m.get("denials"),
            "counters": m.get("counters"), "stats": m.get("stats"),
            "intent": {
                "route": intent.get("route", []),
                "targets": intent.get("targets", []),
                "urgency": intent.get("urgency", 0.0),
                "confidence": intent.get("confidence", 1.0),
            } if intent else None,
        }

    def _jec_view(self, m: Dict) -> Dict:
        return {
            "jec": m.get("jec"), "junction": m.get("junction"),
            "gate": m.get("gate"), "alive": m.get("alive", True),
            "blocked": m.get("blocked", False),
            "occupancy": m.get("occupancy", 0.0),
            "predicted": m.get("predicted", {}),
            "congestion": m.get("congestion", 0.0),
            "queue": m.get("queue", []),
            "reservations": m.get("reservations", []),
            "gate_state": m.get("gate_state", {}),
            "conflicts": m.get("conflicts", []),
            "approaching": m.get("approaching", []),
            "counters": m.get("counters"),
            "predictor": m.get("predictor", "heuristic"),
            "utilization": m.get("utilization", 0.0),
            "stats": m.get("stats"),
        }

    def metrics(self) -> Dict:
        waits = sorted(w for w in self.wait_samples if w > 0)[-4000:]
        msgs_s = 0.0
        bytes_s = 0.0
        dist = 0.0
        energy = 0.0
        vetoes = 0
        replans = 0
        collisions = 0
        tasks_done = 0
        for rb in self.robots.values():
            st = rb.get("stats", {})
            msgs_s += st.get("sent", 0)
            bytes_s += st.get("sent_bytes", 0)
            c = rb.get("counters", {})
            dist += c.get("distance_m", 0.0)
            energy += c.get("energy_j", 0.0)
            vetoes += c.get("veto_episodes", 0)
            replans += c.get("replans", 0)
            collisions += c.get("collisions", 0)
            tasks_done += c.get("tasks_done", 0)
        for jb in self.jecs.values():
            st = jb.get("stats", {})
            msgs_s += st.get("sent", 0)
            bytes_s += st.get("sent_bytes", 0)
        m = {
            "t": round(self.t, 1),
            "robots_online": len([r for r in self.robots.values()]),
            "jecs_online": len([j for j in self.jecs.values() if j.get("alive", True)]),
            "tasks_done": tasks_done,
            "tasks_pending": self.alloc.get("pending", 0),
            "tasks_active": self.alloc.get("active", 0),
            "mean_wait_s": round(sum(waits) / len(waits), 2) if waits else 0.0,
            "p95_wait_s": round(waits[int(0.95 * len(waits))], 2) if waits else 0.0,
            "distance_m": round(dist, 1),
            "energy_j": round(energy, 1),
            "vetoes": vetoes, "replans": replans, "collisions": collisions,
            "messages_per_s": round(msgs_s / max(1.0, self.t), 1),
            "bytes_per_s": round(bytes_s / max(1.0, self.t), 1),
            "conflicts_active": len(self.conflicts),
        }
        self.metrics_history.append(m)
        return m


# ---------------------------------------------------------------------------
# experiment subprocess management
EXPERIMENTS: Dict[str, Dict] = {}


def launch_experiment(spec: Dict) -> Dict:
    exp_id = str(uuid.uuid4())[:8]
    modes = spec.get("modes", ["FULL_DISTRIBUTED_PREDICTIVE"])
    seeds = spec.get("seeds", [7, 42])
    duration = spec.get("duration", 200.0)
    scenario = spec.get("scenario", "baseline")
    cmd = [PY, "-m", "robotics_ws.experiment_runner.runner",
           "--modes", ",".join(modes),
           "--seeds", ",".join(str(s) for s in seeds),
           "--duration", str(duration)]
    proc = subprocess.Popen(cmd, cwd=ROOT, stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL)
    EXPERIMENTS[exp_id] = {"id": exp_id, "pid": proc.pid, "proc": proc,
                           "spec": spec, "started": time.time()}
    return {"id": exp_id, "status": "running", "spec": spec}


def experiment_status(exp_id: str) -> Optional[Dict]:
    e = EXPERIMENTS.get(exp_id)
    if not e:
        return None
    running = e["proc"].poll() is None
    return {"id": exp_id, "status": "running" if running else "done",
            "elapsed_s": round(time.time() - e["started"], 1),
            "spec": e["spec"]}


def build_app(agent: BridgeAgent, wmap, cfg) -> web.Application:
    sio = socketio.AsyncServer(async_mode="aiohttp", cors_allowed_origins="*",
                               ping_timeout=60, ping_interval=25)
    agent.attach_socketio(sio)

    app = web.Application()

    async def get_map(request):
        return web.json_response(wmap.to_frontend())

    async def get_snapshot(request):
        return web.json_response(agent.snapshot())

    async def get_metrics(request):
        return web.json_response(agent.metrics())

    async def get_predictor(request):
        path = project_path("results", "predictor_eval.json")
        if os.path.exists(path):
            return web.json_response(json.load(open(path)))
        return web.json_response({"note": "predictor not evaluated yet"})

    async def post_control(request):
        body = await request.json()
        cmd = body.get("cmd", "")
        if not cmd:
            return web.json_response({"error": "cmd required"}, status=400)
        agent.plane.publish("fleet/control/cmd", {
            "cmd": cmd, **{k: v for k, v in body.items() if k != "cmd"},
            "t": round(agent.t, 3), "src": "BRIDGE",
        })
        agent.events.append({"kind": "control", "t": round(agent.t, 2),
                             "cmd": cmd})
        return web.json_response({"ok": True, "cmd": cmd})

    async def get_experiments(request):
        return web.json_response([
            experiment_status(e) for e in EXPERIMENTS])

    async def post_experiments(request):
        body = await request.json()
        return web.json_response(launch_experiment(body))

    async def get_experiment(request):
        st = experiment_status(request.match_info["exp_id"])
        if st is None:
            return web.json_response({"error": "unknown experiment"}, status=404)
        return web.json_response(st)

    async def get_results_latest(request):
        path = project_path("results", "latest.json")
        if os.path.exists(path):
            return web.json_response(json.load(open(path)))
        return web.json_response({"error": "no results yet"}, status=404)

    async def get_health(request):
        return web.json_response({"ok": True, "t": round(agent.t, 2),
                                  "robots": len(agent.robots),
                                  "jecs": len(agent.jecs)})

    app.router.add_get("/api/map", get_map)
    app.router.add_get("/api/snapshot", get_snapshot)
    app.router.add_get("/api/metrics", get_metrics)
    app.router.add_get("/api/predictor", get_predictor)
    app.router.add_post("/api/control", post_control)
    app.router.add_get("/api/experiments", get_experiments)
    app.router.add_post("/api/experiments", post_experiments)
    app.router.add_get("/api/experiments/{exp_id}", get_experiment)
    app.router.add_get("/api/results/latest", get_results_latest)
    app.router.add_get("/api/health", get_health)
    sio.attach(app)
    return app


async def main_async():
    cfg = load_fleet_config()
    wmap = load_map()
    runtime = AsyncioRuntime(t0=0.0, scale=1.0)
    import random
    backend = make_backend(cfg["transport"]["backend"])
    plane = MessagePlane(backend, "BRIDGE", range_m=float("inf"), infra=True,
                         profile=ImpairProfile(latency_ms=0.0, jitter_ms=0.0,
                                               loss_pct=0.0),
                         rng=random.Random(7), scheduler=runtime.call_later)
    agent = BridgeAgent(runtime, plane, wmap, cfg)
    agent.set_loop(asyncio.get_event_loop())
    agent.start()
    app = build_app(agent, wmap, cfg)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", PORT)
    await site.start()
    print(f"[bridge] listening on :{PORT} (socket.io + REST)", flush=True)
    await asyncio.Event().wait()


def main():
    try:
        asyncio.run(main_async())
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
