"""
Auto-generated latency monitor - 3.17s poll, 100ms P95 threshold.
"""
import time
import logging
from kloros.orchestration.chem_bus_v2 import ChemPub

POLL_INTERVAL = 3.17
P95_THRESHOLD_MS = 100
WINDOW_SIZE = 50
ALERT_PERCENTILE = 95
BATCH_SIZE = 100
TIMEOUT_SEC = 60
LOG_LEVEL = "INFO"

logging.basicConfig(level=LOG_LEVEL)
logger = logging.getLogger(__name__)


def main():
    pub = ChemPub()
    latencies = []

    logger.info(f"Latency monitor started: poll={POLL_INTERVAL}s, p95_threshold={P95_THRESHOLD_MS}ms")

    while True:
        try:
            start_ts = time.time()

            latencies.append(time.time() - start_ts)
            if len(latencies) > WINDOW_SIZE:
                latencies.pop(0)

            if len(latencies) >= WINDOW_SIZE:
                sorted_latencies = sorted(latencies)
                p95_idx = int(len(sorted_latencies) * (ALERT_PERCENTILE / 100.0))
                p95_value = sorted_latencies[p95_idx] * 1000

                if p95_value > P95_THRESHOLD_MS:
                    logger.warning(f"P{ALERT_PERCENTILE} latency {p95_value:.2f}ms exceeds threshold {P95_THRESHOLD_MS}ms")
                    pub.signal("PRESSURE")
                else:
                    logger.debug(f"P{ALERT_PERCENTILE} latency {p95_value:.2f}ms OK")

            time.sleep(POLL_INTERVAL)

        except Exception as e:
            logger.error(f"Monitor error: {e}")
            time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    main()
