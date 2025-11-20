#!/usr/bin/env python3
"""
Promotion Daemon - Validation and acknowledgment of D-REAM promotions.

Scans promotions, validates schema and bounds, creates ACK files.
"""

import json
import time
import logging
from pathlib import Path
from typing import Optional, Tuple
from dataclasses import dataclass

logger = logging.getLogger(__name__)

PROMOTIONS_DIR = Path("/home/kloros/artifacts/dream/promotions")
ACK_DIR = Path("/home/kloros/artifacts/dream/promotions_ack")


@dataclass
class PromotionRegistry:
    """Registry of allowed parameter bounds."""
    min_values: dict[str, float]
    max_values: dict[str, float]


# Default registry (can be loaded from config)
DEFAULT_REGISTRY = PromotionRegistry(
    min_values={
        "learning_rate": 0.0001,
        "batch_size": 1,
        "temperature": 0.1,
        "context_window": 1000,
    },
    max_values={
        "learning_rate": 0.1,
        "batch_size": 128,
        "temperature": 2.0,
        "context_window": 32000,
    }
)


def validate_promotion(promo_path: Path, registry: Optional[PromotionRegistry] = None) -> Tuple[bool, str]:
    """
    Validate promotion file.

    Args:
        promo_path: Path to promotion JSON file
        registry: Parameter bounds registry (uses default if not provided)

    Returns:
        (is_valid, reason) tuple
    """
    if registry is None:
        registry = DEFAULT_REGISTRY

    try:
        with open(promo_path, 'r') as f:
            promo = json.load(f)

        # Check schema version
        schema = promo.get("schema")
        if not schema:
            return False, "Missing schema field"

        if schema not in ["v1", "v2"]:
            return False, f"Unsupported schema version: {schema}"

        # Check required fields
        required = ["id", "timestamp", "fitness", "changes"]
        for field in required:
            if field not in promo:
                return False, f"Missing required field: {field}"

        # Validate fitness
        fitness = promo.get("fitness")
        if not isinstance(fitness, (int, float)):
            return False, f"Invalid fitness type: {type(fitness)}"

        if fitness < 0:
            return False, f"Negative fitness: {fitness}"

        # Validate changes
        changes = promo.get("changes", {})
        if not isinstance(changes, dict):
            return False, "Changes must be a dict"

        # Bounds checking
        for param, value in changes.items():
            if not isinstance(value, (int, float)):
                return False, f"Non-numeric value for {param}: {value}"

            # Check against registry
            if param in registry.min_values:
                if value < registry.min_values[param]:
                    return False, f"{param} below minimum: {value} < {registry.min_values[param]}"

            if param in registry.max_values:
                if value > registry.max_values[param]:
                    return False, f"{param} above maximum: {value} > {registry.max_values[param]}"

        return True, "valid"

    except json.JSONDecodeError as e:
        return False, f"JSON decode error: {e}"
    except Exception as e:
        return False, f"Validation error: {e}"


def create_ack(promo_path: Path, accepted: bool, phase_epoch: str, phase_sha: str, reason: str = "") -> Path:
    """
    Create acknowledgment file for promotion.

    Args:
        promo_path: Path to promotion file
        accepted: Whether promotion was accepted
        phase_epoch: PHASE epoch ID that validated this
        phase_sha: SHA256 of PHASE report
        reason: Rejection reason (if not accepted)

    Returns:
        Path to created ACK file
    """
    ACK_DIR.mkdir(parents=True, exist_ok=True)

    ack_payload = {
        "promotion_id": promo_path.stem,
        "accepted": accepted,
        "phase_epoch": phase_epoch,
        "phase_sha": phase_sha,
        "ts": int(time.time()),
        "schema": "v1"
    }

    if not accepted and reason:
        ack_payload["rejection_reason"] = reason

    # Write ACK
    ack_path = ACK_DIR / f"{promo_path.stem}_ack.json"
    with open(ack_path, 'w') as f:
        json.dump(ack_payload, f, indent=2)

    logger.info(f"Created ACK for {promo_path.name}: accepted={accepted}")
    return ack_path


def scan_unacked_promotions() -> list[Path]:
    """
    Find promotions that don't have ACK files yet.

    Returns:
        List of promotion paths needing acknowledgment
    """
    if not PROMOTIONS_DIR.exists():
        return []

    ACK_DIR.mkdir(parents=True, exist_ok=True)

    unacked = []
    for promo_file in PROMOTIONS_DIR.glob("*.json"):
        ack_file = ACK_DIR / f"{promo_file.stem}_ack.json"
        if not ack_file.exists():
            unacked.append(promo_file)

    return unacked
