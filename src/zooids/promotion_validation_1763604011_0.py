"""
Auto-generated promotion validation - scan=120s, max_fit=0.91, min_fit=0.47, retries=1.
"""
import time
import logging
from kloros.registry.lifecycle_registry import LifecycleRegistry

SCAN_INTERVAL_SEC = 120
MAX_FITNESS_THRESHOLD = 0.91
MIN_FITNESS_THRESHOLD = 0.47
VALIDATION_RETRIES = 1
LOG_LEVEL = "DEBUG"

logging.basicConfig(level=LOG_LEVEL)
logger = logging.getLogger(__name__)


def validate_probation_zooids():
    """Validate zooids in PROBATION state and recommend graduation or demotion."""
    try:
        reg_mgr = LifecycleRegistry()
        reg = reg_mgr.load()

        probation_count = 0
        promotion_candidates = []
        demotion_candidates = []

        for name, z in reg.get("zooids", {}).items():
            if z.get("lifecycle_state") != "PROBATION":
                continue

            probation_count += 1
            phase = z.get("phase", {})
            fitness = phase.get("fitness_mean", 0.0)
            evidence = phase.get("evidence", 0)

            if fitness >= MAX_FITNESS_THRESHOLD and evidence >= 3:
                promotion_candidates.append((name, fitness))
            elif fitness <= MIN_FITNESS_THRESHOLD and evidence >= 2:
                demotion_candidates.append((name, fitness))

        logger.info(f"Probation validation: {probation_count} total, {len(promotion_candidates)} promotion candidates, {len(demotion_candidates)} demotion candidates")

        for name, fitness in promotion_candidates:
            logger.info(f"  Promotion candidate: {name} (fitness={fitness:.3f})")

        for name, fitness in demotion_candidates:
            logger.warning(f"  Demotion candidate: {name} (fitness={fitness:.3f})")

    except Exception as e:
        logger.error(f"Promotion validation error: {e}")


def main():
    logger.info(f"Promotion validation started: scan_interval={SCAN_INTERVAL_SEC}s, thresholds=[{MIN_FITNESS_THRESHOLD}, {MAX_FITNESS_THRESHOLD}]")

    while True:
        try:
            validate_probation_zooids()
            time.sleep(SCAN_INTERVAL_SEC)
        except Exception as e:
            logger.error(f"Promotion validation loop error: {e}")
            time.sleep(SCAN_INTERVAL_SEC)


if __name__ == "__main__":
    main()
