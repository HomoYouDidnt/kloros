"""
Central Ledger Writer - trusted append-only OBSERVATION log.

Verifies HMAC signatures, atomically appends to fitness ledger,
maintains rolling production metrics per zooid.
"""
import hashlib
import hmac
import json
import logging
import os
from pathlib import Path
from typing import Callable, Dict, List, Optional

logger = logging.getLogger(__name__)

DEFAULT_LEDGER_PATH = Path.home() / ".kloros/lineage/fitness_ledger.jsonl"
DEFAULT_HMAC_KEY_PATH = Path.home() / ".kloros/keys/hmac.key"


def verify_hmac(row: dict, key_path: str) -> bool:
    """
    Verify HMAC signature on OBSERVATION row.

    Args:
        row: OBSERVATION dict with 'sig' field
        key_path: Path to HMAC key file

    Returns:
        True if signature is valid, False otherwise

    Algorithm:
        1. Extract sig from row
        2. Canonicalize row (sorted keys, no whitespace, UTF-8)
        3. Compute HMAC-SHA256
        4. Compare with provided sig
    """
    if "sig" not in row:
        logger.warning("Row missing 'sig' field")
        return False

    provided_sig = row["sig"]

    try:
        with open(key_path, 'rb') as f:
            key = f.read()
    except FileNotFoundError:
        logger.error(f"HMAC key not found: {key_path}")
        return False

    row_copy = {k: v for k, v in row.items() if k != "sig"}
    canonical = json.dumps(row_copy, sort_keys=True, separators=(',', ':'), ensure_ascii=False)
    canonical_bytes = canonical.encode('utf-8')

    computed_sig = hmac.new(key, canonical_bytes, hashlib.sha256).hexdigest()

    if hmac.compare_digest(computed_sig, provided_sig):
        return True
    else:
        logger.warning(f"HMAC mismatch for row: {row.get('incident_id', 'unknown')}")
        return False


def append_observation_atomic(row: dict, path: str) -> None:
    """
    Atomically append OBSERVATION row to ledger.

    Args:
        row: OBSERVATION dict to append
        path: Path to ledger file

    Algorithm:
        Open with O_APPEND mode, write single line, fsync
    """
    ledger_path = Path(path)
    ledger_path.parent.mkdir(parents=True, exist_ok=True)

    line = json.dumps(row, separators=(',', ':')) + '\n'

    with open(ledger_path, 'a', buffering=1, encoding='utf-8') as f:
        f.write(line)
        f.flush()
        os.fsync(f.fileno())

    logger.debug(f"Appended row: {row.get('incident_id')}")


def _update_ok_window(z_prod: dict, ok: bool, policy: Optional[dict]) -> None:
    """
    Maintain last-N ok window via 64-bit ring buffer with warm-up denominator.

    Args:
        z_prod: Zooid production metrics dict (mutated in-place)
        ok: Success flag for current observation
        policy: Policy dict with optional prod_ok_window_n

    Updates:
        z_prod.ok_window_bits: Hex string of ring buffer state
        z_prod.ok_window_idx: Current write index [0, N-1]
        z_prod.ok_window_n: Window size (1-64)
        z_prod.ok_rate_window: Ratio of successes in last min(evidence+1, N) observations

    Algorithm:
        - Ring buffer stored as 64-bit integer (hex string in JSON)
        - Warm-up: denominator = min(evidence+1, N) until ring is full
        - After warm-up: denominator = N (fixed window)
        - Bit positions [0, evidence] during warm-up, all N bits after
    """
    if policy is None:
        policy = {}

    N = int(policy.get("prod_ok_window_n", 20))
    N = max(1, min(N, 64))

    # Load ring state
    bits_raw = z_prod.get("ok_window_bits", "0x0")
    bits = int(bits_raw, 16) if isinstance(bits_raw, str) else int(bits_raw or 0)
    idx = int(z_prod.get("ok_window_idx", -1))
    evidence = int(z_prod.get("evidence", 0))

    # Advance index and set/clear bit
    idx = (idx + 1) % N
    if ok:
        bits |= (1 << idx)
    else:
        bits &= ~(1 << idx)

    # Warm-up denominator: use min(observations_seen, N)
    denom = min(evidence + 1, N)

    if evidence < N:
        # Warm-up: count bits in first (evidence+1) positions [0, evidence]
        # We write positions sequentially until ring fills
        mask = (1 << (evidence + 1)) - 1
    else:
        # Full window: count all N bits
        mask = (1 << N) - 1

    window_bits = bits & mask
    k = window_bits.bit_count()

    z_prod["ok_window_bits"] = hex(bits)
    z_prod["ok_window_idx"] = idx
    z_prod["ok_window_n"] = N
    z_prod["ok_rate_window"] = k / float(denom)


