#!/usr/bin/env python
"""
SPICA Instance Reconciliation Tool

Builds authoritative registry from disk, marks tombstones for missing instances.
Part of Phase 3 structural repairs.
"""
import json
from pathlib import Path

BASE = Path("/home/kloros/experiments/spica/instances")
REGISTRY_PATH = Path.home() / ".kloros" / "spica_registry.json"
REGISTRY_PATH.parent.mkdir(parents=True, exist_ok=True)

def find_disk_instances():
    """Scan disk for all SPICA instances with validation."""
    instances = {}
    if not BASE.exists():
        return instances

    for inst_dir in BASE.iterdir():
        if not inst_dir.is_dir():
            continue

        # Skip nested "instances" directory if it exists
        if inst_dir.name == "instances":
            continue

        name = inst_dir.name  # e.g. spica-3480f633

        lineage = inst_dir / "lineage.json"
        manifest = inst_dir / "manifest.json"

        if not lineage.exists() or not manifest.exists():
            # Broken/partial instance, we'll keep flagged
            instances[name] = {
                "name": name,
                "path": str(inst_dir),
                "valid": False,
                "reason": "missing_lineage_or_manifest",
            }
            continue

        instances[name] = {
            "name": name,
            "path": str(inst_dir),
            "valid": True,
            "reason": "ok",
        }

    return instances

def load_registry():
    """Load existing registry or create new one."""
    if not REGISTRY_PATH.exists():
        return {"instances": {}, "version": 1}
    with REGISTRY_PATH.open("r") as f:
        return json.load(f)

def save_registry(registry):
    """Save registry atomically."""
    tmp = REGISTRY_PATH.with_suffix(".tmp")
    with tmp.open("w") as f:
        json.dump(registry, f, indent=2, sort_keys=True)
    tmp.replace(REGISTRY_PATH)

def main():
    print("[reconcile] Scanning disk for SPICA instances...")
    disk_instances = find_disk_instances()
    print(f"[reconcile] Found {len(disk_instances)} instances on disk")

    registry = load_registry()
    registry_instances = registry.get("instances", {})

    # Mark any registry entries that don't exist on disk as tombstones
    tombstoned = 0
    for name, meta in list(registry_instances.items()):
        if name not in disk_instances:
            meta["state"] = "tombstoned"
            meta["reason"] = "missing_on_disk"
            tombstoned += 1

    # Add/refresh from disk
    active = 0
    invalid = 0
    for name, dmeta in disk_instances.items():
        rmeta = registry_instances.get(name, {})
        rmeta.update(
            {
                "name": name,
                "path": dmeta["path"],
                "valid": dmeta["valid"],
                "reason": dmeta["reason"],
                "state": "active" if dmeta["valid"] else "invalid",
            }
        )
        registry_instances[name] = rmeta

        if dmeta["valid"]:
            active += 1
        else:
            invalid += 1

    registry["instances"] = registry_instances
    save_registry(registry)

    print(f"[reconcile] ✓ Reconciliation complete:")
    print(f"  - Active (valid): {active}")
    print(f"  - Invalid (missing lineage/manifest): {invalid}")
    print(f"  - Tombstoned (in registry but missing on disk): {tombstoned}")
    print(f"  - Registry saved to: {REGISTRY_PATH}")

if __name__ == "__main__":
    main()
