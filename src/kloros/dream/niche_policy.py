"""
Migration policy for controlling which systems can be migrated to zooids.

Provides allow-list and blocklist mechanisms to prevent accidental
migration of core infrastructure.
"""

from dataclasses import dataclass
from typing import Dict, Set, Optional, List


@dataclass
class MigrationPolicy:
    allowed_systems: Dict[str, str]
    blocked_systems: Set[str]
    suggested_niches: Dict[str, Dict[str, str]]

    def is_migration_allowed(self, system_name: str) -> bool:
        if system_name in self.blocked_systems:
            return False

        return system_name in self.allowed_systems

    def get_niche(self, system_name: str) -> Optional[str]:
        return self.allowed_systems.get(system_name)

    def get_niche_config(self, niche: str) -> Optional[Dict[str, str]]:
        return self.suggested_niches.get(niche)

    def filter_candidates(self, systems: List[dict]) -> List[dict]:
        candidates = []

        for system in systems:
            name = system['name']

            if system['core_infrastructure']:
                continue

            if name in self.blocked_systems:
                continue

            if name in self.allowed_systems:
                system['suggested_niche'] = self.allowed_systems[name]
                system['migration_approved'] = True
                candidates.append(system)
            else:
                system['suggested_niche'] = None
                system['migration_approved'] = False

        return candidates


MIGRATION_ALLOWLIST = {
    "housekeeping_scheduler": "maintenance_housekeeping",
    "decay_daemon": "memory_decay",
    "promotion_daemon": "promotion_validation",
    "ledger_writer_daemon": "observability_logging",
}

CORE_BLOCKLIST = {
    "dream_domain_service",
    "consumer_daemon",
    "remediation_service",
    "cycle_coordinator",
    "bioreactor",
    "graduator",
    "selector",
    "spawner",
}

NICHE_CONFIGS = {
    "maintenance_housekeeping": {
        "description": "System maintenance and cleanup operations",
        "base_class": "MaintenanceZooid",
        "tick_method": "run_maintenance",
        "typical_interval_sec": "86400",
    },
    "memory_decay": {
        "description": "Memory system decay score management",
        "base_class": "MemoryZooid",
        "tick_method": "update_decay",
        "typical_interval_sec": "3600",
    },
    "promotion_validation": {
        "description": "D-REAM promotion validation and acknowledgment",
        "base_class": "ValidationZooid",
        "tick_method": "validate_promotions",
        "typical_interval_sec": "60",
    },
    "observability_logging": {
        "description": "System observability and ledger writing",
        "base_class": "ObservabilityZooid",
        "tick_method": "write_logs",
        "typical_interval_sec": "1",
    },
}


def get_default_policy() -> MigrationPolicy:
    return MigrationPolicy(
        allowed_systems=MIGRATION_ALLOWLIST,
        blocked_systems=CORE_BLOCKLIST,
        suggested_niches=NICHE_CONFIGS
    )


def apply_migration_policy(discovery_result: dict) -> dict:
    policy = get_default_policy()

    systems = discovery_result.get('unmigrated_systems', [])

    approved = []
    pending = []
    blocked = []

    for system in systems:
        name = system['name']

        if system['core_infrastructure']:
            system['migration_status'] = 'blocked_core'
            blocked.append(system)
            continue

        if name in policy.blocked_systems:
            system['migration_status'] = 'blocked_policy'
            blocked.append(system)
            continue

        if policy.is_migration_allowed(name):
            niche = policy.get_niche(name)
            system['suggested_niche'] = niche
            system['niche_config'] = policy.get_niche_config(niche)
            system['migration_status'] = 'approved'
            approved.append(system)
        else:
            system['suggested_niche'] = None
            system['migration_status'] = 'pending_review'
            pending.append(system)

    return {
        "approved_for_migration": approved,
        "pending_review": pending,
        "blocked": blocked,
        "summary": {
            "approved": len(approved),
            "pending": len(pending),
            "blocked": len(blocked)
        }
    }


if __name__ == "__main__":
    import json
    from pathlib import Path

    discovery_file = Path("/tmp/unmigrated_systems.json")
    if discovery_file.exists():
        with open(discovery_file, 'r') as f:
            discovery = json.load(f)

        result = apply_migration_policy(discovery)

        output_file = Path("/tmp/migration_policy_result.json")
        with open(output_file, 'w') as f:
            json.dump(result, f, indent=2)

        print(f"[policy] Applied migration policy")
        print(f"[policy] Approved: {result['summary']['approved']}")
        print(f"[policy] Pending: {result['summary']['pending']}")
        print(f"[policy] Blocked: {result['summary']['blocked']}")

        print("\n[policy] Approved systems:")
        for system in result['approved_for_migration']:
            print(f"  - {system['name']} → {system['suggested_niche']}")
    else:
        print(f"[policy] Discovery file not found: {discovery_file}")
        print(f"[policy] Run migration_discovery.py first")