def update_registry_rolling_metrics(reg: dict, row: dict, now: float, policy: Optional[dict] = None) -> None:
    """
    Update zooid production metrics in registry.

    Args:
        reg: Registry dict (mutated in-place)
        row: OBSERVATION row with ok, ttr_ms, zooid fields
        now: Current timestamp
        policy: Optional policy dict with prod_ok_window_n

    Updates:
        z.prod.ok_rate (EWMA rolling average)
        z.prod.ok_rate_window (last-N success rate with warm-up)
        z.prod.ttr_ms_mean (EWMA rolling average)
        z.prod.evidence (count)
        z.prod.last_ts (timestamp of last observation)
    """
    zooid_name = row.get("zooid")
    if not zooid_name:
        return

    z = reg["zooids"].get(zooid_name)
    if not z:
        logger.debug(f"Zooid not in registry: {zooid_name}")
        return

    if "prod" not in z:
        z["prod"] = {
            "ok_rate": 0.0,
            "ttr_ms_mean": 0.0,
            "evidence": 0,
            "last_ts": 0.0
        }

    ok = row.get("ok", True)
    ttr_ms = row.get("ttr_ms", 0)

    evidence = z["prod"]["evidence"]
    alpha = 0.1

    # === EWMA ok_rate (unchanged) ===
    if evidence == 0:
        z["prod"]["ok_rate"] = 1.0 if ok else 0.0
        z["prod"]["ttr_ms_mean"] = float(ttr_ms)
    else:
        z["prod"]["ok_rate"] = (1 - alpha) * z["prod"]["ok_rate"] + alpha * (1.0 if ok else 0.0)
        z["prod"]["ttr_ms_mean"] = (1 - alpha) * z["prod"]["ttr_ms_mean"] + alpha * float(ttr_ms)

    # === Windowed ok_rate (NEW) ===
    _update_ok_window(z["prod"], ok, policy)

    # === Evidence and timestamp ===
    z["prod"]["evidence"] += 1
    z["prod"]["last_ts"] = now

    logger.debug(f"Updated metrics for {zooid_name}: ok_rate={z['prod']['ok_rate']:.3f}, ok_rate_window={z['prod'].get('ok_rate_window', 0.0):.3f}, ttr_ms={z['prod']['ttr_ms_mean']:.1f}, evidence={z['prod']['evidence']}")


def process_rows(
    reg: dict,
    rows: List[dict],
    now: float,
    key_path: str,
    ledger_path: str,
    on_event: Optional[Callable[[dict], None]] = None
) -> Dict:
    """
    Process batch of OBSERVATION rows.

    Args:
        reg: Registry dict (mutated in-place)
        rows: List of OBSERVATION dicts
        now: Current timestamp
        key_path: Path to HMAC key
        ledger_path: Path to fitness ledger
        on_event: Optional callback for governance events

    Returns:
        Stats dict with keys: accepted, rejected, backpressure

    Algorithm:
        1. Verify HMAC for each row
        2. Skip future timestamps and malformed rows
        3. Append valid rows to ledger
        4. Update registry metrics
        5. Emit backpressure if queue > threshold
    """
    accepted = 0
    rejected = 0
    backpressure_threshold = 10000

    for row in rows:
        ts = row.get("ts", 0)
        if ts > now + 120:
            logger.warning(f"Skipping future row: ts={ts}, now={now}")
            rejected += 1
            continue

        if not verify_hmac(row, key_path):
            rejected += 1
            continue

        try:
            append_observation_atomic(row, ledger_path)
            update_registry_rolling_metrics(reg, row, now)
            accepted += 1
        except Exception as e:
            logger.error(f"Failed to process row: {e}")
            rejected += 1

    backpressure = len(rows) > backpressure_threshold

    if backpressure and on_event:
        on_event({
            "event": "governance.backpressure",
            "ts": now,
            "queue_depth": len(rows),
            "threshold": backpressure_threshold
        })
        logger.warning(f"Backpressure detected: queue_depth={len(rows)}")

    logger.info(f"Processed batch: accepted={accepted}, rejected={rejected}, backpressure={backpressure}")

    return {
        "accepted": accepted,
        "rejected": rejected,
        "backpressure": backpressure
    }
