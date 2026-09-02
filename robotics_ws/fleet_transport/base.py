"""Message plane: impairment, locality and stats over pluggable backends.

Backends are dumb byte pipes (Zenoh / UDP multicast / in-process). This module
owns the semantics that make coordination honest:

  * sender-side latency scheduling (messages REALLY delayed on the wire)
  * receiver-side loss (packets REALLY dropped before handlers see them)
  * receiver-side radio-range filtering (local communication only)
  * per-agent traffic statistics (msgs/s, bytes/s — real measurements)

Envelope format (JSON):
  {"t": sim_time, "src": agent_id, "pos": [x, y], "payload": {...}}
"""
from __future__ import annotations

import json
import math
import random
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple

Handler = Callable[[str, Dict[str, Any]], None]
PosProvider = Callable[[], Tuple[float, float]]


@dataclass
class ImpairProfile:
    latency_ms: float = 12.0
    jitter_ms: float = 6.0
    loss_pct: float = 0.5

    def draw_latency_s(self, rng: random.Random) -> float:
        lat = self.latency_ms + rng.uniform(-self.jitter_ms, self.jitter_ms)
        return max(0.0, lat / 1000.0)

    def to_msg(self) -> Dict[str, Any]:
        return {"latency_ms": self.latency_ms, "jitter_ms": self.jitter_ms,
                "loss_pct": self.loss_pct}


def key_matches(key: str, pattern: str) -> bool:
    """Segment-wise glob: '*' matches exactly one path segment."""
    if pattern == "**" or pattern == "*/*/**":
        return True
    kparts = key.split("/")
    pparts = pattern.split("/")
    if len(pparts) != len(kparts):
        return False
    for p, k in zip(pparts, kparts):
        if p == "**":
            continue
        if p == "*":
            continue
        if p != k:
            return False
    return True


@dataclass
class AgentStats:
    sent: int = 0
    sent_bytes: int = 0
    recv: int = 0
    recv_bytes: int = 0
    dropped_loss: int = 0
    dropped_range: int = 0
    delivered: int = 0

    def to_msg(self) -> Dict[str, Any]:
        return {"sent": self.sent, "sent_bytes": self.sent_bytes,
                "recv": self.recv, "recv_bytes": self.recv_bytes,
                "dropped_loss": self.dropped_loss, "dropped_range": self.dropped_range,
                "delivered": self.delivered}


class Backend:
    """Byte-pipe backend. Subclasses implement send() and subscribe()."""

    def send(self, key: str, data: bytes) -> None:
        raise NotImplementedError

    def subscribe(self, pattern: str, handler: Callable[[str, bytes], None]) -> None:
        raise NotImplementedError

    def close(self) -> None:
        pass


class MessagePlane:
    """Per-agent messaging facade with impairment + range semantics."""

    def __init__(self, backend: Backend, agent_id: str, *,
                 range_m: float = math.inf,
                 profile: ImpairProfile = None,
                 rng: random.Random = None,
                 scheduler: Optional[Callable[[float, Callable[[], None]], None]] = None,
                 infra: bool = False):
        self.backend = backend
        self.agent_id = agent_id
        self.range_m = range_m
        self.infra = infra          # wired backbone: messages bypass radio range
        self.profile = profile or ImpairProfile()
        self.rng = rng or random.Random()
        self.scheduler = scheduler            # (delay_s, fn) -> None
        self.pos_provider: Optional[PosProvider] = None
        self.stats = AgentStats()
        self._subs: List[Tuple[str, Handler]] = []
        backend.subscribe("**", self._on_raw)

    # ------------------------------------------------------------------
    def set_pos_provider(self, fn: PosProvider) -> None:
        self.pos_provider = fn

    def set_profile(self, profile: ImpairProfile) -> None:
        self.profile = profile

    def subscribe(self, pattern: str, handler: Handler) -> None:
        self._subs.append((pattern, handler))

    def publish(self, key: str, payload: Dict[str, Any]) -> None:
        """Publish with sender-side latency scheduling (real message delay)."""
        pos = self.pos_provider() if self.pos_provider else [0.0, 0.0]
        env = {"t": payload.get("t", 0.0), "src": self.agent_id,
               "pos": [round(pos[0], 2), round(pos[1], 2)],
               "infra": self.infra,
               "key": key, "payload": payload}
        data = json.dumps(env, separators=(",", ":")).encode()
        self.stats.sent += 1
        self.stats.sent_bytes += len(data)
        delay = self.profile.draw_latency_s(self.rng)
        if delay <= 0:
            self.backend.send(key, data)
        else:
            self.scheduler(delay, lambda: self.backend.send(key, data))

    # ------------------------------------------------------------------
    def _on_raw(self, key: str, data: bytes) -> None:
        try:
            env = json.loads(data)
        except (ValueError, UnicodeDecodeError):
            return
        src = env.get("src")
        if src == self.agent_id:
            return                          # own messages echoed back
        self.stats.recv += 1
        self.stats.recv_bytes += len(data)
        # receiver-side loss (real packet drop before handlers)
        if self.profile.loss_pct > 0 and self.rng.random() * 100.0 < self.profile.loss_pct:
            self.stats.dropped_loss += 1
            return
        # receiver-side radio range (wired infrastructure bypasses it)
        if self.range_m != math.inf and not env.get("infra"):
            src_pos = env.get("pos", [0.0, 0.0])
            my_pos = self.pos_provider() if self.pos_provider else (0.0, 0.0)
            d = math.hypot(src_pos[0] - my_pos[0], src_pos[1] - my_pos[1])
            if d > self.range_m:
                self.stats.dropped_range += 1
                return
        msg_key = env.get("key", key)
        for pattern, handler in self._subs:
            if key_matches(msg_key, pattern):
                self.stats.delivered += 1
                try:
                    handler(msg_key, env["payload"])
                except Exception as e:        # noqa: BLE001 — agents must not die on bad input
                    import logging
                    logging.getLogger("message-plane").debug(
                        "handler %s failed on %s: %r", pattern, msg_key, e)


def broadcast_profile(agents: List[MessagePlane], profile: ImpairProfile) -> None:
    for a in agents:
        a.set_profile(profile)
