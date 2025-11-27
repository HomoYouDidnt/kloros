"""
Reflection log service for memory system.

Extracted from housekeeping.py - provides reflection log rotation,
archival, cleanup, and statistics reporting.

This service handles reflection log operations that were previously inline in
MemoryHousekeeper, centralizing reflection log maintenance logic.
"""

import logging
from typing import Any, Dict, Optional

from src.orchestration.core.umn_bus import UMNSub, UMNPub

logger = logging.getLogger(__name__)

try:
    from src.cognition.mind.memory.reflection_logs import ReflectionLogManager
    from src.cognition.mind.memory.logger import MemoryLogger
    from src.cognition.mind.memory.models import EventType
    HAS_MEMORY = True
except ImportError:
    HAS_MEMORY = False
    ReflectionLogManager = None
    MemoryLogger = None
    EventType = None


class ReflectionLogService:
    """
    Reflection log service for episodic memory system.

    Provides:
    - Log rotation when size exceeds limits
    - Archival of old entries
    - Compressed backup creation
    - Statistics and health reporting

    Can operate as UMN subscriber for agentic housekeeping architecture.
    """

    def __init__(self, memory_logger: Optional['MemoryLogger'] = None):
        """
        Initialize reflection log service.

        Args:
            memory_logger: Optional MemoryLogger for event tracking
        """
        self.memory_logger = memory_logger
        self._reflection_log_manager: Optional['ReflectionLogManager'] = None

        self._umn_sub: Optional[UMNSub] = None
        self._umn_pub: Optional[UMNPub] = None

    @property
    def reflection_log_manager(self) -> 'ReflectionLogManager':
        """Lazy-load reflection log manager."""
        if self._reflection_log_manager is None and HAS_MEMORY:
            self._reflection_log_manager = ReflectionLogManager(
                logger=self.memory_logger
            )
        return self._reflection_log_manager

    def subscribe_to_umn(self) -> None:
        """Subscribe to UMN for agentic housekeeping."""
        self._umn_pub = UMNPub()
        self._umn_sub = UMNSub(
            topic="Q_HOUSEKEEPING.REFLECTION",
            on_json=self._handle_reflection_request,
            zooid_name="reflection_log_service",
            niche="memory"
        )
        logger.info("[reflection_log] Subscribed to Q_HOUSEKEEPING.REFLECTION")

    def _handle_reflection_request(self, msg: dict) -> None:
        """Handle UMN request for reflection log cleanup."""
        request_id = msg.get('request_id', 'unknown')

        try:
            results = {}

            results['cleanup'] = self.cleanup_reflection_logs()
            results['stats'] = self.get_reflection_stats()

            self._umn_pub.emit(
                signal="Q_HOUSEKEEPING.REFLECTION.COMPLETE",
                ecosystem="memory",
                facts={
                    'request_id': request_id,
                    'success': True,
                    'results': results
                }
            )

        except Exception as e:
            logger.error(f"[reflection_log] Error during operation: {e}", exc_info=True)
            if self._umn_pub:
                self._umn_pub.emit(
                    signal="Q_HOUSEKEEPING.REFLECTION.COMPLETE",
                    ecosystem="memory",
                    facts={
                        'request_id': request_id,
                        'success': False,
                        'error': str(e)
                    }
                )

    def cleanup_reflection_logs(self) -> Dict[str, Any]:
        """
        Clean up reflection logs based on size and age limits.

        Performs:
        - Log rotation when size exceeds configured maximum
        - Archival of entries older than retention period
        - Compressed backup creation

        Returns:
            Dictionary with cleanup results
        """
        if not HAS_MEMORY or self.reflection_log_manager is None:
            logger.warning("[reflection_log] Reflection log manager not available")
            return {"error": "Service not available"}

        try:
            results = self.reflection_log_manager.cleanup()
            logger.info(f"[reflection_log] Cleanup completed: {results}")
            return results
        except Exception as e:
            logger.error(f"[reflection_log] Error during cleanup: {e}", exc_info=True)
            return {
                "error": str(e),
                "log_rotated": False,
                "entries_archived": 0,
                "bytes_freed": 0,
                "archive_files_created": 0,
                "errors": [str(e)]
            }

    def get_reflection_stats(self) -> Dict[str, Any]:
        """
        Get statistics about the reflection log system.

        Returns:
            Dictionary with reflection log statistics including:
            - Log file size and entry count
            - Oldest and newest entries
            - Archive information
        """
        if not HAS_MEMORY or self.reflection_log_manager is None:
            logger.warning("[reflection_log] Reflection log manager not available")
            return {"error": "Service not available"}

        try:
            stats = self.reflection_log_manager.get_stats()
            logger.info(f"[reflection_log] Stats retrieved: {stats}")
            return stats
        except Exception as e:
            logger.error(f"[reflection_log] Error retrieving stats: {e}", exc_info=True)
            return {
                "error": str(e),
                "log_exists": False,
                "log_size_bytes": 0,
                "log_size_mb": 0.0,
                "entry_count": 0,
                "archive_count": 0
            }

    def shutdown(self) -> None:
        """Close UMN subscriptions."""
        if self._umn_sub:
            self._umn_sub.close()
            logger.info("[reflection_log] Closed UMN subscription")
