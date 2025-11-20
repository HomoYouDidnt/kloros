# phase_adapter.py — PHASE → fitness ledger → bioreactor trigger
from __future__ import annotations
import subprocess
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# Import fitness ledger
import sys
sys.path.insert(0, str(Path(__file__).parents[1]))
from kloros.observability.fitness_ledger import record_outcome, compute_niche_pressure

def record_phase_outcome(
    incident_id: str,
    zooid: str,
    niche: str,
    ok: bool,
    ttr_ms: Optional[float] = None
):
    """
    Record PHASE test outcome to fitness ledger.

    Called after PHASE completes testing a zooid implementation.
    """
    record_outcome(
        incident_id=incident_id,
        zooid=zooid,
        niche=niche,
        ok=ok,
        ttr_ms=ttr_ms
    )
    logger.info(f"PHASE outcome recorded: {zooid} niche={niche} ok={ok}")

def after_phase_batch(ecosystem: str, failure_threshold: float = 0.3):
    """
    Run after PHASE batch completes.

    Triggers bioreactor if recent failure rate exceeds threshold.

    Args:
        ecosystem: Ecosystem to check (e.g., "queue_management")
        failure_threshold: Pressure threshold to trigger evolution (0.0-1.0)
    """
    # Check pressure for each niche in ecosystem
    niches = _get_niches_for_ecosystem(ecosystem)

    high_pressure_niches = []
    for niche in niches:
        pressure = compute_niche_pressure(ecosystem, niche, window_s=3600)
        if pressure > failure_threshold:
            high_pressure_niches.append((niche, pressure))
            logger.warning(f"High pressure detected: {niche} pressure={pressure:.2f}")

    if high_pressure_niches:
        logger.warning(f"Triggering bioreactor for {len(high_pressure_niches)} high-pressure niches:")
        for niche, pressure in high_pressure_niches:
            logger.warning(f"  - {niche}: pressure={pressure:.3f}")

        try:
            # Pass ecosystem and threshold to bioreactor
            result = subprocess.run(
                [
                    "python3",
                    str(Path(__file__).parent / "bioreactor.py"),
                    ecosystem,
                    str(failure_threshold)
                ],
                capture_output=True,
                text=True,
                timeout=120  # Increased timeout for evolution
            )

            if result.returncode == 0:
                logger.info(f"✅ Bioreactor completed successfully")
                logger.info(f"Bioreactor output:\n{result.stdout}")
            else:
                logger.error(f"❌ Bioreactor failed with code {result.returncode}")
                logger.error(f"stderr: {result.stderr}")
                logger.error(f"stdout: {result.stdout}")

        except subprocess.TimeoutExpired:
            logger.error("❌ Bioreactor timed out after 120s")
        except Exception as e:
            logger.error(f"❌ Bioreactor trigger failed: {e}")
            import traceback
            logger.error(traceback.format_exc())
    else:
        max_pressure = max([p for _, p in high_pressure_niches], default=0.0) if high_pressure_niches else 0.0
        logger.info(f"✅ All niches stable, skipping bioreactor (max pressure: {max_pressure:.3f} < {failure_threshold})")

def _get_niches_for_ecosystem(ecosystem: str) -> list[str]:
    """Get list of niches for an ecosystem from registry."""
    import json
    registry_path = Path.home() / ".kloros/registry/niche_map.json"

    if not registry_path.exists():
        return []

    registry = json.loads(registry_path.read_text())
    return list(registry.get("ecosystems", {}).get(ecosystem, {}).get("niches", {}).keys())
