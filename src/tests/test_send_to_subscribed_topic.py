#!/usr/bin/env python3
"""
Test: Send message to a topic that already has subscribers.

We know curiosity.integration_question has subscribers (registered at 15:27:52).
Let's send a message to it and see if it's received.
"""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1]))
sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

from src.orchestration.core.umn_bus import UMNPub as ChemPub

def main():
    print("=== Testing Message to Subscribed Topic ===")
    print("Topic: curiosity.integration_question")
    print("Subscribers exist: YES (registered at 15:27:52)")
    print()

    pub = ChemPub()

    test_timestamp = int(time.time())
    question_id = f'routing_test_{test_timestamp}'

    print(f"Sending message with question_id: {question_id}")

    pub.emit(
        signal="curiosity.integration_question",
        ecosystem="curiosity",
        intensity=0.95,
        facts={
            'question_id': question_id,
            'hypothesis': 'ChemBus routing test',
            'question': 'Is ChemBus routing working?',
            'evidence': ['Testing message delivery to existing subscribers'],
            'severity': 'high',
            'category': 'routing_test',
            'source': 'routing_test_script',
            'timestamp': test_timestamp
        }
    )

    print("✓ Message sent!")
    print()
    print("Check CuriosityCore logs:")
    print("  sudo journalctl -u kloros-curiosity-core-consumer.service -n 50 --no-pager | grep routing_test")
    print()
    print("Check proxy logs:")
    print("  sudo journalctl -u kloros-chem-proxy.service -n 20 --no-pager | grep integration_question")


if __name__ == "__main__":
    main()
