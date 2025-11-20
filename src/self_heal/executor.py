"""Healing executor with canary, validation, and rollback."""

from typing import List, Dict, Any, Optional
import time
from .actions import create_action, HealAction
from .policy import Guardrails
from .health import HealthProbes
from .outcomes import OutcomesLogger


class HealExecutor:
    """Executes healing playbooks with safety checks."""

    def __init__(
        self,
        guardrails: Guardrails,
        health_probes: HealthProbes,
        logger=None,
        outcomes: Optional[OutcomesLogger] = None
    ):
        """Initialize executor.

        Args:
            guardrails: Safety policy manager
            health_probes: Health check manager
            logger: Optional logger for output
            outcomes: Optional outcomes logger
        """
        self.guardrails = guardrails
        self.health = health_probes
        self.logger = logger
        self.outcomes = outcomes or OutcomesLogger()

    def execute_playbook(self, playbook, event, kloros_instance) -> bool:
        """Execute a playbook with validation and rollback.

        Args:
            playbook: Playbook to execute
            event: HealEvent that triggered this
            kloros_instance: KLoROS instance to operate on

        Returns:
            True if execution succeeded and validated
        """
        # Check guardrails
        if not self.guardrails.should_heal(event):
            self._log(f"[executor] Guardrails blocked healing for {event.kind}")
            if self.guardrails.mode == "DRY-RUN":
                self._log(f"[executor] DRY-RUN: Would execute playbook {playbook.name}")
                self._dry_run_steps(playbook.steps)
            return False

        self._log(f"[executor] Executing playbook: {playbook.name}")

        # Parse and create actions
        actions = []
        for step in playbook.steps:
            action = create_action(step)
            if action:
                # Check if action is allowed
                if not self.guardrails.is_action_allowed(action.name, action.params):
                    self._log(f"[executor] Action blocked: {action.name}")
                    continue
                actions.append(action)

        if not actions:
            self._log("[executor] No valid actions to execute")
            return False

        # Canary scope: apply to subset first if specified
        canary_result = self._canary_check(playbook, kloros_instance)
        if not canary_result:
            self._log("[executor] Canary check failed, aborting")
            self.outcomes.log_outcome(event, playbook, success=False, reason="canary_failed")
            return False

        # Apply actions
        applied_actions = []
        try:
            for action in actions:
                self._log(f"[executor] Applying: {action.name}")
                if action.apply(kloros_instance):
                    applied_actions.append(action)
                else:
                    self._log(f"[executor] Action failed: {action.name}")
                    raise Exception(f"Action {action.name} failed")

            # Brief settle time
            time.sleep(0.5)

            # Validate
            validation_passed = self._validate(playbook, kloros_instance)

            if validation_passed:
                self._log(f"[executor] Playbook {playbook.name} succeeded")
                self.outcomes.log_outcome(event, playbook, success=True)
                return True
            else:
                self._log(f"[executor] Validation failed, rolling back")
                self._rollback_actions(applied_actions, kloros_instance)
                self.outcomes.log_outcome(event, playbook, success=False, reason="validation_failed")
                return False

        except Exception as e:
            self._log(f"[executor] Execution error: {e}")
            self._rollback_actions(applied_actions, kloros_instance)
            self.outcomes.log_outcome(event, playbook, success=False, reason=str(e))
            return False

    def _canary_check(self, playbook, kloros_instance) -> bool:
        """Run canary check if specified.

        Args:
            playbook: Playbook with optional canary_scope
            kloros_instance: KLoROS instance

        Returns:
            True if canary passed or not needed
        """
        canary_scope = playbook.canary_scope
        if not canary_scope:
            return True  # No canary needed

        # For now, just return True
        # In production, would test on subset first
        self._log(f"[executor] Canary scope: {canary_scope}")
        return True

    def _validate(self, playbook, kloros_instance) -> bool:
        """Validate that healing worked.

        Args:
            playbook: Playbook with validation requirements
            kloros_instance: KLoROS instance

        Returns:
            True if validation passed
        """
        validate_config = playbook.validate
        if not validate_config:
            return True  # No validation required

        check_type = validate_config.get("check")

        if check_type == "validator_health":
            result = self.health.check_validator_health()
            return result.get("healthy", False)

        elif check_type == "rag_health":
            result = self.health.check_rag_health()
            return result.get("healthy", False)

        elif check_type == "audio_health":
            result = self.health.check_audio_health()
            return result.get("healthy", False)

        elif check_type == "system_health":
            result = self.health.check_system_health()
            return result.get("healthy", False)

        else:
            self._log(f"[executor] Unknown validation check: {check_type}")
            return True  # Unknown checks pass by default

    def _rollback_actions(self, actions: List[HealAction], kloros_instance):
        """Rollback applied actions in reverse order.

        Args:
            actions: List of actions to rollback
            kloros_instance: KLoROS instance
        """
        self._log("[executor] Rolling back actions")
        for action in reversed(actions):
            try:
                action.rollback(kloros_instance)
            except Exception as e:
                self._log(f"[executor] Rollback error for {action.name}: {e}")

    def _dry_run_steps(self, steps: List[Dict[str, Any]]):
        """Log what would happen in dry-run mode.

        Args:
            steps: List of step definitions
        """
        for i, step in enumerate(steps, 1):
            action_name = step.get("action")
            params = step.get("params", {})
            self._log(f"[executor] DRY-RUN step {i}: {action_name} with {params}")

    def _log(self, message: str):
        """Log a message.

        Args:
            message: Message to log
        """
        if self.logger:
            self.logger.info(message)
        else:
            print(message)


# Alias for backwards compatibility / alternative naming
HealingExecutor = HealExecutor
