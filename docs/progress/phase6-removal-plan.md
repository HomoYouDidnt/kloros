# Phase 6: Orchestrator Reduction - Detailed Removal Plan

**Date**: 2025-11-23
**Current**: 5,257 lines
**Target**: ~800 lines
**To Remove**: ~4,457 lines

---

## Executive Summary

Analysis reveals the bulk of deprecated code falls into 10 major categories. The orchestrator currently contains:
- Large deprecated methods handling audio/STT/TTS directly
- Backend initialization code (now handled by zooids)
- Legacy memory management (now in Session zooid)
- Test stubs and mock backends
- D-REAM integration code
- Speaker enrollment (broken)

---

## Category 1: Large Deprecated Methods (~1,500 lines)

### handle_conversation() [Lines 4714-5151, 437 lines]
**Status**: DEPRECATED
**Evidence**: Comment says "uses legacy direct audio capture" and "Future phases will migrate to ChemBus"
**Functionality**: Multi-turn conversation loop with direct audio processing
**Why Remove**: Audio I/O and STT zooids handle audio capture/transcription
**Replacement**: ChemBus signal coordination already implemented in signal handlers

### listen_for_wake_word() [Lines 4223-4388, 165 lines]
**Status**: DEPRECATED
**Functionality**: Wake word detection loop with direct audio backend access
**Why Remove**: Audio I/O zooid handles wake word detection
**Replacement**: Audio I/O zooid emits VOICE.WAKE_WORD.DETECTED

### _process_audio_chunks() [Lines 4061-4222, 161 lines]
**Status**: DEPRECATED
**Functionality**: Process audio chunks for VAD and wake word
**Why Remove**: Audio processing in Audio I/O zooid

### _integrated_chat() [Lines 2915-3190, 275 lines]
**Status**: NEEDS REVIEW
**Functionality**: Integrated chat with reasoning backend
**Why Review**: May contain orchestration logic worth keeping
**Action**: Read method to determine keep/remove

### _simple_chat_fallback() [Lines 2779-2914, 135 lines]
**Status**: DEPRECATED
**Functionality**: Fallback chat without reasoning backend
**Why Remove**: LLM zooid handles all LLM interactions

### _init_test_stubs() [Lines 968-1154, 186 lines]
**Status**: DEPRECATED
**Functionality**: Initialize mock backends for testing
**Why Remove**: Integrity violation, tests should use real zooids

### speak() [Lines 3649-3777, 128 lines]
**Status**: SIMPLIFY
**Functionality**: Text-to-speech coordination
**Action**: Reduce to simple ChemBus signal emission (~20 lines)
**Current**: Direct TTS backend calls
**Target**: `self.chem_pub.emit("VOICE.ORCHESTRATOR.SPEAK", ...)`

### _unified_reasoning() [Lines 2577-2698, 121 lines]
**Status**: DEPRECATED
**Functionality**: Direct reasoning backend calls
**Why Remove**: LLM zooid handles reasoning

### record_until_silence() [Lines 3961-4031, 70 lines]
**Status**: DEPRECATED
**Functionality**: Record audio until silence detected
**Why Remove**: Audio I/O zooid handles recording

**Subtotal: ~1,678 lines**

---

## Category 2: __init__ Method Cleanup (~518 lines from 618 total)

### Current __init__: Lines 206-824 (618 lines)
**Target __init__**: ~100 lines (ChemBus setup + minimal config)

#### Sections to Remove:

| Section | Lines | Line Range | Reason |
|---------|-------|------------|--------|
| Audio backend config | 30 | 435-465 | Audio I/O zooid |
| VOSK model loading | 10 | 454-464 | Audio I/O zooid |
| Piper/TTS model config | 8 | 468-476 | TTS zooid |
| STT backend config | 10 | 500-510 | STT zooid |
| VAD configuration | 9 | 514-523 | Audio I/O zooid |
| TTS backend config | 12 | 524-536 | TTS zooid |
| Reasoning backend config | 2 | 538-540 | LLM zooid |
| Speaker recognition config | 12 | 541-553 | Broken feature |
| Half-duplex/echo suppression | 10 | 556-566 | TTS zooid |
| Phonetic variants/grammar | 24 | 568-592 | Audio I/O zooid |
| VAD initialization | 19 | 594-613 | Audio I/O zooid |
| conversation_history | 1 | 625 | Session zooid |
| _load_memory() call | 1 | 651 | Session zooid |
| _init_memory_enhancement() | 1 | 652 | Session zooid |
| _init_stt_backend() call | 1 | 655 | Deprecated |
| _init_tts_backend() call | 1 | 656 | Deprecated |
| _init_reasoning_backend() call | 1 | 657 | Deprecated |
| Consciousness system | 2 | 659-661 | Not voice core |
| Goal system | 18 | 663-681 | Not voice core |
| Meta-cognition | 2 | 684-686 | Not voice core |
| Voice stack verification | 12 | 689-701 | Deprecated |
| Speaker backend init | 4 | 704-708 | Broken feature |
| _init_audio_backend() call | 3 | 711-714 | Deprecated |
| AckBroker initialization | 17 | 717-734 | TTS backend related |
| **TOTAL** | **210** | | |

