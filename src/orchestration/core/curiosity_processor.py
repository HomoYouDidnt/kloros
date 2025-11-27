#!/usr/bin/env python3
"""
Curiosity Processor - DEPRECATED.

This module is deprecated. CuriosityCore now emits Q_CURIOSITY_INVESTIGATE signals
directly via emit_questions_to_bus(), bypassing this middleman.

The curiosity_core_consumer_daemon now handles the complete flow:
  CuriosityCore.generate_questions_from_matrix() → CuriosityCore.emit_questions_to_bus() → InvestigationConsumer

This file is retained for backward compatibility but should not be used for new deployments.
The systemd service kloros-curiosity-processor.service can be disabled.
"""

import json
import hashlib
import logging
import subprocess
import os
import time
import contextlib
import shutil
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any, Optional
from queue import Queue, Empty

try:
    import filelock
except ImportError:
    filelock = None

logger = logging.getLogger(__name__)

CURIOSITY_FEED = Path("/home/kloros/.kloros/curiosity_feed.json")
SELF_STATE = Path("/home/kloros/.kloros/self_state.json")
INTENT_DIR = Path("/home/kloros/.kloros/intents")
PROCESSED_QUESTIONS = Path("/home/kloros/.kloros/processed_questions.jsonl")
LOCKS_DIR = Path("/home/kloros/.kloros/locks")
JOURNAL_DIR = Path("/home/kloros/.kloros/journals")

VALUE_THRESHOLD = 1.5

USE_PRIORITY_QUEUES = os.getenv("KLR_USE_PRIORITY_QUEUES", "1") == "1"

if USE_PRIORITY_QUEUES:
    try:
        from src.orchestration.core.umn_bus import UMNSub, UMNPub
        CHEM_AVAILABLE = True
    except ImportError:
        CHEM_AVAILABLE = False
        logger.warning("UMNSub/UMNPub not available, priority queue mode may not work")

    try:
        from src.cognition.mind.cognition.curiosity_archive_manager import ArchiveManager
        ARCHIVE_MGR_AVAILABLE = True
    except ImportError:
        ARCHIVE_MGR_AVAILABLE = False
        logger.warning("ArchiveManager not available, question archival disabled")
else:
    CHEM_AVAILABLE = False
    ARCHIVE_MGR_AVAILABLE = False


def _question_to_intent(question: Dict[str, Any]) -> Dict[str, Any]:
    """
    Convert a CuriosityQuestion to an intent for D-REAM.

    Args:
        question: CuriosityQuestion dict from curiosity_feed.json

    Returns:
        Intent dict for orchestrator consumption
    """
    qid = question["id"]
    hypothesis = question["hypothesis"]
    q_text = question["question"]
    action_class = question["action_class"]
    value = question["value_estimate"]
    cost = question["cost"]
    capability_key = question.get("capability_key", "unknown")

    # Map action classes to intent types
    if action_class == "propose_fix":
        intent_type = "curiosity_propose_fix"
        priority = 7
    elif action_class == "investigate":
        intent_type = "curiosity_investigate"
        priority = 6
    elif action_class == "find_substitute":
        intent_type = "curiosity_find_substitute"
        priority = 5
    else:
        intent_type = "curiosity_explore"
        priority = 4

    # Build D-REAM experiment suggestion
    experiment_hint = {
        "hypothesis": hypothesis,
        "search_space": _derive_search_space(question),
        "fitness_metric": _derive_fitness_metric(question),
        "exploration_budget": _derive_budget(value, cost)
    }

    intent = {
        "intent_type": intent_type,
        "priority": priority,
        "reason": f"CuriosityCore question: {hypothesis}",
        "data": {
            "question_id": qid,
            "question": q_text,
            "hypothesis": hypothesis,
            "capability_key": capability_key,
            "value_estimate": value,
            "cost_estimate": cost,
            "action_class": action_class,
            "evidence": question.get("evidence", []),
            "dream_experiment": experiment_hint
        },
        "generated_at": datetime.now().timestamp(),
        "emitted_by": "curiosity_processor"
    }

    return intent


