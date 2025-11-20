#!/usr/bin/env python3
"""
Tests for promotion_daemon.py - Promotion validation.
"""

import pytest
import json
import tempfile
from pathlib import Path

from src.kloros.orchestration.promotion_daemon import (
    validate_promotion,
    create_ack,
    DEFAULT_REGISTRY
)


def test_validate_valid_promotion():
    """Test validation of a valid promotion."""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        promo = {
            "schema": "v1",
            "id": "test_promo_001",
            "timestamp": 1234567890,
            "fitness": 0.85,
            "changes": {
                "learning_rate": 0.01,
                "batch_size": 32
            }
        }
        json.dump(promo, f)
        f.flush()

        path = Path(f.name)

    try:
        is_valid, reason = validate_promotion(path, DEFAULT_REGISTRY)
        assert is_valid
        assert reason == "valid"
    finally:
        path.unlink()


def test_validate_missing_schema():
    """Test validation fails for missing schema."""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        promo = {
            "id": "test_promo_002",
            "timestamp": 1234567890,
            "fitness": 0.85,
            "changes": {}
        }
        json.dump(promo, f)
        f.flush()

        path = Path(f.name)

    try:
        is_valid, reason = validate_promotion(path, DEFAULT_REGISTRY)
        assert not is_valid
        assert "schema" in reason.lower()
    finally:
        path.unlink()


def test_validate_out_of_bounds():
    """Test validation fails for out-of-bounds values."""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        promo = {
            "schema": "v1",
            "id": "test_promo_003",
            "timestamp": 1234567890,
            "fitness": 0.85,
            "changes": {
                "learning_rate": 0.5,  # Max is 0.1 in DEFAULT_REGISTRY
                "batch_size": 32
            }
        }
        json.dump(promo, f)
        f.flush()

        path = Path(f.name)

    try:
        is_valid, reason = validate_promotion(path, DEFAULT_REGISTRY)
        assert not is_valid
        assert "maximum" in reason.lower()
    finally:
        path.unlink()


def test_validate_negative_fitness():
    """Test validation fails for negative fitness."""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        promo = {
            "schema": "v1",
            "id": "test_promo_004",
            "timestamp": 1234567890,
            "fitness": -0.5,
            "changes": {}
        }
        json.dump(promo, f)
        f.flush()

        path = Path(f.name)

    try:
        is_valid, reason = validate_promotion(path, DEFAULT_REGISTRY)
        assert not is_valid
        assert "negative" in reason.lower()
    finally:
        path.unlink()


def test_create_ack_accepted():
    """Test ACK creation for accepted promotion."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir_path = Path(tmpdir)
        promo_path = tmpdir_path / "test_promo_005.json"
        promo_path.write_text('{"id": "test_promo_005"}')

        # Override ACK_DIR for test
        import src.kloros.orchestration.promotion_daemon as pd
        orig_ack_dir = pd.ACK_DIR
        pd.ACK_DIR = tmpdir_path

        try:
            ack_path = create_ack(
                promo_path,
                accepted=True,
                phase_epoch="test_epoch",
                phase_sha="abc123",
                reason=""
            )

            assert ack_path.exists()

            # Check content
            with open(ack_path, 'r') as f:
                ack_data = json.load(f)

            assert ack_data["promotion_id"] == "test_promo_005"
            assert ack_data["accepted"] is True
            assert ack_data["phase_epoch"] == "test_epoch"
            assert ack_data["phase_sha"] == "abc123"
            assert "rejection_reason" not in ack_data

        finally:
            pd.ACK_DIR = orig_ack_dir


def test_create_ack_rejected():
    """Test ACK creation for rejected promotion."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir_path = Path(tmpdir)
        promo_path = tmpdir_path / "test_promo_006.json"
        promo_path.write_text('{"id": "test_promo_006"}')

        # Override ACK_DIR for test
        import src.kloros.orchestration.promotion_daemon as pd
        orig_ack_dir = pd.ACK_DIR
        pd.ACK_DIR = tmpdir_path

        try:
            ack_path = create_ack(
                promo_path,
                accepted=False,
                phase_epoch="test_epoch",
                phase_sha="abc123",
                reason="Out of bounds"
            )

            assert ack_path.exists()

            # Check content
            with open(ack_path, 'r') as f:
                ack_data = json.load(f)

            assert ack_data["promotion_id"] == "test_promo_006"
            assert ack_data["accepted"] is False
            assert ack_data["rejection_reason"] == "Out of bounds"

        finally:
            pd.ACK_DIR = orig_ack_dir
