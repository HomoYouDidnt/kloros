#!/usr/bin/env python3
"""
Baseline Manager - Atomic baseline configuration updates.

Manages system baseline with manifest chain, versioning, and rollback support.
"""

import os
import json
import hashlib
import shutil
import time
import logging
from pathlib import Path
from dataclasses import dataclass, asdict
from typing import Optional

import yaml

logger = logging.getLogger(__name__)

BASE_DIR = Path("/home/kloros/system/baseline")
BASE_CONFIG = BASE_DIR / "baseline.yaml"
MANIFEST_FILE = BASE_DIR / "manifest.json"
VERSIONS_DIR = BASE_DIR / "versions"
MAX_VERSIONS = 10  # Keep last 10 versions


@dataclass
class BaselineManifest:
    """Baseline version manifest with chain tracking."""
    version: int
    sha256: str
    previous_sha: str
    ts: float
    actor: str
    promotion_ids: list[str]


def commit_baseline(new_config: dict, promo_ids: list[str], actor: str = "kloros-orchestrator") -> Path:
    """
    Atomically update baseline configuration.

    Args:
        new_config: New baseline configuration dict
        promo_ids: List of promotion IDs that contributed to this update
        actor: Who/what is making this change

    Returns:
        Path to archived version

    Raises:
        RuntimeError: If commit fails
    """
    BASE_DIR.mkdir(parents=True, exist_ok=True)
    VERSIONS_DIR.mkdir(parents=True, exist_ok=True)

    # Get previous manifest if exists
    previous_sha = ""
    previous_version = 0
    if MANIFEST_FILE.exists():
        try:
            with open(MANIFEST_FILE, 'r') as f:
                prev_manifest = BaselineManifest(**json.load(f))
                previous_sha = prev_manifest.sha256
                previous_version = prev_manifest.version
        except Exception as e:
            logger.warning(f"Could not read previous manifest: {e}")

    new_version = previous_version + 1

    # Write to temp file with fsync
    tmp_file = BASE_CONFIG.with_suffix('.tmp')
    try:
        with open(tmp_file, 'w') as f:
            yaml.safe_dump(new_config, f, default_flow_style=False, sort_keys=False)
            f.flush()
            os.fsync(f.fileno())  # Force to disk

        # Compute SHA256
        new_sha = hashlib.sha256(tmp_file.read_bytes()).hexdigest()

        # Atomic rename
        tmp_file.rename(BASE_CONFIG)
        logger.info(f"Committed baseline v{new_version} (SHA256: {new_sha[:12]}...)")

    except Exception as e:
        if tmp_file.exists():
            tmp_file.unlink()
        raise RuntimeError(f"Failed to commit baseline: {e}")

    # Create manifest
    manifest = BaselineManifest(
        version=new_version,
        sha256=new_sha,
        previous_sha=previous_sha,
        ts=time.time(),
        actor=actor,
        promotion_ids=promo_ids
    )

    # Write manifest
    try:
        with open(MANIFEST_FILE, 'w') as f:
            json.dump(asdict(manifest), f, indent=2)
            f.flush()
            os.fsync(f.fileno())
    except Exception as e:
        logger.error(f"Failed to write manifest: {e}")
        # Don't fail - baseline is already committed

    # Archive version
    archive_path = VERSIONS_DIR / f"baseline_v{new_version:04d}.yaml"
    manifest_archive = VERSIONS_DIR / f"manifest_v{new_version:04d}.json"

    try:
        shutil.copy2(BASE_CONFIG, archive_path)
        shutil.copy2(MANIFEST_FILE, manifest_archive)
        logger.info(f"Archived to {archive_path.name}")
    except Exception as e:
        logger.error(f"Failed to archive version: {e}")

    # Prune old versions
    _prune_old_versions()

    return archive_path


def rollback_to_version(version: int) -> None:
    """
    Rollback baseline to a specific version.

    Args:
        version: Version number to restore

    Raises:
        RuntimeError: If rollback fails or version not found
    """
    archive_path = VERSIONS_DIR / f"baseline_v{version:04d}.yaml"
    manifest_archive = VERSIONS_DIR / f"manifest_v{version:04d}.json"

    if not archive_path.exists():
        raise RuntimeError(f"Version {version} not found in archives")

    if not manifest_archive.exists():
        raise RuntimeError(f"Manifest for version {version} not found")

    try:
        # Restore both baseline and manifest
        shutil.copy2(archive_path, BASE_CONFIG)
        shutil.copy2(manifest_archive, MANIFEST_FILE)

        logger.info(f"Rolled back to version {version}")

    except Exception as e:
        raise RuntimeError(f"Rollback failed: {e}")


def get_current_version() -> Optional[BaselineManifest]:
    """Get current baseline version manifest."""
    if not MANIFEST_FILE.exists():
        return None

    try:
        with open(MANIFEST_FILE, 'r') as f:
            return BaselineManifest(**json.load(f))
    except Exception as e:
        logger.error(f"Failed to read manifest: {e}")
        return None


def list_versions() -> list[int]:
    """List available baseline versions."""
    if not VERSIONS_DIR.exists():
        return []

    versions = []
    for f in VERSIONS_DIR.glob("baseline_v*.yaml"):
        try:
            version = int(f.stem.split('_v')[1])
            versions.append(version)
        except (IndexError, ValueError):
            continue

    return sorted(versions, reverse=True)


def _prune_old_versions() -> None:
    """Keep only the last MAX_VERSIONS versions."""
    versions = list_versions()

    if len(versions) <= MAX_VERSIONS:
        return

    # Delete oldest versions
    to_delete = versions[MAX_VERSIONS:]
    for version in to_delete:
        try:
            (VERSIONS_DIR / f"baseline_v{version:04d}.yaml").unlink()
            (VERSIONS_DIR / f"manifest_v{version:04d}.json").unlink()
            logger.info(f"Pruned old version {version}")
        except Exception as e:
            logger.warning(f"Failed to prune version {version}: {e}")
