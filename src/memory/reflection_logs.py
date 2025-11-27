"""
Reflection Log Management for KLoROS Memory System.

Provides reflection log maintenance operations including rotation,
archival, cleanup, and statistics reporting.
"""

import gzip
import json
import os
import shutil
import time
from datetime import datetime
from typing import Any, Dict, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from .logger import MemoryLogger


class ReflectionLogManager:
    """
    Manages reflection log maintenance operations.

    Handles:
    - Log rotation when size exceeds limits
    - Archival of old entries
    - Compressed backup creation
    - Statistics and health reporting
    """

    def __init__(
        self,
        logger: Optional["MemoryLogger"] = None,
        log_path: str = "/home/kloros/.kloros/reflection.log",
        max_size_mb: int = 50,
        retention_days: int = 60,
        archive_days: int = 30,
    ):
        """
        Initialize reflection log manager.

        Args:
            logger: Memory logger for tracking operations
            log_path: Path to reflection log file
            max_size_mb: Maximum log size before rotation (MB)
            retention_days: Days to retain log entries
            archive_days: Days before archiving entries
        """
        self.logger = logger
        self.log_path = log_path
        self.max_size_mb = max_size_mb
        self.retention_days = retention_days
        self.archive_days = archive_days
        self._last_cleanup: Optional[float] = None
        self._last_archive: Optional[float] = None

    def _log_event(self, event_type: Any, content: str, metadata: Dict[str, Any]) -> None:
        """Log event if logger is available."""
        if self.logger:
            self.logger.log_event(
                event_type=event_type,
                content=content,
                metadata=metadata
            )

    def cleanup(self) -> Dict[str, Any]:
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
            if not os.path.exists(self.log_path):
                return results

            log_size_bytes = os.path.getsize(self.log_path)
            log_size_mb = log_size_bytes / (1024 * 1024)

            if log_size_mb > self.max_size_mb:
                rotation_result = self._rotate_log()
                results.update(rotation_result)

            archive_result = self._archive_old_entries()
            results["entries_archived"] = archive_result.get("entries_archived", 0)
            results["archive_files_created"] += archive_result.get("files_created", 0)
            results["bytes_freed"] += archive_result.get("bytes_freed", 0)

            self._last_cleanup = time.time()

            if self.logger:
                from .models import EventType
                self._log_event(
                    event_type=EventType.MEMORY_HOUSEKEEPING,
                    content="Reflection log cleanup completed",
                    metadata={
                        "log_size_mb": log_size_mb,
                        "log_rotated": results["log_rotated"],
                        "entries_archived": results["entries_archived"],
                        "bytes_freed": results["bytes_freed"],
                        "cleanup_timestamp": self._last_cleanup
                    }
                )

        except Exception as e:
            error_msg = f"Reflection log cleanup error: {str(e)}"
            results["errors"].append(error_msg)
            if self.logger:
                from .models import EventType
                self._log_event(
                    event_type=EventType.ERROR_OCCURRED,
                    content=error_msg,
                    metadata={
                        "error_type": type(e).__name__,
                        "component": "reflection_log_cleanup"
                    }
                )

        return results

    def _rotate_log(self) -> Dict[str, Any]:
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
            if not os.path.exists(self.log_path):
                return results

            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_path = f"{self.log_path}.{timestamp}"

            original_size = os.path.getsize(self.log_path)

            shutil.move(self.log_path, backup_path)

            compressed_path = f"{backup_path}.gz"
            with open(backup_path, 'rb') as f_in:
                with gzip.open(compressed_path, 'wb') as f_out:
                    shutil.copyfileobj(f_in, f_out)

            os.remove(backup_path)

            compressed_size = os.path.getsize(compressed_path)

            results.update({
                "log_rotated": True,
                "backup_created": True,
                "backup_path": compressed_path,
                "original_size_bytes": original_size,
                "compressed_size_bytes": compressed_size,
                "bytes_freed": original_size - compressed_size
            })

            print(f"[reflection_logs] Log rotated: {original_size} -> {compressed_size} bytes")

        except Exception as e:
            print(f"[reflection_logs] Rotation error: {e}")
            results["error"] = str(e)

        return results

    def _archive_old_entries(self) -> Dict[str, Any]:
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
            if not os.path.exists(self.log_path):
                return results

            cutoff_time = time.time() - (self.archive_days * 24 * 3600)

            entries_to_keep = []
            entries_to_archive = []

            with open(self.log_path, 'r', encoding='utf-8') as f:
                content = f.read()

            raw_entries = content.split('---\n')

            for entry in raw_entries:
                if not entry.strip():
                    continue

                try:
                    data = json.loads(entry.strip())
                    entry_time = data.get('timestamp', '')

                    if isinstance(entry_time, str):
                        dt = datetime.fromisoformat(entry_time.replace('Z', '+00:00'))
                        entry_epoch = dt.timestamp()
                    else:
                        entry_epoch = entry_time

                    if entry_epoch < cutoff_time:
                        entries_to_archive.append(entry.strip())
                    else:
                        entries_to_keep.append(entry.strip())

                except (json.JSONDecodeError, ValueError):
                    entries_to_keep.append(entry.strip())

            if entries_to_archive:
                archive_result = self._create_archive(entries_to_archive)
                results["files_created"] = archive_result.get("files_created", 0)

                with open(self.log_path, 'w', encoding='utf-8') as f:
                    for entry in entries_to_keep:
                        f.write(entry + '\n---\n')

                estimated_archived_size = len('\n---\n'.join(entries_to_archive).encode('utf-8'))
                results["bytes_freed"] = estimated_archived_size

                results["entries_archived"] = len(entries_to_archive)

                print(f"[reflection_logs] Archived {len(entries_to_archive)} old entries")

        except Exception as e:
            print(f"[reflection_logs] Archival error: {e}")
            results["error"] = str(e)

        return results

    def _create_archive(self, entries: List[str]) -> Dict[str, Any]:
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
            archive_dir = os.path.join(os.path.dirname(self.log_path), "archives")
            os.makedirs(archive_dir, exist_ok=True)

            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            archive_path = os.path.join(archive_dir, f"reflection_archive_{timestamp}.json.gz")

            archive_data = {
                "created_at": datetime.now().isoformat(),
                "entry_count": len(entries),
                "entries": entries
            }

            with gzip.open(archive_path, 'wt', encoding='utf-8') as f:
                json.dump(archive_data, f, indent=2)

            results.update({
                "files_created": 1,
                "archive_path": archive_path,
                "entries_archived": len(entries)
            })

            print(f"[reflection_logs] Created archive: {archive_path}")

        except Exception as e:
            print(f"[reflection_logs] Archive creation error: {e}")
            results["error"] = str(e)

        return results

    def get_stats(self) -> Dict[str, Any]:
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
            if os.path.exists(self.log_path):
                stats["log_exists"] = True
                stats["log_size_bytes"] = os.path.getsize(self.log_path)
                stats["log_size_mb"] = stats["log_size_bytes"] / (1024 * 1024)

                with open(self.log_path, 'r', encoding='utf-8') as f:
                    content = f.read()

                entries = [e.strip() for e in content.split('---\n') if e.strip()]
                stats["entry_count"] = len(entries)

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

            archive_dir = os.path.join(os.path.dirname(self.log_path), "archives")
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
