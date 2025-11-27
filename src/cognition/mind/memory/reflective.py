"""
Reflective memory system for KLoROS.

Meta-cognitive insights and pattern recognition including:
- Pattern analysis across memory sectors
- Self-improvement suggestions
- Anomaly detection
- Performance insights
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from .storage import MemoryStore

logger = logging.getLogger(__name__)


@dataclass
class Reflection:
    """A meta-cognitive insight or pattern."""

    id: Optional[int] = None
    pattern_type: str = ""  # Type of pattern detected
    insight: str = ""  # The insight itself
    confidence: float = 0.5  # Confidence in this insight (0-1)
    evidence_count: int = 1  # Supporting evidence count
    created_at: float = 0.0
    last_observed: float = 0.0
    metadata: Dict[str, Any] = None

    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}


class ReflectiveSystem:
    """
    System for meta-cognitive analysis and self-reflection.

    Features:
    - Pattern detection across memory types
    - Insight generation
    - Self-improvement suggestions
    - Anomaly detection
    """

    def __init__(self, store: Optional[MemoryStore] = None):
        """Initialize the reflective system."""
        self.store = store or MemoryStore()

    def create_reflection(
        self,
        pattern_type: str,
        insight: str,
        confidence: float = 0.5,
        evidence_count: int = 1,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Reflection:
        """Create a new reflection."""
        current_time = time.time()

        with self.store._transaction() as conn:
            cursor = conn.execute("""
                INSERT INTO reflections (
                    pattern_type, insight, confidence, evidence_count,
                    created_at, last_observed, metadata
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                pattern_type,
                insight,
                confidence,
                evidence_count,
                current_time,
                current_time,
                json.dumps(metadata or {})
            ))

            reflection_id = cursor.lastrowid

        return Reflection(
            id=reflection_id,
            pattern_type=pattern_type,
            insight=insight,
            confidence=confidence,
            evidence_count=evidence_count,
            created_at=current_time,
            last_observed=current_time,
            metadata=metadata or {}
        )

    def get_reflections(
        self,
        pattern_type: Optional[str] = None,
        min_confidence: float = 0.3,
        limit: int = 20
    ) -> List[Reflection]:
        """Get reflections, optionally filtered."""
        query = "SELECT * FROM reflections WHERE confidence >= ?"
        params = [min_confidence]

        if pattern_type:
            query += " AND pattern_type = ?"
            params.append(pattern_type)

        query += " ORDER BY confidence DESC, last_observed DESC LIMIT ?"
        params.append(limit)

        conn = self.store._get_connection()
        cursor = conn.execute(query, params)

        reflections = []
        for row in cursor.fetchall():
            reflections.append(Reflection(
                id=row['id'],
                pattern_type=row['pattern_type'],
                insight=row['insight'],
                confidence=row['confidence'],
                evidence_count=row['evidence_count'],
                created_at=row['created_at'],
                last_observed=row['last_observed'],
                metadata=json.loads(row['metadata']) if row['metadata'] else {}
            ))

        return reflections

    def analyze_memory_patterns(self) -> List[Reflection]:
        """Analyze memory patterns and generate insights."""
        insights = []

        # Analyze event distribution
        conn = self.store._get_connection()

        # Check for high error rates
        cursor = conn.execute("""
            SELECT COUNT(*) as error_count FROM events
            WHERE event_type = 'error_occurred'
            AND timestamp > ?
        """, (time.time() - 86400,))  # Last 24 hours

        error_count = cursor.fetchone()['error_count']

        if error_count > 10:
            insights.append(self.create_reflection(
                pattern_type="error_rate",
                insight=f"High error rate detected: {error_count} errors in last 24 hours",
                confidence=0.9,
                evidence_count=error_count
            ))

        # Check for conversation length patterns
        cursor = conn.execute("""
            SELECT conversation_id, COUNT(*) as event_count
            FROM events
            WHERE conversation_id IS NOT NULL
            GROUP BY conversation_id
            HAVING COUNT(*) > 50
        """)

        long_conversations = cursor.fetchall()
        if len(long_conversations) > 3:
            insights.append(self.create_reflection(
                pattern_type="conversation_length",
                insight=f"Multiple long conversations detected ({len(long_conversations)} conversations > 50 events)",
                confidence=0.7,
                evidence_count=len(long_conversations)
            ))

        return insights


def get_reflective_system(store: Optional[MemoryStore] = None) -> ReflectiveSystem:
    """Get reflective system instance."""
    return ReflectiveSystem(store=store)
