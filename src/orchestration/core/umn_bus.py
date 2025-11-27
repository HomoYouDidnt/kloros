# umn_bus.py — production-hardened Unus Mundus Network
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

DEFAULT_UMN_SOCKET_PATH = "/run/spica/umn/queue.ipc"
SCHEMA_VERSION = 1

# Proxy endpoints (publishers/subscribers CONNECT to these)
# TCP endpoints for production (loopback only, proven working)
XSUB_ENDPOINT = os.getenv("KLR_UMN_XSUB", "tcp://127.0.0.1:5558")
XPUB_ENDPOINT = os.getenv("KLR_UMN_XPUB", "tcp://127.0.0.1:5559")

# Channel types for UMN signal routing
CHANNEL_LEGACY = "legacy"    # Backward compatible pub/sub
CHANNEL_REFLEX = "reflex"    # Fast, ordered, acknowledged (future)
CHANNEL_AFFECT = "affect"    # Modulatory, fire-and-forget
CHANNEL_TROPHIC = "trophic"  # Slow, batched, eventual consistency

@dataclass
class UMNMessage:
    signal: str
    ecosystem: str
    intensity: float = 1.0
    facts: Dict[str, Any] = field(default_factory=dict)
    incident_id: Optional[str] = None
    trace: Optional[str] = None
    ts: float = field(default_factory=lambda: time.time())
    schema_version: int = SCHEMA_VERSION
    channel: str = CHANNEL_LEGACY  # Phase 1: metadata only, routing in future phases

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

# --------------------- Channel-Specific ZMQ Transports (Phase 2) ---------------------

REFLEX_ENDPOINT = os.getenv("KLR_UMN_REFLEX_ENDPOINT", "tcp://127.0.0.1:5560")
AFFECT_XSUB_ENDPOINT = os.getenv("KLR_UMN_AFFECT_XSUB", "tcp://127.0.0.1:5561")
AFFECT_XPUB_ENDPOINT = os.getenv("KLR_UMN_AFFECT_XPUB", "tcp://127.0.0.1:5562")
TROPHIC_PUSH_ENDPOINT = os.getenv("KLR_UMN_TROPHIC_PUSH", "tcp://127.0.0.1:5563")
TROPHIC_PULL_ENDPOINT = os.getenv("KLR_UMN_TROPHIC_PULL", "tcp://127.0.0.1:5564")

REFLEX_TIMEOUT_MS = int(os.getenv("KLR_UMN_REFLEX_TIMEOUT_MS", "5000"))
REFLEX_RETRIES = int(os.getenv("KLR_UMN_REFLEX_RETRIES", "3"))


class _ZmqReflexPub:
    """
    REFLEX publisher using DEALER for acknowledged delivery.

    Connects to proxy's ROUTER socket and waits for ACK/NACK.
    Raises TimeoutError if no ACK received within timeout.
    """

    def __init__(self, endpoint: str = REFLEX_ENDPOINT):
        self._ctx = zmq.Context.instance()
        self._sock = self._ctx.socket(zmq.DEALER)
        self._sock.setsockopt(zmq.IDENTITY, f"reflex-pub-{os.getpid()}".encode("utf-8"))
        self._sock.setsockopt(zmq.LINGER, 1000)
        self._sock.connect(endpoint)
        self._endpoint = endpoint
        logger.info(f"_ZmqReflexPub connected to {endpoint}")

    def emit(self, topic: str, payload: bytes, timeout_ms: int = REFLEX_TIMEOUT_MS) -> dict:
        """
        Emit with acknowledgment.

        Returns ACK response dict on success.
        Raises TimeoutError if no ACK, Exception if NACK.
        """
        self._sock.send_multipart([b"", payload])

        poller = zmq.Poller()
        poller.register(self._sock, zmq.POLLIN)
        socks = dict(poller.poll(timeout_ms))

        if self._sock in socks:
            ack_frames = self._sock.recv_multipart()
            ack_payload = ack_frames[1] if len(ack_frames) > 1 else ack_frames[0]
            ack_data = json.loads(ack_payload.decode("utf-8"))

            if not ack_data.get("ack"):
                raise Exception(f"NACK received: {ack_data.get('error')}")

            return ack_data
        else:
            raise TimeoutError(f"No ACK received within {timeout_ms}ms for topic={topic}")

    def close(self):
        try:
            self._sock.close(linger=0)
        except Exception:
            pass


