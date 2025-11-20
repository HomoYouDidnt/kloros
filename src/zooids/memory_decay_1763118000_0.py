"""
Auto-generated memory decay - interval=120min, threshold=0.9, half_life=24h.
"""
import time
import logging
import json
import pathlib
from datetime import datetime, timezone

UPDATE_INTERVAL_MINUTES = 120
DELETION_THRESHOLD = 0.9
DECAY_HALF_LIFE_HOURS = 24
LOG_LEVEL = "DEBUG"

logging.basicConfig(level=LOG_LEVEL)
logger = logging.getLogger(__name__)


def calculate_decay(created_ts, now_ts):
    """Calculate decay factor based on age and half-life."""
    age_hours = (now_ts - created_ts) / 3600
    decay = 2 ** (-age_hours / DECAY_HALF_LIFE_HOURS)
    return decay


def scan_and_decay():
    """Scan memory-tracked items and decay their scores."""
    try:
        memory_file = pathlib.Path.home() / ".kloros/memory_decay.jsonl"
        if not memory_file.exists():
            logger.info("No memory file to decay")
            return

        decayed_count = 0
        deleted_count = 0
        now = time.time()

        entries = []
        with memory_file.open('r') as f:
            for line in f:
                entry = json.loads(line)
                created = entry.get("created_ts", now)
                decay_factor = calculate_decay(created, now)

                if decay_factor < DELETION_THRESHOLD:
                    deleted_count += 1
                    logger.debug(f"Deleting decayed entry: {entry.get('id', 'unknown')}")
                else:
                    entry["decay_factor"] = decay_factor
                    entries.append(entry)
                    decayed_count += 1

        # Rewrite file with non-deleted entries
        with memory_file.open('w') as f:
            for entry in entries:
                f.write(json.dumps(entry) + "\n")

        logger.info(f"Memory decay complete: {decayed_count} updated, {deleted_count} deleted")
    except Exception as e:
        logger.error(f"Memory decay error: {e}")


def main():
    logger.info(f"Memory decay started: interval={UPDATE_INTERVAL_MINUTES}min, threshold={DELETION_THRESHOLD}, half_life={DECAY_HALF_LIFE_HOURS}h")

    while True:
        try:
            scan_and_decay()
            time.sleep(UPDATE_INTERVAL_MINUTES * 60)
        except Exception as e:
            logger.error(f"Memory decay loop error: {e}")
            time.sleep(UPDATE_INTERVAL_MINUTES * 60)


if __name__ == "__main__":
    main()
