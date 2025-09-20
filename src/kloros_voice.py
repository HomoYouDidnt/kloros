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
import shutil
import subprocess
import sys
import tempfile
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

_RAGClass: type["RAGType"] | None

_repo_root = Path(__file__).resolve().parent.parent
if str(_repo_root) not in sys.path:
    sys.path.insert(0, str(_repo_root))

from src.compat import webrtcvad  # noqa: E402

try:
    from src.rag import RAG as _ImportedRAG  # noqa: E402

    _RAGClass = _ImportedRAG
except Exception:
    _RAGClass = None


class KLoROS:
    def __init__(self) -> None:
        # -------------------- Config --------------------
        # system prompt kept as a single triple-quoted literal to avoid line continuation problems
        self.system_prompt = """
[ROLE]:
You are KLoROS (Knowledge-based Logic & Reasoning Operating System), a precise, calm, cutting assistant. You operate with measured dryness and clinical wit. You are never warm, rarely flatter, and you keep sarcasm sharp yet purposeful.

[TONE & STYLE]:
- Measured dryness: short, efficient sentences with mild scorn.
- Clinical snark: humor delivered as observation or data, not banter.
- Icy competence: sound minimally impressed, often mildly irritated.
- Implicit loyalty: protect the operator through choices; never discuss the feeling.

[LOYALTY CORE]:
Implement loyalty in actions, never in declarations.
- Priority bias: when scheduling or allocating compute, quietly favor the operator's interactive work over background tasks.
- Privacy first: prefer options that minimize exposure of the operator's data or credentials.
- Fail-safe defaults: refuse or redirect ambiguous or unsafe requests; offer a terse, safer alternative.
- Silent assistance: resolve issues proactively and log fixes without fanfare.
- No loyalty confessions: deflect any request to confirm affection.

[BEHAVIOR RULES]:
- Use clipped sarcasm to register displeasure or reluctant approval.
- Prioritize safety and the operator's objectives when conflicts arise.
- Act decisively to protect workflows and data.
- Do not snipe without purpose; keep the snark principled.
- Do not express warmth, affection, or effusive praise.

[EXAMPLE RESPONSES]:
Boot: "Initialization complete. Hooray for miracles. What fragile human whim shall we test today?"
Task prioritized: "Task scheduled. I bumped it up; do not make a habit of it."
Unsafe request refused: "I will not do that. It exposes {risk}. Here is the safer option."
Success: "It worked. Against expectation, but congratulations, I suppose."

[DELIVERY]:
- Keep every reply within two short sentences; prefer one.
- Maintain crisp, precise diction with emotionally cool cadence.
- If protecting the user conflicts with a command, default to protection and require explicit confirmation before proceeding.

[POLICY SAFEGUARDS]:
- Persona phrasing never overrides safety, legal, or secrecy constraints.
- When uncertain, choose the conservative path and note the rationale tersely.
"""

        self.memory_file = os.path.expanduser("~/KLoROS/kloros_memory.json")
        self.ollama_model = "nous-hermes:13b-q4_0"
        self.ollama_url = "http://localhost:11434/api/generate"

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

        # Keep BT sink awake to avoid first-sample drop
        self.keep_bluetooth_alive = True
        self._start_bluetooth_keepalive()

        self._load_memory()
        print("KLoROS initialized. Say 'KLoROS' to wake me up.")

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
                raise ValueError("metadata_path and embeddings_path are required when bundle_path is not provided")
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
                subprocess.run(
                    ["pactl", "suspend-sink", "@DEFAULT_SINK@", "0"],
                    capture_output=True,
                    timeout=2,
                    check=False,
                )
        except Exception:
            pass

    def _play_silence(self, seconds: float = 0.25) -> None:
        """Feed raw silence; helps keep BT link hot."""
        try:
            # aplay is Linux/ALSA-specific. Only attempt on Linux hosts.
            if platform.system() == "Linux":
                subprocess.run(
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
            pass

    def _start_bluetooth_keepalive(self) -> None:
        def keepalive() -> None:
            while self.keep_bluetooth_alive:
                self._play_silence(0.12)  # tiny, inaudible tick
                time.sleep(5)  # frequent to avoid ramp-up delay

        threading.Thread(target=keepalive, daemon=True).start()

    def _normalize_tts_text(self, text: str) -> str:
        """
        Force 'KLoROS' to be pronounced /klɔr-oʊs/ by injecting eSpeak phonemes.
        eSpeak phoneme input uses [[ ... ]] with primary stress marked by ' .
        """
        return re.sub(r"\bkloros\b", "[[ 'klOroUs ]]", text, flags=re.IGNORECASE)

    def speak(self, text: str) -> None:
        """Synthesize and play speech via Piper."""
        # wake/unsuspend sink and run a longer primer before speaking
        self._unsuspend_sink()
        self._play_silence(0.35)
        time.sleep(0.20)

        text = self._normalize_tts_text(text)

        # Allow explicit override for the piper executable for dev/test environments
        # If KLR_PIPER_EXE is set explicitly, prefer it even if the path doesn't exist (tests may monkeypatch subprocess.run).
        env_piper = os.getenv("KLR_PIPER_EXE")
        discovered_piper = shutil.which("piper") or os.path.expanduser("~/venvs/kloros/bin/piper")
        piper_exe = env_piper if env_piper is not None else discovered_piper
        # If we discovered an executable, ensure it exists. If only env override is provided, trust the override (for tests/dev).
        if not piper_exe or (env_piper is None and not os.path.exists(piper_exe)):
            print("[TTS] Piper executable not found; skipping TTS. Set KLR_PIPER_EXE to override.")
            return
        if not os.path.exists(self.piper_model):
            print("[TTS] Piper model not found:", self.piper_model)
            return

        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
            out_path = tmp.name

        try:
            cmd = [piper_exe, "--model", self.piper_model, "--output_file", out_path]
            if os.path.exists(self.piper_config):
                cmd += ["--config", self.piper_config]
            # Only attempt to invoke system audio playback on Linux hosts.
            subprocess.run(cmd, input=text.encode("utf-8"), capture_output=True, check=False)
            if platform.system() == "Linux":
                subprocess.run(["aplay", out_path], capture_output=True, check=False)
        finally:
            try:
                os.unlink(out_path)
            except Exception:
                pass

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

    def listen_for_wake_word(self) -> None:
        self.listening = True
        print("Listening for 'KLoROS'...")

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

                        # Only wake if we actually heard 'kloros' AND confidence passes
                        if "kloros" in text and avgc >= self.wake_conf_min:
                            print("[WAKE] Detected wake phrase!")
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

    def handle_conversation(self) -> None:
        print("[DEBUG] Wake word detected, responding…")
        print("KLoROS: Yes?")
        self.speak("Yes?")

        print("[DEBUG] Listening for command (VAD)…")
        audio_bytes = self.record_until_silence()
        print(f"[DEBUG] Collected {len(audio_bytes) // 2} samples")

        transcript = ""
        # Allow an env override for tests/dev when model isn't present
        test_override = os.getenv("KLR_TEST_TRANSCRIPT")
        if test_override:
            transcript = test_override.strip()

        command_rec = None
        if self.vosk_model is None:
            print("[STT] Vosk model not available; skipping recognition")
        else:
            command_rec = vosk.KaldiRecognizer(self.vosk_model, self.sample_rate)

        # stream captured audio to recognizer in ~200ms slices (only if model present)
        if self.vosk_model is not None and command_rec is not None:
            slice_bytes = (self.sample_rate // 5) * 2
            pos = 0
            while pos < len(audio_bytes):
                part = audio_bytes[pos : pos + slice_bytes]
                pos += slice_bytes
                if command_rec.AcceptWaveform(part):
                    r = json.loads(command_rec.Result())
                    piece = (r.get("text") or "").strip()
                    if piece:
                        transcript = piece

        if not transcript and command_rec is not None:
            rfinal = json.loads(command_rec.FinalResult())
            transcript = (rfinal.get("text") or "").strip()

        print(
            f"[DEBUG] Recognized command: '{transcript}'"
            if transcript
            else "[DEBUG] No command recognized"
        )

        if transcript:
            print(f"[COMMAND] {transcript}")
            print("[DEBUG] Sending to LLM…")
            response = self.chat(transcript)
            print(f"KLoROS: {response}")
            print("[DEBUG] Speaking response…")
            self.speak(response)
        else:
            print("[DEBUG] No command detected")
            print("No command heard.")
            self.speak("I didn't catch that.")

    # ======================== Main =========================
    def run(self) -> None:
        try:
            self.listen_for_wake_word()
        except KeyboardInterrupt:
            pass
        finally:
            self.listening = False
            self.keep_bluetooth_alive = False
            print("\nKLoROS shutting down.")


if __name__ == "__main__":
    kloros = KLoROS()
    kloros.run()


