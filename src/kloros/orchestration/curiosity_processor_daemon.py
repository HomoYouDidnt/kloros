#!/usr/bin/env python3
"""
Curiosity Processor Daemon - KLoROS's autonomous self-examination engine.

KLoROS proactively examines her own system, thinks about improvements,
finds capability gaps, and generates investigation questions.

This daemon uses either priority queue mode (event-driven) or legacy
file-based polling mode based on the KLR_USE_PRIORITY_QUEUES environment variable.
"""

import sys
import logging
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[3]))

from kloros.orchestration.curiosity_processor import CuriosityProcessorDaemon

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
