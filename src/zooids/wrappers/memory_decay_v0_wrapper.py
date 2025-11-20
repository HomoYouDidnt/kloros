"""
Zooid wrapper for decay_daemon (v0 - legacy delegation).

This is a first-generation zooid that delegates to the legacy
DecayDaemon implementation. Future generations can modify
or replace internal behavior while maintaining the zooid interface.
"""

import time
from pathlib import Path
from typing import Dict, Any, Optional

from src.kloros_memory.decay_daemon import DecayDaemon


class DecayZooid:
    """
    Wrapper zooid for memory_decay niche.

    Genome metadata:
    - genome_id: memory_decay_v0_wrapper
    - parent_lineage: []
    - niche: memory_decay
    - generation: 0 (wrapper)
    """

    def __init__(self):
        """Initialize the zooid by wrapping legacy implementation."""
        self.genome_id = "memory_decay_v0_wrapper"
        self.niche = "memory_decay"
        self.generation = 0

        self._impl = DecayDaemon(update_interval_minutes=60, store=None, config=None)

        self.poll_interval_sec = 60.0
        self.batch_size = 10
        self.timeout_sec = 30
        self.log_level = "INFO"

    def tick(self, now: float, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Execute one tick of the zooid behavior.

        This v0 implementation delegates directly to the legacy code.

        Args:
            now: Current timestamp
            context: Optional context dictionary

        Returns:
            Dictionary with tick results
        """
        try:
            result = self._impl.start()

            return {
                "status": "success",
                "timestamp": now,
                "genome_id": self.genome_id,
                "result": result if result else {},
            }

        except Exception as e:
            return {
                "status": "error",
                "timestamp": now,
                "genome_id": self.genome_id,
                "error": str(e),
            }

    def main_loop(self):
        """
        Main execution loop for standalone zooid operation.

        This allows the zooid to run independently as a service.
        """
        print(f"[{self.genome_id}] Starting zooid loop for niche: {self.niche}")

        while True:
            try:
                now = time.time()
                result = self.tick(now)

                if result["status"] == "success":
                    print(f"[{self.genome_id}] Tick completed successfully")
                else:
                    print(f"[{self.genome_id}] Tick failed: {result.get('error')}")

                time.sleep(self.poll_interval_sec)

            except KeyboardInterrupt:
                print(f"[{self.genome_id}] Shutdown requested")
                break
            except Exception as e:
                print(f"[{self.genome_id}] Unexpected error: {e}")
                time.sleep(self.poll_interval_sec)


if __name__ == "__main__":
    zooid = DecayZooid()
    zooid.main_loop()
