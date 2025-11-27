#!/usr/bin/env python3
"""
Curiosity Processor - Converts CuriosityCore questions into actionable intents.

Monitors curiosity_feed.json and spawns D-REAM experiments for high-value questions.
PHASE is for validation, not triggering - curiosity drives exploration immediately.
"""

import json
import hashlib
import logging
import subprocess
import os
import time
import contextlib
import shutil
from collections import deque
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any, Optional
from queue import Queue, Empty

try:
    import filelock
except ImportError:
    filelock = None

# SAFETY: ResourceGovernor for SPICA spawn throttling
try:
    from src.governance.resource_governor import ResourceGovernor
    SAFETY_ENABLED = True
except ImportError:
    SAFETY_ENABLED = False
    logging.warning("ResourceGovernor not available, SPICA spawn throttling disabled")

logger = logging.getLogger(__name__)

CURIOSITY_FEED = Path("/home/kloros/.kloros/curiosity_feed.json")
SELF_STATE = Path("/home/kloros/.kloros/self_state.json")
INTENT_DIR = Path("/home/kloros/.kloros/intents")
PROCESSED_QUESTIONS = Path("/home/kloros/.kloros/processed_questions.jsonl")
LOCKS_DIR = Path("/home/kloros/.kloros/locks")
JOURNAL_DIR = Path("/home/kloros/.kloros/journals")
SPICA_INSTANCES_DIR = Path("/home/kloros/.kloros/spica/instances")
PENDING_SPICA_QUEUE = Path("/home/kloros/.kloros/pending_spica_queue.jsonl")

# Value/cost ratio threshold for spawning D-REAM experiments
VALUE_THRESHOLD = 1.5  # Questions with ratio > 1.5 trigger experiments

# Circuit breaker for SPICA tournament spawning (prevents death spiral)
_tournament_failures = deque(maxlen=10)  # Track last 10 failures with timestamps
_circuit_open_until = None  # Timestamp when circuit breaker can close
CIRCUIT_BREAKER_THRESHOLD = 3  # Failures in 2 minutes
CIRCUIT_BREAKER_WINDOW = 120  # 2 minutes in seconds
CIRCUIT_BREAKER_COOLDOWN = 600  # 10 minutes cooldown when tripped

# SPICA Registry - authoritative source of valid instances (Phase 3.5)
SPICA_REGISTRY_PATH = Path.home() / ".kloros" / "spica_registry.json"
_spica_cache = []  # Cached list of active instance IDs
_spica_cache_ts = 0.0  # Cache timestamp
_SPICA_CACHE_TTL = 300.0  # 5 minutes cache lifetime

# Tournament rate limiting (Phase 3.5)
_tournament_history = []  # Timestamps of tournament runs
_MAX_TOURNAMENTS_PER_HOUR = int(os.getenv("KLR_SPICA_MAX_TOURNAMENTS_PER_HOUR", "4"))

# Tournament enable flag (Phase 3.5 - staged rollout)
ENABLE_SPICA_TOURNAMENTS = os.getenv("KLR_ENABLE_SPICA_TOURNAMENTS", "0") == "1"

# Priority queue feature flag (Task 5: Event-driven priority queue processing)
USE_PRIORITY_QUEUES = os.getenv("KLR_USE_PRIORITY_QUEUES", "1") == "1"

# Import ChemSub and ArchiveManager for priority queue mode
if USE_PRIORITY_QUEUES:
    try:
        from kloros.orchestration.chem_bus_v2 import ChemSub, ChemPub
        CHEM_AVAILABLE = True
    except ImportError:
        CHEM_AVAILABLE = False
        logger.warning("ChemSub/ChemPub not available, priority queue mode may not work")

    try:
        from registry.curiosity_archive_manager import ArchiveManager
        ARCHIVE_MGR_AVAILABLE = True
    except ImportError:
        ARCHIVE_MGR_AVAILABLE = False
        logger.warning("ArchiveManager not available, question archival disabled")
