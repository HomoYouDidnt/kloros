#!/usr/bin/env python3
"""
Speculative Executor - Background prefetch for KLoROS orchestration.

Implements speculative execution by predicting and prefetching likely next actions
based on context and historical patterns. Reduces latency for predicted workflows
by executing operations in background threads before they are explicitly requested.
"""

import time
import logging
import threading
from dataclasses import dataclass, field
from typing import Dict, List, Tuple, Callable, Any, Optional
from concurrent.futures import ThreadPoolExecutor, Future
from prometheus_client import Counter, Gauge

logger = logging.getLogger(__name__)

speculative_hit_total = Counter(
    "kloros_speculative_hit_total",
    "Total speculative execution cache hits"
)
speculative_miss_total = Counter(
    "kloros_speculative_miss_total",
    "Total speculative execution cache misses"
)
speculative_waste_total = Counter(
    "kloros_speculative_waste_total",
    "Total speculative executions that were never used"
)
speculative_prefetch_total = Counter(
    "kloros_speculative_prefetch_total",
    "Total speculative prefetch operations started",
    ["action_type"]
)
speculative_cache_size = Gauge(
    "kloros_speculative_cache_size",
    "Current number of entries in prefetch cache"
)
speculative_pending_size = Gauge(
    "kloros_speculative_pending_size",
    "Current number of pending prefetch operations"
)


@dataclass
class PrefetchResult:
    """Result of a prefetch operation."""
    result: Any
    timestamp: float
    action_key: str
    confidence: float = 0.0


@dataclass
class PredictionContext:
    """Context for predicting next actions."""
    last_action: str
    action_result: Optional[Any] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


class NextActionPredictor:
    """
    Predicts likely next actions based on context and heuristics.

    Uses pattern-based prediction rules to estimate which actions are likely
    to follow the current action, along with confidence scores.
    """

    def __init__(self):
        self._prediction_rules = self._build_prediction_rules()

    def _build_prediction_rules(self) -> Dict[str, List[Tuple[str, float]]]:
        """
        Build heuristic prediction rules.

        Returns:
            Dict mapping action -> List[(next_action, confidence)]
        """
        return {
            "curiosity_question": [
                ("investigation", 0.9),
                ("file_read", 0.7),
            ],
            "code_search": [
                ("file_read", 0.8),
                ("symbol_lookup", 0.75),
            ],
            "error_detection": [
                ("stack_trace_analysis", 0.85),
                ("log_search", 0.8),
            ],
            "file_read": [
                ("related_file_read", 0.7),
                ("code_analysis", 0.65),
            ],
            "investigation": [
                ("evidence_collection", 0.85),
                ("hypothesis_generation", 0.75),
            ],
            "stack_trace_analysis": [
                ("source_location_lookup", 0.9),
                ("variable_inspection", 0.75),
            ],
            "log_search": [
                ("error_extraction", 0.8),
                ("timeline_construction", 0.7),
            ],
        }

    def predict_next(self, context: PredictionContext) -> List[Tuple[str, float]]:
        """
        Predict likely next actions based on current context.

        Args:
            context: Current execution context

        Returns:
            List of (action_name, confidence) tuples sorted by confidence descending
        """
        last_action = context.last_action

        predictions = self._prediction_rules.get(last_action, [])

        metadata = context.metadata or {}
        if "error_detected" in metadata:
            predictions.append(("error_analysis", 0.85))

        if "file_path" in metadata:
            predictions.append(("dependency_scan", 0.7))

        predictions_sorted = sorted(predictions, key=lambda x: x[1], reverse=True)

        logger.debug(f"Predicted {len(predictions_sorted)} next actions for '{last_action}'")

        return predictions_sorted


