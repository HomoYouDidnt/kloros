# Directory Structure Analysis & Cleanup Plan
**Generated:** 2025-11-28
**Updated:** 2025-11-28 (All phases completed)
**Based on:** Episodic memory recovery from Nov 25-27 archived conversations

## Quick Status
- [x] Phase 1: Backup file cleanup (10 files removed)
- [x] Phase 2 partial: kloros_voice CRITICAL fixes (startup scripts, process detection)
- [x] Phase 3: Directory consolidation (41 → 12 directories)
- [ ] Phase 4 remaining: kloros_voice test/demo/doc refs (51 refs in 27 files)
- [ ] Phase 5: chem* → UMN rename (10 refs in 9 files)

## Directory Structure Restored

**Final structure (12 directories):**
```
src/
├── agents/           # 8 agent implementations
├── cognition/        # Brain, basal_ganglia, consciousness, learning, memory
├── core/             # Common, config, interfaces, runtime, middleware
├── governance/       # Guidance, persona, petri, policy
├── knowledge/        # MCP, RAG, scholar, wiki
├── observability/    # Diagnostics, introspection, metrics, self_heal
├── orchestration/    # Daemons, routing, spica, lifecycle
├── voice/            # Audio, STT, TTS, style
├── scripts/          # Utility scripts
├── tests/            # Test suites
├── tools/            # Toolforge, synthesis, curation
└── _archived/        # Historical code
```

**Consolidation performed:**
- core/: +common, +compat, +cache, +middleware, +utils, +shared, +integrations, +gpu_workers, +ingress, +ssot, +ux, +deployment/systemd
- governance/: +persona, +petri, +policy
- knowledge/: +mcp, +rag
- observability/: +diagnostics, +repairlab, +reporting
- orchestration/: +spica
- tools/: +tool_curation, +toolforge, +toolgen, +tool_synthesis
- cognition/: +evaluator, +memory, +uncertainty

## Current Architecture Status

### Voice Architecture (CORRECT - Layered Design)

The voice system correctly follows a layered architecture:

```
voice_daemon.py (orchestrator)
    └── Services Layer: /src/core/interfaces/voice/
        ├── stt_service.py      → uses → /src/voice/stt/*
        ├── tts_service.py      → uses → /src/voice/tts/*
        ├── audio_io.py         → uses → /src/voice/audio/*
        ├── emotion_service.py
        ├── intent_service.py
        ├── knowledge_service.py
        ├── llm_service.py
        ├── session_service.py
        └── gateway.py
```

**Backend Layer** (`/src/voice/`) - 52 Python files:
- `audio/` - Audio capture, VAD, calibration, mic control
- `stt/` - VOSK, Whisper, hybrid backends
- `tts/` - Piper, Supertonic, SmartTTSRouter
- `style/` - Voice style policies

**Service Layer** (`/src/core/interfaces/voice/`) - 19 Python files:
- Orchestration services that call the backends
- Entry point: `voice_daemon.py`

**This is NOT duplication** - it's proper separation of concerns.

## Completed Cleanup (Voice Monolith Purge)

The following files were deleted (8,147 lines removed):
```
✓ /src/voice/kloros_voice.py (2,175 lines) - DELETED
✓ /src/voice/kloros_voice_streaming.py (2,865 lines) - DELETED
✓ /src/voice/kloros_voice_audio_io.py (384 lines) - DELETED
✓ /src/voice/kloros_voice_emotion.py (345 lines) - DELETED
✓ /src/voice/kloros_voice_intent.py (327 lines) - DELETED
✓ /src/voice/kloros_voice_knowledge.py (419 lines) - DELETED
✓ /src/voice/kloros_voice_llm.py (552 lines) - DELETED
✓ /src/voice/kloros_voice_session.py (373 lines) - DELETED
✓ /src/voice/kloros_voice_stt.py (330 lines) - DELETED
✓ /src/voice/kloros_voice_tts.py (377 lines) - DELETED
✓ /src/voice/fuzzy_wakeword.py - DELETED
✓ /src/voice/tts_analysis.py - DELETED
✓ /src/voice/webrtcvad.py - DELETED
✓ /src/voice/_integration_guard.py - DELETED
```

## Pending Cleanup Tasks

### 1. Backup Files ✅ COMPLETED

~~These backup files can be safely removed:~~ **All 10 files removed:**
- ✅ kloros.py.backup-before-hallucination-fix
- ✅ kloros.py.backup-before-reasoning
- ✅ kloros.py.backup-pre-optimization
- ✅ resource_governor.py.backup_phase2_20251105_094538
- ✅ piper_backend.py.backup-pre-muting
- ✅ hybrid_backend.py.backup-before-phase4
- ✅ vosk_backend.py.backup-before-phase4
- ✅ dream_overnight.sh.backup-20251023
- ✅ standalone_chat.py.backup-before-memory-fix
- ✅ real_metrics.py.backup_hardcoded

### 2. kloros_voice String References (57 refs in 32 files)

#### CATEGORY A: BROKEN IMPORTS (Runtime Errors)
These files will crash when run because they import from deleted modules:

**CRITICAL - Will crash at runtime:**
- `/src/ingress/http_text.py:23` - `from src.kloros_voice import KLoROS`
  - OLD: `from src.kloros_voice import KLoROS`
  - NEW: Needs adapter class or rewrite to use gateway service

**Resolution:** Create `src/adapters/kloros_legacy.py` with a `KLoROS` class that wraps
the new voice services, OR rewrite http_text.py to use the gateway directly.

