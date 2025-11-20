#!/usr/bin/env python3
"""
Investigation Consumer Daemon - Curiosity's investigative engine.

Purpose:
    Subscribes to Q_CURIOSITY_INVESTIGATE chemical signals and performs
    deep code analysis to answer questions like "What does this module do?"

    This is curiosity INVESTIGATING, not experimenting. The autism-spectrum
    engineer that obsessively reads every file and figures it out.

Architecture:
    1. Subscribe to Q_CURIOSITY_INVESTIGATE chemical signals
    2. For undiscovered modules: Use ModuleInvestigator for deep LLM analysis
    3. For other questions: Route to appropriate investigation method
    4. Write results to curiosity_investigations.jsonl
    5. Allow capability_integrator to consume results and update registry

Key Difference from Tournament Consumer:
    - Investigation Consumer: Analyzes code to understand what it does
    - Tournament Consumer: Runs experiments to optimize parameters

    Both can subscribe to same signal, but do different things based on question type.
"""

import json
import time
import logging
import threading
import sys
from pathlib import Path
from typing import Dict, Any

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from kloros.orchestration.chem_bus_v2 import _ZmqSub, ChemPub, ChemSub
from kloros.orchestration.maintenance_mode import wait_for_normal_mode
from registry.module_investigator import get_module_investigator
from registry.systemd_investigator import get_systemd_investigator
from registry.semantic_evidence import SemanticEvidenceStore
from kloros.orchestration.generic_investigation_handler import GenericInvestigationHandler
from config.models_config import get_ollama_url, select_best_model_for_task

logger = logging.getLogger(__name__)

INVESTIGATIONS_LOG = Path("/home/kloros/.kloros/curiosity_investigations.jsonl")
PROCESSED_QUESTIONS = Path("/home/kloros/.kloros/processed_questions.jsonl")


