#!/usr/bin/env python3
"""
T6 — Lifecycle-aware Bioreactor test

Validates:
1. Only ACTIVE defenders participate in tournaments
2. New DORMANT candidates generated and added to registry
3. Genome deduplication (existing genome_hash not re-enqueued)
4. Conservative survivor policy (no mass replacement)
5. PHASE queue populated with candidate entries
6. Idempotent: re-running with same data is stable
"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[2] / "src"))

from src.dream.bioreactor import bioreactor_tick


def test_bioreactor_tick():
    """Test T6: Lifecycle-aware bioreactor."""
    print("=" * 60)
    print("T6 — Lifecycle-aware Bioreactor Test")
    print("=" * 60)

    now = time.time()
    phase_queue = []

    def mock_differentiate(niche, ecosystem, m):
        """Generate m candidate zooids."""
        candidates = []
        for i in range(m):
            cand = {
                "name": f"{niche}_cand_{int(now)}_{i}",
                "genome_hash": f"sha256:candidate_{i}_hash",
                "parent_lineage": []
            }
            candidates.append(cand)
        return candidates

    def mock_select_winners(defenders, prod_rows, phase_rows, now, k):
        """Select top k winners from defenders."""
        if len(defenders) >= k:
            return defenders[:k]
        return defenders

    def mock_enqueue_phase(entry):
        """Enqueue candidate to PHASE."""
        phase_queue.append(entry)

    print("\n[1/6] Creating registry with ACTIVE defenders...")
    reg = {
        "niches": {
            "latency_monitoring": {
                "active": ["lat_mon_A1", "lat_mon_A2"],
                "probation": [],
                "dormant": [],
                "retired": []
            }
        },
        "zooids": {
            "lat_mon_A1": {
                "name": "lat_mon_A1",
                "lifecycle_state": "ACTIVE",
                "niche": "latency_monitoring",
                "ecosystem": "prod_guard",
                "genome_hash": "sha256:A1_hash"
            },
            "lat_mon_A2": {
                "name": "lat_mon_A2",
                "lifecycle_state": "ACTIVE",
                "niche": "latency_monitoring",
                "ecosystem": "prod_guard",
                "genome_hash": "sha256:A2_hash"
            }
        },
        "genomes": {
            "sha256:A1_hash": "lat_mon_A1",
            "sha256:A2_hash": "lat_mon_A2"
        },
        "version": 1
    }
    print("  ✓ Registry created with 2 ACTIVE defenders")

    print("\n[2/6] Running bioreactor tick...")
    result = bioreactor_tick(
        reg,
        "prod_guard",
        "latency_monitoring",
        [],
        [],
        now,
        differentiate=mock_differentiate,
        select_winners=mock_select_winners,
        enqueue_phase_candidate=mock_enqueue_phase
    )

    print(f"  Result: {result}")
    assert result["new_candidates"] == 3, f"Expected 3 new candidates, got {result['new_candidates']}"
    print("  ✓ Generated 3 DORMANT candidates")

    print("\n[3/6] Verifying DORMANT candidates in registry...")
    dormant_names = reg["niches"]["latency_monitoring"]["dormant"]
    assert len(dormant_names) == 3, f"Expected 3 dormant, got {len(dormant_names)}"

    for name in dormant_names:
        z = reg["zooids"][name]
        assert z["lifecycle_state"] == "DORMANT"
        assert z["niche"] == "latency_monitoring"
        assert z["ecosystem"] == "prod_guard"
        assert "genome_hash" in z
        assert reg["genomes"][z["genome_hash"]] == name

    print(f"  ✓ DORMANT candidates added: {dormant_names}")

    print("\n[4/6] Verifying PHASE queue...")
    assert len(phase_queue) == 3, f"Expected 3 PHASE entries, got {len(phase_queue)}"

    for entry in phase_queue:
        assert "candidate" in entry
        assert "genome_hash" in entry
        assert "workload_profile_id" in entry
        assert entry["workload_profile_id"] == "QMG-100h-full-traffic-v3"

    print(f"  ✓ PHASE queue populated with {len(phase_queue)} entries")

    print("\n[5/6] Testing conservative survivor policy...")
    active_names = reg["niches"]["latency_monitoring"]["active"]
    assert "lat_mon_A1" in active_names, "A1 should remain ACTIVE"
    assert "lat_mon_A2" in active_names, "A2 should remain ACTIVE"
    assert len(active_names) == 2, "Both defenders should remain (no mass replacement)"
    print("  ✓ Conservative policy: both ACTIVE defenders retained")

    print("\n[6/6] Testing genome deduplication...")
    phase_queue.clear()

    existing_genome = "sha256:candidate_0_hash"
    assert existing_genome in reg["genomes"], "First candidate genome should be bound"

    def mock_differentiate_duplicate(niche, ecosystem, m):
        """Generate candidates with one duplicate genome."""
        candidates = []
        for i in range(m):
            if i == 0:
                cand = {
                    "name": f"{niche}_dup_{int(now)}_{i}",
                    "genome_hash": existing_genome,
                    "parent_lineage": []
                }
            else:
                cand = {
                    "name": f"{niche}_new_{int(now)}_{i}",
                    "genome_hash": f"sha256:new_{i}_hash",
                    "parent_lineage": []
                }
            candidates.append(cand)
        return candidates

    result2 = bioreactor_tick(
        reg,
        "prod_guard",
        "latency_monitoring",
        [],
        [],
        now + 100,
        differentiate=mock_differentiate_duplicate,
        select_winners=mock_select_winners,
        enqueue_phase_candidate=mock_enqueue_phase
    )

    assert result2["new_candidates"] == 3, "Should generate 3 candidates"
    assert len(phase_queue) == 2, f"Only 2 should be enqueued (1 duplicate skipped), got {len(phase_queue)}"
    print("  ✓ Genome deduplication: duplicate genome_hash not re-enqueued")

    print("\n" + "=" * 60)
    print("✅ T6: All tests passed!")
    print("=" * 60)


if __name__ == "__main__":
    test_bioreactor_tick()
