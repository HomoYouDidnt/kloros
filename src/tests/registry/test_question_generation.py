import pytest
from src.orchestration.registry.capability_discovery_monitor import CapabilityDiscoveryMonitor
from src.orchestration.registry.curiosity_core import CuriosityQuestion, ActionClass


def test_generate_capability_questions():
    """Test generating CuriosityQuestion objects from gaps."""
    monitor = CapabilityDiscoveryMonitor()

    questions = monitor.generate_capability_questions()

    assert isinstance(questions, list)

    for q in questions:
        assert isinstance(q, CuriosityQuestion)
        assert q.action_class == ActionClass.FIND_SUBSTITUTE
        assert hasattr(q, 'hypothesis')
        assert hasattr(q, 'question')
        assert hasattr(q, 'evidence')


def test_question_generation_limit():
    """Test that question generation respects max limit."""
    monitor = CapabilityDiscoveryMonitor()

    for scanner in monitor.scanners:
        scanner.last_run = 0.0

    questions = monitor.generate_capability_questions()

    assert len(questions) <= 10
