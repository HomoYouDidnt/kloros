"""Reversible healing actions."""

import os
from typing import Dict, Any, Optional


class HealAction:
    """Base class for reversible healing actions."""

    def __init__(self, name: str, params: Dict[str, Any]):
        """Initialize action.

        Args:
            name: Action name
            params: Action parameters
        """
        self.name = name
        self.params = params
        self._rollback_data: Optional[Dict[str, Any]] = None

    def apply(self, kloros_instance) -> bool:
        """Apply the healing action.

        Args:
            kloros_instance: KLoROS instance to modify

        Returns:
            True if successful
        """
        raise NotImplementedError

    def rollback(self, kloros_instance) -> bool:
        """Rollback the action.

        Args:
            kloros_instance: KLoROS instance to restore

        Returns:
            True if successful
        """
        raise NotImplementedError


class SetFlagAction(HealAction):
    """Set an environment variable or flag."""

    def apply(self, kloros_instance) -> bool:
        flag = self.params.get("flag")
        value = self.params.get("value", "1")

        if not flag:
            return False

        # Save original value for rollback
        self._rollback_data = {"original": os.environ.get(flag)}

        os.environ[flag] = str(value)
        print(f"[action] Set {flag}={value}")
        return True

    def rollback(self, kloros_instance) -> bool:
        if not self._rollback_data:
            return False

        flag = self.params.get("flag")
        original = self._rollback_data.get("original")

        if original is None:
            os.environ.pop(flag, None)
        else:
            os.environ[flag] = original

        print(f"[action] Rolled back {flag}")
        return True


class SetTimeoutAction(HealAction):
    """Increase a timeout value."""

    def apply(self, kloros_instance) -> bool:
        target = self.params.get("target")
        new_timeout = self.params.get("new_timeout_s")

        if not target or new_timeout is None:
            return False

        # Navigate to target attribute
        obj = kloros_instance
        parts = target.split('.')

        for part in parts[:-1]:
            obj = getattr(obj, part, None)
            if obj is None:
                print(f"[action] Target path invalid: {target}")
                return False

        attr_name = parts[-1]

        # Save original for rollback
        self._rollback_data = {
            "obj": obj,
            "attr": attr_name,
            "original": getattr(obj, attr_name, None)
        }

        setattr(obj, attr_name, new_timeout)
        print(f"[action] Set {target}={new_timeout}s")
        return True

    def rollback(self, kloros_instance) -> bool:
        if not self._rollback_data:
            return False

        obj = self._rollback_data["obj"]
        attr = self._rollback_data["attr"]
        original = self._rollback_data["original"]

        if original is not None:
            setattr(obj, attr, original)
            print(f"[action] Rolled back {self.params.get('target')}")

        return True


class LowerThresholdAction(HealAction):
    """Lower a threshold value."""

    def apply(self, kloros_instance) -> bool:
        target = self.params.get("target")
        new_value = self.params.get("new_value")

        if not target or new_value is None:
            return False

        # Navigate to target
        obj = kloros_instance
        parts = target.split('.')

        for part in parts[:-1]:
            obj = getattr(obj, part, None)
            if obj is None:
                return False

        attr_name = parts[-1]

        # Save original
        self._rollback_data = {
            "obj": obj,
            "attr": attr_name,
            "original": getattr(obj, attr_name, None)
        }

        setattr(obj, attr_name, new_value)
        print(f"[action] Lowered {target} to {new_value}")
        return True

    def rollback(self, kloros_instance) -> bool:
        if not self._rollback_data:
            return False

        obj = self._rollback_data["obj"]
        attr = self._rollback_data["attr"]
        original = self._rollback_data["original"]

        if original is not None:
            setattr(obj, attr, original)
            print(f"[action] Rolled back {self.params.get('target')}")

        return True


class EnforceMuteWrapperAction(HealAction):
    """Enforce audio mute wrapper usage."""

    def apply(self, kloros_instance) -> bool:
        # Set flag to enforce mute wrapper
        flag = "KLR_ENFORCE_MUTE_WRAPPER"
        self._rollback_data = {"original": os.environ.get(flag)}

        os.environ[flag] = "1"
        print(f"[action] Enforced mute wrapper")
        return True

    def rollback(self, kloros_instance) -> bool:
        if not self._rollback_data:
            return False

        flag = "KLR_ENFORCE_MUTE_WRAPPER"
        original = self._rollback_data.get("original")

        if original is None:
            os.environ.pop(flag, None)
        else:
            os.environ[flag] = original

        print(f"[action] Rolled back mute wrapper enforcement")
        return True


class EnableAckAction(HealAction):
    """Enable acknowledgment messages for slow operations."""

    def apply(self, kloros_instance) -> bool:
        # Set flag to enable ack
        flag = "KLR_ENABLE_SYNTH_ACK"
        self._rollback_data = {"original": os.environ.get(flag)}

        os.environ[flag] = "1"
        print(f"[action] Enabled synthesis acknowledgments")
        return True

    def rollback(self, kloros_instance) -> bool:
        if not self._rollback_data:
            return False

        flag = "KLR_ENABLE_SYNTH_ACK"
        original = self._rollback_data.get("original")

        if original is None:
            os.environ.pop(flag, None)
        else:
            os.environ[flag] = original

        print(f"[action] Rolled back synthesis acknowledgments")
        return True


# Action registry
ACTION_CLASSES = {
    "set_flag": SetFlagAction,
    "set_timeout": SetTimeoutAction,
    "lower_threshold": LowerThresholdAction,
    "enforce_mute_wrapper": EnforceMuteWrapperAction,
    "enable_ack": EnableAckAction,
}

# Try to load integration actions (code patching)
try:
    from .actions_integration import INTEGRATION_ACTION_CLASSES
    ACTION_CLASSES.update(INTEGRATION_ACTION_CLASSES)
    INTEGRATION_ACTIONS_AVAILABLE = True
except ImportError as e:
    INTEGRATION_ACTIONS_AVAILABLE = False
    # Integration actions not available (missing dependencies)

# Load system-level actions (resource management)
try:
    from .actions_system import SYSTEM_ACTION_CLASSES
    ACTION_CLASSES.update(SYSTEM_ACTION_CLASSES)
    SYSTEM_ACTIONS_AVAILABLE = True
except ImportError as e:
    SYSTEM_ACTIONS_AVAILABLE = False
    print(f"[actions] System actions not available: {e}")


def create_action(action_def: Dict[str, Any]) -> Optional[HealAction]:
    """Factory for creating actions from definitions.

    Args:
        action_def: Action definition dict with 'action' and 'params'

    Returns:
        HealAction instance or None if invalid
    """
    action_name = action_def.get("action")
    params = action_def.get("params", {})

    action_class = ACTION_CLASSES.get(action_name)
    if not action_class:
        print(f"[actions] Unknown action: {action_name}")
        return None

    return action_class(action_name, params)
