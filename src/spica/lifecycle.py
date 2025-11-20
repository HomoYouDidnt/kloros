import time
from enum import Enum
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field

class LifecycleState(Enum):
    PLURIPOTENT = "pluripotent"
    PRIMED = "primed"
    DIFFERENTIATING = "differentiating"
    SPECIALIZED = "specialized"
    INTEGRATED = "integrated"

@dataclass
class StateTransition:
    from_state: LifecycleState
    to_state: LifecycleState
    timestamp: float
    metadata: Dict[str, Any] = field(default_factory=dict)
    event: str = "transition"

    def __getitem__(self, key):
        if key == "state":
            return self.to_state
        elif key == "event":
            return self.event
        elif key == "timestamp":
            return self.timestamp
        elif key == "metadata":
            return self.metadata
        else:
            raise KeyError(f"Invalid key: {key}")

class LifecycleStateMachine:
    VALID_TRANSITIONS = {
        LifecycleState.PLURIPOTENT: [LifecycleState.PRIMED],
        LifecycleState.PRIMED: [LifecycleState.DIFFERENTIATING],
        LifecycleState.DIFFERENTIATING: [LifecycleState.SPECIALIZED],
        LifecycleState.SPECIALIZED: [LifecycleState.INTEGRATED],
        LifecycleState.INTEGRATED: [LifecycleState.PLURIPOTENT],
    }

    def __init__(self):
        self.current_state = LifecycleState.PLURIPOTENT
        self.history: List[StateTransition] = [
            StateTransition(
                from_state=LifecycleState.PLURIPOTENT,
                to_state=LifecycleState.PLURIPOTENT,
                timestamp=time.time(),
                event="init"
            )
        ]

    def transition_to(self, new_state: LifecycleState, metadata: Optional[Dict[str, Any]] = None):
        if new_state not in self.VALID_TRANSITIONS.get(self.current_state, []):
            raise ValueError(
                f"Invalid transition from {self.current_state.value} to {new_state.value}"
            )

        transition = StateTransition(
            from_state=self.current_state,
            to_state=new_state,
            timestamp=time.time(),
            metadata=metadata or {},
            event="transition"
        )
        self.history.append(transition)
        self.current_state = new_state

    def reprogram(self):
        if self.current_state != LifecycleState.INTEGRATED:
            raise ValueError("Can only reprogram from INTEGRATED state")

        transition = StateTransition(
            from_state=self.current_state,
            to_state=LifecycleState.PLURIPOTENT,
            timestamp=time.time(),
            event="reprogram"
        )
        self.history.append(transition)
        self.current_state = LifecycleState.PLURIPOTENT

    def get_state(self) -> Dict[str, Any]:
        return {
            "current_state": self.current_state.value,
            "history_length": len(self.history),
            "last_transition": self.history[-1].timestamp if self.history else None
        }
