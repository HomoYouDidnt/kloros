"""
Unit tests for Voice Session Management Zooid (Phase 5).

Tests cover:
- Session initialization
- Conversation history management
- STT transcription handling
- LLM response handling
- History trimming
- Session state persistence
- UMN signal emission
- Session metadata tracking
"""

import pytest
import time
import json
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock

from src.kloros_voice_session import SessionZooid


class MockUMNPub:
    """Mock UMN publisher for testing."""
    def __init__(self):
        self.signals = []

    def emit(self, signal_name, **kwargs):
        self.signals.append({
            "signal": signal_name,
            **kwargs
        })

    def get_signal_count(self, signal_name):
        return sum(1 for s in self.signals if s["signal"] == signal_name)

    def get_latest_signal(self, signal_name):
        for s in reversed(self.signals):
            if s["signal"] == signal_name:
                return s
        return None


class MockUMNSub:
    """Mock UMN subscriber for testing."""
    def __init__(self, signal_name, callback, **kwargs):
        self.signal_name = signal_name
        self.callback = callback
        self.kwargs = kwargs


@pytest.fixture
def mock_umn(monkeypatch):
    """Mock UMN for all tests."""
    mock_pub = MockUMNPub()
    mock_sub_class = MockUMNSub

    # Patch UMNPub/UMNSub where they're imported in kloros_voice_session
    monkeypatch.setattr("src.kloros_voice_session.UMNPub", lambda *args, **kwargs: mock_pub)
    monkeypatch.setattr("src.kloros_voice_session.UMNSub", mock_sub_class)

    return {"pub": mock_pub, "sub": mock_sub_class}


