#!/usr/bin/env python3
"""
Wrapper script for UnindexedKnowledgeScanner that integrates with curiosity feed.

This script:
1. Runs the UnindexedKnowledgeScanner to find unindexed files
2. Reads the existing curiosity_feed.json
3. Adds new questions (deduplicates by ID)
4. Writes updated feed back to disk
"""

import json
import logging
import sys
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parents[3]))

from src.introspection.scanners.unindexed_knowledge_scanner import scan_for_unindexed_knowledge

logging.basicConfig(
    level=logging.INFO,
    format='[%(levelname)s] %(message)s'
)

logger = logging.getLogger(__name__)

CURIOSITY_FEED_PATH = Path("/home/kloros/.kloros/curiosity_feed.json")


def load_existing_feed():
    """Load existing curiosity feed from disk."""
    if not CURIOSITY_FEED_PATH.exists():
        logger.warning(f"Feed file not found: {CURIOSITY_FEED_PATH}")
        return {"questions": [], "generated_at": datetime.now().isoformat(), "count": 0}

    try:
        with open(CURIOSITY_FEED_PATH, 'r') as f:
            feed = json.load(f)
        logger.info(f"Loaded {len(feed.get('questions', []))} existing questions")
        return feed
    except Exception as e:
        logger.error(f"Failed to load feed: {e}")
        return {"questions": [], "generated_at": datetime.now().isoformat(), "count": 0}


def merge_questions(existing_feed, new_questions):
    """
    Merge new questions into existing feed, deduplicating by ID.

    Args:
        existing_feed: Dict with 'questions' list
        new_questions: List of question dicts

    Returns:
        Updated feed dict
    """
    existing_questions = existing_feed.get("questions", [])
    existing_ids = {q["id"] for q in existing_questions}

    # Add only new questions
    added_count = 0
    for question in new_questions:
        if question["id"] not in existing_ids:
            existing_questions.append(question)
            added_count += 1
        else:
            logger.debug(f"Skipping duplicate question: {question['id']}")

    logger.info(f"Added {added_count} new questions (skipped {len(new_questions) - added_count} duplicates)")

    # Update metadata
    existing_feed["questions"] = existing_questions
    existing_feed["generated_at"] = datetime.now().isoformat()
    existing_feed["count"] = len(existing_questions)

    return existing_feed


def write_feed(feed):
    """Write updated feed back to disk."""
    try:
        CURIOSITY_FEED_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(CURIOSITY_FEED_PATH, 'w') as f:
            json.dump(feed, f, indent=2)
        logger.info(f"Wrote {len(feed['questions'])} questions to {CURIOSITY_FEED_PATH}")
        return True
    except Exception as e:
        logger.error(f"Failed to write feed: {e}")
        return False


def main():
    """Main entry point."""
    logger.info("Starting knowledge scanner...")

    # Run scanner
    new_questions, report = scan_for_unindexed_knowledge()

    logger.info(f"\n{report}")

    if not new_questions:
        logger.info("No new questions generated")
        return 0

    # Load existing feed
    feed = load_existing_feed()

    # Merge questions
    updated_feed = merge_questions(feed, new_questions)

    # Write back
    if write_feed(updated_feed):
        logger.info("✓ Knowledge scanner completed successfully")
        return 0
    else:
        logger.error("✗ Failed to write updated feed")
        return 1


if __name__ == "__main__":
    sys.exit(main())
