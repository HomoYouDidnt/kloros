"""
Failure Pattern Analysis for KLoROS Reflection System.

Analyzes patterns in task failures to identify systematic issues and generate
actionable insights for improvement. Subscribes to affective failure signals
and maintains failure history in episodic memory.
"""

import json
import time
import logging
import traceback
from typing import List, Dict, Any, Optional
from datetime import datetime
from pathlib import Path

from ..config.reflection_config import ReflectionConfig


logger = logging.getLogger(__name__)


class FailurePatternAnalyzer:
    """
    Analyzes failure patterns to identify systematic issues.

    Examines recent error history to identify common failure modes,
    tools with high failure rates, and temporal clustering patterns.
    Generates actionable recommendations for preventive measures.
    """

    def __init__(self, config: Optional[ReflectionConfig] = None, memory_store=None):
        """
        Initialize failure pattern analyzer.

        Args:
            config: Optional reflection configuration
            memory_store: Optional MemoryStore instance for episodic storage
        """
        self.config = config or ReflectionConfig.from_environment()
        self.memory_store = memory_store
        self._failure_sub = None

    def _ensure_memory_store(self):
        """Lazy-initialize memory store if not provided."""
        if self.memory_store is not None:
            return

        try:
            from src.cognition.mind.memory.storage import MemoryStore
            self.memory_store = MemoryStore()
            logger.info("Initialized MemoryStore for failure analysis")
        except ImportError:
            try:
                from src.kloros_memory.storage import MemoryStore
                self.memory_store = MemoryStore()
                logger.info("Initialized MemoryStore for failure analysis (alt path)")
            except Exception as e:
                logger.warning(f"Could not initialize MemoryStore: {e}")
                self.memory_store = None

    def start_affective_subscription(self):
        """Subscribe to AFFECT_TASK_FAILURE_PATTERN for autonomous failure analysis."""
        from src.orchestration.core.umn_bus import UMNSub

        self._failure_sub = UMNSub(
            topic="AFFECT_TASK_FAILURE_PATTERN",
            on_json=self._on_failure_pattern,
            zooid_name="failure_analyzer",
            niche="reflection"
        )
        logger.info("Subscribed to AFFECT_TASK_FAILURE_PATTERN")

    def _on_failure_pattern(self, msg: Dict[str, Any]):
        """
        Handle AFFECT_TASK_FAILURE_PATTERN signal.

        Extracts root causes and actions from message facts and triggers analysis.

        Args:
            msg: UMN message with failure pattern signal
        """
        try:
            facts = msg.get('facts', {})
            root_causes = facts.get('root_causes', [])
            actions = facts.get('actions', [])

            logger.info(f"Received failure pattern signal: {len(root_causes)} root causes, {len(actions)} actions")

            self.analyze_failure_patterns(root_causes, actions)

        except Exception as e:
            logger.error(f"Error handling failure pattern signal: {e}")
            traceback.print_exc()

    def analyze_failure_patterns(self, root_causes: List[str], actions: List[str]) -> bool:
        """
        Analyze patterns in task failures to identify systematic issues.

        Triggered by AFFECT_TASK_FAILURE_PATTERN signals when task failures accumulate.
        Examines recent error history to identify common failure modes and suggest
        preventive measures for future improvement.

        Includes verification to ensure analysis results are persisted correctly.

        Args:
            root_causes: Root causes identified by affective introspection
            actions: Suggested autonomous actions from introspection

        Returns:
            True if analysis succeeded and verified
        """
        logger.info(f"Starting failure pattern analysis: {len(root_causes)} root causes, {len(actions)} actions")

        self._ensure_memory_store()

        try:
            recent_failures = self._get_recent_failures(days=7)

            if not recent_failures:
                logger.info("No recent failures to analyze")
                return True

            patterns = self._identify_patterns(recent_failures)
            insights = self._generate_insights(patterns, root_causes)
            event_id = self._store_failure_analysis(insights, root_causes, actions)

            if event_id and not isinstance(event_id, bool):
                verified = self._verify_episodic_storage(event_id)
                if verified:
                    logger.info(f"Analyzed {len(recent_failures)} failures, found {len(patterns.get('error_types', {}))} error types")
                    return True
                else:
                    logger.warning("Analysis stored but verification failed")
                    return False
            elif event_id is True:
                logger.info(f"Analyzed {len(recent_failures)} failures, found {len(patterns.get('error_types', {}))} error types")
                return True
            else:
                logger.error("Analysis failed to store")
                return False

        except Exception as e:
            logger.error(f"Failed to analyze failure patterns: {e}")
            traceback.print_exc()
            return False

    def _get_recent_failures(self, days: int = 7) -> List[Dict[str, Any]]:
        """
        Retrieve recent failure events from episodic memory.

        Args:
            days: Number of days back to retrieve failures

        Returns:
            List of failure event dictionaries
        """
        try:
            if not self.memory_store:
                return []

            cutoff_time = time.time() - (days * 24 * 3600)

            conn = self.memory_store._get_connection()
            cursor = conn.cursor()

            cursor.execute("""
                SELECT id, timestamp, content, metadata
                FROM events
                WHERE event_type IN ('error_occurred', 'tool_execution')
                AND timestamp >= ?
                AND (
                    event_type = 'error_occurred'
                    OR metadata LIKE '%"success": false%'
                    OR metadata LIKE '%"success":false%'
                )
                ORDER BY timestamp DESC
                LIMIT 100
            """, (cutoff_time,))

            failures = []
            for row in cursor.fetchall():
                event_id, timestamp, content, metadata_json = row

                try:
                    metadata = json.loads(metadata_json) if metadata_json else {}
                except:
                    metadata = {}

                failures.append({
                    'id': event_id,
                    'timestamp': timestamp,
                    'content': content,
                    'metadata': metadata,
                    'occurred_at': datetime.fromtimestamp(timestamp).isoformat()
                })

            return failures

        except Exception as e:
            logger.error(f"Error retrieving failures: {e}")
            return []

    def _identify_patterns(self, failures: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Identify common patterns in failures.

        Analyzes error types, timing, tools, and error messages to find patterns.

        Args:
            failures: List of failure event dictionaries

        Returns:
            Dictionary with identified patterns
        """
        patterns = {
            'error_types': {},
            'failure_times': [],
            'common_tools': {},
            'error_messages': {}
        }

        for failure in failures:
            error_type = failure.get('metadata', {}).get('error_type', 'unknown')
            patterns['error_types'][error_type] = patterns['error_types'].get(error_type, 0) + 1

            patterns['failure_times'].append(failure['timestamp'])

            tool = failure.get('metadata', {}).get('tool_name')
            if tool:
                patterns['common_tools'][tool] = patterns['common_tools'].get(tool, 0) + 1

            content = failure.get('content', '')
            if content:
                short_msg = content[:100]
                patterns['error_messages'][short_msg] = patterns['error_messages'].get(short_msg, 0) + 1

        return patterns

    def _generate_insights(self, patterns: Dict[str, Any], root_causes: List[str]) -> Dict[str, Any]:
        """
        Generate actionable insights from failure patterns.

        Identifies top failure modes and generates recommendations.

        Args:
            patterns: Dictionary of identified patterns
            root_causes: Root causes from affective introspection

        Returns:
            Dictionary with findings and recommendations
        """
        insights = {
            'timestamp': datetime.now().isoformat(),
            'root_causes': root_causes,
            'findings': [],
            'recommendations': []
        }

        if patterns['error_types']:
            most_common = max(patterns['error_types'].items(), key=lambda x: x[1])
            insights['findings'].append(f"Most common error: {most_common[0]} ({most_common[1]} occurrences)")
            insights['recommendations'].append(f"Investigate root cause of {most_common[0]} errors")

        if patterns['common_tools']:
            failing_tools = sorted(patterns['common_tools'].items(), key=lambda x: x[1], reverse=True)[:3]
            for tool, count in failing_tools:
                insights['findings'].append(f"Tool '{tool}' failed {count} times")
                insights['recommendations'].append(f"Review {tool} implementation or usage patterns")

        if len(patterns['failure_times']) >= 3:
            time_range = max(patterns['failure_times']) - min(patterns['failure_times'])
            if time_range < 3600:
                insights['findings'].append("Failures clustered in short time window")
                insights['recommendations'].append("Investigate recent system changes or external dependencies")

        return insights

    def _store_failure_analysis(self, insights: Dict[str, Any], root_causes: List[str], actions: List[str]) -> Any:
        """
        Store failure analysis to episodic memory.

        Persists analysis for future reference and learning.

        Args:
            insights: Analysis insights dictionary
            root_causes: Original root causes
            actions: Original suggested actions

        Returns:
            Event ID if storage succeeded, False if failed
        """
        try:
            if not self.memory_store:
                return False

            try:
                from src.cognition.mind.memory.models import Event, EventType
            except ImportError:
                from src.kloros_memory.models import Event, EventType

            findings_text = "; ".join(insights['findings'][:3])

            metadata = {
                'root_causes': root_causes,
                'suggested_actions': actions,
                'findings': insights['findings'],
                'recommendations': insights['recommendations'],
                'timestamp': insights['timestamp']
            }

            event = Event(
                timestamp=time.time(),
                event_type=EventType.SELF_REFLECTION,
                content=f"Failure pattern analysis: {findings_text}",
                metadata=metadata,
                conversation_id=None
            )

            event_id = self.memory_store.store_event(event)
            logger.info(f"Stored analysis to episodic memory (event_id: {event_id})")
            return event_id if event_id is not None else False

        except Exception as e:
            logger.error(f"Failed to store analysis: {e}")
            return False

    def _verify_episodic_storage(self, event_id: Optional[int]) -> bool:
        """
        Verify event was successfully stored to episodic memory.

        Checks that the event exists in the database after storage attempt.

        Args:
            event_id: Event ID returned from store_event()

        Returns:
            True if event verified in database, False otherwise
        """
        if event_id is None:
            logger.warning("Storage returned None event_id")
            return False

        if not self.memory_store:
            logger.warning("Memory store unavailable")
            return False

        try:
            conn = self.memory_store._get_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT id FROM events WHERE id = ?", (event_id,))
            result = cursor.fetchone()

            if result:
                logger.info(f"Verified: Event {event_id} exists in episodic memory")
                return True
            else:
                logger.warning(f"Event {event_id} not found in database after storage")
                return False

        except Exception as e:
            logger.warning(f"Verification failed: {e}")
            return False