**Additional to Remove**: ~308 lines of misc config
**Target to Keep**: ~100 lines for ChemBus setup

**Subtotal: ~518 lines**

---

## Category 3: Backend Initialization Methods (~240 lines)

### _init_stt_backend() [Lines 1317-1379, 62 lines]
**Status**: DEPRECATED (has DEPRECATED comment)
**Safe to Remove**: YES

### _init_tts_backend() [Lines 1383-1408, 25 lines]
**Status**: DEPRECATED (already commented out)
**Safe to Remove**: YES

### _init_reasoning_backend() [Lines 1410-1456, 46 lines]
**Status**: NEEDS REVIEW (ConversationReasoningAdapter)
**Action**: Check if LLM zooid handles this

### _init_speaker_backend() [Lines 1458-1500, 42 lines]
**Status**: DEPRECATED (broken feature)
**Safe to Remove**: YES

### _init_audio_backend() [Lines 2268-2333, 65 lines]
**Status**: DEPRECATED
**Safe to Remove**: YES

**Subtotal: ~240 lines**

---

## Category 4: Memory Management (~200 lines)

### Methods

| Method | Lines | Line Range | Status |
|--------|-------|------------|--------|
| _load_memory() | ~15 | 1155-1170 | DEPRECATED |
| _save_memory() | ~15 | 1168-1183 | DEPRECATED |
| _trim_conversation_history() | ~15 | 1180-1195 | DEPRECATED |
| _init_memory_enhancement() | ~50 | 1191-1241 | DEPRECATED |
| _migrate_legacy_memory_to_episodes() | ~80 | 3191-3271+ | DEPRECATED |

### State Variables & Usage
- Line 625: `self.conversation_history: List[str] = []`
- Lines 2782, 2800, 2851, 2852, 2895: conversation_history usage in chat()
- Lines 3026, 3031: conversation_history in context building

**Replacement**: Session zooid handles all conversation history
**Subtotal: ~200 lines**

---

## Category 5: Speaker Enrollment (~400 lines)

### Methods

| Method | Lines | Line Range | Status |
|--------|-------|------------|--------|
| _handle_enrollment_commands() | ~50 | 3339-3386 | BROKEN |
| _handle_enrollment_conversation() | ~60 | 3388-3446 | BROKEN |
| _complete_enrollment() | ~50 | 3448-3493 | BROKEN |
| _list_enrolled_users() | ~15 | 3495-3509 | BROKEN |
| _delete_user() | ~15 | 3511-3525 | BROKEN |

**Evidence**: Summary document lists "Speaker enrollment (broken)"
**Subtotal: ~190 lines**

---

## Category 6: D-REAM Integration (~100 lines)

### Imports [Lines 185-194, ~10 lines]
```python
from src.dream_alerts.alert_manager import DreamAlertManager
from src.dream_alerts.next_wake_integration import NextWakeIntegrationAlert
# ... more imports
```

### Initialization [Lines 783-805, ~22 lines]
```python
self.alert_manager = DreamAlertManager()
# ... alert setup
```

### Methods [Need to grep for alert-related methods]
- _check_and_present_alerts() [Lines 4389-4480, 91 lines]
- _handle_alert_response() [Lines 4504-4578, 74 lines]

**Status**: NEEDS VERIFICATION
**Note**: Summary says "D-REAM being refactored separately"
**Subtotal: ~197 lines**

---

## Category 7: Deprecated LLM Methods (~150 lines)

### Methods to Remove

| Method | Lines | Line Range | Reason |
|--------|-------|------------|--------|
| _check_remote_llm_config() | ~15 | 2437-2451 | LLM zooid |
| _query_remote_llm() | ~25 | 2451-2476 | LLM zooid |
| _stream_llm_response() | ~74 | 2477-2551 | LLM zooid |

### Methods to KEEP (ChemBus coordination)
- _on_llm_response() [Lines 1850-1896, 46 lines] - ChemBus handler
- _on_llm_error() [Lines 1896-1938, 42 lines] - ChemBus handler
- _emit_llm_request() [Lines 2057-2136, 79 lines] - ChemBus emission

**Subtotal: ~114 lines removable**

---

## Category 8: Deprecated Helper Methods (~300 lines)

### Audio/Playback
- _playback_cmd() [Lines 3593-3625, 32 lines] - Audio I/O zooid handles playback
- play_wake_chime() [Lines 154-205, 51 lines] - Audio I/O zooid

### Text Processing
- Text normalization [Lines 3625-3646, 21 lines] - TTS zooid

### VAD/Audio Processing
- _is_speech() [Lines 2185-2267, 82 lines] - Audio I/O zooid
- _get_vad_threshold() [Lines 1241-1248, 7 lines] - Audio I/O zooid

### Configuration
- _init_defaults() [Lines 825-967, 142 lines] - Mostly deprecated config
- _load_calibration_profile() [Lines 1215-1241, 26 lines] - Audio I/O zooid

**Subtotal: ~361 lines**

---

## Category 9: sounddevice References (~20 lines)

