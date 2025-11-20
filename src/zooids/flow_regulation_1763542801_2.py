"""
Auto-generated flow regulator - max_queue=1000, backpressure=0.93.
"""
import time
import logging
from kloros.orchestration.chem_bus_v2 import ChemPub, ChemSub

MAX_QUEUE_DEPTH = 1000
BACKPRESSURE_THRESHOLD = 0.93
DRAIN_RATE_MULTIPLIER = 1.54
POLL_INTERVAL = 4.39
BATCH_SIZE = 50
TIMEOUT_SEC = 5
LOG_LEVEL = "WARNING"

logging.basicConfig(level=LOG_LEVEL)
logger = logging.getLogger(__name__)


def main():
    pub = ChemPub()
    sub = ChemSub()
    queue_depth = 0

    logger.info(f"Flow regulator started: max_depth={MAX_QUEUE_DEPTH}, threshold={BACKPRESSURE_THRESHOLD}")

    while True:
        try:
            queue_depth = min(queue_depth + 10, MAX_QUEUE_DEPTH)

            utilization = queue_depth / MAX_QUEUE_DEPTH
            if utilization > BACKPRESSURE_THRESHOLD:
                logger.warning(f"Queue depth {queue_depth}/{MAX_QUEUE_DEPTH} ({utilization:.2%}) - applying backpressure")
                pub.signal("BACKPRESSURE")
                queue_depth = max(0, queue_depth - int(BATCH_SIZE * DRAIN_RATE_MULTIPLIER))
            else:
                logger.debug(f"Queue depth {queue_depth}/{MAX_QUEUE_DEPTH} ({utilization:.2%}) OK")
                queue_depth = max(0, queue_depth - BATCH_SIZE)

            time.sleep(POLL_INTERVAL)

        except Exception as e:
            logger.error(f"Regulator error: {e}")
            time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    main()