def _derive_search_space(question: Dict[str, Any]) -> Dict[str, Any]:
    """
    Derive D-REAM search space from question context.

    Examples:
    - Swap pressure → memory management strategies
    - OOM errors → GPU allocation parameters
    - Missing capability → installation/substitution strategies
    """
    hypothesis = question["hypothesis"].lower()
    evidence = question.get("evidence", [])

    # Parse evidence for domain-specific hints
    domain = "unknown"
    for ev in evidence:
        if ev and ev.startswith("capability:"):
            domain = ev.split(":", 1)[1]
            break

    if "swap" in hypothesis or "memory" in hypothesis:
        return {
            "type": "memory_management",
            "parameters": {
                "restart_strategy": ["periodic", "threshold", "adaptive"],
                "memory_limit_mb": [2048, 4096, 8192, 12288],
                "oom_score_adj": [-1000, -500, 0, 500]
            },
            "domain": domain
        }
    elif "oom" in hypothesis or "gpu" in hypothesis:
        return {
            "type": "gpu_allocation",
            "parameters": {
                "tensor_parallel_size": [1, 2],
                "gpu_memory_utilization": [0.70, 0.75, 0.80, 0.85, 0.90],
                "max_num_seqs": [32, 64, 128, 256]
            },
            "domain": domain
        }
    elif "missing" in hypothesis or "installation" in hypothesis:
        return {
            "type": "capability_setup",
            "parameters": {
                "install_method": ["pip", "apt", "manual", "substitute"],
                "dependency_strategy": ["full", "minimal", "optional"]
            },
            "domain": domain
        }
    else:
        return {
            "type": "generic_exploration",
            "parameters": {},
            "domain": domain
        }


def _derive_fitness_metric(question: Dict[str, Any]) -> str:
    """Derive appropriate fitness metric for D-REAM experiment."""
    hypothesis = question["hypothesis"].lower()

    if "swap" in hypothesis or "memory" in hypothesis:
        return "swap_usage_reduction"
    elif "oom" in hypothesis:
        return "oom_prevention_rate"
    elif "latency" in hypothesis:
        return "latency_p50_improvement"
    elif "pass_rate" in hypothesis or "accuracy" in hypothesis:
        return "test_pass_rate"
    else:
        return "capability_availability"


def _derive_budget(value: float, cost: float) -> Dict[str, int]:
    """
    Derive exploration budget based on value/cost ratio.

    Higher value questions get more D-REAM resources.
    """
    ratio = value / max(cost, 0.01)

    if ratio >= 3.0:
        # Critical - large exploration
        return {"max_trials": 50, "max_time_minutes": 30}
    elif ratio >= 2.0:
        # High value - moderate exploration
        return {"max_trials": 30, "max_time_minutes": 20}
    elif ratio >= 1.5:
        # Medium value - quick exploration
        return {"max_trials": 15, "max_time_minutes": 10}
    else:
        # Low value - minimal exploration
        return {"max_trials": 5, "max_time_minutes": 5}


def _is_question_processed(qid: str) -> bool:
    """Check if question has already been processed."""
    if not PROCESSED_QUESTIONS.exists():
        return False

    try:
        with open(PROCESSED_QUESTIONS, 'r') as f:
            for line in f:
                if not line.strip():
                    continue
                entry = json.loads(line)
                # Skip non-dict entries (e.g., empty arrays from legacy format)
                if not isinstance(entry, dict):
                    continue
                if entry.get("question_id") == qid:
                    return True
    except Exception as e:
        logger.warning(f"Error reading processed questions: {e}")

    return False


def _evidence_hash(evidence: List[Any]) -> str:
    """
    Compute stable hash of evidence that triggered this question.

    Args:
        evidence: List of evidence strings/values

    Returns:
        16-character hash of sorted evidence
    """
    # Convert all evidence items to strings and sort for stability
    evidence_strings = [str(item) for item in evidence]
    evidence_str = "|".join(sorted(evidence_strings))
    return hashlib.sha256(evidence_str.encode()).hexdigest()[:16]


def _mark_question_processed(qid: str, intent_sha: str, evidence: List[Any] = None):
    """
    Mark question as processed with evidence hash.

    Args:
        qid: Question ID
        intent_sha: Intent hash
        evidence: List of evidence that triggered investigation (for context-aware re-investigation)
    """
    PROCESSED_QUESTIONS.parent.mkdir(parents=True, exist_ok=True)

    entry = {
        "question_id": qid,
        "processed_at": datetime.now().timestamp(),
        "intent_sha": intent_sha
    }

    # Include evidence hash for context-aware re-investigation
    if evidence:
        entry["evidence_hash"] = _evidence_hash(evidence)

    with open(PROCESSED_QUESTIONS, 'a') as f:
        f.write(json.dumps(entry) + '\n')


