"""
Exception Monitor - Runtime error detection and tracking.

Monitors orchestrator/system logs and DREAM experiment logs for exceptions.
"""

import hashlib
import json
import logging
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional

from .base_types import (
    CuriosityQuestion,
    QuestionStatus,
    ActionClass,
)

logger = logging.getLogger(__name__)


class ExceptionMonitor:
    """
    Monitors orchestrator/system logs and DREAM experiment logs for exceptions.

    Purpose:
        Automatically detect runtime failures and systematic errors, route to D-REAM for resolution

    Monitors:
        - ModuleNotFoundError / ImportError
        - FileNotFoundError
        - AttributeError
        - ValueError (systematic failures)
        - TypeError
        - Runtime exceptions in orchestrator logs
        - Repeated errors in DREAM experiment runs
    """

    def __init__(
        self,
        orchestrator_log_path: Path = Path("/home/kloros/logs/orchestrator"),
        dream_log_path: Path = Path("/home/kloros/logs/dream"),
        chat_log_path: Path = Path("/home/kloros/.kloros/logs")
    ):
        self.orchestrator_log_path = orchestrator_log_path
        self.dream_log_path = dream_log_path
        self.chat_log_path = chat_log_path
        self.lookback_minutes = 60
        self.systematic_error_threshold = 3
        self.chat_error_threshold = 2

    def generate_exception_questions(self) -> List[CuriosityQuestion]:
        """Parse orchestrator and DREAM logs for exceptions and generate questions."""
        questions = []

        if self.orchestrator_log_path.exists():
            try:
                experiments_log = self.orchestrator_log_path / "curiosity_experiments.jsonl"
                if experiments_log.exists():
                    exceptions = self._parse_jsonl_exceptions(experiments_log)
                    for exc in exceptions:
                        q = self._question_for_exception(exc)
                        if q:
                            questions.append(q)
            except Exception as e:
                logger.warning(f"[exception_monitor] Failed to read orchestrator logs: {e}")

        if self.dream_log_path.exists():
            try:
                systematic_errors = self._scan_dream_logs_for_systematic_errors()
                for error_info in systematic_errors:
                    q = self._question_for_systematic_error(error_info)
                    if q:
                        questions.append(q)
            except Exception as e:
                logger.warning(f"[exception_monitor] Failed to read DREAM logs: {e}")

        if self.chat_log_path.exists():
            try:
                chat_issues = self._scan_chat_logs_for_issues()
                for issue_info in chat_issues:
                    q = self._question_for_chat_issue(issue_info)
                    if q:
                        questions.append(q)
                logger.info(f"[exception_monitor] Generated {len([q for q in questions if 'chat' in q.id])} chat-related questions")
            except Exception as e:
                logger.warning(f"[exception_monitor] Failed to read chat logs: {e}")

        return questions

    def _parse_jsonl_exceptions(self, log_file: Path) -> List[Dict[str, Any]]:
        """Parse JSONL log file for exceptions from recent entries."""
        exceptions = []
        cutoff_time = datetime.now().timestamp() - (self.lookback_minutes * 60)

        try:
            with open(log_file, 'r') as f:
                for line in f:
                    try:
                        entry = json.loads(line)

                        ts = entry.get("ts")
                        if isinstance(ts, str):
                            ts = datetime.fromisoformat(ts.replace('Z', '+00:00')).timestamp()
                        elif not isinstance(ts, (int, float)):
                            continue

                        if ts < cutoff_time:
                            continue

                        result = entry.get("intent", {}).get("data", {}).get("experiment_result", {})
                        if result.get("status") == "error":
                            error_msg = result.get("error", "")
                            if error_msg and ("ModuleNotFoundError" in error_msg or
                                            "ImportError" in error_msg or
                                            "No module named" in error_msg):

                                module = ""
                                if "No module named " in error_msg:
                                    parts = error_msg.split("No module named ")
                                    if len(parts) > 1:
                                        module = parts[1].strip().strip("'\"").split()[0]

                                exc = {
                                    "type": "ModuleNotFoundError" if "ModuleNotFoundError" in error_msg else "ImportError",
                                    "message": error_msg,
                                    "module": module,
                                    "context": entry.get("intent", {}).get("data", {}).get("question", ""),
                                    "timestamp": ts,
                                    "similar_modules": []
                                }

                                if "spica_domain" in module or module.startswith("src.phase.domains.spica"):
                                    exc["similar_modules"] = self._find_similar_modules(module)

                                exceptions.append(exc)

                    except json.JSONDecodeError:
                        continue

        except Exception as e:
            logger.error(f"[exception_monitor] Failed to parse {log_file}: {e}")

        return exceptions

    def _scan_dream_logs_for_systematic_errors(self) -> List[Dict[str, Any]]:
        """Scan all DREAM experiment logs for systematic repeated errors."""
        systematic_errors = []
        cutoff_time = datetime.now().timestamp() - (self.lookback_minutes * 60)

        if not self.dream_log_path.exists():
            return systematic_errors

        for log_file in self.dream_log_path.glob("*.jsonl"):
            try:
                error_counts = defaultdict(lambda: {"count": 0, "recent_ts": 0, "params": []})
                experiment_name = log_file.stem

                with open(log_file, 'r') as f:
                    for line in f:
                        try:
                            entry = json.loads(line)

                            ts = entry.get("ts", 0)
                            if not isinstance(ts, (int, float)) or ts < cutoff_time:
                                continue

                            error = entry.get("error")
                            if error:
                                error_key = error.split("(")[0] if "(" in error else error
                                error_counts[error_key]["count"] += 1
                                error_counts[error_key]["recent_ts"] = max(
                                    error_counts[error_key]["recent_ts"], ts
                                )
                                params = entry.get("params", {})
                                if len(error_counts[error_key]["params"]) < 3:
                                    error_counts[error_key]["params"].append(params)

                        except json.JSONDecodeError:
                            continue

                for error_type, info in error_counts.items():
                    if info["count"] >= self.systematic_error_threshold:
                        systematic_errors.append({
                            "experiment": experiment_name,
                            "error_type": error_type,
                            "error_count": info["count"],
                            "recent_timestamp": info["recent_ts"],
                            "sample_params": info["params"][:3]
                        })

            except Exception as e:
                logger.warning(f"[exception_monitor] Failed to scan {log_file}: {e}")

        return systematic_errors

    def _question_for_systematic_error(self, error_info: Dict[str, Any]) -> Optional[CuriosityQuestion]:
        """Generate curiosity question from systematic error pattern."""
        experiment = error_info["experiment"]
        error_type = error_info["error_type"]
        count = error_info["error_count"]
        sample_params = error_info.get("sample_params", [])

        if "ValueError" in error_type:
            error_category = "value_error"
            action_class = ActionClass.PROPOSE_FIX
            hypothesis = f"SYSTEMATIC_VALUE_ERROR_{experiment.upper()}"
        elif "TypeError" in error_type:
            error_category = "type_error"
            action_class = ActionClass.PROPOSE_FIX
            hypothesis = f"SYSTEMATIC_TYPE_ERROR_{experiment.upper()}"
        elif "ModuleNotFoundError" in error_type or "ImportError" in error_type:
            error_category = "import_error"
            action_class = ActionClass.PROPOSE_FIX
            hypothesis = f"SYSTEMATIC_IMPORT_ERROR_{experiment.upper()}"
        else:
            error_category = "unknown_error"
            action_class = ActionClass.INVESTIGATE
            hypothesis = f"SYSTEMATIC_ERROR_{experiment.upper()}"

        error_summary = error_type[:200] if len(error_type) > 200 else error_type

        evidence = [
            f"experiment:{experiment}",
            f"error_type:{error_category}",
            f"occurrences:{count}",
            f"error:{error_summary}"
        ]

        if sample_params:
            evidence.append(f"sample_params:{json.dumps(sample_params[0])[:100]}")

        q = CuriosityQuestion(
            id=f"systematic.{experiment}.{error_category}.{hashlib.md5(error_type.encode()).hexdigest()[:8]}",
            hypothesis=hypothesis,
            question=(
                f"Why is {experiment} failing systematically with {error_type}? "
                f"This error occurred {count} times in the last {self.lookback_minutes} minutes. "
                f"How do I fix the root cause?"
            ),
            evidence=evidence,
            action_class=action_class,
            autonomy=3,
            value_estimate=0.9,
            cost=0.4,
            capability_key=f"experiment.{experiment}"
        )

        return q

    def _scan_chat_logs_for_issues(self) -> List[Dict[str, Any]]:
        """Scan chat logs for conversation issues."""
        issues = []
        cutoff_time = datetime.now().timestamp() - (self.lookback_minutes * 60)

        issue_counts = defaultdict(lambda: {"count": 0, "examples": []})

        today = datetime.now().strftime("%Y%m%d")
        log_file = self.chat_log_path / f"kloros-{today}.jsonl"

        if not log_file.exists():
            return issues

        try:
            with open(log_file, 'r') as f:
                for line in f:
                    try:
                        entry = json.loads(line)

                        ts_str = entry.get("ts")
                        if not ts_str:
                            continue

                        ts = datetime.fromisoformat(ts_str.replace('Z', '+00:00')).timestamp()
                        if ts < cutoff_time:
                            continue

                        level = entry.get("level", "INFO")
                        name = entry.get("name", "")

                        if level == "ERROR":
                            issue_type = f"error_{name}" if name else "error_unknown"
                            issue_counts[issue_type]["count"] += 1
                            issue_counts[issue_type]["examples"].append(entry)

                        if name == "turn_done" and not entry.get("ok", True):
                            reason = entry.get("reason", "unknown")
                            if reason != "no_voice":
                                issue_type = f"turn_failed_{reason}"
                                issue_counts[issue_type]["count"] += 1
                                issue_counts[issue_type]["examples"].append(entry)

                        if "tool" in name and "error" in entry:
                            issue_type = "tool_call_failed"
                            issue_counts[issue_type]["count"] += 1
                            issue_counts[issue_type]["examples"].append(entry)

                        if name == "final_response":
                            response_text = entry.get("final_text", "")
                            if any(phrase in response_text.lower() for phrase in
                                   ["error", "failed", "unable", "could not", "cannot"]):
                                issue_type = "response_error_indicated"
                                issue_counts[issue_type]["count"] += 1
                                issue_counts[issue_type]["examples"].append(entry)

                    except (json.JSONDecodeError, ValueError):
                        continue

        except Exception as e:
            logger.warning(f"[chat_monitor] Error reading chat log: {e}")
            return issues

        for issue_type, data in issue_counts.items():
            if data["count"] >= self.chat_error_threshold:
                issues.append({
                    "issue_type": issue_type,
                    "count": data["count"],
                    "examples": data["examples"][:3]
                })

        return issues

    def _question_for_chat_issue(self, issue_info: Dict[str, Any]) -> Optional[CuriosityQuestion]:
        """Generate curiosity question from chat log issue pattern."""
        issue_type = issue_info["issue_type"]
        count = issue_info["count"]
        examples = issue_info.get("examples", [])

        if "error" in issue_type:
            action_class = ActionClass.PROPOSE_FIX
            hypothesis = f"CHAT_ERROR_{issue_type.upper()}"
            question = (
                f"Why are chat interactions experiencing {issue_type} errors? "
                f"This occurred {count} times in the last {self.lookback_minutes} minutes. "
                f"How can I improve conversation reliability?"
            )
            value_estimate = 0.85
        elif "tool_call_failed" in issue_type:
            action_class = ActionClass.PROPOSE_FIX
            hypothesis = "CHAT_TOOL_FAILURE"
            question = (
                f"Why are tool calls failing in chat interactions? "
                f"Detected {count} failures in the last {self.lookback_minutes} minutes. "
                f"How can I fix tool integration issues?"
            )
            value_estimate = 0.8
        elif "turn_failed" in issue_type:
            action_class = ActionClass.INVESTIGATE
            hypothesis = f"CHAT_TURN_FAILURE_{issue_type.split('_')[-1].upper()}"
            question = (
                f"Why are conversation turns failing with reason '{issue_type.split('_')[-1]}'? "
                f"This happened {count} times recently. "
                f"What's blocking successful interactions?"
            )
            value_estimate = 0.75
        elif "response_error" in issue_type:
            action_class = ActionClass.INVESTIGATE
            hypothesis = "CHAT_RESPONSE_QUALITY"
            question = (
                f"Why are {count} recent responses indicating errors or failures? "
                f"How can I improve response quality and error handling?"
            )
            value_estimate = 0.7
        else:
            action_class = ActionClass.INVESTIGATE
            hypothesis = f"CHAT_ISSUE_{issue_type.upper()}"
            question = (
                f"What's causing repeated {issue_type} issues in chat? "
                f"Detected {count} occurrences. "
                f"How should I address this pattern?"
            )
            value_estimate = 0.65

        evidence = [
            f"issue_type:{issue_type}",
            f"occurrences:{count}",
            f"timeframe:{self.lookback_minutes}min"
        ]

        if examples:
            first_example = examples[0]
            if "final_text" in first_example:
                evidence.append(f"example_response:{first_example['final_text'][:100]}")
            elif "reason" in first_example:
                evidence.append(f"example_reason:{first_example['reason']}")

        q = CuriosityQuestion(
            id=f"chat.{issue_type}.{hashlib.md5(issue_type.encode()).hexdigest()[:8]}",
            hypothesis=hypothesis,
            question=question,
            evidence=evidence,
            action_class=action_class,
            autonomy=3,
            value_estimate=value_estimate,
            cost=0.3,
            capability_key="conversation.quality"
        )

        return q

    def _find_similar_modules(self, missing_module: str) -> List[str]:
        """Find similar existing modules that could serve as templates."""
        similar = []

        if "spica_domain" in missing_module:
            domains_path = Path("/home/kloros/src/dream/phase/domains")
            if domains_path.exists():
                spica_modules = list(domains_path.glob("spica_*.py"))
                similar = [m.stem for m in spica_modules[:3]]

        return similar

    def _question_for_exception(self, exc: Dict[str, Any]) -> Optional[CuriosityQuestion]:
        """Generate curiosity question from exception details."""
        if exc["type"] == "ModuleNotFoundError":
            module = exc["module"]
            similar = exc["similar_modules"]

            hypothesis = f"MISSING_MODULE_{module.replace('.', '_').upper()}"

            if similar:
                question = (
                    f"How do I generate {module}.py using patterns from existing modules "
                    f"like {', '.join(similar)}?"
                )
                action_class = ActionClass.PROPOSE_FIX
                value = 0.9
                cost = 0.4
            else:
                question = f"What module or package provides {module}?"
                action_class = ActionClass.FIND_SUBSTITUTE
                value = 0.7
                cost = 0.3

            evidence = [
                f"error:{exc['type']}",
                f"module:{module}",
                f"context:{exc.get('context', 'unknown')}"
            ]

            if similar:
                evidence.append(f"similar_modules:{','.join(similar)}")

            return CuriosityQuestion(
                id=f"codegen.{module.replace('.', '_')}",
                hypothesis=hypothesis,
                question=question,
                evidence=evidence,
                action_class=action_class,
                autonomy=3,
                value_estimate=value,
                cost=cost,
                status=QuestionStatus.READY,
                capability_key=f"module.{module}"
            )

        elif exc["type"] == "ImportError":
            hypothesis = "IMPORT_ERROR"
            question = f"What dependency or configuration is missing? {exc['message']}"

            return CuriosityQuestion(
                id=f"import.{abs(hash(exc['message'])) % 100000}",
                hypothesis=hypothesis,
                question=question,
                evidence=[f"error:{exc['type']}", f"message:{exc['message']}"],
                action_class=ActionClass.INVESTIGATE,
                autonomy=3,
                value_estimate=0.6,
                cost=0.2,
                status=QuestionStatus.READY,
                capability_key="system.imports"
            )

        return None
