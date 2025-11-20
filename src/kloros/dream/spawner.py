"""
D-REAM Spawner - generates zooid variants and registers them as DORMANT.

Creates new zooid code from templates with mutated parameters.
"""
import time
import json
import hashlib
import pathlib
import logging
from typing import Optional

from . import genomes
from kloros.registry.lifecycle_registry import LifecycleRegistry

logger = logging.getLogger(__name__)

SPAWN_JOURNAL = pathlib.Path.home() / ".kloros/lineage/dream_spawn.jsonl"


def _sha256_text(s: str) -> str:
    """Compute SHA256 hash of text."""
    return "sha256:" + hashlib.sha256(s.encode("utf-8")).hexdigest()


def _render_template(niche: str, params: dict) -> str:
    """
    Render zooid template with parameters.

    Simple string replacement for {{key}} placeholders.
    Uses Jinja2-style syntax but basic string replace for now.
    """
    template_path = pathlib.Path(f"/home/kloros/src/zooids/templates/{niche}/base.py.j2")

    if not template_path.exists():
        raise FileNotFoundError(f"Template not found: {template_path}")

    tpl = template_path.read_text()

    for key, value in params.items():
        tpl = tpl.replace("{{" + key + "}}", str(value))

    return tpl


def _write_module(module_code: str, name: str) -> str:
    """Write zooid module to filesystem."""
    module_path = pathlib.Path(f"/home/kloros/src/zooids/{name}.py")
    module_path.write_text(module_code)
    return str(module_path)


def spawn_variants(
    niche: str,
    ecosystem: str,
    m: int,
    base_parent: Optional[str] = None,
    policy: Optional[dict] = None
) -> list[dict]:
    """
    Generate M zooid variants for a niche.

    Args:
        niche: Niche name
        ecosystem: Ecosystem name
        m: Number of variants to generate
        base_parent: Optional parent zooid name for lineage tracking
        policy: Optional policy dict

    Returns:
        List of zooid registration dicts
    """
    now = time.time()
    out = []

    for i in range(m):
        # Mutate parameters
        params = genomes.mutate_params(niche)

        # Render template
        module_code = _render_template(niche, params)

        # Compute genome hash
        phenotype_json = json.dumps(params, sort_keys=True)
        ghash = _sha256_text(module_code + phenotype_json)

        # Generate name
        name = f"{niche}_{int(now)}_{i}"

        # Write module
        _write_module(module_code, name)

        out.append({
            "name": name,
            "ecosystem": ecosystem,
            "niche": niche,
            "lifecycle_state": "DORMANT",
            "genome_hash": ghash,
            "parent_lineage": [base_parent] if base_parent else [],
            "created_ts": now,
            "state_changed_ts": now,
            "entered_ts": now,
            "reason": "spawned_by_dream_spawner",
            "phenotype": params,
            "probation": {
                "started_ts": None,
                "phase_submitted_ts": None,
                "evidence": 0
            },
            "prod": {
                "ok_rate": 0.0,
                "ttr_ms_mean": 0.0,
                "evidence": 0,
                "last_heartbeat_ts": None
            },
            "promoted_ts": None,
            "retired_ts": None,
            "demotions": 0,
            "cooldown_until_ts": None,
            "retirement_reason": None
        })

    return out


def dream_spawn_tick(policy: dict) -> list[str]:
    """
    Execute one spawn cycle.

    Evaluates niches, generates variants, registers in registry.

    Args:
        policy: Policy configuration dict

    Returns:
        List of spawned zooid names
    """
    reg_mgr = LifecycleRegistry()
    reg = reg_mgr.load()

    # Determine which niches need new variants
    targets = []
    for niche_name, niche_data in reg.get("niches", {}).items():
        active_count = len(niche_data.get("active", []))
        dormant_count = len(niche_data.get("dormant", []))

        min_active = int(policy.get("spawn_min_active_per_niche", 2))
        max_dormant = int(policy.get("spawn_max_dormant_per_niche", 12))

        if active_count < min_active or dormant_count < max_dormant:
            # Infer ecosystem from existing zooids or use default
            ecosystem = "queue_management"  # Default
            if active_count > 0:
                sample_name = niche_data["active"][0]
                ecosystem = reg["zooids"][sample_name].get("ecosystem", ecosystem)

            targets.append((ecosystem, niche_name))

    spawned = []
    candidates_per_tick = int(policy.get("spawn_candidates_per_tick", 3))

    for ecosystem, niche in targets:
        logger.info(f"Spawning {candidates_per_tick} variants for {niche}")

        for cand in spawn_variants(niche, ecosystem, candidates_per_tick):
            # Dedup by genome hash
            if cand["genome_hash"] in reg.get("genomes", {}):
                logger.debug(f"Skipping duplicate genome: {cand['genome_hash'][:16]}...")
                continue

            # Register zooid
            reg["zooids"][cand["name"]] = cand
            reg["niches"][niche]["dormant"].append(cand["name"])
            reg["genomes"][cand["genome_hash"]] = cand["name"]

            # Journal spawn event
            SPAWN_JOURNAL.parent.mkdir(parents=True, exist_ok=True)
            with SPAWN_JOURNAL.open("a") as f:
                f.write(json.dumps({
                    "ts": time.time(),
                    "event": "dream_spawn",
                    "zooid": cand["name"],
                    "niche": niche,
                    "ecosystem": ecosystem,
                    "genome_hash": cand["genome_hash"],
                    "phenotype": cand["phenotype"]
                }) + "\n")

            spawned.append(cand["name"])
            logger.info(f"  Spawned: {cand['name']}")

    if spawned:
        reg_mgr.snapshot_then_atomic_write(reg)
        logger.info(f"Spawned {len(spawned)} total variants")
    else:
        logger.info("No variants needed")

    return spawned
