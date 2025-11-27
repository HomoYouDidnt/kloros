# Voice Services Refactor - November 25, 2025

## Overview

Major refactoring of the KLoROS voice system from a monolithic architecture to a service-based architecture with intelligent TTS routing.

## Summary of Changes

### 1. Service Decomposition

Decomposed `kloros_voice.py` (2167 lines) into 9 focused services:

| Service | File | Responsibility |
|---------|------|----------------|
| AudioIOService | `audio_io.py` | Audio capture, playback, calibration |
| STTService | `stt_service.py` | Speech-to-text (VOSK/Whisper hybrid) |
| TTSService | `tts_service.py` | Text-to-speech with SmartTTSRouter |
| EmotionService | `emotion_service.py` | Emotion detection from speech |
| IntentService | `intent_service.py` | Intent classification |
| KnowledgeService | `knowledge_service.py` | RAG/knowledge retrieval |
| LLMService | `llm_service.py` | LLM inference coordination |
| SessionService | `session_service.py` | Conversation state management |
| VoiceGateway | `gateway.py` | External API gateway |

Supporting modules:
- `half_duplex.py` - Anti-echo mic muting during playback
- `voice_daemon.py` - Unified daemon launcher for all services
- `base.py` - Base service class
- `streaming.py` - Streaming utilities

### 2. SmartTTSRouter Implementation

Added intelligent TTS routing with Supertonic integration:

**New Files in `src/tts/`:**
- `supertonic_backend.py` - Supertonic TTS backend (built-in text normalization)
- `smart_router.py` - SmartTTSRouter with automatic backend selection
- `text_analyzer.py` - TextComplexityAnalyzer for routing decisions
- `adapters/supertonic.py` - Streaming adapter for Supertonic

**Architecture:**
```
TTSService (backend="smart")
    │
    └── SmartTTSRouter
          ├── TextComplexityAnalyzer
          │     └── Detects: currency, numbers, dates, times,
          │         abbreviations, phone numbers, technical units
          │
          ├── Supertonic (warm) ← Text needs normalization
          │     └── $5.2M → "five point two million dollars"
          │
          └── Piper (warm) ← Clean prose (faster)
```

**Routing Logic:**
- Text with `$`, `%`, digits, dates, abbreviations → Supertonic
- Clean prose → Piper
- Fallback on failure → alternate backend

### 3. Terminology Standardization

Renamed all `*Zooid` classes to `*Service` for consistency:
- `AudioIOZooid` → `AudioIOService`
- `STTZooid` → `STTService`
- `TTSZooid` → `TTSService`
- `EmotionZooid` → `EmotionService`
- `IntentZooid` → `IntentService`
- `KnowledgeZooid` → `KnowledgeService`
- `LLMZooid` → `LLMService`
- `SessionZooid` → `SessionService`

Also updated `zooid_name` → `service_name` throughout.

### 4. Codebase Cleanup

**Deleted Orphaned Modules (src/audio/):**
- `endpoint_detector.py` (13KB)
- `separated_audio.py` (15KB)
- `vosk_http_mode.py` (11KB)
- `vosk_http_client.py` (5KB)
- `vosk_process.py` (17KB)
- `process_ipc.py` (8KB)
- `cues.py` (3KB)
- `silero_vad.py` (6KB) - duplicate of `vad_silero.py`

**Deleted Orphaned Directories:**
- `src/voice/` - `assert_voice_stack` never imported
- `src/ux/` - `AckBroker` never instantiated

**Deleted Orphaned Files:**
- `src/tools/tts_quality.py` - only referenced in docs
- `src/webrtcvad.py` - redundant shim

**Deleted 43 Backup Files** including:
- 5x `kloros_voice.py.*` variants
- Multiple `*.backup*`, `*.bak*`, `*.deprecated*` files
- Backup files in persona/, governance/, kloros/mind/, reasoning/, dream/, etc.

### 5. File Relocations

| From | To |
|------|-----|
| `src/tts_analysis.py` | `src/tts/analysis.py` |
| `kloros_voice.py` | Archived then deleted |

### 6. Import Fixes

