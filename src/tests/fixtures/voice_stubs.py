"""
Voice test stubs for KLoROS unit tests.

Extracted from kloros_voice.py to keep production code clean.
These stubs provide lightweight mocks that tests can use without
loading heavy dependencies (Vosk, Piper, Ollama, etc.).

Usage:
    from tests.fixtures.voice_stubs import (
        TestChatStub,
        TTSBackendStub,
        ChatStateStub,
        ConversationFlowStub,
        MemoryStub,
        apply_test_stubs,
    )
"""

import subprocess


class TestChatStub:
    """Minimal chat stub for test_ollama_call and similar tests."""

    def chat(self, prompt: str, **kwargs) -> str:
        return "Test response"

    def generate(self, prompt: str, **kwargs) -> dict:
        return {"response": "Test response", "done": True}


class TTSBackendStub:
    """TTS backend stub that mirrors Piper invocation for test mocking.

    Tests can monkeypatch subprocess.run to intercept synthesis calls.
    """

    def __init__(self):
        self.cmd = ["piper", "--model", "en_US-glados", "--text", "-"]
        self.fail_open = False
        self._sp = subprocess

    def synthesize(self, text: str, **kwargs):
        """Minimal synthesize that calls subprocess for test mocking."""

        class Result:
            def __init__(self):
                self.audio_path = "/tmp/test.wav"
                self.duration_s = 1.0
                self.sample_rate = 22050
                self.voice = "test_voice"

        self._sp.run(
            self.cmd,
            input=text.encode("utf-8"),
            capture_output=True,
            check=False
        )
        return Result()


class TopicSummaryStub:
    """Stub for topic summary in conversation state."""
    bullet_points = []

    def to_text(self):
        return ""


class ChatStateStub:
    """Robust conversation state stub for tests.

    Covers the typical integrated chat path with message tracking.
    """

    def __init__(self):
        self.entities = {}
        self._idle = False
        self.stack = []
        self.topic_summary = TopicSummaryStub()

    def is_idle(self) -> bool:
        return self._idle

    def set_idle(self, v: bool) -> None:
        self._idle = v

    def maybe_followup(self, message: str) -> bool:
        return False

    def resolve_pronouns(self, message: str) -> str:
        return message

    def extract_entities(self, message: str):
        pass

    def push(self, role: str, content: str) -> None:
        """Track conversation messages."""
        self.stack.append({"role": role, "content": content})

    def pop(self):
        return self.stack.pop() if self.stack else None

    def peek_last(self, role=None):
        if not self.stack:
            return None
        if role is None:
            return self.stack[-1]
        for msg in reversed(self.stack):
            if msg["role"] == role:
                return msg
        return None

    @property
    def last_user_msg(self):
        m = self.peek_last("user")
        return m["content"] if m else None

    @property
    def last_bot_msg(self):
        m = self.peek_last("assistant")
        return m["content"] if m else None

    def reset_topic(self, summary=None):
        self.topic_summary.bullet_points = []
        self.stack.clear()


class ConversationFlowStub:
    """Conversation flow stub for tests.

    Args:
        parent: Parent KLoROS instance (or mock) with ollama attribute
    """

    def __init__(self, parent):
        self.parent = parent
        self.turn = 0
        self.state = ChatStateStub()

    def ensure_thread(self):
        """Stub method that tests expect to exist."""
        return self.state

    def handle(self, message: str) -> str:
        self.turn += 1
        self.state.push("user", message)
        res = self.parent.ollama.generate(message)
        reply = res["response"]
        self.state.push("assistant", reply)
        if hasattr(self.parent, 'conversation_history'):
            self.parent.conversation_history.append({"role": "user", "content": message})
            self.parent.conversation_history.append({"role": "assistant", "content": reply})
        if hasattr(self.parent, '_trim_conversation_history'):
            self.parent._trim_conversation_history()
        return reply


class MemoryStub:
    """Minimal memory system stub for tests."""
    enable_memory = False

    def log_tts_output(self, **kwargs):
        pass

    def log_user_input(self, **kwargs):
        pass

    def retrieve_context(self, **kwargs):
        return []


def apply_test_stubs(kloros_instance) -> None:
    """Apply all test stubs to a KLoROS instance.

    This configures a KLoROS instance for testing without heavy dependencies.

    Args:
        kloros_instance: KLoROS instance to configure
    """
    kloros_instance.system_prompt = "TEST_PERSONA"
    kloros_instance.ollama_model = "test_model"
    kloros_instance.ollama_url = "http://localhost/test"
    kloros_instance.operator_id = "test_operator"
    kloros_instance.memory_file = ":memory:"

    kloros_instance.ollama = TestChatStub()

    kloros_instance._runtime_ready = True

    kloros_instance.tts_backend = TTSBackendStub()
    kloros_instance.enable_tts = 1
    kloros_instance.fail_open_tts = True
    kloros_instance.tts_sample_rate = 22050
    kloros_instance.tts_out_dir = "/tmp"
    kloros_instance.tts_suppression_enabled = False

    kloros_instance.conversation_flow = ConversationFlowStub(kloros_instance)

    kloros_instance.memory_enhanced = MemoryStub()

    print("[test_mode] KLoROS configured with test stubs")