class _ZmqAffectPub:
    """
    AFFECT publisher using PUB for fire-and-forget delivery.

    Low HWM ensures freshness - stale state is worse than dropped messages.
    """

    def __init__(self, endpoint: str = AFFECT_XSUB_ENDPOINT):
        self._ctx = zmq.Context.instance()
        self._sock = self._ctx.socket(zmq.PUB)
        self._sock.setsockopt(zmq.SNDHWM, 100)
        self._sock.setsockopt(zmq.LINGER, 100)
        self._sock.connect(endpoint)
        self._first_sends: Set[str] = set()
        time.sleep(0.1)
        logger.info(f"_ZmqAffectPub connected to {endpoint}")

    def emit(self, topic: str, payload: bytes):
        """Fire-and-forget emit. No acknowledgment, no retries."""
        is_first = topic not in self._first_sends
        self._sock.send_multipart([topic.encode("utf-8"), payload])
        if is_first:
            self._first_sends.add(topic)
            time.sleep(0.05)
            self._sock.send_multipart([topic.encode("utf-8"), payload])

    def close(self):
        try:
            self._sock.close(linger=0)
        except Exception:
            pass


class _ZmqTrophicPub:
    """
    TROPHIC publisher using PUSH for work distribution.

    Large HWM allows batching. Consumer processes in batches for efficiency.
    """

    def __init__(self, endpoint: str = TROPHIC_PUSH_ENDPOINT):
        self._ctx = zmq.Context.instance()
        self._sock = self._ctx.socket(zmq.PUSH)
        self._sock.setsockopt(zmq.SNDHWM, 10000)
        self._sock.setsockopt(zmq.LINGER, 5000)
        self._sock.connect(endpoint)
        logger.info(f"_ZmqTrophicPub connected to {endpoint}")

    def emit(self, topic: str, payload: bytes):
        """Push to work queue. Payload is self-describing (contains topic in JSON)."""
        self._sock.send(payload)

    def close(self):
        try:
            self._sock.close(linger=0)
        except Exception:
            pass


class _ZmqAffectSub:
    """
    AFFECT subscriber for fire-and-forget state changes.
    """

    def __init__(self, topic: str, on_message: Callable[[str, bytes], None],
                 endpoint: str = AFFECT_XPUB_ENDPOINT):
        self._ctx = zmq.Context.instance()
        self._sock = self._ctx.socket(zmq.SUB)
        self._sock.setsockopt(zmq.RCVHWM, 100)
        self._sock.connect(endpoint)
        self._sock.setsockopt(zmq.SUBSCRIBE, topic.encode("utf-8"))
        self._on = on_message
        self._stop = threading.Event()
        self._thr = threading.Thread(target=self._loop, daemon=True)
        self._thr.start()
        logger.info(f"_ZmqAffectSub subscribed to {topic} on {endpoint}")

    def _loop(self):
        while not self._stop.is_set():
            try:
                if self._sock.poll(timeout=1000):
                    topic, payload = self._sock.recv_multipart()
                    self._on(topic.decode("utf-8"), payload)
            except zmq.ZMQError:
                if not self._stop.is_set():
                    time.sleep(0.01)

    def close(self):
        self._stop.set()
        try:
            self._sock.close(linger=0)
        except Exception:
            pass


class _ZmqTrophicSub:
    """
    TROPHIC subscriber using PULL for work distribution.

    Supports batch processing for efficiency.
    """

    def __init__(self, on_message: Callable[[bytes], None],
                 endpoint: str = TROPHIC_PULL_ENDPOINT,
                 batch_size: int = 100,
                 batch_timeout_ms: int = 5000):
        self._ctx = zmq.Context.instance()
        self._sock = self._ctx.socket(zmq.PULL)
        self._sock.setsockopt(zmq.RCVHWM, 10000)
        self._sock.connect(endpoint)
        self._on = on_message
        self._batch_size = batch_size
        self._batch_timeout_ms = batch_timeout_ms
        self._stop = threading.Event()
        self._thr = threading.Thread(target=self._loop, daemon=True)
        self._thr.start()
        logger.info(f"_ZmqTrophicSub connected to {endpoint} batch_size={batch_size}")

    def _loop(self):
        batch = []
        batch_start = time.time()

        while not self._stop.is_set():
            try:
                if self._sock.poll(timeout=100):
                    payload = self._sock.recv()
                    batch.append(payload)

                    batch_elapsed_ms = (time.time() - batch_start) * 1000
                    if len(batch) >= self._batch_size or batch_elapsed_ms >= self._batch_timeout_ms:
                        for msg in batch:
                            self._on(msg)
                        batch = []
                        batch_start = time.time()
                else:
                    if batch:
                        batch_elapsed_ms = (time.time() - batch_start) * 1000
                        if batch_elapsed_ms >= self._batch_timeout_ms:
                            for msg in batch:
                                self._on(msg)
                            batch = []
                            batch_start = time.time()

            except zmq.ZMQError:
                if not self._stop.is_set():
                    time.sleep(0.01)

    def close(self):
        self._stop.set()
        try:
            self._sock.close(linger=0)
        except Exception:
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

