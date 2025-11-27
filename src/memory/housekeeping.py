"""
Housekeeping and maintenance operations for KLoROS memory system.

Provides automated and manual maintenance tasks including cleanup,
optimization, statistics reporting, and data integrity checks.
"""

from __future__ import annotations

import os
import sys
import time
import gzip
import shutil
import json
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

from .models import Event, Episode, EpisodeSummary, EventType
from .storage import MemoryStore
from .condenser import EpisodeCondenser
from .logger import MemoryLogger
from .intelligent_cleanup import IntelligentCleanup
from .qdrant_export import QdrantMemoryExporter


class MemoryHousekeeper:
    """
    Automated housekeeping and maintenance for KLoROS memory system.

    Features:
    - Automated cleanup of old events and episodes
    - Database optimization and vacuuming
    - Statistics reporting and health checks
    - Data integrity validation
    - Episode condensation automation
    """

    def __init__(
        self,
        store: Optional[MemoryStore] = None,
        logger: Optional[MemoryLogger] = None
    ):
        """
        Initialize the memory housekeeper.

        Args:
            store: Memory storage instance
            logger: Memory logger instance
        """
        self.store = store or MemoryStore()
        self.qdrant_exporter: Optional[QdrantMemoryExporter] = None
        self.logger = logger or MemoryLogger(self.store)

        # Configuration from environment
        self.retention_days = int(os.getenv("KLR_RETENTION_DAYS", "30"))
        self.auto_vacuum_days = int(os.getenv("KLR_AUTO_VACUUM_DAYS", "7"))
        self.max_uncondensed_episodes = int(os.getenv("KLR_MAX_UNCONDENSED", "100"))
        self.cleanup_batch_size = int(os.getenv("KLR_CLEANUP_BATCH_SIZE", "1000"))

        # Reflection system housekeeping configuration
        self.reflection_log_max_mb = int(os.getenv("KLR_REFLECTION_LOG_MAX_MB", "50"))
        self.reflection_retention_days = int(os.getenv("KLR_REFLECTION_RETENTION_DAYS", "60"))
        self.reflection_archive_days = int(os.getenv("KLR_REFLECTION_ARCHIVE_DAYS", "30"))
        self.reflection_vacuum_days = int(os.getenv("KLR_REFLECTION_VACUUM_DAYS", "14"))
        self.reflection_log_path = os.getenv("KLR_REFLECTION_LOG_PATH", "/home/kloros/.kloros/reflection.log")

        # Tracking last maintenance operations
        self._last_vacuum: Optional[float] = None
        self._last_cleanup: Optional[float] = None
        self._last_condensation: Optional[float] = None
        self._last_reflection_cleanup: Optional[float] = None
        self._last_reflection_archive: Optional[float] = None

    def run_daily_maintenance(self) -> Dict[str, Any]:
        """
        Run daily maintenance tasks.

        Returns:
            Dictionary with maintenance results
        """
        results = {
            "timestamp": time.time(),
            "tasks_completed": [],
            "errors": [],
            "stats": {}
        }

        try:
            # Task 1: Clean up old events
            cleanup_result = self.cleanup_old_events()
            results["tasks_completed"].append("cleanup_old_events")
            results["cleanup_deleted"] = cleanup_result

            # Task 2: Condense uncondensed episodes
            condensation_result = self.condense_pending_episodes()
            results["tasks_completed"].append("condense_episodes")
            results["episodes_condensed"] = condensation_result

            # Task 3: Vacuum database if needed
            if self._should_vacuum():
                self.vacuum_database()
                results["tasks_completed"].append("vacuum_database")

            # Task 4: Generate statistics
            results["stats"] = self.get_comprehensive_stats()
            results["tasks_completed"].append("generate_stats")

            # Task 5: Validate data integrity
            integrity_result = self.validate_data_integrity()
            results["tasks_completed"].append("validate_integrity")
            results["integrity_issues"] = integrity_result

            # Task 6: Reflection log maintenance
            reflection_result = self.cleanup_reflection_logs()
            results["tasks_completed"].append("cleanup_reflection_logs")
            results["reflection_log_cleanup"] = reflection_result

            # Task 7: TTS output cleanup
            tts_result = self.cleanup_tts_outputs()
            results["tasks_completed"].append("cleanup_tts_outputs")
            results["tts_cleanup"] = tts_result

            # Task 8: Python cache cleanup
            python_cache_result = self.cleanup_python_cache()
            results["tasks_completed"].append("cleanup_python_cache")
            results["python_cache_cleanup"] = python_cache_result

            # Task 9: Backup file management
            backup_result = self.cleanup_backup_files()
            results["tasks_completed"].append("cleanup_backup_files")
            results["backup_cleanup"] = backup_result

            # Task 10: TTS output analysis
            tts_analysis_result = self.analyze_tts_quality()
            results["tasks_completed"].append("analyze_tts_quality")
            results["tts_analysis"] = tts_analysis_result

            # Task 11: Export episode summaries to ChromaDB
            chroma_export_result = self.export_to_chromadb()
            results["tasks_completed"].append("export_to_chromadb")
            results["chroma_export"] = chroma_export_result

            # Task 12: Create daily rollup in ChromaDB
            daily_rollup_result = self.create_daily_rollup()
            results["tasks_completed"].append("create_daily_rollup")
            results["daily_rollup"] = daily_rollup_result

            # Task 13: Export memory to knowledge base (markdown for RAG)
            kb_export_result = self.export_memory_to_kb()
            results["tasks_completed"].append("export_memory_to_kb")
            results["kb_export"] = kb_export_result

            # Task 14: Rebuild RAG database
            rag_rebuild_result = self.rebuild_rag_database()
            results["tasks_completed"].append("rebuild_rag_database")
            results["rag_rebuild"] = rag_rebuild_result

            # Task 15: Archive obsolete scripts
            obsolete_scripts_result = self.cleanup_obsolete_scripts()
            results["tasks_completed"].append("cleanup_obsolete_scripts")
            results["obsolete_scripts_cleanup"] = obsolete_scripts_result

            # Task 16: Sweep and mark obsolete files
            sweep_result = self.sweep_obsolete_files()
            results["tasks_completed"].append("sweep_obsolete_files")
            results["obsolete_sweep"] = sweep_result

            # Task 17: Intelligent file cleanup (backup files, temp files, etc.)
            intelligent_cleanup_result = self.intelligent_file_cleanup()
            results["tasks_completed"].append("intelligent_file_cleanup")
            results["intelligent_cleanup"] = intelligent_cleanup_result

            # Log maintenance completion
            self.logger.log_event(
                event_type=EventType.MEMORY_HOUSEKEEPING,
                content="Daily maintenance completed",
                metadata=results
            )

        except Exception as e:
            error_msg = f"Daily maintenance failed: {e}"
            results["errors"].append(error_msg)
            self.logger.log_error(
                error_message=error_msg,
                error_type=type(e).__name__,
                component="daily_maintenance"
            )

        return results

    def cleanup_old_events(self, retention_days: Optional[int] = None) -> int:
        """
        Clean up old events beyond retention period.

        Args:
            retention_days: Days to retain (uses default if None)

        Returns:
            Number of events deleted
        """
        if retention_days is None:
            retention_days = self.retention_days

        deleted_count = self.store.cleanup_old_events(retention_days)
        self._last_cleanup = time.time()

        # Log cleanup operation
        self.logger.log_event(
            event_type=EventType.MEMORY_HOUSEKEEPING,
            content=f"Cleaned up {deleted_count} old events",
            metadata={
                "deleted_count": deleted_count,
                "retention_days": retention_days,
                "cleanup_timestamp": self._last_cleanup
            }
        )

        return deleted_count

    def condense_pending_episodes(self, max_episodes: Optional[int] = None) -> int:
        """
        Condense uncondensed episodes.

        Args:
            max_episodes: Maximum episodes to process (uses default if None)

        Returns:
            Number of episodes condensed
        """
        if max_episodes is None:
            max_episodes = self.max_uncondensed_episodes

        condenser = EpisodeCondenser(self.store)
        condensed_count = condenser.process_uncondensed_episodes(max_episodes)
        self._last_condensation = time.time()

        # Log condensation operation
        self.logger.log_event(
            event_type=EventType.MEMORY_HOUSEKEEPING,
            content=f"Condensed {condensed_count} episodes",
            metadata={
                "condensed_count": condensed_count,
                "max_episodes": max_episodes,
                "condensation_timestamp": self._last_condensation
            }
        )

        return condensed_count

    def vacuum_database(self) -> None:
        """Vacuum database to reclaim space and optimize performance."""
        start_time = time.time()
        self.store.vacuum_database()
        vacuum_time = time.time() - start_time
        self._last_vacuum = time.time()

        # Log vacuum operation
        self.logger.log_event(
            event_type=EventType.MEMORY_HOUSEKEEPING,
            content="Database vacuumed",
            metadata={
                "vacuum_time": vacuum_time,
                "vacuum_timestamp": self._last_vacuum
            }
        )

    def _should_vacuum(self) -> bool:
        """Check if database should be vacuumed."""
        if self._last_vacuum is None:
            return True

        days_since_vacuum = (time.time() - self._last_vacuum) / 86400
        return days_since_vacuum >= self.auto_vacuum_days

    def get_comprehensive_stats(self) -> Dict[str, Any]:
        """
        Get comprehensive memory system statistics.

        Returns:
            Dictionary with detailed statistics
        """
        stats = self.store.get_stats()

        # Add time-based statistics
        now = time.time()
        day_ago = now - 86400
        week_ago = now - (7 * 86400)

        # Recent activity statistics
        conn = self.store._get_connection()

        # Events by type in last 24 hours
        cursor = conn.execute("""
            SELECT event_type, COUNT(*) as count
            FROM events
            WHERE timestamp >= ?
            GROUP BY event_type
            ORDER BY count DESC
        """, (day_ago,))

        events_24h_by_type = {}
        for row in cursor.fetchall():
            events_24h_by_type[row[0]] = row[1]

        stats["events_24h_by_type"] = events_24h_by_type

        # Average conversation length
        cursor = conn.execute("""
            SELECT AVG(event_count) as avg_length
            FROM episodes
            WHERE start_time >= ?
        """, (week_ago,))

        row = cursor.fetchone()
        stats["avg_conversation_length"] = row[0] if row and row[0] else 0

        # Top conversation topics (from summaries)
        cursor = conn.execute("""
            SELECT key_topics, COUNT(*) as count
            FROM episode_summaries
            WHERE created_at >= ?
            AND key_topics != '[]'
            GROUP BY key_topics
            ORDER BY count DESC
            LIMIT 10
        """, (week_ago,))

        topic_counts = {}
        for row in cursor.fetchall():
            try:
                import json
                topics = json.loads(row[0])
                for topic in topics:
                    topic_counts[topic] = topic_counts.get(topic, 0) + row[1]
            except json.JSONDecodeError:
                continue

        stats["top_topics_week"] = dict(sorted(topic_counts.items(), key=lambda x: x[1], reverse=True)[:10])

        # Memory usage efficiency
        total_events = stats.get("total_events", 0)
        total_summaries = stats.get("total_summaries", 0)
        if total_events > 0:
            stats["summarization_ratio"] = total_summaries / total_events
        else:
            stats["summarization_ratio"] = 0

        # Maintenance status
        stats["maintenance_status"] = {
            "last_vacuum": self._last_vacuum,
            "last_cleanup": self._last_cleanup,
            "last_condensation": self._last_condensation,
            "needs_vacuum": self._should_vacuum()
        }

        return stats

    def validate_data_integrity(self) -> List[Dict[str, Any]]:
        """
        Validate data integrity and return list of issues found.

        Returns:
            List of integrity issues
        """
        issues = []
        conn = self.store._get_connection()

        # Check for episodes without summaries that should be condensed
        cursor = conn.execute("""
            SELECT COUNT(*) as count
            FROM episodes
            WHERE is_condensed = 1
            AND id NOT IN (SELECT episode_id FROM episode_summaries)
        """)

        row = cursor.fetchone()
        if row and row[0] > 0:
            issues.append({
                "type": "missing_summaries",
                "count": row[0],
                "description": "Episodes marked as condensed but missing summaries"
            })

        # Check for orphaned summaries
        cursor = conn.execute("""
            SELECT COUNT(*) as count
            FROM episode_summaries
            WHERE episode_id NOT IN (SELECT id FROM episodes)
        """)

        row = cursor.fetchone()
        if row and row[0] > 0:
            issues.append({
                "type": "orphaned_summaries",
                "count": row[0],
                "description": "Summaries referencing non-existent episodes"
            })

        # Check for very old uncondensed episodes
        old_threshold = time.time() - (7 * 86400)  # 7 days old
        cursor = conn.execute("""
            SELECT COUNT(*) as count
            FROM episodes
            WHERE is_condensed = 0
            AND start_time < ?
        """, (old_threshold,))

        row = cursor.fetchone()
        if row and row[0] > 0:
            issues.append({
                "type": "old_uncondensed_episodes",
                "count": row[0],
                "description": "Episodes older than 7 days that haven't been condensed"
            })

        # Check for events with invalid timestamps
        cursor = conn.execute("""
            SELECT COUNT(*) as count
            FROM events
            WHERE timestamp < 0 OR timestamp > ?
        """, (time.time() + 86400,))  # Future date + 1 day buffer

        row = cursor.fetchone()
        if row and row[0] > 0:
            issues.append({
                "type": "invalid_timestamps",
                "count": row[0],
                "description": "Events with invalid timestamps"
            })

        return issues

    def fix_integrity_issues(self) -> Dict[str, int]:
        """
        Attempt to fix identified integrity issues.

        Returns:
            Dictionary with count of fixes applied
        """
        fixes = {
            "missing_summaries_fixed": 0,
            "orphaned_summaries_removed": 0,
            "invalid_events_removed": 0
        }

        conn = self.store._get_connection()

        # Fix episodes marked as condensed but missing summaries
        cursor = conn.execute("""
            UPDATE episodes
            SET is_condensed = 0, condensed_at = NULL
            WHERE is_condensed = 1
            AND id NOT IN (SELECT episode_id FROM episode_summaries)
        """)
        fixes["missing_summaries_fixed"] = cursor.rowcount

        # Remove orphaned summaries
        cursor = conn.execute("""
            DELETE FROM episode_summaries
            WHERE episode_id NOT IN (SELECT id FROM episodes)
        """)
        fixes["orphaned_summaries_removed"] = cursor.rowcount

        # Remove events with invalid timestamps
        cursor = conn.execute("""
            DELETE FROM events
            WHERE timestamp < 0 OR timestamp > ?
        """, (time.time() + 86400,))
        fixes["invalid_events_removed"] = cursor.rowcount

        # Log fixes applied
        self.logger.log_event(
            event_type=EventType.MEMORY_HOUSEKEEPING,
            content="Data integrity issues fixed",
            metadata=fixes
        )

        return fixes

    def export_memory_summary(self, days: int = 7) -> Dict[str, Any]:
        """
        Export a summary of memory activity for the specified period.

        Args:
            days: Number of days to include in summary

        Returns:
            Dictionary with memory activity summary
        """
        start_time = time.time() - (days * 86400)
        conn = self.store._get_connection()

        summary = {
            "period_days": days,
            "start_time": start_time,
            "end_time": time.time(),
            "conversations": [],
            "top_topics": [],
            "activity_stats": {}
        }

        # Get conversations in period
        cursor = conn.execute("""
            SELECT conversation_id, MIN(start_time) as start_time,
                   MAX(end_time) as end_time, SUM(event_count) as total_events
            FROM episodes
            WHERE start_time >= ?
            GROUP BY conversation_id
            ORDER BY start_time DESC
        """, (start_time,))

        for row in cursor.fetchall():
            summary["conversations"].append({
                "conversation_id": row[0],
                "start_time": row[1],
                "end_time": row[2],
                "total_events": row[3]
            })

        # Get activity statistics
        cursor = conn.execute("""
            SELECT event_type, COUNT(*) as count
            FROM events
            WHERE timestamp >= ?
            GROUP BY event_type
        """, (start_time,))

        activity_stats = {}
        for row in cursor.fetchall():
            activity_stats[row[0]] = row[1]

        summary["activity_stats"] = activity_stats

        return summary

    def schedule_maintenance(self, interval_hours: float = 24.0) -> None:
        """
        Schedule regular maintenance operations.

        Args:
            interval_hours: Hours between maintenance runs
        """
        # This would typically be implemented with a scheduler like APScheduler
        # For now, just log the scheduling request
        self.logger.log_event(
            event_type=EventType.MEMORY_HOUSEKEEPING,
            content=f"Maintenance scheduled every {interval_hours} hours",
            metadata={"interval_hours": interval_hours}
        )

    def get_health_report(self) -> Dict[str, Any]:
        """
        Generate a comprehensive health report for the memory system.

        Returns:
            Dictionary with health status and recommendations
        """
        stats = self.get_comprehensive_stats()
        integrity_issues = self.validate_data_integrity()

        health_score = 100.0
        recommendations = []

        # Deduct health score for issues
        if integrity_issues:
            health_score -= len(integrity_issues) * 10
            recommendations.append("Run fix_integrity_issues() to resolve data integrity problems")

        # Check if vacuum is needed
        if self._should_vacuum():
            health_score -= 5
            recommendations.append("Database vacuum recommended for performance")

        # Check uncondensed episodes
        uncondensed = stats.get("total_episodes", 0) - stats.get("condensed_episodes", 0)
        if uncondensed > self.max_uncondensed_episodes:
            health_score -= 10
            recommendations.append(f"Too many uncondensed episodes ({uncondensed}), consider running condensation")

        # Check database size
        db_size_mb = stats.get("db_size_bytes", 0) / (1024 * 1024)
        if db_size_mb > 1000:  # 1GB threshold
            health_score -= 5
            recommendations.append("Large database size, consider cleanup of old events")

        # Check reflection log health
        reflection_stats = self.get_reflection_log_stats()
        if reflection_stats.get("log_exists", False):
            reflection_log_mb = reflection_stats.get("log_size_mb", 0)

            # Check reflection log size
            if reflection_log_mb > self.reflection_log_max_mb:
                health_score -= 5
                recommendations.append(f"Reflection log exceeds size limit ({reflection_log_mb:.1f}MB > {self.reflection_log_max_mb}MB)")

            # Check for very old reflection entries
            oldest_entry = reflection_stats.get("oldest_entry")
            if oldest_entry:
                try:
                    if isinstance(oldest_entry, str):
                        oldest_dt = datetime.fromisoformat(oldest_entry.replace('Z', '+00:00'))
                        oldest_age_days = (datetime.now().timestamp() - oldest_dt.timestamp()) / 86400

                        if oldest_age_days > self.reflection_retention_days:
                            health_score -= 3
                            recommendations.append(f"Reflection log contains very old entries ({oldest_age_days:.0f} days)")
                except (ValueError, AttributeError):
                    pass

        health_score = max(0.0, health_score)

        return {
            "health_score": health_score,
            "status": "healthy" if health_score >= 90 else "needs_attention" if health_score >= 70 else "critical",
            "recommendations": recommendations,
            "integrity_issues": integrity_issues,
            "stats_summary": {
                "total_events": stats.get("total_events", 0),
                "total_episodes": stats.get("total_episodes", 0),
                "condensed_episodes": stats.get("condensed_episodes", 0),
                "db_size_mb": db_size_mb
            },
            "reflection_summary": {
                "log_exists": reflection_stats.get("log_exists", False),
                "log_size_mb": reflection_stats.get("log_size_mb", 0),
                "entry_count": reflection_stats.get("entry_count", 0),
                "archive_count": reflection_stats.get("archive_count", 0),
                "total_archive_size_mb": reflection_stats.get("total_archive_size_bytes", 0) / (1024 * 1024)
            }
        }

    def cleanup_python_cache(self) -> Dict[str, Any]:
        """
        Clean up Python cache files and directories throughout KLoROS system.

        Removes .pyc files and __pycache__ directories to free disk space
        and prevent stale bytecode issues.

        Returns:
            Dictionary with cleanup results
        """
        results = {
            "pyc_files_deleted": 0,
            "pycache_dirs_deleted": 0,
            "bytes_freed": 0,
            "errors": []
        }

        try:
            import glob
            from pathlib import Path

            # Configuration
            kloros_root = Path("/home/kloros")
            max_scan_depth = int(os.getenv("KLR_CACHE_SCAN_DEPTH", "10"))

            # Find and remove .pyc files
            pyc_pattern = str(kloros_root / "**" / "*.pyc")
            pyc_files = []

            # Use controlled recursion to avoid infinite loops
            for depth in range(max_scan_depth):
                pattern = str(kloros_root / ("**/" * depth) / "*.pyc")
                pyc_files.extend(glob.glob(pattern))

            # Remove duplicates and sort
            pyc_files = list(set(pyc_files))

            for pyc_file in pyc_files:
                try:
                    file_size = os.path.getsize(pyc_file)
                    os.unlink(pyc_file)
                    results["pyc_files_deleted"] += 1
                    results["bytes_freed"] += file_size
                except Exception as e:
                    results["errors"].append(f"Failed to remove {pyc_file}: {e}")

            # Find and remove __pycache__ directories
            pycache_dirs = []
            for root, dirs, files in os.walk(kloros_root):
                if "__pycache__" in dirs:
                    pycache_path = os.path.join(root, "__pycache__")
                    pycache_dirs.append(pycache_path)

            for cache_dir in pycache_dirs:
                try:
                    # Calculate directory size before removal
                    dir_size = sum(
                        os.path.getsize(os.path.join(dirpath, filename))
                        for dirpath, dirnames, filenames in os.walk(cache_dir)
                        for filename in filenames
                    )

                    shutil.rmtree(cache_dir)
                    results["pycache_dirs_deleted"] += 1
                    results["bytes_freed"] += dir_size
                except Exception as e:
                    results["errors"].append(f"Failed to remove {cache_dir}: {e}")

            # Log cleanup operation
            self.logger.log_event(
                event_type=EventType.MEMORY_HOUSEKEEPING,
                content=f"Python cache cleanup: removed {results['pyc_files_deleted']} .pyc files and {results['pycache_dirs_deleted']} __pycache__ dirs",
                metadata={
                    "pyc_files_deleted": results["pyc_files_deleted"],
                    "pycache_dirs_deleted": results["pycache_dirs_deleted"],
                    "bytes_freed": results["bytes_freed"],
                    "error_count": len(results["errors"])
                }
            )

        except Exception as e:
            error_msg = f"Python cache cleanup error: {str(e)}"
            results["errors"].append(error_msg)
            self.logger.log_event(
                event_type=EventType.ERROR_OCCURRED,
                content=error_msg,
                metadata={
                    "error_type": type(e).__name__,
                    "component": "python_cache_cleanup"
                }
            )

        return results

    def cleanup_backup_files(self) -> Dict[str, Any]:
        """
        Clean up excessive backup files, keeping only the most recent ones.

        Manages backup file rotation based on analysis recommendations,
        preserving important backups while removing redundant ones.

        Returns:
            Dictionary with cleanup results
        """
        results = {
            "files_scanned": 0,
            "files_deleted": 0,
            "files_retained": 0,
            "bytes_freed": 0,
            "errors": [],
            "retention_reasons": []
        }

        try:
            from pathlib import Path
            import glob

            # Configuration
            kloros_root = Path("/home/kloros")
            max_backups_per_file = int(os.getenv("KLR_MAX_BACKUPS_PER_FILE", "3"))
            backup_retention_days = int(os.getenv("KLR_BACKUP_RETENTION_DAYS", "30"))

            # Find backup files
            backup_patterns = [
                "*.backup*",
                "*.py.backup*",
                "*backup-*"
            ]

            all_backup_files = []
            for pattern in backup_patterns:
                backup_files = list(kloros_root.rglob(pattern))
                all_backup_files.extend(backup_files)

            # Remove duplicates
            all_backup_files = list(set(all_backup_files))
            results["files_scanned"] = len(all_backup_files)

            if not all_backup_files:
                return results

            # Group backups by base filename
            backup_groups = {}
            for backup_file in all_backup_files:
                # Extract base filename (remove backup suffixes)
                base_name = str(backup_file.name)
                for suffix in [".backup", "backup-", ".backup-"]:
                    if suffix in base_name:
                        base_name = base_name.split(suffix)[0]
                        break

                if base_name not in backup_groups:
                    backup_groups[base_name] = []
                backup_groups[base_name].append(backup_file)

            # Process each group
            cutoff_time = time.time() - (backup_retention_days * 86400)

            for base_name, backup_files in backup_groups.items():
                # Sort by modification time (newest first)
                backup_files.sort(key=lambda f: f.stat().st_mtime, reverse=True)

                # Decide which files to keep/remove
                for i, backup_file in enumerate(backup_files):
                    file_mtime = backup_file.stat().st_mtime
                    should_keep = False
                    reason = ""

                    # Keep recent files
                    if file_mtime > cutoff_time:
                        should_keep = True
                        reason = f"recent (< {backup_retention_days} days)"

                    # Keep most recent N files
                    elif i < max_backups_per_file:
                        should_keep = True
                        reason = f"within last {max_backups_per_file} backups for {base_name}"

                    # Keep files with important-looking names
                    elif any(keyword in backup_file.name.lower() for keyword in ["phase", "deployment", "critical", "important"]):
                        should_keep = True
                        reason = "important backup (phase/deployment/critical)"

                    if should_keep:
                        results["files_retained"] += 1
                        results["retention_reasons"].append(f"{backup_file.name}: {reason}")
                    else:
                        # Delete the backup file
                        try:
                            file_size = backup_file.stat().st_size
                            backup_file.unlink()
                            results["files_deleted"] += 1
                            results["bytes_freed"] += file_size
                        except Exception as e:
                            results["errors"].append(f"Error deleting {backup_file}: {e}")

            # Log cleanup operation
            self.logger.log_event(
                event_type=EventType.MEMORY_HOUSEKEEPING,
                content=f"Backup cleanup: deleted {results['files_deleted']} files, retained {results['files_retained']} files",
                metadata={
                    "files_scanned": results["files_scanned"],
                    "files_deleted": results["files_deleted"],
                    "files_retained": results["files_retained"],
                    "bytes_freed": results["bytes_freed"],
                    "backup_groups": len(backup_groups),
                    "max_backups_per_file": max_backups_per_file,
                    "retention_days": backup_retention_days
                }
            )

        except Exception as e:
            error_msg = f"Backup file cleanup error: {str(e)}"
            results["errors"].append(error_msg)
            self.logger.log_event(
                event_type=EventType.ERROR_OCCURRED,
                content=error_msg,
                metadata={
                    "error_type": type(e).__name__,
                    "component": "backup_file_cleanup"
                }
            )

        return results

    def analyze_tts_quality(self) -> Dict[str, Any]:
        """
        Analyze TTS output quality and log insights for improvement.

        Uses passive analysis of generated TTS files to identify quality issues
        and optimization opportunities for speech synthesis.

        Returns:
            Dictionary with analysis results
        """
        results = {
            "analysis_performed": False,
            "files_analyzed": 0,
            "quality_score": 0.0,
            "insights_generated": 0,
            "recommendations": [],
            "errors": []
        }

        try:
            # Import and initialize TTS analyzer
            from tts_analysis import TTSAnalyzer
            analyzer = TTSAnalyzer()

            # Perform analysis
            analysis_results = analyzer.analyze_recent_tts_outputs()

            # Update results
            results["analysis_performed"] = True
            results["files_analyzed"] = analysis_results.get("files_analyzed", 0)

            # Extract key metrics
            quality_metrics = analysis_results.get("quality_metrics", {})
            if quality_metrics:
                results["quality_score"] = quality_metrics.get("overall_quality_mean", 0.0)

            insights = analysis_results.get("improvement_insights", [])
            results["insights_generated"] = len(insights)
            results["recommendations"] = analysis_results.get("recommendations", [])
            results["errors"] = analysis_results.get("errors", [])

            # Log TTS analysis results to memory
            if results["files_analyzed"] > 0:
                # Log overall analysis event
                self.logger.log_event(
                    event_type=EventType.MEMORY_HOUSEKEEPING,
                    content=f"TTS quality analysis: {results['files_analyzed']} files, quality {results['quality_score']:.3f}",
                    metadata={
                        "files_analyzed": results["files_analyzed"],
                        "quality_score": results["quality_score"],
                        "insights_count": results["insights_generated"],
                        "recommendations": results["recommendations"],
                        "trend_analysis": analysis_results.get("trend_analysis", {}),
                        "component": "tts_quality_analysis"
                    }
                )

                # Log individual insights for improvement tracking
                for insight in insights:
                    if insight.get("priority") in ["high", "medium"]:
                        self.logger.log_event(
                            event_type=EventType.SELF_REFLECTION,
                            content=f"TTS improvement opportunity: {insight.get('message', 'Quality issue detected')}",
                            metadata={
                                "insight_type": insight.get("type"),
                                "priority": insight.get("priority"),
                                "metrics": insight.get("metrics", {}),
                                "component": "tts_optimization"
                            }
                        )

                print(f"[housekeeping] TTS analysis: {results['files_analyzed']} files, quality {results['quality_score']:.3f}")
                if results["recommendations"]:
                    print(f"[housekeeping] TTS recommendations: {len(results['recommendations'])} suggestions")

            else:
                print("[housekeeping] TTS analysis: Insufficient files for analysis")

        except ImportError:
            error_msg = "TTS analysis module not available"
            results["errors"].append(error_msg)
            print(f"[housekeeping] {error_msg}")

        except Exception as e:
            error_msg = f"TTS analysis error: {str(e)}"
            results["errors"].append(error_msg)
            self.logger.log_event(
                event_type=EventType.ERROR_OCCURRED,
                content=error_msg,
                metadata={
                    "error_type": type(e).__name__,
                    "component": "tts_quality_analysis"
                }
            )
            print(f"[housekeeping] {error_msg}")

        return results

    def export_memory_to_kb(self) -> Dict[str, Any]:
        """
        Export episodic memory summaries to knowledge base for RAG expansion.

        Returns:
            Dictionary with export results
        """
        results = {
            "exported": False,
            "summaries_exported": 0,
            "errors": []
        }

        try:
            import subprocess
            script_path = "/home/kloros/scripts/export_memory_to_kb.py"
            result = subprocess.run(
                [sys.executable, script_path],
                capture_output=True,
                text=True,
                timeout=30
            )

            if result.returncode == 0:
                # Parse output for count
                for line in result.stdout.split('\n'):
                    if 'Exported' in line and 'summaries' in line:
                        import re
                        match = re.search(r'Exported (\d+)', line)
                        if match:
                            results["summaries_exported"] = int(match.group(1))
                results["exported"] = True
            else:
                results["errors"].append(f"Export script failed: {result.stderr}")

        except Exception as e:
            results["errors"].append(str(e))

        return results

    def rebuild_rag_database(self) -> Dict[str, Any]:
        """
        Rebuild RAG database from expanded knowledge base.

        Returns:
            Dictionary with rebuild results
        """
        results = {
            "rebuilt": False,
            "document_count": 0,
            "errors": []
        }

        try:
            import subprocess
            script_path = "/home/kloros/scripts/build_knowledge_base_rag.py"
            result = subprocess.run(
                [sys.executable, script_path],
                capture_output=True,
                text=True,
                timeout=120
            )

            if result.returncode == 0:
                # Parse output for document count
                for line in result.stdout.split('\n'):
                    if 'Total chunks:' in line:
                        import re
                        match = re.search(r'Total chunks: (\d+)', line)
                        if match:
                            results["document_count"] = int(match.group(1))
                results["rebuilt"] = True
            else:
                results["errors"].append(f"RAG rebuild failed: {result.stderr}")

        except Exception as e:
            results["errors"].append(str(e))

        return results

    def export_to_chromadb(self) -> Dict[str, Any]:
        """
        Export episode summaries to ChromaDB for semantic retrieval.

        Returns:
            Dictionary with export results
        """
        results = {
            "exported": 0,
            "errors": []
        }

        try:
            # Initialize Qdrant exporter if needed
            if self.qdrant_exporter is None:
                self.qdrant_exporter = QdrantMemoryExporter(self.store)

            # Export recent summaries (last 24 hours)
            export_result = self.qdrant_exporter.export_recent_summaries(
                hours=24.0,
                min_importance=0.3
            )

            results["exported"] = export_result.get("exported", 0)
            results["skipped"] = export_result.get("skipped", 0)

            if export_result.get("errors"):
                results["errors"].extend(export_result["errors"])

        except Exception as e:
            results["errors"].append(f"Qdrant export failed: {e}")

        return results

    def create_daily_rollup(self) -> Dict[str, Any]:
        """
        Create daily rollup in Qdrant from yesterday's summaries.

        Returns:
            Dictionary with rollup results
        """
        results = {
            "rollup_created": False,
            "errors": []
        }

        try:
            # Initialize Qdrant exporter if needed
            if self.qdrant_exporter is None:
                self.qdrant_exporter = QdrantMemoryExporter(self.store)

            # Create rollup for yesterday
            from datetime import datetime, timedelta
            yesterday = datetime.now() - timedelta(days=1)

            rollup_result = self.qdrant_exporter.create_daily_rollup(yesterday)

            results["rollup_created"] = rollup_result.get("rollup_created", False)
            results["summaries_included"] = rollup_result.get("summaries_included", 0)

            if rollup_result.get("errors"):
                results["errors"].extend(rollup_result["errors"])

        except Exception as e:
            results["errors"].append(f"Daily rollup failed: {e}")

        return results

    # =========================================================================
    # Reflection System Housekeeping Methods
    # =========================================================================

    def cleanup_reflection_logs(self) -> Dict[str, Any]:
        """
        Clean up reflection logs based on size and age limits.

        Returns:
            Dictionary with cleanup results
        """
        results = {
            "log_rotated": False,
            "entries_archived": 0,
            "bytes_freed": 0,
            "archive_files_created": 0,
            "errors": []
        }

        try:
            # Check if reflection log exists
            if not os.path.exists(self.reflection_log_path):
                return results

            # Get current log size
            log_size_bytes = os.path.getsize(self.reflection_log_path)
            log_size_mb = log_size_bytes / (1024 * 1024)

            # Rotate log if it exceeds size limit
            if log_size_mb > self.reflection_log_max_mb:
                rotation_result = self._rotate_reflection_log()
                results.update(rotation_result)

            # Archive old entries if needed
            archive_result = self._archive_old_reflection_entries()
            results["entries_archived"] = archive_result.get("entries_archived", 0)
            results["archive_files_created"] += archive_result.get("files_created", 0)
            results["bytes_freed"] += archive_result.get("bytes_freed", 0)

            self._last_reflection_cleanup = time.time()

            # Log cleanup operation
            self.logger.log_event(
                event_type=EventType.MEMORY_HOUSEKEEPING,
                content=f"Reflection log cleanup completed",
                metadata={
                    "log_size_mb": log_size_mb,
                    "log_rotated": results["log_rotated"],
                    "entries_archived": results["entries_archived"],
                    "bytes_freed": results["bytes_freed"],
                    "cleanup_timestamp": self._last_reflection_cleanup
                }
            )

        except Exception as e:
            error_msg = f"Reflection log cleanup error: {str(e)}"
            results["errors"].append(error_msg)
            self.logger.log_event(
                event_type=EventType.ERROR_OCCURRED,
                content=error_msg,
                metadata={
                    "error_type": type(e).__name__,
                    "component": "reflection_log_cleanup"
                }
            )

        return results

    def cleanup_tts_outputs(self) -> Dict[str, Any]:
        """
        Clean up TTS output files based on age and memory analysis.

        Reviews TTS outputs and purges old files after memory processing,
        keeping recent files and any that might be referenced in episodic memory.

        Returns:
            Dictionary with cleanup results
        """
        results = {
            "files_scanned": 0,
            "files_deleted": 0,
            "bytes_freed": 0,
            "errors": [],
            "retained_files": 0,
            "retention_reasons": []
        }

        try:
            import os
            import glob
            from datetime import datetime, timedelta

            # Configuration
            tts_output_dir = os.path.expanduser("~/.kloros/out")
            max_files_to_keep = int(os.getenv("KLR_TTS_MAX_FILES", "50"))  # Keep last 50 files
            min_age_hours = int(os.getenv("KLR_TTS_MIN_AGE_HOURS", "6"))   # Don't delete files < 6 hours old

            if not os.path.exists(tts_output_dir):
                return results

            # Get all TTS files with timestamps
            tts_pattern = os.path.join(tts_output_dir, "tts_*.wav")
            tts_files = glob.glob(tts_pattern)
            results["files_scanned"] = len(tts_files)

            if not tts_files:
                return results

            # Sort by modification time (newest first)
            tts_files.sort(key=lambda f: os.path.getmtime(f), reverse=True)

            # Calculate cutoff time (don't delete recent files)
            cutoff_time = datetime.now() - timedelta(hours=min_age_hours)
            cutoff_timestamp = cutoff_time.timestamp()

            # Get recent TTS events from memory to identify important files
            important_timestamps = set()
            try:
                # Look for recent TTS events in last 24 hours
                from datetime import datetime, timedelta
                from .models import EventType

                start_time = (datetime.now() - timedelta(hours=24)).timestamp()
                recent_events = self.store.get_events(
                    event_type=EventType.TTS_OUTPUT,
                    start_time=start_time,
                    limit=100
                )

                for event in recent_events:
                    # Extract timestamp from TTS filename if present in metadata
                    metadata = getattr(event, 'metadata', {})
                    if isinstance(metadata, dict) and 'file_path' in metadata:
                        file_path = metadata['file_path']
                        if 'tts_' in file_path:
                            # Extract timestamp from filename like tts_1759532391331.wav
                            try:
                                filename = os.path.basename(file_path)
                                timestamp_str = filename.replace('tts_', '').replace('.wav', '')
                                important_timestamps.add(timestamp_str)
                            except:
                                pass

            except Exception as e:
                results["errors"].append(f"Error checking memory for important TTS files: {e}")

            # Process files for deletion
            files_to_keep = []
            files_to_delete = []

            for i, file_path in enumerate(tts_files):
                file_mtime = os.path.getmtime(file_path)
                filename = os.path.basename(file_path)

                # Extract timestamp from filename
                timestamp_str = filename.replace('tts_', '').replace('.wav', '')

                # Retention logic
                should_keep = False
                reason = ""

                # Keep recent files (within min_age_hours)
                if file_mtime > cutoff_timestamp:
                    should_keep = True
                    reason = f"recent (< {min_age_hours}h old)"

                # Keep last N files regardless of age
                elif i < max_files_to_keep:
                    should_keep = True
                    reason = f"within last {max_files_to_keep} files"

                # Keep files referenced in episodic memory
                elif timestamp_str in important_timestamps:
                    should_keep = True
                    reason = "referenced in episodic memory"

                if should_keep:
                    files_to_keep.append(file_path)
                    results["retained_files"] += 1
                    results["retention_reasons"].append(f"{filename}: {reason}")
                else:
                    files_to_delete.append(file_path)

            # Delete old files
            for file_path in files_to_delete:
                try:
                    file_size = os.path.getsize(file_path)
                    os.unlink(file_path)
                    results["files_deleted"] += 1
                    results["bytes_freed"] += file_size

                except Exception as e:
                    results["errors"].append(f"Error deleting {file_path}: {e}")

            # Log cleanup operation
            self.logger.log_event(
                event_type=EventType.MEMORY_HOUSEKEEPING,
                content=f"TTS cleanup: deleted {results['files_deleted']} files, freed {results['bytes_freed']} bytes",
                metadata={
                    "files_scanned": results["files_scanned"],
                    "files_deleted": results["files_deleted"],
                    "files_retained": results["retained_files"],
                    "bytes_freed": results["bytes_freed"],
                    "max_files_to_keep": max_files_to_keep,
                    "min_age_hours": min_age_hours
                }
            )

        except Exception as e:
            error_msg = f"TTS cleanup error: {str(e)}"
            results["errors"].append(error_msg)
            self.logger.log_event(
                event_type=EventType.ERROR_OCCURRED,
                content=error_msg,
                metadata={
                    "error_type": type(e).__name__,
                    "component": "tts_cleanup"
                }
            )

        return results

    def _rotate_reflection_log(self) -> Dict[str, Any]:
        """
        Rotate the reflection log file when it gets too large.

        Returns:
            Dictionary with rotation results
        """
        results = {
            "log_rotated": False,
            "backup_created": False,
            "bytes_freed": 0
        }

        try:
            if not os.path.exists(self.reflection_log_path):
                return results

            # Create backup filename with timestamp
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_path = f"{self.reflection_log_path}.{timestamp}"

            # Get original size
            original_size = os.path.getsize(self.reflection_log_path)

            # Move current log to backup
            shutil.move(self.reflection_log_path, backup_path)

            # Compress the backup
            compressed_path = f"{backup_path}.gz"
            with open(backup_path, 'rb') as f_in:
                with gzip.open(compressed_path, 'wb') as f_out:
                    shutil.copyfileobj(f_in, f_out)

            # Remove uncompressed backup
            os.remove(backup_path)

            # Get compressed size
            compressed_size = os.path.getsize(compressed_path)

            results.update({
                "log_rotated": True,
                "backup_created": True,
                "backup_path": compressed_path,
                "original_size_bytes": original_size,
                "compressed_size_bytes": compressed_size,
                "bytes_freed": original_size - compressed_size
            })

            print(f"[housekeeping] Reflection log rotated: {original_size} -> {compressed_size} bytes")

        except Exception as e:
            print(f"[housekeeping] Reflection log rotation error: {e}")
            results["error"] = str(e)

        return results

    def _archive_old_reflection_entries(self) -> Dict[str, Any]:
        """
        Archive reflection entries older than retention period.

        Returns:
            Dictionary with archival results
        """
        results = {
            "entries_archived": 0,
            "files_created": 0,
            "bytes_freed": 0
        }

        try:
            if not os.path.exists(self.reflection_log_path):
                return results

            # Calculate cutoff time for archival
            cutoff_time = time.time() - (self.reflection_archive_days * 24 * 3600)

            # Read and process reflection log
            entries_to_keep = []
            entries_to_archive = []

            with open(self.reflection_log_path, 'r', encoding='utf-8') as f:
                content = f.read()

            # Split into individual entries
            raw_entries = content.split('---\n')

            for entry in raw_entries:
                if not entry.strip():
                    continue

                try:
                    # Parse JSON entry
                    data = json.loads(entry.strip())
                    entry_time = data.get('timestamp', '')

                    # Convert timestamp to epoch time
                    if isinstance(entry_time, str):
                        dt = datetime.fromisoformat(entry_time.replace('Z', '+00:00'))
                        entry_epoch = dt.timestamp()
                    else:
                        entry_epoch = entry_time

                    # Decide whether to archive or keep
                    if entry_epoch < cutoff_time:
                        entries_to_archive.append(entry.strip())
                    else:
                        entries_to_keep.append(entry.strip())

                except (json.JSONDecodeError, ValueError):
                    # Keep unparseable entries
                    entries_to_keep.append(entry.strip())

            # Archive old entries if any exist
            if entries_to_archive:
                archive_result = self._create_reflection_archive(entries_to_archive)
                results["files_created"] = archive_result.get("files_created", 0)

                # Rewrite log with only recent entries
                with open(self.reflection_log_path, 'w', encoding='utf-8') as f:
                    for entry in entries_to_keep:
                        f.write(entry + '\n---\n')

                # Calculate space saved
                original_size = os.path.getsize(self.reflection_log_path) if entries_to_keep else 0
                estimated_archived_size = len('\n---\n'.join(entries_to_archive).encode('utf-8'))
                results["bytes_freed"] = estimated_archived_size

                results["entries_archived"] = len(entries_to_archive)

                print(f"[housekeeping] Archived {len(entries_to_archive)} old reflection entries")

        except Exception as e:
            print(f"[housekeeping] Reflection archival error: {e}")
            results["error"] = str(e)

        return results

    def _create_reflection_archive(self, entries: List[str]) -> Dict[str, Any]:
        """
        Create compressed archive of old reflection entries.

        Args:
            entries: List of reflection entry strings to archive

        Returns:
            Dictionary with archive creation results
        """
        results = {
            "files_created": 0,
            "archive_path": None
        }

        try:
            # Create archive directory if it doesn't exist
            archive_dir = os.path.join(os.path.dirname(self.reflection_log_path), "archives")
            os.makedirs(archive_dir, exist_ok=True)

            # Create archive filename with timestamp
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            archive_path = os.path.join(archive_dir, f"reflection_archive_{timestamp}.json.gz")

            # Create archive data structure
            archive_data = {
                "created_at": datetime.now().isoformat(),
                "entry_count": len(entries),
                "entries": entries
            }

            # Write compressed archive
            with gzip.open(archive_path, 'wt', encoding='utf-8') as f:
                json.dump(archive_data, f, indent=2)

            results.update({
                "files_created": 1,
                "archive_path": archive_path,
                "entries_archived": len(entries)
            })

            print(f"[housekeeping] Created reflection archive: {archive_path}")

        except Exception as e:
            print(f"[housekeeping] Archive creation error: {e}")
            results["error"] = str(e)

        return results

    def get_reflection_log_stats(self) -> Dict[str, Any]:
        """
        Get statistics about the reflection log system.

        Returns:
            Dictionary with reflection log statistics
        """
        stats = {
            "log_exists": False,
            "log_size_bytes": 0,
            "log_size_mb": 0.0,
            "entry_count": 0,
            "oldest_entry": None,
            "newest_entry": None,
            "archive_count": 0,
            "total_archive_size_bytes": 0
        }

        try:
            # Check main log file
            if os.path.exists(self.reflection_log_path):
                stats["log_exists"] = True
                stats["log_size_bytes"] = os.path.getsize(self.reflection_log_path)
                stats["log_size_mb"] = stats["log_size_bytes"] / (1024 * 1024)

                # Count entries and get timestamps
                with open(self.reflection_log_path, 'r', encoding='utf-8') as f:
                    content = f.read()

                entries = [e.strip() for e in content.split('---\n') if e.strip()]
                stats["entry_count"] = len(entries)

                # Get oldest and newest timestamps
                timestamps = []
                for entry in entries:
                    try:
                        data = json.loads(entry)
                        timestamp = data.get('timestamp')
                        if timestamp:
                            timestamps.append(timestamp)
                    except json.JSONDecodeError:
                        continue

                if timestamps:
                    stats["oldest_entry"] = min(timestamps)
                    stats["newest_entry"] = max(timestamps)

            # Check archives
            archive_dir = os.path.join(os.path.dirname(self.reflection_log_path), "archives")
            if os.path.exists(archive_dir):
                archive_files = [f for f in os.listdir(archive_dir) if f.startswith("reflection_archive_")]
                stats["archive_count"] = len(archive_files)

                total_archive_size = 0
                for archive_file in archive_files:
                    archive_path = os.path.join(archive_dir, archive_file)
                    total_archive_size += os.path.getsize(archive_path)

                stats["total_archive_size_bytes"] = total_archive_size

        except Exception as e:
            stats["error"] = str(e)

        return stats

    def cleanup_obsolete_scripts(self) -> Dict[str, Any]:
        """
        Clean up Python scripts marked as obsolete in their docstrings.

        Searches for .py files with "OBSOLETE" or "DEPRECATED" in their
        docstrings and moves them to an archive directory.

        Returns:
            Dictionary with cleanup statistics
        """
        results = {
            "files_scanned": 0,
            "files_archived": 0,
            "bytes_freed": 0,
            "errors": [],
            "archived_files": []
        }

        try:
            from pathlib import Path

            # Configuration
            kloros_root = Path("/home/kloros")
            archive_dir = Path("/home/kloros/.kloros/obsolete_scripts")
            enabled = os.getenv("KLR_CLEANUP_OBSOLETE_SCRIPTS", "1") == "1"

            if not enabled:
                results["disabled"] = True
                return results

            # Create archive directory if needed
            archive_dir.mkdir(parents=True, exist_ok=True)

            # Search for Python files (exclude venv, __pycache__, .kloros backups)
            exclude_dirs = {".venv", "__pycache__", ".git", ".local", ".config", ".claude"}
            python_files = []

            for py_file in kloros_root.rglob("*.py"):
                # Skip if in excluded directory
                if any(excluded in py_file.parts for excluded in exclude_dirs):
                    continue
                # Skip if already in archive
                if archive_dir in py_file.parents:
                    continue
                python_files.append(py_file)

            results["files_scanned"] = len(python_files)

            # Check each file for obsolete markers
            # Only look for patterns that indicate the FILE ITSELF is obsolete
            obsolete_patterns = [
                "THIS SCRIPT IS OBSOLETE",
                "THIS SCRIPT IS NOW OBSOLETE",
                "THIS FILE IS OBSOLETE",
                "NOW OBSOLETE",
                "SCRIPT IS OBSOLETE",
                "FILE IS OBSOLETE",
                "NOTE: THIS SCRIPT IS OBSOLETE",
                "NOTE: THIS FILE IS OBSOLETE",
                "MODULE IS OBSOLETE",
            ]

            for py_file in python_files:
                try:
                    # Read first 50 lines (docstring typically at top)
                    with open(py_file, 'r', encoding='utf-8', errors='ignore') as f:
                        first_lines = ''.join([f.readline() for _ in range(50)])

                    # Check for obsolete markers indicating file is obsolete
                    # (not just enum values or variable names containing "obsolete")
                    is_obsolete = False
                    first_lines_upper = first_lines.upper()
                    for pattern in obsolete_patterns:
                        if pattern in first_lines_upper:
                            is_obsolete = True
                            break

                    if is_obsolete:
                        # Archive the file
                        file_size = py_file.stat().st_size
                        relative_path = py_file.relative_to(kloros_root)

                        # Create subdirectories in archive to preserve structure
                        archived_path = archive_dir / relative_path
                        archived_path.parent.mkdir(parents=True, exist_ok=True)

                        # Move file to archive
                        shutil.move(str(py_file), str(archived_path))

                        results["files_archived"] += 1
                        results["bytes_freed"] += file_size
                        results["archived_files"].append(str(relative_path))

                except Exception as e:
                    results["errors"].append(f"Error processing {py_file}: {e}")

            # Log cleanup operation
            self.logger.log_event(
                event_type=EventType.MEMORY_HOUSEKEEPING,
                content=f"Obsolete scripts cleanup: archived {results['files_archived']} files",
                metadata={
                    "files_scanned": results["files_scanned"],
                    "files_archived": results["files_archived"],
                    "bytes_freed": results["bytes_freed"],
                    "archived_files": results["archived_files"]
                }
            )

        except Exception as e:
            error_msg = f"Obsolete scripts cleanup error: {str(e)}"
            results["errors"].append(error_msg)
            self.logger.log_event(
                event_type=EventType.MEMORY_HOUSEKEEPING,
                content=error_msg,
                metadata={"error": str(e)}
            )

        return results

    def sweep_obsolete_files(self) -> Dict[str, Any]:
        """
        Run obsolete file sweeper to mark stale files.

        Uses multi-signal confidence scoring:
        - Git history (no commits for N days)
        - Import/usage graph (nothing imports it)
        - System references (not in service files, etc.)
        - Filesystem timestamps (mtime fallback)

        Returns:
            Dictionary with sweep statistics
        """
        results = {
            "enabled": os.getenv("KLR_CLEANUP_OBSOLETE_SCRIPTS", "1") == "1",
            "apply_mode": os.getenv("KLR_OBSOLETE_SWEEPER_APPLY", "0") == "1",
            "candidates_found": 0,
            "files_marked": 0,
            "errors": []
        }

        if not results["enabled"]:
            results["disabled"] = True
            return results

        try:
            import subprocess
            import json

            script_path = "/home/kloros/scripts/sweep_obsolete.py"
            config_path = "/home/kloros/.kloros/obsolete_sweeper.yaml"

            # Check if script exists
            if not os.path.exists(script_path):
                results["errors"].append(f"Sweep script not found: {script_path}")
                return results

            # Build command
            cmd = [sys.executable, script_path, "--config", config_path, "--root", "/home/kloros"]
            if results["apply_mode"]:
                cmd.append("--apply")

            # Run sweeper
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=300
            )

            if result.returncode == 0:
                # Parse report from stdout
                try:
                    report = json.loads(result.stdout.split("\n\n")[0])
                    results["candidates_found"] = report.get("count", 0)
                    results["threshold_days"] = report.get("threshold_days")
                    results["grace_days"] = report.get("grace_days_after_mark")
                    results["score_threshold"] = report.get("score_threshold")

                    # Log summary
                    self.logger.log_event(
                        event_type=EventType.MEMORY_HOUSEKEEPING,
                        content=f"Obsolete sweep: {results['candidates_found']} candidates found",
                        metadata={
                            "candidates": results["candidates_found"],
                            "apply_mode": results["apply_mode"],
                            "threshold_days": results["threshold_days"]
                        }
                    )
                except json.JSONDecodeError:
                    results["errors"].append("Failed to parse sweep report")
            else:
                results["errors"].append(f"Sweep failed: {result.stderr}")

        except subprocess.TimeoutExpired:
            results["errors"].append("Sweep timed out after 300s")
        except Exception as e:
            results["errors"].append(f"Exception during sweep: {e}")

        return results

    def intelligent_file_cleanup(self) -> Dict[str, Any]:
        """
        Run intelligent file cleanup using multi-signal importance analysis.

        This uses the IntelligentCleanup module to safely remove obsolete files
        (backups, temp files, etc.) based on:
        - Git tracking status and commit history
        - File access patterns (atime, mtime)
        - Code dependency analysis (import graph)
        - Systemd service references
        - File type heuristics

        Configured via environment variables:
        - KLR_CLEANUP_DRY_RUN: "1" for dry-run (default), "0" for actual deletion
        - KLR_MIN_DELETION_CONFIDENCE: Threshold for deletion (default: 0.85)
        - KLR_CLEANUP_ARCHIVE: "1" to archive before delete (default)

        Returns:
            Dictionary with cleanup results and statistics
        """
        results = {
            "status": "success",
            "files_scanned": 0,
            "files_deleted": 0,
            "bytes_freed": 0,
            "errors": []
        }

        try:
            # Initialize intelligent cleanup
            cleanup = IntelligentCleanup(root_path="/home/kloros")

            # Define cleanup targets
            target_dirs = [
                "/home/kloros",  # Root level backups
                "/home/kloros/.kloros",  # KLoROS data directory
                "/home/kloros/src",  # Source code directory
                "/home/kloros/backups",  # Backup directory
                "/home/kloros/out",  # Output directory
            ]

            file_patterns = [
                "**/*.backup",  # Backup files
                "**/*.bak",  # Backup files
                "**/*.old",  # Old files
                "**/*.tmp",  # Temp files
                "**/*~",  # Editor backups
            ]

            # Run cleanup
            cleanup_stats = cleanup.scan_and_cleanup(target_dirs, file_patterns)

            # Extract results
            results["files_scanned"] = cleanup_stats["files_scanned"]
            results["files_deleted"] = cleanup_stats["files_deleted"]
            results["files_archived"] = cleanup_stats.get("files_archived", 0)
            results["bytes_freed"] = cleanup_stats["bytes_freed"]
            results["importance_distribution"] = cleanup_stats["importance_distribution"]

            # Check for errors
            if cleanup_stats.get("errors"):
                results["errors"].extend(cleanup_stats["errors"])

            # Log results
            if results["files_deleted"] > 0:
                self.logger.log_event(
                    event_type=EventType.MEMORY_HOUSEKEEPING,
                    content=f"Intelligent cleanup removed {results['files_deleted']} files",
                    metadata={
                        "bytes_freed": results["bytes_freed"],
                        "files_archived": results.get("files_archived", 0),
                        "importance_dist": results["importance_distribution"]
                    }
                )

        except Exception as e:
            results["status"] = "error"
            results["errors"].append(f"Intelligent cleanup failed: {e}")
            self.logger.log_error(
                error_message=str(e),
                error_type=type(e).__name__,
                component="intelligent_file_cleanup"
            )

        return results