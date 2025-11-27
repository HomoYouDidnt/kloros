"""
File Cleanup Operations for KLoROS Memory System.

Provides file system cleanup operations including Python cache,
backup files, TTS outputs, and obsolete script management.
"""

import glob
import os
import shutil
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from .logger import MemoryLogger
    from .storage import MemoryStore


class FileCleanupManager:
    """
    Manages file system cleanup operations.

    Handles cleanup of:
    - Python cache files (__pycache__, .pyc)
    - Backup files (*.backup*, etc.)
    - TTS output files
    - Obsolete/deprecated scripts
    """

    def __init__(
        self,
        logger: Optional["MemoryLogger"] = None,
        store: Optional["MemoryStore"] = None,
        kloros_root: Path = Path("/home/kloros"),
    ):
        """
        Initialize file cleanup manager.

        Args:
            logger: Memory logger for tracking cleanup operations
            store: Memory store for checking file references
            kloros_root: Root directory for KLoROS system
        """
        self.logger = logger
        self.store = store
        self.kloros_root = kloros_root

    def _log_event(self, event_type: Any, content: str, metadata: Dict[str, Any]) -> None:
        """Log event if logger is available."""
        if self.logger:
            self.logger.log_event(
                event_type=event_type,
                content=content,
                metadata=metadata
            )

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
            max_scan_depth = int(os.getenv("KLR_CACHE_SCAN_DEPTH", "10"))

            pyc_pattern = str(self.kloros_root / "**" / "*.pyc")
            pyc_files = []

            for depth in range(max_scan_depth):
                pattern = str(self.kloros_root / ("**/" * depth) / "*.pyc")
                pyc_files.extend(glob.glob(pattern))

            pyc_files = list(set(pyc_files))

            for pyc_file in pyc_files:
                try:
                    file_size = os.path.getsize(pyc_file)
                    os.unlink(pyc_file)
                    results["pyc_files_deleted"] += 1
                    results["bytes_freed"] += file_size
                except Exception as e:
                    results["errors"].append(f"Failed to remove {pyc_file}: {e}")

            pycache_dirs = []
            for root, dirs, files in os.walk(self.kloros_root):
                if "__pycache__" in dirs:
                    pycache_path = os.path.join(root, "__pycache__")
                    pycache_dirs.append(pycache_path)

            for cache_dir in pycache_dirs:
                try:
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

            if self.logger:
                from .models import EventType
                self._log_event(
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

        return results

    def cleanup_backup_files(self) -> Dict[str, Any]:
        """
        Clean up excessive backup files, keeping only the most recent ones.

        Manages backup file rotation based on configuration,
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
            max_backups_per_file = int(os.getenv("KLR_MAX_BACKUPS_PER_FILE", "3"))
            backup_retention_days = int(os.getenv("KLR_BACKUP_RETENTION_DAYS", "30"))

            backup_patterns = [
                "*.backup*",
                "*.py.backup*",
                "*backup-*"
            ]

            all_backup_files = []
            for pattern in backup_patterns:
                backup_files = list(self.kloros_root.rglob(pattern))
                all_backup_files.extend(backup_files)

            all_backup_files = list(set(all_backup_files))
            results["files_scanned"] = len(all_backup_files)

            if not all_backup_files:
                return results

            backup_groups: Dict[str, List[Path]] = {}
            for backup_file in all_backup_files:
                base_name = str(backup_file.name)
                for suffix in [".backup", "backup-", ".backup-"]:
                    if suffix in base_name:
                        base_name = base_name.split(suffix)[0]
                        break

                if base_name not in backup_groups:
                    backup_groups[base_name] = []
                backup_groups[base_name].append(backup_file)

            cutoff_time = time.time() - (backup_retention_days * 86400)

            for base_name, backup_files in backup_groups.items():
                backup_files.sort(key=lambda f: f.stat().st_mtime, reverse=True)

                for i, backup_file in enumerate(backup_files):
                    file_mtime = backup_file.stat().st_mtime
                    should_keep = False
                    reason = ""

                    if file_mtime > cutoff_time:
                        should_keep = True
                        reason = f"recent (< {backup_retention_days} days)"
                    elif i < max_backups_per_file:
                        should_keep = True
                        reason = f"within last {max_backups_per_file} backups for {base_name}"
                    elif any(keyword in backup_file.name.lower() for keyword in ["phase", "deployment", "critical", "important"]):
                        should_keep = True
                        reason = "important backup (phase/deployment/critical)"

                    if should_keep:
                        results["files_retained"] += 1
                        results["retention_reasons"].append(f"{backup_file.name}: {reason}")
                    else:
                        try:
                            file_size = backup_file.stat().st_size
                            backup_file.unlink()
                            results["files_deleted"] += 1
                            results["bytes_freed"] += file_size
                        except Exception as e:
                            results["errors"].append(f"Error deleting {backup_file}: {e}")

            if self.logger:
                from .models import EventType
                self._log_event(
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
            tts_output_dir = os.path.expanduser("~/.kloros/out")
            max_files_to_keep = int(os.getenv("KLR_TTS_MAX_FILES", "50"))
            min_age_hours = int(os.getenv("KLR_TTS_MIN_AGE_HOURS", "6"))

            if not os.path.exists(tts_output_dir):
                return results

            tts_pattern = os.path.join(tts_output_dir, "tts_*.wav")
            tts_files = glob.glob(tts_pattern)
            results["files_scanned"] = len(tts_files)

            if not tts_files:
                return results

            tts_files.sort(key=lambda f: os.path.getmtime(f), reverse=True)

            cutoff_time = datetime.now() - timedelta(hours=min_age_hours)
            cutoff_timestamp = cutoff_time.timestamp()

            important_timestamps: set = set()
            if self.store:
                try:
                    from .models import EventType
                    start_time = (datetime.now() - timedelta(hours=24)).timestamp()
                    recent_events = self.store.get_events(
                        event_type=EventType.TTS_OUTPUT,
                        start_time=start_time,
                        limit=100
                    )

                    for event in recent_events:
                        metadata = getattr(event, 'metadata', {})
                        if isinstance(metadata, dict) and 'file_path' in metadata:
                            file_path = metadata['file_path']
                            if 'tts_' in file_path:
                                try:
                                    filename = os.path.basename(file_path)
                                    timestamp_str = filename.replace('tts_', '').replace('.wav', '')
                                    important_timestamps.add(timestamp_str)
                                except Exception:
                                    pass

                except Exception as e:
                    results["errors"].append(f"Error checking memory for important TTS files: {e}")

            files_to_delete = []

            for i, file_path in enumerate(tts_files):
                file_mtime = os.path.getmtime(file_path)
                filename = os.path.basename(file_path)
                timestamp_str = filename.replace('tts_', '').replace('.wav', '')

                should_keep = False
                reason = ""

                if file_mtime > cutoff_timestamp:
                    should_keep = True
                    reason = f"recent (< {min_age_hours}h old)"
                elif i < max_files_to_keep:
                    should_keep = True
                    reason = f"within last {max_files_to_keep} files"
                elif timestamp_str in important_timestamps:
                    should_keep = True
                    reason = "referenced in episodic memory"

                if should_keep:
                    results["retained_files"] += 1
                    results["retention_reasons"].append(f"{filename}: {reason}")
                else:
                    files_to_delete.append(file_path)

            for file_path in files_to_delete:
                try:
                    file_size = os.path.getsize(file_path)
                    os.unlink(file_path)
                    results["files_deleted"] += 1
                    results["bytes_freed"] += file_size
                except Exception as e:
                    results["errors"].append(f"Error deleting {file_path}: {e}")

            if self.logger:
                from .models import EventType
                self._log_event(
                    event_type=EventType.MEMORY_HOUSEKEEPING,
                    content=f"TTS cleanup: deleted {results['files_deleted']} files, retained {results['retained_files']} files",
                    metadata={
                        "files_scanned": results["files_scanned"],
                        "files_deleted": results["files_deleted"],
                        "bytes_freed": results["bytes_freed"],
                        "retained_files": results["retained_files"]
                    }
                )

        except Exception as e:
            error_msg = f"TTS cleanup error: {str(e)}"
            results["errors"].append(error_msg)

        return results

    def cleanup_obsolete_scripts(self) -> Dict[str, Any]:
        """
        Clean up Python scripts marked as obsolete in their docstrings.

        Searches for .py files with "OBSOLETE" markers in their
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
            archive_dir = Path("/home/kloros/.kloros/obsolete_scripts")
            enabled = os.getenv("KLR_CLEANUP_OBSOLETE_SCRIPTS", "1") == "1"

            if not enabled:
                results["disabled"] = True
                return results

            archive_dir.mkdir(parents=True, exist_ok=True)

            exclude_dirs = {".venv", "__pycache__", ".git", ".local", ".config", ".claude"}
            python_files = []

            for py_file in self.kloros_root.rglob("*.py"):
                if any(excluded in py_file.parts for excluded in exclude_dirs):
                    continue
                if archive_dir in py_file.parents:
                    continue
                python_files.append(py_file)

            results["files_scanned"] = len(python_files)

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
                    with open(py_file, 'r', encoding='utf-8', errors='ignore') as f:
                        first_lines = ''.join([f.readline() for _ in range(50)])

                    is_obsolete = False
                    first_lines_upper = first_lines.upper()
                    for pattern in obsolete_patterns:
                        if pattern in first_lines_upper:
                            is_obsolete = True
                            break

                    if is_obsolete:
                        file_size = py_file.stat().st_size
                        relative_path = py_file.relative_to(self.kloros_root)

                        archived_path = archive_dir / relative_path
                        archived_path.parent.mkdir(parents=True, exist_ok=True)

                        shutil.move(str(py_file), str(archived_path))

                        results["files_archived"] += 1
                        results["bytes_freed"] += file_size
                        results["archived_files"].append(str(relative_path))

                except Exception as e:
                    results["errors"].append(f"Error processing {py_file}: {e}")

            if self.logger:
                from .models import EventType
                self._log_event(
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
        import subprocess
        import json

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
            script_path = "/home/kloros/scripts/sweep_obsolete.py"
            config_path = "/home/kloros/.kloros/obsolete_sweeper.yaml"

            if not os.path.exists(script_path):
                results["errors"].append(f"Sweep script not found: {script_path}")
                return results

            cmd = [sys.executable, script_path, "--config", config_path, "--root", "/home/kloros"]
            if results["apply_mode"]:
                cmd.append("--apply")

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=300
            )

            if result.returncode == 0:
                try:
                    report = json.loads(result.stdout.split("\n\n")[0])
                    results["candidates_found"] = report.get("count", 0)
                    results["threshold_days"] = report.get("threshold_days")
                    results["grace_days"] = report.get("grace_days_after_mark")
                    results["score_threshold"] = report.get("score_threshold")

                    if self.logger:
                        from .models import EventType
                        self._log_event(
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