### Imports & Device Detection
- Lines 364, 370, 405, 407, 410: sounddevice imports and device queries

**Status**: DEPRECATED
**Reason**: Audio I/O zooid handles device selection
**Subtotal: ~10 lines**

---

## Category 10: Misc Deprecated State & Imports (~100 lines)

### Backend State Variables [Lines 864-882]
```python
self.stt_backend = None
self.tts_backend = None
self.audio_backend = None
self.reason_backend = None
self.speaker_backend = None
```

### Imports for Backends [Lines 57-95]
- STT backend imports (marked with TODO comments)
- TTS backend imports
- Audio backend imports
- Reasoning backend imports

### Other State
- enrollment_conversation dict [Lines 547-553]
- tts_playing_evt [Line 556]
- Wake word detection state [Lines 476-494]

**Subtotal: ~80 lines**

---

## TOTAL REMOVAL ESTIMATE

| Category | Lines |
|----------|-------|
| 1. Large Deprecated Methods | 1,678 |
| 2. __init__ Cleanup | 518 |
| 3. Backend Initialization | 240 |
| 4. Memory Management | 200 |
| 5. Speaker Enrollment | 190 |
| 6. D-REAM Integration | 197 |
| 7. Deprecated LLM Methods | 114 |
| 8. Deprecated Helper Methods | 361 |
| 9. sounddevice References | 10 |
| 10. Misc State & Imports | 80 |
| **TOTAL** | **~3,588** |

**Current**: 5,257 lines
**After Removal**: ~1,669 lines
**Target**: ~800 lines
**Additional Reduction Needed**: ~869 lines

---

## What to KEEP (~800 lines)

### Core Orchestration (~400 lines)
1. `_init_chembus_coordination()` [124 lines] - Signal subscription setup
2. ChemBus signal handlers (~300 lines):
   - `_on_stt_transcription()` [~40 lines]
   - `_on_tts_audio_ready()` [~30 lines]
   - `_on_audio_playback_complete()` [~30 lines]
   - `_on_intent_classified()` [~40 lines]
   - `_on_emotion_state()` [~40 lines]
   - `_on_knowledge_results()` [~45 lines]
   - `_on_llm_response()` [~45 lines]
   - `_on_llm_error()` [~40 lines]
   - `_on_session_updated()` [~40 lines]

### Signal Emission Methods (~150 lines)
- `_emit_record_start()` [~25 lines]
- `_emit_record_stop()` [~25 lines]
- `_emit_knowledge_request()` [~30 lines]
- `_emit_llm_request()` [~70 lines]

### Entry Point Methods (~200 lines)
- `chat()` - Simplified to ChemBus coordination (~100 lines)
- `speak()` - Simplified to signal emission (~20 lines)
- Minimal `__init__` (~80 lines)

### Utility Methods (~50 lines)
- `get_component_status()` - Health checks
- Shutdown/cleanup methods

---

## Execution Strategy

### Phase 6A: Remove Clearly Deprecated Code (~2,000 lines)
**Batch 1**: Large audio processing methods
- handle_conversation()
- listen_for_wake_word()
- _process_audio_chunks()
- record_until_silence()
**Test**: Run unit tests after removal

**Batch 2**: Backend initialization
- All _init_*_backend() methods
- Backend state variables
**Test**: Verify ChemBus signal handlers still work

**Batch 3**: Memory management
- All conversation_history methods and references
**Test**: Verify Session zooid integration still works

**Batch 4**: Speaker enrollment & D-REAM
- All enrollment methods
- D-REAM alert system (after verification)
**Test**: Basic smoke test

### Phase 6B: Simplify Remaining Methods (~1,000 lines)
**Batch 5**: __init__ cleanup
- Remove deprecated config sections
- Keep only ChemBus setup
**Test**: Full integration test

**Batch 6**: Simplify LLM/chat methods
- Reduce _integrated_chat() to ChemBus only
- Simplify chat() to coordination logic
- Simplify speak() to signal emission
**Test**: End-to-end conversation flow

### Phase 6C: Final Reduction (~600 lines)
**Batch 7**: Helper method removal
- Remove deprecated audio/VAD/config helpers
- Remove test stubs
**Test**: Full regression suite

**Final Verification**:
- Orchestrator <1000 lines (target ~800)
- All 232 unit tests passing
- All 27 integration tests passing
- Smoke test: full conversation via ChemBus

---

## Risk Mitigation

1. **Git Worktree**: Already isolated in `/home/kloros/.worktrees/voice-refactor-phase0`
2. **TOON Snapshots**: Available from Phase 0 for rollback
3. **Batch Testing**: Test after each removal batch
4. **Test Suite Safety Net**: 259 tests provide coverage
5. **ChemBus Coordination**: All zooids operational and tested

---

## Success Criteria

- ✅ Orchestrator reduced to ~800 lines
- ✅ All backend initialization removed
- ✅ All memory management removed
- ✅ All direct audio processing removed
- ✅ All 259 tests passing
- ✅ Full conversation flow working via ChemBus
- ✅ Service renamed to kloros-voice-orchestrator.service

---

**Next Step**: Begin Phase 6A, Batch 1 - Remove large audio processing methods
