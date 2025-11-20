"""
OBSERVATION event emitter with HMAC signing for fitness ledger.

Zooids use this to emit OBSERVATION events that the ledger writer will consume.
"""
import json
import hmac
import hashlib
import time
import logging
from pathlib import Path
from typing import Dict, Any

logger = logging.getLogger(__name__)

_ZMQ_AVAILABLE = False
try:
    import zmq
    _ZMQ_AVAILABLE = True
except ImportError:
    pass


def _canonical(d: dict) -> bytes:
    """Canonical JSON serialization for HMAC."""
    return json.dumps(d, sort_keys=True, separators=(",", ":")).encode("utf-8")


def sign_and_emit(observation: dict,
                  key_path: str = None,
                  xsub_endpoint: str = "tcp://127.0.0.1:5556"):
    """
    Sign observation with HMAC and emit to ChemBus.

    Args:
        observation: Observation data dict (must include: ts, incident_id, zooid, niche, ok, ttr_ms)
        key_path: Path to HMAC key (default: ~/.kloros/keys/hmac.key)
        xsub_endpoint: ZMQ XSUB endpoint (default: tcp://127.0.0.1:5556)
    """
    if not _ZMQ_AVAILABLE:
        logger.error("ZMQ not available, cannot emit observation")
        return

    # Default key path
    if key_path is None:
        key_path = str(Path.home() / ".kloros/keys/hmac.key")

    # Load HMAC key
    try:
        key = Path(key_path).expanduser().read_bytes()
    except Exception as e:
        logger.error(f"Failed to load HMAC key from {key_path}: {e}")
        return

    # Prepare observation body (exclude 'sig' field)
    body = {k: v for k, v in observation.items() if k != "sig"}

    # Sign with HMAC-SHA256
    sig = hmac.new(key, _canonical(body), hashlib.sha256).hexdigest()
    row = dict(body, sig=sig)

    # Wrap in ChemMessage format
    chem_message = {
        "signal": "OBSERVATION",
        "ecosystem": observation.get("ecosystem", "unknown"),
        "intensity": 1.0,
        "facts": row,  # Observation data goes in facts
        "incident_id": observation.get("incident_id"),
        "ts": observation.get("ts", time.time()),
        "schema_version": 1
    }

    # Emit to ChemBus
    ctx = zmq.Context.instance()
    pub = ctx.socket(zmq.PUB)

    try:
        pub.connect(xsub_endpoint)

        # Slow-joiner mitigation (give subscribers time to connect)
        time.sleep(0.15)

        # Emit as multipart: [topic, payload]
        pub.send_multipart([b"OBSERVATION", _canonical(chem_message)])

        logger.info(f"✓ Emitted OBSERVATION for {observation.get('zooid')} incident={observation.get('incident_id')}")

    except Exception as e:
        logger.error(f"Failed to emit observation: {e}")
    finally:
        pub.close()


def emit_observation_simple(zooid_name: str, niche: str, ecosystem: str,
                             incident_id: str, ok: bool, ttr_ms: float,
                             **extra_facts):
    """
    Simplified observation emitter with common fields.

    Args:
        zooid_name: Zooid name
        niche: Niche name
        ecosystem: Ecosystem name
        incident_id: Incident ID
        ok: Success flag
        ttr_ms: Time-to-resolution in milliseconds
        **extra_facts: Additional facts to include
    """
    observation = {
        "ts": time.time(),
        "incident_id": incident_id,
        "zooid": zooid_name,
        "niche": niche,
        "ecosystem": ecosystem,
        "ok": ok,
        "ttr_ms": ttr_ms,
        **extra_facts
    }

    sign_and_emit(observation)
