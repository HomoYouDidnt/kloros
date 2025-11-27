"""
Database maintenance service for memory system.

Extracted from housekeeping.py - provides database integrity validation,
repair operations, and comprehensive statistics.

This service handles SQL operations that were previously inline in
MemoryHousekeeper, centralizing database maintenance logic.
"""

import json
import time
import logging
from typing import Any, Dict, List, Optional

from src.orchestration.core.umn_bus import UMNSub, UMNPub

logger = logging.getLogger(__name__)

try:
    from src.cognition.mind.memory.storage import MemoryStore
    from src.cognition.mind.memory.logger import MemoryLogger
    from src.cognition.mind.memory.models import EventType
    HAS_MEMORY = True
except ImportError:
    HAS_MEMORY = False
    MemoryStore = None
    MemoryLogger = None
    EventType = None


class DatabaseMaintenanceService:
    """
    Database maintenance service for episodic memory system.

    Provides:
    - Data integrity validation (missing summaries, orphans, invalid timestamps)
    - Data repair operations (fix integrity issues)
    - Comprehensive statistics and analytics

    Can operate as UMN subscriber for agentic housekeeping architecture.
    """

    def __init__(self, memory_logger: Optional['MemoryLogger'] = None):
        """
        Initialize database maintenance service.

        Args:
            memory_logger: Optional MemoryLogger for event tracking
        """
        self.memory_logger = memory_logger
        self._store: Optional['MemoryStore'] = None

        self._umn_sub: Optional[UMNSub] = None
        self._umn_pub: Optional[UMNPub] = None

    @property
    def store(self) -> 'MemoryStore':
        """Lazy-load memory store."""
        if self._store is None and HAS_MEMORY:
            self._store = MemoryStore()
        return self._store

    def subscribe_to_umn(self) -> None:
        """Subscribe to UMN for agentic housekeeping."""
        self._umn_pub = UMNPub()
        self._umn_sub = UMNSub(
            topic="Q_HOUSEKEEPING.DATABASE",
            on_json=self._handle_database_request,
            zooid_name="database_maintenance_service",
            niche="memory"
        )
        logger.info("[database_maintenance] Subscribed to Q_HOUSEKEEPING.DATABASE")

    def _handle_database_request(self, msg: dict) -> None:
        """Handle UMN request for database maintenance."""
        request_id = msg.get('request_id', 'unknown')
        operation = msg.get('facts', {}).get('operation', 'full')

        try:
            results = {}

            if operation in ('full', 'validate'):
                results['integrity_issues'] = self.validate_data_integrity()

            if operation in ('full', 'fix'):
                results['fixes_applied'] = self.fix_integrity_issues()

            if operation in ('full', 'stats'):
                results['statistics'] = self.get_comprehensive_stats()

            self._umn_pub.emit(
                signal="Q_HOUSEKEEPING.DATABASE.COMPLETE",
                ecosystem="memory",
                facts={
                    'request_id': request_id,
                    'success': True,
                    'results': results
                }
            )

        except Exception as e:
            logger.error(f"[database_maintenance] Error during operation: {e}", exc_info=True)
            if self._umn_pub:
                self._umn_pub.emit(
                    signal="Q_HOUSEKEEPING.DATABASE.COMPLETE",
                    ecosystem="memory",
                    facts={
                        'request_id': request_id,
                        'success': False,
                        'error': str(e)
                    }
                )

    def validate_data_integrity(self) -> List[Dict[str, Any]]:
        """
        Validate data integrity of the memory database.

        Checks for:
        - Condensed episodes missing summaries
        - Orphaned summaries without parent episodes
        - Old uncondensed episodes (> 7 days)
        - Events with invalid timestamps

        Returns:
            List of integrity issues found, each as dict with type, count, description
        """
        if not HAS_MEMORY or self.store is None:
            logger.warning("[database_maintenance] Memory system not available")
            return []

        issues = []

        try:
            conn = self.store._get_connection()
            cursor = conn.cursor()

            cursor.execute("""
                SELECT COUNT(*) as count
                FROM episodes
                WHERE is_condensed = 1
                AND id NOT IN (SELECT episode_id FROM episode_summaries)
            """)
            result = cursor.fetchone()
            missing_summaries = result[0] if result else 0

            if missing_summaries > 0:
                issues.append({
                    "type": "missing_summaries",
                    "count": missing_summaries,
                    "description": f"{missing_summaries} condensed episodes are missing their summaries"
                })

            cursor.execute("""
                SELECT COUNT(*) as count
                FROM episode_summaries
                WHERE episode_id NOT IN (SELECT id FROM episodes)
            """)
            result = cursor.fetchone()
            orphaned_summaries = result[0] if result else 0

            if orphaned_summaries > 0:
                issues.append({
                    "type": "orphaned_summaries",
                    "count": orphaned_summaries,
                    "description": f"{orphaned_summaries} summaries reference non-existent episodes"
                })

            seven_days_ago = time.time() - (7 * 86400)
            cursor.execute("""
                SELECT COUNT(*) as count
                FROM episodes
                WHERE is_condensed = 0
                AND start_time < ?
            """, (seven_days_ago,))
            result = cursor.fetchone()
            old_uncondensed = result[0] if result else 0

            if old_uncondensed > 0:
                issues.append({
                    "type": "old_uncondensed",
                    "count": old_uncondensed,
                    "description": f"{old_uncondensed} episodes older than 7 days haven't been condensed"
                })

            future_threshold = time.time() + 86400
            cursor.execute("""
                SELECT COUNT(*) as count
                FROM events
                WHERE timestamp < 0 OR timestamp > ?
            """, (future_threshold,))
            result = cursor.fetchone()
            invalid_timestamps = result[0] if result else 0

            if invalid_timestamps > 0:
                issues.append({
                    "type": "invalid_timestamps",
                    "count": invalid_timestamps,
                    "description": f"{invalid_timestamps} events have invalid timestamps"
                })

        except Exception as e:
            logger.error(f"[database_maintenance] Error validating integrity: {e}", exc_info=True)
            issues.append({
                "type": "validation_error",
                "count": 1,
                "description": f"Error during validation: {str(e)}"
            })

        return issues

    def fix_integrity_issues(self) -> Dict[str, int]:
        """
        Fix detected integrity issues in the database.

        Operations:
        - Reset condensed flag for episodes missing summaries
        - Delete orphaned summaries
        - Delete events with invalid timestamps

        Returns:
            Dict with counts of fixes applied per category
        """
        if not HAS_MEMORY or self.store is None:
            logger.warning("[database_maintenance] Memory system not available")
            return {}

        fixes = {
            "missing_summaries_fixed": 0,
            "orphaned_summaries_removed": 0,
            "invalid_events_removed": 0
        }

        try:
            conn = self.store._get_connection()
            cursor = conn.cursor()

            cursor.execute("""
                UPDATE episodes
                SET is_condensed = 0, condensed_at = NULL
                WHERE is_condensed = 1
                AND id NOT IN (SELECT episode_id FROM episode_summaries)
            """)
            fixes["missing_summaries_fixed"] = cursor.rowcount

            cursor.execute("""
                DELETE FROM episode_summaries
                WHERE episode_id NOT IN (SELECT id FROM episodes)
            """)
            fixes["orphaned_summaries_removed"] = cursor.rowcount

            future_threshold = time.time() + 86400
            cursor.execute("""
                DELETE FROM events
                WHERE timestamp < 0 OR timestamp > ?
            """, (future_threshold,))
            fixes["invalid_events_removed"] = cursor.rowcount

            conn.commit()

            if self.memory_logger and HAS_MEMORY:
                total_fixes = sum(fixes.values())
                if total_fixes > 0:
                    self.memory_logger.log_event(
                        event_type=EventType.MEMORY_HOUSEKEEPING,
                        content=f"Fixed {total_fixes} database integrity issues",
                        metadata=fixes
                    )

            logger.info(f"[database_maintenance] Fixed integrity issues: {fixes}")

        except Exception as e:
            logger.error(f"[database_maintenance] Error fixing integrity: {e}", exc_info=True)
            conn.rollback()

        return fixes

    def get_comprehensive_stats(
        self,
        last_vacuum: Optional[float] = None,
        last_cleanup: Optional[float] = None,
        last_condensation: Optional[float] = None
    ) -> Dict[str, Any]:
        """
        Get comprehensive statistics about the memory database.

        Args:
            last_vacuum: Timestamp of last vacuum operation
            last_cleanup: Timestamp of last cleanup operation
            last_condensation: Timestamp of last condensation

        Returns:
            Dict with statistics including base stats, analytics, and maintenance status
        """
        if not HAS_MEMORY or self.store is None:
            logger.warning("[database_maintenance] Memory system not available")
            return {}

        try:
            stats = self.store.get_stats()

            conn = self.store._get_connection()
            cursor = conn.cursor()

            twenty_four_hours_ago = time.time() - 86400
            cursor.execute("""
                SELECT event_type, COUNT(*) as count
                FROM events
                WHERE timestamp >= ?
                GROUP BY event_type
                ORDER BY count DESC
            """, (twenty_four_hours_ago,))
            events_24h = {row[0]: row[1] for row in cursor.fetchall()}
            stats["events_24h_by_type"] = events_24h

            seven_days_ago = time.time() - (7 * 86400)
            cursor.execute("""
                SELECT AVG(event_count) as avg_length
                FROM episodes
                WHERE start_time >= ?
            """, (seven_days_ago,))
            result = cursor.fetchone()
            stats["avg_conversation_length"] = result[0] if result and result[0] else 0

            cursor.execute("""
                SELECT key_topics, COUNT(*) as count
                FROM episode_summaries
                WHERE created_at >= ?
                AND key_topics != '[]'
                GROUP BY key_topics
                ORDER BY count DESC
                LIMIT 10
            """, (seven_days_ago,))

            topic_counts = {}
            for row in cursor.fetchall():
                try:
                    topics = json.loads(row[0]) if row[0] else []
                    for topic in topics:
                        topic_counts[topic] = topic_counts.get(topic, 0) + row[1]
                except (json.JSONDecodeError, TypeError):
                    continue

            sorted_topics = sorted(topic_counts.items(), key=lambda x: x[1], reverse=True)[:10]
            stats["top_topics_week"] = dict(sorted_topics)

            total_events = stats.get("total_events", 0)
            total_summaries = stats.get("total_summaries", 0)
            stats["summarization_ratio"] = total_summaries / total_events if total_events > 0 else 0

            current_time = time.time()
            stats["maintenance_status"] = {
                "last_vacuum": last_vacuum,
                "last_cleanup": last_cleanup,
                "last_condensation": last_condensation,
                "vacuum_age_hours": (current_time - last_vacuum) / 3600 if last_vacuum else None,
                "cleanup_age_hours": (current_time - last_cleanup) / 3600 if last_cleanup else None,
                "condensation_age_hours": (current_time - last_condensation) / 3600 if last_condensation else None
            }

            return stats

        except Exception as e:
            logger.error(f"[database_maintenance] Error getting stats: {e}", exc_info=True)
            return {"error": str(e)}

    def shutdown(self) -> None:
        """Close UMN subscriptions."""
        if self._umn_sub:
            self._umn_sub.close()
            logger.info("[database_maintenance] Closed UMN subscription")
