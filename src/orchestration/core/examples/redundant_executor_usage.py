#!/usr/bin/env python3
"""
RedundantExecutor Usage Examples

Demonstrates how to use RedundantExecutor for robust task execution
with retry logic and fallback chains in KLoROS orchestration.
"""

import asyncio
import logging
from src.orchestration.core.redundant_executor import (
    RedundantExecutor,
    RetryConfig,
    ExecutionExhaustedError,
)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def example_1_basic_usage():
    """Example 1: Basic usage with primary executor only."""

    print("\n=== Example 1: Basic Usage ===")

    def process_task(task):
        logger.info(f"Processing task: {task}")
        return f"processed_{task}"

    executor = RedundantExecutor(primary=process_task)
    result = executor.execute("task_1")

    print(f"Result: {result}")


def example_2_retry_on_failure():
    """Example 2: Retry on transient failures."""

    print("\n=== Example 2: Retry on Failure ===")

    attempts = []

    def flaky_processor(task):
        attempts.append(1)
        if len(attempts) < 3:
            raise ValueError(f"Simulated failure (attempt {len(attempts)})")
        return f"success_after_{len(attempts)}_attempts"

    config = RetryConfig(
        max_retries=3,
        backoff_ms=100,
        timeout_ms=5000
    )

    executor = RedundantExecutor(
        primary=flaky_processor,
        config=config
    )

    result = executor.execute("task_2")
    print(f"Result: {result}")
    print(f"Total attempts: {len(attempts)}")


def example_3_fallback_chain():
    """Example 3: Fallback chain when primary fails."""

    print("\n=== Example 3: Fallback Chain ===")

    def primary_executor(task):
        raise ValueError("Primary service unavailable")

    def fallback_1(task):
        raise RuntimeError("Fallback 1 also unavailable")

    def fallback_2(task):
        logger.info("Fallback 2 succeeded!")
        return f"fallback_2_processed_{task}"

    config = RetryConfig(max_retries=1, backoff_ms=50)

    executor = RedundantExecutor(
        primary=primary_executor,
        fallbacks=[fallback_1, fallback_2],
        config=config
    )

    result = executor.execute("task_3")
    print(f"Result: {result}")


def example_4_complete_failure():
    """Example 4: Handling complete execution failure."""

    print("\n=== Example 4: Complete Failure ===")

    def primary_executor(task):
        raise ValueError("Primary failed")

    def fallback_1(task):
        raise RuntimeError("Fallback 1 failed")

    def fallback_2(task):
        raise TypeError("Fallback 2 failed")

    config = RetryConfig(max_retries=1, backoff_ms=50)

    executor = RedundantExecutor(
        primary=primary_executor,
        fallbacks=[fallback_1, fallback_2],
        config=config
    )

    try:
        executor.execute("task_4")
    except ExecutionExhaustedError as e:
        print(f"All executors exhausted: {e}")
        print(f"Total errors collected: {len(e.errors)}")
        for idx, error in enumerate(e.errors, 1):
            print(f"  Error {idx}: {type(error).__name__}: {error}")


async def example_5_async_execution():
    """Example 5: Async execution with retry and fallback."""

    print("\n=== Example 5: Async Execution ===")

    attempts = []

    async def async_primary(task):
        attempts.append(1)
        await asyncio.sleep(0.05)
        if len(attempts) < 2:
            raise ValueError(f"Async failure (attempt {len(attempts)})")
        return f"async_success_{task}"

    async def async_fallback(task):
        await asyncio.sleep(0.05)
        return f"async_fallback_{task}"

    config = RetryConfig(max_retries=2, backoff_ms=100)

    executor = RedundantExecutor(
        primary=async_primary,
        fallbacks=[async_fallback],
        config=config
    )

    result = await executor.async_execute("task_5")
    print(f"Result: {result}")
    print(f"Total attempts: {len(attempts)}")


def example_6_kloros_integration():
    """Example 6: Integration with KLoROS orchestration patterns."""

    print("\n=== Example 6: KLoROS Integration ===")

    def primary_spica_executor(observation):
        logger.info(f"Primary SPICA processing: {observation}")
        if observation.get('complexity') == 'high':
            raise RuntimeError("High complexity requires fallback")
        return {'status': 'primary_success', 'observation': observation}

    def fallback_baseline_executor(observation):
        logger.info(f"Fallback baseline processing: {observation}")
        return {'status': 'fallback_baseline', 'observation': observation}

    def fallback_emergency_executor(observation):
        logger.info(f"Emergency fallback: {observation}")
        return {'status': 'emergency_fallback', 'observation': observation}

    config = RetryConfig(
        max_retries=2,
        backoff_ms=200,
        timeout_ms=30000
    )

    executor = RedundantExecutor(
        primary=primary_spica_executor,
        fallbacks=[
            fallback_baseline_executor,
            fallback_emergency_executor
        ],
        config=config
    )

    observations = [
        {'id': 1, 'complexity': 'low', 'data': 'simple_case'},
        {'id': 2, 'complexity': 'high', 'data': 'complex_case'},
    ]

    for obs in observations:
        result = executor.execute(obs)
        print(f"Observation {obs['id']}: {result['status']}")


def example_7_custom_config():
    """Example 7: Custom retry configuration."""

    print("\n=== Example 7: Custom Configuration ===")

    aggressive_config = RetryConfig(
        max_retries=5,
        backoff_ms=50,
        timeout_ms=10000
    )

    conservative_config = RetryConfig(
        max_retries=1,
        backoff_ms=500,
        timeout_ms=60000
    )

    def flaky_task(task):
        import random
        if random.random() < 0.7:
            raise ValueError("Random failure")
        return f"success_{task}"

    print("Aggressive retry strategy:")
    executor_aggressive = RedundantExecutor(
        primary=flaky_task,
        config=aggressive_config
    )

    try:
        result = executor_aggressive.execute("aggressive_task")
        print(f"Success: {result}")
    except ExecutionExhaustedError as e:
        print(f"Failed after {len(e.errors)} attempts")


if __name__ == "__main__":
    print("=" * 60)
    print("RedundantExecutor Usage Examples")
    print("=" * 60)

    example_1_basic_usage()
    example_2_retry_on_failure()
    example_3_fallback_chain()
    example_4_complete_failure()

    print("\nRunning async example...")
    asyncio.run(example_5_async_execution())

    example_6_kloros_integration()
    example_7_custom_config()

    print("\n" + "=" * 60)
    print("All examples completed!")
    print("=" * 60)
