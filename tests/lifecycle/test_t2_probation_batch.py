#!/usr/bin/env python3
"""
T2 — PROBATION batch transition test

Validates:
1. start_probation() transitions DORMANT → PROBATION
2. phase.batches appended correctly
3. Niche indexes updated
4. State change events emitted
5. Idempotent behavior (skips already-PROBATION)
6. ACTIVE zooids unaffected
"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[2] / "src"))

from kloros.lifecycle.state_machine import start_probation

def test_probation_batch():
    """Test T2: PROBATION batch transitions."""
    print("=" * 60)
    print("T2 — PROBATION Batch Transition Test")
    print("=" * 60)

    now = time.time()
    batch_id = "2025-11-07T03:10Z-LIGHT"
    events = []

    def capture_event(event):
        events.append(event)

    reg = {
        "niches": {
            "latency_monitoring": {
                "active": ["existing_active_001"],
                "dormant": ["lat_mon_001", "lat_mon_002"],
                "probation": [],
                "retired": []
            }
        },
        "zooids": {
            "lat_mon_001": {
                "name": "lat_mon_001",
                "lifecycle_state": "DORMANT",
                "niche": "latency_monitoring",
                "ecosystem": "prod_guard",
                "genome_hash": "sha256:abc123",
                "parent_lineage": [],
                "entered_ts": now - 1000,
                "phase": {"batches": [], "evidence": 0, "fitness_mean": 0.0}
            },
            "lat_mon_002": {
                "name": "lat_mon_002",
                "lifecycle_state": "DORMANT",
                "niche": "latency_monitoring",
                "ecosystem": "prod_guard",
                "genome_hash": "sha256:def456",
                "parent_lineage": [],
                "entered_ts": now - 2000,
                "phase": {"batches": [], "evidence": 0, "fitness_mean": 0.0}
            },
            "existing_active_001": {
                "name": "existing_active_001",
                "lifecycle_state": "ACTIVE",
                "niche": "latency_monitoring",
                "ecosystem": "prod_guard",
                "genome_hash": "sha256:ghi789",
                "parent_lineage": [],
                "entered_ts": now - 10000,
                "promoted_ts": now - 9000
            }
        },
        "genomes": {},
        "version": 1
    }

    print("\n[1/6] Testing DORMANT → PROBATION transition...")
    promoted = start_probation(
        reg,
        ["lat_mon_001", "lat_mon_002"],
        batch_id,
        now,
        on_event=capture_event
    )

    assert len(promoted) == 2, f"Expected 2 promotions, got {len(promoted)}"
    assert "lat_mon_001" in promoted
    assert "lat_mon_002" in promoted
    print(f"  ✓ Promoted {len(promoted)} zooids to PROBATION")

    print("\n[2/6] Testing lifecycle_state updates...")
    assert reg["zooids"]["lat_mon_001"]["lifecycle_state"] == "PROBATION"
    assert reg["zooids"]["lat_mon_002"]["lifecycle_state"] == "PROBATION"
    assert reg["zooids"]["existing_active_001"]["lifecycle_state"] == "ACTIVE"
    print("  ✓ Lifecycle states updated correctly")

    print("\n[3/6] Testing phase.batches appended...")
    assert batch_id in reg["zooids"]["lat_mon_001"]["phase"]["batches"]
    assert batch_id in reg["zooids"]["lat_mon_002"]["phase"]["batches"]
    assert len(reg["zooids"]["lat_mon_001"]["phase"]["batches"]) == 1
    print(f"  ✓ Batch ID '{batch_id}' appended to phase.batches")

    print("\n[4/6] Testing niche index updates...")
    niche = reg["niches"]["latency_monitoring"]
    assert len(niche["dormant"]) == 0, f"dormant should be empty, got {niche['dormant']}"
    assert len(niche["probation"]) == 2, f"probation should have 2 zooids, got {niche['probation']}"
    assert "lat_mon_001" in niche["probation"]
    assert "lat_mon_002" in niche["probation"]
    assert len(niche["active"]) == 1, f"active should still have 1 zooid, got {niche['active']}"
    print("  ✓ Niche indexes updated (dormant → probation)")

    print("\n[5/6] Testing state change events...")
    assert len(events) == 2, f"Expected 2 events, got {len(events)}"

    for event in events:
        assert event["event"] == "zooid_state_change"
        assert event["from"] == "DORMANT"
        assert event["to"] == "PROBATION"
        assert event["reason"] == f"phase_batch:{batch_id}"
        assert event["service_action"] == "noop"
        assert "genome_hash" in event

    print(f"  ✓ Emitted {len(events)} state change events")

    print("\n[6/6] Testing idempotency (re-run on same zooids)...")
    events.clear()
    promoted2 = start_probation(
        reg,
        ["lat_mon_001", "lat_mon_002"],
        batch_id,
        now + 100,
        on_event=capture_event
    )

    assert len(promoted2) == 0, f"Expected 0 promotions (already PROBATION), got {len(promoted2)}"
    assert len(events) == 0, f"Expected 0 events (idempotent), got {len(events)}"
    assert len(reg["zooids"]["lat_mon_001"]["phase"]["batches"]) == 1, "Should not duplicate batch_id"
    print("  ✓ Idempotent: skipped already-PROBATION zooids")

    print("\n" + "=" * 60)
    print("✅ T2: All tests passed!")
    print("=" * 60)

if __name__ == "__main__":
    test_probation_batch()
