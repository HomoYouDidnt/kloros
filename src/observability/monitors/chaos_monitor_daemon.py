#!/usr/bin/env python3
"""
Chaos Monitor Daemon - Watches chaos lab results for healing failures.

Replaces ChaosLabMonitor batch polling with streaming event-driven architecture.

Architecture:
- Watches chaos_history.jsonl for new entries (incremental file tailing)
- Tracks healing rates per scenario in memory
- Emits CAPABILITY_GAP signals when healing rates drop below thresholds
- Uses file position tracking (like tail -f)

Memory Profile: ~20MB (scenario stats + file position)
CPU Profile: <5% (incremental processing)
"""

import json
import logging
import os
import sys
import time
from pathlib import Path
from collections import defaultdict
from typing import Dict, Any, Optional

sys.path.insert(0, str(Path(__file__).parents[3]))

from src.orchestration.core.umn_bus import UMNPub as ChemPub
from src.orchestration.maintenance_mode import wait_for_normal_mode

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class ChaosMonitorDaemon:
    """
    Streaming chaos lab monitor daemon.

    Features:
    - Incremental file tailing (tracks file position)
    - Per-scenario healing rate tracking
    - Threshold-based signal emission
    - Low, constant memory usage
    """

    def __init__(self):
        """Initialize chaos monitor daemon."""
        self.running = True
        self.pub = ChemPub()
        self.history_file = Path("/home/kloros/.kloros/chaos_history.jsonl")
        self.last_position = 0

        # Scenario tracking (bounded - only recent data)
        self.scenario_stats = defaultdict(lambda: {
            "total": 0,
            "healed": 0,
            "scores": [],
            "last_failure_emitted": 0  # Timestamp to avoid spam
        })

        # Thresholds
        self.healing_rate_threshold = 0.3  # Alert if <30% healing
        self.score_threshold = 50  # Alert if avg score <50
        self.lookback_experiments = 20  # Keep stats for last N experiments
        self.signal_cooldown = 300  # 5 min between signals for same scenario

        self.entries_processed = 0
        self.signals_emitted = 0
        self.signals_skipped_disabled = 0

    def _is_target_disabled(self, target: str) -> bool:
        """
        Check if a chaos scenario target is for a disabled system.

        Args:
            target: Target system (e.g., "rag.synthesis", "dream.domain:cpu", "tts")

        Returns:
            True if target system is disabled, False otherwise
        """
        # Check for D-REAM targets
        if any(keyword in target.lower() for keyword in ['dream', 'rag']):
            dream_enabled = os.getenv('KLR_ENABLE_DREAM_EVOLUTION', '1') == '1'
            if not dream_enabled:
                return True

        # Check for TTS/Audio targets (TTS system not running)
        if any(keyword in target.lower() for keyword in ['tts', 'audio']):
            # TTS is not currently running (no service enabled)
            return True

        return False

    def run(self):
        """
        Main daemon loop - tail chaos_history.jsonl for new entries.

        Checks every 60 seconds for new entries (chaos experiments are infrequent).
        """
        logger.info("[chaos_monitor] Starting chaos monitor daemon (streaming mode)")
        logger.info(f"[chaos_monitor] Watching {self.history_file}")

        # Initialize file position
        if self.history_file.exists():
            self.last_position = self.history_file.stat().st_size
            logger.info(f"[chaos_monitor] Starting from end of file (position {self.last_position})")

        try:
            while self.running:
                wait_for_normal_mode()

                try:
                    self._check_new_entries()
                except Exception as e:
                    logger.error(f"[chaos_monitor] Error processing entries: {e}")

                # Chaos experiments are infrequent, check every 60s
                time.sleep(60)

        except KeyboardInterrupt:
            logger.info("[chaos_monitor] Keyboard interrupt received")
        finally:
            self.shutdown()

    def _check_new_entries(self):
        """
        Read only NEW lines from chaos_history.jsonl since last check.

        This is incremental - we don't re-read the entire file.
        """
        if not self.history_file.exists():
            return

        current_size = self.history_file.stat().st_size

        # File hasn't grown
        if current_size <= self.last_position:
            return

        # File was truncated (rotated?)
        if current_size < self.last_position:
            logger.warning("[chaos_monitor] File size decreased, resetting position")
            self.last_position = 0

        with open(self.history_file) as f:
            # Seek to last position
            f.seek(self.last_position)

            # Read new lines only
            for line in f:
                try:
                    entry = json.loads(line.strip())
                    self._process_chaos_entry(entry)
                    self.entries_processed += 1
                except json.JSONDecodeError:
                    continue
                except Exception as e:
                    logger.error(f"[chaos_monitor] Error processing entry: {e}")

            # Update position
            self.last_position = f.tell()

    def _process_chaos_entry(self, entry: Dict[str, Any]):
        """
        Process one chaos experiment entry.

        Updates scenario stats and emits signals if thresholds violated.

        Args:
            entry: Chaos experiment result from chaos_history.jsonl
        """
        spec_id = entry.get("spec_id")
        if not spec_id:
            return

        # Update scenario stats
        stats = self.scenario_stats[spec_id]
        stats["total"] += 1

        # Track healing
        outcome = entry.get("outcome", {})
        if outcome.get("healed"):
            stats["healed"] += 1

        # Track score (keep last N)
        score = entry.get("score", 0)
        stats["scores"].append(score)
        if len(stats["scores"]) > self.lookback_experiments:
            stats["scores"].pop(0)

        # Calculate current metrics
        healing_rate = stats["healed"] / stats["total"] if stats["total"] > 0 else 0
        avg_score = sum(stats["scores"]) / len(stats["scores"]) if stats["scores"] else 0

        # Check thresholds (only if we have enough data)
        if stats["total"] >= 3:
            if healing_rate < self.healing_rate_threshold or avg_score < self.score_threshold:
                # Check if target system is disabled
                target = entry.get("target", "unknown")
                if self._is_target_disabled(target):
                    # Skip signal emission for disabled systems
                    logger.info(
                        f"[chaos_monitor] Healing failure expected for disabled system: "
                        f"{spec_id} (target={target}, rate={healing_rate:.1%}, score={avg_score:.1f})"
                    )
                    self.signals_skipped_disabled += 1
                    return

                # Check cooldown to avoid spam
                now = time.time()
                if now - stats["last_failure_emitted"] > self.signal_cooldown:
                    self._emit_healing_failure_gap(spec_id, entry, healing_rate, avg_score, stats["total"])
                    stats["last_failure_emitted"] = now
                    self.signals_emitted += 1

    def _emit_healing_failure_gap(
        self,
        spec_id: str,
        entry: Dict[str, Any],
        healing_rate: float,
        avg_score: float,
        experiment_count: int
    ):
        """
        Emit CAPABILITY_GAP signal for poor healing performance.

        Args:
            spec_id: Chaos scenario ID
            entry: Most recent experiment entry
            healing_rate: Current healing rate (0-1)
            avg_score: Average score across recent experiments
            experiment_count: Total experiments for this scenario
        """
        target = entry.get("target", "unknown")
        mode = entry.get("mode", "unknown")

        # Determine severity
        if healing_rate < 0.1:
            severity = "critical"
        elif healing_rate < 0.2:
            severity = "high"
        else:
            severity = "medium"

        self.pub.emit(
            signal="CAPABILITY_GAP",
            ecosystem="self_healing",
            facts={
                "gap_type": "healing_failure",
                "gap_name": spec_id,
                "gap_category": "resilience",
                "target": target,
                "mode": mode,
                "healing_rate": healing_rate,
                "avg_score": avg_score,
                "experiment_count": experiment_count,
                "severity": severity,
                "threshold_healing_rate": self.healing_rate_threshold,
                "threshold_score": self.score_threshold
            }
        )

        logger.info(
            f"[chaos_monitor] Healing failure detected: {spec_id} "
            f"(rate={healing_rate:.1%}, score={avg_score:.1f}, severity={severity})"
        )

    def shutdown(self):
        """Shutdown daemon gracefully."""
        logger.info("[chaos_monitor] Shutting down chaos monitor daemon")
        logger.info(f"[chaos_monitor] Total entries processed: {self.entries_processed}")
        logger.info(f"[chaos_monitor] Total signals emitted: {self.signals_emitted}")
        logger.info(f"[chaos_monitor] Signals skipped (disabled systems): {self.signals_skipped_disabled}")
        logger.info(f"[chaos_monitor] Scenarios tracked: {len(self.scenario_stats)}")
        self.running = False


def main():
    """Main entry point."""
    daemon = ChaosMonitorDaemon()
    daemon.run()


if __name__ == "__main__":
    main()
