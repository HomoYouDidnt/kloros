"""TUMIX Reasoning Gateway - Central routing and observability for reasoning tasks."""

import logging
from typing import Optional

from src.tumix.meta_coordinator import (
    ReasoningTask,
    ReasoningResult,
    get_meta_coordinator
)

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


def route_reasoning(task: ReasoningTask) -> ReasoningResult:
    """Route a reasoning task through the TUMIX meta-reasoning system.

    This is the primary entry point for reasoning task processing.
    Handles task routing, strategy planning, and execution with observability.

    Args:
        task: The reasoning task to process

    Returns:
        A ReasoningResult with the reasoning outcome

    Raises:
        ValueError: If task validation fails
    """
    logger.info(f"Routing reasoning task {task.task_id}: {task.description[:60]}...")

    coordinator = get_meta_coordinator()

    strategy = coordinator.plan_reasoning(task)
    logger.info(
        f"Routing decision for {task.task_id}: strategy={strategy.strategy_type}, "
        f"complexity={strategy.estimated_complexity:.2f}"
    )

    result = coordinator.execute_strategy(strategy, task)
    logger.info(f"Routing complete for {task.task_id}: success={result.success}")

    return result


def execute_directly(task: ReasoningTask) -> ReasoningResult:
    """Execute a reasoning task directly without strategy planning.

    Bypasses the planning phase and executes immediately with default strategy.
    Useful for simple tasks or explicit direct execution.

    Args:
        task: The reasoning task to execute

    Returns:
        A ReasoningResult with the execution outcome
    """
    logger.info(f"Direct execution of task {task.task_id}")

    coordinator = get_meta_coordinator()

    result = coordinator._simple_execute(task)

    return result
