"""
Robust timestamp parsing for PHASE adaptive controller.

Handles ISO-8601 timestamps (with/without offsets), epoch numbers, and naive datetimes.
Always returns timezone-aware UTC datetime objects for consistent windowing.
"""
from __future__ import annotations
from datetime import datetime, timezone
from typing import Union
import logging

logger = logging.getLogger(__name__)


def parse_ts_utc(ts: Union[str, int, float]) -> datetime:
    """
    Parse ISO-8601 timestamps (with or without offset) and epoch numbers/strings.
    Returns an **aware** UTC datetime. Never returns naive.

    Accepts:
      - "2025-10-17T12:34:56Z"
      - "2025-10-17T12:34:56+00:00"
      - "2025-10-17 12:34:56"       (assumed UTC, with warning)
      - 1697547296 or "1697547296"  (epoch seconds)
      - 1697547296.123               (epoch float)

    Raises:
      - TypeError: if ts is not str/int/float
      - ValueError: if timestamp cannot be parsed
    """
    # Epoch numbers (int/float or numeric strings)
    if isinstance(ts, (int, float)) or (isinstance(ts, str) and ts.replace('.', '', 1).isdigit()):
        return datetime.fromtimestamp(float(ts), tz=timezone.utc)

    if not isinstance(ts, str):
        raise TypeError(f"Unsupported timestamp type: {type(ts)}")

    s = ts.strip()
    # Normalize trailing 'Z' for fromisoformat
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"

    try:
        dt = datetime.fromisoformat(s)
    except ValueError:
        # Fallback: try replacing space with 'T' and retry
        try:
            s2 = s.replace(" ", "T")
            dt = datetime.fromisoformat(s2)
        except Exception as e:
            raise ValueError(f"Unparseable timestamp: {ts}") from e

    # If naive, assume UTC (safe + consistent with pipeline)
    if dt.tzinfo is None:
        logger.debug(f"Naive timestamp encountered, assuming UTC: {ts}")
        dt = dt.replace(tzinfo=timezone.utc)

    return dt.astimezone(timezone.utc)
