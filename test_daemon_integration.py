#!/usr/bin/env python3

import sys
import time
from pathlib import Path

sys.path.insert(0, '/home/kloros/src')
sys.path.insert(0, '/home/kloros')

from kloros.orchestration.chem_bus_v2 import ChemPub, ChemMessage
from registry.curiosity_core import CuriosityCore
from registry.capability_evaluator import CapabilityMatrix

print("[TEST] Starting integration test...")

feed_path = Path("/tmp/test_curiosity_feed.json")
core = CuriosityCore(feed_path=feed_path)

print("[TEST] Subscribing to daemon questions...")
core.subscribe_to_daemon_questions()

time.sleep(0.5)

print("[TEST] Creating ChemPub...")
pub = ChemPub()

print("[TEST] Emitting test question...")
pub.emit(
    signal="curiosity.integration_question",
    ecosystem="curiosity",
    intensity=0.95,
    facts={
        'question_id': 'manual_integration_test',
        'question': 'Is manual integration test working?',
        'evidence': ['Manual test emission', 'Direct daemon simulation'],
        'hypothesis': 'Manual integration flow works',
        'severity': 'high',
        'source': 'manual_test'
    }
)
print(f"[TEST] Emitted question to curiosity.integration_question")

time.sleep(1.0)

print("[TEST] Retrieving daemon questions...")
daemon_questions = core._get_daemon_questions()

print(f"[TEST] Received {len(daemon_questions)} daemon questions")

if len(daemon_questions) > 0:
    for q in daemon_questions:
        print(f"  - Question ID: {q.id}")
        print(f"    Question: {q.question}")
        print(f"    Hypothesis: {q.hypothesis}")
        print(f"    Evidence: {q.evidence}")
        print(f"    Severity: {q.metadata.get('severity')}")
        print()

    print("[TEST] SUCCESS: Questions received from daemon!")
else:
    print("[TEST] WARNING: No questions received")

print("[TEST] Testing integration with generate_questions_from_matrix...")
pub.emit(
    signal="curiosity.integration_question",
    ecosystem="curiosity",
    intensity=0.95,
    facts={
        'question_id': 'manual_integration_test',
        'question': 'Is manual integration test working?',
        'evidence': ['Manual test emission', 'Direct daemon simulation'],
        'hypothesis': 'Manual integration flow works',
        'severity': 'high',
        'source': 'manual_test'
    }
)
time.sleep(0.5)

matrix = CapabilityMatrix(capabilities=[])
feed = core.generate_questions_from_matrix(matrix,
    include_performance=False,
    include_resources=False,
    include_exceptions=False)

question_ids = [q.id for q in feed.questions]
print(f"[TEST] Generated feed has {len(feed.questions)} questions")
print(f"[TEST] Question IDs: {question_ids}")

if 'manual_integration_test' in question_ids:
    print("[TEST] SUCCESS: Daemon question merged into feed!")
else:
    print("[TEST] WARNING: Daemon question not in feed")

print("[TEST] Integration test complete!")
