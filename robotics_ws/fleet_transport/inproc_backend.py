"""In-process backend for the DES runtime (experiments).

Deliveries are scheduled on the DES event heap — same sender-latency and
receiver-loss semantics as the live backends.
"""
from __future__ import annotations

import heapq
import itertools
from typing import Callable, Dict, List, Tuple

from .base import Backend, key_matches


class InprocBackend(Backend):
    """All agents share one registry; publish = scheduled delivery."""

    def __init__(self, runtime):
        self.runtime = runtime
        self._subs: List[Tuple[str, Callable[[str, bytes], None]]] = []

    def send(self, key: str, data: bytes) -> None:
        # deliver to every matching subscriber as a scheduled event
        for pattern, handler in list(self._subs):
            if key_matches(key, pattern):
                h = handler
                self.runtime.call_later(0.0, lambda k=key, d=data, hh=h: hh(k, d))

    def subscribe(self, pattern: str, handler: Callable[[str, bytes], None]) -> None:
        self._subs.append((pattern, handler))

    def close(self) -> None:
        self._subs.clear()