class InvestigationConsumer:
    """
    Curiosity's code investigator - deeply analyzes modules to understand capabilities.
    """

    def __init__(self):
        self.running = False
        self.subscriber = None
        self.investigation_count = 0
        self.chem_pub = ChemPub()

        try:
            self.semantic_store = SemanticEvidenceStore()
        except Exception as e:
            logger.warning(f"[investigation_consumer] Failed to initialize SemanticEvidenceStore: {e}, failure tracking disabled")
            self.semantic_store = None

        # Use automatic failover: remote gaming rig if available, else local
        ollama_url = get_ollama_url()

        # Select best available model for code analysis by querying API
        model = select_best_model_for_task('code', ollama_url)

        logger.info(f"[investigation_consumer] Selected model {model} for code investigations at {ollama_url}")

        self.investigator = get_module_investigator(ollama_host=ollama_url, model=model)
        self.systemd_investigator = get_systemd_investigator(ollama_host=ollama_url, model=model)
        self.generic_handler = GenericInvestigationHandler(ollama_host=ollama_url, model=model)
        # Dynamic concurrent investigation limiting (self-regulates under pressure)
        self.max_concurrent_investigations = 4  # Normal: 4 concurrent
        self.current_concurrent_investigations = 0
        self.concurrent_lock = threading.Lock()
        # Emergency bypass: track high-priority investigations (bypass concurrency limit)
        self.emergency_investigations = 0
        self.emergency_lock = threading.Lock()
        self.last_investigation_time = 0
        self.min_delay_between_investigations = 0.5  # Minimal throttle to prevent thread explosion
        # Investigation timeouts:
        # - Normal: 10 minutes (32B models are thorough, may use RAM offloading)
        # - Emergency: 2 minutes (operational errors need faster response)
        self.normal_investigation_timeout = 600  # 10 minutes
        self.emergency_investigation_timeout = 300  # 5 minutes

        self.metrics_window_start = time.time()
        self.metrics_investigations_completed = 0
        self.metrics_investigations_failed = 0
        self.metrics_lock = threading.Lock()

        self._metrics_thread = threading.Thread(
            target=self._emit_metrics_summary,
            daemon=True
        )
        self._metrics_thread.start()

        # Self-regulation: respond to affective signals
        self.base_delay = 0.5  # Baseline throttle
        self.max_delay = 5.0   # Maximum throttle under pressure
        self.pressure_level = 0  # 0=normal, 1=elevated, 2=critical
        self.pressure_lock = threading.Lock()
        self.last_pressure_signal = 0

        # Queue depth limiting: prevent runaway queue growth
        self.max_queue_depth = 100  # Reject investigations when queue exceeds this
        self.queue_rejection_count = 0

        # Subscribe to AFFECT_MEMORY_PRESSURE for self-regulation
        self.affective_sub = ChemSub(
            topic="AFFECT_MEMORY_PRESSURE",
            on_json=self._on_memory_pressure_signal,
            zooid_name="investigation_consumer_affective",
            niche="consciousness"
        )
        logger.info("[investigation_consumer] ✅ Subscribed to AFFECT_MEMORY_PRESSURE for self-regulation")

    def _on_memory_pressure_signal(self, msg: Dict[str, Any]):
        """
        Handle AFFECT_MEMORY_PRESSURE signal by reducing concurrency and increasing throttle.

        Self-regulation: when under memory/resource pressure, drastically reduce
        concurrent investigations and slow down start rate to allow system to recover.
        """
        facts = msg.get('facts', msg)
        severity = facts.get('severity', 'high')
        thread_count = facts.get('thread_count', 0)
        swap_mb = facts.get('swap_used_mb', 0)

        with self.pressure_lock:
            current_time = time.time()

            # Update pressure level based on severity
            if severity == 'critical':
                self.pressure_level = 2
                self.min_delay_between_investigations = self.max_delay
                self.max_concurrent_investigations = 1  # CRITICAL: Only 1 at a time
                logger.warning(f"[investigation_consumer] 🚨 CRITICAL pressure detected "
                             f"(threads={thread_count}, swap={swap_mb:.0f}MB) - "
                             f"throttling to {self.max_delay}s delay, max 1 concurrent")
            else:  # high
                self.pressure_level = 1
                self.min_delay_between_investigations = (self.base_delay + self.max_delay) / 2
                self.max_concurrent_investigations = 2  # ELEVATED: Max 2 concurrent
                logger.info(f"[investigation_consumer] ⚠️  Elevated pressure detected "
                           f"(threads={thread_count}, swap={swap_mb:.0f}MB) - "
                           f"throttling to {self.min_delay_between_investigations:.1f}s delay, max 2 concurrent")

            self.last_pressure_signal = current_time

    def _check_pressure_recovery(self):
        """
        Periodically check if pressure has subsided and restore normal operation.

        Call this during investigation loop to gradually recover from pressure.
        """
        with self.pressure_lock:
            current_time = time.time()
            time_since_pressure = current_time - self.last_pressure_signal

            # If no pressure signal for 60 seconds, gradually reduce throttle
            if time_since_pressure > 60 and self.pressure_level > 0:
                self.pressure_level -= 1

                if self.pressure_level == 0:
                    self.min_delay_between_investigations = self.base_delay
                    self.max_concurrent_investigations = 4
                    logger.info(f"[investigation_consumer] ✅ Pressure recovered - "
                              f"baseline: {self.base_delay}s delay, max 4 concurrent")
                elif self.pressure_level == 1:
                    self.min_delay_between_investigations = (self.base_delay + self.max_delay) / 2
                    self.max_concurrent_investigations = 2
                    logger.info(f"[investigation_consumer] 📉 Pressure decreasing - "
                              f"{self.min_delay_between_investigations:.1f}s delay, max 2 concurrent")

                # Reset timer for next check
                self.last_pressure_signal = current_time

    def _is_investigation_failure(self, question_data: Dict[str, Any], result: Dict[str, Any]) -> bool:
        """
        Detect if an investigation has failed based on the definition of failure.

        An investigation fails if ANY of:
        1. Status is not "completed" (indicates explicit failure)
        2. Result contains "unsolvable" tag
        3. No evidence was gathered (empty evidence list)
        4. Evidence hash matches previous attempt (no new information)

        Args:
            question_data: Original question with metadata
            result: Investigation result dict

        Returns:
            True if investigation is considered a failure, False otherwise
        """
        status = result.get("status")
        if status != "completed":
            return True

        tags = result.get("tags", [])
        if "unsolvable" in tags:
            return True

        evidence = result.get("evidence", [])
        if not evidence or len(evidence) == 0:
            return True

        evidence_hash = result.get("evidence_hash")
        previous_hash = question_data.get("previous_evidence_hash")
        if evidence_hash and previous_hash and evidence_hash == previous_hash:
            return True

        return False

    def _get_failure_reason(self, result: Dict[str, Any]) -> str:
        """
        Extract a human-readable reason for investigation failure.

        Args:
            result: Investigation result dict

        Returns:
            String description of failure reason
        """
        status = result.get("status")
        if status != "completed":
            return f"Investigation failed with status: {status}"

        tags = result.get("tags", [])
        if "unsolvable" in tags:
            return "Investigation marked as unsolvable"

        evidence_hash = result.get("evidence_hash")
        previous_hash = result.get("previous_evidence_hash")
        if evidence_hash and previous_hash and evidence_hash == previous_hash:
            return f"Investigation produced duplicate evidence (hash: {evidence_hash})"

        evidence = result.get("evidence", [])
        if not evidence or len(evidence) == 0:
            return "Investigation produced no evidence"

        return "Investigation failed: unknown reason"

    def _record_investigation_failure(self, question_data: Dict[str, Any], result: Dict[str, Any]) -> None:
        """
        Record a failure in the semantic evidence store.

        Only records if semantic store is available and capability_key exists.
        Catches and logs exceptions to prevent failure tracking from breaking consumer.

        Args:
            question_data: Original question with metadata
            result: Investigation result dict
        """
        if not self.semantic_store:
            return

        capability_key = question_data.get("capability_key")
        if not capability_key:
            logger.warning(f"[investigation_consumer] No capability_key in question_data, skipping failure tracking")
            return

        try:
            reason = self._get_failure_reason(result)
            self.semantic_store.record_failure(capability_key, reason=reason)
            logger.debug(f"[investigation_consumer] Recorded failure for {capability_key}: {reason}")
        except Exception as e:
            logger.error(f"[investigation_consumer] Failed to record failure: {e}")

    def _is_meta_question(self, question_id: str) -> bool:
        """
        Detect meta-questions that would cause infinite recursion.

        Meta-questions are questions about the curiosity/investigation system itself.
        Investigating these creates loops where we investigate why we're investigating.

        Examples of meta-questions to skip:
        - pattern.archive.* → Questions about why questions are being archived
        - meta.* → Explicitly meta questions
        - investigation.* → Questions about the investigation process itself
        - curiosity.processor.* → Questions about curiosity processor internals

        Args:
            question_id: The question identifier

        Returns:
            True if this is a meta-question that should be skipped
        """
        meta_prefixes = [
            "pattern.archive.",  # Archive system meta-questions
            "meta.",             # Explicitly meta questions
            "investigation.",    # Investigation system questions
            "curiosity.processor.",  # Curiosity processor internals
            "archive.system.",   # Archive system questions
        ]

        for prefix in meta_prefixes:
            if question_id.startswith(prefix):
                return True

        return False

    def _get_host_indicator(self) -> str:
        """Get current Ollama host indicator for logging."""
        ollama_url = get_ollama_url()
        if '100.67.244.66' in ollama_url:
            return "[on AltimitOS@100.67.244.66]"
        else:
            return "[on local]"

    def _get_queue_depth(self) -> int:
        """Get current queue depth by counting pending question files."""
        try:
            questions_dir = Path("/home/kloros/.kloros/curiosity_questions")
            if not questions_dir.exists():
                return 0
            return len(list(questions_dir.glob("*.json")))
        except Exception as e:
            logger.warning(f"[investigation_consumer] Failed to get queue depth: {e}")
            return 0

    def _emit_metrics_summary(self):
        """Emit METRICS_SUMMARY every 5 minutes."""
        while True:
            time.sleep(300)

            try:
                queue_depth = self._get_queue_depth()

                with self.metrics_lock:
                    completed = self.metrics_investigations_completed
                    failed = self.metrics_investigations_failed
                    self.metrics_investigations_completed = 0
                    self.metrics_investigations_failed = 0

                self.chem_pub.emit(
                    signal="METRICS_SUMMARY",
                    ecosystem="introspection",
                    facts={
                        "daemon": "investigation_consumer",
                        "window_duration_s": 300,
                        "investigations_completed": completed,
                        "investigations_failed": failed,
                        "queue_depth_current": queue_depth
                    }
                )

                if queue_depth > 50:
                    self.chem_pub.emit(
                        signal="BOTTLENECK_DETECTED",
                        ecosystem="introspection",
                        intensity=2.0,
                        facts={
                            "daemon": "investigation_consumer",
                            "issue": "queue_buildup",
                            "queue_depth": queue_depth,
                            "threshold": 50
                        }
                    )

            except Exception as e:
                logger.error(f"[investigation_consumer] Metrics summary emission failed: {e}")

    def _on_message(self, topic: str, payload: bytes):
        """Handle incoming chemical signal."""
        try:
            msg = json.loads(payload.decode("utf-8"))

            facts = msg.get("facts", {})
            signal = msg.get("signal", "")
            incident_id = msg.get("incident_id", "")

            if signal == "Q_CURIOSITY_INVESTIGATE":
                # META-LOOP PREVENTION: Skip questions about the investigation/archive system itself
                # These create infinite recursion where we investigate why we're investigating
                question_id = facts.get("question_id", "unknown")
                if self._is_meta_question(question_id):
                    logger.info(f"[investigation_consumer] Skipping meta-question (prevents infinite recursion): {question_id}")
                    self._mark_question_processed(question_id, intent_sha="meta_skipped", evidence=facts.get("evidence"))
                    return

                # QUEUE DEPTH LIMITING: Reject investigations when queue is too deep
                # Prevents runaway queue growth from exhausting memory/disk
                current_queue_depth = self._get_queue_depth()
                if current_queue_depth >= self.max_queue_depth:
                    self.queue_rejection_count += 1
                    logger.warning(
                        f"[investigation_consumer] 🚫 Queue depth ({current_queue_depth}) "
                        f"exceeds limit ({self.max_queue_depth}), REJECTING investigation: {question_id} "
                        f"(total rejections: {self.queue_rejection_count})"
                    )

                    # Emit back-pressure signal to alert curiosity processors
                    self.chem_pub.emit(
                        signal="INVESTIGATION_QUEUE_FULL",
                        ecosystem="consciousness",
                        intensity=2.0,
                        facts={
                            "queue_depth": current_queue_depth,
                            "limit": self.max_queue_depth,
                            "rejected_question_id": question_id,
                            "total_rejections": self.queue_rejection_count
                        }
                    )

                    # Mark as processed to prevent re-queuing
                    self._mark_question_processed(question_id, intent_sha="queue_full", evidence=facts.get("evidence"))
                    return

                logger.info(f"[investigation_consumer] Received {signal} (incident={incident_id})")

                # Check priority (critical/high errors bypass limits)
                priority_str = facts.get("priority", "normal")
                is_emergency = priority_str in ["critical", "high"]

                if is_emergency:
                    logger.warning(f"[investigation_consumer] EMERGENCY investigation: {facts.get('question_id', 'unknown')} (priority={priority_str})")
                    # Run immediately, bypass rate limiting and semaphore
                    thread = threading.Thread(
                        target=self._run_emergency_investigation,
                        args=(facts,),
                        daemon=True
                    )
                    thread.start()
                else:
                    # Normal priority: rate limit and semaphore apply
                    # Check if pressure has subsided and adjust throttle
                    self._check_pressure_recovery()

                    # Rate limit: ensure minimum delay between investigations
                    current_time = time.time()
                    time_since_last = current_time - self.last_investigation_time
                    if time_since_last < self.min_delay_between_investigations:
                        delay = self.min_delay_between_investigations - time_since_last
                        logger.info(f"[investigation_consumer] Rate limiting: waiting {delay:.1f}s before next investigation")
                        time.sleep(delay)

                    self.last_investigation_time = time.time()

                    # Run investigation in background thread with concurrency limit
                    thread = threading.Thread(
                        target=self._run_investigation_with_semaphore,
                        args=(facts,),
                        daemon=True
                    )
                    thread.start()
            else:
                logger.debug(f"[investigation_consumer] Ignoring signal: {signal}")

        except Exception as e:
            logger.error(f"[investigation_consumer] Failed to process message: {e}", exc_info=True)

    def _on_throttle_message(self, topic: str, payload: bytes):
        """
        Handle INVESTIGATION_THROTTLE_REQUEST signal from cognitive actions.

        Reduces investigation concurrency in response to memory pressure.

        Args:
            topic: Signal topic
            payload: Raw JSON bytes
        """
        try:
            msg = json.loads(payload.decode('utf-8'))
            facts = msg.get('facts', {})
            requested_concurrency = facts.get('requested_concurrency', 1)
            reason = facts.get('reason', 'Unknown')
            thread_count = facts.get('thread_count', 0)
            swap_used_mb = facts.get('swap_used_mb', 0)
            memory_used_pct = facts.get('memory_used_pct', 0)

            with self.concurrent_lock:
                old_limit = self.max_concurrent_investigations
                self.max_concurrent_investigations = requested_concurrency

            logger.warning(
                f"[investigation_consumer] 🔻 THROTTLE REQUEST: {old_limit} → {requested_concurrency} "
                f"(threads={thread_count}, swap={swap_used_mb}MB, mem={memory_used_pct}%) "
                f"Reason: {reason}"
            )

        except Exception as e:
            logger.error(f"[investigation_consumer] Failed to process throttle request: {e}", exc_info=True)

    def _run_emergency_investigation(self, question_data: Dict[str, Any]):
        """Emergency investigation - bypass semaphore and rate limiting."""
        with self.emergency_lock:
            self.emergency_investigations += 1

        try:
            question_id = question_data.get("question_id", "unknown")
            host = self._get_host_indicator()
            logger.warning(f"[investigation_consumer] {host} EMERGENCY slot (active emergencies: {self.emergency_investigations}) - {question_id}")
            self._run_investigation_with_timeout(question_data, timeout=self.emergency_investigation_timeout)
        finally:
            with self.emergency_lock:
                self.emergency_investigations -= 1

    def _run_investigation_with_semaphore(self, question_data: Dict[str, Any]):
        """Wrapper to enforce dynamic concurrency limit (self-regulates under pressure)."""
        # Wait until we're below the concurrent investigation limit
        while True:
            with self.concurrent_lock:
                if self.current_concurrent_investigations < self.max_concurrent_investigations:
                    self.current_concurrent_investigations += 1
                    max_allowed = self.max_concurrent_investigations
                    active_count = self.current_concurrent_investigations
                    break
            # If at limit, wait a bit before checking again
            time.sleep(0.5)

        try:
            logger.info(f"[investigation_consumer] Started investigation (active: {active_count}/{max_allowed})")
            self._run_investigation_with_timeout(question_data, timeout=self.normal_investigation_timeout)
        finally:
            with self.concurrent_lock:
                self.current_concurrent_investigations -= 1
                logger.info(f"[investigation_consumer] Completed investigation (active: {self.current_concurrent_investigations}/{self.max_concurrent_investigations})")

    def _run_investigation_with_timeout(self, question_data: Dict[str, Any], timeout: int):
        """Run investigation with timeout protection."""
        question_id = question_data.get("question_id", "unknown")
        result = {"status": "timeout", "question_id": question_id}

        def target(result_container):
            try:
                self._run_investigation(question_data)
                result_container["status"] = "completed"
            except Exception as e:
                result_container["status"] = "failed"
                result_container["error"] = str(e)

        thread = threading.Thread(target=target, args=(result,), daemon=True)
        thread.start()
        thread.join(timeout=timeout)

        if thread.is_alive():
            logger.error(f"[investigation_consumer] Investigation TIMEOUT after {timeout}s: {question_id}")
            # Log the timeout as a failed investigation
            self._log_investigation({
                "timestamp": time.time(),
                "question_id": question_id,
                "question": question_data.get("question", ""),
                "status": "failed",
                "failure_reason": f"Investigation exceeded {timeout}s timeout",
                "timeout": True
            })

            with self.metrics_lock:
                self.metrics_investigations_failed += 1

            # Decompose timed-out question into smaller, more focused questions
            self._decompose_timed_out_question(question_data)
        elif result.get("status") == "failed":
            logger.error(f"[investigation_consumer] Investigation FAILED: {question_id} - {result.get('error', 'unknown')}")

    def _is_investigation_still_relevant(self, question_data: Dict[str, Any]) -> bool:
        """
        Sanity check before starting investigation:
        - Is this issue still relevant?
        - Is there something better to investigate?
        - Does the effort meet the benefit?
        """
        question_id = question_data.get("question_id", "")

        try:
            # For pattern.archive.* questions: check if archive is still actively growing
            if question_id.startswith("pattern.archive."):
                archive_category = question_id.replace("pattern.archive.", "")
                archive_file = Path(f"/home/kloros/.kloros/archives/{archive_category}.jsonl")

                if not archive_file.exists():
                    logger.info(f"[investigation_consumer] Archive {archive_category} no longer exists, skipping")
                    return False

                # Check if archive has been modified in last 5 minutes
                mtime = archive_file.stat().st_mtime
                age_minutes = (time.time() - mtime) / 60

                if age_minutes > 5:
                    logger.info(f"[investigation_consumer] Archive {archive_category} hasn't changed in {age_minutes:.1f} minutes, issue likely resolved")
                    return False

                # Check archive size - if it's small, maybe not worth investigating
                with open(archive_file, 'r') as f:
                    count = sum(1 for line in f if line.strip())

                if count < 3:
                    logger.info(f"[investigation_consumer] Archive {archive_category} only has {count} entries, not significant enough")
                    return False

            return True

        except Exception as e:
            logger.warning(f"[investigation_consumer] Relevance check failed for {question_id}: {e}")
            return True

    def _decompose_timed_out_question(self, question_data: Dict[str, Any]):
        """
        Decompose a timed-out question into smaller, more focused sub-questions.

        Timeout indicates too much context. Break down into narrower questions
        that can be investigated within the time limit.
        """
        question_id = question_data.get("question_id", "")
        question_text = question_data.get("question", "")

        logger.warning(f"[investigation_consumer] Decomposing timed-out question: {question_id}")

        try:
            from registry.curiosity_core import CuriosityQuestion, ActionClass, QuestionStatus

            sub_questions = []

            if question_id.startswith("pattern.archive."):
                archive_category = question_id.replace("pattern.archive.", "")
                archive_file = Path(f"/home/kloros/.kloros/archives/{archive_category}.jsonl")

                if archive_file.exists():
                    sub_questions.extend([
                        CuriosityQuestion(
                            id=f"decomposed.{question_id}.unique_keys",
                            hypothesis=f"DECOMPOSED_TIMEOUT_{archive_category.upper()}",
                            question=f"What are the unique capability_keys in {archive_category} archive?",
                            evidence=[
                                f"parent_question:{question_id}",
                                f"decomposition_reason:timeout",
                                f"archive_file:{archive_file}"
                            ],
                            action_class=ActionClass.INVESTIGATE,
                            autonomy=1,
                            value_estimate=0.4,
                            cost=0.2,
                            status=QuestionStatus.READY,
                            capability_key=f"curiosity.decomposed.{archive_category}"
                        ),
                        CuriosityQuestion(
                            id=f"decomposed.{question_id}.temporal",
                            hypothesis=f"DECOMPOSED_TIMEOUT_{archive_category.upper()}",
                            question=f"When did {archive_category} archiving activity begin?",
                            evidence=[
                                f"parent_question:{question_id}",
                                f"decomposition_reason:timeout",
                                f"archive_file:{archive_file}"
                            ],
                            action_class=ActionClass.INVESTIGATE,
                            autonomy=1,
                            value_estimate=0.3,
                            cost=0.1,
                            status=QuestionStatus.READY,
                            capability_key=f"curiosity.decomposed.{archive_category}"
                        )
                    ])

            if sub_questions:
                for sq in sub_questions:
                    self.chem_pub.emit("Q_CURIOSITY_LOW",
                                      ecosystem='introspection',
                                      facts=sq.to_dict())
                logger.info(f"[investigation_consumer] Emitted {len(sub_questions)} decomposed sub-questions for {question_id}")
            else:
                logger.warning(f"[investigation_consumer] No decomposition strategy for question type: {question_id}")

        except Exception as e:
            logger.error(f"[investigation_consumer] Failed to decompose question: {e}", exc_info=True)

    def _run_investigation(self, question_data: Dict[str, Any]):
        """
        Run investigation for a curiosity question.

        Determines question type and routes to appropriate investigation method.
        """
        question_id = question_data.get("question_id", "unknown")
        question_text = question_data.get("question", "")
        hypothesis = question_data.get("hypothesis", "")

        # Sanity check: Is this investigation still relevant and worth the effort?
        if not self._is_investigation_still_relevant(question_data):
            logger.info(f"[investigation_consumer] SKIPPED (no longer relevant): {question_id}")
            return

        investigation_start_time = time.time()
        question_created_time = question_data.get("created_at", investigation_start_time)
        queue_wait_time_ms = int((investigation_start_time - question_created_time) * 1000)

        try:
            host = self._get_host_indicator()
            logger.info(f"[investigation_consumer] {host} Investigating: {question_id}")

            # Route based on question type
            if question_id.startswith("discover.module.") or question_id.startswith("reinvestigate."):
                # Module discovery/reinvestigation - use deep code analysis
                investigation = self._investigate_module(question_data)

            elif question_id.startswith("systemd_audit_"):
                # Systemd service audit - use specialized service investigator
                investigation = self._investigate_systemd_service(question_data)

            else:
                # Generic investigation - adaptive handler for any question type
                logger.info(f"[investigation_consumer] Using generic investigation handler for: {question_id}")
                initial_evidence = question_data.get("evidence", [])
                investigation = self.generic_handler.investigate(
                    question=question_text,
                    question_id=question_id,
                    initial_evidence=initial_evidence
                )

                # Enrich with question context (preserve gathered evidence!)
                investigation.update({
                    "hypothesis": hypothesis,
                    "initial_evidence": initial_evidence,
                    "investigation_method": "generic_adaptive",
                    "status": "completed" if investigation.get("success") else "failed"
                })

            investigation_duration_ms = int((time.time() - investigation_start_time) * 1000)

            # Write investigation to log
            self._log_investigation(investigation)

            # Update metrics counters
            with self.metrics_lock:
                if investigation.get("status") == "completed":
                    self.metrics_investigations_completed += 1
                else:
                    self.metrics_investigations_failed += 1

            # Track failures for learning (before marking as processed)
            if self._is_investigation_failure(question_data, investigation):
                self._record_investigation_failure(question_data, investigation)

            # Emit Q_INVESTIGATION_COMPLETE signal with performance metrics
            try:
                model_used = investigation.get("model_used", "unknown")
                tokens_used = investigation.get("tokens_used", 0)

                # Validation warning: check for missing metrics
                if model_used == "unknown" or tokens_used == 0:
                    logger.warning(f"[investigation_consumer] Investigation {question_id} has incomplete metrics: model_used={model_used}, tokens_used={tokens_used}")

                self.chem_pub.emit(
                    signal="Q_INVESTIGATION_COMPLETE",
                    ecosystem="introspection",
                    intensity=1.0,
                    facts={
                        "investigation_timestamp": investigation.get("timestamp"),
                        "module_name": investigation.get("module_name"),
                        "question_id": question_id,
                        "status": investigation.get("status"),
                        "duration_ms": investigation_duration_ms,
                        "model_used": model_used,
                        "tokens_used": tokens_used,
                        "queue_wait_time_ms": queue_wait_time_ms
                    }
                )
                logger.debug(f"[investigation_consumer] Emitted Q_INVESTIGATION_COMPLETE for {question_id}")
            except Exception as e:
                logger.warning(f"[investigation_consumer] Failed to emit signal: {e}")

            # Mark question as processed (only after successful investigation)
            if investigation.get("status") == "completed":
                evidence = question_data.get("evidence", [])
                self._mark_question_processed(question_id, evidence=evidence)

            self.investigation_count += 1

            logger.info(f"[investigation_consumer] {host} ✓ Investigation complete for {question_id}")

        except Exception as e:
            logger.error(f"[investigation_consumer] Investigation failed for {question_id}: {e}", exc_info=True)

            with self.metrics_lock:
                self.metrics_investigations_failed += 1

    def _investigate_module(self, question_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Investigate an undiscovered module using deep LLM analysis.

        This is the key method - uses ModuleInvestigator to read all code
        and understand what the module does.

        Args:
            question_data: Question facts including module path and name

        Returns:
            Investigation results dict
        """
        question_id = question_data.get("question_id", "unknown")
        question_text = question_data.get("question", "")
        hypothesis = question_data.get("hypothesis", "")
        evidence = question_data.get("evidence", [])

        # Extract module path and name from evidence OR directly from facts
        module_path = question_data.get("module_path")
        module_name = question_data.get("module_name")

        # If not in facts, check evidence list
        if not module_path:
            for ev in evidence:
                if isinstance(ev, str) and ev.startswith("path:"):
                    module_path = ev.split(":", 1)[1]
                    module_name = module_path.split("/")[-1]
                    break

        if not module_path or not module_name:
            logger.error(f"[investigation_consumer] Could not extract module path from question_data: {question_data}")
            return {
                "timestamp": time.time(),
                "question_id": question_id,
                "question": question_text,
                "hypothesis": hypothesis,
                "status": "failed",
                "error": "Could not extract module path from question_data"
            }

        host = self._get_host_indicator()
        logger.info(f"[investigation_consumer] {host} Investigating module: {module_name} at {module_path}")

        # Extract custom instructions if provided by meta-agent
        custom_instructions = question_data.get('custom_instructions', None)
        if custom_instructions:
            logger.info(f"[investigation_consumer] Using custom instructions from meta-agent")

        # Use ModuleInvestigator for deep analysis
        investigation_result = self.investigator.investigate_module(
            module_path=module_path,
            module_name=module_name,
            question=question_text,
            custom_instructions=custom_instructions
        )

        # Enrich with question context
        investigation_result.update({
            "question_id": question_id,
            "question": question_text,
            "hypothesis": hypothesis,
            "evidence": evidence,
            "investigation_method": "llm_deep_analysis",
            "status": "completed" if investigation_result.get("success") else "failed"
        })

        return investigation_result

    def _investigate_systemd_service(self, question_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Investigate a systemd service using specialized service investigator.

        Extracts service name from question_id and analyzes unit file.

        Args:
            question_data: Question facts including question_id

        Returns:
            Investigation results dict
        """
        question_id = question_data.get("question_id", "unknown")
        question_text = question_data.get("question", "")
        hypothesis = question_data.get("hypothesis", "")
        evidence = question_data.get("evidence", [])

        try:
            service_name, unit_type = self._parse_systemd_question_id(question_id)

            if not service_name:
                logger.error(f"[investigation_consumer] Could not extract service name from question_id: {question_id}")
                return {
                    "timestamp": time.time(),
                    "question_id": question_id,
                    "question": question_text,
                    "hypothesis": hypothesis,
                    "status": "failed",
                    "error": "Could not extract service name from question_id"
                }

            host = self._get_host_indicator()
            logger.info(f"[investigation_consumer] {host} Investigating systemd service: {service_name}.{unit_type}")

            investigation_result = self.systemd_investigator.investigate_service(
                service_name=service_name,
                unit_type=unit_type
            )

            investigation_result.update({
                "question_id": question_id,
                "question": question_text,
                "hypothesis": hypothesis,
                "evidence": evidence,
                "investigation_method": "systemd_service_analysis",
                "status": "completed" if investigation_result.get("success") else "failed"
            })

            return investigation_result

        except Exception as e:
            logger.error(f"[investigation_consumer] Systemd investigation failed for {question_id}: {e}", exc_info=True)
            return {
                "timestamp": time.time(),
                "question_id": question_id,
                "question": question_text,
                "hypothesis": hypothesis,
                "status": "failed",
                "error": str(e)
            }

    def _parse_systemd_question_id(self, question_id: str) -> tuple[str, str]:
        """
        Parse systemd_audit question ID to extract service name and unit type.

        Format: systemd_audit_{service_name}_{unit_type}_{timestamp}
        Example: systemd_audit_nginx_service_1731700123

        Args:
            question_id: The question ID to parse

        Returns:
            Tuple of (service_name, unit_type) or ("", "") if parsing fails
        """
        if not question_id.startswith("systemd_audit_"):
            return "", ""

        parts = question_id.replace("systemd_audit_", "").split("_")

        if len(parts) < 3:
            logger.warning(f"[investigation_consumer] Invalid systemd_audit question format: {question_id}")
            return "", ""

        unit_type = parts[-2]
        service_name = "_".join(parts[:-2])

        if not service_name or not unit_type:
            return "", ""

        return service_name, unit_type

    def _log_investigation(self, investigation: Dict[str, Any]):
        """
        Write investigation results to curiosity_investigations.jsonl.

        Args:
            investigation: Investigation results dict
        """
        try:
            INVESTIGATIONS_LOG.parent.mkdir(parents=True, exist_ok=True)

            with open(INVESTIGATIONS_LOG, "a") as f:
                f.write(json.dumps(investigation) + "\n")

            logger.info(f"[investigation_consumer] Investigation logged to {INVESTIGATIONS_LOG}")

        except Exception as e:
            logger.error(f"[investigation_consumer] Failed to log investigation: {e}", exc_info=True)

    def _evidence_hash(self, evidence):
        """Compute hash of evidence for context-aware re-investigation."""
        import hashlib
        evidence_strings = [str(item) for item in evidence]
        evidence_str = "|".join(sorted(evidence_strings))
        return hashlib.sha256(evidence_str.encode()).hexdigest()[:16]

    def _mark_question_processed(self, question_id: str, intent_sha: str = "investigated", evidence=None):
        """
        Mark question as processed in processed_questions.jsonl with evidence hash.

        Args:
            question_id: The question ID that was investigated
            intent_sha: Optional intent hash (defaults to 'investigated')
            evidence: Evidence list for context-aware re-investigation
        """
        try:
            PROCESSED_QUESTIONS.parent.mkdir(parents=True, exist_ok=True)

            entry = {
                "question_id": question_id,
                "processed_at": time.time(),
                "intent_sha": intent_sha
            }

            # Include evidence hash for context-aware re-investigation
            if evidence:
                entry["evidence_hash"] = self._evidence_hash(evidence)

            with open(PROCESSED_QUESTIONS, "a") as f:
                f.write(json.dumps(entry) + "\n")

            logger.info(f"[investigation_consumer] Marked {question_id} as processed")

        except Exception as e:
            logger.error(f"[investigation_consumer] Failed to mark question as processed: {e}", exc_info=True)

    def run(self):
        """Start the consumer daemon."""
        self.running = True

        logger.info("[investigation_consumer] Starting investigation consumer daemon")
        logger.info("[investigation_consumer] Subscribing to Q_CURIOSITY_INVESTIGATE signals (autonomous)")
        logger.info("[investigation_consumer] Subscribing to Q_INVESTIGATION_REQUEST signals (meta-agent delegation)")
        logger.info("[investigation_consumer] Using LLM-powered deep code analysis")

        try:
            # Create ZMQ subscribers for both autonomous and delegated investigations
            self.subscriber = _ZmqSub(
                topic="Q_CURIOSITY_INVESTIGATE",
                on_message=self._on_message
            )

            # Also subscribe to meta-agent delegation requests
            self.subscriber_delegated = _ZmqSub(
                topic="Q_INVESTIGATION_REQUEST",
                on_message=self._on_message
            )

            # Subscribe to throttle requests from cognitive actions
            self.subscriber_throttle = _ZmqSub(
                topic="INVESTIGATION_THROTTLE_REQUEST",
                on_message=self._on_throttle_message
            )

            logger.info("[investigation_consumer] Consumer daemon running, waiting for signals...")

            # Keep daemon alive
            while self.running:
                # Check maintenance mode before continuing
                wait_for_normal_mode()
                time.sleep(1)

        except KeyboardInterrupt:
            logger.info("[investigation_consumer] Received shutdown signal")
        except Exception as e:
            logger.error(f"[investigation_consumer] Fatal error: {e}", exc_info=True)
        finally:
            if self.subscriber:
                self.subscriber.close()
            if hasattr(self, 'subscriber_delegated') and self.subscriber_delegated:
                self.subscriber_delegated.close()
            if hasattr(self, 'subscriber_throttle') and self.subscriber_throttle:
                self.subscriber_throttle.close()
            logger.info(f"[investigation_consumer] Daemon stopped (completed {self.investigation_count} investigations)")

    def stop(self):
        """Stop the consumer daemon."""
        self.running = False


def main():
    """Entry point for investigation consumer daemon."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    )

    consumer = InvestigationConsumer()

    try:
        consumer.run()
    except KeyboardInterrupt:
        consumer.stop()


if __name__ == "__main__":
    main()
