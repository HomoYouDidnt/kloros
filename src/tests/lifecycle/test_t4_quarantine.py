#!/usr/bin/env python3
"""
T4 — Quarantine flow test

Validates:
1. ACTIVE zooids demoted on N failures in M seconds
2. Exponential backoff cooldown enforced
3. Demotion ceiling triggers retirement
4. Services stopped on demotion
5. Events emitted with failure provenance
6. Idempotency (cooldown prevents re-demotion)
"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[2] / "src"))

from src.observability.metrics.quarantine_monitor import check_quarantine


def test_quarantine():
    """Test T4: Quarantine flow with failure bursts."""
    print("=" * 60)
    print("T4 — Quarantine Flow Test")
    print("=" * 60)

    now = time.time()
    events = []
    service_stop_calls = []

    def mock_stop_service(name):
        service_stop_calls.append(name)
        print(f"  [MOCK] stop_service({name})")

    def capture_event(event):
        events.append(event)

    print("\n[1/7] Creating registry with ACTIVE zooids...")
    reg = {
        "niches": {
            "latency_monitoring": {
                "active": ["lat_mon_001", "lat_mon_002"],
                "probation": [],
                "dormant": [],
                "retired": []
            }
        },
        "zooids": {
            "lat_mon_001": {
                "name": "lat_mon_001",
                "lifecycle_state": "ACTIVE",
                "niche": "latency_monitoring",
                "ecosystem": "prod_guard",
                "genome_hash": "sha256:abc123",
                "parent_lineage": [],
                "entered_ts": now - 10000,
                "promoted_ts": now - 9000,
                "demotions": 0
            },
            "lat_mon_002": {
                "name": "lat_mon_002",
                "lifecycle_state": "ACTIVE",
                "niche": "latency_monitoring",
                "ecosystem": "prod_guard",
                "genome_hash": "sha256:def456",
                "parent_lineage": [],
                "entered_ts": now - 8000,
                "promoted_ts": now - 7000,
                "demotions": 0
            }
        },
        "genomes": {},
        "version": 1
    }
    print("  ✓ Registry created with 2 ACTIVE zooids")

    print("\n[2/7] Creating failure burst rows (3 failures for lat_mon_001)...")
    rows = [
        {"zooid": "lat_mon_001", "ts": now - 600, "ok": False},
        {"zooid": "lat_mon_001", "ts": now - 450, "ok": False},
        {"zooid": "lat_mon_001", "ts": now - 300, "ok": True},
        {"zooid": "lat_mon_001", "ts": now - 150, "ok": False},
        {"zooid": "lat_mon_002", "ts": now - 500, "ok": True},
        {"zooid": "lat_mon_002", "ts": now - 400, "ok": True},
        {"zooid": "lat_mon_002", "ts": now - 200, "ok": False},
        {"zooid": "lat_mon_001", "ts": now - 2000, "ok": False},
    ]
    print(f"  ✓ Created {len(rows)} OBSERVATION rows")

    print("\n[3/7] Running quarantine check (n_failures=3, window=900s)...")
    demoted = check_quarantine(
        reg,
        rows,
        now,
        n_failures=3,
        window_sec=900,
        on_stop_service=mock_stop_service,
        on_event=capture_event
    )

    print(f"  Demoted: {demoted}")
    print(f"  Service stops: {service_stop_calls}")
    print(f"  Events: {len(events)}")

    print("\n[4/7] Testing lat_mon_001 demotion...")
    assert "lat_mon_001" in demoted, "lat_mon_001 should be demoted"
    assert reg["zooids"]["lat_mon_001"]["lifecycle_state"] == "DORMANT"
    assert "lat_mon_001" not in reg["niches"]["latency_monitoring"]["active"]
    assert "lat_mon_001" in reg["niches"]["latency_monitoring"]["dormant"]
    assert reg["zooids"]["lat_mon_001"]["demotions"] == 1
    assert "lat_mon_001" in service_stop_calls
    print("  ✓ lat_mon_001 demoted to DORMANT")

    demot_events = [e for e in events if e["zooid"] == "lat_mon_001" and e["reason"] == "prod_guard_trip"]
    assert len(demot_events) >= 1
    evt = demot_events[0]
    assert evt["failures_in_window"] == 3
    assert evt["window_sec"] == 900
    assert evt["demotions"] == 1
    assert evt["service_action"] == "systemd_stop"
    assert "cooldown_until_ts" in evt
    print(f"  ✓ Event emitted with failures=3, cooldown={evt['cooldown_until_ts'] - now:.0f}s")

    print("\n[5/7] Testing lat_mon_002 (2 failures, no demotion)...")
    assert "lat_mon_002" not in demoted
    assert reg["zooids"]["lat_mon_002"]["lifecycle_state"] == "ACTIVE"
    assert "lat_mon_002" in reg["niches"]["latency_monitoring"]["active"]
    print("  ✓ lat_mon_002 remains ACTIVE (insufficient failures)")

    print("\n[6/7] Testing idempotency (re-run with same rows)...")
    events.clear()
    service_stop_calls.clear()

    demoted2 = check_quarantine(
        reg,
        rows,
        now + 10,
        n_failures=3,
        window_sec=900,
        on_stop_service=mock_stop_service,
        on_event=capture_event
    )

    assert len(demoted2) == 0, "Should not demote again (cooldown active)"
    assert len(service_stop_calls) == 0, "Should not stop service again"
    print("  ✓ Idempotent: cooldown prevents re-demotion")

    print("\n[7/7] Testing demotion ceiling → retirement...")
    reg["zooids"]["lat_mon_001"]["lifecycle_state"] = "ACTIVE"
    reg["zooids"]["lat_mon_001"]["demotions"] = 1
    reg["niches"]["latency_monitoring"]["active"].append("lat_mon_001")
    reg["niches"]["latency_monitoring"]["dormant"].remove("lat_mon_001")

    cooldown_past = now - 100
    reg["zooids"]["lat_mon_001"]["policy"] = {"cooldown_until_ts": cooldown_past}

    more_failures = [
        {"zooid": "lat_mon_001", "ts": now + 100, "ok": False},
        {"zooid": "lat_mon_001", "ts": now + 150, "ok": False},
        {"zooid": "lat_mon_001", "ts": now + 200, "ok": False},
    ]

    events.clear()
    service_stop_calls.clear()

    demoted3 = check_quarantine(
        reg,
        more_failures,
        now + 300,
        n_failures=3,
        window_sec=900,
        on_stop_service=mock_stop_service,
        on_event=capture_event
    )

    assert "lat_mon_001" in demoted3
    assert reg["zooids"]["lat_mon_001"]["lifecycle_state"] == "RETIRED"
    assert "lat_mon_001" in reg["niches"]["latency_monitoring"]["retired"]
    assert reg["zooids"]["lat_mon_001"]["demotions"] == 2

    retirement_events = [e for e in events if e["zooid"] == "lat_mon_001" and e["to"] == "RETIRED"]
    assert len(retirement_events) >= 1
    ret_evt = retirement_events[0]
    assert ret_evt["reason"] == "demotion_ceiling"
    print(f"  ✓ Demotion ceiling reached: lat_mon_001 retired (demotions=2 >= 2)")

    print("\n" + "=" * 60)
    print("✅ T4: All tests passed!")
    print("=" * 60)


if __name__ == "__main__":
    test_quarantine()