ENABLE_CHANNELS = os.getenv("KLR_UMN_ENABLE_CHANNELS", "").lower() in ("true", "1", "yes")


class UMNPub:
    """
    UMN Publisher with optional channel-aware routing.

    When enable_channels=True (or KLR_UMN_ENABLE_CHANNELS env var):
    - REFLEX signals use DEALER/ROUTER with acknowledgment
    - AFFECT signals use dedicated PUB/SUB with low HWM
    - TROPHIC signals use PUSH/PULL for work distribution
    - LEGACY signals use standard PUB/SUB (backward compatible)

    When enable_channels=False (default):
    - All signals use legacy PUB/SUB regardless of channel field
    """

    def __init__(self, ipc_path: str = DEFAULT_UMN_SOCKET_PATH,
                 enable_channels: bool = None):
        self._enable_channels = enable_channels if enable_channels is not None else ENABLE_CHANNELS

        self._legacy = _ZmqPub(ipc_path) if _ZMQ_AVAILABLE else _UnixPub(ipc_path)

        if self._enable_channels and _ZMQ_AVAILABLE:
            self._reflex = _ZmqReflexPub()
            self._affect = _ZmqAffectPub()
            self._trophic = _ZmqTrophicPub()
            logger.info(f"chem:v{SCHEMA_VERSION} UMNPub initialized with channels enabled")
        else:
            self._reflex = None
            self._affect = None
            self._trophic = None
            logger.info(f"chem:v{SCHEMA_VERSION} UMNPub initialized (zmq={_ZMQ_AVAILABLE}, channels={self._enable_channels})")

    def emit(self, signal: str, *, ecosystem: str, intensity: float = 1.0,
             facts: Optional[Dict[str, Any]] = None, incident_id: Optional[str] = None,
             trace: Optional[str] = None, channel: str = CHANNEL_LEGACY,
             ack_timeout_ms: int = REFLEX_TIMEOUT_MS):
        """
        Emit a UMN signal.

        Args:
            signal: Signal name (e.g., "Q_REFLECT_TRIGGER")
            ecosystem: Signal ecosystem (e.g., "orchestration")
            intensity: Signal intensity (0.0-1.0+)
            facts: Signal-specific data payload
            incident_id: Unique identifier for deduplication
            trace: Trace/correlation ID for debugging
            channel: Target channel ("legacy", "reflex", "affect", "trophic")
            ack_timeout_ms: Timeout for REFLEX acknowledgment (only used for reflex channel)

        Raises:
            TimeoutError: If REFLEX signal not acknowledged within timeout
            Exception: If REFLEX signal receives NACK
        """
        msg = UMNMessage(
            signal=signal,
            ecosystem=ecosystem,
            intensity=intensity,
            facts=facts or {},
            incident_id=incident_id,
            trace=trace,
            channel=channel
        )
        payload = msg.to_bytes()

        if self._enable_channels and channel != CHANNEL_LEGACY:
            if channel == CHANNEL_REFLEX and self._reflex:
                ack = self._reflex.emit(signal, payload, timeout_ms=ack_timeout_ms)
                logger.info(f"chem:v{SCHEMA_VERSION} emit.reflex signal={signal} ecosystem={ecosystem} ack={ack.get('ack')}")
                return ack
            elif channel == CHANNEL_AFFECT and self._affect:
                self._affect.emit(signal, payload)
                logger.info(f"chem:v{SCHEMA_VERSION} emit.affect signal={signal} ecosystem={ecosystem}")
            elif channel == CHANNEL_TROPHIC and self._trophic:
                self._trophic.emit(signal, payload)
                logger.info(f"chem:v{SCHEMA_VERSION} emit.trophic signal={signal} ecosystem={ecosystem}")
            else:
                self._legacy.emit(signal, payload)
                logger.info(f"chem:v{SCHEMA_VERSION} emit.fallback signal={signal} ecosystem={ecosystem} channel={channel}")
        else:
            self._legacy.emit(signal, payload)
            logger.info(f"chem:v{SCHEMA_VERSION} emit signal={signal} ecosystem={ecosystem} channel={channel} incident_id={incident_id}")

    def close(self):
        """Close all transport connections."""
        self._legacy.close()
        if self._reflex:
            self._reflex.close()
        if self._affect:
            self._affect.close()
        if self._trophic:
            self._trophic.close()

class UMNSub:
    """
    Chemical signal subscriber with:
    - Replay defense (60s LRU of processed incident_ids)
    - Heartbeat emission (every 10s)
    - Kill switch support (chem://governance.kill)
    """

    def __init__(self, topic: str, on_json: Callable[[Dict[str, Any]], None],
                 ipc_path: str = DEFAULT_UMN_SOCKET_PATH,
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
        self._heartbeat_pub = UMNPub(ipc_path)
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
