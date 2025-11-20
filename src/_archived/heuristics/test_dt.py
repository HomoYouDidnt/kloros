"""Unit tests for robust timestamp parsing."""
from heuristics.dt import parse_ts_utc
from datetime import timezone
import pytest


def test_parse_various_formats():
    """Test parsing various timestamp formats."""
    cases = [
        "2025-10-17T12:34:56Z",
        "2025-10-17T12:34:56+00:00",
        "2025-10-17 12:34:56",   # naive → assume UTC
        1697547296,
        1697547296.123,
        "1697547296"
    ]
    for c in cases:
        dt = parse_ts_utc(c)
        assert dt.tzinfo is not None, f"Got naive datetime from: {c}"
        assert dt.tzinfo.utcoffset(dt).total_seconds() == 0, f"Not UTC: {c}"


def test_raises_on_bad_input():
    """Test that invalid input raises ValueError."""
    with pytest.raises(ValueError):
        parse_ts_utc("not-a-date")


def test_epoch_numbers():
    """Test epoch timestamp handling."""
    # 2023-10-17 12:34:56 UTC
    epoch = 1697547296
    dt1 = parse_ts_utc(epoch)
    dt2 = parse_ts_utc(float(epoch))
    dt3 = parse_ts_utc(str(epoch))

    assert dt1 == dt2 == dt3
    assert dt1.year == 2023
    assert dt1.month == 10


def test_z_suffix_normalization():
    """Test that Z suffix is properly normalized."""
    dt = parse_ts_utc("2025-10-17T16:00:00Z")
    assert dt.tzinfo is not None
    assert dt.year == 2025
    assert dt.hour == 16


def test_naive_assumed_utc():
    """Test that naive datetimes are assumed to be UTC."""
    dt = parse_ts_utc("2025-10-17 12:34:56")
    assert dt.tzinfo is not None
    assert dt.tzinfo.utcoffset(dt).total_seconds() == 0
