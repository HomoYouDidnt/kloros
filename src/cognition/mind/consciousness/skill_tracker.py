#!/usr/bin/env python3
"""
Skill Effectiveness Tracker - Learn which skills solve which problems.

Tracks skill execution history, outcomes, and effectiveness to enable
autonomous learning and continuous improvement.
"""

import json
import logging
import sqlite3
import time
from pathlib import Path
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


@dataclass
class SkillExecution:
    """Record of a single skill execution."""
    execution_id: str
    skill_name: str
    problem_type: str
    problem_description: str
    phase: str
    actions_count: int
    confidence: float
    timestamp: float

    # Outcome tracking
    outcome: Optional[str] = None  # "success", "partial", "failed", "unknown"
    metrics_before: Optional[Dict[str, float]] = None
    metrics_after: Optional[Dict[str, float]] = None
    improvement: Optional[float] = None  # 0.0 to 1.0
    execution_time_s: Optional[float] = None
    notes: Optional[str] = None


class SkillTracker:
    """
    Tracks skill execution history and effectiveness.

    Enables KLoROS to learn which skills work best for which problems,
    building autonomous expertise over time.
    """

    def __init__(self, db_path: Optional[Path] = None):
        """
        Initialize skill tracker.

        Args:
            db_path: Path to SQLite database (defaults to ~/.kloros/skill_tracker.db)
        """
        if db_path is None:
            db_path = Path.home() / ".kloros" / "skill_tracker.db"

        db_path.parent.mkdir(parents=True, exist_ok=True)
        self.db_path = db_path
        self.conn = sqlite3.connect(str(db_path))
        self._init_database()

        logger.info(f"[skill_tracker] Initialized with database: {db_path}")

    def _init_database(self):
        """Initialize database schema."""
        cursor = self.conn.cursor()

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS skill_executions (
                execution_id TEXT PRIMARY KEY,
                skill_name TEXT NOT NULL,
                problem_type TEXT NOT NULL,
                problem_description TEXT,
                phase TEXT,
                actions_count INTEGER,
                confidence REAL,
                timestamp REAL,
                outcome TEXT,
                metrics_before TEXT,
                metrics_after TEXT,
                improvement REAL,
                execution_time_s REAL,
                notes TEXT
            )
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_skill_name
            ON skill_executions(skill_name)
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_problem_type
            ON skill_executions(problem_type)
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_outcome
            ON skill_executions(outcome)
        """)

        self.conn.commit()

    def record_execution(self, execution: SkillExecution) -> bool:
        """
        Record a skill execution.

        Args:
            execution: SkillExecution record

        Returns:
            True if recorded successfully
        """
        try:
            cursor = self.conn.cursor()

            cursor.execute("""
                INSERT INTO skill_executions VALUES (
                    ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
                )
            """, (
                execution.execution_id,
                execution.skill_name,
                execution.problem_type,
                execution.problem_description,
                execution.phase,
                execution.actions_count,
                execution.confidence,
                execution.timestamp,
                execution.outcome,
                json.dumps(execution.metrics_before) if execution.metrics_before else None,
                json.dumps(execution.metrics_after) if execution.metrics_after else None,
                execution.improvement,
                execution.execution_time_s,
                execution.notes
            ))

            self.conn.commit()
            logger.info(f"[skill_tracker] Recorded execution: {execution.execution_id}")
            return True

        except Exception as e:
            logger.error(f"[skill_tracker] Failed to record execution: {e}", exc_info=True)
            return False

    def update_outcome(
        self,
        execution_id: str,
        outcome: str,
        metrics_after: Dict[str, float],
        notes: Optional[str] = None
    ) -> bool:
        """
        Update execution outcome after validation.

        Args:
            execution_id: Execution ID
            outcome: "success", "partial", "failed", "unknown"
            metrics_after: System metrics after execution
            notes: Optional notes

        Returns:
            True if updated successfully
        """
        try:
            cursor = self.conn.cursor()

            # Get metrics_before
            cursor.execute(
                "SELECT metrics_before FROM skill_executions WHERE execution_id = ?",
                (execution_id,)
            )
            row = cursor.fetchone()

            if not row or not row[0]:
                logger.warning(f"[skill_tracker] No metrics_before for {execution_id}")
                improvement = None
            else:
                metrics_before = json.loads(row[0])
                improvement = self._calculate_improvement(metrics_before, metrics_after)

            cursor.execute("""
                UPDATE skill_executions
                SET outcome = ?,
                    metrics_after = ?,
                    improvement = ?,
                    notes = ?
                WHERE execution_id = ?
            """, (
                outcome,
                json.dumps(metrics_after),
                improvement,
                notes,
                execution_id
            ))

            self.conn.commit()
            logger.info(f"[skill_tracker] Updated outcome for {execution_id}: {outcome} (improvement: {improvement})")
            return True

        except Exception as e:
            logger.error(f"[skill_tracker] Failed to update outcome: {e}", exc_info=True)
            return False

    def _calculate_improvement(
        self,
        metrics_before: Dict[str, float],
        metrics_after: Dict[str, float]
    ) -> float:
        """
        Calculate improvement score (0.0 to 1.0).

        Higher is better. Looks at key metrics:
        - Swap usage (lower is better)
        - Memory usage (lower is better)
        - Thread count (lower is better)
        - Investigation failure rate (lower is better)

        Args:
            metrics_before: Metrics before execution
            metrics_after: Metrics after execution

        Returns:
            Improvement score (0.0 = worse, 0.5 = no change, 1.0 = perfect)
        """
        improvements = []

        # Swap (lower is better)
        if 'swap_used_mb' in metrics_before and 'swap_used_mb' in metrics_after:
            before = metrics_before['swap_used_mb']
            after = metrics_after['swap_used_mb']
            if before > 0:
                reduction = (before - after) / before
                improvements.append(min(max(reduction, -1.0), 1.0))

        # Memory (lower is better)
        if 'memory_used_pct' in metrics_before and 'memory_used_pct' in metrics_after:
            before = metrics_before['memory_used_pct']
            after = metrics_after['memory_used_pct']
            if before > 0:
                reduction = (before - after) / before
                improvements.append(min(max(reduction, -1.0), 1.0))

        # Thread count (lower is better)
        if 'thread_count' in metrics_before and 'thread_count' in metrics_after:
            before = metrics_before['thread_count']
            after = metrics_after['thread_count']
            if before > 0:
                reduction = (before - after) / before
                improvements.append(min(max(reduction, -1.0), 1.0))

        if not improvements:
            return 0.5  # No change

        # Average improvement, scaled to 0-1 (0.5 = no change)
        avg = sum(improvements) / len(improvements)
        return (avg + 1.0) / 2.0  # Convert from [-1, 1] to [0, 1]

    def get_skill_effectiveness(
        self,
        skill_name: str,
        problem_type: Optional[str] = None,
        days: int = 30
    ) -> Dict[str, Any]:
        """
        Get effectiveness stats for a skill.

        Args:
            skill_name: Skill name
            problem_type: Optional filter by problem type
            days: Look back this many days

        Returns:
            Statistics dict
        """
        cursor = self.conn.cursor()

        cutoff = time.time() - (days * 86400)

        query = """
            SELECT
                COUNT(*) as total,
                AVG(confidence) as avg_confidence,
                AVG(improvement) as avg_improvement,
                SUM(CASE WHEN outcome = 'success' THEN 1 ELSE 0 END) as successes,
                SUM(CASE WHEN outcome = 'partial' THEN 1 ELSE 0 END) as partials,
                SUM(CASE WHEN outcome = 'failed' THEN 1 ELSE 0 END) as failures,
                AVG(execution_time_s) as avg_time
            FROM skill_executions
            WHERE skill_name = ?
              AND timestamp > ?
        """

        params = [skill_name, cutoff]

        if problem_type:
            query += " AND problem_type = ?"
            params.append(problem_type)

        cursor.execute(query, params)
        row = cursor.fetchone()

        if not row or row[0] == 0:
            return {
                'skill_name': skill_name,
                'total_executions': 0,
                'success_rate': 0.0,
                'avg_improvement': 0.0,
                'avg_confidence': 0.0
            }

        total, avg_conf, avg_imp, successes, partials, failures, avg_time = row

        completed = successes + partials + failures
        success_rate = successes / completed if completed > 0 else 0.0

        return {
            'skill_name': skill_name,
            'problem_type': problem_type,
            'total_executions': total,
            'success_rate': success_rate,
            'avg_improvement': avg_imp or 0.0,
            'avg_confidence': avg_conf or 0.0,
            'avg_execution_time_s': avg_time or 0.0,
            'successes': successes,
            'partials': partials,
            'failures': failures,
            'unknown': total - completed
        }

    def get_best_skill_for_problem(
        self,
        problem_type: str,
        min_executions: int = 3
    ) -> Optional[str]:
        """
        Find best skill for a problem type based on historical success.

        Args:
            problem_type: Problem type
            min_executions: Minimum executions required

        Returns:
            Best skill name or None
        """
        cursor = self.conn.cursor()

        cursor.execute("""
            SELECT
                skill_name,
                COUNT(*) as total,
                AVG(improvement) as avg_improvement,
                SUM(CASE WHEN outcome = 'success' THEN 1 ELSE 0 END) * 1.0 /
                    NULLIF(SUM(CASE WHEN outcome IN ('success', 'partial', 'failed') THEN 1 ELSE 0 END), 0) as success_rate
            FROM skill_executions
            WHERE problem_type = ?
            GROUP BY skill_name
            HAVING total >= ?
            ORDER BY success_rate DESC, avg_improvement DESC
            LIMIT 1
        """, (problem_type, min_executions))

        row = cursor.fetchone()

        if row:
            return row[0]

        return None

    def close(self):
        """Close database connection."""
        if self.conn:
            self.conn.close()


def main():
    """Test skill tracker."""
    logging.basicConfig(level=logging.INFO)

    tracker = SkillTracker()

    # Simulate skill execution
    execution = SkillExecution(
        execution_id="test_001",
        skill_name="systematic-debugging",
        problem_type="performance",
        problem_description="Swap usage at 99.6%",
        phase="Phase 1: Root Cause Investigation",
        actions_count=5,
        confidence=0.8,
        timestamp=time.time(),
        metrics_before={
            'swap_used_mb': 12250,
            'memory_used_pct': 57.0,
            'thread_count': 338
        }
    )

    print("Recording execution...")
    tracker.record_execution(execution)

    # Simulate outcome after some time
    print("Updating outcome...")
    tracker.update_outcome(
        execution_id="test_001",
        outcome="success",
        metrics_after={
            'swap_used_mb': 8500,
            'memory_used_pct': 52.0,
            'thread_count': 150
        },
        notes="Throttled investigations, reduced swap by 30%"
    )

    # Get effectiveness
    stats = tracker.get_skill_effectiveness("systematic-debugging", "performance")
    print(f"\nSkill effectiveness:")
    print(f"  Total executions: {stats['total_executions']}")
    print(f"  Success rate: {stats['success_rate']:.1%}")
    print(f"  Avg improvement: {stats['avg_improvement']:.1%}")
    print(f"  Avg confidence: {stats['avg_confidence']:.1%}")

    tracker.close()


if __name__ == "__main__":
    main()
