import json
import os
import fcntl
import time
import logging
from pathlib import Path
from typing import Dict, List, Optional, Any
from contextlib import contextmanager

logger = logging.getLogger(__name__)

DEFAULT_REGISTRY_PATH = Path.home() / ".kloros/registry/niche_map.json"
DEFAULT_LOCK_PATH = Path.home() / ".kloros/locks/colony_cycle.lock"


class LifecycleRegistry:
    """
    Two-tier registry with atomic operations and consistency reconciliation.

    Structure:
    {
        "niches": {
            "<niche_name>": {
                "active": [zooid_names],
                "probation": [zooid_names],
                "dormant": [zooid_names],
                "retired": [zooid_names]
            }
        },
        "zooids": {
            "<zooid_name>": {full_schema}
        },
        "genomes": {
            "<genome_hash>": "<zooid_name>"
        },
        "version": int
    }
    """

    def __init__(self, registry_path: Optional[Path] = None, lock_path: Optional[Path] = None):
        self.registry_path = Path(registry_path) if registry_path else DEFAULT_REGISTRY_PATH
        self.lock_path = Path(lock_path) if lock_path else DEFAULT_LOCK_PATH

        self.registry_path.parent.mkdir(parents=True, exist_ok=True)
        self.lock_path.parent.mkdir(parents=True, exist_ok=True)

    def load(self) -> Dict:
        """Load registry from disk, creating empty if missing."""
        if not self.registry_path.exists():
            logger.info(f"Registry not found at {self.registry_path}, creating empty")
            return self._empty_registry()

        try:
            with open(self.registry_path, 'r') as f:
                reg = json.load(f)
            logger.info(f"Loaded registry v{reg.get('version', 0)} from {self.registry_path}")
            return reg
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse registry: {e}")
            raise

    def _empty_registry(self) -> Dict:
        """Create empty two-tier registry structure."""
        return {
            "niches": {},
            "zooids": {},
            "genomes": {},
            "version": 0
        }

    def snapshot_then_atomic_write(self, reg: Dict) -> None:
        """
        Write registry atomically with versioned snapshot.

        Steps:
        1. Increment version
        2. Write snapshot (niche_map.v{N}.json)
        3. Write to tmp file
        4. fsync directory
        5. Rename tmp → live
        """
        reg["version"] = reg.get("version", 0) + 1
        version = reg["version"]

        snapshot_path = self.registry_path.parent / f"niche_map.v{version}.json"
        snapshot_path.write_text(json.dumps(reg, indent=2))
        logger.info(f"Saved snapshot: {snapshot_path}")

        tmp_path = self.registry_path.with_suffix('.json.tmp')
        tmp_path.write_text(json.dumps(reg, indent=2))

        try:
            os.fsync(tmp_path.open('r').fileno())
        except Exception as e:
            logger.warning(f"fsync failed (non-critical): {e}")

        tmp_path.rename(self.registry_path)
        logger.info(f"Atomic write complete: {self.registry_path} v{version}")

    @contextmanager
    def lock(self):
        """Acquire exclusive lock for registry mutations."""
        self.lock_path.parent.mkdir(parents=True, exist_ok=True)

        with open(self.lock_path, 'w') as f:
            try:
                fcntl.flock(f.fileno(), fcntl.LOCK_EX)
                logger.debug(f"Acquired lock: {self.lock_path}")
                yield
            finally:
                fcntl.flock(f.fileno(), fcntl.LOCK_UN)
                logger.debug(f"Released lock: {self.lock_path}")

    def add_or_update_zooid(self, reg: Dict, zooid: Dict) -> None:
        """Add or update zooid in registry."""
        name = zooid["name"]
        reg["zooids"][name] = zooid
        logger.debug(f"Added/updated zooid: {name}")

    def index_add(self, reg: Dict, niche: str, state: str, name: str) -> None:
        """Add zooid name to niche index (idempotent)."""
        if niche not in reg["niches"]:
            reg["niches"][niche] = {
                "active": [],
                "probation": [],
                "dormant": [],
                "retired": []
            }

        if name not in reg["niches"][niche][state]:
            reg["niches"][niche][state].append(name)
            logger.debug(f"Added {name} to {niche}.{state}")

    def index_remove(self, reg: Dict, niche: str, state: str, name: str) -> None:
        """Remove zooid name from niche index (idempotent)."""
        if niche in reg["niches"] and name in reg["niches"][niche][state]:
            reg["niches"][niche][state].remove(name)
            logger.debug(f"Removed {name} from {niche}.{state}")

    def index_set(self, reg: Dict, niche: str, state: str, names: List[str]) -> None:
        """Replace niche index with new list."""
        if niche not in reg["niches"]:
            reg["niches"][niche] = {
                "active": [],
                "probation": [],
                "dormant": [],
                "retired": []
            }

        reg["niches"][niche][state] = list(names)
        logger.debug(f"Set {niche}.{state} = {names}")

    def genome_bind(self, reg: Dict, genome_hash: str, name: str) -> None:
        """Bind genome hash to zooid name."""
        if genome_hash in reg["genomes"]:
            existing = reg["genomes"][genome_hash]
            if existing != name:
                logger.warning(f"Genome hash collision: {genome_hash} already bound to {existing}, refusing to bind to {name}")
                raise ValueError(f"Genome hash {genome_hash} already bound to {existing}")

        reg["genomes"][genome_hash] = name
        logger.debug(f"Bound genome {genome_hash[:16]}... → {name}")

    def genome_lookup(self, reg: Dict, genome_hash: str) -> Optional[str]:
        """Look up zooid name by genome hash."""
        return reg["genomes"].get(genome_hash)

    def reconcile(self, reg: Dict) -> List[str]:
        """
        Reconcile index-object consistency and genome bijection.

        Returns list of fixes applied.
        """
        fixes = []

        for niche_name, niche_data in reg["niches"].items():
            for state in ["active", "probation", "dormant", "retired"]:
                zooid_names = niche_data.get(state, [])

                for name in list(zooid_names):
                    if name not in reg["zooids"]:
                        zooid_names.remove(name)
                        fixes.append(f"removed_missing_{niche_name}.{state}: {name}")
                    else:
                        zooid = reg["zooids"][name]
                        if zooid.get("lifecycle_state") != state.upper():
                            zooid_names.remove(name)
                            fixes.append(f"removed_state_mismatch_{niche_name}.{state}: {name} (actual: {zooid.get('lifecycle_state')})")

        genome_counts = {}
        for genome_hash, zooid_name in reg["genomes"].items():
            if zooid_name not in reg["zooids"]:
                fixes.append(f"genome_orphan: {genome_hash[:16]}... → {zooid_name}")

            genome_counts[genome_hash] = genome_counts.get(genome_hash, 0) + 1

        duplicates = {h: c for h, c in genome_counts.items() if c > 1}
        if duplicates:
            fixes.append(f"genome_duplicates: {duplicates}")
            raise ValueError(f"Genome bijection violated: {duplicates}")

        if fixes:
            logger.warning(f"Reconciliation applied {len(fixes)} fixes: {fixes}")
        else:
            logger.info("Reconciliation: no fixes needed")

        return fixes

    def get_zooid_metadata(self, zooid_name: str) -> Dict[str, Any]:
        """
        Get metadata for a zooid including brainmod and variant.

        Infers brainmod and variant from zooid filename pattern:
        {capability}_{timestamp}_{variant}.py

        Args:
            zooid_name: Name of the zooid

        Returns:
            Dict with 'brainmod' and 'variant' keys (may be None if not found)
        """
        zooid_path = self._find_zooid_file(zooid_name)

        if not zooid_path:
            return {"brainmod": None, "variant": None}

        parts = zooid_path.stem.split("_")

        return {
            "brainmod": parts[0] if len(parts) > 0 else None,
            "variant": parts[-1] if len(parts) > 2 else "0",
            "path": str(zooid_path)
        }

    def _find_zooid_file(self, zooid_name: str) -> Optional[Path]:
        """
        Find the file path for a zooid by name.

        Args:
            zooid_name: Name of the zooid

        Returns:
            Path to zooid file, or None if not found
        """
        kloros_home = Path(os.getenv('KLOROS_HOME', '/home/kloros'))
        zooids_dir = kloros_home / "src/zooids"

        if not zooids_dir.exists():
            return None

        zooid_file = zooids_dir / f"{zooid_name}.py"

        if zooid_file.exists():
            return zooid_file

        return None


def load_lifecycle_policy() -> Dict:
    """Load lifecycle policy config."""
    policy_path = Path(os.getenv("KLR_POLICY_PATH", Path.home() / ".kloros/config/lifecycle_policy.json"))

    if not policy_path.exists():
        logger.warning(f"Policy file not found: {policy_path}, using defaults")
        return {
            "phase_threshold": 0.70,
            "min_phase_evidence": 50,
            "phase_half_life_sec": 43200,
            "quarantine_window_sec": 900,
            "n_failures_for_quarantine": 3,
            "demotion_ceiling": 2
        }

    with open(policy_path, 'r') as f:
        return json.load(f)
