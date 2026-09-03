"""BaseAgent: shared scaffolding for every distributed process (robot, JEC, allocator).

Owns: runtime facade, message plane, map, config, RNG, context-event memory
(TTL, bounded), telemetry event publication and the tick loop.
"""
from __future__ import annotations

import random
from collections import deque
from typing import Any, Callable, Dict, List, Optional, Tuple

from ..fleet_core.config import load_fleet_config, load_map
from ..fleet_core.types import ContextEvent
from ..fleet_transport.base import ImpairProfile, MessagePlane
from ..fleet_transport.runtime import RuntimeFacade

MAX_CONTEXT_EVENTS = 64


class BaseAgent:
    kind = "agent"
    range_m = float("inf")

    def __init__(self, agent_id: str, runtime: RuntimeFacade, plane: MessagePlane,
                 wmap=None, cfg: Dict[str, Any] = None, seed: int = 0):
        self.id = agent_id
        self.runtime = runtime
        self.plane = plane
        self.wmap = wmap if wmap is not None else load_map()
        self.cfg = cfg if cfg is not None else load_fleet_config()
        self.rng = random.Random(seed)
        self.t = 0.0
        self.tick_period = 1.0 / self.cfg["fleet"].get("tick_hz", 10)
        self.started = False
        # distributed contextual memory (bounded, TTL)
        self.context: Dict[int, ContextEvent] = {}
        self.context_seq = 0
        self._seq = 0
        self._tick_handle = None
        self._subs: List[Tuple[str, Callable]] = []

    # ------------------------------------------------------------------
    def start(self) -> None:
        if self.started:
            return
        self.started = True
        self.plane.set_pos_provider(self.position)
        self.plane.subscribe("fleet/events/context", self._on_context_event)
        self.plane.subscribe("fleet/control/cmd", self.on_control)
        self._wire()
        self._schedule_tick()

    def _wire(self) -> None:
        """Subclass subscriptions; override."""

    def _schedule_tick(self) -> None:
        self._tick_handle = self.runtime.call_later(self.tick_period, self._tick)

    def _tick(self) -> None:
        self.t = self.runtime.now()
        self.tick()
        self._prune_context()
        if self.started:
            self._schedule_tick()

    def tick(self) -> None:
        """Subclass periodic logic; override."""

    def stop(self) -> None:
        self.started = False
        if self._tick_handle is not None:
            self.runtime.cancel(self._tick_handle)

    # ------------------------------------------------------------------
    def position(self) -> Tuple[float, float]:
        return (0.0, 0.0)

    # ------------------------------------------------------------------
    # context events
    def publish_context(self, ev_type: str, value: str, ttl: float = 20.0,
                        confidence: float = 1.0, affected: Optional[List[str]] = None) -> ContextEvent:
        self._seq += 1
        ev = ContextEvent(ev_type=ev_type, value=value, reporter=self.id, t=self.t,
                          confidence=confidence, ttl=ttl, affected=affected or [], seq=self._seq)
        self.plane.publish("fleet/events/context", {**ev.to_msg()})
        self._remember(ev)
        return ev

    def _on_context_event(self, key: str, payload: Dict[str, Any]) -> None:
        try:
            ev = ContextEvent.from_msg(payload)
        except Exception:  # noqa: BLE001
            return
        if ev.reporter == self.id:
            return
        self._remember(ev)

    def _remember(self, ev: ContextEvent) -> None:
        key = (ev.reporter, ev.seq)
        self.context[key] = ev
        if len(self.context) > MAX_CONTEXT_EVENTS:
            oldest = sorted(self.context.items(), key=lambda kv: kv[1].t)
            for k, _ in oldest[: len(self.context) - MAX_CONTEXT_EVENTS]:
                del self.context[k]

    def _prune_context(self) -> None:
        stale = [k for k, ev in self.context.items() if ev.expired(self.t)]
        for k in stale:
            del self.context[k]

    def active_context(self, ev_type: Optional[str] = None) -> List[ContextEvent]:
        out = [ev for ev in self.context.values() if ev_type is None or ev.ev_type == ev_type]
        return sorted(out, key=lambda e: e.t)

    def context_affects(self, ev_type: str, resource: str) -> bool:
        for ev in self.active_context(ev_type):
            if resource in ev.affected or ev.value == resource:
                return True
        return False

    # ------------------------------------------------------------------
    def on_control(self, key: str, payload: Dict[str, Any]) -> None:
        """Chaos control commands; subclasses override for specifics."""
        cmd = payload.get("cmd")
        if cmd == "SET_LATENCY":
            p = self.plane.profile
            p.latency_ms = float(payload.get("latency_ms", p.latency_ms))
            p.jitter_ms = float(payload.get("jitter_ms", p.jitter_ms))
        elif cmd == "SET_LOSS":
            self.plane.profile.loss_pct = float(payload.get("loss_pct", 0.0))
        elif cmd == "SET_PROFILE":
            prof = payload.get("profile", {})
            self.plane.set_profile(ImpairProfile(**{
                "latency_ms": prof.get("latency_ms", 12.0),
                "jitter_ms": prof.get("jitter_ms", 6.0),
                "loss_pct": prof.get("loss_pct", 0.5)}))

    # ------------------------------------------------------------------
    # telemetry (observability-only channel consumed by the bridge)
    def emit(self, ev_type: str, data: Dict[str, Any]) -> None:
        payload = {"agent": self.id, "kind": self.kind, "t": round(self.t, 3),
                   "type": ev_type, **data}
        self.plane.publish(f"fleet/telemetry/{self.id}", payload)
