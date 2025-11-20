"""
Auto-generated garbage collector - TTL=1800s, scan_interval=60s.
"""
import time
import logging
from kloros.orchestration.chem_bus_v2 import ChemPub

TTL_SEC = 1800
SCAN_INTERVAL_SEC = 60
BATCH_DELETE_SIZE = 10
POLL_INTERVAL = 3.88
BATCH_SIZE = 20
TIMEOUT_SEC = 5
LOG_LEVEL = "INFO"

logging.basicConfig(level=LOG_LEVEL)
logger = logging.getLogger(__name__)


def main():
    pub = ChemPub()
    items = {}
    next_scan = time.time() + SCAN_INTERVAL_SEC

    logger.info(f"Garbage collector started: ttl={TTL_SEC}s, scan_interval={SCAN_INTERVAL_SEC}s")

    while True:
        try:
            now = time.time()

            items[f"item_{int(now)}"] = now

            if now >= next_scan:
                expired = [k for k, ts in items.items() if now - ts > TTL_SEC]

                if expired:
                    batch = expired[:BATCH_DELETE_SIZE]
                    for k in batch:
                        del items[k]
                    logger.info(f"Deleted {len(batch)} expired items (total: {len(items)})")
                else:
                    logger.debug(f"No expired items (total: {len(items)})")

                next_scan = now + SCAN_INTERVAL_SEC

            time.sleep(POLL_INTERVAL)

        except Exception as e:
            logger.error(f"GC error: {e}")
            time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    main()
