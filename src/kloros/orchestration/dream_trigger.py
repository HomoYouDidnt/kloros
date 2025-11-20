#!/usr/bin/env python3
"""
D-REAM Trigger - Wrapper for running D-REAM one-shot cycles.

Executes D-REAM evolutionary optimization with lock protection.
"""

import os
import json
import subprocess
import time
import uuid
import logging
from pathlib import Path
from dataclasses import dataclass
from typing import Optional

from .state_manager import acquire, release

logger = logging.getLogger(__name__)

DREAM_TIMEOUT_S = 30 * 60  # 30 minutes default
PROMOTIONS_DIR = Path("/home/kloros/artifacts/dream/promotions")


@dataclass
class DreamResult:
    """Result of D-REAM execution."""
    exit_code: int
    generation: Optional[int]
    promotion_path: Optional[Path]
    telemetry_path: Optional[Path]
    run_tag: str
    duration_s: float


def run_once(topic: Optional[str] = None, run_tag: Optional[str] = None, timeout_s: int = DREAM_TIMEOUT_S) -> DreamResult:
    """
    Run a single D-REAM cycle with lock protection.

    Args:
        topic: Optional topic filter for experiments
        run_tag: Unique identifier for this run (auto-generated if not provided)
        timeout_s: Maximum execution time (default: 30 minutes)

    Returns:
        DreamResult with execution details

    Raises:
        RuntimeError: If D-REAM execution fails
    """
    lock = acquire("dream")
    start_time = time.time()

    if not run_tag:
        run_tag = f"{int(time.time())}-{uuid.uuid4().hex[:8]}"

    try:
        # Build command (note: D-REAM runner doesn't support --run-tag or --topic)
        cmd = [
            "python3", "-m", "src.dream.runner",
            "--config", "/home/kloros/src/dream/config/dream.yaml",
            "--logdir", "/home/kloros/logs/dream",
            "--epochs-per-cycle", "1",
            "--sleep-between-cycles", "0"
        ]

        # Keep run_tag for internal tracking and log file identification
        logger.info(f"Starting D-REAM one-shot (internal_tag={run_tag}, timeout={timeout_s}s)")

        # Execute D-REAM
        result = subprocess.run(
            cmd,
            cwd="/home/kloros",
            capture_output=True,
            text=True,
            timeout=timeout_s,
            env={**os.environ, "KLR_ORCHESTRATION_MODE": "enabled"}
        )

        duration_s = time.time() - start_time

        if result.returncode != 0:
            logger.error(f"D-REAM failed with exit code {result.returncode}")
            logger.error(f"STDOUT: {result.stdout}")
            logger.error(f"STDERR: {result.stderr}")
            return DreamResult(
                exit_code=result.returncode,
                generation=None,
                promotion_path=None,
                telemetry_path=None,
                run_tag=run_tag,
                duration_s=duration_s
            )

        # Look for newest promotion file
        promotion_path = _find_latest_promotion(run_tag)

        # Extract generation number from output
        generation = _extract_generation(result.stdout, result.stderr)

        # Find telemetry path
        telemetry_path = Path("/home/kloros/logs/dream") / f"runner_{run_tag}.log"
        if not telemetry_path.exists():
            telemetry_path = None

        logger.info(f"D-REAM one-shot completed in {duration_s:.1f}s (generation={generation})")

        return DreamResult(
            exit_code=0,
            generation=generation,
            promotion_path=promotion_path,
            telemetry_path=telemetry_path,
            run_tag=run_tag,
            duration_s=duration_s
        )

    except subprocess.TimeoutExpired:
        logger.error(f"D-REAM timeout after {timeout_s}s")
        return DreamResult(
            exit_code=124,  # Standard timeout exit code
            generation=None,
            promotion_path=None,
            telemetry_path=None,
            run_tag=run_tag,
            duration_s=time.time() - start_time
        )
    except Exception as e:
        logger.error(f"D-REAM execution error: {e}")
        return DreamResult(
            exit_code=1,
            generation=None,
            promotion_path=None,
            telemetry_path=None,
            run_tag=run_tag,
            duration_s=time.time() - start_time
        )
    finally:
        release(lock)


def _find_latest_promotion(run_tag: str) -> Optional[Path]:
    """Find newest promotion file matching run_tag."""
    if not PROMOTIONS_DIR.exists():
        return None

    # Look for files with run_tag or created very recently
    candidates = []
    cutoff_time = time.time() - 60  # Last minute

    for promo_file in PROMOTIONS_DIR.glob("*.json"):
        # Check if file is recent
        if promo_file.stat().st_mtime > cutoff_time:
            candidates.append(promo_file)

    if not candidates:
        return None

    # Return most recent
    return max(candidates, key=lambda p: p.stat().st_mtime)


def _extract_generation(stdout: str, stderr: str) -> Optional[int]:
    """Extract generation number from D-REAM output."""
    combined = stdout + "\n" + stderr

    import re
    patterns = [
        r'generation[:\s]+(\d+)',
        r'Gen:\s*(\d+)',
        r'epoch[:\s]+(\d+)',
    ]

    for pattern in patterns:
        match = re.search(pattern, combined, re.IGNORECASE)
        if match:
            return int(match.group(1))

    return None
