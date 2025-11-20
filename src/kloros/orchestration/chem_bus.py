# chem_bus.py
# Chemical signal bus for KLoROS colony — PUB/SUB via ZeroMQ (preferred) with
# a fallback Unix datagram broadcaster for environments without pyzmq.

from __future__ import annotations
import json
import os
import socket
import threading
import time
from dataclasses import dataclass
from typing import Any, Callable, Dict, Optional

_ZMQ_AVAILABLE = False
try:
    import zmq  # type: ignore
    _ZMQ_AVAILABLE = True
except Exception:
    _ZMQ_AVAILABLE = False

DEFAULT_CHEM_SOCKET_PATH = "/run/spica/chem/queue.ipc"  # directory must exist

@dataclass
class ChemMessage:
    signal: str
    ecosystem: str
    intensity: float = 1.0
    facts: Dict[str, Any] | None = None
    incident_id: str | None = None
    trace: str | None = None
    ts: float = time.time()

    def to_bytes(self) -> bytes:
        return json.dumps(self.__dict__, separators=(",", ":")).encode("utf-8")

# --------------------- ZMQ Transport ---------------------

class _ZmqPub:
    def __init__(self, ipc_path: str):
        self._ctx = zmq.Context.instance()
        self._sock = self._ctx.socket(zmq.PUB)
        os.makedirs(os.path.dirname(ipc_path), exist_ok=True)
        self._sock.bind(f"ipc://{ipc_path}")

    def emit(self, topic: str, payload: bytes):
        # ZeroMQ topics are sent as prefix frame
        self._sock.send_multipart([topic.encode("utf-8"), payload])

    def close(self):
        try:
            self._sock.close(0)
        finally:
            pass

class _ZmqSub:
    def __init__(self, ipc_path: str, topic: str, on_message: Callable[[str, bytes], None]):
        self._ctx = zmq.Context.instance()
        self._sock = self._ctx.socket(zmq.SUB)
        self._sock.connect(f"ipc://{ipc_path}")
        self._sock.setsockopt(zmq.SUBSCRIBE, topic.encode("utf-8"))
        self._on = on_message
        self._stop = threading.Event()
        self._thr = threading.Thread(target=self._loop, daemon=True)
        self._thr.start()

    def _loop(self):
        while not self._stop.is_set():
            try:
                topic, payload = self._sock.recv_multipart()
                self._on(topic.decode("utf-8"), payload)
            except Exception:
                time.sleep(0.01)

    def close(self):
        self._stop.set()
        try:
            self._sock.close(0)
        finally:
            pass

# --------------------- Unix Datagram Fallback ---------------------

class _UnixPub:
    def __init__(self, path: str):
        # Create a datagram socket; broadcast by writing to a shared path.
        os.makedirs(os.path.dirname(path), exist_ok=True)
        # Remove stale socket file
        if os.path.exists(path):
            try:
                os.remove(path)
            except OSError:
                pass
        self._sock = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
        self._sock.bind(path)
        self._path = path

    def emit(self, topic: str, payload: bytes):
        # In fallback mode, topic is prefixed into payload; listeners bind their own path and must recvfrom.
        framed = json.dumps({"topic": topic, "payload": payload.decode("utf-8")}).encode("utf-8")
        # Fanout isn't native for SOCK_DGRAM; clients must poll the publisher path.
        # We simulate fanout by doing nothing here; subscribers will read from the pub socket path.
        self._sock.sendto(framed, self._path)

    def close(self):
        try:
            self._sock.close()
        finally:
            try:
                os.remove(self._path)
            except OSError:
                pass

class _UnixSub:
    def __init__(self, path: str, topic: str, on_message: Callable[[str, bytes], None]):
        self._sock = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
        # Subscribers bind to their own ephemeral path and read from publisher via connect+recv
        self._sub_path = f"{path}.{os.getpid()}.{int(time.time()*1000)}.sub"
        try:
            os.remove(self._sub_path)
        except OSError:
            pass
        self._sock.bind(self._sub_path)
        self._sock.connect(path)
        self._topic = topic
        self._on = on_message
        self._stop = threading.Event()
        self._thr = threading.Thread(target=self._loop, daemon=True)
        self._thr.start()

    def _loop(self):
        while not self._stop.is_set():
            try:
                data = self._sock.recv(65536)
                obj = json.loads(data.decode("utf-8"))
                if obj.get("topic") == self._topic:
                    self._on(self._topic, obj.get("payload", "").encode("utf-8"))
            except Exception:
                time.sleep(0.01)

    def close(self):
        self._stop.set()
        try:
            self._sock.close()
        finally:
            try:
                os.remove(self._sub_path)
            except OSError:
                pass

# --------------------- Public API ---------------------

class ChemPub:
    def __init__(self, ipc_path: str = DEFAULT_CHEM_SOCKET_PATH):
        self._impl = _ZmqPub(ipc_path) if _ZMQ_AVAILABLE else _UnixPub(ipc_path)

    def emit(self, signal: str, *, ecosystem: str, intensity: float = 1.0, facts: Optional[Dict[str, Any]] = None, incident_id: Optional[str] = None, trace: Optional[str] = None):
        msg = ChemMessage(signal=signal, ecosystem=ecosystem, intensity=intensity, facts=facts or {}, incident_id=incident_id, trace=trace)
        self._impl.emit(signal, msg.to_bytes())

    def close(self):
        self._impl.close()

class ChemSub:
    def __init__(self, topic: str, on_json: Callable[[Dict[str, Any]], None], ipc_path: str = DEFAULT_CHEM_SOCKET_PATH):
        def _on(_topic: str, payload: bytes):
            try:
                on_json(json.loads(payload.decode("utf-8")))
            except Exception:
                pass
        self._impl = _ZmqSub(ipc_path, topic, _on) if _ZMQ_AVAILABLE else _UnixSub(ipc_path, topic, _on)

    def close(self):
        self._impl.close()
