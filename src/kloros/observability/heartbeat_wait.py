"""
Heartbeat waiting helper for lifecycle graduation verification.

Subscribes to HEARTBEAT topic on ChemBus and waits for specific zooid heartbeat.
"""
import time
import json
import logging

logger = logging.getLogger(__name__)

_ZMQ_AVAILABLE = False
try:
    import zmq
    _ZMQ_AVAILABLE = True
except ImportError:
    pass


def wait_for_heartbeat(zooid_name: str, timeout_sec: float,
                       xpub_endpoint: str = "tcp://127.0.0.1:5557") -> bool:
    """
    Wait for heartbeat from specific zooid.

    Args:
        zooid_name: Zooid name to wait for
        timeout_sec: Timeout in seconds
        xpub_endpoint: ZMQ XPUB endpoint (default: tcp://127.0.0.1:5557)

    Returns:
        True if heartbeat received within timeout
    """
    if not _ZMQ_AVAILABLE:
        logger.warning("ZMQ not available, skipping heartbeat wait")
        return False

    ctx = zmq.Context.instance()
    sub = ctx.socket(zmq.SUB)

    try:
        sub.connect(xpub_endpoint)
        sub.setsockopt(zmq.SUBSCRIBE, b"HEARTBEAT")  # topic prefix

        deadline = time.time() + timeout_sec
        poller = zmq.Poller()
        poller.register(sub, zmq.POLLIN)

        logger.info(f"Waiting for heartbeat from {zooid_name} (timeout={timeout_sec}s)")

        while time.time() < deadline:
            remaining = deadline - time.time()
            if remaining <= 0:
                break

            socks = dict(poller.poll(timeout=min(250, remaining * 1000)))  # 250ms tick

            if sub in socks and socks[sub] == zmq.POLLIN:
                topic, payload = sub.recv_multipart()

                try:
                    row = json.loads(payload.decode("utf-8"))

                    # Check if this is from our zooid
                    if row.get("facts", {}).get("zooid") == zooid_name:
                        logger.info(f"✓ Heartbeat received from {zooid_name}")
                        return True

                except Exception as e:
                    logger.debug(f"Error parsing heartbeat: {e}")
                    pass

        logger.warning(f"Timeout waiting for heartbeat from {zooid_name}")
        return False

    finally:
        sub.close()
