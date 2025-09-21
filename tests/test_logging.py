"""Unit tests for JSON logging system."""

import json
import os
import time
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from scripts.trace_view import (
    filter_entries,
    find_log_files,
    format_entry,
    parse_time_window,
    read_log_entries,
)
from src.logging.json_logger import JsonFileLogger, create_logger_from_env


class TestJsonFileLogger:
    """Test JSON file logger functionality."""

    def test_writes_jsonl_and_flushes(self, tmp_path):
        """Test that logger writes JSONL and flushes to disk."""
        log_dir = tmp_path / "logs"

        with JsonFileLogger(str(log_dir), mirror_stdout=False) as logger:
            logger.log_event("test_event", {"key": "value", "number": 42})

        # Check that file was created
        log_files = list(log_dir.glob("*.jsonl"))
        assert len(log_files) == 1

        # Read and verify content
        with open(log_files[0], 'r') as f:
            line = f.readline().strip()
            entry = json.loads(line)

        # Verify structure
        assert entry["name"] == "test_event"
        assert entry["key"] == "value"
        assert entry["number"] == 42
        assert "ts" in entry
        assert "level" in entry

        # Verify timestamp format
        ts = datetime.fromisoformat(entry["ts"].replace('Z', '+00:00'))
        assert isinstance(ts, datetime)

    def test_daily_rotation(self, tmp_path):
        """Test daily rotation by mocking date changes."""
        log_dir = tmp_path / "logs"

        logger = JsonFileLogger(str(log_dir), rotate_mode="day", mirror_stdout=False)

        # Mock first date
        with patch('src.logging.json_logger.datetime') as mock_dt:
            mock_dt.now.return_value = datetime(2025, 9, 21, 12, 0, 0, tzinfo=timezone.utc)
            mock_dt.fromisoformat = datetime.fromisoformat
            logger.log_event("day1_event", {"day": 1})

        # Mock second date
        with patch('src.logging.json_logger.datetime') as mock_dt:
            mock_dt.now.return_value = datetime(2025, 9, 22, 12, 0, 0, tzinfo=timezone.utc)
            mock_dt.fromisoformat = datetime.fromisoformat
            logger.log_event("day2_event", {"day": 2})

        logger.close()

        # Should have two files
        log_files = sorted(log_dir.glob("*.jsonl"))
        assert len(log_files) == 2

        # Verify filenames
        expected_files = ["kloros-20250921.jsonl", "kloros-20250922.jsonl"]
        actual_files = [f.name for f in log_files]
        assert actual_files == expected_files

        # Verify content
        with open(log_files[0], 'r') as f:
            entry1 = json.loads(f.readline().strip())
        with open(log_files[1], 'r') as f:
            entry2 = json.loads(f.readline().strip())

        assert entry1["name"] == "day1_event"
        assert entry2["name"] == "day2_event"

    def test_size_rotation(self, tmp_path):
        """Test size-based rotation with small max_bytes."""
        log_dir = tmp_path / "logs"

        # Use very small max_bytes to force rotation
        logger = JsonFileLogger(
            str(log_dir),
            rotate_mode="size",
            max_bytes=100,  # Very small
            backups=3,
            mirror_stdout=False
        )

        # Write several events to trigger rotation
        for i in range(10):
            logger.log_event("big_event", {
                "iteration": i,
                "data": "x" * 50  # Make entries large enough to trigger rotation
            })

        logger.close()

        # Should have current file plus backups
        log_files = list(log_dir.glob("*.jsonl"))
        assert len(log_files) >= 2  # current + at least one backup

        # Verify backup naming
        backup_files = [f for f in log_files if f.name.startswith("kloros-") and f.name != "kloros-current.jsonl"]
        assert len(backup_files) >= 1

    def test_log_levels(self, tmp_path):
        """Test log level filtering."""
        log_dir = tmp_path / "logs"

        logger = JsonFileLogger(str(log_dir), level="WARN", mirror_stdout=False)

        # These should be logged (WARN and above)
        logger.log_event("warn_event", {"level": "WARN", "message": "warning"})
        logger.log_event("error_event", {"level": "ERROR", "message": "error"})

        # These should be filtered out (below WARN)
        logger.log_event("info_event", {"level": "INFO", "message": "info"})
        logger.log_event("debug_event", {"level": "DEBUG", "message": "debug"})

        logger.close()

        # Read all entries
        log_files = list(log_dir.glob("*.jsonl"))
        assert len(log_files) == 1

        entries = []
        with open(log_files[0], 'r') as f:
            for line in f:
                entries.append(json.loads(line.strip()))

        # Should only have WARN and ERROR events
        assert len(entries) == 2
        assert entries[0]["name"] == "warn_event"
        assert entries[1]["name"] == "error_event"

    def test_preserves_trace_id(self, tmp_path):
        """Test that existing trace_id is preserved."""
        log_dir = tmp_path / "logs"

        logger = JsonFileLogger(str(log_dir), mirror_stdout=False)
        trace_id = "abc123def456"

        logger.log_event("traced_event", {
            "trace_id": trace_id,
            "data": "test"
        })

        logger.close()

        # Verify trace_id is preserved
        log_files = list(log_dir.glob("*.jsonl"))
        with open(log_files[0], 'r') as f:
            entry = json.loads(f.readline().strip())

        assert entry["trace_id"] == trace_id

    def test_stdout_mirroring(self, tmp_path, capsys):
        """Test stdout mirroring functionality."""
        log_dir = tmp_path / "logs"

        # Test with mirroring enabled
        logger = JsonFileLogger(str(log_dir), mirror_stdout=True)
        logger.log_event("stdout_test", {"mirror": True})
        logger.close()

        captured = capsys.readouterr()
        assert "stdout_test" in captured.out

        # Test with mirroring disabled
        logger = JsonFileLogger(str(log_dir), mirror_stdout=False)
        logger.log_event("no_stdout_test", {"mirror": False})
        logger.close()

        captured = capsys.readouterr()
        assert "no_stdout_test" not in captured.out

    def test_create_logger_from_env(self, tmp_path):
        """Test creating logger from environment variables."""
        test_env = {
            "KLR_LOG_DIR": str(tmp_path / "env_logs"),
            "KLR_LOG_LEVEL": "DEBUG",
            "KLR_LOG_STDOUT": "0",
            "KLR_LOG_ROTATE_MODE": "size",
            "KLR_LOG_MAX_BYTES": "2048",
            "KLR_LOG_BACKUPS": "5"
        }

        with patch.dict(os.environ, test_env):
            logger = create_logger_from_env()

        assert str(logger.log_dir) == test_env["KLR_LOG_DIR"]
        assert logger.level == "DEBUG"
        assert logger.mirror_stdout is False
        assert logger.rotate_mode == "size"
        assert logger.max_bytes == 2048
        assert logger.backups == 5

        logger.close()


