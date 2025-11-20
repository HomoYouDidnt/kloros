# chem_bus_v2.py — production-hardened chemical signal bus
# Adds: schema versioning, structured logs, heartbeats, replay defense

from __future__ import annotations
import json
import os
import socket
import threading
import time
import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Optional, Set
from collections import OrderedDict

logger = logging.getLogger(__name__)

_ZMQ_AVAILABLE = False
try:
    import zmq  # type: ignore
    _ZMQ_AVAILABLE = True
except Exception:
    _ZMQ_AVAILABLE = False

DEFAULT_CHEM_SOCKET_PATH = "/run/spica/chem/queue.ipc"
SCHEMA_VERSION = 1

# Proxy endpoints (publishers/subscribers CONNECT to these)
# TCP endpoints for production (loopback only, proven working)
XSUB_ENDPOINT = os.getenv("KLR_CHEM_XSUB", "tcp://127.0.0.1:5558")
XPUB_ENDPOINT = os.getenv("KLR_CHEM_XPUB", "tcp://127.0.0.1:5559")

@dataclass
class ChemMessage:
    signal: str
    ecosystem: str
    intensity: float = 1.0
    facts: Dict[str, Any] = field(default_factory=dict)
    incident_id: Optional[str] = None
    trace: Optional[str] = None
    ts: float = field(default_factory=lambda: time.time())
    schema_version: int = SCHEMA_VERSION

    def to_bytes(self) -> bytes:
        return json.dumps(self.__dict__, separators=(",", ":")).encode("utf-8")

# --------------------- ZMQ Transport (CONNECT mode for proxy) ---------------------

class _ZmqPub:
    def __init__(self, ipc_path: str = None):
        self._ctx = zmq.Context.instance()
        self._sock = self._ctx.socket(zmq.PUB)
        self._sock.set_hwm(1000)  # High water mark
        self._first_sends: Set[str] = set()  # Track first sends per topic for double-tap
        # CONNECT to proxy's XSUB endpoint (not BIND)
        logger.info(f"_ZmqPub connecting to XSUB_ENDPOINT: {XSUB_ENDPOINT}")
        self._sock.connect(XSUB_ENDPOINT)
        # ZMQ slow-joiner workaround: wait for connection to establish
        time.sleep(0.1)
        logger.info(f"_ZmqPub connected successfully")

    def emit(self, topic: str, payload: bytes):
        # Double-tap first message per topic (slow-joiner protection)
        is_first = topic not in self._first_sends
        self._sock.send_multipart([topic.encode("utf-8"), payload])
        if is_first:
            self._first_sends.add(topic)
            time.sleep(0.15)  # 150ms gap
            self._sock.send_multipart([topic.encode("utf-8"), payload])
            logger.debug(f"Double-tapped first message for topic: {topic}")

    def close(self):
        try:
            self._sock.close(0)
        finally:
            pass

class _ZmqSub:
    def __init__(self, ipc_path: str = None, topic: str = "", on_message: Callable[[str, bytes], None] = None):
        self._ctx = zmq.Context.instance()
        self._sock = self._ctx.socket(zmq.SUB)
        # CONNECT to proxy's XPUB endpoint (not direct IPC)
        self._sock.connect(XPUB_ENDPOINT)
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

# --------------------- Unix Datagram Fallback (unchanged) ---------------------

class _UnixPub:
    def __init__(self, path: str):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        if os.path.exists(path):
            try:
                os.remove(path)
            except OSError:
                pass
        self._sock = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
        self._sock.bind(path)
        self._path = path

    def emit(self, topic: str, payload: bytes):
        framed = json.dumps({"topic": topic, "payload": payload.decode("utf-8")}).encode("utf-8")
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

# --------------------- Public API with Observability ---------------------

