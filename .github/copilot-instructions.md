<!--
Guidance for AI coding agents working on the KLoROS repository.
Keep this short (20–50 lines). Reference concrete files and observable patterns.
-->
# KLoROS — Copilot instructions (concise)

This file gives focused, actionable context for AI agents editing or extending the KLoROS voice assistant.

- Big picture: single-process local voice assistant combining offline STT (Vosk), TTS (Piper), and a local LLM HTTP endpoint (Ollama).
  - Entry point: `src/kloros_voice.py` (class `KLoROS`). The run loop listens for a wake word, records with VAD, sends text to Ollama, and synthesizes with Piper.
  - Models and runtime files are expected under `~/kloros_models/` (vosk model at `~/kloros_models/vosk/model`, Piper model at `~/kloros_models/piper/*.onnx`). `src/test_components.py` shows example test invocations.

- Key workflows and commands (discoverable from code):
  - Python deps are in `requirements.txt`. Use the same Python interpreter (venv recommended) that provides `sounddevice`, `vosk`, `webrtcvad`, and `requests`.
  - LLM endpoint: Ollama is called at `http://localhost:11434/api/generate`. Ensure Ollama is running and `nous-hermes:13b-q4_0` (or configured model) is available before integration tests.
  - TTS: `piper` CLI is invoked by `KLoROS.speak()`; verify `piper` is on PATH or at `~/venvs/kloros/bin/piper`.

- Project-specific patterns and conventions:
  - Environment overrides: many runtime values come from env vars (e.g., `KLR_INPUT_IDX`, `KLR_WAKE_PHRASES`, `KLR_WAKE_CONF_MIN`, `KLR_INPUT_GAIN`). Prefer non-invasive changes by respecting env overrides.
  - Device discovery: audio device selection attempts to auto-pick a device containing "CMTECK"; tests should avoid hard-coding device indexes.
  - Audio units: code uses raw int16 mono PCM at the detected `sample_rate` (fallback 48000). Frame sizes and blocksize derive from sample rate. When adding audio logic, keep int16 and the existing normalization code paths.
  - Wake grammar: a tight wakephrases grammar is used via Vosk (see `self.wake_grammar`). Avoid loosening by default; add variants via `KLR_WAKE_PHRASES` env.
  - Memory: simple JSON memory file at `~/KLoROS/kloros_memory.json` (see `configs/kloros_memory.json` example). Edits to memory should preserve existing JSON shape: {"conversations": [...], "last_updated": ...}.

- Integration points to check when changing behavior:
  - Vosk usage: `vosk.Model` initialization and `KaldiRecognizer` calls in `src/kloros_voice.py` (wake vs free recognizers). Recreating recognizers is done after each interaction.
  - VAD: `webrtcvad.Vad(1)` with 20ms frames. When changing timings, update `frame_ms`, `silence_end_ms`, `preroll_ms`, and related logic in `record_until_silence()` consistently.
  - LLM calls: `KLoROS.chat()` posts to `self.ollama_url` with `model`, `prompt`, and `stream: False`. Expect a JSON response with key `response`.
  - TTS calls: `piper` is executed as a subprocess; audio is written to a temp WAV and played with `aplay`.

- Safety for edits and tests:
  - Many runtime behaviors rely on host tools (pactl/aplay/piper/ollama). Use `src/test_components.py` as a lightweight smoke test that exercises integrations; for CI or offline tests, mock subprocess calls and network requests.
  - Do not assume a Linux-only environment in code edits; the repository is developed for Linux audio stacks (Pulse/ALSA). If adding Windows-specific branches, gate them clearly.

- Helpful code examples (copyable intent):
  - Restart recognizers after a conversation: recreate `vosk.KaldiRecognizer(self.vosk_model, self.sample_rate)` and the wake grammar recognizer.
  - Normalize text for TTS: call `_normalize_tts_text()` before `piper` to preserve pronunciation rules (example: 'KLoROS' phoneme injection).

- When changing defaults, update these files/places: `src/kloros_voice.py` (init thresholds & env usage), `configs/kloros_memory.json` (memory shape example), and `src/test_components.py` (integration smoke tests).

If any section is unclear or you need more examples (e.g., how tests are expected to mock audio devices or Ollama responses), say which area and I will expand with precise code snippets or test stubs.
