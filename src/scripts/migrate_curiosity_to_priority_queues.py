#!/usr/bin/env python3
"""
Migrate existing curiosity_feed.json to priority-based chemical signals.

Run once during deployment to transition from file-based to queue-based system.
"""

import sys
import json
import shutil
from pathlib import Path
from datetime import datetime

sys.path.insert(0, '/home/kloros/src')

from registry.question_prioritizer import QuestionPrioritizer
from registry.curiosity_core import CuriosityQuestion, ActionClass, QuestionStatus
from kloros.orchestration.chem_bus_v2 import ChemPub

CURIOSITY_FEED = Path.home() / '.kloros' / 'curiosity_feed.json'

def migrate_existing_feed():
    """Migrate curiosity_feed.json to priority-based chemical signals."""

    if not CURIOSITY_FEED.exists():
        print("No existing curiosity_feed.json - nothing to migrate")
        return

    with open(CURIOSITY_FEED, 'r') as f:
        feed = json.load(f)

    questions = feed.get('questions', [])
    if not questions:
        print("curiosity_feed.json is empty - nothing to migrate")
        return

    print(f"Migrating {len(questions)} questions from curiosity_feed.json...")

    prioritizer = QuestionPrioritizer(ChemPub())

    migrated_count = 0

    for question_dict in questions:
        # Convert string fields to enums if needed
        if 'action_class' in question_dict and isinstance(question_dict['action_class'], str):
            question_dict['action_class'] = ActionClass(question_dict['action_class'])
        if 'status' in question_dict and isinstance(question_dict['status'], str):
            question_dict['status'] = QuestionStatus(question_dict['status'])

        q = CuriosityQuestion(**question_dict)

        # Compute hash for null-hash questions
        if q.evidence_hash is None:
            q.evidence_hash = prioritizer.compute_evidence_hash(q.evidence)
            print(f"  Computed hash for {q.id}: {q.evidence_hash}")

        # Emit to appropriate priority queue
        prioritizer.prioritize_and_emit(q)
        migrated_count += 1
        print(f"  Migrated {q.id}")

    # Backup old feed
    backup_path = CURIOSITY_FEED.parent / f'curiosity_feed.backup.{datetime.now().strftime("%Y%m%d_%H%M%S")}.json'
    shutil.copy(CURIOSITY_FEED, backup_path)
    print(f"\nBacked up old feed to {backup_path}")

    # Clear feed (new system uses chemical signals)
    with open(CURIOSITY_FEED, 'w') as f:
        json.dump({
            'questions': [],
            'generated_at': datetime.now().isoformat(),
            'count': 0
        }, f, indent=2)

    print(f"\nMigration complete: {migrated_count} questions migrated to priority queues")
    print("Old feed cleared (backup preserved)")

if __name__ == '__main__':
    migrate_existing_feed()
