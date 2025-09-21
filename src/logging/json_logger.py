"""Compact JSON logging with rotation for KLoROS."""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional, TextIO


class JsonFileLogger:
    """Rotating JSON logger that writes JSONL files."""

    def __init__(
        self,
        log_dir: str,
        level: str = "INFO",
        *,
        rotate_mode: str = "day",
        max_bytes: int = 1_048_576,
        backups: int = 7,
        mirror_stdout: bool = True
    ) -> None:
        """Initialize JSON file logger.

        Args:
            log_dir: Directory to write log files
            level: Log level (DEBUG|INFO|WARN|ERROR)
            rotate_mode: Rotation mode ("day" or "size")
            max_bytes: Max bytes per file if rotate_mode="size"
            backups: Number of backup files to keep
            mirror_stdout: Whether to mirror output to stdout
        """
        self.log_dir = Path(log_dir)
        self.level = level.upper()
        self.rotate_mode = rotate_mode
        self.max_bytes = max_bytes
        self.backups = backups
        self.mirror_stdout = mirror_stdout

        # Create log directory
        self.log_dir.mkdir(parents=True, exist_ok=True)

        # Current log file handle
        self._current_file: Optional[TextIO] = None
        self._current_date: Optional[str] = None

        # Log level hierarchy
        self._levels = {"DEBUG": 10, "INFO": 20, "WARN": 30, "ERROR": 40}

    def _should_log(self, level: str) -> bool:
        """Check if we should log at this level."""
        return self._levels.get(level.upper(), 20) >= self._levels.get(self.level, 20)

    def _get_current_date(self) -> str:
        """Get current date as YYYYMMDD string."""
        return datetime.now(timezone.utc).strftime("%Y%m%d")

    def _get_daily_filename(self, date: str) -> Path:
        """Get filename for daily rotation mode."""
        return self.log_dir / f"kloros-{date}.jsonl"

    def _get_size_filename(self) -> Path:
        """Get filename for size rotation mode."""
        return self.log_dir / "kloros-current.jsonl"

    def _rotate_size_files(self) -> None:
        """Rotate files for size-based rotation."""
        current_file = self._get_size_filename()

        if not current_file.exists():
            return

        # Close current file handle if open
        if self._current_file:
            self._current_file.close()
            self._current_file = None

        # Rotate backup files (kloros-N.jsonl -> kloros-(N+1).jsonl)
        for i in range(self.backups - 1, 0, -1):
            src = self.log_dir / f"kloros-{i}.jsonl"
            dst = self.log_dir / f"kloros-{i + 1}.jsonl"
            if src.exists():
                if dst.exists():
                    dst.unlink()
                src.rename(dst)

        # Move current to kloros-1.jsonl
        backup_file = self.log_dir / "kloros-1.jsonl"
        if backup_file.exists():
            backup_file.unlink()
        current_file.rename(backup_file)

    def _should_rotate_daily(self) -> bool:
        """Check if we should rotate for daily mode."""
        current_date = self._get_current_date()
        return self._current_date is None or self._current_date != current_date

    def _should_rotate_size(self) -> bool:
        """Check if we should rotate for size mode."""
        current_file = self._get_size_filename()
        if not current_file.exists():
            return False

        try:
            return current_file.stat().st_size >= self.max_bytes
        except OSError:
            return False

    def _open_log_file(self) -> TextIO:
        """Open the appropriate log file for writing."""
        if self.rotate_mode == "day":
            current_date = self._get_current_date()

            if self._should_rotate_daily():
                if self._current_file:
                    self._current_file.close()

                self._current_date = current_date
                filename = self._get_daily_filename(current_date)
                self._current_file = open(filename, 'a', encoding='utf-8')

        elif self.rotate_mode == "size":
            if self._should_rotate_size():
                self._rotate_size_files()

            if self._current_file is None:
                filename = self._get_size_filename()
                self._current_file = open(filename, 'a', encoding='utf-8')

        return self._current_file

    def log_event(self, name: str, payload: Dict[str, Any] = None) -> None:
        """Log an event as JSON.

        Args:
            name: Event name
            payload: Event payload dictionary
        """
        if payload is None:
            payload = {}

        # Check log level if specified in payload
        event_level = payload.get('level', 'INFO')
        if not self._should_log(event_level):
            return

        # Build log entry
        entry = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "level": event_level,
            "name": name,
        }

        # Add payload fields
        entry.update(payload)

        # Serialize to JSON
        json_line = json.dumps(entry, separators=(',', ':'), ensure_ascii=False)

        # Write to file
        try:
            log_file = self._open_log_file()
            if log_file:
                log_file.write(json_line + '\n')
                log_file.flush()
        except Exception as e:
            # Fallback to stderr if file writing fails
            print(f"Log write failed: {e}", file=sys.stderr)

        # Mirror to stdout if enabled
        if self.mirror_stdout:
            print(json_line, file=sys.stdout)

    def close(self) -> None:
        """Close the logger and file handles."""
        if self._current_file:
            self._current_file.close()
            self._current_file = None

    def __enter__(self) -> JsonFileLogger:
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """Context manager exit."""
        self.close()


def create_logger_from_env() -> JsonFileLogger:
    """Create a logger from environment variables."""
    log_dir = os.getenv("KLR_LOG_DIR", os.path.expanduser("~/.kloros/logs"))
    level = os.getenv("KLR_LOG_LEVEL", "INFO")
    stdout = bool(int(os.getenv("KLR_LOG_STDOUT", "1")))
    rotate_mode = os.getenv("KLR_LOG_ROTATE_MODE", "day")
    max_bytes = int(os.getenv("KLR_LOG_MAX_BYTES", "1048576"))
    backups = int(os.getenv("KLR_LOG_BACKUPS", "7"))

    return JsonFileLogger(
        log_dir=log_dir,
        level=level,
        rotate_mode=rotate_mode,
        max_bytes=max_bytes,
        backups=backups,
        mirror_stdout=stdout
    )
