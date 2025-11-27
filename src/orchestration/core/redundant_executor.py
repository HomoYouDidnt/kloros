#!/usr/bin/env python3
"""
KLoROS Redundant Execution Module

Provides retry + fallback execution for robust orchestration.

Execution flow:
1. Try primary executor with exponential backoff retries
2. On exhaustion, sequentially try fallback executors
3. Return first success or raise ExecutionExhaustedError
4. Emit metrics for observability

Design:
- RetryConfig: max_retries, backoff_ms, timeout_ms
- RedundantExecutor: primary + fallback chain + retry logic
- Supports both sync and async executors
- Bounded execution with configurable timeouts
"""

import time
import asyncio
import logging
from typing import Any, Callable, List, Optional, TypeVar, Union
from dataclasses import dataclass
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

T = TypeVar('T')


class ExecutionExhaustedError(Exception):
    """Raised when all executors (primary + fallbacks) have failed."""

    def __init__(self, message: str, errors: List[Exception]):
        super().__init__(message)
        self.errors = errors


@dataclass
class RetryConfig:
    """Configuration for retry behavior."""

    max_retries: int = 2
    backoff_ms: int = 100
    timeout_ms: int = 30000

    def __post_init__(self):
        if self.max_retries < 0:
            raise ValueError(f"max_retries must be non-negative, got {self.max_retries}")
        if self.backoff_ms <= 0:
            raise ValueError(f"backoff_ms must be positive, got {self.backoff_ms}")
        if self.timeout_ms <= 0:
            raise ValueError(f"timeout_ms must be positive, got {self.timeout_ms}")


