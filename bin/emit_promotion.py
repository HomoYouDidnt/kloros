#!/usr/bin/env python3
"""
Promotion Emitter - Transforms winners into explicit promotions.

Usage: python emit_promotion.py <domain> <winner_json> <out_promotion_json>
"""
from __future__ import annotations
import json
import sys
import hashlib
import pathlib
import time


APPLY_MAPS = {
    # Maps winner fields → well-known promotion keys used by evaluators
    "spica_toolgen": {
        "bundle_path": "TOOLGEN_REFERENCE_BUNDLE",  # path to bundle dir
        "spec_id": "TOOLGEN_ACTIVE_SPEC"            # short id (e.g., text_deduplicate)
    }
}


def sha256_dir(path: pathlib.Path) -> str:
    """
    Calculate SHA256 hash of directory contents.

    Args:
        path: Directory to hash

    Returns:
        Hex digest of directory contents
    """
    h = hashlib.sha256()
    try:
        for p in sorted(path.rglob("*")):
            if p.is_file():
                h.update(p.relative_to(path).as_posix().encode())
                h.update(p.read_bytes())
    except Exception:
        # If hashing fails, return empty hash
        return "unknown"
    return h.hexdigest()


def main():
    if len(sys.argv) != 4:
        print("usage: emit_promotion.py <domain> <winner_json> <out_promotion_json>", file=sys.stderr)
        sys.exit(2)

    domain = sys.argv[1]
    winner_json = pathlib.Path(sys.argv[2])
    out_json = pathlib.Path(sys.argv[3])

    amap = APPLY_MAPS.get(domain)
    if not amap:
        print(f"unknown domain: {domain}", file=sys.stderr)
        sys.exit(3)

    # Load winner data
    winner = json.loads(winner_json.read_text())

    # Extract winner metadata
    # Expected fields from D-REAM winner tracker:
    # {
    #   "updated_at": 1761617790,
    #   "best": {
    #     "fitness": 0.65,
    #     "params": {"spec_id": "text_deduplicate"},
    #     "metrics": {
    #       "bundle_path": "/home/kloros/artifacts/toolgen_bundles/...",
    #       "tool_id": "text_deduplicate",
    #       "impl_style": "set",
    #       "median_ms": 0.32,
    #       ...
    #     }
    #   }
    # }

    best = winner.get("best", {})
    metrics = best.get("metrics", {})
    params = best.get("params", {})

    bundle_path = metrics.get("bundle_path", "")
    spec_id = metrics.get("tool_id") or params.get("spec_id", "")

    if not bundle_path:
        print(f"ERROR: No bundle_path in winner data", file=sys.stderr)
        sys.exit(4)

    bundle = pathlib.Path(bundle_path)
    if not bundle.exists():
        print(f"WARNING: Bundle directory does not exist: {bundle}", file=sys.stderr)
        digest = "missing"
    else:
        digest = sha256_dir(bundle)

    # Create promotion
    promo = {
        "domain": domain,
        "ts": time.time(),
        "winner_ts": winner.get("updated_at"),
        "winner_fitness": best.get("fitness"),
        "apply_map": {
            amap["bundle_path"]: str(bundle),
            amap["spec_id"]: spec_id,
        },
        "metadata": {
            "impl_style": metrics.get("impl_style"),
            "median_ms": metrics.get("median_ms"),
            "sha256": digest,
            "correctness": metrics.get("correctness"),
            "safety": metrics.get("safety"),
            "performance": metrics.get("performance"),
        }
    }

    # Write promotion file
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(promo, indent=2))
    print(f"✓ Wrote promotion → {out_json}")
    print(f"  Domain: {domain}")
    print(f"  Fitness: {best.get('fitness', 0.0):.3f}")
    print(f"  Bundle: {bundle}")


if __name__ == "__main__":
    main()
