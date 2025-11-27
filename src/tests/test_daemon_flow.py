#!/usr/bin/env python3
"""
Test end-to-end daemon question flow:
1. Publish a question like a daemon would
2. Verify it can be received by a subscriber (simulating CuriosityCore)
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.orchestration.core.umn_bus import UMNPub, UMNSub
import time
import threading

received_questions = []

def on_question(msg):
    """Handler for received questions"""
    received_questions.append(msg)
    print(f"✓ Received question: {msg.get('signal')}")

def main():
    print("=== Testing Daemon Question Flow ===\n")

    # Create subscriber (like CuriosityCore does)
    print("[1] Creating subscriber for curiosity.integration_question...")
    sub = UMNSub(
        topic="curiosity.integration_question",
        on_json=on_question,
        zooid_name="test_curiosity",
        niche="test"
    )
    print("   ✓ Subscriber created")

    # Wait for subscription to propagate
    print("\n[2] Waiting 3 seconds for subscription...")
    time.sleep(3)

    # Create publisher (like integration_monitor_daemon does)
    print("\n[3] Creating publisher...")
    pub = UMNPub()
    print("   ✓ Publisher created")
    time.sleep(1)

    # Publish a test question
    print("\n[4] Publishing test integration question...")
    pub.emit(
        signal="curiosity.integration_question",
        ecosystem="integration",
        intensity=1.0,
        facts={
            "question": "Test: Is module X compatible with module Y?",
            "source": "test_daemon_flow",
            "timestamp": time.time()
        },
        incident_id=f"test_{int(time.time())}"
    )
    print("   ✓ Question published")

    # Wait for message to be received
    print("\n[5] Waiting 5 seconds for message delivery...")
    time.sleep(5)

    # Check results
    print(f"\n{'='*60}")
    if len(received_questions) > 0:
        print(f"✅ SUCCESS: Received {len(received_questions)} question(s)!")
        print("\nDaemon → UMN → CuriosityCore flow is WORKING!")
        print("\nReceived question details:")
        for q in received_questions:
            print(f"  - Signal: {q.get('signal')}")
            print(f"  - Ecosystem: {q.get('ecosystem')}")
            print(f"  - Facts: {q.get('facts', {}).get('question', 'N/A')}")
        return 0
    else:
        print(f"❌ FAILURE: No questions received")
        print("The daemon question flow is NOT working")
        return 1

if __name__ == "__main__":
    exit(main())
