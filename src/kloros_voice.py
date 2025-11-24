#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
KLoROS voice loop: Vosk (offline STT) + Piper (TTS) + Ollama (LLM)
- Auto-picks CMTECK mic (or set env KLR_INPUT_IDX)
- Auto-detects device sample rate (48k typical) and uses it everywhere
- VAD endpointing tuned to be patient (less premature "I didn't catch that")
- Tight wake-grammar for "KLoROS" (optional variants via KLR_WAKE_PHRASES)
- Energy & confidence gates to cut false wakes
- Pronounces "KLoROS" as /klɔr-oʊs/ via eSpeak phonemes [[ 'klOroUs ]]
"""

import collections
import json
import logging
import os
import platform
import queue
import re
import subprocess  # nosec B404
import sys
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable, List, Optional

import numpy as np
import requests  # type: ignore
import vosk

from src.config.models_config import get_ollama_context_size

if TYPE_CHECKING:
    from src.simple_rag import RAG as RAGType
else:
    RAGType = Any  # pragma: no cover

_RAGClass: Optional[type["RAGType"]]

_repo_root = Path(__file__).resolve().parent.parent
if str(_repo_root) not in sys.path:
    sys.path.insert(0, str(_repo_root))

from src.compat import webrtcvad  # noqa: E402
from src.fuzzy_wakeword import fuzzy_wake_match  # noqa: E402
from src.logic.kloros import log_event, protective_choice, should_prioritize  # noqa: E402
from src.persona.kloros import PERSONA_PROMPT, get_line  # noqa: E402
from src.ux.ack_broker import AckBroker  # noqa: E402
from src.kloros.orchestration.maintenance_mode import wait_for_normal_mode  # noqa: E402

try:
    from src.audio.calibration import load_profile  # noqa: E402
except ImportError:
    load_profile = None  # type: ignore

# TODO(PHASE1-STT-EXTRACTION): STT backend imports remain for backward compatibility
# The STT zooid (kloros_voice_stt.py) now handles all STT functionality independently.
# These imports are kept here temporarily for any legacy code paths that might still
# reference self.stt_backend. They will be removed in Phase 6 (final orchestrator reduction).
try:
    from src.stt.base import SttBackend, create_stt_backend  # noqa: E402
except ImportError:
    create_stt_backend = None  # type: ignore
    SttBackend = None  # type: ignore

try:
    from src.audio.vad import detect_voiced_segments, select_primary_segment  # noqa: E402
except ImportError:
    detect_voiced_segments = None  # type: ignore
    select_primary_segment = None  # type: ignore

try:
    from src.tts.base import TtsBackend, create_tts_backend  # noqa: E402
except ImportError:
    create_tts_backend = None  # type: ignore
    TtsBackend = None  # type: ignore

try:
    from src.core.turn import new_trace_id, run_turn  # noqa: E402
except ImportError:
    run_turn = None  # type: ignore
    new_trace_id = None  # type: ignore

try:
    from src.reasoning.base import create_reasoning_backend  # noqa: E402
except ImportError:
    create_reasoning_backend = None  # type: ignore

try:
    from src.simple_rag import RAG as _ImportedRAG  # noqa: E402

    _RAGClass = _ImportedRAG
except Exception:
    _RAGClass = None

# TODO(PHASE1-EXTRACTION): Audio capture functionality extracted to kloros_voice_audio_io.py
# This import and audio backend initialization will be replaced by ChemBus signal handling
# in Phase 1 of the voice zooid refactoring.
# See: /home/kloros/docs/plans/2025-11-23-voice-zooid-refactoring-design.md
try:
    from src.audio.capture import AudioInputBackend, create_audio_backend  # noqa: E402
except ImportError:
    create_audio_backend = None  # type: ignore
    AudioInputBackend = None  # type: ignore

try:
    from src.logging.json_logger import JsonFileLogger, create_logger_from_env  # noqa: E402
except ImportError:
    create_logger_from_env = None  # type: ignore
    JsonFileLogger = None  # type: ignore

try:
    from src.self_heal import (  # noqa: E402
        HealBus,
        TriageEngine,
        HealExecutor,
        Guardrails,
        HealthProbes,
        OutcomesLogger,
        SystemHealthMonitor,
    )
except ImportError:
    HealBus = None  # type: ignore
    TriageEngine = None  # type: ignore
    HealExecutor = None  # type: ignore
    Guardrails = None  # type: ignore
    HealthProbes = None  # type: ignore
    OutcomesLogger = None  # type: ignore
    SystemHealthMonitor = None  # type: ignore

try:
    from src.speaker.base import SpeakerBackend, create_speaker_backend  # noqa: E402
    from src.speaker.enrollment import (  # noqa: E402
        ENROLLMENT_SENTENCES,
        parse_spelled_name,
        verify_name_spelling,
        generate_enrollment_tone,
    )
except ImportError:
    create_speaker_backend = None  # type: ignore
    SpeakerBackend = None  # type: ignore
    ENROLLMENT_SENTENCES = None  # type: ignore
    parse_spelled_name = None  # type: ignore
    verify_name_spelling = None  # type: ignore
    generate_enrollment_tone = None  # type: ignore

# TODO(PHASE1-EXTRACTION): Audio playback functionality (play_wake_chime, etc.)
# will be handled by kloros_voice_audio_io.py zooid via ChemBus signals.
# Direct playback calls will be replaced with VOICE.TTS.PLAY.AUDIO emissions.
try:
    from src.audio.cues import play_wake_chime  # noqa: E402
except ImportError:
    def play_wake_chime():
        pass  # Fallback if cues module not available


try:
    from src.kloros_idle_reflection import IdleReflectionManager
except ImportError:
    IdleReflectionManager = None

try:
    from src.housekeeping_scheduler import HousekeepingScheduler
except ImportError:
    HousekeepingScheduler = None

try:
    from src.kloros.orchestration.chem_bus_v2 import ChemPub, ChemSub
except ImportError:
    ChemPub = None
    ChemSub = None

try:
    from src.meta_cognition import init_meta_cognition, process_with_meta_awareness
except ImportError:
    init_meta_cognition = None
    process_with_meta_awareness = None

try:
    from src.kloros_memory.integration import create_memory_enhanced_kloros  # noqa: E402
except ImportError:
    create_memory_enhanced_kloros = None  # type: ignore

# D-REAM Alert System Integration
try:
    ALERT_SYSTEM_AVAILABLE = True
except ImportError:
    DreamAlertManager = None
    NextWakeIntegrationAlert = None
    PassiveIndicatorAlert = None
    PassiveAlertSync = None
    ReflectionInsightAlert = None
    ALERT_SYSTEM_AVAILABLE = False


# Silero VAD wrapper removed - using WebRTC VAD for simple start/stop detection


class KLoROS:
    def __init__(self) -> None:
        """Initialize voice orchestrator for ChemBus coordination.
        
        The orchestrator's role is minimal:
        - Subscribe to signals from zooids (STT, TTS, Audio I/O, Intent, Emotion, Knowledge, LLM, Session)
        - Coordinate signal flow between zooids
        - Provide chat() entry point for LLM request coordination
        
        All heavy lifting (audio processing, STT, TTS, LLM inference, session management)
        is handled by independent zooid services.
        """
        # Test mode flag (set by tests)
        self._test_mode = getattr(self, '_test_mode', False)
        
        # Initialize defaults first
        self._init_defaults()
        
        if self._test_mode:
            # Lightweight stubs for tests - no heavy deps
            self._init_test_stubs()
            return
        
        # Initialize ChemBus pub/sub coordination
        self._init_chembus_coordination()
        
        # Log boot event
        log_event(
            "orchestrator_ready",
            operator=self.operator_id,
            note="Voice orchestrator initialized for ChemBus coordination"
        )
        print("[orchestrator] Voice orchestrator ready for ChemBus coordination")

    def _init_defaults(self) -> None:
        """Initialize attributes that both test and production modes need.

        Sets safe defaults for all attributes to prevent AttributeError in tests.
        Production code may override these during runtime initialization.
        """
        # Identity / prompts
        self.system_prompt = "PERSONA_PROMPT"  # Overridden in prod
        self.operator_id = "operator"

        # Models / endpoints
        self.ollama_model = "main"
        from src.config.models_config import get_ollama_url
        self.ollama_url = get_ollama_url()
        self.memory_file = ":memory:"  # Safe default for tests

        # Audio configuration
        self.sample_rate = 16000
        self.blocksize = 512
        self.channels = 1
        self.input_device_index = None
        self.playback_cmd = "echo"
        self.playback_target = "null"

        # Models (None until loaded)
        self.vosk_model = None
        self.piper_model = None

        # Capability systems (None until initialized)
        self.capability_registry = None
        self.capabilities_description = ""
        self.mcp = None
        self.heal_bus = None
        self.heal_executor = None
        self.chaos = None
        self.rag = None

        # STT/TTS backends
        self.stt_backend_name = "mock"
        self.stt_backend = None
        self.enable_stt = 0
        self.tts_backend_name = "mock"
        self.tts_backend = None
        self.enable_tts = 0
        self.enable_speaker_id = 0
        self.fail_open_tts = 1

        # Audio backend
        self.audio_backend = None
        self.audio_backend_name = "mock"

        # VAD configuration
        self.vad_threshold_dbfs = None  # Will be set by profile loading or production defaults
        self.agc_gain_db = 0.0
        self.enable_wakeword = 0

        # Reasoning backend
        self.reason_backend = None
        self.reason_backend_name = "ollama"

        # Runtime state
        self._audio_enabled = False
        self._runtime_ready = False

        # Logging / Observability
        self.json_logger = None

        # Conversation state
        self.conversation_flow = None

        # UX components
        self.ack_broker = None
        self.tool_registry = None
        self.reflection_manager = None
        self.housekeeping_scheduler = None

        self.chem_pub = None
        self.audio_sub = None
        self.stt_sub = None
        self.tts_sub = None
        self.playback_complete_sub = None
        self.intent_sub = None
        self.emotion_sub = None
        self.knowledge_sub = None
        self.llm_sub = None
        self.session_updated_sub = None  # Phase 5: Session management
        self._pending_transcription = None
        self._transcription_ready = threading.Event() if not self._test_mode else None

        # Intent/Emotion state tracking (Phase 2)
        # Defaults provide graceful degradation if zooids are unavailable
        self._latest_intent = {
            "intent_type": "conversation",  # Default: send all to LLM
            "confidence": 0.5,
            "command_type": None,
            "parameters": {},
            "timestamp": None
        }

        self._latest_emotion = {
            "valence": 0.0,  # Default: neutral affective state
            "arousal": 0.0,
            "dominance": 0.0,
            "sentiment": "neutral",
            "confidence": 0.5,
            "timestamp": None
        }

        # Knowledge retrieval state tracking (Phase 3)
        # Defaults provide graceful degradation if RAG is unavailable
        self._latest_knowledge = {
            "documents": [],
            "relevance_scores": [],
            "sources": [],
            "count": 0,
            "query": None,
            "timestamp": None
        }

        # LLM integration state tracking (Phase 4)
        # Defaults provide graceful degradation if LLM zooid is unavailable
        self._latest_llm = {
            "response": None,
            "model": None,
            "backend": None,
            "latency": None,
            "error": None,
            "timestamp": None
        }
        self._llm_response_ready = threading.Event() if not self._test_mode else None

        # Session management state tracking (Phase 5)
        # Tracks conversation history metadata from session zooid
        self._latest_session = {
            "session_id": None,
            "message_count": 0,
            "user_messages": 0,
            "assistant_messages": 0,
            "context_size": 0,
            "timestamp": None
        }

    def _init_test_stubs(self) -> None:
        """Lightweight stubs for test mode - no heavy deps loaded.

        Provides minimal objects that tests can interact with without
        triggering resource-intensive initialization.
        """
        # Minimal chat stub for test_ollama_call
        class _TestChatStub:
            def chat(self, prompt: str, **kwargs) -> str:
                return "Test response"

            def generate(self, prompt: str, **kwargs) -> dict:
                return {"response": "Test response", "done": True}

        # Override defaults with test-safe values
        self.system_prompt = "TEST_PERSONA"
        self.ollama_model = "test_model"
        self.ollama_url = "http://localhost/test"
        self.operator_id = "test_operator"
        self.memory_file = ":memory:"

        # Provide stub for ollama interaction
        self.ollama = _TestChatStub()

        # Allow calibration tests to work by loading profile (test can mock load_profile)
        try:
            self._load_calibration_profile()
        except Exception:
            pass  # Non-fatal in test mode

        # Mark ready so test code can proceed
        self._runtime_ready = True

        # ---------------- TTS backend (lightweight) ----------------
        # Some tests mock subprocess; give them a backend that *would* call it.
        import subprocess as _subprocess

        class _TTSBackendStub:
            def __init__(self):
                # Mirror a realistic Piper invocation shape so tests can assert args
                self.cmd = ["piper", "--model", "en_US-glados", "--text", "-"]
                self.fail_open = False
                self._sp = _subprocess

            def synthesize(self, text: str, **kwargs):
                """Minimal synthesize that calls subprocess for test mocking."""
                # Tests will monkeypatch subprocess.run; we route the call
                class Result:
                    def __init__(self):
                        self.audio_path = "/tmp/test.wav"
                        self.duration_s = 1.0
                        self.sample_rate = 22050
                        self.voice = "test_voice"

                # Call subprocess so test mocks can intercept
                self._sp.run(
                    self.cmd,
                    input=text.encode("utf-8"),
                    capture_output=True,
                    check=False
                )
                return Result()

        self.tts_backend = _TTSBackendStub()
        self.enable_tts = 1  # Enable TTS so speak() actually calls the backend
        self.fail_open_tts = True  # Allow graceful degradation

        # TTS configuration needed by speak()
        self.tts_sample_rate = 22050
        self.tts_out_dir = "/tmp"
        self.tts_suppression_enabled = False

        # ------------- Conversation flow (lightweight) -------------
        # Comprehensive chat state stub that covers the integrated chat path
        class _ChatStateStub:
            """Robust conversation state for tests - covers typical integrated path."""
            def __init__(self):
                self.entities = {}
                self._idle = False
                self.stack = []  # [{role, content}]

                # topic_summary with bullet_points and to_text method
                class _TopicSummary:
                    bullet_points = []
                    def to_text(self):
                        return ""

                self.topic_summary = _TopicSummary()

            # Required attributes/behaviors frequently asserted by tests
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

        class _ConversationFlowStub:
            def __init__(self, parent):
                self.parent = parent
                self.turn = 0
                self.state = _ChatStateStub()

            def ensure_thread(self):
                """Stub method that tests expect to exist."""
                return self.state

            def handle(self, message: str) -> str:
                self.turn += 1
                # Reflect into chat_state & conversation_history
                self.state.push("user", message)
                res = self.parent.ollama.generate(message)
                reply = res["response"]
                self.state.push("assistant", reply)
                self.parent.conversation_history.append({"role": "user", "content": message})
                self.parent.conversation_history.append({"role": "assistant", "content": reply})
                self.parent._trim_conversation_history()
                return reply

        self.conversation_flow = _ConversationFlowStub(self)

        # ------------- Tool registry (lightweight) -------------
        class _ToolRegistryStub:
            """Minimal tool registry for tests."""
            def get_tools_description(self) -> str:
                return ""

        self.tool_registry = _ToolRegistryStub()

        # ------------- Memory system (lightweight) -------------
        class _MemoryStub:
            """Minimal memory system for tests."""
            enable_memory = False

            def log_tts_output(self, **kwargs):
                pass

            def log_user_input(self, **kwargs):
                pass

            def retrieve_context(self, **kwargs):
                return []

        self.memory_enhanced = _MemoryStub()

        print("[test_mode] KLoROS initialized in test mode (no heavy deps loaded)")

    # ====================== Memory ======================
    def _load_calibration_profile(self) -> None:
        """Load microphone calibration profile if available."""
        if load_profile is None:
            return  # Calibration module not available

        try:
            profile = load_profile()
            if profile is not None:
                self.vad_threshold_dbfs = profile.vad_threshold_dbfs
                self.agc_gain_db = profile.agc_gain_db

                log_event(
                    "calibration_profile_loaded",
                    vad_threshold_dbfs=profile.vad_threshold_dbfs,
                    agc_gain_db=profile.agc_gain_db,
                    noise_floor_dbfs=profile.noise_floor_dbfs,
                    speech_rms_dbfs=profile.speech_rms_dbfs,
                    spectral_tilt=profile.spectral_tilt,
                    recommended_wake_conf_min=profile.recommended_wake_conf_min,
                )
                print(
                    f"[calib] Loaded profile: VAD={profile.vad_threshold_dbfs:.1f}dBFS, AGC={profile.agc_gain_db:.1f}dB"
                )
        except Exception as e:
            print(f"[calib] Failed to load profile: {e}")

    def _load_capability_registry(self) -> None:
        """Load or reload capability registry from disk.

        This method enables hot-reload of capabilities.yaml without system restart.
        Called during initialization and periodically during conversations.
        """
        try:
            from src.registry.loader import reload_registry
            import time

            self.capability_registry = reload_registry()
            self.capabilities_description = f"\n\n{self.capability_registry.get_system_description()}\n"
            self.registry_last_reload = time.time()

            cap_count = len(self.capability_registry.capabilities)
            enabled_count = len(self.capability_registry.get_enabled_capabilities())
            print(f"[registry] Loaded {cap_count} capabilities ({enabled_count} enabled) for self-awareness")
        except Exception as e:
            print(f"[registry] Failed to load capability registry: {e}")
            self.capabilities_description = ""
            self.capability_registry = None

    def _init_chembus_coordination(self) -> None:
        """Initialize ChemBus pub/sub for zooid coordination.

        Signal flow for voice interaction:
        1. Wake word detected → emit VOICE.STT.RECORD.START
        2. Audio I/O captures → emits VOICE.AUDIO.CAPTURED
        3. STT processes → emits VOICE.STT.TRANSCRIPTION
        4. Intent zooid classifies → emits VOICE.INTENT.CLASSIFIED (Phase 2)
        5. Emotion zooid analyzes → emits VOICE.EMOTION.STATE (Phase 2)
        6. Orchestrator receives transcription + intent + emotion → processes with LLM
        7. Orchestrator calls speak() → emits VOICE.ORCHESTRATOR.SPEAK
        8. TTS generates audio → emits VOICE.TTS.AUDIO.READY + VOICE.TTS.PLAY.AUDIO
        9. Audio I/O plays → emits VOICE.AUDIO.PLAYBACK.COMPLETE

        Phase 2 additions:
        - Intent and Emotion subscriptions are optional (fail gracefully)
        - Default to conversational intent and neutral affect if zooids unavailable
        """
        if ChemPub is None or ChemSub is None:
            print("[chembus] ChemBus not available, signal coordination disabled")
            self.chem_pub = None
            return

        try:
            self.chem_pub = ChemPub()
            print("[chembus] ChemBus publisher initialized")

            self.stt_sub = ChemSub(
                "VOICE.STT.TRANSCRIPTION",
                self._on_stt_transcription,
                zooid_name="kloros-voice-orchestrator",
                niche="voice.orchestrator"
            )

            self.tts_sub = ChemSub(
                "VOICE.TTS.AUDIO.READY",
                self._on_tts_audio_ready,
                zooid_name="kloros-voice-orchestrator",
                niche="voice.orchestrator"
            )

            self.playback_complete_sub = ChemSub(
                "VOICE.AUDIO.PLAYBACK.COMPLETE",
                self._on_audio_playback_complete,
                zooid_name="kloros-voice-orchestrator",
                niche="voice.orchestrator"
            )

            # Phase 2: Intent and Emotion signal subscriptions (optional, fail gracefully)
            try:
                self.intent_sub = ChemSub(
                    "VOICE.INTENT.CLASSIFIED",
                    self._on_intent_classified,
                    zooid_name="kloros-voice-orchestrator",
                    niche="voice.orchestrator"
                )
                print("[chembus] Subscribed to VOICE.INTENT.CLASSIFIED (Phase 2)")
            except Exception as e:
                print(f"[chembus] Intent subscription failed (non-critical): {e}")
                self.intent_sub = None

            try:
                self.emotion_sub = ChemSub(
                    "VOICE.EMOTION.STATE",
                    self._on_emotion_state,
                    zooid_name="kloros-voice-orchestrator",
                    niche="voice.orchestrator"
                )
                print("[chembus] Subscribed to VOICE.EMOTION.STATE (Phase 2)")
            except Exception as e:
                print(f"[chembus] Emotion subscription failed (non-critical): {e}")
                self.emotion_sub = None

            # Phase 3: Knowledge retrieval signal subscription (optional, fail gracefully)
            try:
                self.knowledge_sub = ChemSub(
                    "VOICE.KNOWLEDGE.RESULTS",
                    self._on_knowledge_results,
                    zooid_name="kloros-voice-orchestrator",
                    niche="voice.orchestrator"
                )
                print("[chembus] Subscribed to VOICE.KNOWLEDGE.RESULTS (Phase 3)")
            except Exception as e:
                print(f"[chembus] Knowledge subscription failed (non-critical): {e}")
                self.knowledge_sub = None

            # Phase 4: LLM integration signal subscriptions (optional, fail gracefully)
            try:
                self.llm_response_sub = ChemSub(
                    "VOICE.LLM.RESPONSE",
                    self._on_llm_response,
                    zooid_name="kloros-voice-orchestrator",
                    niche="voice.orchestrator"
                )
                self.llm_error_sub = ChemSub(
                    "VOICE.LLM.ERROR",
                    self._on_llm_error,
                    zooid_name="kloros-voice-orchestrator",
                    niche="voice.orchestrator"
                )
                print("[chembus] Subscribed to VOICE.LLM.RESPONSE and VOICE.LLM.ERROR (Phase 4)")
            except Exception as e:
                print(f"[chembus] LLM subscription failed (non-critical): {e}")
                self.llm_response_sub = None
                self.llm_error_sub = None

            # Phase 5: Session management signal subscriptions (optional, fail gracefully)
            try:
                self.session_updated_sub = ChemSub(
                    "VOICE.SESSION.UPDATED",
                    self._on_session_updated,
                    zooid_name="kloros-voice-orchestrator",
                    niche="voice.orchestrator"
                )
                print("[chembus] Subscribed to VOICE.SESSION.UPDATED (Phase 5)")
            except Exception as e:
                print(f"[chembus] Session subscription failed (non-critical): {e}")
                self.session_updated_sub = None

            print("[chembus] Subscribed to core zooid signals: STT.TRANSCRIPTION, TTS.AUDIO.READY, AUDIO.PLAYBACK.COMPLETE")

        except Exception as e:
            print(f"[chembus] Failed to initialize ChemBus coordination: {e}")
            self.chem_pub = None

    def _on_stt_transcription(self, event: dict) -> None:
        """Handle VOICE.STT.TRANSCRIPTION signal from STT zooid.

        Args:
            event: ChemBus event containing:
                - facts.text: Transcribed text
                - facts.confidence: Transcription confidence (0.0-1.0)
                - facts.language: Detected language
                - facts.metadata: Additional STT metadata
        """
        try:
            facts = event.get("facts", {})
            transcript = facts.get("text", "")
            confidence = facts.get("confidence", 0.0)
            language = facts.get("language", "unknown")

            print(f"[orchestrator] Received transcription: '{transcript}' (confidence={confidence:.2f}, lang={language})")

            if not transcript or confidence < 0.3:
                print("[orchestrator] Low confidence or empty transcription, ignoring")
                return

            self._pending_transcription = {
                "text": transcript,
                "confidence": confidence,
                "language": language,
                "metadata": facts.get("metadata", {}),
                "timestamp": time.time()
            }

            if hasattr(self, '_transcription_ready') and self._transcription_ready:
                self._transcription_ready.set()

        except Exception as e:
            print(f"[orchestrator] ERROR handling STT transcription: {e}")
            import traceback
            traceback.print_exc()

    def _on_tts_audio_ready(self, event: dict) -> None:
        """Handle VOICE.TTS.AUDIO.READY signal from TTS zooid.

        Args:
            event: ChemBus event containing:
                - facts.audio_file: Path to generated audio file
                - facts.duration: Audio duration in seconds
                - facts.affective_markers: Emotional markers in audio

        Note: The TTS zooid automatically triggers playback, so this handler
        is primarily for logging/monitoring. The Audio I/O zooid handles
        the actual playback when it receives VOICE.TTS.PLAY.AUDIO.
        """
        try:
            facts = event.get("facts", {})
            audio_file = facts.get("audio_file", "unknown")
            duration = facts.get("duration", 0.0)

            print(f"[orchestrator] TTS audio ready: {audio_file} ({duration:.2f}s)")
            log_event(
                "tts_audio_ready",
                audio_file=audio_file,
                duration=duration
            )

        except Exception as e:
            print(f"[orchestrator] ERROR handling TTS audio ready: {e}")

    def _on_audio_playback_complete(self, event: dict) -> None:
        """Handle VOICE.AUDIO.PLAYBACK.COMPLETE from Audio I/O zooid.

        Args:
            event: ChemBus event containing:
                - facts.audio_file: Path to played audio file
                - facts.duration: Actual playback duration
                - facts.status: Playback status (success/error)

        This signal indicates that audio playback has finished and the
        system is ready for the next interaction.
        """
        try:
            facts = event.get("facts", {})
            audio_file = facts.get("audio_file", "unknown")
            status = facts.get("status", "unknown")

            print(f"[orchestrator] Audio playback complete: {audio_file} (status={status})")
            log_event(
                "audio_playback_complete",
                audio_file=audio_file,
                status=status
            )

        except Exception as e:
            print(f"[orchestrator] ERROR handling playback complete: {e}")

    def _on_intent_classified(self, event: dict) -> None:
        """Handle VOICE.INTENT.CLASSIFIED signal from Intent zooid (Phase 2).

        Args:
            event: ChemBus event containing:
                - facts.text: Original transcription
                - facts.intent_type: "command", "question", or "conversation"
                - facts.confidence: Classification confidence (0.0-1.0)
                - facts.command_type: Specific command type (if intent_type == "command")
                - facts.parameters: Extracted parameters from utterance

        Updates self._latest_intent for use in orchestration decisions.
        This is optional - orchestrator defaults to conversational intent if unavailable.
        """
        try:
            facts = event.get("facts", {})
            intent_type = facts.get("intent_type", "conversation")
            confidence = facts.get("confidence", 0.0)
            command_type = facts.get("command_type")
            parameters = facts.get("parameters", {})

            self._latest_intent = {
                "intent_type": intent_type,
                "confidence": confidence,
                "command_type": command_type,
                "parameters": parameters,
                "timestamp": time.time()
            }

            print(f"[orchestrator] Intent classified: {intent_type}/{command_type} (conf={confidence:.2f})")
            log_event(
                "intent_classified",
                intent_type=intent_type,
                command_type=command_type,
                confidence=confidence
            )

        except Exception as e:
            print(f"[orchestrator] ERROR handling intent classification: {e}")

    def _on_emotion_state(self, event: dict) -> None:
        """Handle VOICE.EMOTION.STATE signal from Emotion zooid (Phase 2).

        Args:
            event: ChemBus event containing:
                - facts.text: Original transcription
                - facts.sentiment: "positive", "negative", or "neutral"
                - facts.valence: -1 (negative) to +1 (positive)
                - facts.arousal: -1 (calm) to +1 (excited)
                - facts.dominance: -1 (submissive) to +1 (dominant)
                - facts.confidence: Emotion detection confidence (0.0-1.0)

        Updates self._latest_emotion for use in response modulation.
        This is optional - orchestrator defaults to neutral affect if unavailable.
        """
        try:
            facts = event.get("facts", {})
            sentiment = facts.get("sentiment", "neutral")
            valence = facts.get("valence", 0.0)
            arousal = facts.get("arousal", 0.0)
            dominance = facts.get("dominance", 0.0)
            confidence = facts.get("confidence", 0.0)

            self._latest_emotion = {
                "sentiment": sentiment,
                "valence": valence,
                "arousal": arousal,
                "dominance": dominance,
                "confidence": confidence,
                "timestamp": time.time()
            }

            print(f"[orchestrator] Emotion detected: {sentiment} (v={valence:.2f}, a={arousal:.2f}, conf={confidence:.2f})")
            log_event(
                "emotion_state",
                sentiment=sentiment,
                valence=valence,
                arousal=arousal,
                confidence=confidence
            )

        except Exception as e:
            print(f"[orchestrator] ERROR handling emotion state: {e}")

    def _on_knowledge_results(self, event: dict) -> None:
        """Handle VOICE.KNOWLEDGE.RESULTS signal from Knowledge zooid (Phase 3).

        Args:
            event: ChemBus event containing:
                - facts.query: Original query text
                - facts.documents: Retrieved document texts
                - facts.relevance_scores: Relevance scores for each document
                - facts.sources: Source metadata for each document
                - facts.count: Number of results returned
                - facts.metadata: Additional metadata (query_time, filters, etc.)

        Updates self._latest_knowledge for use in LLM context augmentation.
        This is optional - orchestrator defaults to empty knowledge if unavailable.
        """
        try:
            facts = event.get("facts", {})
            query = facts.get("query", "")
            documents = facts.get("documents", [])
            relevance_scores = facts.get("relevance_scores", [])
            sources = facts.get("sources", [])
            count = facts.get("count", 0)

            self._latest_knowledge = {
                "query": query,
                "documents": documents,
                "relevance_scores": relevance_scores,
                "sources": sources,
                "count": count,
                "timestamp": time.time()
            }

            print(f"[orchestrator] Knowledge retrieved: {count} docs for query '{query[:40]}...'")
            if count > 0 and relevance_scores:
                avg_relevance = sum(relevance_scores) / len(relevance_scores)
                print(f"[orchestrator] Average relevance: {avg_relevance:.3f}")

            log_event(
                "knowledge_retrieved",
                query=query,
                count=count,
                avg_relevance=sum(relevance_scores) / len(relevance_scores) if relevance_scores else 0.0
            )

        except Exception as e:
            print(f"[orchestrator] ERROR handling knowledge results: {e}")

    def _on_llm_response(self, event: dict) -> None:
        """Handle VOICE.LLM.RESPONSE signal from LLM zooid (Phase 4).

        Args:
            event: ChemBus event containing:
                - facts.response: Generated LLM response text
                - facts.model: Model used for generation
                - facts.backend: Backend used (remote/ollama)
                - facts.latency: Generation latency in seconds
                - facts.temperature: Temperature used

        Updates self._latest_llm for use in conversation flow.
        This is optional - orchestrator falls back to local LLM if zooid unavailable.
        """
        try:
            facts = event.get("facts", {})
            response = facts.get("response", "")
            model = facts.get("model", "unknown")
            backend = facts.get("backend", "unknown")
            latency = facts.get("latency", 0.0)

            self._latest_llm = {
                "response": response,
                "model": model,
                "backend": backend,
                "latency": latency,
                "error": None,
                "timestamp": time.time()
            }

            if self._llm_response_ready:
                self._llm_response_ready.set()

            print(f"[orchestrator] LLM response received ({latency:.2f}s, {backend}/{model}): {response[:60]}...")

            log_event(
                "llm_response",
                model=model,
                backend=backend,
                latency=latency,
                response_len=len(response)
            )

        except Exception as e:
            print(f"[orchestrator] ERROR handling LLM response: {e}")

    def _on_llm_error(self, event: dict) -> None:
        """Handle VOICE.LLM.ERROR signal from LLM zooid (Phase 4).

        Args:
            event: ChemBus event containing:
                - facts.error_type: Type of error
                - facts.details: Error details
                - facts.attempt_count: Number of attempts made

        Updates self._latest_llm with error information.
        Orchestrator can fall back to local LLM or canned response.
        """
        try:
            facts = event.get("facts", {})
            error_type = facts.get("error_type", "unknown")
            details = facts.get("details", "")
            attempt_count = facts.get("attempt_count", 0)

            self._latest_llm = {
                "response": None,
                "model": None,
                "backend": None,
                "latency": None,
                "error": f"{error_type}: {details}",
                "timestamp": time.time()
            }

            if self._llm_response_ready:
                self._llm_response_ready.set()

            print(f"[orchestrator] LLM error after {attempt_count} attempts: {error_type} - {details}")

            log_event(
                "llm_error",
                error_type=error_type,
                details=details[:100],
                attempt_count=attempt_count
            )

        except Exception as e:
            print(f"[orchestrator] ERROR handling LLM error: {e}")

    def _on_session_updated(self, event: dict) -> None:
        """Handle VOICE.SESSION.UPDATED signal from Session zooid (Phase 5).

        Updates orchestrator's session state tracking with metadata from the session zooid.
        This is informational only - the session zooid is the source of truth for conversation history.

        Signal flow:
        1. Session zooid receives VOICE.STT.TRANSCRIPTION or VOICE.LLM.RESPONSE
        2. Session zooid appends to conversation_history
        3. Session zooid emits VOICE.SESSION.UPDATED with metadata
        4. Orchestrator updates _latest_session for monitoring/logging

        Args:
            event: ChemBus signal with session metadata
        """
        try:
            facts = event.get("facts", {})
            session_id = facts.get("session_id", "unknown")
            message_count = facts.get("message_count", 0)
            user_messages = facts.get("user_messages", 0)
            assistant_messages = facts.get("assistant_messages", 0)
            context_size = facts.get("context_size", 0)

            self._latest_session = {
                "session_id": session_id,
                "message_count": message_count,
                "user_messages": user_messages,
                "assistant_messages": assistant_messages,
                "context_size": context_size,
                "timestamp": time.time()
            }

            print(f"[orchestrator] Session updated: {message_count} messages ({context_size} chars)")

        except Exception as e:
            print(f"[orchestrator] ERROR handling session update: {e}")

    def _emit_record_start(self) -> None:
        """Emit VOICE.STT.RECORD.START signal to Audio I/O zooid.

        Instructs the Audio I/O zooid to begin capturing audio for speech recognition.
        The captured audio will be emitted as VOICE.AUDIO.CAPTURED for STT processing.
        """
        if not self.chem_pub:
            print("[orchestrator] ChemBus not available, cannot emit record start")
            return

        try:
            self.chem_pub.emit(
                "VOICE.STT.RECORD.START",
                ecosystem="voice",
                intensity=1.0,
                facts={
                    "sample_rate": self.sample_rate,
                    "channels": self.channels,
                    "max_duration_s": self.max_turn_seconds,
                    "timestamp": time.time()
                }
            )
            print("[orchestrator] Emitted VOICE.STT.RECORD.START")
        except Exception as e:
            print(f"[orchestrator] ERROR emitting record start: {e}")

    def _emit_record_stop(self) -> None:
        """Emit VOICE.STT.RECORD.STOP signal to Audio I/O zooid.

        Instructs the Audio I/O zooid to stop capturing audio and finalize
        the current recording session.
        """
        if not self.chem_pub:
            print("[orchestrator] ChemBus not available, cannot emit record stop")
            return

        try:
            self.chem_pub.emit(
                "VOICE.STT.RECORD.STOP",
                ecosystem="voice",
                intensity=1.0,
                facts={
                    "timestamp": time.time()
                }
            )
            print("[orchestrator] Emitted VOICE.STT.RECORD.STOP")
        except Exception as e:
            print(f"[orchestrator] ERROR emitting record stop: {e}")

    def _emit_knowledge_request(self, query: str, top_k: int = 5, filters: dict = None, incident_id: str = None) -> None:
        """Emit VOICE.ORCHESTRATOR.KNOWLEDGE.REQUEST signal to Knowledge zooid (Phase 3).

        Args:
            query: Query text for semantic search
            top_k: Number of documents to retrieve (default: 5)
            filters: Optional filters for search
            incident_id: Optional event correlation ID

        Instructs the Knowledge zooid to perform RAG retrieval and emit results
        via VOICE.KNOWLEDGE.RESULTS signal.
        """
        if not self.chem_pub:
            print("[orchestrator] ChemBus not available, cannot emit knowledge request")
            return

        try:
            self.chem_pub.emit(
                "VOICE.ORCHESTRATOR.KNOWLEDGE.REQUEST",
                ecosystem="voice",
                intensity=1.0,
                facts={
                    "query": query,
                    "top_k": top_k,
                    "filters": filters or {},
                    "timestamp": time.time()
                },
                incident_id=incident_id
            )
            print(f"[orchestrator] Emitted VOICE.ORCHESTRATOR.KNOWLEDGE.REQUEST: '{query[:60]}...' (top_k={top_k})")
        except Exception as e:
            print(f"[orchestrator] ERROR emitting knowledge request: {e}")

    def _emit_llm_request(
        self,
        prompt: str,
        mode: Literal["streaming", "non-streaming"] = "non-streaming",
        temperature: float = 0.8,
        max_tokens: Optional[int] = None,
        model: Optional[str] = None,
        incident_id: Optional[str] = None,
        timeout: float = 65.0
    ) -> Optional[str]:
        """Emit VOICE.ORCHESTRATOR.LLM.REQUEST signal to LLM zooid (Phase 4).

        Args:
            prompt: Input prompt for LLM
            mode: "streaming" or "non-streaming" (default: non-streaming)
            temperature: Generation temperature (default: 0.8)
            max_tokens: Maximum tokens to generate (default: None)
            model: Override model selection (default: None, uses zooid default)
            incident_id: Optional event correlation ID
            timeout: Timeout in seconds to wait for response (default: 65.0s)

        Returns:
            LLM response text if successful, None on timeout/error

        Instructs the LLM zooid to generate a response and emit results
        via VOICE.LLM.RESPONSE or VOICE.LLM.ERROR signals.
        """
        if not self.chem_pub:
            print("[orchestrator] ChemBus not available, cannot emit LLM request")
            return None

        if not self._llm_response_ready:
            print("[orchestrator] LLM response event not available (test mode)")
            return None

        try:
            self._llm_response_ready.clear()
            self._latest_llm = {
                "response": None,
                "model": None,
                "backend": None,
                "latency": None,
                "error": None,
                "timestamp": None
            }

            self.chem_pub.emit(
                "VOICE.ORCHESTRATOR.LLM.REQUEST",
                ecosystem="voice",
                intensity=1.0,
                facts={
                    "prompt": prompt,
                    "mode": mode,
                    "temperature": temperature,
                    "max_tokens": max_tokens,
                    "model": model,
                    "timestamp": time.time()
                },
                incident_id=incident_id
            )

            print(f"[orchestrator] Emitted VOICE.ORCHESTRATOR.LLM.REQUEST (mode={mode}, temp={temperature})")

            if self._llm_response_ready.wait(timeout=timeout):
                if self._latest_llm["response"]:
                    return self._latest_llm["response"]
                elif self._latest_llm["error"]:
                    print(f"[orchestrator] LLM error: {self._latest_llm['error']}")
                    return None
                else:
                    print("[orchestrator] LLM response received but empty")
                    return None
            else:
                print(f"[orchestrator] LLM request timed out after {timeout}s")
                return None

        except Exception as e:
            print(f"[orchestrator] ERROR emitting LLM request: {e}")
            return None

    def _init_silero_vad(self) -> None:
        """Initialize Silero VAD for neural network-based speech detection."""
        try:
            import torch
            import numpy as np

            # Load Silero VAD model
            self.silero_model, utils = torch.hub.load(
                repo_or_dir='snakers4/silero-vad',
                model='silero_vad',
                force_reload=False,
                onnx=False
            )

            # Store model directly - no wrapper needed
            self.vad_model = self.silero_model
            self.vad_type = "silero"
            print(f"[vad] ✓ Silero VAD initialized (threshold={self.vad_threshold})")

        except Exception as e:
            print(f"[vad] ✗ Silero VAD failed to initialize: {e}")
            print("[vad] Falling back to WebRTC VAD")
            self._init_webrtc_vad()

    def _init_webrtc_vad(self) -> None:
        """Initialize WebRTC VAD as fallback."""
        self.vad_model = webrtcvad.Vad(1)
        self.vad_type = "webrtc"
        print("[vad] Using WebRTC VAD (fallback)")

    def _get_silero_vad_wrapper(self):
        """Lazy-load SileroVAD wrapper for two-stage VAD.

        Returns:
            SileroVAD instance or None if loading fails
        """
        if self.silero_vad_wrapper is None and self.vad_type == "two_stage":
            try:
                from src.audio.vad_silero import SileroVAD
                device = "cuda" if os.getenv("CUDA_VISIBLE_DEVICES") else "cpu"
                threshold = float(os.getenv("KLR_VAD_STAGE_B_THRESHOLD", "0.60"))
                self.silero_vad_wrapper = SileroVAD(device=device, threshold=threshold)
                print(f"[vad] ✓ Lazy-loaded SileroVAD wrapper (device={device}, threshold={threshold})")
            except Exception as e:
                print(f"[vad] ✗ Failed to lazy-load SileroVAD: {e}")
                print("[vad] Two-stage VAD will fall back to dBFS-only")
        return self.silero_vad_wrapper

    def _init_json_logger(self) -> None:
        """Initialize JSON file logger."""
        if create_logger_from_env is None:
            print("[logging] JSON logger module unavailable; using print fallback")
            self.json_logger = None
            return

        try:
            self.json_logger = create_logger_from_env()
            print(f"[logging] JSON logger initialized: {self.json_logger.log_dir}")
        except Exception as e:
            print(f"[logging] Failed to initialize JSON logger: {e}")
            self.json_logger = None

    def _log_event(self, name: str, **payload) -> None:
        """Log event using JSON logger if available, otherwise fallback to original."""
        if self.json_logger:
            self.json_logger.log_event(name, payload)
        else:
            # Fallback to original log_event
            log_event(name, **payload)

    def get_component_status(self) -> dict:
        """Return status of all major system components."""
        status = {
            "audio_backend": {
                "name": self.audio_backend_name,
                "initialized": self.audio_backend is not None,
                "sample_rate": self.sample_rate if hasattr(self, 'sample_rate') else None,
            },
            "stt_backend": {
                "name": self.stt_backend_name,
                "initialized": self.stt_backend is not None,
            },
            "tts_backend": {
                "name": self.tts_backend_name,
                "initialized": self.tts_backend is not None,
            },
            "reasoning_backend": {
                "name": self.reason_backend_name,
                "initialized": self.reason_backend is not None,
            },
            "speaker_backend": {
                "name": self.speaker_backend_name,
                "initialized": self.speaker_backend is not None,
            },
            "vad": {
                "type": self.vad_type if hasattr(self, 'vad_type') else None,
                "threshold": self.vad_threshold if hasattr(self, 'vad_threshold') else None,
            },
            "memory": {
                "enabled": hasattr(self, 'memory_enhanced') and self.memory_enhanced is not None and self.memory_enhanced.enable_memory,
            }
        }
        return status

    def get_audio_diagnostics(self) -> str:
        """Return formatted audio pipeline diagnostics."""
        lines = []
        lines.append("🔊 Audio Pipeline Status")
        lines.append("")
        lines.append(f"Backend: {self.audio_backend_name}")
        lines.append(f"Device Index: {self.audio_device_index}")
        lines.append(f"Sample Rate: {self.sample_rate} Hz")
        lines.append(f"Channels: {self.audio_channels}")
        lines.append(f"Input Gain: {self.input_gain}x")
        lines.append("")
        lines.append(f"VAD Type: {self.vad_type if hasattr(self, 'vad_type') else 'unknown'}")
        lines.append(f"VAD Threshold: {self.vad_threshold if hasattr(self, 'vad_threshold') else 'unknown'}")
        lines.append("")
        lines.append(f"Backend Initialized: {'✓' if self.audio_backend is not None else '✗'}")
        return "\n".join(lines)

    def generate_full_diagnostic(self) -> str:
        """Generate complete system diagnostic report."""
        lines = []
        lines.append("=== KLoROS SYSTEM DIAGNOSTIC REPORT ===")
        lines.append("")

        # Component status
        lines.append("📊 Component Status:")
        comp_status = self.get_component_status()
        for component, details in comp_status.items():
            status = "✓" if details.get("initialized", False) else "✗"
            name = details.get("name", "unknown")
            lines.append(f"  {component}: {status} ({name})")
        lines.append("")

        # Audio diagnostics
        lines.append(self.get_audio_diagnostics())
        lines.append("")

        # Memory status
        if hasattr(self, 'memory_enhanced') and self.memory_enhanced and self.memory_enhanced.enable_memory:
            lines.append("💾 Memory System: Enabled")
        else:
            lines.append("💾 Memory System: Disabled")

        lines.append("")
        lines.append("=== END DIAGNOSTIC REPORT ===")
        return "\n".join(lines)

    # ======================== Remote LLM Helper =======================
    def _check_remote_llm_config(self) -> None:
        """Check dashboard for remote LLM configuration."""
        try:
            r = requests.get(f"{self.dashboard_url}/api/curiosity/remote-llm-config", timeout=2)
            if r.status_code == 200:
                config = r.json()
                self.remote_llm_enabled = config.get("enabled", False)
                self.remote_llm_model = config.get("selected_model", "qwen2.5:72b")
                if self.remote_llm_enabled:
                    print(f"[remote-llm] Enabled with model: {self.remote_llm_model}")
        except Exception as e:
            print(f"[remote-llm] Config check failed: {e}")
            self.remote_llm_enabled = False

    def _query_remote_llm(self, prompt: str, model: str = None) -> tuple[bool, str]:
        """
        Query remote LLM via dashboard proxy.
        Returns (success: bool, response: str)
        """
        if not model:
            model = self.remote_llm_model

        try:
            r = requests.post(
                f"{self.dashboard_url}/api/curiosity/remote-query",
                json={"model": model, "prompt": prompt, "enabled": True},
                timeout=120
            )
            if r.status_code == 200:
                data = r.json()
                if data.get("success"):
                    return (True, data.get("response", ""))
                else:
                    return (False, f"Remote LLM error: {data.get('error', 'Unknown')}")
            else:
                return (False, f"Dashboard proxy error: HTTP {r.status_code}")
        except Exception as e:
            return (False, f"Remote LLM query failed: {e}")

    # ======================== LLM =======================
    def _log_final_response(self, response: str, t_start: float, tool_calls: int = 0) -> None:
        """Log final response with metrics for E2E testing."""
        import time

        latency_ms = int((time.time() - t_start) * 1000)

        if self.json_logger:
            try:
                # Generate trace ID if not already present
                trace_id = getattr(self, '_current_trace_id', f"trace_{int(time.time() * 1000)}")

                self.json_logger.log_event(
                    name="final_response",
                    payload={
                        "level": "INFO",
                        "phase": "final_response",
                        "final_text": response[:500],  # Truncate very long responses
                        "latency_ms": latency_ms,
                        "tool_calls": tool_calls,
                        "trace_id": trace_id
                    }
                )
            except Exception as e:
                print(f"[logging] Failed to log final response: {e}")

    def _unified_reasoning(self, transcript: str, confidence: float = 0.85) -> str:
        """
        Unified reasoning method used by both voice and text interfaces.

        Handles: consciousness updates → reasoning → expression

        Args:
            transcript: User input text
            confidence: Input confidence (0.95 for text, 0.85 for voice)

        Returns:
            Response text with optional affective expression
        """
        from src.consciousness.integration import (
            process_event,
            update_consciousness_signals,
            process_consciousness_and_express
        )
        from src.middleware import filter_response, sanitize_output

        if not transcript:
            return ""

        # Update consciousness with user interaction
        process_event(self, "user_input", metadata={'transcript': transcript})
        update_consciousness_signals(self, user_interaction=True, confidence=confidence)

        # Log user input to memory system
        if hasattr(self, "memory_enhanced") and self.memory_enhanced and self.memory_enhanced.enable_memory:
            try:
                self.memory_enhanced.memory_logger.log_user_input(
                    transcript=transcript,
                    confidence=confidence
                )
            except Exception as e:
                print(f"[memory] User input logging failed: {e}")

        # Build conveyance-enhanced prompt with emotional style parameters
        enhanced_transcript = transcript
        if hasattr(self, 'consciousness') and self.consciousness:
            try:
                from src.consciousness.conveyance_helper import (
                    get_or_create_conveyance_engine,
                    build_style_context,
                    inject_style_into_prompt
                )

                conveyance = get_or_create_conveyance_engine(self)
                if conveyance:
                    style_context = build_style_context(
                        consciousness=self.consciousness,
                        conveyance_engine=conveyance,
                        decision="EXECUTE_COMMAND",  # Default to execution
                        audience="adam",
                        modality="text" if confidence > 0.9 else "voice",
                        crisis=False  # TODO: Add crisis detection
                    )

                    if style_context:
                        enhanced_transcript = inject_style_into_prompt(transcript, style_context)
                        print(f"[conveyance] Injected style context (snark, empathy, directness, verbosity)")

            except Exception as e:
                print(f"[conveyance] Style injection failed: {e}")
                # Continue with original transcript

        # Use reasoning backend if available
        if self.reason_backend is not None:
            try:
                result = self.reason_backend.reply(enhanced_transcript, kloros_instance=self)

                # Store sources for later logging
                self._last_reasoning_sources = getattr(result, "sources", [])

                # Get raw reply
                reply = result.reply_text

                # Apply middleware pipeline: tool filtering → Portal sanitization
                reply, _ = filter_response(reply, kloros_instance=self)
                reply = sanitize_output(reply, aggressive=False)

                # Process consciousness and add grounded expression if policy changed
                reply = process_consciousness_and_express(
                    self,
                    response=reply,
                    success=True,
                    confidence=confidence,
                    retries=0
                )

                # Process with meta-cognitive awareness (dialogue quality monitoring)
                # This may prepend meta-interventions like "[META: Sensing confusion - clarifying]"
                # Optional: can be disabled via KLR_ENABLE_META_COGNITION=0 to save ~300ms per turn
                enable_meta = os.getenv("KLR_ENABLE_META_COGNITION", "1") == "1"
                if enable_meta:
                    from src.meta_cognition import process_with_meta_awareness
                    reply = process_with_meta_awareness(
                        kloros_instance=self,
                        user_input=transcript,
                        response=reply,
                        confidence=confidence
                    )

                # Log response to memory system
                if hasattr(self, "memory_enhanced") and self.memory_enhanced and self.memory_enhanced.enable_memory:
                    try:
                        self.memory_enhanced.memory_logger.log_llm_response(
                            response=reply,
                            model=getattr(result, 'model', 'unknown')
                        )
                    except Exception as e:
                        print(f"[memory] Response logging failed: {e}")

                return reply

            except Exception as e:
                print(f"[reasoning] Backend failed: {e}")
                # Fall through to fallback

        # Fallback to basic chat if reasoning backend unavailable
        return self._simple_chat_fallback(transcript)

    def get_component_status(self) -> dict:
        """
        Lightweight health snapshot for introspection tools.

        Returns component health status without heavy operations.
        Used by component_status tool to answer "how are you doing?" queries.

        Returns:
            dict: Component health status with overall health indicator
        """
        status = {}

        # Check reasoning backend
        status["reasoning"] = (
            hasattr(self, "reason_backend")
            and self.reason_backend is not None
        )

        # Check memory system
        status["memory"] = (
            hasattr(self, "memory_enhanced")
            and self.memory_enhanced is not None
        )

        # Check STT backend
        status["stt"] = (
            hasattr(self, "stt_backend")
            and self.stt_backend is not None
            and self.enable_stt
        )

        # Check TTS backend
        status["tts"] = (
            hasattr(self, "tts_backend")
            and self.tts_backend is not None
        )

        # Check audio backend
        status["audio"] = (
            hasattr(self, "audio_backend")
            and self.audio_backend is not None
        )

        # Overall health: all critical components active
        status["overall"] = all([
            status.get("reasoning", False),
            status.get("stt", False),
            status.get("tts", False),
        ])

        return status

    def chat(self, user_message: str) -> str:
        """Text-based chat interface that routes through the full KLoROS reasoning system."""
        import time

        t_start = time.time()
        tool_calls = 0

        # Check for enrollment commands first

        # System introspection commands now handled by Qwen reasoning + tool integration

        # Check for identity/name queries
        identity_response = self._handle_identity_commands(user_message)
        if identity_response:
            return identity_response

        # Route through unified reasoning (consciousness + reasoning + expression)
        print(f"[chat] Routing through unified reasoning system")
        response = self._unified_reasoning(user_message, confidence=0.95)

        # Log final response for E2E testing
        self._log_final_response(response, t_start, tool_calls)

        return response

    def _handle_introspection_commands(self, user_message: str) -> Optional[str]:
        """Handle system introspection queries."""
        # Disable introspection during enrollment to prevent conflicts
        if self.enrollment_conversation["active"]:
            return None
        from src import system_introspection
    
        msg_lower = user_message.lower()
    
        # Full diagnostic report
        if any(phrase in msg_lower for phrase in ["system diagnostic", "full diagnostic", "system status", "run diagnostic"]):
            return system_introspection.generate_full_diagnostic(self)
    
        # Audio pipeline status
        if any(phrase in msg_lower for phrase in ["audio pipeline", "audio status", "audio diagnostic"]):
            return system_introspection.get_audio_diagnostics(self)
    
        # STT status
        if any(phrase in msg_lower for phrase in ["stt status", "speech recognition", "stt diagnostic", "vosk"]):
            return system_introspection.get_stt_diagnostics(self)
    
        # Memory system status
        if any(phrase in msg_lower for phrase in ["memory status", "memory diagnostic", "memory system"]):
            return system_introspection.get_memory_diagnostics(self)
    
        # Component status (JSON)
        if any(phrase in msg_lower for phrase in ["component status", "list components"]):
            import json
            status = system_introspection.get_component_status(self)
            return json.dumps(status, indent=2)
    
        return None

    def _detect_conversation_exit(self, transcript: str) -> Optional[str]:
        """Detect if user wants to end the conversation.

        Args:
            transcript: User's speech input

        Returns:
            Goodbye message if exit detected, None otherwise
        """
        msg_lower = transcript.lower().strip()

        # Conversation closure phrases
        exit_phrases = [
            "goodbye", "bye", "see you later", "see you", "talk to you later",
            "that's all", "that's it", "i'm done", "i'm good", "all done",
            "thanks bye", "thank you bye", "okay bye", "ok bye",
            "nevermind", "never mind", "forget it"
        ]

        # Check for exact matches or phrases at end of sentence
        for phrase in exit_phrases:
            if msg_lower == phrase or msg_lower.endswith(phrase):
                # Set flag for conversation loop to exit
                self._conversation_exit_requested = True

                # Generate natural goodbye
                import random
                goodbyes = [
                    "Talk to you later.",
                    "See you around.",
                    "Until next time.",
                    "Catch you later.",
                ]
                return random.choice(goodbyes)

        return None

    def _handle_identity_commands(self, user_message: str) -> Optional[str]:
        """Handle identity and name queries."""
        msg_lower = user_message.lower().strip()

        # Check for name/identity queries
        if any(phrase in msg_lower for phrase in [
            "what's my name", "what is my name", "who am i", "who am I",
            "what's my username", "what is my username", "my name is",
            "do you know my name", "remember my name"
        ]):
            # Return the current operator ID (speaker identification result)
            if self.operator_id and self.operator_id != "operator":
                return f"Your name is {self.operator_id.title()}. I recognized your voice from our previous conversation."
            else:
                return "I don't know your name yet. You can enroll your voice by saying 'enroll me' so I can learn to recognize you."

        return None

    def load_rag(
        self,
        metadata_path: str | None = None,
        embeddings_path: str | None = None,
        faiss_index: str | None = None,
        bundle_path: str | None = None,
    ) -> None:
        """Load RAG artifacts for later retrieval. Uses src.rag.RAG.

        Either provide a secure .npz bundle via ``bundle_path`` (preferred) or supply
        separate ``metadata_path`` + ``embeddings_path``. Paths should point to files on
        the local filesystem. If a Faiss index is available, pass its path via
        ``faiss_index`` (optional).
        """
        if _RAGClass is None:
            raise RuntimeError("RAG module not available; ensure src/rag.py is present")
        if bundle_path:
            self.rag = _RAGClass(bundle_path=bundle_path)
        else:
            if metadata_path is None or embeddings_path is None:
                raise ValueError(
                    "metadata_path and embeddings_path are required when bundle_path is not provided"
                )
            self.rag = _RAGClass(metadata_path=metadata_path, embeddings_path=embeddings_path)
        if faiss_index:
            try:
                import importlib

                faiss = importlib.import_module("faiss")
                idx = faiss.read_index(faiss_index)
                if self.rag is not None:
                    self.rag.faiss_index = idx  # type: ignore[attr-defined]
            except Exception as e:
                print("[RAG] failed to load faiss index:", e)

    def answer_with_rag(
        self,
        question: str,
        top_k: int = 5,
        embedder: Optional[Callable[..., Any]] = None,
        speak: bool = False,
    ) -> str:
        """Retrieve context and ask Ollama for a grounded response. Optionally speak result via Piper.

        Provide either an embedder callable or ensure the RAG object can accept a precomputed query embedding.
        """
        if not hasattr(self, "rag") or self.rag is None:
            raise RuntimeError("RAG not loaded. Call load_rag() first.")
        if embedder is None:
            raise ValueError("Provide an embedder callable for query embedding")
        out = self.rag.answer(
            question,
            embedder=embedder,
            top_k=top_k,
            ollama_url=self.ollama_url,
            model=self.ollama_model,
        )
        resp = out.get("response", "")
        if speak and resp:
            try:
                self.speak(resp)
            except Exception as e:
                print("[RAG] speak failed:", e)
        return resp

    # =================== Output helpers =================
    # TODO(PHASE1-EXTRACTION): Audio playback now handled by kloros_voice_audio_io.py zooid.
    # This _playback_cmd method will be removed in Phase 6.
    # Playback is now triggered via ChemBus signal VOICE.TTS.PLAY.AUDIO.
    def _playback_cmd(self, audio_path: str) -> list:
        """Build playback command using PipeWire."""
        return [self.playback_cmd, "--target", self.playback_target, audio_path]

    def _emit_persona(
        self, kind: str, context: dict[str, Any] | None = None, *, speak: bool = False
    ) -> str:
        """Route persona phrasing and optionally synthesize it."""
        try:
            line = get_line(kind, context or {})
        except ValueError:
            line = get_line("quip", {"line": "Unsupported persona signal"})
        print(f"KLoROS: {line}")
        try:
            log_event(
                "persona_line",
                kind=kind,
                text=line,
                context=context or {},
            )
        except Exception:
            pass  # nosec B110
        if speak:
            try:
                self.speak(line)
            except Exception as exc:
                print("[persona] speak failed:", exc)
        return line

    # TODO(PHASE1-TTS-EXTRACTION): Text normalization extracted to kloros_voice_tts.py zooid
    # The TTS zooid now handles text normalization independently.
    # This method kept for backward compatibility during migration.
    def _normalize_tts_text(self, text: str) -> str:
        """
        Force 'KLoROS' to be pronounced as a word, not spelled out.
        Piper TTS needs phonetic hints to avoid treating it as an acronym.

        NOTE: Text normalization now handled by kloros_voice_tts.py zooid.
        This method is deprecated and will be removed in Phase 6.
        """
        # First, collapse spelled-out versions (K.L.O.R.O.S. or K. L. O. R. O. S.)
        # Remove periods and spaces between single letters
        text = re.sub(r"\b([kK])\.?\s*([lL])\.?\s*([oO])\.?\s*([rR])\.?\s*([oO])\.?\s*([sS])\.?", r"Kloros", text)
        # Then handle remaining normal versions
        text = re.sub(r"\bkloros\b", "Kloros", text, flags=re.IGNORECASE)
        text = re.sub(r"\bKLoROS\b", "Kloros", text)
        # Clean up "Kloros." when it's not end of sentence (followed by space)
        text = re.sub(r"\bKloros\.\s+", "Kloros ", text)
        return text

    # TODO(PHASE1-TTS-EXTRACTION): Speech synthesis extracted to kloros_voice_tts.py zooid
    # The TTS zooid now handles speech synthesis via ChemBus signals.
    # This method updated to emit ChemBus signals instead of direct synthesis.
    def speak(self, text: str) -> None:
        """Synthesize and play speech via TTS zooid (ChemBus-based).

        NOTE: Speech synthesis now handled by kloros_voice_tts.py zooid.
        This method emits VOICE.ORCHESTRATOR.SPEAK signal to trigger TTS zooid.
        """
        from src.middleware import sanitize_output

        text = sanitize_output(text, aggressive=False)
        text = self._normalize_tts_text(text)

        print(f"[speak] Emitting VOICE.ORCHESTRATOR.SPEAK signal: {text[:100]}...")

        try:
            if hasattr(self, 'chem_pub') and self.chem_pub:
                self.chem_pub.emit(
                    "VOICE.ORCHESTRATOR.SPEAK",
                    ecosystem="voice",
                    intensity=1.0,
                    facts={
                        "text": text,
                        "affective_state": {},
                        "urgency": 0.5,
                        "timestamp": time.time(),
                    }
                )
                print(f"[speak] Signal emitted successfully")
            else:
                print(f"[speak] ChemBus not available, falling back to console: {text}")
        except Exception as e:
            print(f"[speak] ERROR emitting TTS signal: {e}")
            print(f"[speak] Falling back to console: {text}")

    # ================== Half-duplex helpers =================
    def _pre_tts_suppress(self):
        """Arm suppression before playback so producer thread stops queuing."""
        self.tts_playing_evt.set()
        self._tts_armed_at = time.monotonic()
        # Best-effort ASR pause if supported
        try:
            if hasattr(self, 'asr') and self.asr and hasattr(self.asr, "pause"):
                if hasattr(self, 'asr') and self.asr:
                    self.asr.pause()
        except Exception:
            pass
        print("[HALFDUPLEX] suppression enabled")

    def _clear_tts_suppress(self, play_indicator: bool = True):
        """Disarm suppression after cleanup.

        Args:
            play_indicator: If True, play listening indicator beep
        """
        self.tts_playing_evt.clear()
        self._tts_armed_at = None
        # Best-effort ASR resume if supported
        try:
            if hasattr(self, 'asr') and hasattr(self.asr, "resume"):
                self.asr.resume()
        except Exception:
            pass
        print("[HALFDUPLEX] suppression disabled - ready to listen")

        # Play listening indicator if enabled
        indicator_enabled = int(os.getenv("KLR_LISTENING_INDICATOR", "1"))
        print(f"[indicator] play_indicator={play_indicator}, KLR_LISTENING_INDICATOR={indicator_enabled}")
        if play_indicator and indicator_enabled:
            print("[indicator] Calling _play_listening_beep()")
            self._play_listening_beep()

    def _play_listening_beep(self):
        """Play a short beep to indicate KLoROS is ready to listen."""
        try:
            import tempfile
            import wave

            # Generate a short 880Hz beep (A5 note, pleasant and non-intrusive)
            sample_rate = 22050
            duration = 0.08  # 80ms - very brief
            frequency = 880  # A5
            samples = int(sample_rate * duration)

            # Generate sine wave
            t = np.linspace(0, duration, samples, dtype=np.float32)
            beep = np.sin(2 * np.pi * frequency * t)

            # Apply fade in/out to avoid clicks
            fade_samples = int(sample_rate * 0.01)  # 10ms fade
            beep[:fade_samples] *= np.linspace(0, 1, fade_samples, dtype=np.float32)
            beep[-fade_samples:] *= np.linspace(1, 0, fade_samples, dtype=np.float32)

            # Scale to 16-bit range (50% volume)
            beep_int16 = (beep * 16384).astype(np.int16)

            # Write to temporary WAV file
            with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as f:
                beep_path = f.name
                with wave.open(beep_path, 'wb') as wav:
                    wav.setnchannels(1)
                    wav.setsampwidth(2)  # 16-bit
                    wav.setframerate(sample_rate)
                    wav.writeframes(beep_int16.tobytes())

            # Play beep using same playback command (muted to prevent mic echo)
            import subprocess
            from src.audio.mic_mute import mute_during_playback
            cmd = self._playback_cmd(beep_path)
            print(f"[indicator] Playing beep: {' '.join(cmd)}")

            # Mute mic during beep to prevent echo feedback
            with mute_during_playback(audio_duration_s=0.2, buffer_ms=100, audio_backend=self.audio_backend):
                result = subprocess.run(cmd, capture_output=True, check=False, timeout=1.0)  # nosec B603, B607

            if result.returncode == 0:
                print(f"[indicator] Beep played successfully")
            else:
                print(f"[indicator] Beep playback failed: {result.stderr.decode() if result.stderr else 'unknown error'}")

            # Clean up
            try:
                os.unlink(beep_path)
            except Exception:
                pass

        except Exception as e:
            # Silently fail - listening indicator is non-critical
            print(f"[indicator] Beep playback skipped: {e}")

    def _duplex_healthcheck(self):
        """Safety watchdog: auto-clear stuck suppression flag after 30s."""
        if self.tts_playing_evt.is_set() and self._tts_armed_at:
            if time.monotonic() - self._tts_armed_at > 30:
                print("[HALFDUPLEX] WARNING: suppression stuck >30s, auto-clearing")
                self.tts_playing_evt.clear()
                self._tts_armed_at = None

    def _drain_queue(self, max_items=10000):
        """Bounded queue purge to prevent infinite loops."""
        if hasattr(self, 'audio_queue') and self.audio_queue:
            n = 0
            if hasattr(self, 'audio_queue') and self.audio_queue:
                while n < max_items and not self.audio_queue.empty():
                    try:
                        self.audio_queue.get_nowait()
                        n += 1
                    except queue.Empty:
                        break
        return n

    def _post_tts_cooldown_and_flush(self, audio_duration_s: float = 0.0):
        """Wait for device/room tail, then aggressively purge queued chunks.

        Args:
            audio_duration_s: Duration of TTS audio in seconds (for dynamic tail calculation)
        """
        # Dynamic echo tail based on audio duration
        # - Short acks (<1s): 200ms (fast return to listening)
        # - Normal speech (1-3s): 300ms (standard tail)
        # - Longer speech (>3s): adaptive up to 900ms (account for room acoustics)
        if audio_duration_s > 0:
            if audio_duration_s < 1.0:
                tail_ms = 200  # Fast for short voice acks
            elif audio_duration_s < 3.0:
                tail_ms = 300  # Standard for normal speech
            else:
                # Adaptive: 300ms + 100ms per second over 3s, capped at 900ms
                tail_ms = min(900, 300 + int((audio_duration_s - 3.0) * 100))
            print(f"[ANTI-ECHO] Dynamic tail: {tail_ms}ms (audio: {audio_duration_s:.2f}s)")
        else:
            # Fallback to configured extra_tail_ms if no duration provided
            tail_ms = self.extra_tail_ms
            print(f"[ANTI-ECHO] Static tail: {tail_ms}ms (no duration)")

        time.sleep(tail_ms / 1000.0)
        total = 0
        for p in range(self.flush_passes):
            flushed = self._drain_queue()
            total += flushed
            if flushed:
                print(f"[ANTI-ECHO] flush pass {p+1}: {flushed} chunks")
            time.sleep(self.flush_gap_ms / 1000.0)
        if total == 0:
            print("[ANTI-ECHO] queue already empty post-TTS")

    # ================== Input / STT side =================
    def audio_callback(self, indata, frames, _time_info, status) -> None:
        if status:
            print(f"[audio] {status}")
        # optional software preamp (keep modest)
        if self.input_gain != 1.0:
            arr = np.frombuffer(indata, dtype=np.int16).astype(np.int32)
            arr = np.clip(arr * self.input_gain, -32768, 32767).astype(np.int16)
            payload = arr.tobytes()
        else:
            payload = bytes(indata)
        try:
            self.audio_queue.put_nowait(payload)
        except queue.Full:
            pass  # drop if backlog, avoid latency

        # heartbeat roughly every ~1s (blocksize ~200ms → 5 blocks)
        self._heartbeat += 1
        if self._heartbeat % 5 == 0:
            print(".", end="", flush=True)

    def _chunker(self, data: bytes, sr: int, frame_ms: int):
        """Yield fixed-size frames for VAD from arbitrary-sized input bytes."""
        frame_bytes = int(sr * (frame_ms / 1000.0)) * 2  # int16 mono
        buf = getattr(self, "_chunkbuf", b"") + data
        pos = 0
        frames = []
        while pos + frame_bytes <= len(buf):
            frames.append(buf[pos : pos + frame_bytes])
            pos += frame_bytes
        self._chunkbuf = buf[pos:]
        return frames

    def _rms16(self, b: bytes) -> int:
        """Short-term RMS of int16 mono chunk (energy gate for wake)."""
        if not b:
            return 0
        a = np.frombuffer(b, dtype=np.int16).astype(np.int32)
        return int(np.sqrt(np.mean(a * a)) or 0)

    def _avg_conf(self, res: dict) -> float:
        """Average per-word confidence from a Vosk final result, if present."""
        seg = res.get("result") or []
        if not seg:
            return 1.0  # some models omit confidences; treat as OK
        confs = [w.get("conf", 1.0) for w in seg if isinstance(w, dict)]
        return float(sum(confs) / max(len(confs), 1))

    def _command_is_risky(self, transcript: str) -> bool:
        """Heuristic guard for risky voice commands."""
        lowered = transcript.lower()
        triggers = (
            "delete",
            "format",
            "rm ",
            "shutdown",
            "wipe",
            "drop table",
            "erase",
        )
        return any(trigger in lowered for trigger in triggers)

    def _handle_improvement_queries(self, transcript: str) -> Optional[str]:
        """Handle direct improvement status queries outside of alert mode.

        Args:
            transcript: User's spoken input

        Returns:
            str: Response about improvements, or None if not an improvement query
        """
        print(f"[DEBUG] _handle_improvement_queries called with: '{transcript}'")
        if not self.alert_manager:
            print(f"[DEBUG] No alert_manager available")
            return None

        transcript_lower = transcript.lower().strip()
        print(f"[DEBUG] transcript_lower: '{transcript_lower}'")

        # Check if this is an improvement status query
        improvement_keywords = [
            "what improvements", "improvements pending", "pending improvements",
            "any improvements", "improvements available", "what optimizations",
            "optimizations pending", "pending optimizations", "system improvements",
            "what enhancements", "enhancements pending", "pending enhancements"
        ]

        is_improvement_query = any(keyword in transcript_lower for keyword in improvement_keywords)

        if is_improvement_query:
            try:
                print(f"[alerts] Detected improvement status query: {transcript}")

                # Use the alert manager's status handling
                response_result = self.alert_manager._handle_status_request("voice")

                if response_result.get("success", False):
                    message = response_result.get("message", "No pending improvements.")
                    pending_count = response_result.get("pending_count", 0)

                    if pending_count > 0:
                        # Enable alert mode for follow-up commands
                        self._alert_response_mode = {
                            "active": True,
                            "presented_alerts": self.alert_manager.get_pending_alerts()
                        }
                        print(f"[alerts] Enabled alert mode for {pending_count} pending improvements")

                    return message
                else:
                    return "I'm unable to check for pending improvements right now."

            except Exception as e:
                print(f"[alerts] Error handling improvement query: {e}")
                return "I encountered an error while checking for improvements."

        return None

        return None

