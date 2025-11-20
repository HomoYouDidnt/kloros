#!/usr/bin/env python3
"""
Skill Auto-Executor - Safely execute low-risk skill plans autonomously.

Executes approved skill plans, validates outcomes, and tracks effectiveness
to enable continuous autonomous improvement.
"""

import os
import time
import json
import logging
import psutil
from typing import Dict, List, Optional, Any
from dataclasses import dataclass

from consciousness.skill_loader import SkillLoader
from consciousness.skill_executor import SkillExecutionPlan
from consciousness.skill_tracker import SkillTracker, SkillExecution
from kloros.orchestration.chem_bus_v2 import ChemPub

logger = logging.getLogger(__name__)


@dataclass
class ExecutionResult:
    """Result of autonomous skill execution."""
    execution_id: str
    skill_name: str
    success: bool
    outcome: str  # "success", "partial", "failed"
    metrics_before: Dict[str, float]
    metrics_after: Dict[str, float]
    improvement: float
    actions_executed: int
    execution_time_s: float
    notes: str


class SkillAutoExecutor:
    """
    Autonomous skill executor for low-risk healing operations.

    Only executes skills marked as `auto_executable: true` in metadata.
    Tracks outcomes and learns from results.
    """

    def __init__(self):
        """Initialize auto-executor."""
        self.skill_loader = SkillLoader()
        self.tracker = SkillTracker()
        self.chem_pub = ChemPub()

        # Safety limits
        self.max_execution_time = 300  # 5 minutes
        self.min_cooldown = 600  # 10 minutes between same skill
        self.last_execution = {}

        logger.info("[skill_auto_executor] Initialized with safety limits")

    def can_auto_execute(self, skill_name: str) -> bool:
        """
        Check if skill can be auto-executed.

        Args:
            skill_name: Name of skill

        Returns:
            True if safe to auto-execute
        """
        skill = self.skill_loader.load_skill(skill_name)

        if not skill:
            logger.warning(f"[skill_auto_executor] Skill not found: {skill_name}")
            return False

        auto_executable = skill.metadata.get('auto_executable', 'false').lower() == 'true'
        risk_level = skill.metadata.get('risk_level', 'high').lower()

        if not auto_executable:
            logger.info(f"[skill_auto_executor] Skill not auto-executable: {skill_name}")
            return False

        if risk_level not in ['low', 'minimal']:
            logger.warning(f"[skill_auto_executor] Risk level too high ({risk_level}): {skill_name}")
            return False

        last_exec = self.last_execution.get(skill_name, 0)
        if time.time() - last_exec < self.min_cooldown:
            logger.info(f"[skill_auto_executor] Cooldown active for {skill_name}")
            return False

        return True

    def execute_plan(
        self,
        plan: SkillExecutionPlan,
        auto_execute: bool = False
    ) -> Optional[ExecutionResult]:
        """
        Execute a skill plan autonomously.

        Args:
            plan: Skill execution plan
            auto_execute: Allow autonomous execution

        Returns:
            ExecutionResult if executed, None if skipped
        """
        if not auto_execute:
            logger.info(f"[skill_auto_executor] Auto-execution disabled for {plan.skill_name}")
            return None

        if not self.can_auto_execute(plan.skill_name):
            logger.warning(f"[skill_auto_executor] Cannot auto-execute {plan.skill_name}")
            return None

        execution_id = f"{plan.skill_name}_{int(time.time())}"

        logger.info(f"[skill_auto_executor] 🤖 AUTO-EXECUTING: {plan.skill_name}")
        logger.info(f"[skill_auto_executor]   Problem: {plan.problem_description[:80]}...")
        logger.info(f"[skill_auto_executor]   Actions: {len(plan.actions)}")
        logger.info(f"[skill_auto_executor]   Confidence: {plan.confidence}")

        start_time = time.time()

        # Collect baseline metrics
        metrics_before = self._collect_metrics()

        # Record execution start
        skill_execution = SkillExecution(
            execution_id=execution_id,
            skill_name=plan.skill_name,
            problem_type="performance",  # TODO: Extract from problem description
            problem_description=plan.problem_description,
            phase=plan.phase,
            actions_count=len(plan.actions),
            confidence=plan.confidence,
            timestamp=time.time(),
            metrics_before=metrics_before
        )

        self.tracker.record_execution(skill_execution)

        # Execute actions
        actions_executed = 0
        try:
            for action in plan.actions:
                if not self._execute_action(action):
                    logger.warning(f"[skill_auto_executor] Action failed: {action.get('description', 'unknown')}")
                    break
                actions_executed += 1

            # Wait for stabilization
            logger.info("[skill_auto_executor] Waiting 60s for system stabilization...")
            time.sleep(60)

            # Collect after metrics
            metrics_after = self._collect_metrics()

            # Calculate outcome
            outcome, improvement, notes = self._evaluate_outcome(metrics_before, metrics_after, plan)

            # Update tracker
            self.tracker.update_outcome(execution_id, outcome, metrics_after, notes)

            execution_time = time.time() - start_time

            result = ExecutionResult(
                execution_id=execution_id,
                skill_name=plan.skill_name,
                success=(outcome == "success"),
                outcome=outcome,
                metrics_before=metrics_before,
                metrics_after=metrics_after,
                improvement=improvement,
                actions_executed=actions_executed,
                execution_time_s=execution_time,
                notes=notes
            )

            # Emit result signal
            self.chem_pub.emit(
                signal="SKILL_EXECUTION_COMPLETE",
                ecosystem="consciousness",
                intensity=2.0 if outcome == "success" else 1.0,
                facts={
                    "execution_id": execution_id,
                    "skill_name": plan.skill_name,
                    "outcome": outcome,
                    "improvement": improvement,
                    "actions_executed": actions_executed,
                    "execution_time_s": execution_time
                }
            )

            logger.info(f"[skill_auto_executor] ✓ Execution complete: {outcome} (improvement: {improvement:.1%})")

            self.last_execution[plan.skill_name] = time.time()

            return result

        except Exception as e:
            logger.error(f"[skill_auto_executor] Execution failed: {e}", exc_info=True)

            metrics_after = self._collect_metrics()
            self.tracker.update_outcome(execution_id, "failed", metrics_after, f"Exception: {str(e)}")

            return None

    def _execute_action(self, action: Dict[str, str]) -> bool:
        """
        Execute a single action from skill plan.

        Args:
            action: Action dict with type, description, command

        Returns:
            True if successful
        """
        action_type = action.get('action_type', 'unknown')
        description = action.get('description', '')
        command = action.get('command', '')

        logger.info(f"[skill_auto_executor]   Executing: {description[:60]}...")

        # Map actions to actual implementations
        if 'throttle' in command.lower() and 'investigation' in command.lower():
            return self._throttle_investigations()

        elif 'reduce_investigation_concurrency' in command:
            return self._throttle_investigations()

        elif action_type in ['measure', 'collect', 'record']:
            logger.info(f"[skill_auto_executor]   (Measurement action - metrics collected automatically)")
            return True

        elif action_type in ['wait', 'delay', 'stabilize']:
            logger.info(f"[skill_auto_executor]   (Stabilization action - allowing system to settle)")
            return True

        elif action_type in ['validate', 'verify', 'check']:
            logger.info(f"[skill_auto_executor]   (Validation action - will be checked in outcome evaluation)")
            return True

        elif action_type in ['investigate', 'analyze']:
            logger.info(f"[skill_auto_executor]   (Investigation/Analysis action - logged only)")
            return True

        elif action_type in ['mitigate', 'throttle', 'reduce']:
            if 'investigation' in description.lower() or 'concurrency' in description.lower():
                return self._throttle_investigations()
            else:
                logger.info(f"[skill_auto_executor]   (Mitigation action - specific handler not implemented)")
                return True

        else:
            logger.warning(f"[skill_auto_executor]   Unknown action type: {action_type}")
            return True  # Don't fail on unknown actions

    def _throttle_investigations(self) -> bool:
        """Throttle investigation consumer."""
        try:
            self.chem_pub.emit(
                signal="INVESTIGATION_THROTTLE_REQUEST",
                ecosystem="orchestration",
                intensity=2.0,
                facts={
                    "reason": "Autonomous memory optimization",
                    "requested_concurrency": 1
                }
            )
            logger.info("[skill_auto_executor]   ✓ Throttle signal emitted")
            return True

        except Exception as e:
            logger.error(f"[skill_auto_executor]   ✗ Throttle failed: {e}")
            return False

    def _collect_metrics(self) -> Dict[str, float]:
        """Collect current system metrics."""
        try:
            mem = psutil.virtual_memory()
            swap = psutil.swap_memory()

            # Try to get investigation consumer thread count
            thread_count = 0
            for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
                try:
                    cmdline = proc.info.get('cmdline', [])
                    if cmdline and 'investigation_consumer_daemon' in ' '.join(cmdline):
                        thread_count = proc.num_threads()
                        break
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue

            return {
                'swap_used_mb': swap.used / (1024 * 1024),
                'swap_percent': swap.percent,
                'memory_used_pct': mem.percent,
                'memory_available_gb': mem.available / (1024**3),
                'thread_count': thread_count
            }

        except Exception as e:
            logger.error(f"[skill_auto_executor] Failed to collect metrics: {e}")
            return {}

    def _evaluate_outcome(
        self,
        before: Dict[str, float],
        after: Dict[str, float],
        plan: SkillExecutionPlan
    ) -> tuple[str, float, str]:
        """
        Evaluate execution outcome.

        Args:
            before: Metrics before execution
            after: Metrics after execution
            plan: Original plan

        Returns:
            (outcome, improvement_score, notes)
        """
        # Calculate improvements
        swap_reduction = 0.0
        mem_reduction = 0.0
        thread_reduction = 0.0

        if 'swap_used_mb' in before and 'swap_used_mb' in after and before['swap_used_mb'] > 0:
            swap_reduction = (before['swap_used_mb'] - after['swap_used_mb']) / before['swap_used_mb']

        if 'memory_used_pct' in before and 'memory_used_pct' in after and before['memory_used_pct'] > 0:
            mem_reduction = (before['memory_used_pct'] - after['memory_used_pct']) / before['memory_used_pct']

        if 'thread_count' in before and 'thread_count' in after and before['thread_count'] > 0:
            thread_reduction = (before['thread_count'] - after['thread_count']) / before['thread_count']

        # Overall improvement (weighted average)
        improvement = (swap_reduction * 0.4 + mem_reduction * 0.3 + thread_reduction * 0.3)

        # Classify outcome
        if improvement >= 0.20:
            outcome = "success"
            notes = f"Swap: {swap_reduction:.1%}, Mem: {mem_reduction:.1%}, Threads: {thread_reduction:.1%}"
        elif improvement >= 0.05:
            outcome = "partial"
            notes = f"Minor improvement - Swap: {swap_reduction:.1%}, Mem: {mem_reduction:.1%}"
        elif improvement >= -0.05:
            outcome = "failed"
            notes = "No significant improvement"
        else:
            outcome = "failed"
            notes = f"Metrics worsened - Swap: {swap_reduction:.1%}, Mem: {mem_reduction:.1%}"

        # Normalize improvement to 0-1 scale
        improvement_normalized = (improvement + 1.0) / 2.0

        return outcome, improvement_normalized, notes

    def close(self):
        """Cleanup resources."""
        if self.tracker:
            self.tracker.close()
        if self.chem_pub:
            self.chem_pub.close()


def main():
    """Test auto-executor."""
    logging.basicConfig(level=logging.INFO)

    from consciousness.skill_executor import SkillExecutor

    executor_llm = SkillExecutor()
    auto_exec = SkillAutoExecutor()

    problem = {
        'description': 'Swap usage at 50% (14GB used) causing moderate performance impact',
        'evidence': {'swap_percent': 50.0},
        'metrics': {'swap_used_mb': 14000, 'memory_used_pct': 58.0, 'thread_count': 300}
    }

    print("\n=== Testing Auto-Execution ===\n")

    # Generate plan
    plan = executor_llm.execute_skill('memory-optimization', problem)

    if plan:
        print(f"Plan generated: {plan.phase}")
        print(f"Can auto-execute? {auto_exec.can_auto_execute('memory-optimization')}")

        # Note: Don't actually execute in test
        print("\n(Auto-execution would happen here if auto_execute=True)")

    auto_exec.close()


if __name__ == "__main__":
    main()
