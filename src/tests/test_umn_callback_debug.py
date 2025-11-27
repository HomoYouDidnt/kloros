#!/usr/bin/env python3
"""
Debug test for UMN callback invocation.
"""

import sys
import time
import logging
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1]))
sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

from src.orchestration.core.umn_bus import UMNPub, UMNSub

logging.basicConfig(level=logging.DEBUG, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)

# Track if callback was invoked
callback_invoked = False
received_messages = []

def test_callback(msg):
    """Test callback that logs when invoked."""
    global callback_invoked, received_messages
    callback_invoked = True
    received_messages.append(msg)
    logger.info(f"✓ CALLBACK INVOKED! Received message: {msg.get('facts', {}).get('question_id', 'unknown')}")


def main():
    logger.info("=== UMN Callback Debug Test ===")

    # Step 1: Create subscription
    logger.info("Step 1: Creating UMNSub subscription...")
    sub = UMNSub(
        topic="curiosity.test_signal",
        on_json=test_callback,
        zooid_name="callback_test",
        niche="testing"
    )
    logger.info("Subscription created, waiting for initialization...")
    time.sleep(2)

    # Step 2: Emit test message
    logger.info("Step 2: Emitting test message...")
    pub = UMNPub()

    pub.emit(
        signal="curiosity.test_signal",
        ecosystem="curiosity",
        intensity=0.95,
        facts={
            'question_id': 'callback_test_123',
            'test': 'callback_invocation'
        }
    )
    logger.info("Message emitted")

    # Step 3: Wait for callback
    logger.info("Step 3: Waiting for callback...")
    for i in range(5):
        time.sleep(1)
        if callback_invoked:
            logger.info(f"✓ Callback invoked after {i+1} seconds")
            break
        logger.debug(f"Waiting... ({i+1}/5)")

    # Step 4: Results
    if callback_invoked:
        logger.info("✓ SUCCESS: Callback was invoked!")
        logger.info(f"Received {len(received_messages)} message(s)")
        return 0
    else:
        logger.error("✗ FAILURE: Callback was NOT invoked")
        logger.error("This indicates a UMN routing issue")
        return 1


if __name__ == "__main__":
    sys.exit(main())