else:
    CHEM_AVAILABLE = False
    ARCHIVE_MGR_AVAILABLE = False


def _load_active_spica_instances(refresh: bool = False) -> List[str]:
    """
    Load active SPICA instances from authoritative registry.

    This prevents curiosity from requesting non-existent instance IDs that caused
    the death spiral (100% mismatch between requested vs. disk instances).

    Phase 3.5: Registry binding for controlled curiosity re-enable.

    Args:
        refresh: Force cache refresh

    Returns:
        List of active instance IDs (e.g., ['spica-229daf86', ...])
    """
    global _spica_cache, _spica_cache_ts

    now = time.time()
    if not refresh and (now - _spica_cache_ts) < _SPICA_CACHE_TTL and _spica_cache:
        return _spica_cache

    if not SPICA_REGISTRY_PATH.exists():
        logger.warning("[spica] Registry not found at %s", SPICA_REGISTRY_PATH)
        _spica_cache = []
        _spica_cache_ts = now
        return _spica_cache

    try:
        with SPICA_REGISTRY_PATH.open("r") as f:
            reg = json.load(f)
    except Exception as e:
        logger.error("[spica] Failed to load registry %s: %s", SPICA_REGISTRY_PATH, e)
        _spica_cache = []
        _spica_cache_ts = now
        return _spica_cache

    active = [
        name
        for name, meta in reg.get("instances", {}).items()
        if meta.get("state") == "active" and meta.get("valid") is True
    ]

    _spica_cache = active
    _spica_cache_ts = now

    logger.info("[spica] Loaded %d active SPICA instances from registry", len(active))
    return _spica_cache


def _select_spica_candidates(max_candidates: int = 3) -> List[str]:
    """
    Select SPICA instance candidates for tournament from registry.

    Returns only instances that exist and are validated (state=active, valid=true).
    This makes it structurally impossible to request ghost instances.

    Args:
        max_candidates: Maximum number of instances to select

    Returns:
        List of selected instance IDs (may be empty if registry has no instances)
    """
    candidates = _load_active_spica_instances()
    if not candidates:
        logger.warning("[spica] No active SPICA instances available; skipping tournament")
        return []

    # Simple deterministic selection: take first N from registry
    # (Could use random.sample() for variety if desired)
    sample = candidates[:max_candidates]
    logger.debug("[spica] Selected SPICA candidates for tournament: %s", sample)
    return sample


def _can_run_tournament(now: float) -> bool:
    """
    Check if tournament can run based on rate limit.

    Phase 3.5: Prevent tournament spam during staged re-enable.

    Args:
        now: Current timestamp

    Returns:
        True if rate limit allows tournament, False otherwise
    """
    global _tournament_history

    # Drop history older than 1 hour
    _tournament_history[:] = [t for t in _tournament_history if now - t <= 3600]

    if len(_tournament_history) >= _MAX_TOURNAMENTS_PER_HOUR:
        logger.warning(
            "[spica] Tournament rate limit reached (%d in last hour, max=%d); skipping",
            len(_tournament_history),
            _MAX_TOURNAMENTS_PER_HOUR
        )
        return False

    return True