def _should_investigate_with_new_evidence(qid: str, current_evidence: List[Any]) -> bool:
    """
    Check if we should investigate based on NEW evidence (context-aware re-investigation).

    Returns True if:
    - Never investigated before, OR
    - Evidence has changed since last investigation

    Args:
        qid: Question ID
        current_evidence: Current evidence list for this question

    Returns:
        True if should investigate (new or changed evidence)
    """
    # EVIDENCE-BASED DEDUP BYPASS (2025-11-16): Align with processed_question_filter bypass
    # Rationale: Same as processed_question_filter - new actionability analysis deployed,
    # need to re-investigate all questions with new logic before implementing cooldowns.
    # Both dedup systems must honor the same bypass to prevent conflicting behavior.
    logger.debug(f"[curiosity_processor] {qid}: Evidence-based dedup bypass active - allowing through")
    return True

    # Original evidence-based dedup logic (DISABLED during bypass period):
    # if not PROCESSED_QUESTIONS.exists():
    #     return True  # Never processed anything
    #
    # current_hash = _evidence_hash(current_evidence)
    #
    # try:
    #     with open(PROCESSED_QUESTIONS) as f:
    #         for line in f:
    #             entry = json.loads(line.strip())
    #             if entry.get("question_id") == qid:
    #                 # Found previous processing
    #                 previous_hash = entry.get("evidence_hash")
    #                 if previous_hash == current_hash:
    #                     # Same evidence - skip re-investigation
    #                     return False
    #                 # Evidence changed - re-investigate!
    #                 # (will continue checking for most recent entry)
    #
    #     # Either never processed or evidence changed
    #     return True
    #
    # except Exception as e:
    #     logger.error(f"Error checking evidence for {qid}: {e}")
    #     return True  # Default to investigating on error


def _has_spawned_curiosity(qid: str) -> bool:
    """
    Check if we've already spawned experiments for this question.

    Makes re-runs idempotent by checking intents directory.
    """
    intents = list(INTENT_DIR.glob(f"curiosity_*{qid}.json"))
    archived_intents = list((INTENT_DIR / "processed").glob(f"**/curiosity_*{qid}.json"))

    return bool(intents or archived_intents)


def _processed_older_than(qid: str, days: int) -> bool:
    """
    Check if question was processed more than N days ago.

    Returns True if question is old enough to allow re-processing.
    Note: Checks most recent processed_at timestamp (file may have duplicates).
    """
    if not PROCESSED_QUESTIONS.exists():
        return True

    cutoff = time.time() - (days * 86400)
    most_recent_timestamp = 0

    try:
        with open(PROCESSED_QUESTIONS, 'r') as f:
            for line in f:
                if not line.strip():
                    continue
                entry = json.loads(line)
                # Skip non-dict entries (e.g., empty arrays from legacy format)
                if not isinstance(entry, dict):
                    continue
                if entry.get("question_id") == qid:
                    processed_at = entry.get("processed_at", 0)
                    if isinstance(processed_at, str):
                        try:
                            processed_at = datetime.fromisoformat(processed_at).timestamp()
                        except (ValueError, AttributeError):
                            processed_at = 0
                    most_recent_timestamp = max(most_recent_timestamp, processed_at)
    except Exception as e:
        logger.warning(f"Error checking processed age for {qid}: {e}")
        return True

    # If found, check if most recent processing is older than cutoff
    if most_recent_timestamp > 0:
        return most_recent_timestamp < cutoff

    # Not found = allow processing
    return True


def _reprocess_window_allows(qid: str) -> bool:
    """
    Check if re-processing window allows this question to be processed again.

    Uses KLR_CURIOSITY_REPROCESS_DAYS environment variable (default: 7 days).
    """
    days = int(os.environ.get("KLR_CURIOSITY_REPROCESS_DAYS", "7"))
    return _processed_older_than(qid, days)


@contextlib.contextmanager
def _curiosity_txn(qid: str):
    """
    Create a transaction context with file lock and journal for crash safety.

    The lock prevents concurrent processing of the same question.
    The journal enables crash recovery to detect partial processing.
    """
    LOCKS_DIR.mkdir(parents=True, exist_ok=True)
    JOURNAL_DIR.mkdir(parents=True, exist_ok=True)

    lock_path = LOCKS_DIR / f"curiosity_{qid}.lock"
    journal_path = JOURNAL_DIR / f"curiosity_{qid}.journal"

    if filelock is None:
        logger.warning(f"filelock not available, proceeding without lock for {qid}")
        try:
            journal_path.write_text(json.dumps({"stage": "begin", "qid": qid, "ts": time.time()}))
            yield {"journal": journal_path}
            journal_path.write_text(json.dumps({"stage": "commit", "qid": qid, "ts": time.time()}))
        finally:
            try:
                journal_path.unlink()
            except:
                pass
    else:
        with filelock.FileLock(str(lock_path), timeout=30):
            try:
                journal_path.write_text(json.dumps({"stage": "begin", "qid": qid, "ts": time.time()}))
                yield {"journal": journal_path}
                journal_path.write_text(json.dumps({"stage": "commit", "qid": qid, "ts": time.time()}))
            finally:
                try:
                    journal_path.unlink()
                except:
                    pass


