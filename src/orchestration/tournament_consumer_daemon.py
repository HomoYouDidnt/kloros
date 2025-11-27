"""
Tournament Consumer Daemon - Async SPICA tournament processor.

Subscribes to Q_CURIOSITY_INVESTIGATE chemical signals and runs tournaments
asynchronously with rate limiting to prevent memory issues.

Key features:
- Single tournament at a time (prevents memory spikes)
- Rate limiting (configurable cooldown between tournaments)
- Circuit breaker for failure resilience
- Uses bracket tournament for fast execution
- Queue system (stores deferred signals instead of dropping them)
- Convergence detection (stops when results stabilize)
"""
import json
import time
import logging
import threading
from pathlib import Path
from typing import Dict, Any, Optional
from collections import deque, defaultdict
import os
import sys

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from kloros.orchestration.chem_bus_v2 import _ZmqSub
from kloros.orchestration.maintenance_mode import wait_for_normal_mode
import zmq

logger = logging.getLogger(__name__)

# Rate limiting
MIN_TOURNAMENT_INTERVAL_SEC = int(os.getenv("KLR_MIN_TOURNAMENT_INTERVAL", "60"))  # Default: 1 minute between tournaments

# Concurrency control
_tournament_lock = threading.Lock()
_last_tournament_time = 0.0

# Circuit breaker
_circuit_open_until: Optional[float] = None
_tournament_failures = []

# Tournament queue (stores pending requests instead of dropping them)
_tournament_queue: deque = deque(maxlen=100)  # Max 100 pending tournaments
_queue_lock = threading.Lock()

# Convergence tracking (question_id -> list of recent fitnesses)
_convergence_history: Dict[str, list] = defaultdict(lambda: [])
CONVERGENCE_WINDOW = 5  # Check last 5 tournaments
CONVERGENCE_THRESHOLD = 0.02  # If variance < 0.02 for 5 runs, converged