#### CATEGORY B: STARTUP SCRIPTS ✅ FIXED
~~These scripts try to run the deleted module:~~

- `/src/scripts/start_kloros.sh:42` - ✅ Updated to voice_daemon
- `/src/scripts/run_kloros_stable.sh:54` - ✅ Updated to voice_daemon
- `/src/scripts/start_kloros_35mm.sh:18` - ✅ Updated to voice_daemon

#### CATEGORY C: PROCESS DETECTION ✅ PARTIALLY FIXED
These files look for "kloros_voice" in process lists:

- `/src/observability/introspection/scanners/service_health_correlator.py:157` - ✅ Added voice_daemon
- `/src/observability/introspection/scanners/performance_profiler_scanner.py:149` - ✅ Added voice_daemon
- `/src/cognition/consciousness/interoception_daemon.py:258,270` - ✅ Added voice_daemon
- `/src/cognition/consciousness/meta_agent_daemon.py:1631` - still refs kloros_voice
- `/src/tests/test_rag_end_to_end.py:394` - test file, deferred
- `/src/tests/test_voice_rag_integration.py:142` - test file, deferred
- `/src/core/config/self_heal_playbooks.yaml:78` - ✅ Changed to voice_daemon
- `/src/cognition/awareness/capabilities.yaml:91` - ✅ Changed module path

#### CATEGORY D: TEST CODE (Tests will fail)
These tests reference the old module:

- `/src/tests/comprehensive_test_suite_v2.py` (11 refs) - tries to import kloros_voice
- `/src/tests/run_voice_tests.sh:66-68` - coverage targets deleted modules
- `/src/tests/test_reasoning_adapter.py:175-191` - references deleted logic
- `/src/agents/selfcoder/selfcoder.py:76` - tries to import kloros_voice
- `/src/tools/import_smoke.py:9` - includes deleted filename

**Resolution:** Update to test new architecture or remove stale tests

#### CATEGORY E: DOCUMENTATION/COMMENTS (No runtime impact)
These are safe but should be updated for accuracy:

**Historical references (can keep as documentation):**
- `/src/core/interfaces/voice/VOICE_SERVICES_REFACTOR_2025-11-25.md` (4 refs)

**Comments that reference old module:**
- `/src/tests/conftest.py:162` - comment about test mode guard
- `/src/tests/fixtures/voice_stubs.py:4` - "Extracted from kloros_voice.py"
- `/src/core/interfaces/voice/half_duplex.py:5` - "Extracted from kloros_voice.py"
- `/src/core/interfaces/voice/streaming.py:5` - "Salvaged from kloros_voice_streaming.py"
- `/src/tests/test_components.py:5` - path reference in comment

**Dead documentation files:**
- `/src/diagnostics/voice_pipeline_analysis.md:101`
- `/src/observability/diagnostics/voice_pipeline_analysis.md:101`
- `/src/scripts/validate_system.sh:145,179`

#### CATEGORY F: DEMO/EXAMPLE CODE (May fail)
These demo files reference old paths:

- `/src/scripts/demos/demo_c2c_unified.py:79`
- `/src/tools/demos/demo_c2c_unified.py:79`
- `/src/knowledge/wiki/demo_wiki_awareness.py:226`
- `/src/knowledge/wiki/test_wiki_resolver.py:82-248` (test fixtures)
- `/src/agents/c2c/claude_bridge.py:233,259`

#### CATEGORY G: PERSISTENCE FILENAME (Backwards compatible)
- `/src/core/interfaces/voice/session_service.py:54` - `kloros_voice_session.json`

**Resolution:** Keep for backwards compatibility with existing session files

### 3. chem* → UMN Rename (10 refs in 9 files)

The old "chem*" naming (chemistry-based pub/sub metaphor) should be renamed to UMN (Unus Mundus Network):

```
/src/orchestration/core/kloros_policy_engine.py
/src/orchestration/core/reflection_consumer_daemon.py
/src/toolforge/orchestrator.py
/src/orchestration/core/intent_router.py
/src/cognition/critic.py
/src/tests/test_chem_bus_poc.py (2 refs - rename file too)
/src/tests/test_failed_study_events_schema.py
/src/tool_synthesis/manifest_loader.py
/src/cognition/goals/__init__.py
```

## Preserved Components (From Nov 25 Work)

The following components from the Nov 25 voice decomposition are intact:

### SmartTTSRouter
- Location: `/src/voice/tts/smart_router.py`
- TextComplexityAnalyzer: `/src/voice/tts/text_analyzer.py`

### Supertonic TTS Backend
- Location: `/src/voice/tts/supertonic_backend.py`
- Adapter: `/src/voice/tts/adapters/supertonic.py`
- Models: `/home/kloros/models/supertonic/`

### VOSK/Whisper Hybrid STT
- Location: `/src/voice/stt/hybrid_backend.py`
- VOSK: `/src/voice/stt/vosk_backend.py`
- Whisper: `/src/voice/stt/whisper_backend.py`

## Execution Order

1. **Phase 1: Backup Cleanup** (5 min)
   - Remove 10 backup files
   - No code changes needed

2. **Phase 2: kloros_voice Refs** (30-60 min)
   - Update imports in test files
   - Update references in production code
   - Update scripts and documentation

3. **Phase 3: chem* → UMN** (15-30 min)
   - Rename references in 9 files
   - Rename test_chem_bus_poc.py → test_umn_bus_poc.py

4. **Phase 4: Verification** (30 min)
   - Run test suite
   - Verify voice daemon starts correctly