@pytest.fixture
def temp_persist_dir():
    """Create temporary directory for session persistence."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def zooid(mock_umn, temp_persist_dir, monkeypatch):
    """Create SessionZooid instance with mocked dependencies."""
    monkeypatch.setenv("KLR_SESSION_PERSIST_DIR", str(temp_persist_dir))
    zooid = SessionZooid()
    # Don't set chem_pub here - let start() create it via the monkeypatch
    # This ensures we use the mocked UMNPub that tracks signals
    return zooid


# ============================================================================
# Initialization Tests
# ============================================================================

class TestSessionZooidInit:
    """Test Session zooid initialization."""

    def test_init_defaults(self, zooid):
        """Test default initialization values."""
        assert zooid.zooid_name == "kloros-voice-session"
        assert zooid.niche == "voice.session"
        assert isinstance(zooid.session_id, str)
        assert len(zooid.session_id) > 0
        assert zooid.conversation_history == []
        assert zooid.max_history_entries == 100

    def test_init_statistics(self, zooid):
        """Test statistics initialization."""
        assert zooid.stats["total_messages"] == 0
        assert zooid.stats["user_messages"] == 0
        assert zooid.stats["assistant_messages"] == 0
        assert zooid.stats["truncations"] == 0
        assert zooid.stats["saves"] == 0
        assert zooid.stats["loads"] == 0

    def test_init_persistence_enabled(self, zooid):
        """Test persistence is enabled by default."""
        assert zooid.persist_enabled is True
        assert zooid.persist_dir.exists()

    def test_init_environment_variables(self, temp_persist_dir, monkeypatch):
        """Test environment variable configuration."""
        monkeypatch.setenv("KLR_SESSION_MAX_ENTRIES", "50")
        monkeypatch.setenv("KLR_SESSION_AUTOSAVE_INTERVAL", "120")
        monkeypatch.setenv("KLR_SESSION_PERSIST_DIR", str(temp_persist_dir))

        zooid = SessionZooid()
        assert zooid.max_history_entries == 50
        assert zooid.auto_save_interval == 120
        assert zooid.persist_dir == temp_persist_dir


# ============================================================================
# Startup Tests
# ============================================================================

class TestSessionZooidStart:
    """Test Session zooid startup."""

    def test_start_emits_ready_signal(self, zooid, mock_umn):
        """Test that start() emits VOICE.SESSION.READY signal."""
        zooid.start()

        ready_signals = [s for s in zooid.chem_pub.signals if s["signal"] == "VOICE.SESSION.READY"]
        assert len(ready_signals) == 1

        signal = ready_signals[0]
        assert signal["facts"]["session_id"] == zooid.session_id
        assert signal["facts"]["max_entries"] == 100
        assert signal["facts"]["persist_enabled"] is True

    def test_start_creates_subscriptions(self, zooid):
        """Test that start() creates UMN subscriptions."""
        zooid.start()

        assert zooid.stt_sub is not None
        assert zooid.llm_sub is not None
        assert zooid.stt_sub.signal_name == "VOICE.STT.TRANSCRIPTION"
        assert zooid.llm_sub.signal_name == "VOICE.LLM.RESPONSE"

    def test_start_sets_running_flag(self, zooid):
        """Test that start() sets running flag."""
        assert zooid.running is False
        zooid.start()
        assert zooid.running is True


# ============================================================================
# STT Transcription Handling Tests
# ============================================================================

class TestSTTTranscriptionHandling:
    """Test handling of VOICE.STT.TRANSCRIPTION signals."""

    def test_on_stt_transcription_appends_message(self, zooid):
        """Test that STT transcription is appended to history."""
        zooid.start()
        event = {
            "facts": {
                "text": "Hello, assistant!",
                "confidence": 0.95,
                "timestamp": time.time()
            }
        }

        zooid._on_stt_transcription(event)

        assert len(zooid.conversation_history) == 1
        msg = zooid.conversation_history[0]
        assert msg["role"] == "user"
        assert msg["content"] == "Hello, assistant!"
        assert msg["confidence"] == 0.95

    def test_on_stt_transcription_updates_stats(self, zooid):
        """Test that STT transcription updates statistics."""
        zooid.start()
        event = {
            "facts": {
                "text": "Test message",
                "confidence": 0.9,
                "timestamp": time.time()
            }
        }

        zooid._on_stt_transcription(event)

        assert zooid.stats["total_messages"] == 1
        assert zooid.stats["user_messages"] == 1
        assert zooid.stats["assistant_messages"] == 0

    def test_on_stt_transcription_emits_session_updated(self, zooid, mock_umn):
        """Test that STT transcription emits VOICE.SESSION.UPDATED signal."""
        zooid.start()
        mock_umn["pub"].signals.clear()  # Clear ready signal

        event = {
            "facts": {
                "text": "Test",
                "confidence": 0.9,
                "timestamp": time.time()
            }
        }

        zooid._on_stt_transcription(event)

        updated_signals = [s for s in zooid.chem_pub.signals if s["signal"] == "VOICE.SESSION.UPDATED"]
        assert len(updated_signals) == 1
        assert updated_signals[0]["facts"]["message_count"] == 1

    def test_on_stt_transcription_empty_text(self, zooid):
        """Test that empty transcription is skipped."""
        zooid.start()
        event = {
            "facts": {
                "text": "",
                "confidence": 0.0,
                "timestamp": time.time()
            }
        }

        zooid._on_stt_transcription(event)

        assert len(zooid.conversation_history) == 0


# ============================================================================
# LLM Response Handling Tests
# ============================================================================

class TestLLMResponseHandling:
    """Test handling of VOICE.LLM.RESPONSE signals."""

    def test_on_llm_response_appends_message(self, zooid):
        """Test that LLM response is appended to history."""
        zooid.start()
        event = {
            "facts": {
                "response": "Hello, human!",
                "model": "qwen2.5:72b",
                "backend": "remote",
                "timestamp": time.time()
            }
        }

        zooid._on_llm_response(event)

        assert len(zooid.conversation_history) == 1
        msg = zooid.conversation_history[0]
        assert msg["role"] == "assistant"
        assert msg["content"] == "Hello, human!"
        assert msg["model"] == "qwen2.5:72b"
        assert msg["backend"] == "remote"

    def test_on_llm_response_updates_stats(self, zooid):
        """Test that LLM response updates statistics."""
        zooid.start()
        event = {
            "facts": {
                "response": "Test response",
                "model": "main",
                "backend": "ollama",
                "timestamp": time.time()
            }
        }

        zooid._on_llm_response(event)

        assert zooid.stats["total_messages"] == 1
        assert zooid.stats["user_messages"] == 0
        assert zooid.stats["assistant_messages"] == 1

    def test_on_llm_response_emits_session_updated(self, zooid, mock_umn):
        """Test that LLM response emits VOICE.SESSION.UPDATED signal."""
        zooid.start()
        mock_umn["pub"].signals.clear()

        event = {
            "facts": {
                "response": "Response",
                "model": "main",
                "backend": "ollama",
                "timestamp": time.time()
            }
        }

        zooid._on_llm_response(event)

        updated_signals = [s for s in zooid.chem_pub.signals if s["signal"] == "VOICE.SESSION.UPDATED"]
        assert len(updated_signals) == 1

    def test_on_llm_response_empty_response(self, zooid):
        """Test that empty LLM response is skipped."""
        zooid.start()
        event = {
            "facts": {
                "response": "",
                "model": "main",
                "backend": "ollama",
                "timestamp": time.time()
            }
        }

        zooid._on_llm_response(event)

        assert len(zooid.conversation_history) == 0


# ============================================================================
# History Trimming Tests
# ============================================================================

class TestHistoryTrimming:
    """Test conversation history trimming."""

    def test_trim_when_exceeds_max_entries(self, zooid, monkeypatch):
        """Test that history is trimmed when exceeding max_entries."""
        monkeypatch.setattr(zooid, "max_history_entries", 5)

        # Add 10 messages
        for i in range(10):
            zooid.conversation_history.append({
                "role": "user" if i % 2 == 0 else "assistant",
                "content": f"Message {i}",
                "timestamp": time.time()
            })

        zooid._trim_conversation_history()

        assert len(zooid.conversation_history) == 5
        assert zooid.conversation_history[0]["content"] == "Message 5"
        assert zooid.stats["truncations"] == 1

    def test_no_trim_when_within_limit(self, zooid):
        """Test that history is not trimmed when within limit."""
        for i in range(50):
            zooid.conversation_history.append({
                "role": "user",
                "content": f"Message {i}",
                "timestamp": time.time()
            })

        zooid._trim_conversation_history()

        assert len(zooid.conversation_history) == 50
        assert zooid.stats["truncations"] == 0


# ============================================================================
# Session Persistence Tests
# ============================================================================

class TestSessionPersistence:
    """Test session state save/load."""

    def test_save_session_state(self, zooid):
        """Test saving session state to disk."""
        zooid.start()

        # Add some conversation history
        zooid.conversation_history = [
            {"role": "user", "content": "Hello", "timestamp": time.time()},
            {"role": "assistant", "content": "Hi there", "timestamp": time.time()}
        ]
        zooid.stats["total_messages"] = 2

        zooid._save_session_state()

        assert zooid.persist_file.exists()
        assert zooid.stats["saves"] == 1

        # Verify saved content
        with open(zooid.persist_file, 'r') as f:
            data = json.load(f)

        assert data["session_id"] == zooid.session_id
        assert len(data["conversations"]) == 2
        assert data["conversations"][0]["content"] == "Hello"

    def test_load_session_state(self, zooid):
        """Test loading session state from disk."""
        # Create a saved session file
        saved_session = {
            "session_id": "test-session-123",
            "session_start_time": time.time() - 3600,
            "conversations": [
                {"role": "user", "content": "Previous message", "timestamp": time.time()}
            ],
            "stats": {
                "total_messages": 5,
                "user_messages": 3,
                "assistant_messages": 2,
                "truncations": 0,
                "saves": 0,
                "loads": 0,
                "snapshots": 0
            }
        }

        with open(zooid.persist_file, 'w') as f:
            json.dump(saved_session, f)

        zooid._load_session_state()

        assert zooid.session_id == "test-session-123"
        assert len(zooid.conversation_history) == 1
        assert zooid.conversation_history[0]["content"] == "Previous message"
        assert zooid.stats["total_messages"] == 5
        assert zooid.stats["loads"] == 1

    def test_load_session_state_no_file(self, zooid):
        """Test loading when no saved state exists."""
        zooid._load_session_state()

        assert len(zooid.conversation_history) == 0
        assert zooid.stats["loads"] == 0

    def test_load_session_state_trim_history(self, zooid, monkeypatch):
        """Test that loaded history is trimmed if exceeds max_entries."""
        monkeypatch.setattr(zooid, "max_history_entries", 2)

        saved_session = {
            "session_id": "test-session",
            "session_start_time": time.time(),
            "conversations": [
                {"role": "user", "content": "Msg 1", "timestamp": time.time()},
                {"role": "assistant", "content": "Msg 2", "timestamp": time.time()},
                {"role": "user", "content": "Msg 3", "timestamp": time.time()},
                {"role": "assistant", "content": "Msg 4", "timestamp": time.time()}
            ],
            "stats": {}
        }

        with open(zooid.persist_file, 'w') as f:
            json.dump(saved_session, f)

        zooid._load_session_state()

        assert len(zooid.conversation_history) == 2
        assert zooid.conversation_history[0]["content"] == "Msg 3"

    def test_auto_save_when_interval_elapsed(self, zooid, monkeypatch):
        """Test that auto-save triggers when interval has elapsed."""
        monkeypatch.setattr(zooid, "auto_save_interval", 1)
        zooid.last_save_time = time.time() - 2  # 2 seconds ago
        zooid.start()

        zooid._maybe_auto_save()

        assert zooid.stats["saves"] == 1

    def test_no_auto_save_when_interval_not_elapsed(self, zooid, monkeypatch):
        """Test that auto-save does not trigger when interval hasn't elapsed."""
        monkeypatch.setattr(zooid, "auto_save_interval", 10)
        zooid.last_save_time = time.time()
        zooid.start()

        zooid._maybe_auto_save()

        assert zooid.stats["saves"] == 0