class ChemPub:
    def __init__(self, ipc_path: str = DEFAULT_CHEM_SOCKET_PATH):
        self._impl = _ZmqPub(ipc_path) if _ZMQ_AVAILABLE else _UnixPub(ipc_path)
        logger.info(f"chem:v{SCHEMA_VERSION} ChemPub initialized (zmq={_ZMQ_AVAILABLE})")

    def emit(self, signal: str, *, ecosystem: str, intensity: float = 1.0,
             facts: Optional[Dict[str, Any]] = None, incident_id: Optional[str] = None,
             trace: Optional[str] = None):
        msg = ChemMessage(
            signal=signal,
            ecosystem=ecosystem,
            intensity=intensity,
            facts=facts or {},
            incident_id=incident_id,
            trace=trace
        )
        self._impl.emit(signal, msg.to_bytes())
        logger.info(f"chem:v{SCHEMA_VERSION} emit signal={signal} ecosystem={ecosystem} incident_id={incident_id}")

    def close(self):
        self._impl.close()

class ChemSub:
    """
    Chemical signal subscriber with:
    - Replay defense (60s LRU of processed incident_ids)
    - Heartbeat emission (every 10s)
    - Kill switch support (chem://governance.kill)
    """

    def __init__(self, topic: str, on_json: Callable[[Dict[str, Any]], None],
                 ipc_path: str = DEFAULT_CHEM_SOCKET_PATH,
                 zooid_name: Optional[str] = None,
                 niche: Optional[str] = None):
        self.zooid_name = zooid_name or f"zooid_{os.getpid()}"
        self.niche = niche or "unknown"
        self._processed_incidents: OrderedDict[str, float] = OrderedDict()  # incident_id -> ts
        self._replay_window_s = 60.0
        self._on_json = on_json
        self._killed = False

        def _on_message(_topic: str, payload: bytes):
            try:
                msg = json.loads(payload.decode("utf-8"))

                # Kill switch
                if _topic == "governance.kill":
                    logger.warning(f"chem:v{SCHEMA_VERSION} {self.zooid_name} received kill signal")
                    self._killed = True
                    return

                # Replay defense
                incident_id = msg.get("incident_id")
                if incident_id and self._is_duplicate(incident_id):
                    logger.debug(f"chem:v{SCHEMA_VERSION} {self.zooid_name} skipping duplicate incident_id={incident_id}")
                    return

                # Process message
                self._on_json(msg)

                # Record processed
                if incident_id:
                    self._mark_processed(incident_id)

            except Exception as e:
                logger.error(f"chem:v{SCHEMA_VERSION} {self.zooid_name} error processing message: {e}")

        # Subscribe to target topic + kill switch
        self._impl = _ZmqSub(ipc_path, topic, _on_message) if _ZMQ_AVAILABLE else _UnixSub(ipc_path, topic, _on_message)
        self._kill_sub = _ZmqSub(ipc_path, "governance.kill", _on_message) if _ZMQ_AVAILABLE else None

        # Start heartbeat thread
        self._heartbeat_pub = ChemPub(ipc_path)
        self._heartbeat_thread = threading.Thread(target=self._heartbeat_loop, daemon=True)
        self._heartbeat_thread.start()

        logger.info(f"chem:v{SCHEMA_VERSION} {self.zooid_name} subscribed to {topic} niche={self.niche}")

    def _is_duplicate(self, incident_id: str) -> bool:
        """Check if incident was recently processed (replay defense)."""
        now = time.time()

        # Prune old entries
        cutoff = now - self._replay_window_s
        while self._processed_incidents and next(iter(self._processed_incidents.values())) < cutoff:
            self._processed_incidents.popitem(last=False)

        return incident_id in self._processed_incidents

    def _mark_processed(self, incident_id: str):
        """Mark incident as processed."""
        self._processed_incidents[incident_id] = time.time()

    def _heartbeat_loop(self):
        """Emit heartbeat every 10s."""
        while not self._killed:
            try:
                self._heartbeat_pub.emit(
                    "HEARTBEAT",
                    ecosystem="colony",
                    facts={
                        "zooid": self.zooid_name,
                        "niche": self.niche,
                        "uptime_s": time.time(),
                        "processed_count": len(self._processed_incidents)
                    }
                )
                time.sleep(10)
            except Exception as e:
                logger.error(f"Heartbeat error: {e}")
                break

    def is_killed(self) -> bool:
        """Check if kill switch was triggered."""
        return self._killed

    def close(self):
        self._killed = True
        self._impl.close()
        if self._kill_sub:
            self._kill_sub.close()
        self._heartbeat_pub.close()
