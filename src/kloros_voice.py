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
import sounddevice as sd
import vosk

if TYPE_CHECKING:
    from src.rag import RAG as RAGType
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
    from src.rag import RAG as _ImportedRAG  # noqa: E402

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


class KLoROS:
    def __init__(self) -> None:
        # -------------------- Config --------------------
        # system prompt defined in persona module to keep voice logic slim
        self.system_prompt = PERSONA_PROMPT

        self.memory_file = os.path.expanduser("~/KLoROS/kloros_memory.json")
        self.ollama_model = "nous-hermes:13b-q4_0"
        self.ollama_url = "http://localhost:11434/api/generate"
        self.operator_id = os.getenv("KLR_OPERATOR_ID", "operator")

        self.rag: Optional["RAGType"] = None

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
                for i, d in enumerate(sd.query_devices()):
                    # d may be a mapping-like object or a string in some environments — handle both
                    if isinstance(d, dict):
                        name = d.get("name")
                        max_in = d.get("max_input_channels", 0)
                    else:
                        name = str(d)
                        max_in = 0
                    if "CMTECK" in (name or "") and (max_in or 0) > 0:
                        self.input_device_index = i
                        break
            except Exception as e:
                print("[audio] failed to query devices:", e)
                self.input_device_index = None

            # Detect device default sample rate (fallback 48000)
            try:
                idev = sd.query_devices(
                    self.input_device_index
                    if self.input_device_index is not None
                    else sd.default.device[0],
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
        # ~200 ms blocks (snappier partials); keep a lower bound
        self.blocksize = max(256, self.sample_rate // 5)
        self.channels = 1
        self.input_gain = float(os.getenv("KLR_INPUT_GAIN", "1.0"))  # 1.0–2.0

        print(
            f"[audio] input index={self.input_device_index}  SR={self.sample_rate}  block={self.blocksize}"
        )

        # Audio capture backend configuration
        self.audio_backend_name = os.getenv("KLR_AUDIO_BACKEND", "sounddevice")
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
        self.audio_block_ms = int(os.getenv("KLR_AUDIO_BLOCK_MS", "30"))
        self.audio_channels = int(os.getenv("KLR_AUDIO_CHANNELS", "1"))
        self.audio_ring_secs = float(os.getenv("KLR_AUDIO_RING_SECS", "2.0"))
        self.audio_warmup_ms = int(os.getenv("KLR_AUDIO_WARMUP_MS", "200"))
        self.enable_wakeword = int(os.getenv("KLR_ENABLE_WAKEWORD", "1"))

        # Audio backend will be initialized later
        self.audio_backend: Optional[AudioInputBackend] = None

        # -------------------- Models --------------------
        self.piper_model = os.path.expanduser("~/kloros_models/piper/glados_piper_medium.onnx")
        self.piper_config = os.path.expanduser(
            "~/kloros_models/piper/glados_piper_medium.onnx.json"
        )
        # Load Vosk model defensively — missing model should not crash the process.
        self.vosk_model = None
        try:
            vosk_path = os.path.expanduser("~/kloros_models/vosk/model")
            if os.path.exists(vosk_path):
                self.vosk_model = vosk.Model(vosk_path)
            else:
                print(f"[vosk] model path not found: {vosk_path}")
        except Exception as e:
            print("[vosk] model load failed:", e)

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

        self.wake_grammar = json.dumps(self.wake_phrases + ["[unk]"])
        # Create recognizers only if the model loaded successfully
        if self.vosk_model is not None:
            self.wake_rec = vosk.KaldiRecognizer(
                self.vosk_model, self.sample_rate, self.wake_grammar
            )
            self.vosk_rec = vosk.KaldiRecognizer(self.vosk_model, self.sample_rate)
        else:
            self.wake_rec = None
            self.vosk_rec = None

        # -------------------- VAD (more patient) -----------------
        self.vad = webrtcvad.Vad(1)  # less aggressive than 2
        self.frame_ms = 20  # 10/20/30 supported
        self.max_cmd_s = 12.0  # allow a bit longer
        self.silence_end_ms = 1400  # wait longer before stopping
        self.preroll_ms = 600  # include some audio before start
        self.start_timeout_ms = 3500  # time to begin speaking after wake
        self.min_cmd_ms = 900  # require ~0.9s of speech before ending

        # -------------------- State ---------------------
        self.audio_queue: "queue.Queue[bytes]" = queue.Queue(maxsize=64)
        self.listening = False
        self._heartbeat = 0
        self.conversation_history: List[str] = []
        self.json_logger: Optional[Any] = None

        # Keep BT sink awake to avoid first-sample drop
        self.keep_bluetooth_alive = True
        self._start_bluetooth_keepalive()

        self._load_memory()
        self._load_calibration_profile()
        self._init_json_logger()
        self._init_stt_backend()
        self._init_tts_backend()
        self._init_reasoning_backend()
        self._init_audio_backend()
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

    # ====================== Memory ======================
    def _load_memory(self) -> None:
        try:
            if os.path.exists(self.memory_file):
                with open(self.memory_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self.conversation_history = data.get("conversations", [])
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

    def _init_stt_backend(self) -> None:
        """Initialize STT backend if enabled."""
        if not self.enable_stt or create_stt_backend is None:
            return

        try:
            # Try to create the requested backend
            self.stt_backend = create_stt_backend(self.stt_backend_name)  # type: ignore
            print(f"[stt] Initialized {self.stt_backend_name} backend")
        except Exception as e:
            print(f"[stt] Failed to initialize {self.stt_backend_name} backend: {e}")

            # Fallback to mock backend if primary backend fails
            if self.stt_backend_name != "mock":
                try:
                    self.stt_backend = create_stt_backend("mock")  # type: ignore
                    print("[stt] Falling back to mock backend")
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
            self.reason_backend = create_reasoning_backend(self.reason_backend_name)  # type: ignore
            print(f"[reasoning] Initialized {self.reason_backend_name} backend")
        except Exception as e:
            print(f"[reasoning] Failed to initialize {self.reason_backend_name} backend: {e}")

            # Try fallback to mock if not already using mock
            if self.reason_backend_name != "mock":
                try:
                    self.reason_backend = create_reasoning_backend("mock")  # type: ignore
                    print("[reasoning] Falling back to mock backend")
                    self._log_event(
                        "reason_backend_fallback",
                        requested=self.reason_backend_name,
                        fallback="mock",
                        error=str(e),
                    )
                except Exception as fallback_e:
                    print(f"[reasoning] Fallback to mock backend also failed: {fallback_e}")
                    self.reason_backend = None

    def _init_audio_backend(self) -> None:
        """Initialize audio capture backend with fallback to mock."""
        if create_audio_backend is None:
            print("[audio] Audio capture module unavailable; using legacy audio")
            return

        try:
            self.audio_backend = create_audio_backend(self.audio_backend_name)  # type: ignore
            self.audio_backend.open(
                sample_rate=self.audio_sample_rate,
                channels=self.audio_channels,
                device=self.audio_device_index,
            )

            # Warmup period
            if self.audio_warmup_ms > 0:
                print(f"[audio] Warming up for {self.audio_warmup_ms}ms...")
                time.sleep(self.audio_warmup_ms / 1000.0)

            print(f"[audio] Initialized {self.audio_backend_name} backend")

        except Exception as e:
            print(f"[audio] Failed to initialize {self.audio_backend_name} backend: {e}")

            # Try fallback to mock if not already using mock
            if self.audio_backend_name != "mock":
                try:
                    self.audio_backend = create_audio_backend("mock")
                    self.audio_backend.open(
                        sample_rate=self.audio_sample_rate,
                        channels=self.audio_channels,
                        device=None,
                    )
                    print("[audio] Falling back to mock backend")
                    self._log_event(
                        "audio_backend_fallback",
                        requested=self.audio_backend_name,
                        fallback="mock",
                        error=str(e),
                    )
                except Exception as fallback_e:
                    print(f"[audio] Fallback to mock backend also failed: {fallback_e}")
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

    # ======================== LLM =======================
    def chat(self, user_message: str) -> str:
        self.conversation_history.append(f"User: {user_message}")
        context = (
            f"System: {self.system_prompt}\n\n"
            + "\n".join(self.conversation_history[-20:])
            + "\n\nAssistant:"
        )
        try:
            r = requests.post(
                self.ollama_url,
                json={"model": self.ollama_model, "prompt": context, "stream": False},
                timeout=60,
            )
            if r.status_code == 200:
                resp = r.json().get("response", "").strip()
            else:
                resp = f"Error: Ollama HTTP {r.status_code}"
        except requests.RequestException as e:
            resp = f"Ollama error: {e}"

        self.conversation_history.append(f"Assistant: {resp}")
        self._save_memory()
        return resp

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
    def _unsuspend_sink(self) -> None:
        """Politely nudge the default sink awake (PipeWire/Pulse)."""
        try:
            # Only run Pulse/PipeWire commands on Linux; dev machines (Windows) skip.
            if platform.system() == "Linux":
                subprocess.run(  # nosec B603, B607
                    ["pactl", "suspend-sink", "@DEFAULT_SINK@", "0"],
                    capture_output=True,
                    timeout=2,
                    check=False,
                )
        except Exception:
            pass  # nosec B110

    def _play_silence(self, seconds: float = 0.25) -> None:
        """Feed raw silence; helps keep BT link hot."""
        try:
            # aplay is Linux/ALSA-specific. Only attempt on Linux hosts.
            if platform.system() == "Linux":
                subprocess.run(  # nosec B603, B607
                    [
                        "aplay",
                        "-q",
                        "-t",
                        "raw",
                        "-f",
                        "S16_LE",
                        "-r",
                        str(self.sample_rate),
                        "-d",
                        str(seconds),
                        "/dev/zero",
                    ],
                    capture_output=True,
                    timeout=3,
                    check=False,
                )
        except Exception:
            pass  # nosec B110

    def _start_bluetooth_keepalive(self) -> None:
        def keepalive() -> None:
            while self.keep_bluetooth_alive:
                self._play_silence(0.12)  # tiny, inaudible tick
                time.sleep(5)  # frequent to avoid ramp-up delay

        threading.Thread(target=keepalive, daemon=True).start()

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
        Force 'KLoROS' to be pronounced /klɔr-oʊs/ by injecting eSpeak phonemes.
        eSpeak phoneme input uses [[ ... ]] with primary stress marked by ' .
        """
        return re.sub(r"\bkloros\b", "[[ 'klOroUs ]]", text, flags=re.IGNORECASE)

    def speak(self, text: str) -> None:
        """Synthesize and play speech via TTS backend."""
        # wake/unsuspend sink and run a longer primer before speaking
        self._unsuspend_sink()
        self._play_silence(0.35)
        time.sleep(0.20)

        text = self._normalize_tts_text(text)

        if not self.enable_tts or self.tts_backend is None:
            if self.fail_open_tts:
                print(f"[TTS] Backend unavailable; printing to console: {text}")
                return
            else:
                print("[TTS] Backend unavailable and fail_open disabled")
                return

        try:
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

            # Play audio on Linux hosts
            if platform.system() == "Linux":
                try:
                    subprocess.run(["aplay", result.audio_path], capture_output=True, check=False)  # nosec B603, B607
                except Exception as e:
                    print(f"[TTS] Audio playback failed: {e}")

        except Exception as e:
            print(f"[TTS] Synthesis failed: {e}")
            if self.fail_open_tts:
                print(f"[TTS] Falling back to console: {text}")
            else:
                print("[TTS] Fail_open disabled; no fallback")

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
                is_speech = self.vad.is_speech(frame, sr)
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
            buffer_duration_s = 1.5  # Accumulate ~1.5 seconds of audio before processing
            target_chunks = int(buffer_duration_s * 1000 / self.audio_block_ms)

            for chunk in self.audio_backend.chunks(self.audio_block_ms):
                if not self.listening:
                    break

                chunk_buffer.append(chunk)

                # When we have enough chunks, process as a turn
                if len(chunk_buffer) >= target_chunks:
                    # Combine chunks into single audio buffer
                    audio_buffer = np.concatenate(chunk_buffer)

                    # Only process if we have reasonable audio energy
                    rms = np.sqrt(np.mean(audio_buffer**2))
                    if rms > 0.001:  # Basic energy gate for float32 audio
                        try:
                            # Use the turn orchestrator if available
                            if run_turn is not None and self.stt_backend is not None:
                                # Create reasoning function
                                def reason_fn(transcript: str) -> str:
                                    if self.reason_backend:
                                        result = self.reason_backend.reply(transcript)
                                        return result.reply_text
                                    else:
                                        return self.chat(transcript)

                                # Get VAD threshold
                                vad_threshold = self._get_vad_threshold()

                                # Run the turn
                                turn_result = run_turn(
                                    audio=audio_buffer,
                                    sample_rate=self.audio_sample_rate,
                                    stt=self.stt_backend,
                                    reason_fn=reason_fn,
                                    tts=self.tts_backend,
                                    vad_threshold_dbfs=vad_threshold,
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

        try:
            with sd.RawInputStream(
                samplerate=self.sample_rate,
                blocksize=self.blocksize,
                device=self.input_device_index if self.input_device_index is not None else None,
                dtype="int16",
                channels=self.channels,
                callback=self.audio_callback,
            ):
                print("[audio] using device index:", self.input_device_index)
                while self.listening:
                    try:
                        data = self.audio_queue.get(timeout=1.0)
                    except queue.Empty:
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
                        if text:
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
                        if (
                            is_match
                            and avgc >= self.wake_conf_min
                            and (now_ms - self._last_wake_ms) > self.wake_cooldown_ms
                            and (now_ms - self._last_emit_ms) > self.wake_debounce_ms
                        ):
                            print("[WAKE] Detected wake phrase!")
                            log_event(
                                "wake_confirmed",
                                transcript=text,
                                matched_phrase=phrase,
                                fuzzy_score=score,
                                confidence=avgc,
                                rms=rms,
                            )
                            self._last_wake_ms = now_ms
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
                        p = json.loads(self.wake_rec.PartialResult()).get("partial", "")
                        if p:
                            print(f"\r[…] {p[:80]:<80}", end="", flush=True)
        except Exception as e:
            print("\n[audio] failed to open input stream:", e)
            print("Tip: set KLR_INPUT_IDX to a valid input device index.")

    def _create_reason_function(self):
        """Create a reasoning function for the turn orchestrator."""

        def reason_fn(transcript: str) -> str:
            """Generate response from transcript using reasoning backend or fallback."""
            if not transcript:
                return ""

            # Apply existing safety checks
            if self._command_is_risky(transcript):
                decision = protective_choice(
                    (
                        {"name": "llm_response", "risk": 0.6},
                        {"name": "safe_refusal", "risk": 0.1},
                    ),
                    {"id": self.operator_id, "command": transcript},
                )
                if decision.get("name") != "llm_response":
                    log_event("safe_redirect", reason="risky_command", command=transcript)
                    return "That request risks collateral. Choose the safer task I logged."

            # Use reasoning backend if available
            if self.reason_backend is not None:
                try:
                    result = self.reason_backend.reply(transcript)
                    # Store sources for later logging (the orchestrator will log them)
                    # We'll modify the orchestrator to handle this
                    self._last_reasoning_sources = getattr(result, "sources", [])
                    return result.reply_text
                except Exception as e:
                    log_event("reasoning_error", error=str(e))
                    # Fall through to legacy chat method

            # Fallback to existing chat method
            try:
                self._last_reasoning_sources = []  # No sources for legacy method
                return self.chat(transcript)
            except Exception as e:
                log_event("llm_error", error=str(e))
                return "I encountered an error processing your request."

        return reason_fn

    def handle_conversation(self) -> None:
        print("[DEBUG] Wake word detected, responding.")
        self._emit_persona("quip", {"line": "What fragile crisis now?"}, speak=True)
        log_event("conversation_start", user=self.operator_id)
        task = {"name": "voice_command", "kind": "interactive", "priority": "high"}
        if should_prioritize(self.operator_id, task):
            log_event("priority_bump", user=self.operator_id, task=task["name"])

        print("[DEBUG] Listening for command (VAD).")
        audio_bytes = self.record_until_silence()
        sample_count = len(audio_bytes) // 2
        log_event("audio_capture", samples=sample_count)
        print(f"[DEBUG] Collected {sample_count} samples")

        # Convert audio to float32 numpy array
        audio_array = np.frombuffer(audio_bytes, dtype=np.int16).astype(np.float32) / 32767.0

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
                        log_event(name, **payload)

                # Run orchestrated turn
                summary = run_turn(
                    audio_array,
                    self.sample_rate,
                    stt=self.stt_backend,
                    reason_fn=self._create_reason_function(),
                    tts=self.tts_backend if self.enable_tts else None,
                    vad_threshold_dbfs=self._get_vad_threshold(),
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
                    print(f"[TRANSCRIPT] {summary.transcript}")
                    print(f"KLoROS: {summary.reply_text}")

                    # Play audio if TTS was successful
                    if summary.tts and summary.tts.audio_path:
                        # Audio already synthesized by orchestrator
                        if platform.system() == "Linux":
                            try:
                                subprocess.run(  # nosec B603, B607
                                    ["aplay", summary.tts.audio_path],
                                    capture_output=True,
                                    check=False,
                                )
                            except Exception as e:
                                print(f"[TTS] Audio playback failed: {e}")
                    elif summary.reply_text:
                        # Fallback to speak method if no TTS result
                        self.speak(summary.reply_text)

                elif not summary.ok:
                    if summary.reason == "no_voice":
                        print("[DEBUG] No voice activity detected")
                        self._emit_persona("error", {"issue": "No command detected"}, speak=True)
                    elif summary.reason == "timeout":
                        print("[DEBUG] Turn timed out")
                        self._emit_persona("error", {"issue": "Request took too long"}, speak=True)
                    else:
                        print(f"[DEBUG] Turn failed: {summary.reason}")
                        self._emit_persona("error", {"issue": "Processing failed"}, speak=True)

            except Exception as e:
                print(f"[TURN] Orchestrator failed: {e}")
                log_event("turn_error", error=str(e))
                self._emit_persona("error", {"issue": "System error"}, speak=True)

        else:
            # Fallback to legacy logic when orchestrator unavailable
            print("[DEBUG] Using legacy conversation handling")
            # This maintains backward compatibility for cases where orchestrator is not available
            self._emit_persona("error", {"issue": "Voice processing unavailable"}, speak=True)

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
            self.keep_bluetooth_alive = False
            if self.audio_backend:
                self.audio_backend.close()
            self._log_event("shutdown", reason="loop_exit")
            self._emit_persona("quip", {"line": "Shutting down. Try not to miss me."})
            if self.json_logger:
                self.json_logger.close()


if __name__ == "__main__":
    kloros = KLoROS()
    kloros.run()
