#!/usr/bin/env python3
"""
Curiosity Core - Automatic Question Generator from Capability Gaps

Analyzes capability matrix and generates questions to guide self-directed learning.

Governance:
- Tool-Integrity: Self-contained, testable, complete docstrings
- D-REAM-Allowed-Stack: Uses JSON, no unbounded loops
- Autonomy Level 2: Proposes questions, user decides actions

Purpose:
    Transform capability gaps into concrete, actionable questions that drive curiosity

Outcomes:
    - Generates questions from missing/degraded capabilities
    - Estimates value, cost, and autonomy level for each question
    - Provides hypotheses and evidence for each question
    - Enables "what's the minimal substitute?" type reasoning
"""

import json
import logging
import hashlib
import sys
from pathlib import Path
from typing import List, Dict, Any, Optional
from datetime import datetime

try:
    from .semantic_evidence import SemanticEvidenceStore
except ImportError:
    sys.path.insert(0, str(Path(__file__).parent))
    from semantic_evidence import SemanticEvidenceStore

try:
    from .question_prioritizer import QuestionPrioritizer
except ImportError:
    sys.path.insert(0, str(Path(__file__).parent))
    from question_prioritizer import QuestionPrioritizer

try:
    from src.orchestration.core.umn_bus import UMNPub, UMNSub
except ImportError:
    try:
        from src.orchestration.core.umn_bus import UMNPub, UMNSub
    except ImportError:
        UMNPub = None
        UMNSub = None

try:
    from .capability_evaluator import CapabilityMatrix, CapabilityState, CapabilityRecord
except ImportError:
    sys.path.insert(0, str(Path(__file__).parent))
    from capability_evaluator import CapabilityMatrix, CapabilityState, CapabilityRecord

from .monitors import (
    QuestionStatus,
    ActionClass,
    CuriosityQuestion,
    CuriosityFeed,
    PerformanceTrend,
    SystemResourceSnapshot,
    PerformanceMonitor,
    TestResultMonitor,
    SystemResourceMonitor,
    ModuleDiscoveryMonitor,
    ChaosLabMonitor,
    MetricQualityMonitor,
    ExceptionMonitor,
)

logger = logging.getLogger(__name__)

MAX_FOLLOWUP_QUESTIONS_PER_CYCLE = 10


