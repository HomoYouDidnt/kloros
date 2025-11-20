#!/usr/bin/env python3
"""
T3 — Graduation gate test

Validates:
1. PROBATION zooids evaluated against PHASE fitness
2. Gates enforced: fitness >= threshold AND evidence >= minimum
3. Service start and heartbeat verification
4. Rollback on heartbeat failure
5. Events emitted with fitness breakdown
"""
import json
import sys
import time
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[2] / "src"))

from kloros.phase.graduator import run_graduations


def test_graduation():
    """Test T3: Graduation gates with PHASE fitness."""
    print("=" * 60)
    print("T3 — Graduation Gate Test")
    print("=" * 60)

    now = time.time()
    events = []
    service_calls = []
    heartbeat_calls = []

    def mock_start_service(name):
        service_calls.append(name)
        print(f"  [MOCK] start_service({name})")

    def mock_wait_for_heartbeat(name, timeout_sec):
        heartbeat_calls.append((name, timeout_sec))
        print(f"  [MOCK] wait_for_heartbeat({name}, {timeout_sec})")
        if name == "probe_ok":
            return True
        elif name == "probe_rollback":
            return False
        return False

    def capture_event(event):
        events.append(event)

    with tempfile.TemporaryDirectory() as tmpdir:
        tmppath = Path(tmpdir)
        phase_fitness_path = tmppath / "phase_fitness.jsonl"

        print("\n[1/8] Creating mock PHASE fitness data...")

        with open(phase_fitness_path, 'w') as f:
            for i in range(60):
                row = {
                    "candidate": "probe_ok",
                    "ts": now - (7200 - i * 120),
                    "composite_phase_fitness": 0.82 + (i % 10) * 0.01
                }
                f.write(json.dumps(row) + "\n")

            for i in range(20):
                row = {
                    "candidate": "probe_low",
                    "ts": now - (7200 - i * 360),
                    "composite_phase_fitness": 0.65 + (i % 5) * 0.01
                }
                f.write(json.dumps(row) + "\n")

            for i in range(55):
                row = {
                    "candidate": "probe_rollback",
                    "ts": now - (7200 - i * 130),
                    "composite_phase_fitness": 0.85 + (i % 8) * 0.005
                }
                f.write(json.dumps(row) + "\n")

        print(f"  ✓ Created {phase_fitness_path}")

        import kloros.phase.graduator as graduator_module
        original_path = graduator_module.DEFAULT_PHASE_FITNESS_PATH
        graduator_module.DEFAULT_PHASE_FITNESS_PATH = phase_fitness_path

        print("\n[2/8] Creating registry with PROBATION zooids...")
        reg = {
            "niches": {
                "latency_monitoring": {
                    "active": [],
                    "probation": ["probe_ok", "probe_low", "probe_rollback"],
                    "dormant": [],
                    "retired": []
                }
            },
            "zooids": {
                "probe_ok": {
                    "name": "probe_ok",
                    "lifecycle_state": "PROBATION",
                    "niche": "latency_monitoring",
                    "ecosystem": "prod_guard",
                    "genome_hash": "sha256:abc123",
                    "parent_lineage": [],
                    "entered_ts": now - 10000,
                    "phase": {"batches": ["2025-11-07T03:10Z-LIGHT"], "evidence": 0, "fitness_mean": 0.0}
                },
                "probe_low": {
                    "name": "probe_low",
                    "lifecycle_state": "PROBATION",
                    "niche": "latency_monitoring",
                    "ecosystem": "prod_guard",
                    "genome_hash": "sha256:def456",
                    "parent_lineage": [],
                    "entered_ts": now - 10000,
                    "phase": {"batches": ["2025-11-07T03:10Z-LIGHT"], "evidence": 0, "fitness_mean": 0.0}
                },
                "probe_rollback": {
                    "name": "probe_rollback",
                    "lifecycle_state": "PROBATION",
                    "niche": "latency_monitoring",
                    "ecosystem": "prod_guard",
                    "genome_hash": "sha256:ghi789",
                    "parent_lineage": [],
                    "entered_ts": now - 10000,
                    "phase": {"batches": ["2025-11-07T03:10Z-HEAVY"], "evidence": 0, "fitness_mean": 0.0}
                }
            },
            "genomes": {},
            "version": 1
        }
        print("  ✓ Registry created with 3 PROBATION zooids")

        print("\n[3/8] Running graduations...")
        promoted = run_graduations(
            reg,
            now,
            start_service=mock_start_service,
            wait_for_heartbeat=mock_wait_for_heartbeat,
            on_event=capture_event
        )

        print(f"\n  Promoted: {promoted}")
        print(f"  Service calls: {service_calls}")
        print(f"  Heartbeat calls: {heartbeat_calls}")
        print(f"  Events: {len(events)}")

        print("\n[4/8] Testing probe_ok (passes gates, heartbeat OK)...")
        assert "probe_ok" in promoted, "probe_ok should be promoted"
        assert reg["zooids"]["probe_ok"]["lifecycle_state"] == "ACTIVE"
        assert "probe_ok" in reg["niches"]["latency_monitoring"]["active"]
        assert "probe_ok" not in reg["niches"]["latency_monitoring"]["probation"]
        assert "probe_ok" in service_calls
        assert any(name == "probe_ok" for name, _ in heartbeat_calls)
        print("  ✓ probe_ok promoted to ACTIVE")

        probe_ok_events = [e for e in events if e["zooid"] == "probe_ok" and e["to"] == "ACTIVE"]
        assert len(probe_ok_events) >= 1
        evt = probe_ok_events[0]
        assert evt["reason"] == "phase_graduation"
        assert evt["phase_fit"] >= 0.70, f"Expected phase_fit >= 0.70, got {evt['phase_fit']}"
        assert evt["phase_ev"] >= 50, f"Expected phase_ev >= 50, got {evt['phase_ev']}"
        assert evt["service_action"] == "systemd_start"
        print(f"  ✓ Event emitted: fit={evt['phase_fit']:.3f}, ev={evt['phase_ev']}")

        print("\n[5/8] Testing probe_low (fails gates, not promoted)...")
        assert "probe_low" not in promoted, "probe_low should NOT be promoted"
        assert reg["zooids"]["probe_low"]["lifecycle_state"] == "PROBATION"
        assert "probe_low" not in reg["niches"]["latency_monitoring"]["active"]
        assert "probe_low" in reg["niches"]["latency_monitoring"]["probation"]
        assert "probe_low" not in service_calls
        print("  ✓ probe_low remains in PROBATION")

        print("\n[6/8] Testing probe_rollback (passes gates but heartbeat fails)...")
        assert "probe_rollback" not in promoted, "probe_rollback should be rolled back"
        assert reg["zooids"]["probe_rollback"]["lifecycle_state"] == "DORMANT"
        assert "probe_rollback" not in reg["niches"]["latency_monitoring"]["active"]
        assert "probe_rollback" not in reg["niches"]["latency_monitoring"]["probation"]
        assert "probe_rollback" in reg["niches"]["latency_monitoring"]["dormant"]
        assert "probe_rollback" in service_calls
        assert any(name == "probe_rollback" for name, _ in heartbeat_calls)
        print("  ✓ probe_rollback rolled back to DORMANT")

        print("\n[7/8] Testing rollback events...")
        rollback_promotion_events = [
            e for e in events
            if e["zooid"] == "probe_rollback" and e["from"] == "PROBATION" and e["to"] == "ACTIVE"
        ]
        rollback_demotion_events = [
            e for e in events
            if e["zooid"] == "probe_rollback" and e["from"] == "ACTIVE" and e["to"] == "DORMANT"
        ]

        assert len(rollback_promotion_events) >= 1, "Should have promotion event for probe_rollback"
        assert len(rollback_demotion_events) >= 1, "Should have rollback event for probe_rollback"

        rollback_evt = rollback_demotion_events[0]
        assert rollback_evt["reason"] == "rollback_no_heartbeat"
        assert rollback_evt["service_action"] == "systemd_stop"
        print("  ✓ Rollback events: promotion → demotion with reason=rollback_no_heartbeat")

        print("\n[8/8] Testing PHASE fitness updates...")
        assert reg["zooids"]["probe_ok"]["phase"]["fitness_mean"] >= 0.70
        assert reg["zooids"]["probe_ok"]["phase"]["evidence"] >= 50
        assert reg["zooids"]["probe_low"]["phase"]["fitness_mean"] < 0.70 or \
               reg["zooids"]["probe_low"]["phase"]["evidence"] < 50
        print("  ✓ PHASE fitness aggregated with EWMA")

        graduator_module.DEFAULT_PHASE_FITNESS_PATH = original_path

    print("\n" + "=" * 60)
    print("✅ T3: All tests passed!")
    print("=" * 60)


if __name__ == "__main__":
    test_graduation()