class TournamentConsumer:
    """
    Consumes Q_CURIOSITY_INVESTIGATE chemical signals and runs tournaments asynchronously.

    Prevents memory issues by:
    - Running only one tournament at a time
    - Rate limiting (minimum interval between tournaments)
    - Circuit breaker on repeated failures
    """

    def __init__(self):
        self.running = False
        self.subscriber = None
        self.tournament_count = 0
        self.queue_worker_thread = None

    def _can_run_tournament(self) -> tuple[bool, str]:
        """Check if tournament can run based on rate limiting and circuit breaker."""
        global _last_tournament_time, _circuit_open_until

        current_time = time.time()

        # Check circuit breaker
        if _circuit_open_until is not None and current_time < _circuit_open_until:
            remaining = int(_circuit_open_until - current_time)
            return False, f"circuit_breaker (cooldown: {remaining}s remaining)"

        # Circuit cooldown expired
        if _circuit_open_until is not None and current_time >= _circuit_open_until:
            logger.info("[tournament_consumer] Circuit breaker cooldown expired - closing circuit")
            _circuit_open_until = None

        # Check rate limit
        time_since_last = current_time - _last_tournament_time
        if time_since_last < MIN_TOURNAMENT_INTERVAL_SEC:
            remaining = int(MIN_TOURNAMENT_INTERVAL_SEC - time_since_last)
            return False, f"rate_limit (wait {remaining}s)"

        return True, "ok"

    def _record_failure(self):
        """Record tournament failure for circuit breaker."""
        global _tournament_failures, _circuit_open_until

        current_time = time.time()

        # Clean old failures (older than 2 minutes)
        _tournament_failures = [t for t in _tournament_failures if current_time - t < 120]

        # Record new failure
        _tournament_failures.append(current_time)

        # Open circuit if 3+ failures in 2 minutes
        if len(_tournament_failures) >= 3:
            cooldown_sec = 600  # 10 minutes
            _circuit_open_until = current_time + cooldown_sec
            logger.error(
                f"[tournament_consumer] Circuit breaker OPENED: {len(_tournament_failures)} failures in 2 minutes, "
                f"blocking tournaments for {cooldown_sec}s"
            )

    def _has_converged(self, question_id: str, new_fitness: float) -> bool:
        """
        Check if a question has converged (stable results over multiple tournaments).

        Args:
            question_id: The question being tested
            new_fitness: Latest fitness score

        Returns:
            True if converged (stable results), False otherwise
        """
        global _convergence_history

        # Add new fitness to history
        _convergence_history[question_id].append(new_fitness)

        # Keep only recent history
        if len(_convergence_history[question_id]) > CONVERGENCE_WINDOW:
            _convergence_history[question_id] = _convergence_history[question_id][-CONVERGENCE_WINDOW:]

        # Need at least CONVERGENCE_WINDOW samples to check convergence
        if len(_convergence_history[question_id]) < CONVERGENCE_WINDOW:
            return False

        # Calculate variance of recent fitnesses
        recent = _convergence_history[question_id]
        mean = sum(recent) / len(recent)
        variance = sum((x - mean) ** 2 for x in recent) / len(recent)

        is_converged = variance < CONVERGENCE_THRESHOLD

        if is_converged:
            logger.info(
                f"[tournament_consumer] CONVERGED: {question_id} "
                f"(variance={variance:.4f}, mean={mean:.3f}, n={len(recent)})"
            )

        return is_converged

    def _emit_winner(
        self,
        question_id: str,
        champion_id: str,
        candidates: list,
        fitnesses: list,
        artifacts: dict,
        context: dict
    ):
        """
        Extract champion parameters and emit winner file for deployment.

        This is the CRITICAL step that closes the autonomous loop:
        Tournament → Winner File → Winner Deployer → Config Application
        """
        try:
            # Find champion's index in fitnesses
            if not fitnesses:
                logger.warning(f"[tournament_consumer] No fitnesses for {question_id}, skipping winner emission")
                return

            max_fitness = max(fitnesses)
            champion_idx = fitnesses.index(max_fitness)

            # Extract champion params
            champion_params = candidates[champion_idx] if champion_idx < len(candidates) else {}

            # Get instance map for additional metadata
            instance_map = artifacts.get("instance_map", [])
            champion_metadata = {}
            if champion_idx < len(instance_map):
                champion_metadata = instance_map[champion_idx]

            # Create winner record
            winner_record = {
                "updated_at": int(time.time()),
                "question_id": question_id,
                "hypothesis": context.get("hypothesis", ""),
                "best": {
                    "fitness": max_fitness,
                    "params": champion_params,
                    "metrics": champion_metadata.get("metrics"),
                    "spica_id": champion_id
                },
                "tournament_summary": {
                    "champion_idx": champion_idx,
                    "total_candidates": len(candidates),
                    "fitness_range": {
                        "max": max_fitness,
                        "min": min(fitnesses) if fitnesses else 0.0,
                        "avg": sum(fitnesses) / len(fitnesses) if fitnesses else 0.0
                    },
                    "all_fitnesses": fitnesses
                }
            }

            # Write to winners directory
            winners_dir = Path("/home/kloros/artifacts/dream/winners")
            winners_dir.mkdir(parents=True, exist_ok=True)

            # Sanitize question_id for filename (replace special chars)
            safe_name = "".join(c if c.isalnum() or c in "._-" else "_" for c in question_id)
            winner_file = winners_dir / f"{safe_name}.json"

            with open(winner_file, 'w') as f:
                json.dump(winner_record, f, indent=2)

            logger.info(
                f"[tournament_consumer] Winner emitted: {winner_file.name} "
                f"(champion={champion_id}, fitness={max_fitness:.3f})"
            )

        except Exception as e:
            logger.error(f"[tournament_consumer] Failed to emit winner for {question_id}: {e}", exc_info=True)

    def _execute_tournament(self, question_data: Dict[str, Any]):
        """Execute tournament logic (assumes lock is already held)."""
        global _last_tournament_time

        question_id = question_data.get("question_id", "unknown")
        hypothesis = question_data.get("hypothesis", "")

        # Skip module discovery tasks - these are handled by investigation consumer
        if question_id.startswith("discover.module."):
            logger.debug(f"[tournament_consumer] Skipping module discovery task: {question_id}")
            return

        # Check convergence - skip if already converged
        if _convergence_history.get(question_id) and len(_convergence_history[question_id]) >= CONVERGENCE_WINDOW:
            # Calculate current variance to check if still converged
            recent = _convergence_history[question_id][-CONVERGENCE_WINDOW:]
            mean = sum(recent) / len(recent)
            variance = sum((x - mean) ** 2 for x in recent) / len(recent)

            if variance < CONVERGENCE_THRESHOLD:
                logger.info(
                    f"[tournament_consumer] Skipping {question_id}: already converged "
                    f"(variance={variance:.4f}, mean={mean:.3f})"
                )
                return

        logger.info(f"[tournament_consumer] Starting tournament for {question_id}: {hypothesis[:100]}")

        try:
            # Import here to avoid circular dependencies
            from integrations.spica_spawn import prune_instances
            from kloros.orchestration.chamber_mapper import get_chamber_mapper
            from dream.dream_config_loader import get_dream_config
            import random

            # Pre-tournament cleanup
            try:
                prune_result = prune_instances(max_instances=2, max_age_days=1, dry_run=False)
                logger.info(f"[tournament_consumer] Pre-tournament cleanup: pruned {prune_result.get('pruned', 0)} instances")
                if prune_result.get('pruned', 0) > 0:
                    time.sleep(1)
            except Exception as e:
                logger.warning(f"[tournament_consumer] Pre-tournament cleanup failed (non-fatal): {e}")

            # Map question to appropriate test chamber
            chamber_mapper = get_chamber_mapper()
            question_text = question_data.get("question", hypothesis)
            chamber_name = chamber_mapper.map_question_to_chamber(question_text, question_id)

            if not chamber_name:
                logger.warning(f"[tournament_consumer] No chamber match for {question_id}, using default")
                chamber_name = chamber_mapper.get_default_chamber()

            if not chamber_name:
                logger.error(f"[tournament_consumer] No chambers available for {question_id}, skipping tournament")
                return

            logger.info(f"[tournament_consumer] Selected chamber: {chamber_name}")
            logger.info(f"[tournament_consumer] Chamber tests: {chamber_mapper.get_chamber_description(chamber_name)}")

            # Load D-REAM config for this chamber
            dream_config = get_dream_config()
            experiment = dream_config.get_experiment(chamber_name)

            if not experiment:
                logger.error(f"[tournament_consumer] Chamber config not found: {chamber_name}")
                return

            # Get evaluator class dynamically
            evaluator_class = dream_config.get_evaluator_class(chamber_name)
            if not evaluator_class:
                logger.error(f"[tournament_consumer] Failed to load evaluator for {chamber_name}")
                return

            # Get init kwargs for evaluator
            init_kwargs = dream_config.get_evaluator_init_kwargs(chamber_name)

            # Get search space for parameter generation
            search_space = dream_config.get_search_space(chamber_name)

            # Prepare tournament context
            context = {
                "question_id": question_id,
                "hypothesis": hypothesis,
                "chamber_name": chamber_name,
                "search_space": search_space,
                "advancement_metric": "speed",
                "generation": 0
            }

            # Generate 8 candidate param sets from search space
            candidates = []
            for i in range(8):
                candidate = {"name": f"{chamber_name}_tournament_{i}"}

                # Sample parameters from search space
                for param_name, param_values in search_space.items():
                    if isinstance(param_values, list) and param_values:
                        # Randomly sample from allowed values
                        candidate[param_name] = random.choice(param_values)

                candidates.append(candidate)

            if not candidates:
                logger.error(f"[tournament_consumer] No candidates generated for {chamber_name}")
                return

            logger.info(f"[tournament_consumer] Generated {len(candidates)} candidates from search space")
            logger.info(f"[tournament_consumer] Example candidate params: {list(candidates[0].keys())}")

            # Wrap chamber evaluator for batch evaluation
            from dream.evaluators.chamber_batch_evaluator import ChamberBatchEvaluator
            evaluator = ChamberBatchEvaluator(evaluator_class, init_kwargs)

            # Run tournament
            start_time = time.time()
            fitnesses, artifacts = evaluator.evaluate_batch(candidates, context)
            duration = time.time() - start_time

            # Extract champion from artifacts (format depends on evaluator type)
            if "chamber_evaluation" in artifacts:
                champion = artifacts["chamber_evaluation"].get("champion", "unknown")
            elif "bracket_tournament" in artifacts:
                champion = artifacts["bracket_tournament"].get("champion", "unknown")
            else:
                champion = "unknown"

            logger.info(
                f"[tournament_consumer] Tournament complete for {question_id}: "
                f"champion={champion}, duration={duration:.1f}s, "
                f"fitnesses={[f'{f:.3f}' for f in fitnesses]}"
            )

            # Extract champion params and write winner file BEFORE any cleanup
            self._emit_winner(
                question_id=question_id,
                champion_id=champion,
                candidates=candidates,
                fitnesses=fitnesses,
                artifacts=artifacts,
                context=context
            )

            # Track convergence with champion fitness
            max_fitness = max(fitnesses) if fitnesses else 0.0
            self._has_converged(question_id, max_fitness)

            # Update last tournament time
            _last_tournament_time = time.time()
            self.tournament_count += 1

        except Exception as e:
            logger.error(f"[tournament_consumer] Tournament failed for {question_id}: {e}", exc_info=True)
            self._record_failure()

    def _run_tournament(self, question_data: Dict[str, Any]):
        """Run tournament for a curiosity question (handles locking and queuing)."""
        question_id = question_data.get("question_id", "unknown")

        # Try to acquire lock
        if not _tournament_lock.acquire(blocking=False):
            # Tournament already running - enqueue this request
            with _queue_lock:
                if not any(q.get("question_id") == question_id for q in _tournament_queue):
                    _tournament_queue.append(question_data)
                    logger.info(f"[tournament_consumer] Tournament busy, queued {question_id} (queue size: {len(_tournament_queue)})")
            return

        try:
            # Check if we can run
            can_run, reason = self._can_run_tournament()
            if not can_run:
                # Rate limited - enqueue for later
                with _queue_lock:
                    if not any(q.get("question_id") == question_id for q in _tournament_queue):
                        _tournament_queue.append(question_data)
                        logger.info(f"[tournament_consumer] Rate limited, queued {question_id}: {reason}")
                return

            # Execute tournament (lock is held)
            self._execute_tournament(question_data)

        finally:
            _tournament_lock.release()

    def _on_message(self, topic: str, payload: bytes):
        """Handle incoming chemical signal."""
        try:
            msg = json.loads(payload.decode("utf-8"))

            # Extract facts from message
            facts = msg.get("facts", {})
            signal = msg.get("signal", "")
            incident_id = msg.get("incident_id", "")

            if signal == "Q_CURIOSITY_INVESTIGATE":
                logger.info(f"[tournament_consumer] Received {signal} (incident={incident_id})")

                # Run tournament in background thread (non-blocking)
                thread = threading.Thread(
                    target=self._run_tournament,
                    args=(facts,),
                    daemon=True
                )
                thread.start()
            else:
                logger.debug(f"[tournament_consumer] Ignoring signal: {signal}")

        except Exception as e:
            logger.error(f"[tournament_consumer] Failed to process message: {e}", exc_info=True)

    def _queue_worker(self):
        """Background worker that processes queued tournaments."""
        logger.info("[tournament_consumer] Queue worker started")

        while self.running:
            try:
                time.sleep(15)

                with _queue_lock:
                    if not _tournament_queue:
                        continue

                    queue_size = len(_tournament_queue)

                can_run, reason = self._can_run_tournament()
                if not can_run:
                    continue

                if not _tournament_lock.acquire(blocking=False):
                    continue

                try:
                    question_data = None
                    with _queue_lock:
                        if _tournament_queue:
                            question_data = _tournament_queue.popleft()
                            logger.info(
                                f"[tournament_consumer] Processing queued tournament "
                                f"(queue: {len(_tournament_queue)} remaining)"
                            )

                    if question_data:
                        # Execute tournament directly (lock already held)
                        self._execute_tournament(question_data)

                finally:
                    _tournament_lock.release()

            except Exception as e:
                logger.error(f"[tournament_consumer] Queue worker error: {e}", exc_info=True)

        logger.info("[tournament_consumer] Queue worker stopped")

    def run(self):
        """Start the consumer daemon."""
        self.running = True

        logger.info("[tournament_consumer] Starting tournament consumer daemon")
        logger.info(f"[tournament_consumer] Rate limit: {MIN_TOURNAMENT_INTERVAL_SEC}s between tournaments")
        logger.info(f"[tournament_consumer] Subscribing to Q_CURIOSITY_INVESTIGATE signals")

        try:
            # Start queue worker thread
            self.queue_worker_thread = threading.Thread(
                target=self._queue_worker,
                daemon=True,
                name="tournament-queue-worker"
            )
            self.queue_worker_thread.start()
            logger.info("[tournament_consumer] Queue worker thread started")

            # Create ZMQ subscriber for Q_CURIOSITY_INVESTIGATE
            self.subscriber = _ZmqSub(
                topic="Q_CURIOSITY_INVESTIGATE",
                on_message=self._on_message
            )

            logger.info("[tournament_consumer] Consumer daemon running, waiting for signals...")

            # Keep daemon alive
            while self.running:
                # Check maintenance mode before continuing
                wait_for_normal_mode()
                time.sleep(1)

        except KeyboardInterrupt:
            logger.info("[tournament_consumer] Received shutdown signal")
        except Exception as e:
            logger.error(f"[tournament_consumer] Fatal error: {e}", exc_info=True)
        finally:
            if self.subscriber:
                self.subscriber.close()
            logger.info(f"[tournament_consumer] Daemon stopped (ran {self.tournament_count} tournaments)")

    def stop(self):
        """Stop the consumer daemon."""
        self.running = False


def main():
    """Entry point for tournament consumer daemon."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    )

    consumer = TournamentConsumer()

    try:
        consumer.run()
    except KeyboardInterrupt:
        consumer.stop()


if __name__ == "__main__":
    main()
