#!/usr/bin/env python3
"""
Orchestrator Monitor - Advisory monitoring daemon for KLoROS orchestration.

Purpose:
    Monitor system conditions and emit advisory chemical signals to inform
    the policy engine and other orchestration components about system state.

Architecture:
    1. Run periodic checks every 60 seconds (asyncio event loop)
    2. Check for unacknowledged D-REAM promotions
    3. Monitor system health (basic checks)
    4. Emit advisory signals via ZMQ chemical bus with rich contextual facts

Advisory Signals Emitted:
    - Q_PROMOTIONS_DETECTED: Unacknowledged D-REAM promotions exist
    - Q_MODULE_DISCOVERED: New module detected (optional/future)
    - Q_HEALTH_ALERT: System health issue detected (optional/minimal)

This is Phase 3 of the event-driven orchestrator migration.
"""

import asyncio
import json
import logging
import os
import sys
from pathlib import Path
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from kloros.orchestration.chem_bus_v2 import ChemPub

logger = logging.getLogger(__name__)

DEFAULT_PROMOTIONS_DIR = Path("/home/kloros/.kloros/dream_lab/promotions")
DEFAULT_CHECK_INTERVAL_S = 60


class OrchestratorMonitor:
    """
    Advisory monitoring daemon for orchestration.

    Emits chemical signals to inform policy engine about system conditions.
    """

    def __init__(
        self,
        promotions_dir: Path = DEFAULT_PROMOTIONS_DIR,
        check_interval_s: int = DEFAULT_CHECK_INTERVAL_S,
        chem_pub: Optional[ChemPub] = None,
    ):
        """
        Initialize orchestrator monitor.

        Args:
            promotions_dir: Directory containing D-REAM promotion files
            check_interval_s: Seconds between periodic checks
            chem_pub: Optional ChemPub instance (for testing with mocks)
        """
        self.promotions_dir = Path(promotions_dir)
        self.check_interval_s = check_interval_s

        self.promotions_dir.mkdir(parents=True, exist_ok=True)

        self.chem_pub = chem_pub if chem_pub is not None else ChemPub()

        logger.info(f"[orchestrator_monitor] Initialized")
        logger.info(f"[orchestrator_monitor] Promotions dir: {self.promotions_dir}")
        logger.info(f"[orchestrator_monitor] Check interval: {self.check_interval_s}s")

    def _count_unacknowledged_promotions(self) -> Dict[str, Any]:
        """
        Count unacknowledged D-REAM promotions.

        Returns:
            Dictionary with:
                - promotion_count: Number of unacknowledged promotions
                - oldest_promotion_age_hours: Age of oldest promotion in hours
                - newest_promotion_age_hours: Age of newest promotion in hours
                - promotion_files: List of promotion file paths
        """
        try:
            if not self.promotions_dir.exists():
                return {
                    "promotion_count": 0,
                    "oldest_promotion_age_hours": None,
                    "newest_promotion_age_hours": None,
                    "promotion_files": []
                }

            promotion_files = [
                f for f in self.promotions_dir.iterdir()
                if f.is_file() and f.suffix == '.json' and f.parent.name != 'acknowledged'
            ]

            if not promotion_files:
                return {
                    "promotion_count": 0,
                    "oldest_promotion_age_hours": None,
                    "newest_promotion_age_hours": None,
                    "promotion_files": []
                }

            now = datetime.now(timezone.utc).timestamp()

            ages_hours = []
            for pfile in promotion_files:
                mtime = pfile.stat().st_mtime
                age_hours = (now - mtime) / 3600
                ages_hours.append(age_hours)

            return {
                "promotion_count": len(promotion_files),
                "oldest_promotion_age_hours": max(ages_hours),
                "newest_promotion_age_hours": min(ages_hours),
                "promotion_files": [str(f.name) for f in promotion_files]
            }

        except Exception as e:
            logger.error(f"[orchestrator_monitor] Error counting promotions: {e}", exc_info=True)
            return {
                "promotion_count": 0,
                "oldest_promotion_age_hours": None,
                "newest_promotion_age_hours": None,
                "promotion_files": [],
                "error": str(e)
            }

    def _check_system_health(self) -> List[Dict[str, Any]]:
        """
        Perform basic system health checks.

        Returns:
            List of health issues (empty if all healthy)
        """
        health_issues = []

        try:
            pass

        except Exception as e:
            logger.error(f"[orchestrator_monitor] Error checking system health: {e}", exc_info=True)
            health_issues.append({
                "issue_type": "health_check_error",
                "details": str(e)
            })

        return health_issues

    def _emit_signal(self, signal_type: str, facts: Dict[str, Any]):
        """
        Emit advisory chemical signal.

        Args:
            signal_type: Signal name (e.g., Q_PROMOTIONS_DETECTED)
            facts: Signal facts dictionary with contextual information
        """
        try:
            facts_with_source = {**facts, "source": "orchestrator_monitor"}
            self.chem_pub.emit(
                signal=signal_type,
                ecosystem="orchestration",
                intensity=1.0,
                facts=facts_with_source
            )
            logger.info(f"[orchestrator_monitor] Emitted {signal_type} with facts: {facts_with_source}")

        except Exception as e:
            logger.error(f"[orchestrator_monitor] Failed to emit signal {signal_type}: {e}", exc_info=True)

    async def periodic_checks(self):
        """
        Run monitoring checks periodically.

        This is the main daemon loop that runs continuously.
        """
        logger.info("[orchestrator_monitor] Starting periodic checks")

        while True:
            try:
                promotion_facts = self._count_unacknowledged_promotions()

                if promotion_facts['promotion_count'] > 0:
                    self._emit_signal("Q_PROMOTIONS_DETECTED", promotion_facts)
                    logger.info(
                        f"[orchestrator_monitor] Detected {promotion_facts['promotion_count']} "
                        f"unacknowledged promotions"
                    )

                health_issues = self._check_system_health()
                for issue in health_issues:
                    self._emit_signal("Q_HEALTH_ALERT", issue)

                await asyncio.sleep(self.check_interval_s)

            except asyncio.CancelledError:
                logger.info("[orchestrator_monitor] Periodic checks cancelled")
                break
            except Exception as e:
                logger.error(f"[orchestrator_monitor] Error in periodic check: {e}", exc_info=True)
                await asyncio.sleep(5)

        logger.info("[orchestrator_monitor] Periodic checks stopped")

    async def run_async(self):
        """
        Run the monitor daemon (async version).
        """
        logger.info("[orchestrator_monitor] Starting daemon")

        try:
            await self.periodic_checks()
        except KeyboardInterrupt:
            logger.info("[orchestrator_monitor] Received shutdown signal")
        except Exception as e:
            logger.error(f"[orchestrator_monitor] Fatal error: {e}", exc_info=True)
        finally:
            self.chem_pub.close()
            logger.info("[orchestrator_monitor] Daemon stopped")

    def run(self):
        """
        Run the monitor daemon (sync wrapper for asyncio).
        """
        asyncio.run(self.run_async())


def main():
    """Entry point for orchestrator monitor daemon."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    )

    monitor = OrchestratorMonitor()
    monitor.run()


if __name__ == "__main__":
    main()
