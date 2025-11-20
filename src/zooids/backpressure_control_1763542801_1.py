"""
Auto-generated backpressure controller - threshold=0.72, recovery=0.26, timeout=30s.
"""
import time
import logging
from kloros.orchestration.chem_bus_v2 import ChemPub, ChemSub

PRESSURE_THRESHOLD = 0.72
RECOVERY_RATE = 0.26
CIRCUIT_BREAKER_TIMEOUT_SEC = 30
POLL_INTERVAL = 3.9
BATCH_SIZE = 10
TIMEOUT_SEC = 10
LOG_LEVEL = "DEBUG"

logging.basicConfig(level=LOG_LEVEL)
logger = logging.getLogger(__name__)


def main():
    pub = ChemPub()
    sub = ChemSub()
    pressure_level = 0.0
    circuit_open = False
    circuit_open_ts = None

    logger.info(f"Backpressure controller started: threshold={PRESSURE_THRESHOLD}, recovery={RECOVERY_RATE}")

    while True:
        try:
            signals = sub.poll_batch(max_count=10, timeout_sec=0.1)
            pressure_signals = sum(1 for s in signals if s.get("type") == "PRESSURE")

            if pressure_signals > 0:
                pressure_level = min(1.0, pressure_level + 0.1 * pressure_signals)
            else:
                pressure_level = max(0.0, pressure_level - RECOVERY_RATE)

            if pressure_level > PRESSURE_THRESHOLD and not circuit_open:
                logger.warning(f"Pressure {pressure_level:.2%} exceeds threshold - opening circuit breaker")
                circuit_open = True
                circuit_open_ts = time.time()
                pub.signal("CIRCUIT_OPEN")

            if circuit_open:
                if time.time() - circuit_open_ts > CIRCUIT_BREAKER_TIMEOUT_SEC:
                    if pressure_level < PRESSURE_THRESHOLD * 0.5:
                        logger.info(f"Pressure {pressure_level:.2%} recovered - closing circuit breaker")
                        circuit_open = False
                        circuit_open_ts = None
                        pub.signal("CIRCUIT_CLOSED")
                    else:
                        logger.warning(f"Pressure {pressure_level:.2%} still high - circuit remains open")
                        circuit_open_ts = time.time()
            else:
                logger.debug(f"Pressure level: {pressure_level:.2%}")

            time.sleep(POLL_INTERVAL)

        except Exception as e:
            logger.error(f"Backpressure controller error: {e}")
            time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    main()