# ============================================================================
# Session Metadata Tests
# ============================================================================

class TestSessionMetadata:
    """Test session metadata tracking."""

    def test_get_session_info(self, zooid):
        """Test get_session_info returns correct metadata."""
        zooid.start()
        zooid.conversation_history = [
            {"role": "user", "content": "Hello", "timestamp": time.time()},
            {"role": "assistant", "content": "Hi", "timestamp": time.time()}
        ]
        zooid.stats["total_messages"] = 2

        info = zooid.get_session_info()

        assert info["session_id"] == zooid.session_id
        assert info["message_count"] == 2
        assert info["context_size"] == 7  # "Hello" + "Hi"
        assert "session_duration" in info
        assert info["stats"]["total_messages"] == 2

    def test_emit_session_updated(self, zooid, mock_umn):
        """Test _emit_session_updated emits correct signal."""
        zooid.start()
        mock_umn["pub"].signals.clear()

        zooid.conversation_history = [
            {"role": "user", "content": "Test", "timestamp": time.time()}
        ]
        zooid.stats["user_messages"] = 1

        zooid._emit_session_updated()

        updated_signals = [s for s in zooid.chem_pub.signals if s["signal"] == "VOICE.SESSION.UPDATED"]
        assert len(updated_signals) == 1

        facts = updated_signals[0]["facts"]
        assert facts["message_count"] == 1
        assert facts["user_messages"] == 1
        assert facts["context_size"] == 4  # "Test"


# ============================================================================
# Shutdown Tests
# ============================================================================

class TestSessionZooidShutdown:
    """Test Session zooid shutdown."""

    def test_shutdown_saves_state(self, zooid):
        """Test that shutdown saves session state."""
        zooid.start()
        zooid.conversation_history = [
            {"role": "user", "content": "Farewell", "timestamp": time.time()}
        ]

        zooid.shutdown()

        assert zooid.persist_file.exists()
        assert zooid.stats["saves"] == 1

    def test_shutdown_emits_signal(self, zooid, mock_umn):
        """Test that shutdown emits VOICE.SESSION.SHUTDOWN signal."""
        zooid.start()
        mock_umn["pub"].signals.clear()

        zooid.shutdown()

        shutdown_signals = [s for s in zooid.chem_pub.signals if s["signal"] == "VOICE.SESSION.SHUTDOWN"]
        assert len(shutdown_signals) == 1
        assert shutdown_signals[0]["facts"]["session_id"] == zooid.session_id

    def test_shutdown_clears_running_flag(self, zooid):
        """Test that shutdown clears running flag."""
        zooid.start()
        assert zooid.running is True

        zooid.shutdown()
        assert zooid.running is False