class SpeculativeExecutor:
    """
    Manages speculative execution and prefetching of predicted actions.

    Spawns background threads to execute predicted actions before they are
    requested. Results are cached and returned immediately when requested,
    falling back to synchronous execution if not cached.
    """

    def __init__(
        self,
        confidence_threshold: float = 0.7,
        max_workers: int = 2,
        cache_ttl_seconds: int = 60
    ):
        """
        Initialize speculative executor.

        Args:
            confidence_threshold: Minimum confidence to trigger prefetch (0.0-1.0)
            max_workers: Maximum concurrent prefetch threads
            cache_ttl_seconds: Cache entry time-to-live in seconds
        """
        self.confidence_threshold = confidence_threshold
        self.cache_ttl_seconds = cache_ttl_seconds

        self.prefetch_cache: Dict[str, PrefetchResult] = {}
        self.pending_prefetches: Dict[str, Future] = {}

        self._cache_lock = threading.Lock()
        self._pending_lock = threading.Lock()

        self.executor = ThreadPoolExecutor(
            max_workers=max_workers,
            thread_name_prefix="speculative"
        )

        self.prediction_model = NextActionPredictor()

        self._total_hits = 0
        self._total_misses = 0
        self._total_wasted = 0

        logger.info(
            f"SpeculativeExecutor initialized: "
            f"threshold={confidence_threshold}, "
            f"workers={max_workers}, "
            f"ttl={cache_ttl_seconds}s"
        )

    def speculate_next(
        self,
        context: PredictionContext,
        executor_fn: Callable[[str], Any]
    ) -> int:
        """
        Spawn prefetch operations for predicted next actions.

        Args:
            context: Current execution context
            executor_fn: Function to execute for each predicted action
                         Takes action_key as argument

        Returns:
            Number of prefetch operations spawned
        """
        predictions = self.prediction_model.predict_next(context)

        spawned = 0
        for action_key, confidence in predictions:
            if confidence < self.confidence_threshold:
                logger.debug(
                    f"Skipping prefetch for '{action_key}': "
                    f"confidence {confidence:.2f} below threshold {self.confidence_threshold:.2f}"
                )
                continue

            with self._cache_lock:
                if action_key in self.prefetch_cache:
                    logger.debug(f"Prefetch for '{action_key}' already cached")
                    continue

            with self._pending_lock:
                if action_key in self.pending_prefetches:
                    logger.debug(f"Prefetch for '{action_key}' already pending")
                    continue

            logger.info(
                f"Spawning speculative prefetch for '{action_key}' "
                f"(confidence: {confidence:.2f})"
            )

            future = self.executor.submit(
                self._prefetch_worker,
                action_key,
                executor_fn,
                confidence
            )

            with self._pending_lock:
                self.pending_prefetches[action_key] = future

            speculative_prefetch_total.labels(action_type=action_key).inc()
            spawned += 1

        self._evict_stale()
        self._update_metrics()

        return spawned

    def _prefetch_worker(
        self,
        action_key: str,
        executor_fn: Callable[[str], Any],
        confidence: float
    ):
        """
        Background worker that executes prefetch and caches result.

        Args:
            action_key: Unique key for the action being prefetched
            executor_fn: Function to execute
            confidence: Prediction confidence score
        """
        try:
            logger.debug(f"Prefetch worker starting for '{action_key}'")

            result = executor_fn(action_key)

            prefetch_result = PrefetchResult(
                result=result,
                timestamp=time.time(),
                action_key=action_key,
                confidence=confidence
            )

            with self._cache_lock:
                self.prefetch_cache[action_key] = prefetch_result

            logger.debug(f"Prefetch completed for '{action_key}'")

        except Exception as e:
            logger.warning(f"Prefetch failed for '{action_key}': {e}")

        finally:
            with self._pending_lock:
                self.pending_prefetches.pop(action_key, None)

    def get_or_execute(
        self,
        action_key: str,
        executor_fn: Callable[[str], Any],
        timeout_seconds: float = 5.0
    ) -> Any:
        """
        Get cached result or execute synchronously.

        First checks prefetch cache for existing result. If found and still valid,
        returns immediately (cache hit). Otherwise checks if prefetch is pending
        and waits up to timeout. Finally falls back to synchronous execution.

        Args:
            action_key: Unique key for the action
            executor_fn: Function to execute if cache miss
            timeout_seconds: Maximum time to wait for pending prefetch

        Returns:
            Result of the action execution
        """
        with self._cache_lock:
            if action_key in self.prefetch_cache:
                cached = self.prefetch_cache[action_key]

                age = time.time() - cached.timestamp
                if age < self.cache_ttl_seconds:
                    logger.info(
                        f"Speculative cache HIT for '{action_key}' "
                        f"(age: {age:.1f}s, confidence: {cached.confidence:.2f})"
                    )
                    self._total_hits += 1
                    speculative_hit_total.inc()

                    del self.prefetch_cache[action_key]

                    return cached.result
                else:
                    logger.debug(f"Cached result for '{action_key}' is stale (age: {age:.1f}s)")
                    del self.prefetch_cache[action_key]
                    self._total_wasted += 1
                    speculative_waste_total.inc()

        with self._pending_lock:
            pending = self.pending_prefetches.get(action_key)

        if pending:
            logger.info(f"Waiting for pending prefetch '{action_key}' (timeout: {timeout_seconds}s)")
            try:
                pending.result(timeout=timeout_seconds)

                with self._cache_lock:
                    if action_key in self.prefetch_cache:
                        cached = self.prefetch_cache[action_key]
                        logger.info(f"Pending prefetch completed for '{action_key}'")
                        self._total_hits += 1
                        speculative_hit_total.inc()

                        del self.prefetch_cache[action_key]

                        return cached.result

            except Exception as e:
                logger.warning(f"Pending prefetch failed or timed out for '{action_key}': {e}")

        logger.info(f"Speculative cache MISS for '{action_key}' - executing synchronously")
        self._total_misses += 1
        speculative_miss_total.inc()

        return executor_fn(action_key)

    def _evict_stale(self):
        """Remove stale entries from cache that exceeded TTL."""
        now = time.time()
        evicted = []

        with self._cache_lock:
            for key, cached in list(self.prefetch_cache.items()):
                age = now - cached.timestamp
                if age > self.cache_ttl_seconds:
                    evicted.append(key)
                    del self.prefetch_cache[key]
                    self._total_wasted += 1
                    speculative_waste_total.inc()

        if evicted:
            logger.debug(f"Evicted {len(evicted)} stale cache entries: {evicted}")

    def _update_metrics(self):
        """Update Prometheus metrics."""
        with self._cache_lock:
            speculative_cache_size.set(len(self.prefetch_cache))

        with self._pending_lock:
            speculative_pending_size.set(len(self.pending_prefetches))

    def get_metrics(self) -> Dict[str, Any]:
        """
        Get current metrics snapshot.

        Returns:
            Dict with hit_rate, waste_rate, cache_size, pending_size
        """
        total = self._total_hits + self._total_misses
        hit_rate = self._total_hits / total if total > 0 else 0.0

        total_executed = self._total_hits + self._total_wasted
        waste_rate = self._total_wasted / total_executed if total_executed > 0 else 0.0

        with self._cache_lock:
            cache_size = len(self.prefetch_cache)

        with self._pending_lock:
            pending_size = len(self.pending_prefetches)

        return {
            "speculative_hit_rate": hit_rate,
            "speculative_waste_rate": waste_rate,
            "cache_size": cache_size,
            "pending_size": pending_size,
            "total_hits": self._total_hits,
            "total_misses": self._total_misses,
            "total_wasted": self._total_wasted,
        }

    def shutdown(self, wait: bool = True):
        """
        Shutdown executor and cleanup resources.

        Args:
            wait: If True, wait for pending operations to complete
        """
        logger.info("Shutting down SpeculativeExecutor")

        self.executor.shutdown(wait=wait)

        with self._cache_lock:
            wasted = len(self.prefetch_cache)
            self.prefetch_cache.clear()
            if wasted > 0:
                logger.info(f"Cleared {wasted} unused prefetch results on shutdown")
                self._total_wasted += wasted
                speculative_waste_total.inc(wasted)

        with self._pending_lock:
            self.pending_prefetches.clear()

        metrics = self.get_metrics()
        logger.info(
            f"SpeculativeExecutor shutdown complete. "
            f"Final metrics: hit_rate={metrics['speculative_hit_rate']:.2%}, "
            f"waste_rate={metrics['speculative_waste_rate']:.2%}"
        )

    def __enter__(self):
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit with cleanup."""
        self.shutdown(wait=True)
        return False
