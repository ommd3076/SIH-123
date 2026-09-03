"""Zenoh backend (primary live transport).

Uses eclipse-zenoh Python bindings (pip install eclipse-zenoh), peer mode with
default multicast scouting — verified working on this host. Each agent process
opens its own Zenoh session: no central broker is required for coordination.

Zenoh key expressions ('fleet/robot/*/intent') are used natively for
subscription filtering; messages carry the same JSON envelope as every other
backend.
"""
from __future__ import annotations

import atexit
import logging
from typing import Callable, List, Tuple

from .base import Backend

log = logging.getLogger("zenoh-backend")


class ZenohBackend(Backend):
    def __init__(self, session=None):
        self._owned = False
        if session is None:
            import zenoh
            self._zenoh = zenoh
            self.session = zenoh.open(zenoh.Config())
            self._owned = True
            atexit.register(self.close)
        else:
            self.session = session
        self._subs: List[Tuple[str, Callable]] = []
        self._declared = []

    def send(self, key: str, data: bytes) -> None:
        try:
            self.session.put(key, data)
        except Exception as e:  # noqa: BLE001
            log.debug("zenoh put failed: %s", e)

    def subscribe(self, pattern: str, handler: Callable[[str, bytes], None]) -> None:

        def _cb(sample):
            try:
                # recover the envelope key (zenoh delivers the key expression)
                key = str(sample.key_expr)
                payload = bytes(sample.payload)
                handler(key, payload)
            except Exception:  # noqa: BLE001
                pass

        sub = self.session.declare_subscriber(pattern, _cb)
        self._declared.append(sub)

    def close(self) -> None:
        for s in self._declared:
            try:
                s.undeclare()
            except Exception:  # noqa: BLE001
                pass
        self._declared.clear()
        if self._owned:
            try:
                self.session.close()
            except Exception:  # noqa: BLE001
                pass


def make_backend(kind: str, **kwargs) -> Backend:
    if kind == "zenoh":
        try:
            return ZenohBackend()
        except Exception as e:  # noqa: BLE001
            log.warning("zenoh unavailable (%s), falling back to udp-mesh", e)
            from .udpmesh_backend import UdpMeshBackend
            return UdpMeshBackend()
    if kind == "udp":
        from .udpmesh_backend import UdpMeshBackend
        return UdpMeshBackend()
    if kind == "inproc":
        from .inproc_backend import InprocBackend
        return InprocBackend(kwargs["runtime"])
    raise ValueError(f"unknown backend: {kind}")
