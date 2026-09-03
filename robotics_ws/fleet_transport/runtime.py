"""Runtimes drive agent logic.

  * DESRuntime      — deterministic discrete-event virtual time (experiments)
  * AsyncioRuntime  — real wall-clock time, asyncio loop (live multi-process demo)

Agents are written against the RuntimeFacade interface only:
    now(), call_later(dt, fn), cancel(handle)
so the SAME agent code runs in both.
"""
from __future__ import annotations

import asyncio
import heapq
import itertools
import time
from typing import Any, Callable, Dict, List, Optional


class RuntimeFacade:
    def now(self) -> float:
        raise NotImplementedError

    def call_later(self, dt: float, fn: Callable[[], None]) -> Any:
        raise NotImplementedError

    def cancel(self, handle: Any) -> None:
        raise NotImplementedError

    def sleep_task(self, dt: float) -> "asyncio.Future":
        raise NotImplementedError


class DESRuntime(RuntimeFacade):
    """Virtual-time discrete-event runtime. Deterministic: events are ordered
    by (time, insertion sequence)."""

    def __init__(self, t0: float = 0.0):
        self._t = t0
        self._heap: List[Any] = []
        self._seq = itertools.count()
        self._cancelled: set = set()
        self.now_wall = time.perf_counter

    def now(self) -> float:
        return self._t

    def call_later(self, dt: float, fn: Callable[[], None]) -> Any:
        if dt < 0:
            dt = 0.0
        entry = (self._t + dt, next(self._seq), fn)
        heapq.heappush(self._heap, entry)
        return entry

    def cancel(self, handle: Any) -> None:
        self._cancelled.add(id(handle))

    def run(self, until: float) -> None:
        while self._heap:
            t = self._heap[0][0]
            if t > until:
                break
            entry = heapq.heappop(self._heap)     # the ORIGINAL object
            if id(entry) in self._cancelled:
                continue
            if t > self._t:
                self._t = t
            entry[2]()

    def step(self, max_events: int = 100000) -> None:
        for _ in range(max_events):
            if not self._heap:
                return
            entry = heapq.heappop(self._heap)
            if id(entry) in self._cancelled:
                continue
            if entry[0] > self._t:
                self._t = entry[0]
            entry[2]()
            return

    def pending(self) -> int:
        return len(self._heap)


class AsyncioRuntime(RuntimeFacade):
    """Wall-clock runtime with optional time scaling.

    sim_now = epoch + (perf_counter - wall0) * scale
    A `dt` in sim seconds is scheduled dt/scale wall seconds later.
    """

    def __init__(self, t0: float = 0.0, scale: float = 1.0, loop: asyncio.AbstractEventLoop = None):
        self.scale = scale
        self._t0 = t0
        self._wall0 = time.perf_counter()
        self.loop = loop or asyncio.get_event_loop()

    def now(self) -> float:
        return self._t0 + (time.perf_counter() - self._wall0) * self.scale

    def call_later(self, dt: float, fn: Callable[[], None]) -> Any:
        wall = max(0.0, dt / self.scale)
        return self.loop.call_later(wall, fn)

    def cancel(self, handle: Any) -> None:
        try:
            handle.cancel()
        except Exception:  # noqa: BLE001
            pass

    async def wait(self, dt: float) -> None:
        await asyncio.sleep(max(0.0, dt / self.scale))
