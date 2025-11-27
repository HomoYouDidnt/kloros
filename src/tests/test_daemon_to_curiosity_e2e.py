#!/usr/bin/env python3
"""
End-to-end test: Daemon → ChemBus → CuriosityCore

Verifies that:
1. Daemons can emit questions to ChemBus
2. CuriosityCore subscriptions receive the messages
3. Questions appear in CuriosityCore's daemon_questions list
"""

import sys
import time
import logging
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1]))
sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

from src.orchestration.core.umn_bus import UMNPub as ChemPub
from registry.curiosity_core import CuriosityCore

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)


def test_daemon_to_curiosity_flow():
    """Test that daemon questions flow to CuriosityCore via ChemBus."""

    logger.info("=== Starting End-to-End Test ===")

    # Step 1: Create CuriosityCore with daemon subscriptions enabled
    logger.info("Step 1: Creating CuriosityCore with daemon subscriptions...")
    curiosity = CuriosityCore(enable_daemon_subscriptions=True)
    time.sleep(2)  # Give subscriptions time to initialize

    # Step 2: Emit a test question via ChemBus (simulating a daemon)
    logger.info("Step 2: Emitting test question via ChemBus (simulating daemon)...")
    pub = ChemPub()

    test_timestamp = int(time.time())
    question_id = f'test_integration_{test_timestamp}'

    pub.emit(
        signal="curiosity.integration_question",
        ecosystem="curiosity",
        intensity=0.95,
        facts={
            'question_id': question_id,
            'hypothesis': 'Test orphaned queue pattern',
            'question': 'Should we integrate this test queue?',
            'evidence': ['Found orphaned_test_queue in test_file.py'],
            'severity': 'high',
            'category': 'integration_test',
            'source': 'integration_test_script',
            'timestamp': test_timestamp
        }
    )
    logger.info(f"Emitted test question: {question_id}")

    # Step 3: Wait for message delivery
    logger.info("Step 3: Waiting for message delivery...")
    time.sleep(2)

    # Step 4: Check if CuriosityCore received the question
    logger.info("Step 4: Checking if CuriosityCore received the question...")
    daemon_questions = curiosity._get_daemon_questions()

    if daemon_questions:
        logger.info(f"✓ SUCCESS: CuriosityCore received {len(daemon_questions)} daemon question(s)")
        for q in daemon_questions:
            logger.info(f"  - Question ID: {q.id}")
            logger.info(f"  - Question: {q.question}")
            logger.info(f"  - Evidence: {q.evidence}")
        return True
    else:
        logger.warning("✗ FAILURE: CuriosityCore received 0 daemon questions")
        logger.warning("  This might indicate:")
        logger.warning("  1. ChemBus subscription not active")
        logger.warning("  2. Message routing issue")
        logger.warning("  3. Callback not being invoked")
        return False


def main():
    success = test_daemon_to_curiosity_flow()

    if success:
        logger.info("\n=== Test PASSED ===")
        logger.info("Daemon → ChemBus → CuriosityCore flow is working!")
        sys.exit(0)
    else:
        logger.error("\n=== Test FAILED ===")
        logger.error("Daemon questions are not reaching CuriosityCore")
        sys.exit(1)


if __name__ == "__main__":
    main()