class TestTraceViewer:
    """Test trace viewer functionality."""

    def test_parse_time_window(self):
        """Test time window parsing."""
        now = datetime.now(timezone.utc)

        # Test minutes
        result = parse_time_window("15m")
        expected = now - timedelta(minutes=15)
        assert abs((result - expected).total_seconds()) < 1

        # Test hours
        result = parse_time_window("2h")
        expected = now - timedelta(hours=2)
        assert abs((result - expected).total_seconds()) < 1

        # Test days
        result = parse_time_window("1d")
        expected = now - timedelta(days=1)
        assert abs((result - expected).total_seconds()) < 1

    def test_find_log_files(self, tmp_path):
        """Test finding log files in directory."""
        log_dir = tmp_path / "logs"
        log_dir.mkdir()

        # Create some log files with different timestamps
        file1 = log_dir / "kloros-20250921.jsonl"
        file2 = log_dir / "kloros-20250922.jsonl"
        file3 = log_dir / "other.txt"

        file1.write_text("log1")
        time.sleep(0.01)  # Ensure different mtimes
        file2.write_text("log2")
        file3.write_text("not a log")

        # Find log files
        log_files = find_log_files(str(log_dir))

        # Should find .jsonl files, sorted by mtime (newest first)
        assert len(log_files) == 2
        assert log_files[0].name == "kloros-20250922.jsonl"  # Newer
        assert log_files[1].name == "kloros-20250921.jsonl"  # Older

    def test_read_log_entries(self, tmp_path):
        """Test reading and filtering log entries by time."""
        log_dir = tmp_path / "logs"
        log_dir.mkdir()

        # Create log file with entries at different times
        log_file = log_dir / "test.jsonl"
        entries = [
            {"ts": "2025-09-21T10:00:00Z", "name": "old_event", "data": "old"},
            {"ts": "2025-09-21T12:00:00Z", "name": "recent_event", "data": "recent"},
            {"ts": "2025-09-21T14:00:00Z", "name": "new_event", "data": "new"}
        ]

        with open(log_file, 'w') as f:
            for entry in entries:
                f.write(json.dumps(entry) + '\n')

        # Read with time filter
        since = datetime(2025, 9, 21, 11, 0, 0, tzinfo=timezone.utc)
        result = read_log_entries([log_file], since)

        # Should get 2 entries (recent and new)
        assert len(result) == 2
        assert result[0]["name"] == "recent_event"
        assert result[1]["name"] == "new_event"

    def test_filter_entries(self):
        """Test filtering entries by trace_id and names."""
        entries = [
            {"trace_id": "abc123", "name": "event1", "data": "test1"},
            {"trace_id": "def456", "name": "event2", "data": "test2"},
            {"trace_id": "abc789", "name": "event1", "data": "test3"},
            {"trace_id": "ghi012", "name": "event3", "data": "test4"}
        ]

        # Filter by trace_id prefix
        result = filter_entries(entries, trace_id="abc")
        assert len(result) == 2
        assert all(e["trace_id"].startswith("abc") for e in result)

        # Filter by event names
        result = filter_entries(entries, names=["event1", "event3"])
        assert len(result) == 3
        assert all(e["name"] in ["event1", "event3"] for e in result)

        # Filter by both
        result = filter_entries(entries, trace_id="abc", names=["event1"])
        assert len(result) == 2
        assert all(e["trace_id"].startswith("abc") and e["name"] == "event1" for e in result)

    def test_format_entry(self):
        """Test formatting log entries for display."""
        entry = {
            "ts": "2025-09-21T13:37:12Z",
            "trace_id": "abc123def456",
            "name": "stt_done",
            "level": "INFO",
            "confidence": 0.95,
            "lang": "en-US",
            "duration_ms": 85
        }

        result = format_entry(entry)

        # Should contain key components
        assert "13:37:12Z" in result
        assert "abc123…" in result  # Truncated trace_id
        assert "stt_done" in result
        assert "conf=0.95" in result
        assert "lang=en-US" in result
        assert "duration_ms=85ms" in result

    def test_trace_view_filters(self, tmp_path):
        """Test end-to-end trace view filtering."""
        log_dir = tmp_path / "logs"
        log_dir.mkdir()

        # Create log file with diverse entries
        log_file = log_dir / "test.jsonl"
        entries = [
            {
                "ts": "2025-09-21T13:37:00Z",
                "trace_id": "abc123",
                "name": "turn_start",
                "level": "INFO"
            },
            {
                "ts": "2025-09-21T13:37:01Z",
                "trace_id": "abc123",
                "name": "vad_gate",
                "open": True,
                "thr": -48.0
            },
            {
                "ts": "2025-09-21T13:37:02Z",
                "trace_id": "abc123",
                "name": "stt_done",
                "confidence": 0.95,
                "lang": "en-US"
            },
            {
                "ts": "2025-09-21T13:37:03Z",
                "trace_id": "def456",
                "name": "turn_start",
                "level": "INFO"
            }
        ]

        with open(log_file, 'w') as f:
            for entry in entries:
                f.write(json.dumps(entry) + '\n')

        # Test reading all entries
        all_entries = read_log_entries([log_file], datetime.min.replace(tzinfo=timezone.utc))
        assert len(all_entries) == 4

        # Test filtering by trace_id
        filtered = filter_entries(all_entries, trace_id="abc123")
        assert len(filtered) == 3
        assert all(e["trace_id"] == "abc123" for e in filtered)

        # Test filtering by name
        filtered = filter_entries(all_entries, names=["turn_start"])
        assert len(filtered) == 2
        assert all(e["name"] == "turn_start" for e in filtered)

        # Test combined filtering
        filtered = filter_entries(all_entries, trace_id="abc123", names=["vad_gate", "stt_done"])
        assert len(filtered) == 2
        assert all(e["trace_id"] == "abc123" and e["name"] in ["vad_gate", "stt_done"] for e in filtered)
