#!/usr/bin/env python3
"""
Tests for RedundantExecutor

Validates retry logic, fallback execution, timeout enforcement,
and both sync/async execution paths.
"""

import pytest
import asyncio
import time
from unittest.mock import Mock, patch

from src.orchestration.core.redundant_executor import (
    RedundantExecutor,
    RetryConfig,
    ExecutionExhaustedError,
)


class TestRetryConfig:
    """Test RetryConfig validation."""

    def test_default_values(self):
        config = RetryConfig()
        assert config.max_retries == 2
        assert config.backoff_ms == 100
        assert config.timeout_ms == 30000

    def test_custom_values(self):
        config = RetryConfig(max_retries=5, backoff_ms=200, timeout_ms=60000)
        assert config.max_retries == 5
        assert config.backoff_ms == 200
        assert config.timeout_ms == 60000

    def test_validation_negative_retries(self):
        with pytest.raises(ValueError, match="max_retries must be non-negative"):
            RetryConfig(max_retries=-1)

    def test_validation_invalid_backoff(self):
        with pytest.raises(ValueError, match="backoff_ms must be positive"):
            RetryConfig(backoff_ms=0)

    def test_validation_invalid_timeout(self):
        with pytest.raises(ValueError, match="timeout_ms must be positive"):
            RetryConfig(timeout_ms=-100)


class TestRedundantExecutorSync:
    """Test synchronous execution."""

    def test_primary_success_first_attempt(self):
        def primary(task):
            return f"primary_{task}"

        executor = RedundantExecutor(primary)
        result = executor.execute("test_task")

        assert result == "primary_test_task"
        assert len(executor._errors) == 0

    def test_primary_success_after_retry(self):
        attempts = []

        def primary(task):
            attempts.append(1)
            if len(attempts) < 2:
                raise ValueError("Simulated failure")
            return f"primary_{task}"

        config = RetryConfig(max_retries=2, backoff_ms=10)
        executor = RedundantExecutor(primary, config=config)
        result = executor.execute("test_task")

        assert result == "primary_test_task"
        assert len(attempts) == 2
        assert len(executor._errors) == 1

    def test_fallback_used_after_primary_exhausted(self):
        def primary(task):
            raise ValueError("Primary always fails")

        def fallback1(task):
            raise ValueError("Fallback1 fails")

        def fallback2(task):
            return f"fallback2_{task}"

        config = RetryConfig(max_retries=1, backoff_ms=10)
        executor = RedundantExecutor(
            primary,
            fallbacks=[fallback1, fallback2],
            config=config
        )
        result = executor.execute("test_task")

        assert result == "fallback2_test_task"
        assert len(executor._errors) == 3

    def test_all_executors_exhausted(self):
        def primary(task):
            raise ValueError("Primary fails")

        def fallback1(task):
            raise RuntimeError("Fallback1 fails")

        def fallback2(task):
            raise TypeError("Fallback2 fails")

        config = RetryConfig(max_retries=1, backoff_ms=10)
        executor = RedundantExecutor(
            primary,
            fallbacks=[fallback1, fallback2],
            config=config
        )

        with pytest.raises(ExecutionExhaustedError) as exc_info:
            executor.execute("test_task")

        assert "All executors failed" in str(exc_info.value)
        assert len(exc_info.value.errors) == 4
        assert len(executor._errors) == 4

    def test_exponential_backoff(self):
        attempts = []

        def primary(task):
            attempts.append(time.time())
            raise ValueError("Always fails")

        config = RetryConfig(max_retries=2, backoff_ms=100)
        executor = RedundantExecutor(primary, config=config)

        try:
            executor.execute("test_task")
        except ExecutionExhaustedError:
            pass

        assert len(attempts) == 3

        if len(attempts) >= 3:
            delay1 = (attempts[1] - attempts[0]) * 1000
            delay2 = (attempts[2] - attempts[1]) * 1000

            assert delay1 >= 90
            assert delay2 >= 180
            assert delay2 > delay1

    def test_no_fallbacks(self):
        def primary(task):
            return f"primary_{task}"

        executor = RedundantExecutor(primary)
        result = executor.execute("test_task")

        assert result == "primary_test_task"

    def test_empty_fallbacks_list(self):
        def primary(task):
            return f"primary_{task}"

        executor = RedundantExecutor(primary, fallbacks=[])
        result = executor.execute("test_task")

        assert result == "primary_test_task"

    def test_zero_retries(self):
        attempts = []

        def primary(task):
            attempts.append(1)
            raise ValueError("Fails")

        config = RetryConfig(max_retries=0, backoff_ms=10)
        executor = RedundantExecutor(primary, config=config)

        with pytest.raises(ExecutionExhaustedError):
            executor.execute("test_task")

        assert len(attempts) == 1

    @patch('kloros.orchestration.redundant_executor.logger')
    def test_logging_primary_success(self, mock_logger):
        def primary(task):
            return "success"

        executor = RedundantExecutor(primary)
        executor.execute("test_task")

        assert any("Primary executor succeeded" in str(call) for call in mock_logger.info.call_args_list)

    @patch('kloros.orchestration.redundant_executor.logger')
    def test_logging_fallback_used(self, mock_logger):
        def primary(task):
            raise ValueError("Primary fails")

        def fallback(task):
            return "fallback_success"

        config = RetryConfig(max_retries=0, backoff_ms=10)
        executor = RedundantExecutor(primary, fallbacks=[fallback], config=config)
        executor.execute("test_task")

        assert any("Fallback executor succeeded" in str(call) for call in mock_logger.info.call_args_list)

    @patch('kloros.orchestration.redundant_executor.logger')
    def test_logging_total_failure(self, mock_logger):
        def primary(task):
            raise ValueError("Fails")

        config = RetryConfig(max_retries=0, backoff_ms=10)
        executor = RedundantExecutor(primary, config=config)

        try:
            executor.execute("test_task")
        except ExecutionExhaustedError:
            pass

        assert any("All executors exhausted" in str(call) for call in mock_logger.error.call_args_list)


