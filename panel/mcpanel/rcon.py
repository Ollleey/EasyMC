"""Minimal Source RCON client (enough to run a command and read the reply).

Used for clean stat/command queries so they don't clutter the live console.
Falls back silently; callers handle exceptions.
"""
from __future__ import annotations

import socket
import struct

_TYPE_AUTH = 3
_TYPE_EXEC = 2


def _packet(req_id: int, ptype: int, body: str) -> bytes:
    payload = struct.pack("<ii", req_id, ptype) + body.encode("utf-8") + b"\x00\x00"
    return struct.pack("<i", len(payload)) + payload


def command(host: str, port: int, password: str, cmd: str, timeout: float = 5.0) -> str:
    """Connect, authenticate, run one command, return the response text."""
    with socket.create_connection((host, port), timeout=timeout) as sock:
        sock.settimeout(timeout)
        sock.sendall(_packet(1, _TYPE_AUTH, password))
        _read(sock)  # auth response
        sock.sendall(_packet(2, _TYPE_EXEC, cmd))
        return _read(sock)


def _read(sock: socket.socket) -> str:
    raw_len = _recv_exact(sock, 4)
    (length,) = struct.unpack("<i", raw_len)
    data = _recv_exact(sock, length)
    req_id, ptype = struct.unpack("<ii", data[:8])
    if req_id == -1:
        raise RuntimeError("RCON authentication failed")
    return data[8:-2].decode("utf-8", errors="replace")


def _recv_exact(sock: socket.socket, n: int) -> bytes:
    buf = b""
    while len(buf) < n:
        chunk = sock.recv(n - len(buf))
        if not chunk:
            raise ConnectionError("RCON connection closed")
        buf += chunk
    return buf
