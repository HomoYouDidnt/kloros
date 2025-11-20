#!/usr/bin/env python3
"""
D-REAM Candidate Adoption System

Handles promotion of admitted candidates to active KLoROS configuration.
"""
import os
import json
from datetime import datetime
from typing import List, Dict
from pathlib import Path


def adopt_candidates(run_id: str) -> Dict:
    """
    Adopt admitted candidates from a D-REAM run.

    Args:
        run_id: The D-REAM run identifier

    Returns:
        Dictionary with adoption results
    """
    dream_artifacts = os.environ.get("DREAM_ARTIFACTS", "/home/kloros/src/dream/artifacts")

    # Load admitted candidates
    admitted_path = Path(dream_artifacts) / "candidates" / run_id / "admitted.json"
    if not admitted_path.exists():
        return {"ok": False, "error": f"No admitted candidates for run {run_id}"}

    with open(admitted_path) as f:
        pack = json.load(f)

    admitted = pack.get("admitted", [])
    lineage = pack.get("lineage", {})

    if not admitted:
        return {"ok": False, "error": "No candidates to adopt"}

    # Record adoption
    adoption_log_path = Path(dream_artifacts) / "adoptions.jsonl"
    adoption_record = {
        "timestamp": datetime.utcnow().isoformat(),
        "run_id": run_id,
        "origin": lineage.get("origin"),
        "episode_id": lineage.get("episode_id"),
        "generator_sha": lineage.get("generator_sha"),
        "judge_sha": lineage.get("judge_sha"),
        "adopted_count": len(admitted),
        "candidates": [
            {
                "id": c["id"],
                "domain": c["domain"],
                "metrics": c["metrics"]
            }
            for c in admitted
        ]
    }

    with open(adoption_log_path, "a") as f:
        f.write(json.dumps(adoption_record) + "\n")

    # TODO: Apply domain-specific configurations
    # For now, we just log the adoption
    # Future: Wire to actual KLoROS config update mechanisms

    return {
        "ok": True,
        "run_id": run_id,
        "adopted_count": len(admitted),
        "message": f"Adopted {len(admitted)} candidates from {run_id}",
        "domains": list(set(c["domain"] for c in admitted)),
        "log_path": str(adoption_log_path)
    }


def list_adoptions(limit: int = 10) -> List[Dict]:
    """
    List recent adoptions.

    Args:
        limit: Maximum number of adoptions to return

    Returns:
        List of adoption records
    """
    dream_artifacts = os.environ.get("DREAM_ARTIFACTS", "/home/kloros/src/dream/artifacts")
    adoption_log_path = Path(dream_artifacts) / "adoptions.jsonl"

    if not adoption_log_path.exists():
        return []

    adoptions = []
    with open(adoption_log_path) as f:
        for line in f:
            adoptions.append(json.loads(line))

    # Return most recent first
    return list(reversed(adoptions[-limit:]))


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Usage: python adopt.py <run_id>")
        sys.exit(1)

    result = adopt_candidates(sys.argv[1])
    print(json.dumps(result, indent=2))
