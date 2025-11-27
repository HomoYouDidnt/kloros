#!/usr/bin/env python3
"""
Curiosity Processor Daemon - DEPRECATED.

This daemon is deprecated. Use curiosity_core_consumer_daemon instead.

The curiosity_core_consumer_daemon now handles the complete flow:
  CuriosityCore.generate_questions_from_matrix() → CuriosityCore.emit_questions_to_bus() → InvestigationConsumer

The systemd service kloros-curiosity-processor.service can be disabled.
"""

import sys
import logging
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[3]))

from src.orchestration.core.curiosity_processor import CuriosityProcessorDaemon

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s'
)


def main():
    """Entry point for curiosity processor daemon."""
    daemon = CuriosityProcessorDaemon()
    daemon.run()


if __name__ == "__main__":
    main()
