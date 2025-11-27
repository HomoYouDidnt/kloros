"""
Vector export service for memory system.

Extracted from housekeeping.py - provides vector database export operations
for Qdrant/ChromaDB via QdrantMemoryExporter.

This service handles vector export operations that were previously inline in
MemoryHousekeeper, centralizing vector database operations.
"""

import json
import logging
from typing import Any, Dict, Optional
from datetime import datetime

from src.orchestration.core.umn_bus import UMNSub, UMNPub

logger = logging.getLogger(__name__)

try:
    from src.cognition.mind.memory.storage import MemoryStore
    from src.cognition.mind.memory.logger import MemoryLogger
    from src.cognition.mind.memory.models import EventType
    from src.cognition.mind.memory.qdrant_export import QdrantMemoryExporter
    HAS_MEMORY = True
except ImportError:
    HAS_MEMORY = False
    MemoryStore = None
    MemoryLogger = None
    EventType = None
    QdrantMemoryExporter = None


class VectorExportService:
    """
    Vector export service for episodic memory system.

    Provides:
    - Export of recent summaries to vector databases (Qdrant/ChromaDB)
    - Daily and weekly rollup creation for vector search
    - Vector database statistics and status

    Can operate as UMN subscriber for agentic housekeeping architecture.
    """

    def __init__(self, memory_logger: Optional['MemoryLogger'] = None):
        """
        Initialize vector export service.

        Args:
            memory_logger: Optional MemoryLogger for event tracking
        """
        self.memory_logger = memory_logger
        self._store: Optional['MemoryStore'] = None
        self._exporter: Optional['QdrantMemoryExporter'] = None

        self._umn_sub: Optional[UMNSub] = None
        self._umn_pub: Optional[UMNPub] = None

    @property
    def store(self) -> 'MemoryStore':
        """Lazy-load memory store."""
        if self._store is None and HAS_MEMORY:
            self._store = MemoryStore()
        return self._store

    @property
    def exporter(self) -> Optional['QdrantMemoryExporter']:
        """Lazy-load Qdrant memory exporter."""
        if self._exporter is None and HAS_MEMORY:
            try:
                if QdrantMemoryExporter is None:
                    logger.warning("[vector_export] QdrantMemoryExporter not available")
                    return None

                self._exporter = QdrantMemoryExporter(self.store)
                logger.info("[vector_export] Lazy-loaded QdrantMemoryExporter")
            except Exception as e:
                logger.error(f"[vector_export] Failed to initialize QdrantMemoryExporter: {e}")
                self._exporter = None

        return self._exporter

    def subscribe_to_umn(self) -> None:
        """Subscribe to UMN for agentic housekeeping."""
        self._umn_pub = UMNPub()
        self._umn_sub = UMNSub(
            topic="Q_HOUSEKEEPING.VECTOR_EXPORT",
            on_json=self._handle_vector_export_request,
            zooid_name="vector_export_service",
            niche="memory"
        )
        logger.info("[vector_export] Subscribed to Q_HOUSEKEEPING.VECTOR_EXPORT")

    def _handle_vector_export_request(self, msg: dict) -> None:
        """Handle UMN request for vector export operations."""
        request_id = msg.get('request_id', 'unknown')
        operation = msg.get('facts', {}).get('operation', 'full')

        try:
            results = {}

            if operation in ('full', 'export_recent'):
                export_result = self.export_recent_summaries()
                results['export_recent'] = export_result

            if operation in ('full', 'daily_rollup'):
                daily_result = self.create_daily_rollup()
                results['daily_rollup'] = daily_result

            if operation in ('full', 'weekly_rollup'):
                weekly_result = self.create_weekly_rollup()
                results['weekly_rollup'] = weekly_result

            if operation in ('full', 'stats'):
                stats_result = self.get_vector_export_stats()
                results['stats'] = stats_result

            self._umn_pub.emit(
                signal="Q_HOUSEKEEPING.VECTOR_EXPORT.COMPLETE",
                ecosystem="memory",
                facts={
                    'request_id': request_id,
                    'success': True,
                    'results': results
                }
            )

        except Exception as e:
            logger.error(f"[vector_export] Error during operation: {e}", exc_info=True)
            if self._umn_pub:
                self._umn_pub.emit(
                    signal="Q_HOUSEKEEPING.VECTOR_EXPORT.COMPLETE",
                    ecosystem="memory",
                    facts={
                        'request_id': request_id,
                        'success': False,
                        'error': str(e)
                    }
                )

    def export_recent_summaries(
        self,
        hours: float = 24.0,
        min_importance: float = 0.3
    ) -> Dict[str, Any]:
        """
        Export recent episode summaries to Qdrant.

        Args:
            hours: Time window for recent summaries
            min_importance: Minimum importance score to export

        Returns:
            Dictionary with export results
        """
        if not HAS_MEMORY:
            logger.warning("[vector_export] Memory system not available")
            return {"error": "Memory system not available"}

        if self.exporter is None:
            logger.warning("[vector_export] QdrantMemoryExporter not initialized")
            return {"error": "Qdrant exporter not initialized"}

        try:
            result = self.exporter.export_recent_summaries(
                hours=hours,
                min_importance=min_importance
            )

            if self.memory_logger:
                self.memory_logger.log_event(
                    event_type=EventType.MEMORY_HOUSEKEEPING,
                    content=f"Exported recent summaries: {result.get('exported', 0)} exported, {result.get('skipped', 0)} skipped",
                    metadata=result
                )

            logger.info(f"[vector_export] Exported recent summaries: {result}")
            return result

        except Exception as e:
            logger.error(f"[vector_export] Error exporting recent summaries: {e}", exc_info=True)
            return {"error": str(e), "exported": 0, "skipped": 0, "errors": [str(e)]}

    def create_daily_rollup(self, date: Optional[datetime] = None) -> Dict[str, Any]:
        """
        Create daily rollup of episode summaries.

        Args:
            date: Date to rollup (default: yesterday)

        Returns:
            Dictionary with rollup results
        """
        if not HAS_MEMORY:
            logger.warning("[vector_export] Memory system not available")
            return {"error": "Memory system not available"}

        if self.exporter is None:
            logger.warning("[vector_export] QdrantMemoryExporter not initialized")
            return {"error": "Qdrant exporter not initialized"}

        try:
            result = self.exporter.create_daily_rollup(date=date)

            if result.get('rollup_created') and self.memory_logger:
                self.memory_logger.log_event(
                    event_type=EventType.MEMORY_HOUSEKEEPING,
                    content=f"Created daily rollup: {result.get('summaries_included', 0)} summaries included",
                    metadata=result
                )

            logger.info(f"[vector_export] Daily rollup created: {result}")
            return result

        except Exception as e:
            logger.error(f"[vector_export] Error creating daily rollup: {e}", exc_info=True)
            return {"error": str(e), "rollup_created": False, "summaries_included": 0, "errors": [str(e)]}

    def create_weekly_rollup(self, week_start: Optional[datetime] = None) -> Dict[str, Any]:
        """
        Create weekly rollup of daily rollups.

        Args:
            week_start: Start of week to rollup (default: last week)

        Returns:
            Dictionary with rollup results
        """
        if not HAS_MEMORY:
            logger.warning("[vector_export] Memory system not available")
            return {"error": "Memory system not available"}

        if self.exporter is None:
            logger.warning("[vector_export] QdrantMemoryExporter not initialized")
            return {"error": "Qdrant exporter not initialized"}

        try:
            result = self.exporter.create_weekly_rollup(week_start=week_start)

            if result.get('rollup_created') and self.memory_logger:
                self.memory_logger.log_event(
                    event_type=EventType.MEMORY_HOUSEKEEPING,
                    content=f"Created weekly rollup: {result.get('days_included', 0)} days included",
                    metadata=result
                )

            logger.info(f"[vector_export] Weekly rollup created: {result}")
            return result

        except Exception as e:
            logger.error(f"[vector_export] Error creating weekly rollup: {e}", exc_info=True)
            return {"error": str(e), "rollup_created": False, "days_included": 0, "errors": [str(e)]}

    def get_vector_export_stats(self) -> Dict[str, Any]:
        """
        Get vector export statistics.

        Returns:
            Dictionary with statistics including Qdrant collection info
        """
        if not HAS_MEMORY:
            logger.warning("[vector_export] Memory system not available")
            return {"error": "Memory system not available"}

        if self.exporter is None:
            logger.warning("[vector_export] QdrantMemoryExporter not initialized")
            return {"error": "Qdrant exporter not initialized"}

        try:
            stats = self.exporter.get_stats()
            logger.info(f"[vector_export] Retrieved vector export stats: {stats}")
            return stats

        except Exception as e:
            logger.error(f"[vector_export] Error getting stats: {e}", exc_info=True)
            return {"error": str(e)}

    def shutdown(self) -> None:
        """Close UMN subscriptions."""
        if self._umn_sub:
            self._umn_sub.close()
            logger.info("[vector_export] Closed UMN subscription")