def _cleanup_stale_processed_questions(max_age_days: int = None, max_entries: int = None):
    """
    Archive processed questions older than max_age_days and enforce max size with LRU eviction.

    This prevents the processed_questions.jsonl from growing indefinitely
    and allows re-processing of questions after they become stale.

    Args:
        max_age_days: Age threshold for archiving (default from KLR_CURIOSITY_REPROCESS_DAYS or 7 days)
        max_entries: Maximum entries to keep (default from KLR_CURIOSITY_MAX_PROCESSED or 500)
    """
    if not PROCESSED_QUESTIONS.exists():
        return

    if max_age_days is None:
        max_age_days = int(os.environ.get("KLR_CURIOSITY_REPROCESS_DAYS", "7"))
    if max_entries is None:
        max_entries = int(os.environ.get("KLR_CURIOSITY_MAX_PROCESSED", "500"))

    try:
        cutoff_time = datetime.now().timestamp() - (max_age_days * 86400)
        fresh_entries = []
        archived_count = 0

        # Read all entries and filter out stale ones
        with open(PROCESSED_QUESTIONS, 'r') as f:
            for line in f:
                if not line.strip():
                    continue
                entry = json.loads(line)
                if not isinstance(entry, dict):
                    continue
                processed_at = entry.get("processed_at", 0)

                if isinstance(processed_at, str):
                    try:
                        processed_at = datetime.fromisoformat(processed_at).timestamp()
                        entry["processed_at"] = processed_at
                    except (ValueError, AttributeError):
                        processed_at = 0
                        entry["processed_at"] = 0

                if processed_at > cutoff_time:
                    fresh_entries.append(entry)
                else:
                    archived_count += 1

        # LRU eviction: keep only most recent max_entries
        if len(fresh_entries) > max_entries:
            # Sort by processed_at (oldest first)
            fresh_entries.sort(key=lambda e: float(e.get("processed_at", 0)))
            # Keep only the newest max_entries
            evicted = len(fresh_entries) - max_entries
            fresh_entries = fresh_entries[-max_entries:]
            logger.info(f"LRU eviction: removed {evicted} oldest entries (kept {max_entries})")

        # Rewrite file with only fresh entries
        if archived_count > 0 or len(fresh_entries) != (archived_count + len(fresh_entries)):
            with open(PROCESSED_QUESTIONS, 'w') as f:
                for entry in fresh_entries:
                    f.write(json.dumps(entry) + '\n')

            logger.info(f"Archived {archived_count} stale processed questions (>{max_age_days} days old), "
                       f"kept {len(fresh_entries)} fresh entries")

    except Exception as e:
        logger.error(f"Error cleaning up processed questions: {e}")


def _check_for_stale_data() -> bool:
    """
    Check if curiosity feed is based on outdated capability state.

    Returns:
        True if feed should be regenerated, False otherwise
    """
    if not CURIOSITY_FEED.exists():
        return False  # No feed to be stale

    if not SELF_STATE.exists():
        return False  # No state to compare against

    try:
        state_mtime = SELF_STATE.stat().st_mtime
        feed_mtime = CURIOSITY_FEED.stat().st_mtime

        if state_mtime > feed_mtime:
            age_seconds = state_mtime - feed_mtime
            logger.warning(f"Stale curiosity feed detected: capability state updated {age_seconds:.1f}s after feed generation")
            return True

        return False
    except Exception as e:
        logger.error(f"Error checking for stale data: {e}")
        return False


