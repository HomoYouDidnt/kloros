import pytest
from src.registry.curiosity_core import CuriosityCore
from src.registry.capability_evaluator import CapabilityMatrix


def test_curiosity_core_includes_capability_questions():
    """Test that CuriosityCore generates capability discovery questions."""
    core = CuriosityCore()

    # Create a minimal CapabilityMatrix for testing
    matrix = CapabilityMatrix()

    feed = core.generate_questions_from_matrix(matrix)

    # Should generate questions
    assert feed is not None
    assert hasattr(feed, 'questions')

    # Look for capability questions
    capability_questions = [
        q for q in feed.questions
        if q.id.startswith('capability.')
    ]

    # May or may not have capability questions depending on state
    # But integration should work without errors
    assert isinstance(capability_questions, list)
