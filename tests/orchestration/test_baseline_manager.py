#!/usr/bin/env python3
"""
Tests for baseline_manager.py - Baseline configuration management.
"""

import pytest
from pathlib import Path
import shutil

from src.kloros.orchestration.baseline_manager import (
    commit_baseline,
    rollback_to_version,
    get_current_version,
    list_versions,
    BASE_DIR,
    BASE_CONFIG,
    MANIFEST_FILE,
    VERSIONS_DIR
)


@pytest.fixture
def clean_baseline_dir():
    """Clean up baseline directory before and after tests."""
    # Backup if exists
    backup_dir = BASE_DIR.parent / "baseline_backup_test"
    if BASE_DIR.exists():
        if backup_dir.exists():
            shutil.rmtree(backup_dir)
        shutil.copytree(BASE_DIR, backup_dir)

    # Clean for test
    if BASE_DIR.exists():
        shutil.rmtree(BASE_DIR)
    BASE_DIR.mkdir(parents=True, exist_ok=True)

    yield

    # Restore backup
    if backup_dir.exists():
        if BASE_DIR.exists():
            shutil.rmtree(BASE_DIR)
        shutil.copytree(backup_dir, BASE_DIR)
        shutil.rmtree(backup_dir)


def test_commit_baseline_creates_version(clean_baseline_dir):
    """Test that committing baseline creates a version."""
    config = {"version": 1, "test": "data"}

    archive_path = commit_baseline(config, ["promo1"], actor="test")

    assert BASE_CONFIG.exists()
    assert MANIFEST_FILE.exists()
    assert archive_path.exists()

    # Check manifest
    manifest = get_current_version()
    assert manifest is not None
    assert manifest.version == 1
    assert "promo1" in manifest.promotion_ids


def test_commit_multiple_versions(clean_baseline_dir):
    """Test that multiple commits create version chain."""
    config1 = {"version": 1}
    commit_baseline(config1, ["promo1"], actor="test")

    config2 = {"version": 2}
    commit_baseline(config2, ["promo2"], actor="test")

    config3 = {"version": 3}
    commit_baseline(config3, ["promo3"], actor="test")

    # Check versions
    versions = list_versions()
    assert len(versions) == 3
    assert 1 in versions
    assert 2 in versions
    assert 3 in versions

    # Check manifest chain
    manifest = get_current_version()
    assert manifest.version == 3
    assert manifest.previous_sha != ""


def test_rollback_to_version(clean_baseline_dir):
    """Test rollback functionality."""
    config1 = {"version": 1, "data": "first"}
    commit_baseline(config1, ["promo1"], actor="test")

    config2 = {"version": 2, "data": "second"}
    commit_baseline(config2, ["promo2"], actor="test")

    config3 = {"version": 3, "data": "third"}
    commit_baseline(config3, ["promo3"], actor="test")

    # Rollback to version 2
    rollback_to_version(2)

    # Check current version
    manifest = get_current_version()
    assert manifest.version == 2

    # Verify config content
    import yaml
    with open(BASE_CONFIG, 'r') as f:
        current_config = yaml.safe_load(f)
    assert current_config["data"] == "second"


def test_list_versions_empty(clean_baseline_dir):
    """Test listing versions when none exist."""
    versions = list_versions()
    assert versions == []


def test_version_pruning(clean_baseline_dir):
    """Test that old versions are pruned."""
    # Create more than MAX_VERSIONS (10)
    for i in range(15):
        config = {"version": i + 1}
        commit_baseline(config, [f"promo{i+1}"], actor="test")

    # Check that only last 10 remain
    versions = list_versions()
    assert len(versions) == 10
    assert max(versions) == 15
    assert min(versions) == 6  # Oldest kept should be 6


def test_get_current_version_none(clean_baseline_dir):
    """Test getting current version when none exists."""
    manifest = get_current_version()
    assert manifest is None