- `housekeeping.py`: `from tts_analysis` → `from src.tts.analysis`
- `tts/curate_refs.py`: `import webrtcvad` → `from src.compat import webrtcvad`

### 7. Supertonic Setup

Cloned Supertonic TTS repository and assets:
```
/home/kloros/models/supertonic/
├── py/                    # Python SDK
├── assets/
│   ├── onnx/             # ONNX models (~260MB)
│   │   ├── duration_predictor.onnx
│   │   ├── text_encoder.onnx
│   │   ├── vector_estimator.onnx
│   │   └── vocoder.onnx
│   └── voice_styles/     # Voice presets
│       ├── F1.json, F2.json (female)
│       └── M1.json, M2.json (male)
```

## Final Directory Structure

### Voice Services (`kloros/interfaces/voice/`)
```
kloros/interfaces/voice/
├── __init__.py
├── audio_io.py          # AudioIOService
├── base.py              # Base service class
├── embedding_backend.py # Speaker embeddings
├── emotion_service.py   # EmotionService
├── enrollment_handler.py
├── enrollment.py
├── gateway.py           # VoiceGateway
├── half_duplex.py       # HalfDuplexController
├── intent_service.py    # IntentService
├── knowledge_service.py # KnowledgeService
├── llm_service.py       # LLMService
├── mock_backend.py
├── session_service.py   # SessionService
├── streaming.py
├── stt_service.py       # STTService
├── tts_service.py       # TTSService
└── voice_daemon.py      # Unified launcher
```

### TTS Backends (`src/tts/`)
```
src/tts/
├── adapters/
│   ├── __init__.py
│   ├── kokoro.py
│   ├── mimic3.py
│   ├── piper.py
│   ├── supertonic.py    # NEW
│   └── xtts_v2.py
├── __init__.py
├── analysis.py          # RELOCATED from root
├── base.py              # UPDATED with supertonic/smart
├── chunker.py
├── config.yaml
├── curate_refs.py
├── mock_backend.py
├── piper_backend.py
├── piper_stream.py
├── router.py
├── smart_router.py      # NEW
├── supertonic_backend.py # NEW
└── text_analyzer.py     # NEW
```

### Audio Utilities (`src/audio/`)
```
src/audio/
├── __init__.py
├── calibration.py       # Microphone calibration
├── capture.py           # PulseAudio capture
├── mic_mute.py          # Half-duplex mute control
├── vad.py               # VAD utilities
└── vad_silero.py        # Silero VAD implementation
```

## Environment Variables

### TTS Configuration
| Variable | Default | Description |
|----------|---------|-------------|
| `KLR_TTS_BACKEND` | `smart` | Backend: smart, supertonic, piper, mock |
| `KLR_TTS_PREWARM` | `1` | Pre-load backends on startup |
| `KLR_TTS_SAMPLE_RATE` | `22050` | Output sample rate |
| `KLR_TTS_OUT_DIR` | `~/.kloros/tts/out` | Output directory |
| `KLR_SUPERTONIC_VOICE` | `~/KLoROS/models/supertonic/assets/voice_styles/M1.json` | Voice style |
| `KLR_PIPER_VOICE` | `~/KLoROS/models/piper/glados_piper_medium.onnx` | Piper model |

### Service Toggles
| Variable | Default | Description |
|----------|---------|-------------|
| `KLR_ENABLE_STT` | `1` | Enable STT service |
| `KLR_ENABLE_TTS` | `1` | Enable TTS service |
| `KLR_VOICE_ENABLE_ANALYSIS` | `0` | Enable emotion/intent services |
| `KLR_VOICE_ENABLE_BACKEND` | `0` | Enable knowledge/LLM/session services |

## Next Steps

1. **Systemd Units** - Create service units for deployment
2. **UMN Signal Wiring** - Verify all services communicate correctly
3. **Integration Testing** - End-to-end voice pipeline tests
4. **Performance Profiling** - Measure latency improvements from SmartTTSRouter

## Migration Notes

- The deprecated `kloros_voice.py` has been removed
- All voice functionality now lives in `kloros/interfaces/voice/`
- TTS defaults to SmartTTSRouter with Piper + Supertonic warm pool
- Services are designed for independent operation via UMN pub/sub