def _record_tournament_run(now: float) -> None:
    """Record tournament run timestamp for rate limiting."""
    _tournament_history.append(now)


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

    Makes re-runs idempotent by checking both intents and SPICA instances.
    """
    intents = list(INTENT_DIR.glob(f"curiosity_*{qid}.json"))
    archived_intents = list((INTENT_DIR / "processed").glob(f"**/curiosity_*{qid}.json"))

    if SPICA_INSTANCES_DIR.exists():
        spica = list(SPICA_INSTANCES_DIR.glob(f"*{qid}*"))
    else:
        spica = []

    return bool(intents or archived_intents or spica)


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


def _add_to_pending_queue(question: Dict[str, Any]) -> bool:
    """
    Add a question to the pending SPICA spawn queue (with deduplication).

    Questions are queued when ResourceGovernor blocks spawning.
    They'll be processed on the next orchestrator run.

    Deduplication: Only adds if question ID not already in queue.

    Returns:
        True if added, False if already queued (duplicate)
    """
    PENDING_SPICA_QUEUE.parent.mkdir(parents=True, exist_ok=True)

    # Check if question already queued (deduplication)
    qid = question['id']
    if PENDING_SPICA_QUEUE.exists():
        try:
            with open(PENDING_SPICA_QUEUE, 'r') as f:
                for line in f:
                    if not line.strip():
                        continue
                    entry = json.loads(line)
                    if entry.get("question", {}).get("id") == qid:
                        logger.debug(f"[pending_queue] Question {qid} already queued, skipping duplicate")
                        return False  # Already queued
        except Exception as e:
            logger.warning(f"[pending_queue] Deduplication check failed: {e}")

    entry = {
        "question": question,
        "queued_at": datetime.now().timestamp()
    }

    with open(PENDING_SPICA_QUEUE, 'a') as f:
        f.write(json.dumps(entry) + '\n')

    logger.info(f"[pending_queue] Added {question['id']} to pending queue")
    return True  # Successfully added


def _get_pending_queue() -> List[Dict[str, Any]]:
    """
    Load all pending questions from the queue.

    Returns:
        List of question dicts (oldest first, FIFO order)
    """
    if not PENDING_SPICA_QUEUE.exists():
        return []

    questions = []
    try:
        with open(PENDING_SPICA_QUEUE, 'r') as f:
            for line in f:
                if not line.strip():
                    continue
                entry = json.loads(line)
                if isinstance(entry, dict) and "question" in entry:
                    questions.append(entry["question"])
    except Exception as e:
        logger.error(f"[pending_queue] Error reading pending queue: {e}")

    return questions


def _clear_pending_queue():
    """Clear the pending queue after successful processing."""
    if PENDING_SPICA_QUEUE.exists():
        PENDING_SPICA_QUEUE.unlink()
        logger.info(f"[pending_queue] Cleared pending queue")


def _spawn_direct_experiment(question: Dict[str, Any]) -> Dict[str, Any]:
    """
    Spawn a single D-REAM experiment for direct-build mode.

    Used when KLoROS provides specific guidance/hypothesis.
    """
    # SAFETY CHECK: Verify ResourceGovernor allows spawning
    if SAFETY_ENABLED:
        try:
            governor = ResourceGovernor()
            can_spawn, reason = governor.can_spawn()
            if not can_spawn:
                logger.warning(f"Direct experiment spawn blocked by ResourceGovernor: {reason}")
                return {
                    "mode": "direct_build",
                    "status": "blocked",
                    "reason": reason,
                    "question_id": question["id"]
                }
        except Exception as e:
            logger.error(f"ResourceGovernor check failed: {e}")
            # Continue with spawn (fail-open for now)

    try:
        from src.dream.config_tuning.spica_spawner import spawn_instance

        # Create candidate from question hypothesis
        candidate = {
            "hypothesis": question["hypothesis"],
            "capability_key": question.get("capability_key", "unknown"),
            "value_estimate": question["value_estimate"]
        }

        instance = spawn_instance(
            candidate=candidate,
            parent_id=None,
            notes=f"Curiosity direct-build: {question['id']}"
        )

        logger.info(f"Spawned direct-build SPICA instance: {instance.spica_id}")
        return {
            "mode": "direct_build",
            "status": "spawned",
            "spica_id": instance.spica_id,
            "question_id": question["id"]
        }

    except Exception as e:
        logger.error(f"Failed to spawn direct experiment: {e}", exc_info=True)
        return {
            "mode": "direct_build",
            "status": "error",
            "error": str(e)
        }


def _spawn_tournament(question: Dict[str, Any]) -> Dict[str, Any]:
    """
    Spawn a D-REAM tournament for open exploration.

    Creates 8+ SPICA cells with different strategies, bracket elimination.

    Implements circuit breaker to prevent death spiral:
    - Tracks failures with timestamps
    - Opens circuit (blocks spawns) after 3 failures in 2 minutes
    - Stays open for 10 minute cooldown period
    """
    global _circuit_open_until, _tournament_failures

    # CIRCUIT BREAKER: Check if in cooldown period
    current_time = time.time()
    if _circuit_open_until is not None and current_time < _circuit_open_until:
        remaining = int(_circuit_open_until - current_time)
        logger.warning(f"Circuit breaker OPEN: Blocking tournament spawn (cooldown: {remaining}s remaining)")
        return {
            "mode": "tournament",
            "status": "blocked",
            "reason": "circuit_breaker",
            "cooldown_remaining": remaining
        }

    # Circuit closed or cooldown expired - allow spawn
    if _circuit_open_until is not None and current_time >= _circuit_open_until:
        logger.info("Circuit breaker cooldown expired - closing circuit")
        _circuit_open_until = None

    # PRE-TOURNAMENT CLEANUP: Ensure space for new instances
    try:
        from src.integrations.spica_spawn import prune_instances
        prune_result = prune_instances(max_instances=2, max_age_days=1, dry_run=False)
        logger.info(f"Pre-tournament cleanup: pruned {prune_result.get('pruned', 0)} instances")

        if prune_result.get('pruned', 0) > 0:
            time.sleep(1)
    except Exception as e:
        logger.warning(f"Pre-tournament cleanup failed (non-fatal): {e}")

    try:
        from src.dream.evaluators.spica_tournament_evaluator import SPICATournamentEvaluator

        # Prepare tournament context
        context = {
            "question_id": question["id"],
            "hypothesis": question["hypothesis"],
            "search_space": _derive_search_space(question),
            "advancement_metric": "speed"
        }

        evaluator = SPICATournamentEvaluator(
            suite_id=f"curiosity.{question.get('capability_key', 'unknown')}",
            qtime={"epochs": 1, "slices_per_epoch": 4, "replicas_per_slice": 2}
        )

        # Generate 8 candidate strategies (minimum bracket size)
        candidates = _generate_candidate_strategies(question, min_count=8)

        logger.info(f"Spawning tournament with {len(candidates)} candidates for {question['id']}")

        # Run bracket evaluation
        fitnesses, artifacts = evaluator.evaluate_batch(candidates, context)

        # Find champion
        champion_idx = fitnesses.index(max(fitnesses))
        champion = candidates[champion_idx]

        logger.info(f"Tournament complete: Champion fitness={fitnesses[champion_idx]:.3f}")

        return {
            "mode": "tournament",
            "status": "complete",
            "question_id": question["id"],
            "champion": champion,
            "champion_fitness": fitnesses[champion_idx],
            "total_candidates": len(candidates),
            "artifacts": artifacts
        }

    except Exception as e:
        logger.error(f"Failed to spawn tournament: {e}", exc_info=True)

        # CIRCUIT BREAKER: Track failure and check threshold
        _tournament_failures.append(current_time)

        # Count failures in the time window
        cutoff_time = current_time - CIRCUIT_BREAKER_WINDOW
        recent_failures = sum(1 for t in _tournament_failures if t >= cutoff_time)

        if recent_failures >= CIRCUIT_BREAKER_THRESHOLD:
            _circuit_open_until = current_time + CIRCUIT_BREAKER_COOLDOWN
            logger.error(
                f"Circuit breaker TRIPPED: {recent_failures} failures in {CIRCUIT_BREAKER_WINDOW}s "
                f"(threshold: {CIRCUIT_BREAKER_THRESHOLD}). Blocking spawns for {CIRCUIT_BREAKER_COOLDOWN}s."
            )

        return {
            "mode": "tournament",
            "status": "error",
            "error": str(e),
            "circuit_failures": recent_failures
        }


def _generate_candidate_strategies(question: Dict[str, Any], min_count: int = 8) -> List[Dict[str, Any]]:
    """Generate diverse candidate strategies using evolutionary approach."""
    try:
        from src.dream.spica_evolution import generate_evolutionary_candidates

        question_id = question.get("id", "unknown")
        candidates = generate_evolutionary_candidates(question_id, min_count=min_count)
        logger.info(f"Generated {len(candidates)} evolutionary candidates for {question_id}")
        return candidates

    except Exception as e:
        logger.warning(f"Evolutionary generation failed, falling back to baseline strategies: {e}")

        base_strategies = [
            {"name": "conservative", "temperature": 0.3, "explore": False},
            {"name": "aggressive", "temperature": 0.9, "explore": True},
            {"name": "balanced", "temperature": 0.6, "explore": True},
            {"name": "adaptive", "temperature": 0.7, "adaptive_temp": True},
        ]

        while len(base_strategies) < min_count:
            base_strategies.append({
                "name": f"variant_{len(base_strategies)}",
                "temperature": 0.5 + (len(base_strategies) * 0.05),
                "explore": len(base_strategies) % 2 == 0
            })

        return base_strategies[:min_count]


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
                self.chem_pub = ChemPub()
                logger.info("[curiosity_processor] ChemPub initialized for priority queue mode")
            except Exception as e:
                logger.error(f"[curiosity_processor] Failed to initialize ChemPub: {e}")
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
            logger.warning("[curiosity_processor] Cannot initialize subscribers: ChemSub not available")
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

                subscriber = ChemSub(
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

        autonomy = question_dict.get('autonomy', 2)
        if autonomy >= 3 and SAFETY_ENABLED:
            try:
                governor = ResourceGovernor()
                can_spawn, reason = governor.can_spawn()
                if not can_spawn:
                    return {'action': 'skip', 'reason': 'resource_blocked'}
            except Exception as e:
                logger.warning(f"[curiosity_processor] ResourceGovernor check failed for {qid}: {e}")

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
            from registry.curiosity_core import CuriosityQuestion, ActionClass, QuestionStatus

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
        Emit intent directly as ChemBus signal instead of writing to file.

        Converts intent structure to appropriate ChemBus signal based on intent_type.
        """
        if not self.chem_pub:
            logger.warning(f"[curiosity_processor] Cannot emit signal: ChemPub not initialized")
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

        elif intent_type == "spica_spawn_request":
            signal_type = "Q_SPICA_SPAWN"
            ecosystem = "experimentation"
            facts = {
                "question_id": intent_data.get("question_id", "unknown"),
                "question": intent_data.get("question", ""),
                "hypothesis": intent_data.get("hypothesis", ""),
                "fix_context": intent_data.get("fix_context", {}),
                "validation": intent_data.get("validation", {}),
                "priority": priority_str,
                "reason": intent.get("reason", "")
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
    Process curiosity_feed.json and spawn D-REAM experiments for high-value questions.

    Returns:
        Dict with processing summary
    """
    # Check if curiosity processing is disabled
    if os.environ.get("KLR_DISABLE_CURIOSITY") == "1":
        return {"status": "disabled", "intents_emitted": 0, "experiments_spawned": 0}

    # Clean up stale processed questions to allow re-processing
    _cleanup_stale_processed_questions()

    # Check for stale data and regenerate if needed
    if _check_for_stale_data():
        logger.info("Detected stale curiosity feed - regenerating before processing")
        if not _regenerate_curiosity_feed():
            logger.warning("Feed regeneration failed, proceeding with existing feed")

    if not CURIOSITY_FEED.exists():
        logger.debug("No curiosity feed found")
        return {"status": "no_feed", "intents_emitted": 0, "experiments_spawned": 0}

    try:
        with open(CURIOSITY_FEED, 'r') as f:
            feed = json.load(f)
    except Exception as e:
        logger.error(f"Failed to read curiosity feed: {e}")
        return {"status": "error", "error": str(e), "intents_emitted": 0, "experiments_spawned": 0}

    questions = feed.get("questions", [])
    intents_emitted = 0
    experiments_spawned = 0
    skipped_low_value = 0
    skipped_processed = 0

    # PROCESS PENDING QUEUE FIRST (FIFO - oldest questions first)
    pending_questions = _get_pending_queue()
    if pending_questions:
        logger.info(f"[pending_queue] Found {len(pending_questions)} pending questions from previous runs")
        # Prepend pending questions (process them first, in order they were queued)
        questions = pending_questions + questions
        # Clear the pending queue file now that we've loaded them
        _clear_pending_queue()

    logger.info(f"Processing {len(questions)} curiosity questions ({len(pending_questions)} pending + {len(feed.get('questions', []))} new)")

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

        # INTEGRATION QUESTIONS: Route to BOTH documentation AND autonomous fix (if autonomy >= 3)
        if hypothesis.startswith(("ORPHANED_QUEUE_", "UNINITIALIZED_COMPONENT_", "DUPLICATE_")):
            try:
                from src.dream.remediation_manager import RemediationExperimentGenerator
                remediation = RemediationExperimentGenerator()
                fix_spec = remediation.generate_from_integration_question(q)

                if fix_spec:
                    autonomy = q.get("autonomy", 2)
                    logger.info(f"[integration_fix] Generated fix for {qid}: {fix_spec.get('action_type')} (autonomy={autonomy})")

                    # CHECK ResourceGovernor FIRST if autonomy >= 3 (will spawn SPICA)
                    if autonomy >= 3:
                        if SAFETY_ENABLED:
                            try:
                                governor = ResourceGovernor()
                                can_spawn, reason = governor.can_spawn()
                                if not can_spawn:
                                    logger.info(f"[pending_queue] ResourceGovernor blocked {qid}: {reason}")
                                    was_added = _add_to_pending_queue(q)
                                    if was_added:
                                        logger.info(f"[pending_queue] Added {qid} to queue for next run")
                                    else:
                                        logger.info(f"[pending_queue] {qid} already queued, moving to next question")
                                    # Don't create any intents - will process from queue later
                                    continue
                            except Exception as e:
                                logger.error(f"[spica_spawn] ResourceGovernor check failed for {qid}: {e}")
                                # Continue with spawn (fail-open for now)

                    # ALWAYS create documentation intent (if we got here, ResourceGovernor allowed it or autonomy < 3)
                    doc_intent = {
                        "intent_type": "integration_fix",
                        "priority": 9,
                        "reason": f"Integration issue: {hypothesis}",
                        "data": {
                            "question_id": qid,
                            "question": q["question"],
                            "hypothesis": hypothesis,
                            "fix_specification": fix_spec,
                            "autonomy_level": autonomy
                        },
                        "generated_at": datetime.now().timestamp(),
                        "emitted_by": "curiosity_processor_integration_router"
                    }

                    self._emit_intent_as_signal(doc_intent)
                    intents_emitted += 1
                    logger.info(f"[integration_fix] Emitted Q_INTEGRATION_FIX signal for {qid}")

                    # CONDITIONALLY create SPICA spawn intent for high autonomy
                    if autonomy >= 3:

                        evidence = q.get("evidence", [])

                        target_files = []
                        for ev in evidence:
                            if "Produced in:" in ev or "Found in:" in ev:
                                parts = ev.split(":")
                                if len(parts) >= 2:
                                    file_paths = parts[1].strip()
                                    for file_path in file_paths.split(","):
                                        file_path = file_path.strip()
                                        if file_path:
                                            target_files.append(file_path)

                        spica_intent = {
                            "intent_type": "spica_spawn_request",
                            "priority": q.get("priority", 8),
                            "reason": "Autonomous fix attempt for integration issue",
                            "data": {
                                "question_id": qid,
                                "question": q["question"],
                                "hypothesis": hypothesis,
                                "fix_context": {
                                    "evidence": evidence,
                                    "analysis_report": None,
                                    "target_files": target_files,
                                    "proposed_changes": fix_spec.get("action", "Fix integration issue")
                                },
                                "validation": {
                                    "run_tests": True,
                                    "test_command": "uv run pytest tests/ -v",
                                    "require_pass": True
                                }
                            },
                            "generated_at": datetime.now().timestamp(),
                            "emitted_by": "curiosity_processor_spica_router"
                        }

                        self._emit_intent_as_signal(spica_intent)
                        intents_emitted += 1
                        logger.info(f"[spica_spawn] Emitted Q_SPICA_SPAWN signal for {qid} (autonomy={autonomy})")

                    _mark_question_processed(qid, doc_intent_sha, evidence)
                    continue
                else:
                    logger.warning(f"[integration_fix] No fix generated for {qid}, falling back to D-REAM")
            except Exception as e:
                logger.error(f"[integration_fix] Failed to generate fix for {qid}: {e}")
                # Fall through to D-REAM

        # Route to D-REAM mode based on action_class (ONLY if synchronous tournaments enabled)
        # By default (ENABLE_SPICA_TOURNAMENTS=0), rely on chemical signal routing for async processing
        if ENABLE_SPICA_TOURNAMENTS:
            if action_class in ["propose_fix", "explain_and_soft_fallback"]:
                # Direct build - KLoROS provided specific guidance
                logger.info(f"[DIAGNOSTIC] Direct-build mode for {qid} (action={action_class})")
                experiment_result = _spawn_direct_experiment(q)
                experiments_spawned += 1
                logger.info(f"[DIAGNOSTIC] Spawned direct experiment for {qid}, experiments_spawned now={experiments_spawned}")
            else:
                # Tournament mode - open exploration needed
                logger.info(f"Tournament mode for {qid} (action={action_class})")
                experiment_result = _spawn_tournament(q)
                experiments_spawned += 1

            # Also emit intent as ChemBus signal for orchestrator visibility
            intent = _question_to_intent(q)
            intent["data"]["experiment_result"] = experiment_result

            self._emit_intent_as_signal(intent)
            logger.info(f"Emitted ChemBus signal for question {qid} (ratio={ratio:.2f}, priority={intent['priority']})")
            intents_emitted += 1

            try:
                # Mark as processed with evidence hash for context-aware re-investigation
                intent_json = json.dumps(intent, indent=2)
                intent_sha = hashlib.sha256(intent_json.encode()).hexdigest()[:8]
                _mark_question_processed(qid, intent_sha, evidence)

            except Exception as e:
                logger.error(f"Failed to emit intent for {qid}: {e}")
        else:
            # Synchronous tournaments disabled - emit ChemBus signal for async chemical routing
            logger.debug(f"Skipping synchronous tournament for {qid} (ENABLE_SPICA_TOURNAMENTS=0, will route via chemical signals)")
            intent = _question_to_intent(q)
            intent["data"]["experiment_result"] = {"status": "pending", "mode": "async_chemical_routing"}

            self._emit_intent_as_signal(intent)
            logger.info(f"Emitted ChemBus signal for question {qid} (ratio={ratio:.2f}, priority={intent['priority']})")
            intents_emitted += 1

            # NOTE: Don't mark as processed yet for async routing - investigation_consumer will mark when complete

    summary = {
        "status": "complete",
        "questions_total": len(questions),
        "intents_emitted": intents_emitted,
        "experiments_spawned": experiments_spawned,
        "skipped_low_value": skipped_low_value,
        "skipped_processed": skipped_processed
    }

    # Structured logging for observability
    logger.info(json.dumps({
        "event": "curiosity_processing_complete",
        "experiments_spawned": experiments_spawned,
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