class CuriosityCore:
    """
    Generates curiosity questions from capability matrix analysis.

    Purpose:
        Enable KLoROS to form concrete questions about missing/degraded capabilities

    Outcomes:
        - Analyzes capability matrix for gaps and contradictions
        - Generates questions with hypotheses and evidence
        - Estimates value and cost for each question
        - Writes curiosity_feed.json for consumption by picker/scheduler
    """

    _instance: Optional['CuriosityCore'] = None
    _daemon_subs_initialized: bool = False

    def __new__(cls, feed_path: Optional[Path] = None, enable_daemon_subscriptions: bool = False):
        """Enforce singleton pattern to prevent thread/memory leaks."""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self, feed_path: Optional[Path] = None, enable_daemon_subscriptions: bool = False):
        """Initialize curiosity core."""
        if self._initialized:
            return

        if feed_path is None:
            feed_path = Path("/home/kloros/.kloros/curiosity_feed.json")

        self.feed_path = feed_path
        self.feed: Optional[CuriosityFeed] = None

        self.semantic_store: Optional[SemanticEvidenceStore] = None
        try:
            self.semantic_store = SemanticEvidenceStore()
            logger.debug("[curiosity_core] Initialized SemanticEvidenceStore for suppression tracking")
        except Exception as e:
            logger.warning(f"[curiosity_core] Failed to initialize SemanticEvidenceStore: {e}, suppression checks disabled")

        self.daemon_questions: List[CuriosityQuestion] = []
        self.chem_subs: List[Any] = []
        self.chem_pub = None
        self.processed_questions_path = Path("/home/kloros/.kloros/processed_questions.jsonl")
        self.value_threshold = 1.5

        if UMNPub is not None:
            try:
                self.chem_pub = UMNPub()
                logger.debug("[curiosity_core] Initialized UMNPub for direct signal emission")
            except Exception as e:
                logger.warning(f"[curiosity_core] Failed to initialize UMNPub: {e}, direct emission disabled")

        if enable_daemon_subscriptions and not CuriosityCore._daemon_subs_initialized:
            self.subscribe_to_daemon_questions()
            CuriosityCore._daemon_subs_initialized = True
            logger.info("[curiosity_core] Daemon subscriptions initialized")

        self._initialized = True
        logger.debug("[curiosity_core] CuriosityCore singleton initialized")

    def should_generate_followup(self, parent_question: Dict[str, Any], investigation_result: Dict[str, Any]) -> bool:
        """Decide if followup generation is productive."""
        parent_id = parent_question.get('id', '')

        if parent_id.endswith('.followup'):
            confidence = investigation_result.get('confidence', 0)
            evidence_list = investigation_result.get('evidence', [])
            evidence_count = len(evidence_list) if evidence_list else 0

            if confidence < 0.6 and evidence_count < 2:
                logger.info(f"[curiosity_core] Parent question {parent_id} unresolvable "
                           f"(low confidence={confidence:.2f}, insufficient evidence={evidence_count})")
                return False

        return True

    def _convert_daemon_message_to_questions(self, message: Dict[str, Any]) -> List[CuriosityQuestion]:
        """Convert a UMN daemon message to CuriosityQuestion objects."""
        questions = []

        try:
            facts = message.get('facts', {})

            question_id = facts.get('question_id')
            question_text = facts.get('question')
            hypothesis = facts.get('hypothesis')

            if not question_id or not question_text:
                logger.warning("[curiosity_core] Daemon message missing required fields (question_id, question)")
                return questions

            evidence = facts.get('evidence', [])
            severity = facts.get('severity', 'medium')
            source = facts.get('source', 'daemon')

            evidence_hash = None
            if evidence:
                evidence_str = '|'.join(sorted(evidence))
                evidence_hash = hashlib.sha256(evidence_str.encode()).hexdigest()[:16]

            action_class = ActionClass.INVESTIGATE
            if severity == 'critical':
                action_class = ActionClass.PROPOSE_FIX
            elif severity == 'high':
                action_class = ActionClass.INVESTIGATE

            metadata = {
                'severity': severity,
                'source': source,
            }
            if 'metadata' in facts:
                metadata.update(facts['metadata'])

            q = CuriosityQuestion(
                id=question_id,
                hypothesis=hypothesis or question_text,
                question=question_text,
                evidence=evidence,
                evidence_hash=evidence_hash,
                action_class=action_class,
                autonomy=2,
                value_estimate=0.8 if severity in ['critical', 'high'] else 0.6,
                cost=0.5,
                status=QuestionStatus.READY,
                created_at=datetime.now().isoformat(),
                metadata=metadata
            )

            questions.append(q)
            logger.info(f"[curiosity_core] Received 1 integration question from daemon: {question_id}")

        except Exception as e:
            logger.warning(f"[curiosity_core] Failed to convert daemon message: {e}")

        return questions

    def _on_daemon_question(self, message: Dict[str, Any]):
        """UMN callback for daemon question messages."""
        new_questions = self._convert_daemon_message_to_questions(message)
        self.daemon_questions.extend(new_questions)

    def subscribe_to_daemon_questions(self):
        """Subscribe to all daemon question streams via UMN."""
        if UMNSub is None:
            logger.warning("[curiosity_core] UMNSub not available, daemon subscription disabled")
            return

        daemon_signals = [
            "curiosity.integration_question",
            "curiosity.capability_question",
            "curiosity.exploration_question",
            "curiosity.knowledge_question"
        ]

        for signal in daemon_signals:
            try:
                sub = UMNSub(
                    topic=signal,
                    on_json=self._on_daemon_question,
                    zooid_name="curiosity_core",
                    niche="curiosity"
                )
                self.chem_subs.append(sub)
                logger.info(f"[curiosity_core] Subscribed to {signal}")
            except Exception as e:
                logger.warning(f"[curiosity_core] Failed to subscribe to {signal}: {e}")

        logger.info(f"[curiosity_core] Successfully subscribed to {len(self.chem_subs)}/4 daemon signals")

    def _get_daemon_questions(self) -> List[CuriosityQuestion]:
        """Retrieve and clear accumulated daemon questions."""
        questions = self.daemon_questions.copy()
        self.daemon_questions.clear()

        if questions:
            logger.info(f"[curiosity_core] Retrieved {len(questions)} integration questions from daemon")

        return questions

    def generate_questions_from_matrix(
        self,
        matrix: CapabilityMatrix,
        include_performance: bool = True,
        include_resources: bool = True,
        include_exceptions: bool = True
    ) -> CuriosityFeed:
        """Generate curiosity questions from capability matrix, performance trends, system resources, runtime exceptions, and test failures."""
        questions = []

        for cap in matrix.capabilities:
            if cap.state == CapabilityState.MISSING:
                q = self._question_for_missing_capability(cap)
                if q:
                    questions.append(q)

            elif cap.state == CapabilityState.DEGRADED:
                q = self._question_for_degraded_capability(cap)
                if q:
                    questions.append(q)

        if include_performance:
            try:
                perf_monitor = PerformanceMonitor()
                experiments = [
                    "spica_cognitive_variants",
                    "audio_latency_trim",
                    "conv_quality_tune",
                    "rag_opt_baseline",
                    "tool_evolution"
                ]
                perf_questions = perf_monitor.generate_performance_questions(experiments)
                questions.extend(perf_questions)
                logger.info(f"[curiosity_core] Generated {len(perf_questions)} performance questions")
            except Exception as e:
                logger.warning(f"[curiosity_core] Failed to generate performance questions: {e}")

        if include_resources:
            try:
                resource_monitor = SystemResourceMonitor()
                resource_questions = resource_monitor.generate_resource_questions()
                questions.extend(resource_questions)
                logger.info(f"[curiosity_core] Generated {len(resource_questions)} resource questions")
            except Exception as e:
                logger.warning(f"[curiosity_core] Failed to generate resource questions: {e}")

        if include_exceptions:
            try:
                exception_monitor = ExceptionMonitor()
                exception_questions = exception_monitor.generate_exception_questions()
                questions.extend(exception_questions)
                logger.info(f"[curiosity_core] Generated {len(exception_questions)} exception questions")
            except Exception as e:
                logger.warning(f"[curiosity_core] Failed to generate exception questions: {e}")

        try:
            test_monitor = TestResultMonitor()
            test_questions = test_monitor.generate_test_questions()
            questions.extend(test_questions)
            logger.info(f"[curiosity_core] Generated {len(test_questions)} test-failure questions")
        except Exception as e:
            logger.warning(f"[curiosity_core] Failed to generate test questions: {e}")

        logger.debug("[curiosity_core] Module discovery now provided by CapabilityDiscoveryDaemon")

        try:
            quality_monitor = MetricQualityMonitor()
            quality_questions = quality_monitor.generate_quality_questions()
            questions.extend(quality_questions)
            logger.info(f"[curiosity_core] Generated {len(quality_questions)} metric quality questions")
        except Exception as e:
            logger.warning(f"[curiosity_core] Failed to generate quality questions: {e}")

        try:
            chaos_monitor = ChaosLabMonitor()
            chaos_questions = chaos_monitor.generate_chaos_questions()
            questions.extend(chaos_questions)
            logger.info(f"[curiosity_core] Generated {len(chaos_questions)} chaos lab questions")
        except Exception as e:
            logger.warning(f"[curiosity_core] Failed to generate chaos questions: {e}")

        logger.debug("[curiosity_core] Integration questions now provided by IntegrationMonitorDaemon")
        logger.debug("[curiosity_core] Capability questions now provided by CapabilityDiscoveryDaemon")
        logger.debug("[curiosity_core] Exploration questions now provided by ExplorationScannerDaemon")
        logger.debug("[curiosity_core] Knowledge questions now provided by KnowledgeDiscoveryDaemon")

        try:
            daemon_questions = self._get_daemon_questions()
            questions.extend(daemon_questions)
            if daemon_questions:
                logger.info(f"[curiosity_core] Received {len(daemon_questions)} integration questions from daemon")
        except Exception as e:
            logger.warning(f"[curiosity_core] Failed to retrieve daemon questions: {e}")

        pre_reasoning_count = len(questions)
        try:
            from src.cognition.mind.cognition.processed_question_filter import ProcessedQuestionFilter

            question_filter = ProcessedQuestionFilter()
            questions = question_filter.filter_questions(questions)
            filtered_before_reasoning = pre_reasoning_count - len(questions)

            if filtered_before_reasoning > 0:
                logger.info(f"[curiosity_core] Early filter: removed {filtered_before_reasoning} "
                           f"questions in cooldown (saved expensive reasoning on {filtered_before_reasoning} questions)")
        except Exception as e:
            logger.warning(f"[curiosity_core] Early filtering failed, continuing: {e}")

        pre_disabled_filter_count = len(questions)
        filtered_questions = []
        for q in questions:
            if q.metadata.get("intentionally_disabled"):
                logger.debug(f"[curiosity_core] Skipping intentionally disabled: {q.id}")
                continue
            filtered_questions.append(q)
        questions = filtered_questions
        filtered_disabled = pre_disabled_filter_count - len(questions)
        if filtered_disabled > 0:
            logger.info(f"[curiosity_core] Filtered {filtered_disabled} questions for intentionally disabled services")

        pre_suppression_filter_count = len(questions)
        filtered_questions = []
        suppressed_count = 0
        for q in questions:
            capability_key = q.capability_key
            if capability_key and self.semantic_store:
                try:
                    if self.semantic_store.is_suppressed(capability_key):
                        suppression_info = self.semantic_store.get_suppression_info(capability_key)
                        reason = suppression_info.get("reason", "unknown reason")
                        logger.debug(f"[curiosity_core] Skipping suppressed capability: {capability_key} ({reason})")
                        suppressed_count += 1
                        continue
                except Exception as e:
                    logger.error(f"[curiosity_core] Error checking suppression for {capability_key}: {e}, assuming not suppressed")
            filtered_questions.append(q)
        questions = filtered_questions
        if suppressed_count > 0:
            logger.info(f"[curiosity_core] Filtered {suppressed_count} questions for suppressed capabilities")

        class StreamingBuffer:
            """Bounded buffer for streaming VOI-based ranking."""

            def __init__(self, capacity: int = 20):
                self.capacity = capacity
                self.buffer: List = []

            def add(self, item):
                """Add item to buffer. Returns top-10 by VOI when full, else None."""
                self.buffer.append(item)
                if len(self.buffer) >= self.capacity:
                    return self.flush()
                return None

            def flush(self):
                """Sort by VOI, return top-10, clear buffer."""
                self.buffer.sort(key=lambda x: x.voi_score, reverse=True)
                top_10 = self.buffer[:10]
                self.buffer.clear()
                return top_10

            def get_remaining(self):
                """Get remaining questions sorted by VOI."""
                if not self.buffer:
                    return []
                self.buffer.sort(key=lambda x: x.voi_score, reverse=True)
                return self.buffer[:10]

        try:
            from src.cognition.mind.cognition.curiosity_reasoning import get_curiosity_reasoning

            reasoning = get_curiosity_reasoning()

            discovery_questions = [q for q in questions if "UNDISCOVERED_MODULE" in q.hypothesis]
            other_questions = [q for q in questions if "UNDISCOVERED_MODULE" not in q.hypothesis]

            logger.info(f"[curiosity_core] Applying brainmods reasoning to {len(other_questions)} questions (preserving {len(discovery_questions)} discovery questions)...")

            buffer = StreamingBuffer(capacity=20)
            follow_up_count = 0
            all_reasoned = []

            logger.info(f"[curiosity_core] Streaming {len(other_questions)} questions through reasoning...")

            for reasoned_q in reasoning.stream_reason(other_questions):
                top_batch = buffer.add(reasoned_q)
                all_reasoned.append(reasoned_q)

                if top_batch:
                    logger.info(f"[curiosity_core] Processing top-10 batch from buffer (total followups: {follow_up_count})")

                    for rq in top_batch:
                        if follow_up_count >= MAX_FOLLOWUP_QUESTIONS_PER_CYCLE:
                            logger.info(f"Reached followup limit ({MAX_FOLLOWUP_QUESTIONS_PER_CYCLE}), stopping generation")
                            break

                        investigation_result = {
                            'confidence': rq.confidence,
                            'evidence': rq.follow_up_questions if rq.follow_up_questions else []
                        }

                        if not self.should_generate_followup({'id': rq.original_question.id}, investigation_result):
                            logger.debug(f"[curiosity_core] Skipping followup generation for {rq.original_question.id} (unresolvable)")
                            continue

                        if hasattr(rq.original_question, 'metadata') and rq.original_question.metadata.get('intentionally_disabled'):
                            logger.debug(f"[curiosity_core] Skipping followup generation for {rq.original_question.id} (intentionally disabled)")
                            continue

                        if hasattr(rq.original_question, 'capability_key') and rq.original_question.capability_key:
                            if self.semantic_store:
                                try:
                                    if self.semantic_store.is_suppressed(rq.original_question.capability_key):
                                        suppression_info = self.semantic_store.get_suppression_info(rq.original_question.capability_key)
                                        reason = suppression_info.get("reason", "unknown reason")
                                        logger.debug(f"[curiosity_core] Skipping followup generation for {rq.original_question.id} (capability suppressed: {rq.original_question.capability_key}, {reason})")
                                        continue
                                except Exception as e:
                                    logger.error(f"[curiosity_core] Error checking suppression for {rq.original_question.capability_key}: {e}, proceeding with followup")

                        if 'orphaned_queue' in rq.original_question.id:
                            from src.cognition.mind.cognition.systemd_helpers import is_service_intentionally_disabled
                            if is_service_intentionally_disabled('kloros-dream.service'):
                                logger.debug(f"[curiosity_core] Skipping followup generation for {rq.original_question.id} (D-REAM disabled)")
                                continue

                        if rq.follow_up_questions:
                            logger.info(f"[curiosity_core] Generating {len(rq.follow_up_questions)} "
                                      f"follow-up questions for {rq.original_question.id}")

                            for follow_up_dict in rq.follow_up_questions[:3]:
                                if follow_up_count >= MAX_FOLLOWUP_QUESTIONS_PER_CYCLE:
                                    logger.info(f"Reached followup limit ({MAX_FOLLOWUP_QUESTIONS_PER_CYCLE}), stopping generation")
                                    break

                                action_class_str = follow_up_dict.get('action_class', 'investigate')
                                try:
                                    action_class_enum = ActionClass(action_class_str)
                                except ValueError:
                                    action_class_enum = ActionClass.INVESTIGATE

                                follow_up_q = CuriosityQuestion(
                                    id=f"{rq.original_question.id}.followup.{follow_up_count}",
                                    hypothesis=follow_up_dict.get('hypothesis', 'UNKNOWN'),
                                    question=follow_up_dict.get('question', 'Unknown follow-up question'),
                                    evidence=[f"parent_question:{rq.original_question.id}",
                                            f"reason:{follow_up_dict.get('reason', 'Evidence gap detected')}",
                                            f"evidence_type:{follow_up_dict.get('evidence_type', 'unknown')}"],
                                    action_class=action_class_enum,
                                    value_estimate=rq.voi_score * 0.7,
                                    cost=0.2,
                                    capability_key=rq.original_question.capability_key if hasattr(rq.original_question, 'capability_key') else None
                                )
                                questions.append(follow_up_q)
                                follow_up_count += 1

                    if follow_up_count >= MAX_FOLLOWUP_QUESTIONS_PER_CYCLE:
                        break

            if follow_up_count < MAX_FOLLOWUP_QUESTIONS_PER_CYCLE:
                remaining = buffer.get_remaining()
                if remaining:
                    logger.info(f"[curiosity_core] Processing {len(remaining)} remaining questions from buffer")

                    for rq in remaining:
                        if follow_up_count >= MAX_FOLLOWUP_QUESTIONS_PER_CYCLE:
                            logger.info(f"Reached followup limit ({MAX_FOLLOWUP_QUESTIONS_PER_CYCLE}), stopping generation")
                            break

                        investigation_result = {
                            'confidence': rq.confidence,
                            'evidence': rq.follow_up_questions if rq.follow_up_questions else []
                        }

                        if not self.should_generate_followup({'id': rq.original_question.id}, investigation_result):
                            logger.debug(f"[curiosity_core] Skipping followup generation for {rq.original_question.id} (unresolvable)")
                            continue

                        if hasattr(rq.original_question, 'metadata') and rq.original_question.metadata.get('intentionally_disabled'):
                            logger.debug(f"[curiosity_core] Skipping followup generation for {rq.original_question.id} (intentionally disabled)")
                            continue

                        if hasattr(rq.original_question, 'capability_key') and rq.original_question.capability_key:
                            if self.semantic_store:
                                try:
                                    if self.semantic_store.is_suppressed(rq.original_question.capability_key):
                                        suppression_info = self.semantic_store.get_suppression_info(rq.original_question.capability_key)
                                        reason = suppression_info.get("reason", "unknown reason")
                                        logger.debug(f"[curiosity_core] Skipping followup generation for {rq.original_question.id} (capability suppressed: {rq.original_question.capability_key}, {reason})")
                                        continue
                                except Exception as e:
                                    logger.error(f"[curiosity_core] Error checking suppression for {rq.original_question.capability_key}: {e}, proceeding with followup")

                        if 'orphaned_queue' in rq.original_question.id:
                            from src.cognition.mind.cognition.systemd_helpers import is_service_intentionally_disabled
                            if is_service_intentionally_disabled('kloros-dream.service'):
                                logger.debug(f"[curiosity_core] Skipping followup generation for {rq.original_question.id} (D-REAM disabled)")
                                continue

                        if rq.follow_up_questions:
                            logger.info(f"[curiosity_core] Generating {len(rq.follow_up_questions)} "
                                      f"follow-up questions for {rq.original_question.id}")

                            for follow_up_dict in rq.follow_up_questions[:3]:
                                if follow_up_count >= MAX_FOLLOWUP_QUESTIONS_PER_CYCLE:
                                    logger.info(f"Reached followup limit ({MAX_FOLLOWUP_QUESTIONS_PER_CYCLE}), stopping generation")
                                    break

                                action_class_str = follow_up_dict.get('action_class', 'investigate')
                                try:
                                    action_class_enum = ActionClass(action_class_str)
                                except ValueError:
                                    action_class_enum = ActionClass.INVESTIGATE

                                follow_up_q = CuriosityQuestion(
                                    id=f"{rq.original_question.id}.followup.{follow_up_count}",
                                    hypothesis=follow_up_dict.get('hypothesis', 'UNKNOWN'),
                                    question=follow_up_dict.get('question', 'Unknown follow-up question'),
                                    evidence=[f"parent_question:{rq.original_question.id}",
                                            f"reason:{follow_up_dict.get('reason', 'Evidence gap detected')}",
                                            f"evidence_type:{follow_up_dict.get('evidence_type', 'unknown')}"],
                                    action_class=action_class_enum,
                                    value_estimate=rq.voi_score * 0.7,
                                    cost=0.2,
                                    capability_key=rq.original_question.capability_key if hasattr(rq.original_question, 'capability_key') else None
                                )
                                questions.append(follow_up_q)
                                follow_up_count += 1

            for rq in all_reasoned:
                if hasattr(rq.original_question, 'value_estimate'):
                    rq.original_question.value_estimate = rq.voi_score

            for dq in discovery_questions:
                dq.value_estimate = 0.95

            questions = discovery_questions + [rq.original_question for rq in all_reasoned]

            if follow_up_count > 0:
                logger.info(f"[curiosity_core] Added {follow_up_count} follow-up questions to feed")

            if questions:
                logger.info(f"[curiosity_core] Questions re-ranked by VOI, top question: "
                          f"{questions[0].id} (VOI: {questions[0].value_estimate:.2f})")
            else:
                logger.info(f"[curiosity_core] Questions re-ranked by VOI, top question: none")

        except Exception as e:
            logger.warning(f"[curiosity_core] Brainmods reasoning failed, continuing without: {e}")

        try:
            from src.cognition.mind.cognition.processed_question_filter import ProcessedQuestionFilter

            question_filter = ProcessedQuestionFilter()
            original_count = len(questions)
            questions = question_filter.filter_questions(questions)
            filtered_count = original_count - len(questions)

            if filtered_count > 0:
                logger.info(f"[curiosity_core] Safety filter: removed {filtered_count} questions "
                           f"in cooldown (mostly follow-ups, kept {len(questions)})")
        except Exception as e:
            logger.warning(f"[curiosity_core] Question filtering failed, "
                          f"continuing with unfiltered questions: {e}")

        self.feed = CuriosityFeed(questions=questions)
        return self.feed

    def _question_for_missing_capability(self, cap: CapabilityRecord) -> Optional[CuriosityQuestion]:
        """Generate question for missing capability."""
        why = cap.why.lower()

        if "not in group" in why:
            hypothesis = f"{cap.key.upper()}_PERMISSION"
            question = f"Can I prove {cap.key} works by adding user to the required group, or is there a permission-free substitute?"
            action_class = ActionClass.REQUEST_USER_ACTION
            value = 0.7
            cost = 0.2
        elif "not found" in why or "does not exist" in why:
            hypothesis = f"{cap.key.upper()}_INSTALLATION"
            question = f"What exact step installs {cap.key}, or what existing capability can substitute for it?"
            action_class = ActionClass.FIND_SUBSTITUTE
            value = 0.6
            cost = 0.3
        elif "not readable" in why or "not writable" in why:
            hypothesis = f"{cap.key.upper()}_ACCESS"
            question = f"What file permission change enables {cap.key}, and is it safe to apply at autonomy level 2?"
            action_class = ActionClass.PROPOSE_FIX
            value = 0.7
            cost = 0.2
        elif "not set" in why:
            hypothesis = f"{cap.key.upper()}_CONFIGURATION"
            question = f"What value should be set for the missing configuration, and what are the safe defaults?"
            action_class = ActionClass.INVESTIGATE
            value = 0.6
            cost = 0.1
        elif "not available" in why or "not in path" in why:
            hypothesis = f"{cap.key.upper()}_DEPENDENCY"
            question = f"Can I verify {cap.key} installation, or identify an alternative dependency?"
            action_class = ActionClass.FIND_SUBSTITUTE
            value = 0.5
            cost = 0.3
        elif "disabled in config" in why:
            hypothesis = f"{cap.key.upper()}_DISABLED"
            question = f"Why is {cap.key} disabled? Is it safe to enable, or should I use an alternative?"
            action_class = ActionClass.INVESTIGATE
            value = 0.4
            cost = 0.1
        else:
            hypothesis = f"{cap.key.upper()}_PRECONDITION"
            question = f"What unmet precondition blocks {cap.key}, and how can I work around it?"
            action_class = ActionClass.EXPLAIN_AND_SOFT_FALLBACK
            value = 0.5
            cost = 0.2

        if cap.kind in ["service", "reasoning"]:
            value += 0.1
        if cap.provides and len(cap.provides) > 2:
            value += 0.1
        value = min(1.0, value)

        return CuriosityQuestion(
            id=f"enable.{cap.key}",
            hypothesis=hypothesis,
            question=question,
            evidence=[
                f"capability:{cap.key}",
                f"state:{cap.state.value}",
                f"why:{cap.why}",
                f"provides:{','.join(cap.provides)}"
            ],
            action_class=action_class,
            autonomy=3,
            value_estimate=value,
            cost=cost,
            status=QuestionStatus.READY,
            capability_key=cap.key
        )

    def _question_for_degraded_capability(self, cap: CapabilityRecord) -> Optional[CuriosityQuestion]:
        """Generate question for degraded capability."""
        hypothesis = f"{cap.key.upper()}_DEGRADED"
        question = f"What caused {cap.key} to degrade ({cap.why}), and which past mitigation worked best?"
        action_class = ActionClass.PROPOSE_FIX
        value = 0.8
        cost = 0.3

        return CuriosityQuestion(
            id=f"stabilize.{cap.key}",
            hypothesis=hypothesis,
            question=question,
            evidence=[
                f"capability:{cap.key}",
                f"state:{cap.state.value}",
                f"why:{cap.why}",
                f"provides:{','.join(cap.provides)}"
            ],
            action_class=action_class,
            autonomy=3,
            value_estimate=value,
            cost=cost,
            status=QuestionStatus.READY,
            capability_key=cap.key
        )

    def write_feed_json(self) -> bool:
        """Write curiosity_feed.json to disk."""
        if not self.feed:
            logger.error("[curiosity_core] No feed to write (call generate_questions_from_matrix first)")
            return False

        try:
            self.feed_path.parent.mkdir(parents=True, exist_ok=True)

            with open(self.feed_path, 'w') as f:
                json.dump(self.feed.to_dict(), f, indent=2)

            logger.info(f"[curiosity_core] Wrote {len(self.feed.questions)} questions to {self.feed_path}")
            return True

        except Exception as e:
            logger.error(f"[curiosity_core] Failed to write feed: {e}")
            return False

    def load_feed_from_disk(self) -> bool:
        """Load curiosity_feed.json from disk into self.feed."""
        if not self.feed_path.exists():
            logger.warning(f"[curiosity_core] Feed file not found: {self.feed_path}")
            return False

        try:
            with open(self.feed_path, 'r') as f:
                data = json.load(f)

            questions = []
            for q_dict in data.get("questions", []):
                action_class_str = q_dict.get("action_class", "explain_and_soft_fallback")
                try:
                    action_class = ActionClass(action_class_str)
                except ValueError:
                    action_class = ActionClass.EXPLAIN_AND_SOFT_FALLBACK

                status_str = q_dict.get("status", "ready")
                try:
                    status = QuestionStatus(status_str)
                except ValueError:
                    status = QuestionStatus.READY

                question = CuriosityQuestion(
                    id=q_dict["id"],
                    hypothesis=q_dict["hypothesis"],
                    question=q_dict["question"],
                    evidence=q_dict.get("evidence", []),
                    action_class=action_class,
                    autonomy=q_dict.get("autonomy", 2),
                    value_estimate=q_dict.get("value_estimate", 0.5),
                    cost=q_dict.get("cost", 0.2),
                    status=status,
                    created_at=q_dict.get("created_at", datetime.now().isoformat()),
                    capability_key=q_dict.get("capability_key")
                )
                questions.append(question)

            self.feed = CuriosityFeed(
                questions=questions,
                generated_at=data.get("generated_at", datetime.now().isoformat())
            )

            logger.debug(f"[curiosity_core] Loaded {len(questions)} questions from {self.feed_path}")
            return True

        except Exception as e:
            logger.error(f"[curiosity_core] Failed to load feed from disk: {e}")
            return False

    def get_top_questions(self, n: int = 5) -> List[CuriosityQuestion]:
        """Get top N questions sorted by value/cost ratio."""
        if not self.feed:
            return []

        sorted_questions = sorted(
            self.feed.questions,
            key=lambda q: q.value_estimate / max(q.cost, 0.01),
            reverse=True
        )

        return sorted_questions[:n]

    def get_summary_text(self) -> str:
        """Generate human-readable summary of curiosity feed."""
        if not self.feed:
            return "No curiosity feed available"

        lines = []
        lines.append("CURIOSITY FEED")
        lines.append("=" * 60)
        lines.append(f"Total questions: {len(self.feed.questions)}")
        lines.append("")

        top_questions = self.get_top_questions(n=5)
        if top_questions:
            lines.append("TOP 5 QUESTIONS (by value/cost ratio):")
            for i, q in enumerate(top_questions, 1):
                ratio = q.value_estimate / max(q.cost, 0.01)
                lines.append(f"{i}. [{ratio:.1f}] {q.question}")
                lines.append(f"   Hypothesis: {q.hypothesis}")
                lines.append(f"   Action: {q.action_class.value}")
                lines.append("")

        return "\n".join(lines)

    def _is_question_processed(self, qid: str) -> bool:
        """Check if question has already been processed."""
        if not self.processed_questions_path.exists():
            return False

        try:
            with open(self.processed_questions_path, 'r') as f:
                for line in f:
                    if not line.strip():
                        continue
                    entry = json.loads(line)
                    if not isinstance(entry, dict):
                        continue
                    if entry.get("question_id") == qid:
                        return True
        except Exception as e:
            logger.warning(f"[curiosity_core] Error reading processed questions: {e}")

        return False

    def _mark_question_emitted(self, qid: str, evidence: List[Any] = None):
        """Mark question as emitted to prevent re-emission."""
        self.processed_questions_path.parent.mkdir(parents=True, exist_ok=True)

        import hashlib
        evidence_hash = None
        if evidence:
            evidence_str = "|".join(sorted(str(e) for e in evidence))
            evidence_hash = hashlib.sha256(evidence_str.encode()).hexdigest()[:16]

        entry = {
            "question_id": qid,
            "processed_at": datetime.now().timestamp(),
            "evidence_hash": evidence_hash
        }

        with open(self.processed_questions_path, 'a') as f:
            f.write(json.dumps(entry) + '\n')

    def emit_questions_to_bus(self) -> Dict[str, Any]:
        """
        Emit high-value questions directly to UMN bus as Q_CURIOSITY_INVESTIGATE signals.

        This bypasses the file-based handoff to curiosity_processor, allowing direct
        routing to investigation consumers.

        Returns:
            Dict with emission summary
        """
        if not self.feed:
            return {"status": "no_feed", "emitted": 0, "skipped": 0}

        if not self.chem_pub:
            logger.warning("[curiosity_core] UMNPub not available, falling back to write_feed_json")
            self.write_feed_json()
            return {"status": "fallback_to_file", "emitted": 0, "skipped": len(self.feed.questions)}

        emitted = 0
        skipped_low_value = 0
        skipped_processed = 0

        for q in self.feed.questions:
            ratio = q.value_estimate / max(q.cost, 0.01)

            if ratio < self.value_threshold:
                skipped_low_value += 1
                continue

            if self._is_question_processed(q.id):
                skipped_processed += 1
                continue

            priority_map = {
                "propose_fix": "high",
                "investigate": "normal",
                "find_substitute": "normal",
                "explain_and_soft_fallback": "low"
            }
            priority = priority_map.get(q.action_class.value, "normal")

            facts = {
                "question_id": q.id,
                "question": q.question,
                "hypothesis": q.hypothesis,
                "evidence": q.evidence,
                "capability_key": q.capability_key or "",
                "action_class": q.action_class.value,
                "value_estimate": q.value_estimate,
                "cost_estimate": q.cost,
                "priority": priority
            }

            try:
                self.chem_pub.emit(
                    signal="Q_CURIOSITY_INVESTIGATE",
                    ecosystem="introspection",
                    intensity=1.0,
                    facts=facts
                )
                self._mark_question_emitted(q.id, q.evidence)
                emitted += 1
                logger.debug(f"[curiosity_core] Emitted Q_CURIOSITY_INVESTIGATE: {q.id}")
            except Exception as e:
                logger.error(f"[curiosity_core] Failed to emit signal for {q.id}: {e}")

        logger.info(f"[curiosity_core] Emitted {emitted} questions "
                   f"(skipped: {skipped_low_value} low-value, {skipped_processed} already processed)")

        return {
            "status": "complete",
            "emitted": emitted,
            "skipped_low_value": skipped_low_value,
            "skipped_processed": skipped_processed
        }


def main():
    """Self-test and demonstration."""
    print("=== Curiosity Core Self-Test ===\n")

    try:
        from .capability_evaluator import CapabilityEvaluator
    except ImportError:
        from capability_evaluator import CapabilityEvaluator

    evaluator = CapabilityEvaluator()
    matrix = evaluator.evaluate_all()

    curiosity = CuriosityCore()
    feed = curiosity.generate_questions_from_matrix(matrix)

    print(curiosity.get_summary_text())

    if curiosity.write_feed_json():
        print(f"Wrote feed to {curiosity.feed_path}")
    else:
        print(f"Failed to write feed")

    return feed


if __name__ == "__main__":
    main()
