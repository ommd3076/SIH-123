"""UDP-multicast backend (fallback transport for hosts without Zenoh).

Each process binds the multicast group port and sends datagrams to the group.
Works on typical container/bridge networks (verified on this host).
"""
from __future__ import annotations

import socket
import struct
import threading
from typing import Callable, List, Tuple

from .base import Backend


class UdpMeshBackend(Backend):
    def __init__(self, group: str = "239.255.42.99", port: int = 50101):
        self.group = (group, port)
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            self._sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 4)
            self._sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_LOOP, 1)
        except OSError:
            pass
        self._recv = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        self._recv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._recv.bind(("", port))
        mreq = struct.pack("4sl", socket.inet_aton(group), socket.INADDR_ANY)
        self._recv.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)
        self._recv.settimeout(0.25)
        self._subs: List[Tuple[str, Callable[[str, bytes], None]]] = []
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def _loop(self) -> None:
        from .base import key_matches
        while self._running:
            try:
                data, _ = self._recv.recvfrom(262144)
            except socket.timeout:
                continue
            except OSError:
                break
            # minimal envelope parse to route by key
            try:
                import json
                env = json.loads(data)
                key = env.get("key", "")
            except Exception:  # noqa: BLE001
                continue
            for pattern, handler in list(self._subs):
                if key_matches(key, pattern):
                    try:
                        handler(key, data)
                    except Exception:  # noqa: BLE001
                        pass

    def send(self, key: str, data: bytes) -> None:
        self._sock.sendto(data, self.group)

    def subscribe(self, pattern: str, handler: Callable[[str, bytes], None]) -> None:
        self._subs.append((pattern, handler))

    def close(self) -> None:
        self._running = False
        try:
            self._recv.close()
            self._sock.close()
        except OSError:
            pass
