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
    from src.dream_alerts.alert_manager import DreamAlertManager
    from src.dream_alerts.next_wake_integration import NextWakeIntegrationAlert
    from src.dream_alerts.passive_indicators import PassiveIndicatorAlert
    from src.dream_alerts.passive_sync import PassiveAlertSync
    from src.dream_alerts.reflection_insight_alert import ReflectionInsightAlert
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
        # -------------------- Mode Detection --------------------
        self._test_mode = os.getenv("KLR_TEST_MODE") == "1"

        # Initialize defaults that both test and production need
        self._init_defaults()

        if self._test_mode:
            # Lightweight stubs for tests - no heavy deps
            self._init_test_stubs()
            return

        # -------------------- Config --------------------
        # system prompt defined in persona module to keep voice logic slim
        self.system_prompt = PERSONA_PROMPT

        from src.config.models_config import get_ollama_model, get_ollama_url
        self.memory_file = os.path.expanduser("~/KLoROS/kloros_memory.json")
        self.ollama_model = get_ollama_model()
        self.ollama_url = f"{get_ollama_url()}/api/generate"
        self.operator_id = os.getenv("KLR_OPERATOR_ID", "operator")

        # Remote LLM configuration (via dashboard proxy to ALTIMITOS)
        self.dashboard_url = "http://localhost:8765"
        self.remote_llm_enabled = False
        self.remote_llm_model = "qwen2.5:72b"  # Default model
        self._check_remote_llm_config()

        # C2C (Cache-to-Cache) semantic communication
        self.c2c_enabled = os.getenv("KLR_C2C_ENABLED", "1") == "1"
        self.c2c_manager = None
        self.last_ollama_context = None
        if self.c2c_enabled:
            try:
                from src.c2c import C2CManager
                self.c2c_manager = C2CManager()
                print("[C2C] Cache-to-Cache enabled for voice system")
            except ImportError:
                print("[C2C] Failed to import C2CManager, disabling C2C")
                self.c2c_enabled = False

        self.rag: Optional["RAGType"] = None

        # -------------------- Capability Registry (Self-Awareness) --------------------
        # Load capability registry at initialization with hot-reload support
        # This enables KLoROS to always know what systems she has integrated
        self.capability_registry = None
        self.capabilities_description = ""
        self.registry_last_reload = None
        self._load_capability_registry()

        # -------------------- MCP Integration (Capability Introspection) --------------------
        print("[DEBUG] Reached MCP initialization section")
        # Initialize Model Context Protocol for full capability introspection
        # Provides "what/why/when" transparency and routing with fallback chains
        self.mcp = None
        try:
            from src.mcp.integration import MCPIntegration
            self.mcp = MCPIntegration(enable_discovery=True)
            mcp_summary = self.mcp.graph.get_summary()
            print(f"[mcp] Initialized with {mcp_summary['total_capabilities']} MCP capabilities from {len(mcp_summary['servers'])} servers")
        except Exception as e:
            print(f"[mcp] Failed to initialize MCP: {e}")
            self.mcp = None

        print("[DEBUG] Reached Self-Healing initialization section")
        # -------------------- Self-Healing System --------------------
        # Initialize self-healing system early so it's available for all components
        self.heal_bus = None
        self.heal_executor = None
        if HealBus is not None:
            try:
                self.heal_bus = HealBus()
                guardrails = Guardrails(mode=os.getenv("KLR_HEAL_MODE", "SAFE"))
                health_probes = HealthProbes(kloros_instance=self)
                triage = TriageEngine(os.getenv("KLR_HEAL_PLAYBOOKS", "/home/kloros/self_heal_playbooks.yaml"))
                outcomes = OutcomesLogger()
                self.heal_executor = HealExecutor(guardrails, health_probes, outcomes=outcomes)

                # Subscribe executor to heal events
                def handle_heal_event(event):
                    playbook = triage.triage(event)
                    if playbook:
                        self.heal_executor.execute_playbook(playbook, event, self)

                self.heal_bus.subscribe(handle_heal_event)
                print("[self-heal] Healing system initialized")

                # Initialize Chaos Lab for self-healing testing
                try:
                    from src.dream_lab import ChaosOrchestrator
                    self.chaos = ChaosOrchestrator(
                        heal_bus=self.heal_bus,
                        tool_registry=None,  # Will be set later
                        dream_runtime=None,  # Will be set later
                        metrics=None,
                        logger=None,
                        safe_mode=True,
                        kloros_instance=self  # Pass self so chaos can access backends
                    )
                    # Subscribe chaos observer to heal bus
                    self.heal_bus.subscribe(self.chaos.obs.on_event)
                    print("[chaos] Chaos Lab initialized with backend access")
                except Exception as chaos_err:
                    print(f"[chaos] Chaos Lab unavailable: {chaos_err}")
                    self.chaos = None

                # Initialize System Health Monitor for active resource monitoring
                try:
                    if SystemHealthMonitor is not None:
                        self.system_health_monitor = SystemHealthMonitor(
                            kloros_instance=self,
                            check_interval_seconds=60,
                            swap_warning_threshold=70,
                            swap_critical_threshold=90,
                            memory_critical_gb=2.0
                        )
                        self.system_health_monitor.start()
                        print("[system-health] Active system monitoring started")
                    else:
                        self.system_health_monitor = None
                except Exception as monitor_err:
                    print(f"[system-health] System monitor unavailable: {monitor_err}")
                    self.system_health_monitor = None

            except Exception as e:
                print(f"[self-heal] Failed to initialize healing system: {e}")
                self.heal_bus = None
                self.chaos = None
                self.system_health_monitor = None

        # -------------------- Runtime Exception Bridge (Self-Awareness) --------------------
        # Initialize exception monitoring to feed errors into meta-cognition
        self.exception_bridge = None
        try:
            from src.runtime_exception_bridge import init_exception_bridge
            self.exception_bridge = init_exception_bridge(self)
            print("[exception-bridge] Runtime exception monitoring enabled")
        except Exception as e:
            print(f"[exception-bridge] Failed to initialize: {e}")
            self.exception_bridge = None

        # Audio playback configuration
        # Use pw-play (PipeWire native) instead of aplay to avoid hardware locking
        # Override with KLR_PLAYBACK_CMD env var
        self.playback_cmd = os.getenv("KLR_PLAYBACK_CMD", "pw-play")
        self.playback_target = os.getenv("KLR_PLAYBACK_TARGET", "alsa_output.pci-0000_09_00.4.iec958-stereo")

        # ----------------- Audio device -----------------
        self.input_device_index = None
        idx_env = os.getenv("KLR_INPUT_IDX")
        if idx_env is not None:
            try:
                self.input_device_index = int(idx_env)
            except ValueError:
                self.input_device_index = None
        if self.input_device_index is None:
            try:
                import sounddevice as sd

                # Priority order for microphone detection
                preferred_mics = ["CMTECK", "USB Audio", "Blue Snowball", "Audio-Technica"]
                fallback_device = None
                
                for i, d in enumerate(sd.query_devices()):
                    # d may be a mapping-like object or a string in some environments — handle both
                    if isinstance(d, dict):
                        name = d.get("name", "")
                        max_in = d.get("max_input_channels", 0)
                    else:
                        name = str(d)
                        max_in = 0
                    
                    if max_in > 0:  # Must have input channels
                        # Check for preferred microphones first
                        for preferred in preferred_mics:
                            if preferred in name:
                                self.input_device_index = i
                                print(f"[audio] auto-detected preferred mic: {name} (device {i})")
                                break
                        
                        if self.input_device_index is not None:
                            break
                            
                        # Store first available input device as fallback
                        if fallback_device is None:
                            fallback_device = i
                
                # Use fallback if no preferred mic found
                if self.input_device_index is None and fallback_device is not None:
                    self.input_device_index = fallback_device
                    print(f"[audio] using fallback input device {fallback_device}")
                    
            except Exception as e:
                print("[audio] failed to query devices:", e)
                self.input_device_index = None

        # Detect device default sample rate (fallback 48000)
        try:
            import sounddevice as sd

            idev = sd.query_devices(
                self.input_device_index
                if self.input_device_index is not None
                else self.input_device_index if self.input_device_index is not None else sd.default.device[0],
                "input",
            )
            # device entries can be mapping-like; attempt dict-like access, fallback to attribute access
            if isinstance(idev, dict):
                self.sample_rate = int(idev.get("default_samplerate") or 48000)
            else:
                # best-effort: some snd libs return objects with attribute access
                self.sample_rate = int(getattr(idev, "default_samplerate", 48000) or 48000)
        except Exception:
            self.sample_rate = 48000
        # Use configurable block size from environment, fallback to 16ms blocks
        block_ms = int(os.getenv("KLR_AUDIO_BLOCK_MS", "8"))
        self.blocksize = max(256, int(self.sample_rate * block_ms / 1000))
        self.channels = 1
        self.input_gain = float(os.getenv("KLR_INPUT_GAIN", "1.0"))  # 1.0–2.0

        # Only show audio config once at startup, not repeatedly
        if not hasattr(self, '_audio_config_shown'):
            print(
                f"[audio] input index={self.input_device_index}  SR={self.sample_rate}  block={self.blocksize}"
            )
            self._audio_config_shown = True

        # Audio capture backend configuration
        self.audio_backend_name = os.getenv("KLR_AUDIO_BACKEND", "pulseaudio")
        self.audio_device_index = None
        device_env = os.getenv("KLR_AUDIO_DEVICE_INDEX")
        if device_env:
            try:
                self.audio_device_index = int(device_env)
            except ValueError:
                pass
        if self.audio_device_index is None:
            self.audio_device_index = self.input_device_index

        self.audio_sample_rate = int(os.getenv("KLR_AUDIO_SAMPLE_RATE", str(self.sample_rate)))
        self.audio_block_ms = int(os.getenv("KLR_AUDIO_BLOCK_MS", "8"))
        self.audio_channels = int(os.getenv("KLR_AUDIO_CHANNELS", "1"))
        self.audio_ring_secs = float(os.getenv("KLR_AUDIO_RING_SECS", "2.0"))
        self.audio_warmup_ms = int(os.getenv("KLR_AUDIO_WARMUP_MS", "200"))
        self.enable_wakeword = int(os.getenv("KLR_ENABLE_WAKEWORD", "1"))


        # VOSK model for wake word detection and hybrid STT
        self.vosk_model = None
        try:
            vosk_path = os.getenv("KLR_VOSK_MODEL_DIR") or os.path.expanduser("~/models/vosk/model")
            if os.path.exists(vosk_path) and self.enable_wakeword:
                import vosk
                self.vosk_model = vosk.Model(vosk_path)
                print(f"[vosk] Wake word model loaded from {vosk_path}")
        except Exception as e:
            print(f"[vosk] Wake word model load failed: {e}")
        # Audio backend will be initialized later
        self.audio_backend: Optional[AudioInputBackend] = None

        # -------------------- Models --------------------
        self.piper_model = os.path.expanduser("~/KLoROS/models/piper/glados_piper_medium.onnx")
        self.piper_config = os.path.expanduser(
            "~/KLoROS/models/piper/glados_piper_medium.onnx.json"
        )

        # -------- Wake phrase grammar (KLoROS + optional variants) --------
        # Keep default tight to just 'kloros' to avoid 'hey' false triggers.
        base_list = os.getenv("KLR_WAKE_PHRASES", "kloros")
        self.wake_phrases = [s.strip().lower() for s in base_list.split(",") if s.strip()]

        # thresholds you can tune via env
        self.wake_conf_min = float(os.getenv("KLR_WAKE_CONF_MIN", "0.65"))  # 0.0–1.0
        self.wake_rms_min = int(os.getenv("KLR_WAKE_RMS_MIN", "350"))  # 16-bit RMS energy gate
        self.fuzzy_threshold = float(
            os.getenv("KLR_FUZZY_THRESHOLD", "0.8")
        )  # fuzzy matching threshold
        self.wake_debounce_ms = int(
            os.getenv("KLR_WAKE_DEBOUNCE_MS", "400")
        )  # debounce within utterance
        self.wake_cooldown_ms = int(
            os.getenv("KLR_WAKE_COOLDOWN_MS", "2000")
        )  # cooldown between wakes
        self._last_wake_ms: float = 0
        self._last_emit_ms = 0

        # Calibration-derived thresholds (will be set by _load_calibration_profile)
        self.vad_threshold_dbfs: Optional[float] = None  # VAD threshold in dBFS, if calibrated
        self.agc_gain_db: float = 0.0  # AGC gain in dB, if calibrated

        # STT configuration
        self.enable_stt = int(os.getenv("KLR_ENABLE_STT", "0"))
        self.stt_backend_name = os.getenv("KLR_STT_BACKEND", "mock")
        self.stt_lang = os.getenv("KLR_STT_LANG", "en-US")
        self.max_turn_seconds = float(os.getenv("KLR_MAX_TURN_SECONDS", "30.0"))
        self.stt_backend: Optional[Any] = None  # Will be initialized later if needed
        self.asr: Optional[Any] = None  # Optional ASR integration (not currently implemented)


        # VAD configuration
        self.vad_use_calibration = int(os.getenv("KLR_VAD_USE_CALIBRATION", "1"))
        self.vad_threshold_dbfs_fallback = float(os.getenv("KLR_VAD_THRESHOLD_DBFS", "-48.0"))
        self.vad_frame_ms = int(os.getenv("KLR_VAD_FRAME_MS", "30"))
        self.vad_hop_ms = int(os.getenv("KLR_VAD_HOP_MS", "10"))
        self.vad_attack_ms = int(os.getenv("KLR_VAD_ATTACK_MS", "50"))
        self.vad_release_ms = int(os.getenv("KLR_VAD_RELEASE_MS", "200"))
        self.vad_min_active_ms = int(os.getenv("KLR_VAD_MIN_ACTIVE_MS", "200"))
        self.vad_margin_db = float(os.getenv("KLR_VAD_MARGIN_DB", "2.0"))
        self.log_vad_frames = int(os.getenv("KLR_LOG_VAD_FRAMES", "0"))

        # TTS configuration
        self.enable_tts = int(os.getenv("KLR_ENABLE_TTS", "1"))
        self.tts_backend_name = os.getenv("KLR_TTS_BACKEND", "piper")
        self.tts_sample_rate = int(os.getenv("KLR_TTS_SAMPLE_RATE", "22050"))
        self.tts_out_dir = os.getenv("KLR_TTS_OUT_DIR")
        self.fail_open_tts = int(os.getenv("KLR_FAIL_OPEN_TTS", "1"))
        self.tts_backend: Optional[Any] = None  # Will be initialized later if needed

        # Reasoning configuration
        self.reason_backend_name = os.getenv("KLR_REASON_BACKEND", "mock")
        self.reason_backend: Optional[Any] = None  # Will be initialized later if needed

        # Speaker recognition configuration
        self.enable_speaker_id = int(os.getenv("KLR_ENABLE_SPEAKER_ID", "0"))  # Default disabled
        self.speaker_backend_name = os.getenv("KLR_SPEAKER_BACKEND", "embedding")
        self.speaker_threshold = float(os.getenv("KLR_SPEAKER_THRESHOLD", "0.8"))
        self.speaker_backend: Optional[Any] = None  # Will be initialized later if needed
        # Simple enrollment conversation state
        self.enrollment_conversation = {
            "active": False,
            "user_name": "",
            "sentence_index": 0,
            "audio_samples": [],
            "sentences": []
        }

        # Half-duplex / echo suppression to prevent audio feedback loops
        self.tts_playing_evt = threading.Event()  # Thread-safe flag to suppress VAD during TTS output
        # Strip inline comments from env vars before parsing
        halfduplex_enabled = os.getenv("KLR_HALFDUPLEX_ENABLED", "1").split("#")[0].strip()
        self.tts_suppression_enabled = bool(int(halfduplex_enabled))
        flush_passes_val = os.getenv("KLR_HALFDUPLEX_FLUSH_PASSES", "3").split("#")[0].strip()
        self.flush_passes = int(flush_passes_val)
        flush_gap_val = os.getenv("KLR_HALFDUPLEX_FLUSH_GAP_MS", "100").split("#")[0].strip()
        self.flush_gap_ms = int(flush_gap_val)
        extra_tail_val = os.getenv("KLR_HALFDUPLEX_EXTRA_TAIL_MS", "800").split("#")[0].strip()
        self.extra_tail_ms = int(extra_tail_val)
        self._tts_armed_at = None  # Watchdog timestamp for stuck suppression detection

        # Enhanced phonetic variants that closely match "kloros" pronunciation
        # These words are in the Vosk vocabulary and will eliminate the warning
        # Get custom phonetic variants from environment or use defaults
        env_variants = os.getenv("KLR_PHONETIC_VARIANTS", "")
        if env_variants:
            phonetic_variants = [v.strip().lower() for v in env_variants.split(",") if v.strip()]
        else:
            phonetic_variants = [
            "colors", "chorus", "close", "clear", "clears", "clause", "course",
            "coral", "choral", "cross", "calls", "crawls", "rows", "clothes",
            "carlos", "corals", "closes", "gross", "loss", "boss", "moss"
            ]
        # Use only phonetic variants in Vosk grammar to eliminate "kloros" vocabulary warning
        # The fuzzy matching will still work with the original wake_phrases
        self.wake_grammar = json.dumps(phonetic_variants + ["[unk]"])
        # Create recognizers only if the model loaded successfully
        if self.vosk_model is not None:
            self.wake_rec = vosk.KaldiRecognizer(
                self.vosk_model, self.sample_rate, self.wake_grammar
            )
            self.vosk_rec = vosk.KaldiRecognizer(self.vosk_model, self.sample_rate)
        else:
            self.wake_rec = None
            self.vosk_rec = None

        # -------------------- VAD (Voice Activity Detection) -----------------
        # Try to initialize Silero VAD, fallback to WebRTC if it fails
        self.vad_type = os.getenv("KLR_VAD_TYPE", "silero").lower()
        self.vad_threshold = float(os.getenv("KLR_VAD_THRESHOLD", "0.5"))

        # Lazy-loaded SileroVAD wrapper for two-stage mode
        self.silero_vad_wrapper = None

        if self.vad_type == "two_stage":
            # Two-stage VAD: dBFS pre-gate + Silero refinement (lazy-loaded)
            self.vad_model = "two_stage"  # Sentinel value for integration guard
            print("[vad] Using two-stage VAD (dBFS pre-gate + Silero refinement)")
        elif self.vad_type == "silero":
            self._init_silero_vad()
        elif self.vad_type == "dbfs":
            # Legacy dBFS-only mode (no Silero)
            self.vad_model = "dbfs"  # Sentinel value for integration guard
            print("[vad] Using dBFS-only VAD (legacy mode)")
        else:
            self._init_webrtc_vad()

        self.frame_ms = 20  # 10/20/30 supported
        self.max_cmd_s = 12.0  # allow a bit longer
        self.silence_end_ms = 500  # snappy end-pointing - 500ms silence ends turn
        self.preroll_ms = 400  # include some audio before start (reduced for speed)
        self.start_timeout_ms = 3500  # time to begin speaking after wake
        self.min_cmd_ms = 400  # allow shorter commands (reduced from 500ms)

        # -------------------- State ---------------------
        self.audio_queue: "queue.Queue[bytes]" = queue.Queue(maxsize=64)
        self.listening = False
        self._heartbeat = 0
        self.conversation_history: List[str] = []
        # Conversation flow for multi-turn context
        from src.core.conversation_flow import ConversationFlow
        from src.core.policies import DialoguePolicy
        self.conversation_flow = ConversationFlow(idle_cutoff_s=180)
        self.dialogue_policy = DialoguePolicy()
        self.json_logger: Optional[Any] = None

        # Memory optimization: Periodic garbage collection
        import gc
        self.gc_counter = 0
        self.gc_interval = 10  # Run GC every 10 interactions

        # Memory monitoring with auto-restart on critical threshold
        self.memory_monitor = None
        try:
            from src.common.memory_monitor import create_monitor
            self.memory_monitor = create_monitor(
                service_name="kloros_voice",
                warning_mb=1024,
                critical_mb=2048
            )
            print("[memory-monitor] Memory monitoring enabled")
        except ImportError:
            print("[memory-monitor] Module not available, monitoring disabled")

        self._load_memory()
        self._init_memory_enhancement()
        self._load_calibration_profile()
        self._init_json_logger()
        self._init_stt_backend()
        self._init_tts_backend()
        self._init_reasoning_backend()

        # Initialize consciousness system (Phase 1 + Phase 2) with expression filter
        from src.consciousness.integration import integrate_consciousness
        integrate_consciousness(self, cooldown=5.0, max_expressions=10)

        # Initialize goal system with persistent memory and consciousness integration
        try:
            from src.goal_system import GoalManager, integrate_goals_with_consciousness
            goal_persistence_path = Path.home() / ".kloros" / "goals.json"
            goal_persistence_path.parent.mkdir(parents=True, exist_ok=True)

            self.goal_manager = GoalManager(persistence_path=goal_persistence_path)
            self.goal_integrator = integrate_goals_with_consciousness(self.consciousness, self.goal_manager)

            logger = logging.getLogger(__name__)
            logger.info(f"Goal system initialized with persistence at {goal_persistence_path}")
        except ImportError as e:
            print(f"[goal_system] Failed to initialize goal system: {e}")
            self.goal_manager = None
            self.goal_integrator = None
        except Exception as e:
            print(f"[goal_system] Error during goal system initialization: {e}")
            self.goal_manager = None
            self.goal_integrator = None

        # Initialize meta-cognitive system (conversational self-awareness)
        # Bridges consciousness, memory, and conversation flow for real-time dialogue quality monitoring
        from src.meta_cognition import init_meta_cognition
        init_meta_cognition(self)

        # Verify voice stack integrity (prevent regressions)
        try:
            from src.voice import assert_voice_stack
            assert_voice_stack(
                asr=getattr(self, 'stt_backend', None),
                vad=getattr(self, 'vad_model', None)
            )
            print("[voice] ✓ Voice stack integration verified")
        except AssertionError as e:
            print(f"[voice] ✗ Voice stack verification failed: {e}")
            raise
        except ImportError:
            # Guard module not available, skip check
            pass

        # Stagger GPU-heavy backend initialization to prevent cuDNN conflicts
        if self.enable_speaker_id:
            import time
            print("[init] Staggering speaker backend initialization (cuDNN conflict prevention)")
            time.sleep(2.0)  # 2-second delay for GPU context stabilization
        self._init_speaker_backend()

        # Only initialize audio backend if enabled
        if os.getenv("KLR_ENABLE_AUDIO", "1") != "0":
            self._init_audio_backend()
        else:
            print("[audio] Audio backend disabled via KLR_ENABLE_AUDIO=0")

        # -------------------- UX Components ---------------------
        # Create acknowledgment broker for immediate user feedback during long operations
        if self.tts_backend and self.audio_backend:
            try:
                self.ack_broker = AckBroker(
                    tts_backend=self.tts_backend,
                    audio_backend=self.audio_backend,
                    min_quiet_gap_s=6.0
                )
                print("[ux] AckBroker initialized for rate-limited user feedback")

                # Wire AckBroker into reasoning backend if it's RAG-based
                if hasattr(self, 'reason_backend') and self.reason_backend:
                    if hasattr(self.reason_backend, '__class__') and 'LocalRagBackend' in str(self.reason_backend.__class__):
                        self.reason_backend.ack_broker = self.ack_broker
                        print("[ux] AckBroker wired into RAG backend")
            except Exception as e:
                print(f"[ux] Failed to initialize AckBroker: {e}")
                self.ack_broker = None
        else:
            print("[ux] Skipping AckBroker (TTS or audio backend unavailable)")
            self.ack_broker = None

        # -------------------- Introspection Tools ---------------------
        from src.introspection_tools import IntrospectionToolRegistry, register_scholar_tools, register_browser_tools
        self.tool_registry = IntrospectionToolRegistry()

        register_scholar_tools()
        register_browser_tools()

        logger.info("Scholar and browser_agent tools registered")

        # -------------------- Capability Hot-Reload ---------------------
        # Re-enabled after fixing memory leak (was from D-REAM Evolution, not hot-reload)
        try:
            from src.config.hot_reload import start_hot_reload
            self.capability_reloader = start_hot_reload()
            print("[hot_reload] Config hot-reload enabled")
        except Exception as e:
            self.capability_reloader = None
            print(f"[hot_reload] Could not start hot-reload (non-fatal): {e}")

        # Initialize idle reflection manager
        self.reflection_manager = None
        if IdleReflectionManager is not None:
            try:
                self.reflection_manager = IdleReflectionManager(self)
                # Reload config to pick up environment variables set by hot_reload
                if hasattr(self.reflection_manager, 'enhanced_manager') and self.reflection_manager.enhanced_manager:
                    import time as time_module
                    time_module.sleep(0.5)  # Let hot_reload finish updating os.environ
                    from src.idle_reflection import reload_config
                    self.reflection_manager.enhanced_manager.config = reload_config()
                print("[reflection] Idle reflection system initialized")
            except Exception as e:
                print(f"[reflection] Failed to initialize reflection manager: {e}")

        # Initialize housekeeping scheduler
        self.housekeeping_scheduler = None
        if HousekeepingScheduler is not None:
            try:
                self.housekeeping_scheduler = HousekeepingScheduler(self)
                print("[housekeeping] Scheduler initialized")
            except Exception as e:
                print(f"[housekeeping] Failed to initialize scheduler: {e}")

        # Initialize D-REAM Alert System
        self.alert_manager = None
        self.passive_sync = None
        self._alert_response_mode = {"active": False, "presented_alerts": []}
        if ALERT_SYSTEM_AVAILABLE:
            try:
                self.alert_manager = DreamAlertManager()

                # Register Phase 1 alert methods
                next_wake = NextWakeIntegrationAlert()
                passive = PassiveIndicatorAlert()
                reflection_insight = ReflectionInsightAlert(kloros_instance=self)

                self.alert_manager.register_alert_method("next_wake", next_wake)
                self.alert_manager.register_alert_method("passive", passive)
                self.alert_manager.register_alert_method("reflection_insight", reflection_insight)

                # Initialize passive alert sync (background → KLoROS communication)
                # Pass alert_manager so alerts get added to BOTH next-wake AND main queue
                self.passive_sync = PassiveAlertSync(passive, next_wake, self.alert_manager)
                print("[alerts] Passive alert sync initialized (background system → KLoROS)")

                print("[alerts] D-REAM Alert System initialized")
            except Exception as e:
                print(f"[alerts] Failed to initialize alert system: {e}")
                self.alert_manager = None
                self.passive_sync = None

        log_event(
            "boot_ready",
            operator=self.operator_id,
            sample_rate=self.sample_rate,
            blocksize=self.blocksize,
            wake_phrases=self.wake_phrases,
        )
        self._emit_persona(
            "boot",
            {"detail": "Systems nominal. Say 'KLoROS' to wake me."},
        )

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
        self.conversation_history = []
        self.conversation_flow = None

        # UX components
        self.ack_broker = None
        self.tool_registry = None
        self.reflection_manager = None
        self.housekeeping_scheduler = None

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
    def _load_memory(self) -> None:
        try:
            if os.path.exists(self.memory_file):
                with open(self.memory_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    conversations = data.get("conversations", [])
                    # Only load recent conversations to prevent unbounded growth
                    self.conversation_history = conversations[-100:] if len(conversations) > 100 else conversations
                    if len(conversations) > 100:
                        print(f"[mem] Trimmed loaded history: {len(conversations)} → {len(self.conversation_history)} entries")
        except Exception as e:
            print("[mem] load failed:", e)

    def _save_memory(self) -> None:
        try:
            data = {
                "conversations": self.conversation_history,
                "last_updated": datetime.now().isoformat(),
            }
            os.makedirs(os.path.dirname(self.memory_file), exist_ok=True)
            with open(self.memory_file, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            print("[mem] save failed:", e)

    def _trim_conversation_history(self, max_entries: int = 100) -> None:
        """Keep only the most recent conversation entries to prevent unbounded memory growth.

        Args:
            max_entries: Maximum number of conversation entries to retain (default: 100)
        """
        if len(self.conversation_history) > max_entries:
            trimmed_count = len(self.conversation_history) - max_entries
            self.conversation_history = self.conversation_history[-max_entries:]
            print(f"[mem] Trimmed conversation history: removed {trimmed_count} old entries, kept {max_entries}")

    def _init_memory_enhancement(self) -> None:
        """Initialize episodic-semantic memory enhancement if available."""
        if create_memory_enhanced_kloros is None:
            print("[memory] Advanced memory system not available")
            self.memory_enhanced = None
            return

        try:
            self.memory_enhanced = create_memory_enhanced_kloros(self)
            if self.memory_enhanced.enable_memory:
                print("[memory] Episodic-semantic memory system initialized")
            else:
                print("[memory] Advanced memory disabled by configuration")
        except Exception as e:
            print(f"[memory] Failed to initialize advanced memory: {e}")
            self.memory_enhanced = None

        # Initialize meta-cognitive layer after memory system
        if init_meta_cognition is not None:
            try:
                init_meta_cognition(self)
            except Exception as e:
                print(f"[meta-cognition] Failed to initialize: {e}")

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

    def _get_vad_threshold(self) -> float:
        """Resolve VAD threshold: calibration profile or environment fallback."""
        if self.vad_use_calibration and self.vad_threshold_dbfs is not None:
            return self.vad_threshold_dbfs
        return self.vad_threshold_dbfs_fallback

    # ====================== Capability Registry (Hot-Reload) ======================
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

    def _check_and_reload_registry(self) -> bool:
        """Check if capabilities.yaml has been modified and reload if needed.

        Returns:
            True if registry was reloaded, False otherwise
        """
        try:
            from pathlib import Path
            import time

            # Get capabilities.yaml path
            registry_path = Path(__file__).parent / "registry" / "capabilities.yaml"

            if not registry_path.exists():
                return False

            # Check file modification time
            current_mtime = registry_path.stat().st_mtime

            # If we haven't loaded yet or file has been modified, reload
            if self.registry_last_reload is None or current_mtime > self.registry_last_reload:
                old_count = len(self.capability_registry.capabilities) if self.capability_registry else 0
                self._load_capability_registry()
                new_count = len(self.capability_registry.capabilities) if self.capability_registry else 0

                if new_count != old_count:
                    print(f"[registry] Hot-reloaded: {old_count} → {new_count} capabilities")
                else:
                    print(f"[registry] Hot-reloaded: {new_count} capabilities (no count change)")

                return True

            return False

        except Exception as e:
            print(f"[registry] Failed to check/reload registry: {e}")
            return False

    def _init_stt_backend(self) -> None:
        """Initialize STT backend if enabled."""
        if not self.enable_stt or create_stt_backend is None:
            return

        try:
            # Prepare backend-specific configuration
            backend_kwargs = {}
            
            if self.stt_backend_name == "hybrid":
                # Configure hybrid backend with ASR environment variables
                backend_kwargs.update({
                    "vosk_model_dir": os.getenv("ASR_VOSK_MODEL"),
                    "vosk_model": self.vosk_model,  # Share VOSK model instance (memory optimization)
                    "whisper_model_size": os.getenv("ASR_WHISPER_SIZE", "medium"),
                    "whisper_device": "auto",  # Will auto-detect
                    "whisper_device_index": int(os.getenv("ASR_PRIMARY_GPU", "0")),
                    "correction_threshold": float(os.getenv("ASR_CORRECTION_THRESHOLD", "0.75")),
                    "confidence_boost_threshold": float(os.getenv("ASR_CONFIDENCE_BOOST_THRESHOLD", "0.9")),
                    "enable_corrections": bool(int(os.getenv("ASR_ENABLE_CORRECTIONS", "1"))),
                })
                print(f"[stt] Configuring hybrid ASR: VOSK + Whisper-{backend_kwargs['whisper_model_size']} (shared VOSK model)")
                print(f"[stt] Correction threshold: {backend_kwargs['correction_threshold']}, GPU: {backend_kwargs['whisper_device_index']}")
            elif self.stt_backend_name == "vosk":
                # Configure VOSK with shared model instance (memory optimization)
                backend_kwargs["vosk_model"] = self.vosk_model
                if os.getenv("ASR_VOSK_MODEL"):
                    backend_kwargs["model_dir"] = os.getenv("ASR_VOSK_MODEL")
            elif self.stt_backend_name == "whisper":
                # Configure Whisper with ASR settings
                backend_kwargs.update({
                    "model_size": os.getenv("ASR_WHISPER_SIZE", "medium"),
                    "device": "auto",
                    "device_index": int(os.getenv("ASR_PRIMARY_GPU", "0")),
                    "model_dir": os.getenv("ASR_WHISPER_MODEL"),
                })

            # Try to create the requested backend
            self.stt_backend = create_stt_backend(self.stt_backend_name, **backend_kwargs)  # type: ignore
            print(f"[stt] ✅ Initialized {self.stt_backend_name} backend")
            
            # Show backend info for hybrid systems
            if hasattr(self.stt_backend, 'get_info') and self.stt_backend_name == "hybrid":
                info = self.stt_backend.get_info()
                print(f"[stt] 🔀 Hybrid strategy ready - corrections: {info.get('enable_corrections', False)}")
                
        except Exception as e:
            print(f"[stt] ❌ Failed to initialize {self.stt_backend_name} backend: {e}")
            import traceback
            print(f"[stt] Error details: {traceback.format_exc()}")

            # Fallback to mock backend if primary backend fails
            if self.stt_backend_name != "mock":
                try:
                    self.stt_backend = create_stt_backend("mock")  # type: ignore
                    print("[stt] 🔄 Falling back to mock backend")
                except Exception as fallback_e:
                    print(f"[stt] Fallback to mock backend also failed: {fallback_e}")
                    self.stt_backend = None

    def _init_tts_backend(self) -> None:
        """Initialize TTS backend if enabled."""
        if not self.enable_tts or create_tts_backend is None:
            return

        try:
            self.tts_backend = create_tts_backend(self.tts_backend_name, out_dir=self.tts_out_dir)  # type: ignore
            print(f"[tts] Initialized {self.tts_backend_name} backend")
        except Exception as e:
            print(f"[tts] Failed to initialize {self.tts_backend_name} backend: {e}")

            # Try fallback to mock if not already using mock
            if self.tts_backend_name != "mock":
                try:
                    self.tts_backend = create_tts_backend("mock", out_dir=self.tts_out_dir)  # type: ignore
                    print("[tts] Falling back to mock backend")
                except Exception as fallback_e:
                    print(f"[tts] Fallback to mock backend also failed: {fallback_e}")
                    self.tts_backend = None

    def _init_reasoning_backend(self) -> None:
        """Initialize reasoning backend if available."""
        if create_reasoning_backend is None:
            print("[reasoning] Reasoning module unavailable; using fallback")
            return

        try:
            # Pass heal_bus to reasoning backend for self-healing
            self.reason_backend = create_reasoning_backend(
                self.reason_backend_name,
                heal_bus=self.heal_bus
            )  # type: ignore
            print(f"[reasoning] Initialized {self.reason_backend_name} backend")

            # Wrap with adaptive reasoning for conversation mode
            try:
                from src.conversation_reasoning import ConversationReasoningAdapter
                self.reason_backend = ConversationReasoningAdapter(self.reason_backend)
                print("[reasoning] Wrapped with adaptive conversation reasoning")
            except Exception as wrap_e:
                print(f"[reasoning] Failed to wrap with conversation reasoning: {wrap_e}")
                # Continue with unwrapped backend
        except Exception as e:
            print(f"[reasoning] Failed to initialize {self.reason_backend_name} backend: {e}")

            # Try fallback to mock if not already using mock
            if self.reason_backend_name != "mock":
                try:
                    self.reason_backend = create_reasoning_backend("mock")  # type: ignore
                    print("[reasoning] Falling back to mock backend")

                    # Wrap mock backend too
                    try:
                        from src.conversation_reasoning import ConversationReasoningAdapter
                        self.reason_backend = ConversationReasoningAdapter(self.reason_backend)
                        print("[reasoning] Wrapped mock backend with conversation reasoning")
                    except Exception as wrap_e:
                        print(f"[reasoning] Failed to wrap mock backend: {wrap_e}")
                    self._log_event(
                        "reason_backend_fallback",
                        requested=self.reason_backend_name,
                        fallback="mock",
                        error=str(e),
                    )
                except Exception as fallback_e:
                    print(f"[reasoning] Fallback to mock backend also failed: {fallback_e}")
                    self.reason_backend = None

    def _init_speaker_backend(self) -> None:
        """Initialize speaker recognition backend if enabled."""
        if not self.enable_speaker_id:
            print("[speaker] Speaker identification disabled")
            return

        if create_speaker_backend is None:
            print("[speaker] Speaker module unavailable; disabling speaker ID")
            return

        # Production safeguard: Prevent mock backend usage
        if self.speaker_backend_name == "mock":
            print("[speaker] WARNING: Mock backend requested - this generates fake data!")
            print("[speaker] Mock backend should only be used for testing/development")
            # Check if this is intentional (development/testing environment)
            if os.getenv("KLR_ALLOW_MOCK_BACKENDS", "0") != "1":
                print("[speaker] Mock backend blocked - set KLR_ALLOW_MOCK_BACKENDS=1 to override")
                self.speaker_backend = None
                return

        try:
            self.speaker_backend = create_speaker_backend(self.speaker_backend_name)  # type: ignore
            print(f"[speaker] Initialized {self.speaker_backend_name} backend")

            # Validate that we got a real backend, not mock
            if hasattr(self.speaker_backend, '__class__') and 'Mock' in self.speaker_backend.__class__.__name__:
                print("[speaker] WARNING: Mock backend active - speaker recognition will use fake data!")

        except Exception as e:
            print(f"[speaker] Failed to initialize {self.speaker_backend_name} backend: {e}")

            # NO MORE AUTOMATIC FALLBACK TO MOCK - this was a fabrication risk
            print("[speaker] Speaker backend initialization failed - disabling speaker recognition")
            print("[speaker] To enable fallback to mock (for testing), set KLR_ALLOW_MOCK_BACKENDS=1")
            self.speaker_backend = None

            log_event(
                "speaker_backend_failure",
                requested=self.speaker_backend_name,
                error=str(e),
                fallback_blocked=True
            )

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

    def _is_speech(self, audio_frame: bytes, sample_rate: int) -> bool:
        """Check if audio frame contains speech using active VAD (Silero, WebRTC, or two-stage)."""
        if self.vad_type == "two_stage":
            # Two-stage VAD: For frame-by-frame detection, use only dBFS (Stage A)
            # Stage B (Silero) is used for batch refinement elsewhere, not per-frame
            # This avoids running expensive neural network inference on every 20ms frame
            try:
                import numpy as np

                # Stage A: dBFS-based speech detection (fast, lightweight)
                audio_np = np.frombuffer(audio_frame, dtype=np.int16).astype(np.float32) / 32768.0
                rms = np.sqrt(np.mean(audio_np ** 2))
                dbfs = 20 * np.log10(rms + 1e-10)

                stage_a_threshold = float(os.getenv("KLR_VAD_STAGE_A_THRESHOLD", "-28.0"))

                # Debug logging
                if not hasattr(self, '_vad_debug_counter'):
                    self._vad_debug_counter = 0
                self._vad_debug_counter += 1
                if self._vad_debug_counter % 50 == 0:
                    print(f"[vad-debug] dBFS={dbfs:.1f} threshold={stage_a_threshold} result={dbfs >= stage_a_threshold}")

                # Return True if passes dBFS threshold (Silero refinement happens at batch level)
                return dbfs >= stage_a_threshold

            except Exception as e:
                print(f"[vad] Two-stage VAD error: {e}, defaulting to silence")
                import traceback
                traceback.print_exc()
                return False

        elif self.vad_type == "silero":
            try:
                import torch
                import numpy as np
                from scipy import signal

                # Convert bytes to numpy array
                audio_np = np.frombuffer(audio_frame, dtype=np.int16).astype(np.float32) / 32768.0

                # Proper resampling if needed (Silero expects 16kHz)
                if sample_rate != 16000:
                    # Use scipy for proper anti-aliased resampling
                    target_length = int(len(audio_np) * 16000 / sample_rate)
                    audio_np = signal.resample(audio_np, target_length)

                # Ensure minimum length for Silero
                if len(audio_np) < 512:
                    # Pad with zeros if too short
                    audio_np = np.pad(audio_np, (0, 512 - len(audio_np)))

                # Convert to torch tensor and get speech probability
                audio_tensor = torch.from_numpy(audio_np)
                speech_prob = self.vad_model(audio_tensor, 16000).item()

                # Debug logging every 50 frames to see what Silero is detecting
                if not hasattr(self, '_vad_debug_count'):
                    self._vad_debug_count = 0
                self._vad_debug_count += 1
                if self._vad_debug_count % 50 == 0:
                    print(f"[vad] Silero prob={speech_prob:.3f} threshold={self.vad_threshold} rms={np.sqrt(np.mean(audio_np**2)):.4f}")

                return speech_prob > self.vad_threshold

            except Exception as e:
                # Fallback to WebRTC on any error (including missing scipy)
                print(f"[vad] Silero error, falling back to WebRTC: {e}")
                return self.vad_model.is_speech(audio_frame, sample_rate)
        else:
            # WebRTC VAD
            return self.vad_model.is_speech(audio_frame, sample_rate)

    def _init_audio_backend(self) -> None:
        """Initialize audio capture backend with comprehensive fallback chain."""
        if create_audio_backend is None:
            print("[audio] Audio capture module unavailable; using legacy audio")
            return

        # Define fallback chain: PulseAudio -> SoundDevice -> Mock
        # Note: sounddevice marked as non-viable for production (comparative testing 2025-09-28)
        fallback_chain = [
            ("pulseaudio", "Primary: PulseAudio Backend (pacat subprocess)"),
            ("sounddevice", "Fallback: SoundDevice (NON-VIABLE FOR PRODUCTION)"),
            ("mock", "Emergency: Mock Backend")
        ]

        # Try each backend in chain starting with requested
        backend_attempted = False
        for backend_name, description in fallback_chain:
            # Try requested backend first, then continue with chain
            if not backend_attempted and backend_name == self.audio_backend_name:
                backend_attempted = True
            elif not backend_attempted:
                continue

            try:
                print(f"[audio] Attempting {description}")
                self.audio_backend = create_audio_backend(backend_name)  # type: ignore
                self.audio_backend.open(
                    sample_rate=self.audio_sample_rate,
                    channels=self.audio_channels,
                    device=self.audio_device_index,
                )

                # Warmup period
                if self.audio_warmup_ms > 0:
                    print(f"[audio] Warming up for {self.audio_warmup_ms}ms...")
                    time.sleep(self.audio_warmup_ms / 1000.0)

                print(f"[audio] ✓ Initialized {backend_name} backend successfully")

                # Log non-viable production warning
                if backend_name == "sounddevice":
                    print("[audio] ⚠ WARNING: SoundDevice backend marked NON-VIABLE for production")
                    print("[audio] ⚠ This backend failed comparative testing (2025-09-28)")
                    print("[audio] ⚠ Use only for emergency fallback scenarios")

                self.audio_backend_name = backend_name  # Update to actual backend used
                return

            except Exception as e:
                print(f"[audio] ✗ {backend_name} backend failed: {e}")

                # Log fallback event
                if backend_name != "mock":
                    self._log_event(
                        "audio_backend_fallback",
                        requested=backend_name,
                        error=str(e),
                        fallback_available=True
                    )

                # Continue to next backend

        # If we get here, all backends failed
        print("[audio] ✗ All audio backends failed - no audio input available")
        self.audio_backend = None

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
    def _stream_llm_response(self, context: str) -> str:
        """Stream LLM tokens and start TTS on sentence boundaries."""
        # Check if remote LLM is enabled and try it first
        self._check_remote_llm_config()
        if self.remote_llm_enabled:
            success, response = self._query_remote_llm(context)
            if success:
                # Speak the response in chunks
                sentences = response.split('. ')
                for sentence in sentences:
                    if len(sentence.strip()) > 20:
                        self.speak(sentence + '.')
                return response
            else:
                print(f"[remote-llm] Failed, falling back to local: {response}")

        # Fall back to local Ollama
        buffer = ""
        complete_response = ""
        sentence_endings = {'.', '!', '?'}

        try:
            r = requests.post(
                self.ollama_url,
                json={
                    "model": self.ollama_model,
                    "prompt": context,
                    "stream": True,
                    "options": {"temperature": 0.8, "top_p": 0.9, "repeat_penalty": 1.1,
                    "num_ctx": get_ollama_context_size(check_vram=False)
                }
                },
                stream=True,
                timeout=60,
            )

            if r.status_code != 200:
                return f"Error: Ollama HTTP {r.status_code}"

            for line in r.iter_lines():
                if not line:
                    continue

                try:
                    chunk = json.loads(line)
                    token = chunk.get("response", "")
                    buffer += token
                    complete_response += token

                    # Check for sentence boundary
                    if token.strip() and token.strip()[-1] in sentence_endings:
                        sentence = buffer.strip()
                        # Only speak if sentence is substantial (>20 chars)
                        if len(sentence) > 20:
                            print(f"[LLM] Sentence complete, queuing TTS: {sentence[:50]}...")
                            self.speak(sentence)
                            buffer = ""

                    if chunk.get("done", False):
                        break

                except json.JSONDecodeError as e:
                    print(f"[LLM] JSON decode error: {e}")
                    continue

            # Speak any remaining buffer
            if buffer.strip():
                print(f"[LLM] Final buffer, queuing TTS: {buffer.strip()[:50]}...")
                self.speak(buffer.strip())

            return complete_response.strip()

        except requests.RequestException as e:
            return f"Ollama error: {e}"

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
        enrollment_response = self._handle_enrollment_commands(user_message)
        if enrollment_response:
            return enrollment_response

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

    def _simple_chat_fallback(self, user_message: str) -> str:
        """Simple fallback chat when full reasoning system unavailable."""

        self.conversation_history.append(f"User: {user_message}")

        # Retrieve memory context to enhance conversation
        memory_context = ""
        if hasattr(self, "memory_enhanced") and self.memory_enhanced and self.memory_enhanced.enable_memory:
            try:
                context_result = self.memory_enhanced._retrieve_context(user_message)
                if context_result:
                    memory_context = self.memory_enhanced._format_context_for_prompt(context_result)
                    if memory_context:
                        memory_context = f"\n\nRelevant context from past conversations:\n{memory_context}\n"
            except Exception as e:
                print(f"[memory] Context retrieval failed: {e}")

        # Add tool descriptions to system prompt
        tools_desc = self.tool_registry.get_tools_description() if hasattr(self, "tool_registry") else ""
        context = (
            f"System: {self.system_prompt}{tools_desc}{memory_context}\n\n"
            + "\n".join(self.conversation_history[-20:])
            + "\n\nAssistant:"
        )

        # Try remote LLM first if enabled
        self._check_remote_llm_config()
        if self.remote_llm_enabled:
            success, resp = self._query_remote_llm(context)
            if not success:
                print(f"[remote-llm] Failed in fallback, using local: {resp}")
                resp = None  # Force fallback to local
        else:
            resp = None

        # Fall back to local Ollama if remote failed or not enabled
        if resp is None:
            try:
                r = requests.post(
                    self.ollama_url,
                    json={"model": self.ollama_model, "prompt": context, "stream": False, "options": {"temperature": 0.8, "top_p": 0.9, "repeat_penalty": 1.1,
                    "num_ctx": get_ollama_context_size(check_vram=False)
                }},
                    timeout=60,
                )
                if r.status_code == 200:
                    response_data = r.json()
                    resp = response_data.get("response", "").strip()

                    # Capture context for C2C
                    if self.c2c_enabled and response_data.get("context"):
                        self.last_ollama_context = response_data.get("context")
                else:
                    resp = f"Error: Ollama HTTP {r.status_code}"
            except requests.RequestException as e:
                resp = f"Ollama error: {e}"

        # Check if LLM requested a tool
        if hasattr(self, "tool_registry"):
            from src.introspection_tools import IntrospectionToolRegistry
            tool_name = IntrospectionToolRegistry.parse_tool_call(resp)
            if tool_name:
                tool = self.tool_registry.get_tool(tool_name)
                if tool:
                    try:
                        # Execute the tool and get actual data
                        tool_result = tool.execute(self)
                        # Return the tool result directly
                        resp = tool_result
                    except Exception as e:
                        resp = f"Tool execution failed: {e}"

        self.conversation_history.append(f"Assistant: {resp}")
        self._trim_conversation_history()

        # Periodic garbage collection to prevent memory leaks
        self.gc_counter += 1
        if self.gc_counter >= self.gc_interval:
            import gc
            gc.collect()
            self.gc_counter = 0

        # Memory monitoring and auto-restart check
        mem_status = self.memory_monitor.check_and_log()
        if mem_status['status'] == 'critical':
            print(f"[memory] CRITICAL: {mem_status['rss_mb']}MB. Service restart required.")
            if self.memory_monitor.should_restart():
                self.listening = False

        # Process with meta-cognitive awareness (even in fallback mode)
        # Optional: can be disabled via KLR_ENABLE_META_COGNITION=0 to save ~300ms per turn
        enable_meta = os.getenv("KLR_ENABLE_META_COGNITION", "1") == "1"
        if enable_meta:
            from src.meta_cognition import process_with_meta_awareness
            resp = process_with_meta_awareness(
                kloros_instance=self,
                user_input=user_message,
                response=resp,
                confidence=0.7  # Lower confidence for fallback mode
            )

        # Log assistant response to memory system
        if hasattr(self, "memory_enhanced") and self.memory_enhanced and self.memory_enhanced.enable_memory:
            try:
                self.memory_enhanced.memory_logger.log_llm_response(
                    response=resp,
                    model=self.ollama_model,
                )
            except Exception as e:
                print(f"[memory] LLM response logging failed: {e}")

        self._save_memory()

        # Save C2C context snapshot after significant conversations
        if self.c2c_enabled and self.c2c_manager and self.last_ollama_context:
            # Save if conversation has sufficient depth (>5 turns)
            turn_count = len([m for m in self.conversation_history if m.startswith("User:")])
            if turn_count >= 5:
                try:
                    self.c2c_manager.save_context(
                        context_tokens=self.last_ollama_context,
                        source_model=self.ollama_model,
                        source_subsystem='voice',
                        topic='user_conversation',
                        metadata={
                            'turns': turn_count,
                            'operator': self.operator_id,
                            'last_message': user_message[:100]
                        }
                    )
                    print(f"[C2C] Saved conversation context ({len(self.last_ollama_context)} tokens, {turn_count} turns)")
                except Exception as e:
                    print(f"[C2C] Failed to save context: {e}")

        return resp

    def _integrated_chat(self, user_message: str) -> str:
        """
        Memory-integrated chat with full cognitive architecture.

        This method replaces the legacy conversation_history list with:
        1. ConversationFlow for state management
        2. Episodic memory retrieval from SQLite
        3. Reasoning trace logging
        4. Auto-condensation on conversation end

        Args:
            user_message: User's input text

        Returns:
            Assistant's response text
        """

        # =============================================================================
        # STEP 1: Update Conversation Flow State
        # =============================================================================

        # Get or create active conversation state
        state = self.conversation_flow.ensure_thread()

        # Resolve pronouns (e.g., "it" → "GPU" if last discussing GPU)
        resolved_message = user_message
        if state.maybe_followup(user_message):
            resolved_message = state.resolve_pronouns(user_message)

        # Extract entities from user message (GPU: RTX 3080, project: KLoROS, etc.)
        state.extract_entities(resolved_message)

        # Detect follow-ups (e.g., "also", "and", "what about")
        is_followup = state.maybe_followup(resolved_message)

        # Add user turn to conversation state
        state.push("user", resolved_message)

        # Log user input to memory system
        if hasattr(self, "memory_enhanced") and self.memory_enhanced and self.memory_enhanced.enable_memory:
            try:
                self.memory_enhanced.memory_logger.log_user_input(
                    transcript=resolved_message,
                    confidence=0.95
                )
            except Exception as e:
                print(f"[memory] User input logging failed: {e}")

        # =============================================================================
        # STEP 2: Retrieve Episodic Memory Context
        # =============================================================================

        memory_context = ""
        context_events_count = 0
        context_summaries_count = 0

        if hasattr(self, "memory_enhanced") and self.memory_enhanced and self.memory_enhanced.enable_memory:
            try:
                # Retrieve relevant episodes and events from SQLite
                context_result = self.memory_enhanced._retrieve_context(resolved_message)

                if context_result:
                    memory_context = self.memory_enhanced._format_context_for_prompt(context_result)
                    context_events_count = len(context_result.events)
                    context_summaries_count = len(context_result.summaries)

                    if memory_context:
                        memory_context = f"\n\nRelevant context from past conversations:\n{memory_context}\n"

                    # Log context retrieval as memory event
                    self.memory_enhanced.memory_logger.log_context_retrieval(
                        query=resolved_message,
                        retrieved_events=context_events_count,
                        retrieved_summaries=context_summaries_count,
                        total_tokens=context_result.total_tokens,
                        retrieval_time=context_result.retrieval_time
                    )
            except Exception as e:
                print(f"[memory] Context retrieval failed: {e}")

        # =============================================================================
        # STEP 3: Build Conversation Context
        # =============================================================================

        # Add tool descriptions to system prompt
        tools_desc = self.tool_registry.get_tools_description() if hasattr(self, "tool_registry") else ""

        # Use persistent capability awareness loaded at initialization
        # This provides self-awareness without per-turn overhead
        capabilities_desc = self.capabilities_description

        # Add entity context from conversation flow
        entity_context = ""
        if state.entities:
            entity_context = "\n\nCurrent conversation entities:\n"
            for key, value in state.entities.items():
                entity_context += f"- {key}: {value}\n"

        # Add topic summary if available
        topic_summary = ""
        if state.topic_summary and state.topic_summary.bullet_points:
            topic_summary = f"\n\nConversation thread summary:\n{state.topic_summary.to_text()}\n"

        # Format recent conversation history from ConversationFlow (last 10 turns)
        recent_turns = []
        for turn in list(state.turns)[-10:]:
            if turn.role == "user":
                recent_turns.append(f"User: {turn.text}")
            elif turn.role == "assistant":
                recent_turns.append(f"Assistant: {turn.text}")

        conversation_history_text = "\n".join(recent_turns)

        # Build full prompt context
        context = (
            f"System: {self.system_prompt}{capabilities_desc}{tools_desc}{memory_context}{entity_context}{topic_summary}\n\n"
            f"{conversation_history_text}\n\n"
            f"User: {resolved_message}\n\nAssistant:"
        )

        # =============================================================================
        # STEP 4: Generate Response with Reasoning Trace
        # =============================================================================

        reasoning_trace_start = time.time()
        resp = ""

        # Try remote LLM first if enabled
        self._check_remote_llm_config()
        if self.remote_llm_enabled:
            success, resp = self._query_remote_llm(context)
            if not success:
                print(f"[remote-llm] Failed in integrated chat, using local: {resp}")
                resp = ""  # Force fallback to local

        # Fall back to local Ollama if remote failed or not enabled
        if not resp:
            try:
                # Call Ollama for response generation
                r = requests.post(
                    self.ollama_url,
                    json={
                        "model": self.ollama_model,
                        "prompt": context,
                        "stream": False,
                        "options": {
                            "temperature": 0.8,
                            "top_p": 0.9,
                            "repeat_penalty": 1.1,
                            "num_ctx": get_ollama_context_size(check_vram=False)
                        }
                    },
                    timeout=60,
                )

                if r.status_code == 200:
                    resp = r.json().get("response", "").strip()
                else:
                    resp = f"Error: Ollama HTTP {r.status_code}"

            except requests.RequestException as e:
                resp = f"Ollama error: {e}"

        # Check if LLM requested a tool (works for both remote and local)
        if hasattr(self, "tool_registry"):
            from src.introspection_tools import IntrospectionToolRegistry
            tool_name = IntrospectionToolRegistry.parse_tool_call(resp)

            if tool_name:
                tool = self.tool_registry.get_tool(tool_name)
                if tool:
                    try:
                        # Execute the tool and get actual data
                        tool_result = tool.execute(self)
                        resp = tool_result

                        # Log tool execution to memory
                        if hasattr(self, "memory_enhanced") and self.memory_enhanced and self.memory_enhanced.enable_memory:
                            try:
                                from src.kloros_memory.models import EventType
                                self.memory_enhanced.memory_logger.log_event(
                                    event_type=EventType.TOOL_EXECUTION,
                                    content=f"Executed tool: {tool_name}",
                                    metadata={
                                        "tool_name": tool_name,
                                        "result_preview": str(tool_result)[:200]
                                    }
                                )
                            except Exception as e:
                                print(f"[memory] Tool execution logging failed: {e}")

                    except Exception as e:
                        resp = f"Tool execution failed: {e}"

        reasoning_duration = time.time() - reasoning_trace_start

        # =============================================================================
        # STEP 5: Log Reasoning Trace to Memory
        # =============================================================================

        if hasattr(self, "memory_enhanced") and self.memory_enhanced and self.memory_enhanced.enable_memory:
            try:
                # Log reasoning trace as cognitive event
                from src.kloros_memory.models import EventType
                self.memory_enhanced.memory_logger.log_event(
                    event_type=EventType.REASONING_TRACE,
                    content=f"Query: {resolved_message[:100]}",
                    metadata={
                        "query": resolved_message,
                        "entities": state.entities,
                        "is_followup": is_followup,
                        "context_events": context_events_count,
                        "context_summaries": context_summaries_count,
                        "response_length": len(resp),
                        "duration_ms": int(reasoning_duration * 1000),
                        "model": self.ollama_model
                    }
                )
            except Exception as e:
                print(f"[memory] Reasoning trace logging failed: {e}")

        # =============================================================================
        # STEP 6: Update Conversation State
        # =============================================================================

        # Add assistant response to conversation flow
        state.push("assistant", resp)

        # Extract entities from assistant response
        state.extract_entities(resp)

        # Update topic summary with key facts from this exchange
        if len(resp) > 20:  # Only add substantial responses
            # Simple heuristic: add first sentence as bullet point
            first_sentence = resp.split('.')[0].strip()
            if first_sentence and len(first_sentence) > 10:
                state.topic_summary.add_fact(first_sentence)

        # Log assistant response to memory system
        if hasattr(self, "memory_enhanced") and self.memory_enhanced and self.memory_enhanced.enable_memory:
            try:
                self.memory_enhanced.memory_logger.log_llm_response(
                    response=resp,
                    model=self.ollama_model
                )
            except Exception as e:
                print(f"[memory] LLM response logging failed: {e}")

        # =============================================================================
        # STEP 7: Check for Conversation End and Auto-Condense
        # =============================================================================

        # Check if conversation is ending (idle detection)
        if state.is_idle():
            print("[memory] Conversation idle detected, triggering episode condensation...")

            if hasattr(self, "memory_enhanced") and self.memory_enhanced and self.memory_enhanced.enable_memory:
                try:
                    # End current conversation
                    self.memory_enhanced.memory_logger.end_conversation()

                    # Auto-condense episodes if enabled
                    if self.memory_enhanced.auto_condense:
                        self.memory_enhanced._auto_condense_episodes()

                    # Start new conversation for next interaction
                    import uuid
                    self.memory_enhanced.current_conversation_id = str(uuid.uuid4())
                    self.memory_enhanced.memory_logger.start_conversation(
                        self.memory_enhanced.current_conversation_id
                    )
                except Exception as e:
                    print(f"[memory] Auto-condensation failed: {e}")

        return resp

    def _migrate_legacy_memory_to_episodes(self):
        """
        One-time migration: convert old conversation_history JSON to episodes.

        This preserves existing conversation data when switching to the new system.
        """
        import json
        import os
        from pathlib import Path

        legacy_file = Path.home() / "KLoROS" / "kloros_memory.json"

        if not legacy_file.exists():
            return

        print("[memory] Migrating legacy conversation history to episodes...")

        try:
            with open(legacy_file, 'r') as f:
                data = json.load(f)

            conversations = data.get("conversations", [])

            if not conversations:
                return

            # Group conversations into episodes
            if hasattr(self, "memory_enhanced") and self.memory_enhanced and self.memory_enhanced.enable_memory:
                import uuid
                migration_id = str(uuid.uuid4())

                self.memory_enhanced.memory_logger.start_conversation(migration_id)

                # Log each line as a user/assistant event
                for line in conversations:
                    if line.startswith("User: "):
                        text = line[6:]
                        self.memory_enhanced.memory_logger.log_user_input(text, confidence=0.9)
                    elif line.startswith("Assistant: "):
                        text = line[11:]
                        self.memory_enhanced.memory_logger.log_llm_response(text, model="legacy")

                self.memory_enhanced.memory_logger.end_conversation()

                # Condense into episode
                if self.memory_enhanced.auto_condense:
                    self.memory_enhanced._auto_condense_episodes()

                print(f"[memory] ✓ Migrated {len(conversations)} legacy messages to episode {migration_id}")

                # Archive old file
                backup_file = legacy_file.with_suffix('.json.backup')
                os.rename(legacy_file, backup_file)
                print(f"[memory] ✓ Archived legacy file to {backup_file}")

        except Exception as e:
            print(f"[memory] ⚠️ Migration failed: {e}")

    # =============== Speaker enrollment helpers ===============
    # =============== System Introspection ===============
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

    def _handle_enrollment_commands(self, user_message: str, confidence: float = 1.0, audio_quality: dict = None) -> Optional[str]:
        """Handle speaker enrollment using simple conversation flow."""
        if not self.enable_speaker_id or self.speaker_backend is None:
            return None

        message_lower = user_message.lower().strip()
        enrollment = self.enrollment_conversation

        # Start enrollment command
        if any(phrase in message_lower for phrase in ["enroll me", "add my voice", "remember my voice", "learn my voice"]):
            if enrollment["active"]:
                return "I'm already helping you with enrollment. Please say 'cancel enrollment' to start over."

            enrollment["active"] = True
            enrollment["user_name"] = ""
            enrollment["sentence_index"] = 0
            enrollment["audio_samples"] = []
            enrollment["sentences"] = []
            log_event("enrollment_started")
            return "Let's set up your voice profile! First, please tell me your name."

        # Cancel enrollment
        if enrollment["active"] and any(phrase in message_lower for phrase in ["cancel", "stop", "quit"]):
            enrollment["active"] = False
            enrollment["user_name"] = ""
            enrollment["sentence_index"] = 0
            enrollment["audio_samples"] = []
            enrollment["sentences"] = []
            log_event("enrollment_cancelled")
            return "Voice enrollment cancelled. You can start again anytime by saying 'enroll me'."

        # Handle enrollment conversation flow
        if enrollment["active"]:
            return self._handle_enrollment_conversation(user_message)

        # Speaker management commands
        if "list users" in message_lower or "who do you know" in message_lower:
            return self._list_enrolled_users()

        if "delete user" in message_lower or "remove user" in message_lower:
            words = user_message.split()
            for i, word in enumerate(words):
                if word.lower() in ["user", "voice"] and i + 1 < len(words):
                    user_to_delete = words[i + 1].lower()
                    return self._delete_user(user_to_delete)
            return "Please specify which user to delete, like 'delete user alice'."

        return None

    def _handle_enrollment_conversation(self, user_message: str) -> str:
        """Handle enrollment as a simple conversation using proven audio pipeline."""
        enrollment = self.enrollment_conversation

        # Step 1: Get user name
        if not enrollment["user_name"]:
            name = user_message.strip()
            if len(name) < 2:
                return "That name seems too short. Could you tell me your full first name?"
            if len(name) > 50:
                return "That name seems quite long. Could you just tell me your first name?"

            enrollment["user_name"] = name.title()

            # Set up enrollment sentences
            if ENROLLMENT_SENTENCES is None:
                # Generate natural LLM response for missing enrollment sentences
                return self.chat("The enrollment sentence templates aren't available in my system right now")

            from src.speaker.enrollment import format_enrollment_sentences
            enrollment["sentences"] = format_enrollment_sentences(enrollment["user_name"])

            log_event("enrollment_name_provided", name=enrollment["user_name"])
            # Generate natural LLM response for starting enrollment
            return self.chat(f"Great! I'll call you {enrollment['user_name']}. Now I need you to repeat {len(enrollment['sentences'])} sentences so I can learn your voice. The first sentence is: '{enrollment['sentences'][0]}'")

        # Step 2: Collect sentence recordings
        if enrollment["sentence_index"] < len(enrollment["sentences"]):
            # Capture audio from the proven conversation pipeline
            if hasattr(self, '_last_audio_bytes') and self._last_audio_bytes:
                audio_bytes = self._last_audio_bytes

                # Validate audio quality
                min_audio_length = self.sample_rate * 2  # 2 bytes per sample, 1 second
                if len(audio_bytes) >= min_audio_length:
                    enrollment["audio_samples"].append(audio_bytes)
                    enrollment["sentence_index"] += 1

                    log_event("enrollment_sample_captured",
                             sentence_index=enrollment["sentence_index"],
                             audio_length=len(audio_bytes))

                    # Check if we need more sentences
                    if enrollment["sentence_index"] < len(enrollment["sentences"]):
                        next_sentence = enrollment["sentences"][enrollment["sentence_index"]]
                        # Generate natural LLM response for next sentence
                        return self.chat(f"Got it! Now sentence {enrollment['sentence_index'] + 1} of {len(enrollment['sentences'])}: '{next_sentence}'")
                    else:
                        # All sentences collected - complete enrollment
                        return self._complete_enrollment()
                else:
                    # Generate natural LLM response for short recording
                    return self.chat("That recording was too short - could you speak the sentence more clearly and completely?")
            else:
                # Generate natural LLM response for no audio
                return self.chat("I didn't capture any audio that time - please speak the sentence clearly")

        # Generate natural LLM response for unexpected state
        return self.chat("I'm not sure what happened with the enrollment - you can say 'cancel enrollment' to start over")

    def _complete_enrollment(self) -> str:
        """Complete the enrollment process using captured audio samples."""
        enrollment = self.enrollment_conversation

        try:
            if self.speaker_backend and hasattr(self.speaker_backend, "enroll_user"):
                # Validate we have enough samples
                if len(enrollment["audio_samples"]) < 3:
                    log_event("enrollment_insufficient_samples",
                             user_name=enrollment["user_name"],
                             sample_count=len(enrollment["audio_samples"]))
                    # Generate natural LLM response for insufficient samples
                    return self.chat(f"I only captured {len(enrollment['audio_samples'])} samples but I need at least 3 to create a reliable voice profile - let's try enrolling again by saying 'enroll me'")

                # Save to speaker backend
                success = self.speaker_backend.enroll_user(
                    enrollment["user_name"].lower(), enrollment["audio_samples"], self.sample_rate
                )

                if success:
                    log_event("enrollment_completed", user_name=enrollment["user_name"])

                    # Reset enrollment state
                    enrollment["active"] = False
                    enrollment["user_name"] = ""
                    enrollment["sentence_index"] = 0
                    enrollment["audio_samples"] = []
                    enrollment["sentences"] = []

                    # Generate natural LLM response for successful enrollment
                    return self.chat(f"Perfect! Your voice profile has been saved, {enrollment['user_name']}. I'll recognize you from now on.")
                else:
                    log_event("enrollment_backend_failed", user_name=enrollment["user_name"])
                    # Generate natural LLM response for save failure
                    return self.chat("There was an error saving your voice profile - let's try enrolling again by saying 'enroll me'")

            else:
                log_event("enrollment_no_backend")
                # Generate natural LLM response for missing backend
                return self.chat("Voice enrollment isn't available right now because the speaker recognition system isn't configured")

        except Exception as e:
            log_event("enrollment_exception", user_name=enrollment["user_name"], error=str(e))
            # Generate natural LLM response for exception
            return self.chat(f"I hit an unexpected error during enrollment: {str(e)} - let's try again by saying 'enroll me'")


    def _list_enrolled_users(self) -> str:
        """List all enrolled users."""
        if not self.speaker_backend or not hasattr(self.speaker_backend, "list_users"):
            return "Speaker recognition is not available."

        try:
            users = self.speaker_backend.list_users()
            if not users:
                return "No users are enrolled yet. Say 'enroll me' to add your voice."
            else:
                user_list = ", ".join(users)
                return f"I know these voices: {user_list}"
        except Exception as e:
            return f"Error listing users: {e}"


    def _delete_user(self, user_id: str) -> str:
        """Delete a user's voice profile."""
        if not self.speaker_backend or not hasattr(self.speaker_backend, "delete_user"):
            return "Speaker recognition is not available."

        try:
            success = self.speaker_backend.delete_user(user_id)
            if success:
                log_event("user_deleted", user_id=user_id)
                return f"I've forgotten {user_id}'s voice."
            else:
                return f"I don't know anyone named {user_id}."
        except Exception as e:
            return f"Error deleting user: {e}"

    # =============== RAG integration helpers ===============
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

    def _normalize_tts_text(self, text: str) -> str:
        """
        Force 'KLoROS' to be pronounced as a word, not spelled out.
        Piper TTS needs phonetic hints to avoid treating it as an acronym.
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

    def speak(self, text: str) -> None:
        """Synthesize and play speech via TTS backend."""
        from src.middleware import sanitize_output
        
        # Sanitize output before TTS (remove Portal references)
        text = sanitize_output(text, aggressive=False)
        text = self._normalize_tts_text(text)

        if not self.enable_tts or self.tts_backend is None:
            if self.fail_open_tts:
                print(f"[TTS] Backend unavailable; printing to console: {text}")
                return
            else:
                print("[TTS] Backend unavailable and fail_open disabled")
                return

        try:
            # Arm suppression BEFORE synthesis to prevent echo during TTS generation
            synthesis_armed = False
            if self.tts_suppression_enabled and platform.system() == "Linux":
                self._pre_tts_suppress()
                synthesis_armed = True

            # Synthesize audio using TTS backend
            result = self.tts_backend.synthesize(
                text,
                sample_rate=self.tts_sample_rate,
                voice=os.getenv("KLR_PIPER_VOICE"),
                out_dir=self.tts_out_dir,
            )

            # Log TTS completion
            log_event(
                "tts_done",
                audio_path=result.audio_path,
                duration_s=result.duration_s,
                sample_rate=result.sample_rate,
                voice=result.voice,
            )

            print(f"[TTS] Synthesized: {result.audio_path} ({result.duration_s:.2f}s)")

            # Save last TTS output for E2E testing
            try:
                import shutil
                last_tts_path = Path.home() / ".kloros" / "tts" / "last.wav"
                last_tts_path.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(result.audio_path, last_tts_path)
                print(f"[TTS] Saved to {last_tts_path} for E2E testing")
            except Exception as e:
                print(f"[TTS] Failed to save last output: {e}")


            # Log TTS to memory system
            if hasattr(self, "memory_enhanced") and self.memory_enhanced and self.memory_enhanced.enable_memory:
                try:
                    self.memory_enhanced.log_tts_output(
                        text=text,
                        voice_model=result.voice or "piper"
                    )
                except Exception as e:
                    print(f"[memory] TTS logging failed: {e}")

            # Play audio on Linux hosts
            if platform.system() == "Linux":
                # Suppression already armed before synthesis (synthesis_armed flag)
                # No need to arm again here

                try:
                    # Hardware-level mic muting (if enabled)
                    # Strip inline comments from env var before parsing
                    tts_mute_val = os.getenv("KLR_TTS_MUTE", "0").split("#")[0].strip()
                    use_hardware_mute = int(tts_mute_val)
                    if use_hardware_mute:
                        try:
                            from src.audio.mic_mute import mute_during_playback
                            # Keep mic muted for 500ms after response to prevent echo pickup
                            with mute_during_playback(result.duration_s, buffer_ms=500, audio_backend=self.audio_backend):
                                cmd = self._playback_cmd(result.audio_path)
                                print(f"[playback] Running with hardware mute: {" ".join(cmd)}")
                                proc = subprocess.run(cmd, capture_output=True, check=False)  # nosec B603, B607
                        except ImportError:
                            print(f"[TTS] Hardware mute unavailable, using software suppression only")
                            use_hardware_mute = False

                    if not use_hardware_mute:
                        # Standard playback without hardware muting
                        cmd = self._playback_cmd(result.audio_path)
                        print(f"[playback] Running: {" ".join(cmd)}")
                        proc = subprocess.run(cmd, capture_output=True, check=False)  # nosec B603, B607

                    if proc.returncode != 0:
                        print(f"[playback] Failed with code {proc.returncode}: {proc.stderr.decode()}")
                    else:
                        print(f"[playback] Success")

                except Exception as e:
                    print(f"[TTS] Audio playback failed: {e}")
                finally:
                    # Post-playback cooldown and flush, then disarm suppression
                    # Pass audio duration for dynamic echo tail
                    self._post_tts_cooldown_and_flush(audio_duration_s=result.duration_s if result else 0.0)
                    if synthesis_armed and self.tts_suppression_enabled:
                        self._clear_tts_suppress()

        except Exception as e:
            print(f"[TTS] Synthesis failed: {e}")
            # If synthesis failed but we armed suppression, clear it
            if synthesis_armed and self.tts_suppression_enabled:
                self._clear_tts_suppress()
            if self.fail_open_tts:
                print(f"[TTS] Falling back to console: {text}")
            else:
                print("[TTS] Fail_open disabled; no fallback")

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

    def record_until_silence(self) -> bytes:
        """
        Wait start_timeout_ms for speech to begin, then record until trailing
        silence_end_ms is observed. Ensure we captured at least min_cmd_ms of speech.
        Returns raw int16 mono bytes at self.sample_rate (or b'' on no speech).
        """
        # Reset Silero VAD state before each recording to prevent contamination
        if self.vad_type == "silero" and hasattr(self, 'vad_model') and hasattr(self.vad_model, 'reset_states'):
            try:
                self.vad_model.reset_states()
                print("[vad] Reset Silero model state before recording")
            except Exception as e:
                print(f"[vad] Failed to reset Silero state: {e}")

        sr = self.sample_rate
        max_frames = int(self.max_cmd_s * 1000 / self.frame_ms)
        silence_needed = int(self.silence_end_ms / self.frame_ms)
        preroll_needed = int(self.preroll_ms / self.frame_ms)
        min_cmd_frames = int(self.min_cmd_ms / self.frame_ms)

        started = False
        silence_run = 0
        total_frames = 0
        speech_frames = 0

        preroll: collections.deque[bytes] = collections.deque(maxlen=preroll_needed)
        captured: list[bytes] = []

        t0 = time.monotonic()
        while total_frames < max_frames:
            try:
                data = self.audio_queue.get(timeout=0.3)
            except queue.Empty:
                # bail cleanly if we never started and timed out
                if not started and (time.monotonic() - t0) * 1000 >= self.start_timeout_ms:
                    return b""
                continue

            for frame in self._chunker(data, sr, self.frame_ms):
                is_speech = self._is_speech(frame, sr)
                total_frames += 1

                if not started:
                    preroll.append(frame)
                    # timeout check while waiting for first speech
                    if (time.monotonic() - t0) * 1000 >= self.start_timeout_ms and not is_speech:
                        if total_frames >= max_frames:
                            return b""
                        continue
                    if is_speech:
                        started = True
                        captured.extend(preroll)  # include some audio before speech
                        silence_run = 0
                        speech_frames = 1
                    continue

                captured.append(frame)
                if is_speech:
                    speech_frames += 1
                    silence_run = 0
                else:
                    silence_run += 1
                    # only end if we’ve seen enough trailing silence AND enough speech
                    if silence_run >= silence_needed and speech_frames >= min_cmd_frames:
                        end = len(captured) - silence_run
                        return b"".join(captured[: max(end, 0)])

        # hit hard cap; return what we have
        return b"".join(captured)

    # -------- Wake gating helpers --------
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

    def _process_audio_chunks(self) -> None:
        """Process audio using the new chunked capture system."""
        if self.audio_backend is None:
            print("[audio] No audio backend available, falling back to legacy method")
            self.listen_for_wake_word()
            return

        self.listening = True
        log_event(
            "chunk_listen_started",
            backend=self.audio_backend_name,
            sample_rate=self.audio_sample_rate,
            block_ms=self.audio_block_ms,
        )
        self._emit_persona("quip", {"line": "Listening with chunked audio capture."})

        try:
            # Accumulate chunks for processing
            chunk_buffer = []
            buffer_duration_s = float(os.getenv("KLR_CHUNK_BUFFER_DURATION_S", "3.5"))  # Configurable buffer duration
            target_chunks = int(buffer_duration_s * 1000 / self.audio_block_ms)

            for chunk in self.audio_backend.chunks(self.audio_block_ms):
                if not self.listening:
                    break

                chunk_buffer.append(chunk)

                # When we have enough chunks, process as a turn
                if len(chunk_buffer) >= target_chunks:
                    # TTS suppression: skip processing during TTS output
                    if self.tts_suppression_enabled and self.tts_playing_evt.is_set():
                        chunk_buffer = []  # Clear buffer and continue
                        continue

                    # Combine chunks into single audio buffer
                    audio_buffer = np.concatenate(chunk_buffer)

                    # Only process if we have reasonable audio energy
                    rms = np.sqrt(np.mean(audio_buffer**2))
                    if rms > 0.001:  # Basic energy gate for float32 audio
                        try:
                            # Use the turn orchestrator if available
                            if run_turn is not None and self.stt_backend is not None:
                                # Create reasoning function with enrollment command handling
                                def reason_fn(transcript: str) -> str:
                                    # Check for enrollment commands first (before RAG backend)
                                    enrollment_response = self._handle_enrollment_commands(transcript)
                                    if enrollment_response:
                                        return enrollment_response

                                    if self.reason_backend:
                                        result = self.reason_backend.reply(transcript, kloros_instance=self)
                                        return result.reply_text
                                    else:
                                        return self.chat(transcript)

                                # Get VAD threshold
                                vad_threshold = self._get_vad_threshold()

                                # Store audio for enrollment capture
                                audio_bytes = (audio_buffer * 32767.0).astype(np.int16).tobytes()
                                self._last_audio_bytes = audio_bytes

                                # Run the turn with two-stage VAD support
                                turn_result = run_turn(
                                    audio=audio_buffer,
                                    sample_rate=self.audio_sample_rate,
                                    stt=self.stt_backend,
                                    reason_fn=reason_fn,
                                    tts=self.tts_backend,
                                    vad_threshold_dbfs=vad_threshold,
                                    silero_vad=self._get_silero_vad_wrapper() if self.vad_type == "two_stage" else None,
                                    use_two_stage=(self.vad_type == "two_stage"),
                                    stage_a_threshold_dbfs=float(os.getenv("KLR_VAD_STAGE_A_THRESHOLD", "-28.0")),
                                    stage_b_threshold=float(os.getenv("KLR_VAD_STAGE_B_THRESHOLD", "0.60")),
                                    max_cmd_ms=int(os.getenv("KLR_VAD_MAX_CMD_MS", "5500")),
                                    prefer_first=True,
                                    max_turn_seconds=self.max_turn_seconds,
                                    logger=self.json_logger if self.json_logger else None,
                                )

                                if turn_result.ok:
                                    print(
                                        f"[turn] Successful turn: '{turn_result.transcript}' -> '{turn_result.reply_text}'"
                                    )
                                    self._log_event(
                                        "turn_completed",
                                        transcript=turn_result.transcript,
                                        reply=turn_result.reply_text,
                                        timings=turn_result.timings_ms,
                                    )

                                    # Play TTS if synthesized by orchestrator
                                    if turn_result.tts and turn_result.tts.audio_path:
                                        # Arm half-duplex suppression before playback
                                        if self.tts_suppression_enabled:
                                            self._pre_tts_suppress()

                                        try:
                                            # Play the audio with hardware mute if enabled
                                            import platform
                                            import subprocess
                                            if platform.system() == "Linux":
                                                # Check if hardware mute is enabled
                                                tts_mute_val = os.getenv("KLR_TTS_MUTE", "0").split("#")[0].strip()
                                                use_hardware_mute = int(tts_mute_val)

                                                if use_hardware_mute:
                                                    try:
                                                        from src.audio.mic_mute import mute_during_playback
                                                        audio_dur = turn_result.tts.duration_s if turn_result.tts else 0.0
                                                        print(f"[playback] Playing with hardware mute: {turn_result.tts.audio_path} ({audio_dur:.2f}s)")
                                                        # Keep mic muted for 500ms after response to prevent echo pickup
                                                        with mute_during_playback(audio_dur, buffer_ms=500, audio_backend=self.audio_backend):
                                                            subprocess.run(
                                                                self._playback_cmd(turn_result.tts.audio_path),
                                                                capture_output=True,
                                                                check=False,
                                                            )
                                                    except ImportError:
                                                        print(f"[playback] Hardware mute unavailable")
                                                        use_hardware_mute = False

                                                if not use_hardware_mute:
                                                    print(f"[playback] Playing: {turn_result.tts.audio_path}")
                                                    subprocess.run(
                                                        self._playback_cmd(turn_result.tts.audio_path),
                                                        capture_output=True,
                                                        check=False,
                                                    )
                                        except Exception as e:
                                            print(f"[playback] TTS playback error: {e}")
                                        finally:
                                            # Post-playback cooldown and flush, then disarm suppression
                                            # Pass audio duration for dynamic echo tail
                                            audio_dur = turn_result.tts.duration_s if turn_result.tts else 0.0
                                            self._post_tts_cooldown_and_flush(audio_duration_s=audio_dur)
                                            if self.tts_suppression_enabled:
                                                self._clear_tts_suppress()
                                    elif turn_result.reply_text:
                                        # Fallback: use speak() if no TTS was synthesized
                                        self.speak(turn_result.reply_text)
                                else:
                                    print(f"[turn] Turn failed: {turn_result.reason}")

                        except Exception as e:
                            print(f"[turn] Error processing audio: {e}")

                    # Reset buffer
                    chunk_buffer = []

        except KeyboardInterrupt:
            pass
        except Exception as e:
            print(f"[audio] Chunked processing error: {e}")
            # Fall back to legacy method
            self.listen_for_wake_word()
        finally:
            if self.audio_backend:
                self.audio_backend.close()

    def listen_for_wake_word(self) -> None:
        self.listening = True
        log_event(
            "listen_started",
            device=self.input_device_index,
            sample_rate=self.sample_rate,
        )
        self._emit_persona("quip", {"line": "Listening for your next whim."})

        if self.audio_backend is None:
            print("[audio] No audio backend available for wake word detection")
            return

        try:
            print(f"[audio] Wake loop using {self.audio_backend_name} backend")

            # Systemd watchdog notification
            watchdog_counter = 0
            watchdog_interval = int(60000 / self.audio_block_ms)  # Notify every ~60 seconds

            # Process audio chunks from the unified backend
            for chunk in self.audio_backend.chunks(self.audio_block_ms):
                if not self.listening:
                    break

                # Check maintenance mode before processing
                wait_for_normal_mode()

                # Send watchdog keepalive to systemd every 60 seconds
                watchdog_counter += 1
                if watchdog_counter >= watchdog_interval:
                    try:
                        import socket
                        sock = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
                        sock.sendto(b"WATCHDOG=1", "/run/systemd/notify")
                        sock.close()
                    except Exception:
                        pass  # Gracefully handle if not running under systemd
                    watchdog_counter = 0

                # Skip processing during TTS playback (half-duplex suppression)
                if self.tts_suppression_enabled and self.tts_playing_evt.is_set():
                    time.sleep(0.001)  # Avoid tight spin
                    continue

                # Apply input gain, then convert float32 chunk to int16 for Vosk
                gained_chunk = chunk * self.input_gain
                gained_chunk = np.clip(gained_chunk, -1.0, 1.0)
                int16_chunk = (gained_chunk * 32767).astype(np.int16)
                data = int16_chunk.tobytes()
                
                # Fill audio queue for record_until_silence() to use later
                try:
                    self.audio_queue.put_nowait(data)
                except queue.Full:
                    # Drain oldest if full to prevent blocking
                    try:
                        self.audio_queue.get_nowait()
                        self.audio_queue.put_nowait(data)
                    except queue.Empty:
                        pass

                # Perform idle reflection during quiet periods
                if self.reflection_manager and hasattr(self, 'reflection_manager'):
                    try:
                        self.reflection_manager.perform_reflection()
                    except Exception as e:
                        print(f"[reflection] Reflection error: {e}")

                # Perform scheduled housekeeping during quiet periods
                if self.housekeeping_scheduler and hasattr(self, 'housekeeping_scheduler'):
                    try:
                        self.housekeeping_scheduler.run_scheduled_maintenance()
                    except Exception as e:
                        print(f"[housekeeping] Maintenance error: {e}")

                # --- TTS suppression: skip processing during TTS output ---
                if self.tts_suppression_enabled and self.tts_playing_evt.is_set():
                    continue

                # --- energy gate: skip tiny/noisy chunks before recognition ---
                rms = self._rms16(data)
                if rms < self.wake_rms_min:
                    continue

                # Grammar-limited recognizer for wake detection (skip if model missing)
                if self.wake_rec is None:
                    # No STT model available — fall back to RMS-only gating for diagnostics
                    print(f"[wake] Vosk model missing; rms={rms} (no recognition)")
                    continue

                if self.wake_rec.AcceptWaveform(data):
                    res = json.loads(self.wake_rec.Result())
                    text = (res.get("text") or "").lower().strip()
                    avgc = self._avg_conf(res)
                    if text and text != "[unk]":
                        print(f"\n[wake-final] {text}  (avg_conf={avgc:.2f}, rms={rms})")
                        log_event(
                            "wake_result",
                            transcript=text,
                            confidence=avgc,
                            rms=rms,
                        )

                    # Fuzzy wake-word matching with debounce/cooldown
                    is_match, score, phrase = fuzzy_wake_match(
                        text, self.wake_phrases, threshold=self.fuzzy_threshold
                    )
                    now_ms = time.monotonic() * 1000
                    # DEBUG: Show fuzzy match results only for valid candidates (not [unk])
                    if text and text != "[unk]":
                        print(f"[wake-debug] match={is_match}, score={score:.3f}, phrase='{phrase}', wake_phrases={self.wake_phrases}, threshold={self.fuzzy_threshold}")
                    if (
                        is_match
                        and avgc >= self.wake_conf_min
                        and (now_ms - self._last_wake_ms) > self.wake_cooldown_ms
                        and (now_ms - self._last_emit_ms) > self.wake_debounce_ms
                        and not self.enrollment_conversation["active"]  # Skip wake detection during enrollment
                    ):
                        print("[WAKE] Detected wake phrase!")
                        play_wake_chime()  # Audio confirmation
                        log_event(
                            "wake_confirmed",
                            transcript=text,
                            matched_phrase=phrase,
                            fuzzy_score=score,
                            confidence=avgc,
                            rms=rms,
                        )
                        self._last_wake_ms = now_ms

                        # Log wake detection to memory system
                        if hasattr(self, "memory_enhanced") and self.memory_enhanced and self.memory_enhanced.enable_memory:
                            try:
                                self.memory_enhanced.log_wake_detection(
                                    transcript=text,
                                    confidence=avgc,
                                    wake_phrase=phrase
                                )
                            except Exception as e:
                                print(f"[memory] Wake detection logging failed: {e}")

                        # Check for pending alerts before normal conversation
                        if self._check_and_present_alerts():
                            # Alert was presented, now enter conversation mode for response
                            self.handle_conversation()
                        else:
                            # No alerts, proceed with normal conversation
                            self.handle_conversation()
                        # reset recognizers for next round (guarded creation)
                        if self.vosk_model is not None:
                            self.vosk_rec = vosk.KaldiRecognizer(
                                self.vosk_model, self.sample_rate
                            )
                            self.wake_rec = vosk.KaldiRecognizer(
                                self.vosk_model, self.sample_rate, self.wake_grammar
                            )
                else:
                    # Partial results suppressed to reduce log spam
                    pass
        except Exception as e:
            import traceback
            print("\n[audio] Wake loop error:", e)
            print("[audio] Full traceback:")
            traceback.print_exc()

    def _check_and_present_alerts(self) -> bool:
        """Check for pending alerts and present them if found.

        Returns:
            bool: True if alerts were presented, False if no alerts pending
        """
        if not self.alert_manager:
            return False

        try:
            # Sync passive alerts from background system into next-wake queue
            if self.passive_sync:
                synced_count = self.passive_sync.sync_pending_alerts()
                if synced_count > 0:
                    print(f"[alerts] Synced {synced_count} alert(s) from background system")

            # Check for pending reflection insights (NEW)
            reflection_method = self.alert_manager.alert_methods.get("reflection_insight")
            reflection_insights = []
            if reflection_method:
                reflection_insights = reflection_method.get_pending_for_presentation()

            # Check next-wake method for pending alerts
            next_wake_method = self.alert_manager.alert_methods.get("next_wake")
            if not next_wake_method:
                return False

            pending_alerts = next_wake_method.get_pending_for_presentation()

            # Combine alerts and insights (NEW - prioritize insights for engagement)
            if not pending_alerts and not reflection_insights:
                return False

            # Format alert/insight message
            alert_message = ""

            # Prioritize reflection insights first (more conversational/engaging)
            if reflection_insights:
                insight_message = reflection_method.format_insight_message(reflection_insights)
                alert_message = insight_message

                # If there are also improvement alerts, mention them
                if pending_alerts:
                    alert_message += f"\n\nI also have {len(pending_alerts)} improvement proposal(s) if you'd like to hear about them."
            elif pending_alerts:
                alert_message = next_wake_method.format_next_wake_message(pending_alerts)

            if alert_message:
                print(f"[alerts] Presenting {len(pending_alerts)} pending alert(s)")

                # Use the TTS system to speak the alert
                if self.tts_backend:
                    try:
                        result = self.tts_backend.synthesize(alert_message)
                        if result and result.audio_path:
                            # Play the synthesized alert audio with mic muted to prevent echo
                            import subprocess
                            from src.audio.mic_mute import mute_during_playback

                            duration_s = getattr(result, "duration_s", 2.0)
                            with mute_during_playback(duration_s=duration_s,
                                                      buffer_ms=200,
                                                      audio_backend=self.audio_backend):
                                subprocess.run(self._playback_cmd(result.audio_path), capture_output=True, check=False)  # nosec B603

                        # DON'T mark alerts as presented yet - wait for user response!
                        # They will be marked as presented when user approves/rejects in _handle_alert_response()

                        # Set up alert response mode with alerts still in queue
                        self._alert_response_mode = {
                            "active": True,
                            "presented_alerts": pending_alerts,
                            "next_wake_method": next_wake_method,  # Store reference for later cleanup
                            "reflection_insights": reflection_insights if reflection_insights else [],
                            "reflection_method": reflection_method
                        }

                        return True

                    except Exception as e:
                        print(f"[alerts] Failed to synthesize alert message: {e}")
                        return False
                else:
                    print("[alerts] No TTS backend available for alert presentation")
                    return False

        except Exception as e:
            print(f"[alerts] Error checking/presenting alerts: {e}")
            return False

        return False

    def _cleanup_presented_alert(self, request_id: str) -> None:
        """Clean up alert after user has responded (approved/rejected).

        Args:
            request_id: The alert request ID to clean up
        """
        try:
            # Get references from alert response mode
            next_wake_method = self._alert_response_mode.get("next_wake_method")

            # Mark as presented in next-wake queue
            if next_wake_method:
                next_wake_method.mark_presented([request_id])

            # Clear from passive sync
            if self.passive_sync:
                self.passive_sync.clear_synced_alerts([request_id])

            print(f"[alerts] Cleaned up presented alert {request_id}")

        except Exception as e:
            print(f"[alerts] Error cleaning up presented alert: {e}")

    def _handle_alert_response(self, transcript: str) -> Optional[str]:
        """Handle user responses to alert presentations.

        Args:
            transcript: User's spoken response

        Returns:
            str: Response to speak back, or None if not an alert command
        """
        if not self.alert_manager or not self._alert_response_mode.get("active", False):
            return None

        try:
            # Process the response through alert manager
            response_result = self.alert_manager.process_user_response(transcript, "voice")

            if response_result.get("success", False):
                action = response_result.get("action", "unknown")

                if action == "approved":
                    request_id = response_result.get("request_id", "unknown")

                    # Clean up: Mark alert as presented now that user responded
                    self._cleanup_presented_alert(request_id)

                    # Disable alert mode since we processed the response
                    self._alert_response_mode["active"] = False

                    # Check deployment status
                    if response_result.get("deployment_status") == "completed":
                        return f"Excellent! I've approved and deployed the improvement. {response_result.get('message', '')}"
                    elif response_result.get("deployment_status") == "failed":
                        return f"I approved the improvement, but deployment failed: {response_result.get('error', 'Unknown error')}"
                    else:
                        return f"Excellent! I've approved improvement {request_id} for implementation. The enhancement will be deployed shortly."

                elif action == "rejected":
                    request_id = response_result.get("request_id", "unknown")

                    # Clean up: Mark alert as presented now that user responded
                    self._cleanup_presented_alert(request_id)

                    # Disable alert mode since we processed the response
                    self._alert_response_mode["active"] = False
                    return f"Understood. I've rejected improvement {request_id} and removed it from the queue."

                elif action == "explanation":
                    explanation = response_result.get("explanation", "No details available.")
                    # Stay in alert mode for follow-up approval/rejection
                    return explanation

                elif action == "status":
                    message = response_result.get("message", "No pending improvements.")
                    # Stay in alert mode for follow-up commands
                    return message

            else:
                # Failed to parse, provide guidance
                error = response_result.get("error", "Unknown error")
                suggestion = response_result.get("suggestion", "")

                if "Could not parse response" in error:
                    # Generate natural LLM response for unparseable command
                    return self.chat(f"I didn't understand that command - {suggestion}")
                else:
                    # Generate natural LLM response for processing issue
                    return self.chat(f"There was an issue processing your response: {error}")

        except Exception as e:
            print(f"[alerts] Error handling alert response: {e}")
            # Disable alert mode on error to prevent getting stuck
            self._alert_response_mode["active"] = False
            # Generate natural LLM response for error
            return self.chat(f"I encountered an error processing your response: {str(e)} - let's continue with normal conversation")

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

    def _create_reason_function(self):
        """Create a reasoning function for the turn orchestrator."""

        def reason_fn(transcript: str) -> str:
            """Generate response from transcript using reasoning backend or fallback."""
            if not transcript:
                return ""

            # Check for alert responses first if we're in alert mode
            if self._alert_response_mode.get("active", False):
                alert_response = self._handle_alert_response(transcript)
                if alert_response:
                    return alert_response

            # Check for improvement status queries (even when not in alert mode)
            if self.alert_manager:
                improvement_response = self._handle_improvement_queries(transcript)
                if improvement_response:
                    return improvement_response

            # Check for enrollment commands first (including ongoing enrollment flow)
            enrollment_response = self._handle_enrollment_commands(transcript)
            if enrollment_response:
                return enrollment_response

            # Check for identity/name queries
            identity_response = self._handle_identity_commands(transcript)
            if identity_response:
                return identity_response

            # Check for conversation exit intent
            exit_response = self._detect_conversation_exit(transcript)
            if exit_response:
                return exit_response

            # Ingest user input through conversation flow
            state, normalized_transcript = self.conversation_flow.ingest_user(transcript)

            # Build conversation context for better threading
            flow_context = self.conversation_flow.context_block(
                preamble=self.system_prompt
            )

            # Apply existing safety checks (relaxed for better conversational flow)
            if self._command_is_risky(normalized_transcript):
                # Log risky command but allow LLM to decide response
                log_event("risky_command_detected", command=transcript)
                # Continue to LLM instead of blocking

            # Route through unified reasoning (consciousness + reasoning + expression)
            reply = self._unified_reasoning(normalized_transcript, confidence=0.85)

            # Ingest assistant response into conversation flow
            self.conversation_flow.ingest_assistant(reply)

            # Apply dialogue policy
            return self.dialogue_policy.apply(reply)

        return reason_fn


    def _generate_wake_acknowledgment(self) -> str:
        """Generate a natural wake acknowledgment - simple and fast."""
        # Use simple static acknowledgements for speed
        # Wake acknowledgement should be instant, not go through RAG pipeline
        import random
        acknowledgements = [
            "Yes?",
            "I'm here.",
            "Listening.",
            "Ready.",
            "Go ahead."
        ]
        return random.choice(acknowledgements)


    # Properly structured handle_conversation method
    def handle_conversation(self) -> None:
        """Handle conversation with multi-turn support."""
        import threading

        conversation_active = True
        turn_count = 0
        consecutive_no_voice = 0
        max_turns = int(os.getenv("KLR_MAX_CONVERSATION_TURNS", "5"))
        max_consecutive_no_voice = 2  # Allow one VAD miss before exiting
        conversation_timeout_s = float(os.getenv("KLR_CONVERSATION_TIMEOUT", "15.0"))

        # Initialize conversation exit flag
        self._conversation_exit_requested = False

        # Store original timeout for restoration
        original_timeout = self.start_timeout_ms

        while conversation_active and turn_count < max_turns:
            turn_count += 1
            print(f"[CONVERSATION] Turn {turn_count}/{max_turns}")

            # Send watchdog keepalive at start of each turn
            try:
                import socket
                sock = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
                sock.sendto(b"WATCHDOG=1", "/run/systemd/notify")
                sock.close()
            except Exception:
                pass  # Gracefully handle if not running under systemd

            # Hot-reload capability registry if capabilities.yaml has been updated
            # This enables KLoROS to adopt new modules without restart
            try:
                self._check_and_reload_registry()
            except Exception as e:
                print(f"[registry] Registry reload check failed: {e}")

            # Only say "Yes?" on first turn, not follow-ups
            if turn_count == 1:
                print("[DEBUG] Wake word detected, responding.")

                wake_response = self._generate_wake_acknowledgment()
                if wake_response:
                    # Speak wake acknowledgment WITHOUT clearing suppression afterward
                    # Pass suppress_control=False to prevent automatic unmuting
                    try:
                        # Synthesize wake acknowledgment
                        result = self.tts_backend.synthesize(wake_response)
                        if result and result.audio_path:
                            # Play with hardware mute
                            tts_mute_val = os.getenv("KLR_TTS_MUTE", "0").split("#")[0].strip()
                            use_hardware_mute = int(tts_mute_val)

                            from src.audio.mic_mute import mute_during_playback

                            if use_hardware_mute:
                                print(f"[playback] Wake ack with hardware mute: {result.audio_path}")
                                # Keep mic muted for 500ms after wake ack to let room reverb die down
                                # This prevents picking up echo during the subsequent listening phase
                                with mute_during_playback(result.duration_s, buffer_ms=500, audio_backend=self.audio_backend):
                                    subprocess.run(self._playback_cmd(result.audio_path), capture_output=True, check=False)
                            else:
                                # Even without mute flag, wrap fallback paths to prevent echo
                                with mute_during_playback(result.duration_s, buffer_ms=500, audio_backend=self.audio_backend):
                                    subprocess.run(self._playback_cmd(result.audio_path), capture_output=True, check=False)
                    except Exception as e:
                        print(f"[CONVERSATION] Wake acknowledgment TTS failed: {e}")

                    # Flush audio buffers immediately after "Yes?" to minimize delay
                    # This clears any TTS echo and old buffer, allowing instant user response
                    flush_start = time.time()

                    # Flush backend ring buffer first
                    backend_flushed = 0
                    if hasattr(self.audio_backend, 'flush'):
                        backend_flushed = self.audio_backend.flush()

                    # Then flush audio queue
                    queue_flushed = 0
                    while not self.audio_queue.empty():
                        try:
                            self.audio_queue.get_nowait()
                            queue_flushed += 1
                        except queue.Empty:
                            break

                    flush_time = (time.time() - flush_start) * 1000
                    print(f"[audio] Flushed {backend_flushed} samples + {queue_flushed} queue chunks in {flush_time:.1f}ms for instant response")

                    # Additional settle time after wake ack to avoid picking up own voice
                    # Hardware mute provides 500ms, but add extra buffer for room acoustics
                    settle_delay_ms = int(os.getenv("KLR_WAKE_ACK_SETTLE_MS", "200"))
                    if settle_delay_ms > 0:
                        print(f"[audio] Waiting {settle_delay_ms}ms for room acoustics to settle after wake ack")
                        time.sleep(settle_delay_ms / 1000.0)

            log_event("conversation_start", user=self.operator_id)
            task = {"name": "voice_command", "kind": "interactive", "priority": "high"}
            if should_prioritize(self.operator_id, task):
                log_event("priority_bump", user=self.operator_id, task=task["name"])

            # Start background thread to keep filling audio queue during command recording
            keep_filling = threading.Event()
            keep_filling.set()

            def fill_queue_from_backend():
                """Background thread to continuously fill audio queue from backend."""
                print("[DEBUG] Filler thread started, calling audio_backend.chunks()")
                try:
                    chunk_count = 0
                    for chunk in self.audio_backend.chunks(self.audio_block_ms):
                        if not keep_filling.is_set():
                            print(f"[DEBUG] Filler thread stopping (got {chunk_count} chunks)")
                            break
                        # Echo suppression at source: skip queuing during TTS playback
                        if self.tts_suppression_enabled and self.tts_playing_evt.is_set():
                            time.sleep(0.001)  # Avoid tight spin if backend is non-blocking
                            continue
                        # Apply input gain, then convert float32 to int16
                        gained_chunk = chunk * self.input_gain
                        gained_chunk = np.clip(gained_chunk, -1.0, 1.0)
                        int16_chunk = (gained_chunk * 32767).astype(np.int16)
                        data = int16_chunk.tobytes()
                        try:
                            self.audio_queue.put_nowait(data)
                            chunk_count += 1
                            if chunk_count == 1:
                                print("[DEBUG] Filler thread: first chunk added to queue")
                        except queue.Full:
                            # Drain oldest if full
                            try:
                                self.audio_queue.get_nowait()
                                self.audio_queue.put_nowait(data)
                            except queue.Empty:
                                pass
                    print(f"[DEBUG] Filler thread ended normally (total {chunk_count} chunks)")
                except Exception as e:
                    import traceback
                    print(f"[DEBUG] Queue filler thread error: {e}")
                    traceback.print_exc()

            # Clear queue of wake artifacts
            flushed = 0
            while not self.audio_queue.empty():
                try:
                    self.audio_queue.get_nowait()
                    flushed += 1
                except queue.Empty:
                    break
            if flushed > 0:
                print(f"[DEBUG] Flushed {flushed} chunks from queue before listening for command")

            # Start background filler thread
            filler_thread = threading.Thread(target=fill_queue_from_backend, daemon=True)
            filler_thread.start()
            print(f"[DEBUG] Started background audio queue filler thread")

            print("[DEBUG] Listening for command (VAD).")
            audio_bytes = self.record_until_silence()

            # Stop filler thread
            keep_filling.clear()
            filler_thread.join(timeout=1.0)
            print(f"[DEBUG] Stopped background audio queue filler thread")
            sample_count = len(audio_bytes) // 2
            log_event("audio_capture", samples=sample_count)
            print(f"[DEBUG] Collected {sample_count} samples")

            # Store audio for potential enrollment use
            self._last_audio_bytes = audio_bytes

            # Convert audio to float32 numpy array
            audio_array = np.frombuffer(audio_bytes, dtype=np.int16).astype(np.float32) / 32767.0

            # Speaker identification (if enabled)
            speaker_gate_passed = True  # Default to allowing audio
            if self.enable_speaker_id and self.speaker_backend is not None:
                try:
                    speaker_result = self.speaker_backend.identify_speaker(
                        audio_bytes, self.sample_rate
                    )
                    if speaker_result.is_known_speaker:
                        print(
                            f"[speaker] Identified: {speaker_result.user_id} (confidence: {speaker_result.confidence:.2f})"
                        )
                        # Update operator_id for this interaction
                        self.operator_id = speaker_result.user_id
                        log_event(
                            "speaker_identified",
                            user_id=speaker_result.user_id,
                            confidence=speaker_result.confidence,
                        )
                    else:
                        print(
                            f"[speaker] Unknown speaker (confidence: {speaker_result.confidence:.2f})"
                        )
                        log_event("speaker_unknown", confidence=speaker_result.confidence)

                    # SPEAKER CONFIDENCE GATE: Reject low-confidence audio (likely echo/noise)
                    # This prevents the triple hallucination cascade:
                    # Audio echo → Whisper hallucination → LLM fabrication
                    min_confidence = float(os.getenv("KLR_MIN_SPEAKER_CONFIDENCE", "0.6"))
                    if speaker_result.confidence < min_confidence:
                        print(
                            f"[speaker] REJECTED: Confidence {speaker_result.confidence:.2f} "
                            f"below threshold {min_confidence:.2f} (likely echo/noise)"
                        )
                        log_event(
                            "speaker_rejected_low_confidence",
                            confidence=speaker_result.confidence,
                            threshold=min_confidence
                        )
                        speaker_gate_passed = False

                except Exception as e:
                    print(f"[speaker] Identification failed: {e}")
                    log_event("speaker_error", error=str(e))

            # If speaker gate failed, skip processing entirely
            if not speaker_gate_passed:
                print("[speaker] Skipping audio processing due to low speaker confidence")
                return

            # Check for test override
            test_override = os.getenv("KLR_TEST_TRANSCRIPT")
            if test_override:
                print(f"[TEST] Using transcript override: {test_override}")
                # For test override, create a simple response and speak it
                transcript = test_override.strip()
                response = self.chat(transcript) if transcript else ""
                if response:
                    print(f"KLoROS: {response}")
                    self.speak(response)
                return

            # Use turn orchestrator if available
            if (
                run_turn is not None
                and self.stt_backend is not None
                and self.enable_stt
                and detect_voiced_segments is not None
            ):
                try:
                    # Generate trace ID
                    trace_id = (
                        new_trace_id() if new_trace_id is not None else str(int(time.time() * 1000))
                    )

                    # Create logger adapter that enhances reason_done events with sources
                    class LoggerAdapter:
                        def __init__(self, voice_instance):
                            self.voice = voice_instance

                        def log_event(self, name: str, **payload):
                            # Enhance reason_done events with sources information
                            if name == "reason_done" and hasattr(self.voice, "_last_reasoning_sources"):
                                sources = getattr(self.voice, "_last_reasoning_sources", [])
                                if sources:
                                    payload["sources_count"] = len(sources)
                            self.voice._log_event(name, **payload)

                    # Run orchestrated turn with two-stage VAD support
                    summary = run_turn(
                        audio_array,
                        self.sample_rate,
                        stt=self.stt_backend,
                        reason_fn=self._create_reason_function(),
                        tts=self.tts_backend if self.enable_tts else None,
                        vad_threshold_dbfs=self._get_vad_threshold(),
                        silero_vad=self._get_silero_vad_wrapper() if self.vad_type == "two_stage" else None,
                        use_two_stage=(self.vad_type == "two_stage"),
                        stage_a_threshold_dbfs=float(os.getenv("KLR_VAD_STAGE_A_THRESHOLD", "-28.0")),
                        stage_b_threshold=float(os.getenv("KLR_VAD_STAGE_B_THRESHOLD", "0.60")),
                        max_cmd_ms=int(os.getenv("KLR_VAD_MAX_CMD_MS", "5500")),
                        prefer_first=True,
                        frame_ms=self.vad_frame_ms,
                        hop_ms=self.vad_hop_ms,
                        attack_ms=self.vad_attack_ms,
                        release_ms=self.vad_release_ms,
                        min_active_ms=self.vad_min_active_ms,
                        margin_db=self.vad_margin_db,
                        max_turn_seconds=self.max_turn_seconds,
                        logger=LoggerAdapter(self),
                        trace_id=trace_id,
                    )

                    print(f"[TURN] {summary.trace_id}: {summary.reason}")

                    if summary.ok and summary.reply_text:
                        # Reset no-voice counter on successful turn
                        consecutive_no_voice = 0

                        print(f"[TRANSCRIPT] {summary.transcript}")

                        # Process with meta-cognitive awareness
                        processed_reply = summary.reply_text
                        if process_with_meta_awareness is not None:
                            try:
                                processed_reply = process_with_meta_awareness(
                                    self,
                                    user_input=summary.transcript,
                                    response=summary.reply_text,
                                    confidence=summary.confidence if hasattr(summary, 'confidence') else 1.0
                                )
                            except Exception as e:
                                print(f"[meta-cognition] Processing failed: {e}")

                        print(f"KLoROS: {processed_reply}")

                        # Track TTS duration for dynamic flush
                        tts_duration_s = 0.0

                        # Play audio if TTS was successful
                        if summary.tts and summary.tts.audio_path:
                            # Audio already synthesized by orchestrator
                            tts_duration_s = summary.tts.duration_s or 0.0
                            if platform.system() == "Linux":
                                # Arm half-duplex suppression before playback
                                if self.tts_suppression_enabled:
                                    self._pre_tts_suppress()

                                try:
                                    # Check if hardware mute is enabled
                                    tts_mute_val = os.getenv("KLR_TTS_MUTE", "0").split("#")[0].strip()
                                    use_hardware_mute = int(tts_mute_val)

                                    if use_hardware_mute:
                                        try:
                                            from src.audio.mic_mute import mute_during_playback
                                            print(f"[playback] Playing with hardware mute: {summary.tts.audio_path} ({tts_duration_s:.2f}s)")
                                            # Keep mic muted for 500ms after response to prevent echo pickup
                                            with mute_during_playback(tts_duration_s, buffer_ms=500, audio_backend=self.audio_backend):
                                                subprocess.run(  # nosec B603, B607
                                                    self._playback_cmd(summary.tts.audio_path),
                                                    capture_output=True,
                                                    check=False,
                                                )
                                            print(f"[playback] Completed with hardware mute ({tts_duration_s:.2f}s)")
                                        except ImportError:
                                            print(f"[playback] Hardware mute unavailable")
                                            use_hardware_mute = False

                                    if not use_hardware_mute:
                                        print(f"[playback] Playing: {summary.tts.audio_path} ({tts_duration_s:.2f}s)")
                                        subprocess.run(  # nosec B603, B607
                                            self._playback_cmd(summary.tts.audio_path),
                                            capture_output=True,
                                            check=False,
                                        )
                                        print(f"[playback] Completed ({tts_duration_s:.2f}s)")
                                except Exception as e:
                                    print(f"[TTS] Audio playback failed: {e}")
                                finally:
                                    # Post-playback cooldown and flush, then disarm suppression
                                    if turn_count < max_turns:  # Only flush if continuing conversation
                                        # Pass audio duration for dynamic echo tail
                                        self._post_tts_cooldown_and_flush(audio_duration_s=tts_duration_s)
                                    if self.tts_suppression_enabled:
                                        self._clear_tts_suppress()
                        elif summary.reply_text:
                            # Fallback to speak method if no TTS result (it has its own suppression)
                            self.speak(summary.reply_text)

                        # Check if user requested conversation exit
                        if hasattr(self, '_conversation_exit_requested') and self._conversation_exit_requested:
                            print("[CONVERSATION] User requested exit, ending conversation")
                            conversation_active = False
                            break

                    elif not summary.ok:
                        if summary.reason == "no_voice":
                            consecutive_no_voice += 1
                            print(f"[DEBUG] No voice activity detected (consecutive: {consecutive_no_voice}/{max_consecutive_no_voice})")

                            # Generate natural LLM response for no voice detection
                            response = self._create_reason_function()("I'm listening but I didn't hear anything just now")
                            self.speak(response)

                            # Exit conversation mode after speaking
                            if consecutive_no_voice >= max_consecutive_no_voice:
                                print(f"[CONVERSATION] Exiting after {consecutive_no_voice} consecutive no-voice turns")
                                conversation_active = False
                                break
                        elif summary.reason == "timeout":
                            print("[DEBUG] Turn timed out")
                            # Generate natural LLM response for timeout
                            response = self._create_reason_function()("The audio took too long to process - could you try speaking more concisely?")
                            self.speak(response)
                        else:
                            print(f"[DEBUG] Turn failed: {summary.reason}")
                            # Generate natural LLM response for general failure
                            response = self._create_reason_function()(f"Something didn't work right - the system reported: {summary.reason}")
                            self.speak(response)

                except Exception as e:
                    print(f"[TURN] Orchestrator failed: {e}")
                    log_event("turn_error", error=str(e))
                    # Generate natural LLM response for orchestrator error
                    response = self._create_reason_function()(f"I encountered an error while processing: {str(e)}")
                    self.speak(response)

            else:
                # Fallback to legacy logic when orchestrator unavailable
                print("[DEBUG] Using legacy conversation handling")
                # Generate natural LLM response for unavailable orchestrator
                response = self._create_reason_function()("The voice processing system isn't available right now")
                self.speak(response)

            # Check if conversation should continue
            # Priority: enrollment mode takes precedence over normal conversation flow
            if self.enrollment_conversation["active"]:
                print("[CONVERSATION] Enrollment active, forcing conversation continuation...")
                # Set shorter timeout for enrollment steps
                self.start_timeout_ms = int(conversation_timeout_s * 1000)
                conversation_active = True
            elif self.conversation_flow.current and not self.conversation_flow.current.is_idle():
                print("[CONVERSATION] Waiting for follow-up...")
                # Set shorter timeout for follow-ups
                self.start_timeout_ms = int(conversation_timeout_s * 1000)
                conversation_active = True
            else:
                print("[CONVERSATION] Conversation thread idle, returning to wake mode")
                conversation_active = False

        # Restore original timeout when exiting conversation
        self.start_timeout_ms = original_timeout
        print(f"[CONVERSATION] Exited multi-turn mode after {turn_count} turns")

    # ======================== Main =========================
    def run(self) -> None:
        try:
            # Use chunked audio processing if wakeword is disabled and audio backend is available
            if not self.enable_wakeword and self.audio_backend is not None:
                self._process_audio_chunks()
            else:
                self.listen_for_wake_word()
        except KeyboardInterrupt:
            pass
        finally:
            self.listening = False
            if self.audio_backend:
                self.audio_backend.close()
            self._log_event("shutdown", reason="loop_exit")
            self._emit_persona("quip", {"line": "Shutting down. Try not to miss me."})
            if self.json_logger:
                self.json_logger.close()


def load_kloros_environment():
    """Load environment variables from .kloros_env file before KLoROS initialization.

    This function loads environment variables from the KLoROS configuration file,
    ensuring compatibility with both systemd services and manual execution.
    Variables already set in the environment (e.g., from systemd) take precedence.
    """
    env_file_paths = [
        '/home/kloros/.kloros_env',        # Primary location
        os.path.expanduser('~/.kloros_env'), # Fallback for user home
    ]

    loaded_count = 0
    already_set_count = 0
    total_vars_in_file = 0

    for env_file in env_file_paths:
        if os.path.exists(env_file) and os.access(env_file, os.R_OK):
            try:
                with open(env_file, 'r') as f:
                    for line_num, line in enumerate(f, 1):
                        line = line.strip()

                        # Skip empty lines and comments
                        if not line or line.startswith('#'):
                            continue

                        # Check for valid key=value format
                        if '=' not in line:
                            continue

                        try:
                            key, value = line.split('=', 1)

                            # Handle export prefix and whitespace
                            key = key.replace('export ', '').strip()
                            value = value.strip()

                            # Strip inline comments (# after value)
                            if '#' in value:
                                value = value.split('#')[0].strip()

                            # Remove surrounding quotes if present
                            if (value.startswith('"') and value.endswith('"')) or \
                               (value.startswith("'") and value.endswith("'")):
                                value = value[1:-1]

                            if key:
                                total_vars_in_file += 1
                                # Only set if not already in environment (respect systemd/CLI)
                                if key not in os.environ:
                                    os.environ[key] = value
                                    loaded_count += 1
                                else:
                                    already_set_count += 1

                        except Exception:
                            continue  # Skip malformed lines

                print(f"[env] Environment config: {total_vars_in_file} total, {already_set_count} pre-loaded (systemd), {loaded_count} newly set from {env_file}")
                return  # Success - don't try other paths

            except Exception as e:
                print(f"[env] Warning: Failed to load {env_file}: {e}")
                continue

    print("[env] No environment file found or accessible")


if __name__ == "__main__":
    # Load environment variables before KLoROS initialization
    load_kloros_environment()

    kloros = KLoROS()

    # Notify systemd that we're ready (for Type=notify services)
    try:
        import socket
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
        sock.sendto(b"READY=1", "/run/systemd/notify")
        sock.close()
        print("[systemd] Sent READY=1 notification")
    except Exception:
        pass  # Not running under systemd or notify socket unavailable

    kloros.run()

