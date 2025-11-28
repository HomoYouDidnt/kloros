"""
File cleanup service for memory system.

Extracted from housekeeping.py - provides comprehensive file system cleanup
operations including Python cache, backup files, TTS outputs, and script
management.

This service handles file operations that were previously inline in
MemoryHousekeeper, centralizing file cleanup logic.
"""

import logging
import time
from typing import Any, Dict, List, Optional

from src.orchestration.core.umn_bus import UMNSub, UMNPub

logger = logging.getLogger(__name__)

try:
    from src.cognition.mind.memory.file_cleanup import FileCleanupManager
    from src.cognition.mind.memory.intelligent_cleanup import IntelligentCleanup
    from src.cognition.mind.memory.logger import MemoryLogger
    from src.cognition.mind.memory.models import EventType
    HAS_MEMORY = True
except ImportError:
    HAS_MEMORY = False
    FileCleanupManager = None
    IntelligentCleanup = None
    MemoryLogger = None
    EventType = None


class FileCleanupService:
    """
    File cleanup service for episodic memory system.

    Provides:
    - Python cache cleanup (.pyc files, __pycache__ directories)
    - Backup file rotation and cleanup
    - TTS output file management
    - Obsolete script detection and archival
    - Comprehensive file sweeping with obsolescence detection
    - Intelligent cleanup with multi-signal confidence scoring

    Can operate as UMN subscriber for agentic housekeeping architecture.
    """

    def __init__(self, memory_logger: Optional['MemoryLogger'] = None):
        """
        Initialize file cleanup service.

        Args:
            memory_logger: Optional MemoryLogger for event tracking
        """
        self.memory_logger = memory_logger
        self._file_cleanup_manager: Optional['FileCleanupManager'] = None
        self._intelligent_cleanup: Optional['IntelligentCleanup'] = None

        self._umn_sub: Optional[UMNSub] = None
        self._umn_pub: Optional[UMNPub] = None

    @property
    def file_cleanup_manager(self) -> 'FileCleanupManager':
        """Lazy-load file cleanup manager."""
        if self._file_cleanup_manager is None and HAS_MEMORY:
            self._file_cleanup_manager = FileCleanupManager(
                logger=self.memory_logger
            )
        return self._file_cleanup_manager

    @property
    def intelligent_cleanup(self) -> 'IntelligentCleanup':
        """Lazy-load intelligent cleanup system."""
        if self._intelligent_cleanup is None and HAS_MEMORY:
            self._intelligent_cleanup = IntelligentCleanup()
        return self._intelligent_cleanup

    def subscribe_to_umn(self) -> None:
        """Subscribe to UMN for agentic housekeeping."""
        self._umn_pub = UMNPub()
        self._umn_sub = UMNSub(
            topic="Q_HOUSEKEEPING.FILE_CLEANUP",
            on_json=self._handle_file_cleanup_request,
            zooid_name="file_cleanup_service",
            niche="memory"
        )
        logger.info("[file_cleanup] Subscribed to Q_HOUSEKEEPING.FILE_CLEANUP")

    def _handle_file_cleanup_request(self, msg: dict) -> None:
        """Handle UMN request for file cleanup."""
        request_id = msg.get('request_id', 'unknown')
        operation = msg.get('facts', {}).get('operation', 'full')

        try:
            results = {}

            if operation in ('full', 'python_cache'):
                results['python_cache'] = self.cleanup_python_cache()

            if operation in ('full', 'backup_files'):
                results['backup_files'] = self.cleanup_backup_files()

            if operation in ('full', 'tts_outputs'):
                results['tts_outputs'] = self.cleanup_tts_outputs()

            if operation in ('full', 'obsolete_scripts'):
                results['obsolete_scripts'] = self.cleanup_obsolete_scripts()

            if operation in ('full', 'sweep_obsolete'):
                results['sweep_obsolete'] = self.sweep_obsolete_files()

            if operation in ('full', 'intelligent_cleanup'):
                results['intelligent_cleanup'] = self.intelligent_file_cleanup()

            self._umn_pub.emit(
                signal="Q_HOUSEKEEPING.FILE_CLEANUP.COMPLETE",
                ecosystem="memory",
                facts={
                    'request_id': request_id,
                    'success': True,
                    'results': results
                }
            )

        except Exception as e:
            logger.error(f"[file_cleanup] Error during operation: {e}", exc_info=True)
            if self._umn_pub:
                self._umn_pub.emit(
                    signal="Q_HOUSEKEEPING.FILE_CLEANUP.COMPLETE",
                    ecosystem="memory",
                    facts={
                        'request_id': request_id,
                        'success': False,
                        'error': str(e)
                    }
                )

    def cleanup_python_cache(self) -> Dict[str, Any]:
        """
        Clean up Python cache files and directories.

        Removes .pyc files and __pycache__ directories to free disk space
        and prevent stale bytecode issues.

        Returns:
            Dictionary with cleanup results
        """
        if not HAS_MEMORY or self.file_cleanup_manager is None:
            logger.warning("[file_cleanup] File cleanup manager not available")
            return {"error": "Service not available"}

        try:
            results = self.file_cleanup_manager.cleanup_python_cache()
            logger.info(f"[file_cleanup] Python cache cleanup: {results}")
            return results
        except Exception as e:
            logger.error(f"[file_cleanup] Error during python cache cleanup: {e}", exc_info=True)
            return {
                "error": str(e),
                "pyc_files_deleted": 0,
                "pycache_dirs_deleted": 0,
                "bytes_freed": 0,
                "errors": [str(e)]
            }

    def cleanup_backup_files(self) -> Dict[str, Any]:
        """
        Clean up excessive backup files.

        Manages backup file rotation based on configuration,
        preserving important backups while removing redundant ones.

        Returns:
            Dictionary with cleanup results
        """
        if not HAS_MEMORY or self.file_cleanup_manager is None:
            logger.warning("[file_cleanup] File cleanup manager not available")
            return {"error": "Service not available"}

        try:
            results = self.file_cleanup_manager.cleanup_backup_files()
            logger.info(f"[file_cleanup] Backup files cleanup: {results}")
            return results
        except Exception as e:
            logger.error(f"[file_cleanup] Error during backup cleanup: {e}", exc_info=True)
            return {
                "error": str(e),
                "files_scanned": 0,
                "files_deleted": 0,
                "files_retained": 0,
                "bytes_freed": 0,
                "errors": [str(e)]
            }

    def cleanup_tts_outputs(self) -> Dict[str, Any]:
        """
        Clean up TTS output files.

        Reviews TTS outputs and purges old files after memory processing,
        keeping recent files and any that might be referenced in episodic memory.

        Returns:
            Dictionary with cleanup results
        """
        if not HAS_MEMORY or self.file_cleanup_manager is None:
            logger.warning("[file_cleanup] File cleanup manager not available")
            return {"error": "Service not available"}

        try:
            results = self.file_cleanup_manager.cleanup_tts_outputs()
            logger.info(f"[file_cleanup] TTS outputs cleanup: {results}")
            return results
        except Exception as e:
            logger.error(f"[file_cleanup] Error during TTS cleanup: {e}", exc_info=True)
            return {
                "error": str(e),
                "files_scanned": 0,
                "files_deleted": 0,
                "bytes_freed": 0,
                "retained_files": 0,
                "errors": [str(e)]
            }

    def cleanup_obsolete_scripts(self) -> Dict[str, Any]:
        """
        Clean up Python scripts marked as obsolete.

        Searches for .py files with "OBSOLETE" markers in their
        docstrings and moves them to an archive directory.

        Returns:
            Dictionary with cleanup statistics
        """
        if not HAS_MEMORY or self.file_cleanup_manager is None:
            logger.warning("[file_cleanup] File cleanup manager not available")
            return {"error": "Service not available"}

        try:
            results = self.file_cleanup_manager.cleanup_obsolete_scripts()
            logger.info(f"[file_cleanup] Obsolete scripts cleanup: {results}")
            return results
        except Exception as e:
            logger.error(f"[file_cleanup] Error during obsolete scripts cleanup: {e}", exc_info=True)
            return {
                "error": str(e),
                "files_scanned": 0,
                "files_archived": 0,
                "bytes_freed": 0,
                "errors": [str(e)]
            }

    def sweep_obsolete_files(self) -> Dict[str, Any]:
        """
        Run obsolete file sweeper.

        Uses multi-signal confidence scoring:
        - Git history (no commits for N days)
        - Import/usage graph (nothing imports it)
        - System references (not in service files, etc.)
        - Filesystem timestamps (mtime fallback)

        Returns:
            Dictionary with sweep statistics
        """
        if not HAS_MEMORY or self.file_cleanup_manager is None:
            logger.warning("[file_cleanup] File cleanup manager not available")
            return {"error": "Service not available"}

        try:
            results = self.file_cleanup_manager.sweep_obsolete_files()
            logger.info(f"[file_cleanup] Obsolete files sweep: {results}")
            return results
        except Exception as e:
            logger.error(f"[file_cleanup] Error during sweep: {e}", exc_info=True)
            return {
                "error": str(e),
                "enabled": False,
                "candidates_found": 0,
                "files_marked": 0,
                "errors": [str(e)]
            }

    def intelligent_file_cleanup(self) -> Dict[str, Any]:
        """
        Run intelligent file cleanup with multi-signal analysis.

        Performs comprehensive cleanup using importance scoring across:
        - Git history and tracking status
        - File access patterns
        - Code dependency analysis
        - System references
        - File type and location heuristics

        Returns:
            Dictionary with cleanup statistics
        """
        if not HAS_MEMORY or self.intelligent_cleanup is None:
            logger.warning("[file_cleanup] Intelligent cleanup not available")
            return {"error": "Service not available"}

        try:
            results = self.intelligent_cleanup.scan_and_cleanup(
                target_dirs=["/home/kloros"],
                file_patterns=["*.tmp", "*.log", "*.bak", "*.backup*"]
            )
            logger.info(f"[file_cleanup] Intelligent cleanup: {results}")
            return results
        except Exception as e:
            logger.error(f"[file_cleanup] Error during intelligent cleanup: {e}", exc_info=True)
            return {
                "error": str(e),
                "files_scanned": 0,
                "files_analyzed": 0,
                "files_deleted": 0,
                "bytes_freed": 0,
                "errors": [str(e)]
            }

    def shutdown(self) -> None:
        """Close UMN subscriptions."""
        if self._umn_sub:
            self._umn_sub.close()
            logger.info("[file_cleanup] Closed UMN subscription")
