# Git Sync Recovery Plan
**Created:** 2025-11-28
**Issue:** Nov 27 git sync disaster resurrected deleted code

## Summary

The git sync on Nov 27 at 18:00 overwrote local changes with remote state, resurrecting the old `kloros_voice` monolith that had been decomposed into the new architecture at `/src/core/interfaces/voice/`.

## Current State

### GOOD: Decomposed Architecture Intact
Location: `/home/kloros/src/core/interfaces/voice/`
- audio_io.py (410 lines)
- stt_service.py (467 lines)
- tts_service.py (391 lines)
- gateway.py (305 lines)
- voice_daemon.py (163 lines) - **NEW ENTRY POINT**
- Plus: emotion_service, intent_service, session_service, llm_service, etc.
- **Total: 4,956 lines (properly decomposed)**

Production code already uses this:
- `governance/persona/kloros.py` imports from decomposed architecture
- `voice_daemon.py` orchestrates all services

### BAD: Old Monolith Resurrected
Location: `/home/kloros/src/voice/kloros_voice*.py`
- kloros_voice.py (2,175 lines) - THE OLD MONOLITH
- kloros_voice_streaming.py (2,865 lines)
- kloros_voice_audio_io.py (384 lines)
- kloros_voice_emotion.py (345 lines)
- kloros_voice_intent.py (327 lines)
- kloros_voice_knowledge.py (419 lines)
- kloros_voice_llm.py (552 lines)
- kloros_voice_session.py (373 lines)
- kloros_voice_stt.py (330 lines)
- kloros_voice_tts.py (377 lines)
- **Total: 8,147 lines (DEAD CODE)**

Also resurrected:
- fuzzy_wakeword.py (dead, only test imports)

## Phase 1: Voice Monolith Purge

### Files to DELETE:
```
/home/kloros/src/voice/kloros_voice.py
/home/kloros/src/voice/kloros_voice_streaming.py
/home/kloros/src/voice/kloros_voice_audio_io.py
/home/kloros/src/voice/kloros_voice_emotion.py
/home/kloros/src/voice/kloros_voice_intent.py
/home/kloros/src/voice/kloros_voice_knowledge.py
/home/kloros/src/voice/kloros_voice_llm.py
/home/kloros/src/voice/kloros_voice_session.py
/home/kloros/src/voice/kloros_voice_stt.py
/home/kloros/src/voice/kloros_voice_tts.py
/home/kloros/src/voice/fuzzy_wakeword.py
/home/kloros/src/voice/tts_analysis.py
/home/kloros/src/voice/webrtcvad.py
/home/kloros/src/voice/_integration_guard.py
```

### Directories to KEEP:
```
/home/kloros/src/voice/stt/     (STT backends: VOSK, Whisper, hybrid)
/home/kloros/src/voice/tts/     (TTS backends: Piper, etc.)
/home/kloros/src/voice/audio/   (Audio processing)
/home/kloros/src/voice/style/   (Voice style)
```

## Phase 2: Test Import Updates

Files needing import updates:
1. `/home/kloros/src/tests/test_calibration.py`
2. `/home/kloros/src/tests/test_smoke.py`
3. `/home/kloros/src/tests/e2e_harness/ingress/http_text.py`
4. `/home/kloros/src/tests/comprehensive_test_suite.py`
5. `/home/kloros/src/tests/comprehensive_test_suite_v2.py`
6. `/home/kloros/src/tests/functional_test_suite.py`

Change from:
```python
from src.voice.kloros_voice import KLoROS
```
To:
```python
from src.core.interfaces.voice.voice_daemon import VoiceDaemon
```

## Estimated Effort

- **Phase 1**: 5 minutes (delete files)
- **Phase 2**: 30-60 minutes (update test imports)
- **Testing**: 1-2 hours

**NOT** 15 weeks. The decomposed architecture is already in place and working.

## Execution Commands

### Phase 1 - Delete monolith files:
```bash
rm -f /home/kloros/src/voice/kloros_voice.py \
      /home/kloros/src/voice/kloros_voice_streaming.py \
      /home/kloros/src/voice/kloros_voice_audio_io.py \
      /home/kloros/src/voice/kloros_voice_emotion.py \
      /home/kloros/src/voice/kloros_voice_intent.py \
      /home/kloros/src/voice/kloros_voice_knowledge.py \
      /home/kloros/src/voice/kloros_voice_llm.py \
      /home/kloros/src/voice/kloros_voice_session.py \
      /home/kloros/src/voice/kloros_voice_stt.py \
      /home/kloros/src/voice/kloros_voice_tts.py \
      /home/kloros/src/voice/fuzzy_wakeword.py \
      /home/kloros/src/voice/tts_analysis.py \
      /home/kloros/src/voice/webrtcvad.py \
      /home/kloros/src/voice/_integration_guard.py
```

### Verification:
```bash
# Should show only directories (stt/, tts/, audio/, style/) and __init__.py
ls /home/kloros/src/voice/
```
