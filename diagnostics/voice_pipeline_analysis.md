# Voice Pipeline Analysis
**Generated:** 2025-10-12 01:46:00
**Method:** Static analysis + configuration review

---

## Executive Summary

Voice pipeline architecture is sound but has integration issues with memory and tool systems.

---

## Pipeline Components

### 1. Audio Capture
- **Backend:** PulseAudio
- **Device:** alsa_input.usb-CMTECK_Co._Ltd._CMTECK_000000000000-00.mono-fallback
- **Sample Rate:** 48kHz capture
- **Input Gain:** 5.0x
- **Status:** ✅ Configured

### 2. Wake Word Detection
- **Phrases:** kloros, chorus, clothes
- **Confidence Threshold:** 0.65
- **RMS Threshold:** 180
- **Status:** ✅ Configured

### 3. STT (Speech-to-Text)
- **Backend:** Hybrid (Vosk + Whisper)
- **Models:**
  - Vosk: /home/kloros/models/vosk/model
  - Whisper: tiny, int8_float16
- **Status:** ✅ Configured
- **GPU:** CPU-only mode

### 4. TTS (Text-to-Speech)
- **Engine:** Piper
- **Voice:** GLaDOS medium
- **Sample Rate:** 22.05kHz
- **Status:** ✅ Configured

### 5. Memory Integration
- **Enabled:** Yes (KLR_ENABLE_MEMORY=1)
- **Max Context Events:** 6
- **Max Context Summaries:** 10
- **Status:** ⚠️ Broken (90% NULL conversation_ids)

---

## Critical Issues

### 1. Tool System Unavailable
- **Impact:** HIGH
- **Cause:** Missing sounddevice dependency
- **Effect:** Cannot execute system commands via voice

### 2. Memory Context Broken
- **Impact:** CRITICAL
- **Cause:** 90.2% NULL conversation_ids
- **Effect:** No context awareness across turns

### 3. RAG Latency
- **Impact:** MEDIUM
- **Cause:** Simple hash embedder (SentenceTransformer not available)
- **Effect:** 2900ms average latency (target: <1500ms)

---

## Configuration Issues

### Audio Configuration
- ✅ Sample rates properly configured
- ✅ TTS suppression enabled
- ✅ Input gain appropriate (5.0x)
- ⚠️ Device names hardcoded (fragile)

### Memory Configuration
- ✅ Memory enabled
- ⚠️ Max context events low (6) - should be 10-20
- ⚠️ Max context summaries high (10) - should be 3-5

### STT Configuration
- ✅ Hybrid backend for accuracy
- ⚠️ CPU-only mode (could be faster with GPU)
- ✅ VAD threshold appropriate

---

## Recommendations

1. **Install sounddevice** - Unblocks tool system
2. **Fix conversation_id assignment** - Restores context awareness
3. **Install sentence-transformers** - Improves RAG speed and quality
4. **Increase max context events** to 15-20
5. **Enable GPU for Whisper** if available

---

## Files Analyzed
- `/home/kloros/.kloros_env`
- `/home/kloros/src/kloros_voice.py` (identified)
- `/home/kloros/src/stt/*.py` (11 files identified)
