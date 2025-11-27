#!/usr/bin/env python3
"""Quick test of Observer components."""

import sys
import logging
from pathlib import Path

# Add src to path
sys.path.insert(0, "/home/kloros")

from src.observability.observer import (
    Event, RuleEngine, IntentEmitter, Observer,
    JournaldSource, InotifySource, MetricsSource
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def test_event_creation():
    """Test Event dataclass."""
    event = Event(
        source="test",
        type="test_event",
        ts=1234567890.0,
        data={"foo": "bar"}
    )
    assert event.source == "test"
    assert event.hash_key() == "test:test_event"
    logger.info("✓ Event creation works")


def test_rule_engine():
    """Test RuleEngine processing."""
    import time

    engine = RuleEngine()

    # Create a promotion event with current time
    now = time.time()

    event = Event(
        source="inotify",
        type="promotion_new",
        ts=now,
        data={"path": "/home/kloros/out/promotions/test.json"}
    )

    # First event - no cluster yet
    intent = engine.process(event)
    assert intent is None, "Should not trigger on single promotion"

    # Add 2 more promotions with different paths (to avoid rate-limiting)
    for i in range(2):
        # Sleep briefly to avoid rate-limiting
        time.sleep(1)
        event = Event(
            source="inotify",
            type="promotion_new",
            ts=time.time(),
            data={"path": f"/home/kloros/out/promotions/test{i}.json"}
        )
        intent = engine.process(event)

    # Third promotion should trigger cluster rule
    assert intent is not None, "Should trigger on 3rd promotion"
    assert intent.intent_type == "trigger_phase_promotion_cluster"

    logger.info("✓ RuleEngine works (cluster rule triggered)")


def test_intent_emitter():
    """Test IntentEmitter."""
    from src.observability.observer.rules import Intent

    emitter = IntentEmitter(intents_dir=Path("/home/kloros/.kloros/intents"))

    intent = Intent(
        intent_type="test_intent",
        priority=5,
        reason="Test intent for validation",
        data={"test": True}
    )

    # Emit intent
    success = emitter.emit(intent)
    assert success, "Intent emission should succeed"

    # Check file was created
    pending = emitter.list_pending()
    assert len(pending) > 0, "Should have pending intents"

    # Verify integrity
    latest = pending[-1]
    valid = emitter.verify_intent(latest)
    assert valid, "Intent checksum should be valid"

    logger.info(f"✓ IntentEmitter works (emitted {latest.name})")

    # Clean up test intent
    latest.unlink()


def test_observer_instantiation():
    """Test Observer can be instantiated."""
    observer = Observer(
        journald_units=["dream.service"],
        watch_paths=[Path("/home/kloros/out/promotions")],
        metrics_endpoint="http://localhost:9090/metrics",
        metrics_interval_s=60
    )

    assert observer is not None
    assert observer.rule_engine is not None
    assert observer.intent_emitter is not None

    logger.info("✓ Observer instantiation works")


if __name__ == "__main__":
    try:
        test_event_creation()
        test_rule_engine()
        test_intent_emitter()
        test_observer_instantiation()

        print("\n" + "=" * 60)
        print("All Observer component tests passed!")
        print("=" * 60)

    except Exception as e:
        logger.error(f"Test failed: {e}", exc_info=True)
        sys.exit(1)
