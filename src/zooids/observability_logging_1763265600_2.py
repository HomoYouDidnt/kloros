"""
Auto-generated observability logger - flush=3.31s, buffer=500, rotation=100MB, compression=True.
"""
import time
import logging
import json
import pathlib
import gzip
from datetime import datetime, timezone

FLUSH_INTERVAL_SEC = 3.31
BUFFER_SIZE = 500
LOG_ROTATION_MB = 100
COMPRESSION_ENABLED = True
LOG_LEVEL = "WARNING"

logging.basicConfig(level=LOG_LEVEL)
logger = logging.getLogger(__name__)


class ObservabilityLogger:
    def __init__(self):
        self.buffer = []
        self.log_path = pathlib.Path.home() / ".kloros/observability.jsonl"
        self.log_path.parent.mkdir(parents=True, exist_ok=True)

    def add_event(self, event_type, data):
        """Add an event to the buffer."""
        entry = {
            "ts": time.time(),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "event": event_type,
            "data": data
        }
        self.buffer.append(entry)

        if len(self.buffer) >= BUFFER_SIZE:
            self.flush()

    def flush(self):
        """Flush buffer to disk."""
        if not self.buffer:
            return

        try:
            with self.log_path.open('a') as f:
                for entry in self.buffer:
                    f.write(json.dumps(entry) + "\n")

            logger.debug(f"Flushed {len(self.buffer)} events to {self.log_path}")
            self.buffer = []

            # Check for rotation
            if self.log_path.stat().st_size > LOG_ROTATION_MB * 1024 * 1024:
                self.rotate_log()

        except Exception as e:
            logger.error(f"Flush error: {e}")

    def rotate_log(self):
        """Rotate log file when it exceeds size limit."""
        try:
            timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
            rotated_path = self.log_path.parent / f"observability.{timestamp}.jsonl"

            if COMPRESSION_ENABLED:
                # Compress old log
                with self.log_path.open('rb') as f_in:
                    with gzip.open(f"{rotated_path}.gz", 'wb') as f_out:
                        f_out.writelines(f_in)
                self.log_path.unlink()
                logger.info(f"Rotated and compressed log to {rotated_path}.gz")
            else:
                self.log_path.rename(rotated_path)
                logger.info(f"Rotated log to {rotated_path}")

            # Create new empty log
            self.log_path.touch()

        except Exception as e:
            logger.error(f"Log rotation error: {e}")


def main():
    logger.info(f"Observability logger started: flush_interval={FLUSH_INTERVAL_SEC}s, buffer_size={BUFFER_SIZE}, rotation={LOG_ROTATION_MB}MB")

    obs_logger = ObservabilityLogger()
    last_flush = time.time()

    # Log startup event
    obs_logger.add_event("observability_started", {
        "flush_interval_sec": FLUSH_INTERVAL_SEC,
        "buffer_size": BUFFER_SIZE,
        "log_rotation_mb": LOG_ROTATION_MB,
        "compression_enabled": COMPRESSION_ENABLED
    })

    while True:
        try:
            now = time.time()

            # Periodic flush
            if now - last_flush >= FLUSH_INTERVAL_SEC:
                obs_logger.flush()
                last_flush = now

            # Example: Log system heartbeat
            obs_logger.add_event("heartbeat", {
                "buffer_length": len(obs_logger.buffer)
            })

            time.sleep(min(FLUSH_INTERVAL_SEC, 60))

        except Exception as e:
            logger.error(f"Observability logger loop error: {e}")
            time.sleep(FLUSH_INTERVAL_SEC)


if __name__ == "__main__":
    main()