class RedundantExecutor:
    """
    Executes tasks with retry logic and fallback chain.

    Execution strategy:
    1. Primary executor: max_retries attempts with exponential backoff
    2. Each fallback: single attempt, no retry
    3. First success returns immediately
    4. All failures raise ExecutionExhaustedError

    Thread-safe for synchronous executors.
    """

    def __init__(
        self,
        primary: Callable[[Any], Any],
        fallbacks: Optional[List[Callable[[Any], Any]]] = None,
        config: Optional[RetryConfig] = None
    ):
        self.primary = primary
        self.fallbacks = fallbacks or []
        self.config = config or RetryConfig()
        self._errors: List[Exception] = []

        logger.info(
            f"RedundantExecutor initialized: primary={primary.__name__}, "
            f"fallbacks={len(self.fallbacks)}, max_retries={self.config.max_retries}"
        )

    def execute(self, task: Any) -> Any:
        """
        Execute task with retry and fallback logic.

        Args:
            task: Task payload to execute

        Returns:
            Result from first successful executor

        Raises:
            ExecutionExhaustedError: All executors failed
        """
        self._errors = []
        start_time = time.time()

        result = self._try_primary(task)
        if result is not None:
            self._log_metric("redundant_execution_primary_success")
            elapsed_ms = int((time.time() - start_time) * 1000)
            logger.info(f"Primary executor succeeded in {elapsed_ms}ms")
            return result

        result = self._try_fallbacks(task)
        if result is not None:
            self._log_metric("redundant_execution_fallback_used")
            elapsed_ms = int((time.time() - start_time) * 1000)
            logger.info(f"Fallback executor succeeded in {elapsed_ms}ms after primary exhausted")
            return result

        self._log_metric("redundant_execution_total_failure")
        elapsed_ms = int((time.time() - start_time) * 1000)
        logger.error(
            f"All executors exhausted in {elapsed_ms}ms: "
            f"primary={self.primary.__name__}, fallbacks={len(self.fallbacks)}, "
            f"total_errors={len(self._errors)}"
        )

        raise ExecutionExhaustedError(
            f"All executors failed: {len(self._errors)} attempts",
            self._errors
        )

    async def async_execute(self, task: Any) -> Any:
        """
        Execute task asynchronously with retry and fallback logic.

        Args:
            task: Task payload to execute

        Returns:
            Result from first successful executor

        Raises:
            ExecutionExhaustedError: All executors failed
        """
        self._errors = []
        start_time = time.time()

        result = await self._try_primary_async(task)
        if result is not None:
            self._log_metric("redundant_execution_primary_success")
            elapsed_ms = int((time.time() - start_time) * 1000)
            logger.info(f"Primary executor succeeded in {elapsed_ms}ms (async)")
            return result

        result = await self._try_fallbacks_async(task)
        if result is not None:
            self._log_metric("redundant_execution_fallback_used")
            elapsed_ms = int((time.time() - start_time) * 1000)
            logger.info(f"Fallback executor succeeded in {elapsed_ms}ms after primary exhausted (async)")
            return result

        self._log_metric("redundant_execution_total_failure")
        elapsed_ms = int((time.time() - start_time) * 1000)
        logger.error(
            f"All async executors exhausted in {elapsed_ms}ms: "
            f"primary={self.primary.__name__}, fallbacks={len(self.fallbacks)}, "
            f"total_errors={len(self._errors)}"
        )

        raise ExecutionExhaustedError(
            f"All async executors failed: {len(self._errors)} attempts",
            self._errors
        )

    def _try_primary(self, task: Any) -> Optional[Any]:
        """Execute primary with retry logic."""
        for attempt in range(self.config.max_retries + 1):
            try:
                logger.debug(
                    f"Primary executor attempt {attempt + 1}/{self.config.max_retries + 1}: "
                    f"{self.primary.__name__}"
                )
                result = self._execute_with_timeout(self.primary, task)
                return result

            except Exception as e:
                self._errors.append(e)
                logger.warning(
                    f"Primary executor failed on attempt {attempt + 1}: {type(e).__name__}: {e}"
                )

                if attempt < self.config.max_retries:
                    backoff_ms = self.config.backoff_ms * (2 ** attempt)
                    logger.debug(f"Backing off for {backoff_ms}ms before retry")
                    time.sleep(backoff_ms / 1000.0)

        return None

    async def _try_primary_async(self, task: Any) -> Optional[Any]:
        """Execute primary asynchronously with retry logic."""
        for attempt in range(self.config.max_retries + 1):
            try:
                logger.debug(
                    f"Primary async executor attempt {attempt + 1}/{self.config.max_retries + 1}: "
                    f"{self.primary.__name__}"
                )
                result = await self._execute_with_timeout_async(self.primary, task)
                return result

            except Exception as e:
                self._errors.append(e)
                logger.warning(
                    f"Primary async executor failed on attempt {attempt + 1}: {type(e).__name__}: {e}"
                )

                if attempt < self.config.max_retries:
                    backoff_ms = self.config.backoff_ms * (2 ** attempt)
                    logger.debug(f"Backing off for {backoff_ms}ms before retry (async)")
                    await asyncio.sleep(backoff_ms / 1000.0)

        return None

    def _try_fallbacks(self, task: Any) -> Optional[Any]:
        """Try each fallback executor once."""
        for idx, fallback in enumerate(self.fallbacks):
            try:
                logger.info(
                    f"Trying fallback executor {idx + 1}/{len(self.fallbacks)}: {fallback.__name__}"
                )
                result = self._execute_with_timeout(fallback, task)
                logger.info(f"Fallback executor {fallback.__name__} succeeded")
                return result

            except Exception as e:
                self._errors.append(e)
                logger.warning(
                    f"Fallback executor {fallback.__name__} failed: {type(e).__name__}: {e}"
                )

        return None

    async def _try_fallbacks_async(self, task: Any) -> Optional[Any]:
        """Try each fallback executor once asynchronously."""
        for idx, fallback in enumerate(self.fallbacks):
            try:
                logger.info(
                    f"Trying fallback async executor {idx + 1}/{len(self.fallbacks)}: {fallback.__name__}"
                )
                result = await self._execute_with_timeout_async(fallback, task)
                logger.info(f"Fallback async executor {fallback.__name__} succeeded")
                return result

            except Exception as e:
                self._errors.append(e)
                logger.warning(
                    f"Fallback async executor {fallback.__name__} failed: {type(e).__name__}: {e}"
                )

        return None

    def _execute_with_timeout(self, executor: Callable, task: Any) -> Any:
        """Execute with timeout enforcement."""
        import signal

        def timeout_handler(signum, frame):
            raise TimeoutError(f"Executor {executor.__name__} exceeded {self.config.timeout_ms}ms timeout")

        old_handler = signal.signal(signal.SIGALRM, timeout_handler)
        signal.setitimer(signal.ITIMER_REAL, self.config.timeout_ms / 1000.0)

        try:
            result = executor(task)
            return result
        finally:
            signal.setitimer(signal.ITIMER_REAL, 0)
            signal.signal(signal.SIGALRM, old_handler)

    async def _execute_with_timeout_async(self, executor: Callable, task: Any) -> Any:
        """Execute asynchronously with timeout enforcement."""
        try:
            result = await asyncio.wait_for(
                executor(task),
                timeout=self.config.timeout_ms / 1000.0
            )
            return result
        except asyncio.TimeoutError:
            raise TimeoutError(
                f"Async executor {executor.__name__} exceeded {self.config.timeout_ms}ms timeout"
            )

    def _log_metric(self, metric_name: str) -> None:
        """Log metric event for observability."""
        logger.info(f"METRIC: {metric_name} timestamp={datetime.now(timezone.utc).isoformat()}")
