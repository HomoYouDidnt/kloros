#!/usr/bin/env python3
"""
T5 — Central Ledger Writer test

Validates:
1. HMAC verification accepts valid signatures
2. HMAC verification rejects invalid signatures
3. Valid rows appended to ledger atomically
4. Registry production metrics updated (ok_rate, ttr_ms_mean, evidence)
5. Backpressure event emitted when queue > threshold
6. Future timestamps rejected
"""
import hashlib
import hmac
import json
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[2] / "src"))

from kloros.observability.ledger_writer import (
    verify_hmac,
    append_observation_atomic,
    update_registry_rolling_metrics,
    process_rows
)


def compute_hmac_sig(row: dict, key: bytes) -> str:
    """Helper to compute HMAC signature for test rows."""
    canonical = json.dumps(row, sort_keys=True, separators=(',', ':'), ensure_ascii=False)
    canonical_bytes = canonical.encode('utf-8')
    return hmac.new(key, canonical_bytes, hashlib.sha256).hexdigest()


def test_ledger_writer():
    """Test T5: Central ledger writer."""
    print("=" * 60)
    print("T5 — Central Ledger Writer Test")
    print("=" * 60)

    now = time.time()
    events = []

    def capture_event(event):
        events.append(event)

    with tempfile.TemporaryDirectory() as tmpdir:
        tmppath = Path(tmpdir)
        hmac_key_path = tmppath / "hmac.key"
        ledger_path = tmppath / "fitness_ledger.jsonl"

        hmac_key = b"test_hmac_key_32_bytes_long!!!!!"
        hmac_key_path.write_bytes(hmac_key)

        print("\n[1/6] Creating test OBSERVATION rows...")

        valid_row1 = {
            "ts": now - 100,
            "incident_id": "incident_001",
            "zooid": "lat_mon_001",
            "niche": "latency_monitoring",
            "ecosystem": "prod_guard",
            "ok": True,
            "ttr_ms": 250
        }
        valid_row1["sig"] = compute_hmac_sig(valid_row1, hmac_key)

        valid_row2 = {
            "ts": now - 50,
            "incident_id": "incident_002",
            "zooid": "lat_mon_001",
            "niche": "latency_monitoring",
            "ecosystem": "prod_guard",
            "ok": False,
            "ttr_ms": 800
        }
        valid_row2["sig"] = compute_hmac_sig(valid_row2, hmac_key)

        valid_row3 = {
            "ts": now - 30,
            "incident_id": "incident_003",
            "zooid": "lat_mon_002",
            "niche": "latency_monitoring",
            "ecosystem": "prod_guard",
            "ok": True,
            "ttr_ms": 180
        }
        valid_row3["sig"] = compute_hmac_sig(valid_row3, hmac_key)

        bad_sig_row = {
            "ts": now - 20,
            "incident_id": "incident_004",
            "zooid": "lat_mon_001",
            "niche": "latency_monitoring",
            "ecosystem": "prod_guard",
            "ok": True,
            "ttr_ms": 200,
            "sig": "deadbeefdeadbeefdeadbeefdeadbeef"
        }

        future_row = {
            "ts": now + 500,
            "incident_id": "incident_005",
            "zooid": "lat_mon_001",
            "niche": "latency_monitoring",
            "ecosystem": "prod_guard",
            "ok": True,
            "ttr_ms": 300
        }
        future_row["sig"] = compute_hmac_sig(future_row, hmac_key)

        all_rows = [valid_row1, valid_row2, valid_row3, bad_sig_row, future_row]
        print(f"  ✓ Created {len(all_rows)} test rows (3 valid, 1 bad sig, 1 future)")

        print("\n[2/6] Testing HMAC verification...")
        assert verify_hmac(valid_row1, str(hmac_key_path)) is True
        assert verify_hmac(bad_sig_row, str(hmac_key_path)) is False
        print("  ✓ HMAC verification works correctly")

        print("\n[3/6] Creating registry...")
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
                    "ecosystem": "prod_guard"
                },
                "lat_mon_002": {
                    "name": "lat_mon_002",
                    "lifecycle_state": "ACTIVE",
                    "niche": "latency_monitoring",
                    "ecosystem": "prod_guard"
                }
            },
            "genomes": {},
            "version": 1
        }
        print("  ✓ Registry created with 2 ACTIVE zooids")

        print("\n[4/6] Processing rows...")
        stats = process_rows(
            reg,
            all_rows,
            now,
            str(hmac_key_path),
            str(ledger_path),
            on_event=capture_event
        )

        print(f"  Stats: {stats}")
        assert stats["accepted"] == 3, f"Expected 3 accepted, got {stats['accepted']}"
        assert stats["rejected"] == 2, f"Expected 2 rejected, got {stats['rejected']}"
        assert stats["backpressure"] is False
        print("  ✓ Accepted 3 valid rows, rejected 2 invalid rows")

        print("\n[5/6] Verifying ledger contents...")
        assert ledger_path.exists(), "Ledger file should exist"

        with open(ledger_path, 'r') as f:
            ledger_lines = f.readlines()

        assert len(ledger_lines) == 3, f"Expected 3 lines in ledger, got {len(ledger_lines)}"

        ledger_incidents = []
        for line in ledger_lines:
            row = json.loads(line)
            ledger_incidents.append(row["incident_id"])

        assert "incident_001" in ledger_incidents
        assert "incident_002" in ledger_incidents
        assert "incident_003" in ledger_incidents
        assert "incident_004" not in ledger_incidents
        assert "incident_005" not in ledger_incidents
        print("  ✓ Ledger contains exactly the valid rows")

        print("\n[6/6] Verifying registry metrics...")
        z1 = reg["zooids"]["lat_mon_001"]
        assert "prod" in z1
        assert z1["prod"]["evidence"] == 2, f"Expected evidence=2, got {z1['prod']['evidence']}"
        assert 0.0 <= z1["prod"]["ok_rate"] <= 1.0
        assert z1["prod"]["ttr_ms_mean"] > 0
        print(f"  lat_mon_001: ok_rate={z1['prod']['ok_rate']:.3f}, ttr_ms={z1['prod']['ttr_ms_mean']:.1f}, evidence={z1['prod']['evidence']}")

        z2 = reg["zooids"]["lat_mon_002"]
        assert "prod" in z2
        assert z2["prod"]["evidence"] == 1
        assert z2["prod"]["ok_rate"] == 1.0
        print(f"  lat_mon_002: ok_rate={z2['prod']['ok_rate']:.3f}, ttr_ms={z2['prod']['ttr_ms_mean']:.1f}, evidence={z2['prod']['evidence']}")
        print("  ✓ Registry metrics updated correctly")

        print("\n[7/7] Testing backpressure...")
        many_rows = []
        for i in range(15000):
            row = {
                "ts": now - i,
                "incident_id": f"incident_{i}",
                "zooid": "lat_mon_001",
                "niche": "latency_monitoring",
                "ecosystem": "prod_guard",
                "ok": True,
                "ttr_ms": 100
            }
            row["sig"] = compute_hmac_sig(row, hmac_key)
            many_rows.append(row)

        events.clear()
        stats2 = process_rows(
            reg,
            many_rows,
            now,
            str(hmac_key_path),
            str(ledger_path),
            on_event=capture_event
        )

        assert stats2["backpressure"] is True
        assert len(events) >= 1
        bp_event = events[0]
        assert bp_event["event"] == "governance.backpressure"
        assert bp_event["queue_depth"] == 15000
        print(f"  ✓ Backpressure event emitted: queue_depth={bp_event['queue_depth']}")

    print("\n" + "=" * 60)
    print("✅ T5: All tests passed!")
    print("=" * 60)


if __name__ == "__main__":
    test_ledger_writer()
