#!/usr/bin/env python3
"""
SPICA tournament admission logic.

Handles winner selection, bundle creation, and KLoROS admission
for SPICA tournament cycles.
"""

import json, os, sys, hmac, hashlib, shutil
from pathlib import Path

# SPICA/PHASE integration constants
SPICA_INSTANCES_ROOT = Path("/home/kloros/experiments/spica/instances")
HMAC_KEY_ENV = "DREAM_PROMOTION_HMAC_KEY"


def choose_winner(tournament: dict) -> str:
    """
    Select tournament winner from PHASE results.

    Policy: maximize exact_match_mean, tie-break by min latency_p50_ms.
    For integrity-only tournaments, use integrity_verified ratio.

    Args:
        tournament: PHASE tournament results dict

    Returns:
        spica_id of winning instance

    Raises:
        RuntimeError: If no winner can be determined
    """
    # Check if we have per-instance metrics (real PHASE) or integrity-only
    instances_data = tournament.get("instances", [])

    if instances_data and isinstance(instances_data[0], dict) and "metrics_aggregate" in instances_data[0]:
        # Real PHASE with per-instance metrics
        best_id, best_score, best_lat = None, -1.0, 1e12
        for item in instances_data:
            m = item["metrics_aggregate"]
            em = float(m.get("exact_match_mean", 0.0))
            lat = float(m.get("latency_p50_ms", 1e12))
            if em > best_score or (em == best_score and lat < best_lat):
                best_id, best_score, best_lat = item["spica_id"], em, lat
    else:
        # Integrity-only mode: pick first verified instance
        results = tournament.get("results", {}).get("results", [])
        for r in results:
            if r.get("status") == "integrity_verified":
                # Extract actual spica_id from metrics (not full path)
                best_id = r.get("metrics", {}).get("spica_id")
                if best_id:
                    break
        else:
            best_id = None

    if not best_id:
        raise RuntimeError("No winner found in tournament - all instances failed integrity checks")

    return best_id


def _find_instance_root(spica_id: str, root: Path = SPICA_INSTANCES_ROOT) -> Path:
    """Find instance directory by spica_id."""
    for candidate_dir in root.iterdir():
        if not candidate_dir.is_dir():
            continue
        manifest_path = candidate_dir / "manifest.json"
        if manifest_path.exists():
            manifest = json.loads(manifest_path.read_text())
            if manifest.get("spica_id") == spica_id:
                return candidate_dir
    raise FileNotFoundError(f"Instance for {spica_id} not found in {root}")


def _hmac_sign_dir(dir_path: Path, key: bytes) -> str:
    """
    Compute HMAC signature over all files in directory (sorted).

    Args:
        dir_path: Directory to sign
        key: HMAC key bytes

    Returns:
        Hex digest signature
    """
    h = hmac.new(key, digestmod=hashlib.sha256)

    # Sort files for deterministic signature
    for file_path in sorted(dir_path.rglob("*"), key=lambda x: str(x)):
        if file_path.is_file():
            h.update(file_path.read_bytes())

    sig = h.hexdigest()
    (dir_path / "SIGNATURE.hmac").write_text(sig)
    return sig


def build_promotion_bundle(spica_id: str, tournament: dict, out_dir: str) -> str:
    """
    Build signed promotion bundle for winner.

    Includes:
    - manifest.json (instance metadata)
    - lineage.json (provenance)
    - tournament.json (PHASE results)
    - snapshot/ (if exists)
    - artifacts/ (if exists)
    - SIGNATURE.hmac (HMAC over all files)

    Args:
        spica_id: Winner instance ID
        tournament: PHASE tournament results
        out_dir: Output directory for bundles

    Returns:
        Path to promotion bundle directory

    Raises:
        RuntimeError: If HMAC key not set
        FileNotFoundError: If instance not found
    """
    # Find instance
    inst = _find_instance_root(spica_id)

    # Create bundle directory
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    bundle = out / f"promotion_{spica_id}"

    if bundle.exists():
        shutil.rmtree(bundle)
    bundle.mkdir()

    # Copy core artifacts
    shutil.copy(inst / "manifest.json", bundle / "manifest.json")
    shutil.copy(inst / "lineage.json", bundle / "lineage.json")

    # Copy optional directories
    if (inst / "snapshot").exists():
        shutil.copytree(inst / "snapshot", bundle / "snapshot")
    if (inst / "artifacts").exists():
        shutil.copytree(inst / "artifacts", bundle / "artifacts")

    # Write tournament results
    (bundle / "tournament.json").write_text(json.dumps(tournament, indent=2))

    # HMAC sign entire bundle
    key = os.environ.get(HMAC_KEY_ENV, "").encode()
    if not key:
        raise RuntimeError(
            f"Missing HMAC key environment variable: {HMAC_KEY_ENV}\n"
            f"Set with: export {HMAC_KEY_ENV}=$(openssl rand -hex 32)"
        )

    signature = _hmac_sign_dir(bundle, key)

    print(f"✅ Promotion bundle created: {bundle}")
    print(f"   HMAC signature: {signature[:16]}...")

    return str(bundle)


def admit_winner_to_kloros(spica_id: str, bundle_path: str) -> None:
    """
    Admit tournament winner to KLoROS production.

    INTEGRATION STUB: Wire to your KLoROS integrator.
    This function should be the ONLY place where KLoROS gets touched.

    Args:
        spica_id: Winner instance ID
        bundle_path: Path to signed promotion bundle
    """
    # For now, just log the admission
    # Real integrator would:
    # 1. Verify HMAC signature
    # 2. Extract artifacts from bundle
    # 3. Stage in KLoROS deployment
    # 4. Run integration tests
    # 5. Promote to production

    admission_record = {
        "admit": True,
        "spica_id": spica_id,
        "bundle": bundle_path,
        "timestamp": int(os.times().elapsed * 1000),
        "note": "INTEGRATION STUB - wire to KLoROS deployer"
    }

    print(json.dumps(admission_record, indent=2))

    # TODO: Replace with actual KLoROS integration
    # from kloros.deployment import stage_variant
    # stage_variant(bundle_path, verify_signature=True)


if __name__ == "__main__":
    # CLI usage
    import argparse

    parser = argparse.ArgumentParser(description="SPICA tournament admission")
    parser.add_argument("--tournament", required=True, help="Path to tournament.json")
    parser.add_argument("--out-dir", default="/home/kloros/artifacts/dream/promotions",
                       help="Output directory for promotion bundles")
    parser.add_argument("--admit", action="store_true", help="Admit winner to KLoROS")

    args = parser.parse_args()

    # Load tournament results
    tournament = json.loads(Path(args.tournament).read_text())

    # Choose winner
    winner_id = choose_winner(tournament)
    print(f"🏆 Winner: {winner_id}")

    # Build bundle
    bundle = build_promotion_bundle(winner_id, tournament, args.out_dir)
    print(f"📦 Bundle: {bundle}")

    # Admit to KLoROS (if requested)
    if args.admit:
        admit_winner_to_kloros(winner_id, bundle)
