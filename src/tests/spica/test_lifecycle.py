import pytest
from src.spica.lifecycle import LifecycleStateMachine, LifecycleState

def test_initial_state_is_pluripotent():
    sm = LifecycleStateMachine()
    assert sm.current_state == LifecycleState.PLURIPOTENT

def test_transition_pluripotent_to_primed():
    sm = LifecycleStateMachine()
    sm.transition_to(LifecycleState.PRIMED, metadata={"dr_path": "/path/to/dr.yaml"})
    assert sm.current_state == LifecycleState.PRIMED

def test_invalid_transition_raises_error():
    sm = LifecycleStateMachine()
    with pytest.raises(ValueError, match="Invalid transition"):
        sm.transition_to(LifecycleState.SPECIALIZED)

def test_reprogram_from_integrated_to_pluripotent():
    sm = LifecycleStateMachine()
    sm.transition_to(LifecycleState.PRIMED, metadata={"dr_path": "/path"})
    sm.transition_to(LifecycleState.DIFFERENTIATING)
    sm.transition_to(LifecycleState.SPECIALIZED)
    sm.transition_to(LifecycleState.INTEGRATED)
    sm.reprogram()
    assert sm.current_state == LifecycleState.PLURIPOTENT
    assert sm.history[-1]["event"] == "reprogram"

def test_state_history_tracking():
    sm = LifecycleStateMachine()
    sm.transition_to(LifecycleState.PRIMED, metadata={"dr_path": "/path"})
    assert len(sm.history) == 2
    assert sm.history[0]["state"] == LifecycleState.PLURIPOTENT
    assert sm.history[1]["state"] == LifecycleState.PRIMED
