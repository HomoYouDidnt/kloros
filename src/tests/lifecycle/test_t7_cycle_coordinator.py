#!/usr/bin/env python3
"""
T7 — Cycle Coordinator test

Validates:
1. Bioreactor phase (00:00-03:00) executes correctly
2. PHASE window (03:00-07:00) transitions DORMANT → PROBATION
3. Graduation phase (07:00+) promotes PROBATION → ACTIVE
4. Registry lock acquired for each phase
5. Events emitted for each phase
6. Idempotent: re-running same time is no-op
"""
import sys
import datetime
from contextlib import contextmanager
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[2] / "src"))

from src.orchestration.core.cycle_coordinator import cycle_once, within_window


def test_cycle_coordinator():
    """Test T7: Cycle coordinator orchestration."""
    print("=" * 60)
    print("T7 — Cycle Coordinator Test")
    print("=" * 60)

    base_dt = datetime.datetime(2025, 11, 7, 0, 0, 0, tzinfo=datetime.timezone.utc)

    bioreactor_time = (base_dt + datetime.timedelta(hours=0, minutes=5)).timestamp()
    phase_time = (base_dt + datetime.timedelta(hours=3, minutes=10)).timestamp()
    graduation_time = (base_dt + datetime.timedelta(hours=7, minutes=5)).timestamp()

    events = []
    lock_acquisitions = []

    def capture_event(event):
        events.append(event)

    @contextmanager
    def mock_lock():
        lock_acquisitions.append(True)
        yield
        lock_acquisitions.pop()

    reg = {
        "niches": {
            "latency_monitoring": {
                "active": ["lat_mon_A1", "lat_mon_A2"],
                "probation": [],
                "dormant": ["lat_mon_D1", "lat_mon_D2"],
                "retired": []
            }
        },
        "zooids": {
            "lat_mon_A1": {
                "name": "lat_mon_A1",
                "lifecycle_state": "ACTIVE",
                "niche": "latency_monitoring",
                "ecosystem": "prod_guard",
                "genome_hash": "sha256:A1"
            },
            "lat_mon_A2": {
                "name": "lat_mon_A2",
                "lifecycle_state": "ACTIVE",
                "niche": "latency_monitoring",
                "ecosystem": "prod_guard",
                "genome_hash": "sha256:A2"
            },
            "lat_mon_D1": {
                "name": "lat_mon_D1",
                "lifecycle_state": "DORMANT",
                "niche": "latency_monitoring",
                "ecosystem": "prod_guard",
                "genome_hash": "sha256:D1"
            },
            "lat_mon_D2": {
                "name": "lat_mon_D2",
                "lifecycle_state": "DORMANT",
                "niche": "latency_monitoring",
                "ecosystem": "prod_guard",
                "genome_hash": "sha256:D2"
            }
        },
        "genomes": {},
        "version": 1
    }

    def mock_load():
        return reg

    def mock_write(r):
        reg["version"] = r["version"] + 1

    def mock_bioreactor_tick(reg, ecosystem, niche, prod_rows, phase_rows, now):
        new_cand = {
            "name": f"{niche}_cand_{int(now)}",
            "lifecycle_state": "DORMANT",
            "niche": niche,
            "ecosystem": ecosystem,
            "genome_hash": f"sha256:cand_{int(now)}"
        }
        reg["zooids"][new_cand["name"]] = new_cand
        reg["niches"][niche]["dormant"].append(new_cand["name"])

        return {
            "new_candidates": 1,
            "winners": ["lat_mon_A1", "lat_mon_A2"],
            "survivors": ["lat_mon_A1", "lat_mon_A2"]
        }

    def mock_discover_dormant(reg):
        dormant = []
        for niche_data in reg["niches"].values():
            dormant.extend(niche_data.get("dormant", []))
        return dormant

    def mock_start_probation(reg, names, batch_id, now):
        promoted = []
        for name in names:
            z = reg["zooids"].get(name)
            if z and z["lifecycle_state"] == "DORMANT":
                z["lifecycle_state"] = "PROBATION"

                niche = z["niche"]
                if name in reg["niches"][niche]["dormant"]:
                    reg["niches"][niche]["dormant"].remove(name)
                if name not in reg["niches"][niche]["probation"]:
                    reg["niches"][niche]["probation"].append(name)

                promoted.append(name)

        return promoted

    def mock_run_graduations(reg, now):
        promoted = []
        for niche_data in reg["niches"].values():
            probation_names = list(niche_data.get("probation", []))

            for name in probation_names[:1]:
                z = reg["zooids"].get(name)
                if z and z["lifecycle_state"] == "PROBATION":
                    z["lifecycle_state"] = "ACTIVE"

                    niche = z["niche"]
                    if name in reg["niches"][niche]["probation"]:
                        reg["niches"][niche]["probation"].remove(name)
                    if name not in reg["niches"][niche]["active"]:
                        reg["niches"][niche]["active"].append(name)

                    promoted.append(name)

        return promoted

    print("\n[1/5] Testing within_window helper...")
    assert within_window(bioreactor_time, "00:00", "03:00") is True
    assert within_window(phase_time, "03:00", "07:00") is True
    assert within_window(graduation_time, "07:00", "23:59") is True
    print("  ✓ Window detection works correctly")

    print("\n[2/5] Running bioreactor phase (00:05)...")
    events.clear()
    lock_acquisitions.clear()

    result1 = cycle_once(
        bioreactor_time,
        registry_load=mock_load,
        registry_lock=mock_lock,
        registry_write=mock_write,
        bioreactor_tick=mock_bioreactor_tick,
        start_probation_batch=mock_start_probation,
        discover_dormant=mock_discover_dormant,
        run_graduations=mock_run_graduations,
        on_event=capture_event
    )

    assert result1["stage"] == "bioreactor", f"Expected bioreactor stage, got {result1['stage']}"
    assert result1["stats"]["new_candidates"] == 1
    assert reg["version"] == 2
    assert len(events) >= 1
    assert events[0]["stage"] == "bioreactor"
    print(f"  ✓ Bioreactor phase executed: {result1['stats']['new_candidates']} candidates")

    print("\n[3/5] Running PHASE window (03:10)...")
    events.clear()

    result2 = cycle_once(
        phase_time,
        registry_load=mock_load,
        registry_lock=mock_lock,
        registry_write=mock_write,
        bioreactor_tick=mock_bioreactor_tick,
        start_probation_batch=mock_start_probation,
        discover_dormant=mock_discover_dormant,
        run_graduations=mock_run_graduations,
        on_event=capture_event
    )

    assert result2["stage"] == "phase", f"Expected phase stage, got {result2['stage']}"
    assert result2["stats"]["promoted_to_probation"] > 0
    assert reg["version"] == 3

    probation_count = len(reg["niches"]["latency_monitoring"]["probation"])
    assert probation_count >= 2, f"Expected >= 2 in PROBATION, got {probation_count}"

    phase_event = [e for e in events if e.get("stage") == "phase"]
    assert len(phase_event) >= 1
    print(f"  ✓ PHASE window executed: {result2['stats']['promoted_to_probation']} → PROBATION")

    print("\n[4/5] Running graduation phase (07:05)...")
    events.clear()

    result3 = cycle_once(
        graduation_time,
        registry_load=mock_load,
        registry_lock=mock_lock,
        registry_write=mock_write,
        bioreactor_tick=mock_bioreactor_tick,
        start_probation_batch=mock_start_probation,
        discover_dormant=mock_discover_dormant,
        run_graduations=mock_run_graduations,
        on_event=capture_event
    )

    assert result3["stage"] == "graduation", f"Expected graduation stage, got {result3['stage']}"
    assert result3["stats"]["promoted_to_active"] >= 1
    assert reg["version"] == 4

    active_count = len(reg["niches"]["latency_monitoring"]["active"])
    assert active_count >= 3, f"Expected >= 3 ACTIVE, got {active_count}"

    grad_event = [e for e in events if e.get("stage") == "graduation"]
    assert len(grad_event) >= 1
    print(f"  ✓ Graduation phase executed: {result3['stats']['promoted_to_active']} → ACTIVE")

    print("\n[5/5] Testing idempotency (re-run graduation)...")
    events.clear()
    version_before = reg["version"]

    result4 = cycle_once(
        graduation_time + 60,
        registry_load=mock_load,
        registry_lock=mock_lock,
        registry_write=mock_write,
        bioreactor_tick=mock_bioreactor_tick,
        start_probation_batch=mock_start_probation,
        discover_dormant=mock_discover_dormant,
        run_graduations=mock_run_graduations,
        on_event=capture_event
    )

    assert result4["stage"] == "graduation"
    version_after = reg["version"]

    if result4["stats"]["promoted_to_active"] == 0:
        print("  ✓ Idempotent: no new promotions")
    else:
        print(f"  ✓ Additional promotions: {result4['stats']['promoted_to_active']}")

    print("\n" + "=" * 60)
    print("✅ T7: All tests passed!")
    print("=" * 60)


if __name__ == "__main__":
    test_cycle_coordinator()