def _regenerate_curiosity_feed() -> bool:
    """
    Regenerate curiosity feed from current capability state.

    Returns:
        True if regeneration succeeded, False otherwise
    """
    try:
        logger.info("Regenerating curiosity feed from updated capability state...")

        # Run curiosity_core module to regenerate feed
        result = subprocess.run(
            ["/home/kloros/.venv/bin/python3", "-m", "src.registry.curiosity_core"],
            cwd="/home/kloros",
            capture_output=True,
            text=True,
            timeout=30
        )

        if result.returncode == 0:
            logger.info("Successfully regenerated curiosity feed")
            return True
        else:
            logger.error(f"Failed to regenerate curiosity feed: {result.stderr[:200]}")
            return False

    except subprocess.TimeoutExpired:
        logger.error("Curiosity feed regeneration timed out after 30s")
        return False
    except Exception as e:
        logger.error(f"Error regenerating curiosity feed: {e}")
        return False


class CuriosityProcessorDaemon:
    """
    Event-driven curiosity processor supporting both file-polling and priority-queue modes.

    Priority Queue Mode (KLR_USE_PRIORITY_QUEUES=1):
    - Subscribes to 4 priority signals: CRITICAL, HIGH, MEDIUM, LOW
    - Callback-based processing via message queues
    - Archives skipped questions with skip reasons
    - Opportunistic rehydration from archives when idle

    File Polling Mode (KLR_USE_PRIORITY_QUEUES=0, legacy):
    - Polls curiosity_feed.json every 20 seconds
    - Processes all questions in sequence
    - Preserves backward compatibility for rollback
    """

    def __init__(self):
        self.running = False
        self.cycle_count = 0
        self.chem_pub = None

        if USE_PRIORITY_QUEUES and CHEM_AVAILABLE:
            try:
                self.chem_pub = UMNPub()
                logger.info("[curiosity_processor] UMNPub initialized for priority queue mode")
            except Exception as e:
                logger.error(f"[curiosity_processor] Failed to initialize UMNPub: {e}")
                self.chem_pub = None

            if ARCHIVE_MGR_AVAILABLE:
                try:
                    self.archive_mgr = ArchiveManager(
                        Path.home() / '.kloros' / 'archives',
                        self.chem_pub
                    )
                    logger.info("[curiosity_processor] ArchiveManager initialized")
                except Exception as e:
                    logger.error(f"[curiosity_processor] Failed to initialize ArchiveManager: {e}")
                    self.archive_mgr = None
            else:
                self.archive_mgr = None

            self.subscribers = {}
            self.message_queues = {}
            self._init_priority_subscribers()
        else:
            self.archive_mgr = None
            self.subscribers = {}
            self.message_queues = {}

    def _init_priority_subscribers(self):
        """Initialize subscribers to priority signals with message queues."""
        if not CHEM_AVAILABLE or not self.chem_pub:
            logger.warning("[curiosity_processor] Cannot initialize subscribers: UMNSub not available")
            return

        priority_levels = ['critical', 'high', 'medium', 'low']
        signal_names = {
            'critical': 'Q_CURIOSITY_CRITICAL',
            'high': 'Q_CURIOSITY_HIGH',
            'medium': 'Q_CURIOSITY_MEDIUM',
            'low': 'Q_CURIOSITY_LOW'
        }

        for level in priority_levels:
            self.message_queues[level] = Queue(maxsize=100)
            signal_name = signal_names[level]

            try:
                def make_callback(queue_ref):
                    def on_message(msg: Dict[str, Any]):
                        try:
                            question_dict = msg.get('facts', msg)
                            queue_ref.put_nowait(question_dict)
                        except:
                            logger.debug(f"Queue full for {signal_name}, dropping message")
                    return on_message

                subscriber = UMNSub(
                    topic=signal_name,
                    on_json=make_callback(self.message_queues[level]),
                    zooid_name=f"curiosity_processor_{level}",
                    niche="curiosity"
                )
                self.subscribers[level] = subscriber
                logger.info(f"[curiosity_processor] Subscribed to {signal_name} (priority={level})")

            except Exception as e:
                logger.error(f"[curiosity_processor] Failed to subscribe to {signal_name}: {e}")

    def run(self):
        """Main entry point: route to appropriate loop based on feature flag."""
        if USE_PRIORITY_QUEUES and CHEM_AVAILABLE and self.chem_pub:
            logger.info("[curiosity_processor] Starting priority queue loop")
            self._run_priority_queue_loop()
        else:
            logger.info("[curiosity_processor] Starting file polling loop (legacy mode)")
            self._run_file_polling_loop()

    def _run_priority_queue_loop(self):
        """
        Event-driven processing from priority signals.

        Polls subscribers in priority order (CRITICAL → HIGH → MEDIUM → LOW),
        processes questions through intent generation, archives skipped questions
        with skip reasons, and rehydrates from archives during idle periods.
        """
        self.running = True
        logger.info("[curiosity_processor] Priority queue loop started")

        while self.running:
            question_dict = None
            priority_level = None

            for level in ['critical', 'high', 'medium', 'low']:
                queue = self.message_queues.get(level)
                if not queue:
                    continue

                try:
                    question_dict = queue.get_nowait()
                    priority_level = level
                    break
                except Empty:
                    continue

            if not question_dict:
                main_feed_size = self._estimate_queue_size()
                if self.archive_mgr:
                    try:
                        self.archive_mgr.rehydrate_opportunistic(main_feed_size)
                    except Exception as e:
                        logger.error(f"[curiosity_processor] Rehydration error: {e}")

                time.sleep(1)
                continue

            self.cycle_count += 1
            qid = question_dict.get('id', 'unknown')
            logger.info(f"[curiosity_processor] Cycle {self.cycle_count}: "
                       f"Processing {qid} (priority={priority_level})")

            try:
                result = self._process_question(question_dict)

                if result['action'] == 'emit_intent':
                    if self.chem_pub:
                        try:
                            self.chem_pub.emit(
                                "Q_CURIOSITY_INVESTIGATE",
                                ecosystem='introspection',
                                facts={
                                    'question_id': qid,
                                    'question': question_dict.get('question'),
                                    'hypothesis': question_dict.get('hypothesis'),
                                    'capability_key': question_dict.get('capability_key'),
                                    'evidence': question_dict.get('evidence', []),
                                    'action_class': question_dict.get('action_class'),
                                    'value_estimate': question_dict.get('value_estimate'),
                                    'cost_estimate': question_dict.get('cost')
                                }
                            )
                            logger.info(f"[curiosity_processor] Emitted Q_CURIOSITY_INVESTIGATE for {qid}")
                        except Exception as e:
                            logger.error(f"[curiosity_processor] Failed to emit investigation signal for {qid}: {e}")

                elif result['action'] == 'skip':
                    if self.archive_mgr:
                        try:
                            self._archive_skipped_question(question_dict, result['reason'])
                        except Exception as e:
                            logger.error(f"[curiosity_processor] Archive error for {qid}: {e}")
                    else:
                        logger.debug(f"[curiosity_processor] Skipped {qid}: {result['reason']} (no archive)")

            except Exception as e:
                logger.error(f"[curiosity_processor] Error processing {qid}: {e}")

    def _run_file_polling_loop(self):
        """
        Legacy file-polling loop (backward compatibility).

        Uses existing process_curiosity_feed() logic.
        """
        self.running = True
        logger.info("[curiosity_processor] File polling loop started (legacy mode)")

        while self.running:
            try:
                result = process_curiosity_feed()
                logger.debug(f"[curiosity_processor] Polling cycle: {result}")
            except Exception as e:
                logger.error(f"[curiosity_processor] Polling error: {e}")

            time.sleep(20)

    def _process_question(self, question_dict: Dict) -> Dict:
        """
        Process single question, return action and reason.

        Returns:
            {'action': 'emit_intent' | 'skip', 'reason': str}
        """
        qid = question_dict.get('id', 'unknown')
        evidence = question_dict.get('evidence', [])

        evidence_based_dedup = _should_investigate_with_new_evidence(qid, evidence)
        if not evidence_based_dedup:
            return {'action': 'skip', 'reason': 'already_processed'}

        already_spawned = _has_spawned_curiosity(qid)
        if already_spawned:
            return {'action': 'skip', 'reason': 'already_processed'}

        if self._has_missing_dependencies(question_dict):
            return {'action': 'skip', 'reason': 'missing_deps'}

        try:
            intent = _question_to_intent(question_dict)
            self._emit_intent_as_signal(intent)

            # Compute intent hash for processed log
            intent_json = json.dumps(intent, indent=2)
            intent_sha = hashlib.sha256(intent_json.encode()).hexdigest()[:8]

            _mark_question_processed(qid, intent_sha=intent_sha, evidence=evidence)
            return {'action': 'emit_intent', 'reason': 'processed'}
        except Exception as e:
            logger.error(f"[curiosity_processor] Intent generation failed for {qid}: {e}")
            return {'action': 'skip', 'reason': 'intent_generation_error'}

    def _has_missing_dependencies(self, question: Dict) -> bool:
        """Check if question has unresolved dependencies."""
        capability_key = question.get('capability_key') or ''

        if capability_key.startswith('agent.'):
            playwright_path = Path('/home/kloros/.venv/bin/playwright')
            if not playwright_path.exists():
                logger.debug(f"[curiosity_processor] Missing playwright for {capability_key}")
                return True

        if capability_key.startswith('module.'):
            module_path = Path(f"/home/kloros/src/{capability_key.replace('.', '/')}")
            if not module_path.exists():
                logger.debug(f"[curiosity_processor] Missing module path: {module_path}")
                return True

        return False

    def _estimate_queue_size(self) -> int:
        """Estimate total questions waiting across all queues."""
        total = 0
        for level, queue in self.message_queues.items():
            total += queue.qsize()
        return total

    def _archive_skipped_question(self, question_dict: Dict, reason: str):
        """Archive skipped question with reason."""
        if not self.archive_mgr:
            return

        try:
            from src.cognition.mind.cognition.curiosity_core import CuriosityQuestion, ActionClass, QuestionStatus

            # Convert string fields to enums if needed
            q_dict = question_dict.copy()
            if 'action_class' in q_dict and isinstance(q_dict['action_class'], str):
                q_dict['action_class'] = ActionClass(q_dict['action_class'])
            if 'status' in q_dict and isinstance(q_dict['status'], str):
                q_dict['status'] = QuestionStatus(q_dict['status'])

            q = CuriosityQuestion(**q_dict)
            self.archive_mgr.archive_question(q, reason)

            # Add evidence hash to processed log to prevent re-emission
            if q.evidence_hash:
                try:
                    with open(PROCESSED_QUESTIONS, 'a') as f:
                        json.dump({
                            'id': q.id,
                            'evidence_hash': q.evidence_hash,
                            'processed_at': datetime.now().isoformat(),
                            'reason': f'archived_{reason}'
                        }, f)
                        f.write('\n')
                except Exception as e2:
                    logger.warning(f"[curiosity_processor] Could not add to processed log: {e2}")

            logger.debug(f"[curiosity_processor] Archived {q.id} as {reason}")
        except Exception as e:
            logger.warning(f"[curiosity_processor] Failed to archive question: {e}")

    def _emit_intent_as_signal(self, intent: Dict[str, Any]):
        """
        Emit intent directly as UMN signal instead of writing to file.

        Converts intent structure to appropriate UMN signal based on intent_type.
        """
        if not self.chem_pub:
            logger.warning(f"[curiosity_processor] Cannot emit signal: UMNPub not initialized")
            return

        intent_type = intent.get("intent_type", "unknown")
        intent_data = intent.get("data", {})
        priority = intent.get("priority", "normal")

        if isinstance(priority, int):
            priority_map = {10: "critical", 9: "critical", 8: "high", 7: "high", 6: "normal", 5: "normal", 4: "low"}
            priority_str = priority_map.get(priority, "normal")
        else:
            priority_str = priority

        signal_type = None
        ecosystem = "introspection"
        facts = {}

        if intent_type in ['curiosity_investigate', 'curiosity_propose_fix',
                          'curiosity_find_substitute', 'curiosity_explore']:
            signal_type = "Q_CURIOSITY_INVESTIGATE"
            facts = {
                "question": intent_data.get("question", ""),
                "question_id": intent_data.get("question_id", "unknown"),
                "priority": priority_str,
                "evidence": intent_data.get("evidence", []),
                "hypothesis": intent_data.get("hypothesis", ""),
                "capability_key": intent_data.get("capability_key", ""),
                "action_class": intent_data.get("action_class", "investigate")
            }

        elif intent_type == "integration_fix":
            signal_type = "Q_INTEGRATION_FIX"
            ecosystem = "queue_management"
            facts = {
                "question_id": intent_data.get("question_id", "unknown"),
                "question": intent_data.get("question", ""),
                "hypothesis": intent_data.get("hypothesis", ""),
                "fix_specification": intent_data.get("fix_specification", {}),
                "autonomy_level": intent_data.get("autonomy_level", 1),
                "reason": intent.get("reason", ""),
                "priority": priority_str
            }

        else:
            logger.warning(f"[curiosity_processor] Unknown intent type: {intent_type}, cannot emit signal")
            return

        try:
            self.chem_pub.emit(
                signal=signal_type,
                ecosystem=ecosystem,
                intensity=1.0,
                facts=facts
            )
            logger.info(f"[curiosity_processor] Emitted {signal_type} signal: {facts.get('question_id', 'unknown')}")
        except Exception as e:
            logger.error(f"[curiosity_processor] Failed to emit {signal_type}: {e}")

    def stop(self):
        """Gracefully stop the processor."""
        self.running = False
        for subscriber in self.subscribers.values():
            try:
                subscriber.close()
            except:
                pass
        if self.chem_pub:
            try:
                self.chem_pub.close()
            except:
                pass


