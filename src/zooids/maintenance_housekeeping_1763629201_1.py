"""
Auto-generated maintenance housekeeping - interval=12.0h, daily=4:00, mem_cleanup=True, py_cache=True.
"""
import time
import logging
import gc
import shutil
import pathlib
from datetime import datetime, timezone

MAINTENANCE_INTERVAL_HOURS = 12.0
DAILY_MAINTENANCE_HOUR = 4
MEMORY_CLEANUP_ENABLED = True
PYTHON_CACHE_CLEANUP_ENABLED = True
POLL_INTERVAL_SEC = 300  # Check every 5 minutes
LOG_LEVEL = "WARNING"

logging.basicConfig(level=LOG_LEVEL)
logger = logging.getLogger(__name__)


def cleanup_python_caches():
    """Clean up Python __pycache__ directories."""
    if not PYTHON_CACHE_CLEANUP_ENABLED:
        logger.debug("Python cache cleanup disabled")
        return 0

    cleaned = 0
    try:
        kloros_root = pathlib.Path("/home/kloros/src")
        for pycache_dir in kloros_root.rglob("__pycache__"):
            try:
                shutil.rmtree(pycache_dir)
                cleaned += 1
                logger.debug(f"Removed {pycache_dir}")
            except Exception as e:
                logger.warning(f"Failed to remove {pycache_dir}: {e}")
        logger.info(f"Python cache cleanup: removed {cleaned} directories")
    except Exception as e:
        logger.error(f"Python cache cleanup error: {e}")
    return cleaned


def cleanup_memory():
    """Force garbage collection to reclaim memory."""
    if not MEMORY_CLEANUP_ENABLED:
        logger.debug("Memory cleanup disabled")
        return 0

    try:
        collected = gc.collect()
        logger.info(f"Memory cleanup: collected {collected} objects")
        return collected
    except Exception as e:
        logger.error(f"Memory cleanup error: {e}")
        return 0


def should_run_daily_maintenance():
    """Check if it's time for daily scheduled maintenance."""
    now = datetime.now(timezone.utc)
    return now.hour == DAILY_MAINTENANCE_HOUR and now.minute < 5


def main():
    logger.info(f"Maintenance housekeeping started: interval={MAINTENANCE_INTERVAL_HOURS}h, daily_hour={DAILY_MAINTENANCE_HOUR}")
    logger.info(f"Memory cleanup: {MEMORY_CLEANUP_ENABLED}, Python cache cleanup: {PYTHON_CACHE_CLEANUP_ENABLED}")

    last_maintenance_ts = 0
    daily_maintenance_done_today = False

    while True:
        try:
            now = time.time()
            hours_since_last = (now - last_maintenance_ts) / 3600

            # Check for daily scheduled maintenance
            if should_run_daily_maintenance() and not daily_maintenance_done_today:
                logger.info("Running daily scheduled maintenance")
                cleanup_memory()
                cleanup_python_caches()
                daily_maintenance_done_today = True
                last_maintenance_ts = now

            # Reset daily flag after the maintenance hour passes
            if datetime.now(timezone.utc).hour != DAILY_MAINTENANCE_HOUR:
                daily_maintenance_done_today = False

            # Check for interval-based maintenance
            if hours_since_last >= MAINTENANCE_INTERVAL_HOURS:
                logger.info(f"Running interval maintenance ({hours_since_last:.1f}h since last)")
                cleanup_memory()
                cleanup_python_caches()
                last_maintenance_ts = now

            time.sleep(POLL_INTERVAL_SEC)

        except Exception as e:
            logger.error(f"Maintenance housekeeping error: {e}")
            time.sleep(POLL_INTERVAL_SEC)


if __name__ == "__main__":
    main()
