"""
Procedural memory system for KLoROS.

Tracks and learns patterns, skills, and procedures including:
- Tool/command usage patterns
- Workflow sequences
- Success rates
- Skill condensation
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from .models import Event, EventType
from .storage import MemoryStore

logger = logging.getLogger(__name__)


@dataclass
class ProceduralMemory:
    """A learned procedure or skill."""

    id: Optional[int] = None
    skill_id: str = ""  # Unique identifier
    pattern: str = ""  # Pattern description or sequence
    description: Optional[str] = None
    usage_count: int = 1
    last_used: float = 0.0
    success_rate: float = 1.0
    created_at: float = 0.0
    metadata: Dict[str, Any] = None

    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}


class ProceduralMemorySystem:
    """
    System for tracking and learning procedural knowledge.

    Features:
    - Pattern detection in event sequences
    - Tool/command usage tracking
    - Success rate calculation
    - Skill condensation
    """

    def __init__(self, store: Optional[MemoryStore] = None):
        """
        Initialize the procedural memory system.

        Args:
            store: Memory storage instance
        """
        self.store = store or MemoryStore()

        # Pattern detection thresholds
        self.min_pattern_frequency = 3  # Minimum occurrences to become a skill
        self.pattern_window_hours = 168  # Look back 7 days for patterns

    def detect_command_pattern(self, events: List[Event]) -> Optional[str]:
        """
        Detect command patterns in event sequence.

        Args:
            events: Sequential events to analyze

        Returns:
            Pattern string if detected, None otherwise
        """
        if len(events) < 2:
            return None

        # Extract meaningful content
        commands = []
        for event in events:
            # Look for command-like patterns
            content_lower = event.content.lower()

            # Common command patterns
            if any(keyword in content_lower for keyword in ["run", "execute", "start", "test", "build", "deploy"]):
                commands.append(content_lower)

        if len(commands) >= 2:
            # Create pattern hash
            pattern_str = " → ".join(commands[:5])  # Limit to 5 steps
            return pattern_str

        return None

    def record_pattern(
        self,
        pattern: str,
        description: Optional[str] = None,
        success: bool = True,
        metadata: Optional[Dict[str, Any]] = None
    ) -> ProceduralMemory:
        """
        Record a pattern occurrence.

        Args:
            pattern: Pattern string
            description: Human-readable description
            success: Whether the pattern execution succeeded
            metadata: Additional metadata

        Returns:
            The procedural memory object
        """
        # Generate skill ID from pattern
        skill_id = hashlib.md5(pattern.encode()).hexdigest()[:16]

        # Check if pattern already exists
        conn = self.store._get_connection()
        cursor = conn.execute(
            "SELECT * FROM procedural_memories WHERE skill_id = ?",
            (skill_id,)
        )
        row = cursor.fetchone()

        current_time = time.time()

        if row:
            # Update existing pattern
            usage_count = row['usage_count'] + 1
            old_success_rate = row['success_rate']
            old_count = row['usage_count']

            # Update success rate (weighted average)
            new_success = 1.0 if success else 0.0
            success_rate = (old_success_rate * old_count + new_success) / usage_count

            with self.store._transaction() as conn:
                conn.execute("""
                    UPDATE procedural_memories
                    SET usage_count = ?, last_used = ?, success_rate = ?
                    WHERE skill_id = ?
                """, (usage_count, current_time, success_rate, skill_id))

            return ProceduralMemory(
                id=row['id'],
                skill_id=skill_id,
                pattern=pattern,
                description=row['description'],
                usage_count=usage_count,
                last_used=current_time,
                success_rate=success_rate,
                created_at=row['created_at'],
                metadata=json.loads(row['metadata']) if row['metadata'] else {}
            )

        else:
            # Create new pattern
            success_rate = 1.0 if success else 0.0

            with self.store._transaction() as conn:
                cursor = conn.execute("""
                    INSERT INTO procedural_memories (
                        skill_id, pattern, description, usage_count,
                        last_used, success_rate, created_at, metadata
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    skill_id,
                    pattern,
                    description or pattern,
                    1,
                    current_time,
                    success_rate,
                    current_time,
                    json.dumps(metadata or {})
                ))

                new_id = cursor.lastrowid

            return ProceduralMemory(
                id=new_id,
                skill_id=skill_id,
                pattern=pattern,
                description=description or pattern,
                usage_count=1,
                last_used=current_time,
                success_rate=success_rate,
                created_at=current_time,
                metadata=metadata or {}
            )

    def get_frequent_patterns(
        self,
        min_usage: int = 3,
        limit: int = 20
    ) -> List[ProceduralMemory]:
        """
        Get frequently used patterns.

        Args:
            min_usage: Minimum usage count
            limit: Maximum patterns to return

        Returns:
            List of procedural memories
        """
        conn = self.store._get_connection()
        cursor = conn.execute("""
            SELECT * FROM procedural_memories
            WHERE usage_count >= ?
            ORDER BY usage_count DESC, success_rate DESC
            LIMIT ?
        """, (min_usage, limit))

        patterns = []
        for row in cursor.fetchall():
            patterns.append(ProceduralMemory(
                id=row['id'],
                skill_id=row['skill_id'],
                pattern=row['pattern'],
                description=row['description'],
                usage_count=row['usage_count'],
                last_used=row['last_used'],
                success_rate=row['success_rate'],
                created_at=row['created_at'],
                metadata=json.loads(row['metadata']) if row['metadata'] else {}
            ))

        return patterns

    def get_pattern_by_id(self, skill_id: str) -> Optional[ProceduralMemory]:
        """
        Get a specific pattern by skill ID.

        Args:
            skill_id: Skill identifier

        Returns:
            Procedural memory if found
        """
        conn = self.store._get_connection()
        cursor = conn.execute(
            "SELECT * FROM procedural_memories WHERE skill_id = ?",
            (skill_id,)
        )
        row = cursor.fetchone()

        if row:
            return ProceduralMemory(
                id=row['id'],
                skill_id=row['skill_id'],
                pattern=row['pattern'],
                description=row['description'],
                usage_count=row['usage_count'],
                last_used=row['last_used'],
                success_rate=row['success_rate'],
                created_at=row['created_at'],
                metadata=json.loads(row['metadata']) if row['metadata'] else {}
            )

        return None

    def suggest_next_step(self, current_pattern: str) -> Optional[str]:
        """
        Suggest next step based on learned patterns.

        Args:
            current_pattern: Current pattern/command

        Returns:
            Suggested next step, or None
        """
        # Find patterns that start with current pattern
        conn = self.store._get_connection()
        cursor = conn.execute("""
            SELECT pattern, usage_count, success_rate
            FROM procedural_memories
            WHERE pattern LIKE ?
            ORDER BY usage_count DESC, success_rate DESC
            LIMIT 1
        """, (f"%{current_pattern}%",))

        row = cursor.fetchone()

        if row:
            full_pattern = row['pattern']
            # Extract next step after current pattern
            if " → " in full_pattern:
                steps = full_pattern.split(" → ")
                for i, step in enumerate(steps):
                    if current_pattern.lower() in step.lower() and i < len(steps) - 1:
                        return steps[i + 1]

        return None

    def get_statistics(self) -> Dict[str, Any]:
        """
        Get procedural memory statistics.

        Returns:
            Dictionary with statistics
        """
        conn = self.store._get_connection()

        stats = {}

        # Total patterns
        cursor = conn.execute("SELECT COUNT(*) FROM procedural_memories")
        stats['total_patterns'] = cursor.fetchone()[0]

        # Most used pattern
        cursor = conn.execute("""
            SELECT pattern, usage_count FROM procedural_memories
            ORDER BY usage_count DESC LIMIT 1
        """)
        row = cursor.fetchone()
        if row:
            stats['most_used_pattern'] = {
                'pattern': row['pattern'],
                'usage_count': row['usage_count']
            }

        # Highest success rate
        cursor = conn.execute("""
            SELECT pattern, success_rate FROM procedural_memories
            WHERE usage_count >= 3
            ORDER BY success_rate DESC LIMIT 1
        """)
        row = cursor.fetchone()
        if row:
            stats['best_success_rate'] = {
                'pattern': row['pattern'],
                'success_rate': row['success_rate']
            }

        # Average success rate
        cursor = conn.execute("SELECT AVG(success_rate) FROM procedural_memories")
        avg_success = cursor.fetchone()[0]
        stats['avg_success_rate'] = avg_success if avg_success else 0.0

        return stats


# Global singleton
_procedural_system: Optional[ProceduralMemorySystem] = None


def get_procedural_system(store: Optional[MemoryStore] = None) -> ProceduralMemorySystem:
    """Get global procedural memory system instance."""
    global _procedural_system
    if _procedural_system is None:
        _procedural_system = ProceduralMemorySystem(store=store)
    return _procedural_system