def process_curiosity_feed() -> Dict[str, Any]:
    """
    Process curiosity_feed.json and emit intents for high-value questions.

    Questions are routed to investigation consumers via async chemical signals.

    Returns:
        Dict with processing summary
    """
    # Check if curiosity processing is disabled
    if os.environ.get("KLR_DISABLE_CURIOSITY") == "1":
        return {"status": "disabled", "intents_emitted": 0}

    # Clean up stale processed questions to allow re-processing
    _cleanup_stale_processed_questions()

    # Check for stale data and regenerate if needed
    if _check_for_stale_data():
        logger.info("Detected stale curiosity feed - regenerating before processing")
        if not _regenerate_curiosity_feed():
            logger.warning("Feed regeneration failed, proceeding with existing feed")

    if not CURIOSITY_FEED.exists():
        logger.debug("No curiosity feed found")
        return {"status": "no_feed", "intents_emitted": 0}

    try:
        with open(CURIOSITY_FEED, 'r') as f:
            feed = json.load(f)
    except Exception as e:
        logger.error(f"Failed to read curiosity feed: {e}")
        return {"status": "error", "error": str(e), "intents_emitted": 0}

    questions = feed.get("questions", [])
    intents_emitted = 0
    skipped_low_value = 0
    skipped_processed = 0

    logger.info(f"Processing {len(questions)} curiosity questions")

    for q in questions:
        qid = q["id"]
        value = q["value_estimate"]
        cost = q["cost"]
        ratio = value / max(cost, 0.01)
        action_class = q["action_class"]
        hypothesis = q.get("hypothesis") or ""

        # Check if already processed AND spawned (processed ≠ spawned)
        # Use evidence-based re-investigation for ALL questions (context-aware, not time-based)
        # This prevents wasting investigations on questions with identical evidence
        evidence = q.get("evidence", [])
        should_investigate = _should_investigate_with_new_evidence(qid, evidence)
        already_processed = not should_investigate  # Invert: if should investigate, not "already processed"
        already_spawned = _has_spawned_curiosity(qid)
        reprocess_age_ok = should_investigate  # Re-investigate when evidence changes

        # DIAGNOSTIC: Log decision variables for first 3 questions
        if skipped_processed + skipped_low_value < 3:
            logger.info(f"[DIAGNOSTIC] {qid}: processed={already_processed}, spawned={already_spawned}, age_ok={reprocess_age_ok}")

        # Skip only if processed AND (already spawned OR too recent to reprocess)
        if already_processed and (already_spawned or not reprocess_age_ok):
            skipped_processed += 1
            if skipped_processed <= 3:
                logger.info(f"[DIAGNOSTIC] Skipping {qid}: processed={already_processed} AND (spawned={already_spawned} OR age_not_ok={not reprocess_age_ok})")
            continue

        # Filter by value/cost ratio
        if ratio < VALUE_THRESHOLD:
            skipped_low_value += 1
            logger.debug(f"Skipping low-value question {qid} (ratio={ratio:.2f})")
            continue

        # Route to async chemical routing - emit UMN signal for investigation consumers
        intent = _question_to_intent(q)
        intent["data"]["experiment_result"] = {"status": "pending", "mode": "async_chemical_routing"}

        # Write intent to file for orchestrator visibility
        intent_file = INTENT_DIR / f"curiosity_{qid}_{int(datetime.now().timestamp())}.json"
        INTENT_DIR.mkdir(parents=True, exist_ok=True)
        with open(intent_file, 'w') as f:
            json.dump(intent, f, indent=2)

        logger.info(f"Created intent for question {qid} (ratio={ratio:.2f}, priority={intent['priority']})")
        intents_emitted += 1

    summary = {
        "status": "complete",
        "questions_total": len(questions),
        "intents_emitted": intents_emitted,
        "skipped_low_value": skipped_low_value,
        "skipped_processed": skipped_processed
    }

    # Structured logging for observability
    logger.info(json.dumps({
        "event": "curiosity_processing_complete",
        "intents_emitted": intents_emitted,
        "skipped_processed": skipped_processed,
        "skipped_low_value": skipped_low_value,
        "questions_seen": len(questions)
    }))

    return summary


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    result = process_curiosity_feed()
    print(json.dumps(result, indent=2))