class TestRedundantExecutorAsync:
    """Test asynchronous execution."""

    @pytest.mark.asyncio
    async def test_async_primary_success(self):
        async def primary(task):
            await asyncio.sleep(0.01)
            return f"async_primary_{task}"

        executor = RedundantExecutor(primary)
        result = await executor.async_execute("test_task")

        assert result == "async_primary_test_task"
        assert len(executor._errors) == 0

    @pytest.mark.asyncio
    async def test_async_primary_retry(self):
        attempts = []

        async def primary(task):
            attempts.append(1)
            await asyncio.sleep(0.01)
            if len(attempts) < 2:
                raise ValueError("Simulated failure")
            return f"async_primary_{task}"

        config = RetryConfig(max_retries=2, backoff_ms=10)
        executor = RedundantExecutor(primary, config=config)
        result = await executor.async_execute("test_task")

        assert result == "async_primary_test_task"
        assert len(attempts) == 2

    @pytest.mark.asyncio
    async def test_async_fallback_used(self):
        async def primary(task):
            raise ValueError("Primary fails")

        async def fallback(task):
            await asyncio.sleep(0.01)
            return f"async_fallback_{task}"

        config = RetryConfig(max_retries=0, backoff_ms=10)
        executor = RedundantExecutor(
            primary,
            fallbacks=[fallback],
            config=config
        )
        result = await executor.async_execute("test_task")

        assert result == "async_fallback_test_task"

    @pytest.mark.asyncio
    async def test_async_all_exhausted(self):
        async def primary(task):
            raise ValueError("Primary fails")

        async def fallback(task):
            raise RuntimeError("Fallback fails")

        config = RetryConfig(max_retries=1, backoff_ms=10)
        executor = RedundantExecutor(
            primary,
            fallbacks=[fallback],
            config=config
        )

        with pytest.raises(ExecutionExhaustedError) as exc_info:
            await executor.async_execute("test_task")

        assert len(exc_info.value.errors) == 3

    @pytest.mark.asyncio
    async def test_async_timeout(self):
        async def slow_primary(task):
            await asyncio.sleep(10)
            return "should_timeout"

        config = RetryConfig(max_retries=0, backoff_ms=10, timeout_ms=100)
        executor = RedundantExecutor(slow_primary, config=config)

        with pytest.raises(ExecutionExhaustedError) as exc_info:
            await executor.async_execute("test_task")

        assert any(isinstance(e, TimeoutError) for e in exc_info.value.errors)


class TestMetricsLogging:
    """Test metric emission."""

    @patch('kloros.orchestration.redundant_executor.logger')
    def test_metric_primary_success(self, mock_logger):
        def primary(task):
            return "success"

        executor = RedundantExecutor(primary)
        executor.execute("test_task")

        metric_calls = [str(call) for call in mock_logger.info.call_args_list]
        assert any("redundant_execution_primary_success" in call for call in metric_calls)

    @patch('kloros.orchestration.redundant_executor.logger')
    def test_metric_fallback_used(self, mock_logger):
        def primary(task):
            raise ValueError("Fails")

        def fallback(task):
            return "success"

        config = RetryConfig(max_retries=0, backoff_ms=10)
        executor = RedundantExecutor(primary, fallbacks=[fallback], config=config)
        executor.execute("test_task")

        metric_calls = [str(call) for call in mock_logger.info.call_args_list]
        assert any("redundant_execution_fallback_used" in call for call in metric_calls)

    @patch('kloros.orchestration.redundant_executor.logger')
    def test_metric_total_failure(self, mock_logger):
        def primary(task):
            raise ValueError("Fails")

        config = RetryConfig(max_retries=0, backoff_ms=10)
        executor = RedundantExecutor(primary, config=config)

        try:
            executor.execute("test_task")
        except ExecutionExhaustedError:
            pass

        metric_calls = [str(call) for call in mock_logger.info.call_args_list]
        assert any("redundant_execution_total_failure" in call for call in metric_calls)
