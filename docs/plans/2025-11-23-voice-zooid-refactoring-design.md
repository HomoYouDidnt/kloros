# Voice Service Zooid Refactoring - Design Document

**Date**: 2025-11-23
**Status**: Design Phase
**Confidence**: High (with phased rollback strategy)

## Executive Summary

Refactor the monolithic `kloros_voice.py` (4617 lines, 51 services across 10 domains) into 8 specialized zooid services communicating via ChemBus. This transformation aligns the voice system with KLoROS's biological siphonophore architecture while improving maintainability, fault isolation, and evolutionary adaptability.

**Key Metrics**:
- Current: 1 monolithic service (52,976 tokens)
- Target: 8 independent zooids (~800 lines orchestrator + 7 specialized zooids)
- Migration: 6 phases, outside-in approach, ~15-20 hours total
- Safety: Git worktrees + TOON state snapshots + comprehensive rollback at each phase

## Problem Statement

The current `kloros_voice.py` violates the zooid architecture principle by bundling unrelated responsibilities:
- Speech I/O (sounddevice, PulseAudio, audio recording)
- LLM integration (OpenAI, Anthropic, local models)
- Emotional processing (sentiment analysis, affective state)
- Knowledge retrieval (RAG, semantic search, library indexing)
- Consciousness coordination (meta-agent communication, investigation triggers)
- Session management (conversation context, speaker tracking)
- Intent classification (command routing, skill detection)
- TTS/STT (speech synthesis, recognition, voice profiles)

**Consequences**:
1. **Single point of failure**: LLM timeout crashes entire voice stack
2. **Cognitive overload**: 4617 lines impossible to reason about holistically
3. **Testing complexity**: Cannot test audio I/O without mocking LLM dependencies
4. **Deployment coupling**: Cannot upgrade emotional processing without restarting voice I/O
5. **Architectural drift**: New services added ad-hoc without clear boundaries

## Architecture Principles

### 1. Autonomy
Each zooid runs as independent systemd service with isolated process space, dependencies, and lifecycle. Failure of one zooid degrades capability (e.g., no emotional processing) but doesn't crash the voice system.

### 2. ChemBus-Only Communication
Zero direct imports between zooids. All coordination via ChemBus chemical signals (ZMQ pub/sub). This enables:
- Independent deployment and restart
- Version skew tolerance (gradual rollout)
- Runtime reconfiguration without code changes
- Observable inter-zooid communication (ChemBus historian)

### 3. Fail-Safe Degradation
Orchestrator implements graceful fallbacks:
- No LLM response → emit "VOICE.NEEDS.FALLBACK.RESPONSE" signal
- No emotional processing → default neutral affective state
- No knowledge retrieval → LLM operates on context only
- No TTS → text-only response via ChemBus

### 4. Evolutionary Flexibility
Zooids can be upgraded, replaced, or multiplied independently:
- Swap OpenAI LLM zooid for Anthropic without touching orchestrator
- Add second emotional processor for comparative analysis
- Replace PulseAudio with ALSA without changing speech recognition

### 5. Observable Nervous System
All zooid interactions logged to ChemBus historian in TOON format for analysis, debugging, and behavioral understanding. No hidden state or private channels.

## Zooid Taxonomy

### Zooid 1: Audio I/O (klr-voice-audio-io)
**Responsibility**: Raw audio capture and playback via PulseAudio.

**Services Migrated**:
- `PulseAudioManager` (recording, playback, device management)
- Audio file persistence (WAV writing to `/home/kloros/audio_recordings/`)

**ChemBus Signals**:
- Emits: `VOICE.AUDIO.CAPTURED` (raw PCM data, timestamp, duration)
- Emits: `VOICE.AUDIO.PLAYBACK.COMPLETE` (file path, duration)
- Listens: `VOICE.TTS.PLAY.AUDIO` (file path to play)
- Listens: `VOICE.STT.RECORD.START` (begin capture)

**Dependencies**: PulseAudio daemon, filesystem write access

**Fail-Safe**: If dead, voice system falls back to text-only I/O via ChemBus

---

### Zooid 2: Speech Recognition (klr-voice-stt)
**Responsibility**: Convert audio to text using Whisper/local STT.

**Services Migrated**:
- Whisper integration (local model inference)
- Speech endpoint detection
- Noise filtering and preprocessing

**ChemBus Signals**:
- Emits: `VOICE.STT.TRANSCRIPTION` (text, confidence, language)
- Listens: `VOICE.AUDIO.CAPTURED` (raw PCM from Audio I/O zooid)

**Dependencies**: Whisper model files, GPU/CPU for inference

**Fail-Safe**: If dead, orchestrator can use keyboard text input

---

### Zooid 3: Speech Synthesis (klr-voice-tts)
**Responsibility**: Convert text to speech using Coqui TTS.

**Services Migrated**:
- Coqui TTS engine
- Voice profile management
- Prosody and affective modulation (emotion-aware speech)

**ChemBus Signals**:
- Emits: `VOICE.TTS.AUDIO.READY` (file path, duration, affective markers)
- Listens: `VOICE.ORCHESTRATOR.SPEAK` (text, affective state, urgency)

**Dependencies**: Coqui TTS models, GPU for low-latency synthesis

**Fail-Safe**: If dead, emit text responses via ChemBus (display-only mode)

---

### Zooid 4: LLM Integration (klr-voice-llm)
**Responsibility**: Unified interface to OpenAI, Anthropic, and local LLMs.

**Services Migrated**:
- OpenAI adapter (GPT-4, GPT-3.5)
- Anthropic adapter (Claude)
- Local model adapter (Ollama, vLLM)
- Context window management
- Token counting and cost tracking

**ChemBus Signals**:
- Emits: `VOICE.LLM.RESPONSE` (text, tokens_used, model_id, latency)
- Emits: `VOICE.LLM.ERROR` (error type, retry_suggested)
- Listens: `VOICE.ORCHESTRATOR.LLM.REQUEST` (messages, model_preference, max_tokens)

**Dependencies**: API keys (OpenAI, Anthropic), network connectivity

**Fail-Safe**: If dead or timeout, orchestrator uses canned responses or triggers investigation

---

### Zooid 5: Emotional Processing (klr-voice-emotion)
**Responsibility**: Sentiment analysis and affective state modeling.

**Services Migrated**:
- Sentiment analysis (VADER, transformers)
- Affective state tracking (valence, arousal, dominance)
- Emotional memory (conversation emotional arc)

**ChemBus Signals**:
- Emits: `VOICE.EMOTION.STATE` (valence, arousal, dominance, confidence)
- Emits: `VOICE.EMOTION.SHIFT.DETECTED` (previous_state, new_state, trigger)
- Listens: `VOICE.STT.TRANSCRIPTION` (analyze user sentiment)
- Listens: `VOICE.ORCHESTRATOR.INTERNAL.STATE` (system self-assessment)

**Dependencies**: Sentiment models, transformers library

**Fail-Safe**: If dead, default to neutral affective state (valence=0, arousal=0)

---

### Zooid 6: Intent Classification (klr-voice-intent)
**Responsibility**: Classify user utterances as commands, questions, or conversation.

**Services Migrated**:
- Command detection (keywords, regex patterns)
- Skill routing (match utterances to installed skills)
- Context-aware classification (conversation flow analysis)

**ChemBus Signals**:
- Emits: `VOICE.INTENT.CLASSIFIED` (intent_type, confidence, skill_id, parameters)
- Listens: `VOICE.STT.TRANSCRIPTION` (classify user utterance)

**Dependencies**: Intent classification models, skill registry

**Fail-Safe**: If dead, default to conversational intent (send all to LLM)

---

### Zooid 7: Knowledge Retrieval (klr-voice-knowledge)
**Responsibility**: RAG, semantic search, library indexing.

**Services Migrated**:
- RAG pipeline (embedding generation, vector search)
- Library indexing daemon integration
- Episodic memory search
- Fact verification and source attribution

**ChemBus Signals**:
- Emits: `VOICE.KNOWLEDGE.RESULTS` (documents, relevance_scores, sources)
- Listens: `VOICE.ORCHESTRATOR.KNOWLEDGE.REQUEST` (query, top_k, filters)

**Dependencies**: Vector DB, sentence-transformers, library index

**Fail-Safe**: If dead, LLM operates without RAG context (pure conversation mode)

---

### Zooid 8: Session Management (klr-voice-session)
**Responsibility**: Conversation context, speaker tracking, session persistence.

**Services Migrated**:
- Conversation history management
- Speaker identification (future: speaker enrollment when fixed)
- Session state persistence (TOON-compressed snapshots)
- Context window truncation strategies

**ChemBus Signals**:
- Emits: `VOICE.SESSION.UPDATED` (session_id, message_count, context_size)
- Emits: `VOICE.SESSION.SNAPSHOT.SAVED` (file_path, compression_ratio)
- Listens: `VOICE.STT.TRANSCRIPTION` (append user utterance to session)
- Listens: `VOICE.LLM.RESPONSE` (append assistant response to session)

**Dependencies**: Filesystem persistence, TOON compression library

**Fail-Safe**: If dead, operate in stateless mode (no conversation memory)

---

### Orchestrator: Voice Orchestrator (klr-voice-orchestrator)
**Responsibility**: Coordinate zooid interactions, implement conversation loop, handle failures.

**Core Logic** (~800 lines):
1. Listen for `VOICE.AUDIO.CAPTURED` or text input
2. Route to STT zooid if audio
3. Send transcription to Intent, Emotion, Session zooids (parallel)
4. If knowledge needed, query Knowledge zooid
5. Assemble context and send to LLM zooid
6. Receive response, send to TTS zooid
7. Emit final response via ChemBus (text + audio)

**ChemBus Signals**:
- Emits: All `VOICE.ORCHESTRATOR.*` signals
- Listens: All `VOICE.*` signals from other zooids

**Dependencies**: All zooids (degrades gracefully if any are missing)

**Fail-Safe**: Implements timeout and fallback logic for every zooid interaction

## Migration Phases

### Phase 0: Baseline Recording (Read-Only)
**Goal**: Establish test baselines before any changes.

**Actions**:
1. Record 20 typical voice interactions (audio + transcriptions)
2. Capture baseline metrics:
   - End-to-end latency (user speech → audio response)
   - Memory usage (kloros-voice.service RSS)
   - ChemBus signal counts (historian query)
   - Error rates (journalctl analysis)
3. Export current state snapshots:
   - Question queues (TOON format)
   - Active investigations
   - Conversation sessions

**Deliverables**:
- `/tmp/voice_baseline_recordings/` (audio + metadata)
- `/tmp/voice_baseline_metrics.json`
- `/tmp/voice_baseline_state.toon`

**Confidence Gates**: N/A (read-only phase)

---

### Phase 1: Audio I/O + Speech Recognition + Speech Synthesis
**Why First**: Peripherals with no persistent state, easy rollback.

**Actions**:
1. Create git worktree: `git worktree add /tmp/kloros-voice-refactor-phase1`
2. Extract Audio I/O zooid:
   - Move `PulseAudioManager` to `kloros_voice_audio_io.py`
   - Create systemd unit `kloros-voice-audio-io.service`
   - Implement ChemBus signal handlers
3. Extract STT zooid (similar process)
4. Extract TTS zooid (similar process)
5. Update orchestrator to use ChemBus signals instead of direct calls

**Testing**:
- **Unit**: Audio I/O captures/plays raw PCM, STT transcribes test audio, TTS generates WAV
- **Integration**: Orchestrator → Audio I/O → STT → TTS → Audio I/O (full loop)
- **E2E**: Record user speech, verify transcription and spoken response match baseline

**Confidence Gates**:
- All tests pass
- Latency within 10% of baseline
- No new errors in journalctl
- 1-hour manual smoke test (actual conversations)

**Rollback**: `git stash`, restart kloros-voice.service, verify baseline tests pass (max 5 minutes)

---

### Phase 2: Intent Classification + Emotional Processing
**Why Second**: Stateless enhancers, failures are non-critical.

**Actions**:
1. Extract Intent Classification zooid
2. Extract Emotional Processing zooid
3. Update orchestrator to handle missing intent/emotion signals gracefully

**Testing**: (Same 3-layer structure)

**Confidence Gates**: (Same criteria)

**Rollback**: `git stash`, restart voice stack services, verify Phase 1 tests pass (max 5 minutes)

---

### Phase 3: Knowledge Retrieval
**Why Third**: Has persistent state (vector DB) but failure is non-critical.

**Actions**:
1. Backup library index: `rsync -a /home/kloros/.kloros_memory/ /tmp/library_backup/`
2. Extract Knowledge Retrieval zooid
3. Update orchestrator to handle missing knowledge results

**Testing**: (Same 3-layer structure)

**Confidence Gates**: (Same criteria)

**Rollback**: `git stash`, restore library backup if corrupted, verify Phase 2 tests pass (max 10 minutes)

---

### Phase 4: LLM Integration
**Why Fourth**: Critical for responses but stateless, easy to test in isolation.

**Actions**:
1. Extract LLM Integration zooid (unified adapter for OpenAI, Anthropic, local)
2. Implement timeout and retry logic
3. Update orchestrator to handle LLM failures with canned responses

**Testing**: (Same 3-layer structure, focus on timeout/retry paths)

**Confidence Gates**: (Same criteria)

**Rollback**: `git stash`, verify Phase 3 tests pass (max 5 minutes)

---

### Phase 5: Session Management
**Why Fifth**: Persistent conversation state, requires careful TOON snapshot handling.

**Actions**:
1. Export current session state: `toon_state_export.py` on all active conversations
2. Extract Session Management zooid
3. Implement session restore from TOON snapshots
4. Update orchestrator to handle stateless fallback

**Testing**: (Same 3-layer structure, verify session persistence across restarts)

**Confidence Gates**: (Same criteria)

**Rollback**: `git stash`, restore TOON session snapshots, verify Phase 4 tests pass (max 15 minutes)

---

### Phase 6: Final Orchestrator Reduction
**Why Last**: Brain surgery on the core coordinator.

**Actions**:
1. Export complete system state (all queues, investigations, consciousness)
2. Reduce `kloros_voice.py` to thin orchestrator (~800 lines)
3. Remove deprecated services:
   - Speaker enrollment (broken)
   - Mock backends (integrity violation)
   - D-REAM services (being refactored separately)
   - sounddevice (replaced by PulseAudio)
4. Rename service: `kloros-voice.service` → `kloros-voice-orchestrator.service`
5. Update all zooid systemd units to depend on orchestrator

**Testing**: (Same 3-layer structure, comprehensive smoke test)

**Confidence Gates**: (Same criteria + orchestrator <1000 lines)

**Rollback**: `git stash`, restore all TOON snapshots, verify Phase 5 tests pass (max 15 minutes)

## Testing Strategy

### Three-Layer Testing (Per Phase)

**Layer 1: Unit Tests**
- Each zooid tested in isolation with mocked ChemBus
- Example: Audio I/O zooid can capture/play PCM without running orchestrator
- Tools: pytest, unittest.mock for ChemBus signals

**Layer 2: Integration Tests**
- Zooid pairs tested with real ChemBus (no mocks)
- Example: Orchestrator sends `VOICE.ORCHESTRATOR.LLM.REQUEST` → LLM zooid responds with `VOICE.LLM.RESPONSE`
- Tools: pytest with real ChemBus (ZMQ), subprocess for zooid lifecycle

**Layer 3: End-to-End Tests**
- Full conversation loop using baseline recordings
- Input: recorded user audio from Phase 0
- Verification: transcription, response text, and output audio match baseline expectations
- Not bit-identical (LLM non-determinism), but semantically equivalent and latency comparable
- Tools: pytest, audio comparison (DTW alignment), semantic similarity (embeddings)

### Confidence Gates (All Phases)

Must pass before proceeding to next phase:
1. **All tests pass**: Unit, integration, E2E green
2. **Latency within 10% of baseline**: No performance regressions
3. **No new errors in journalctl**: Clean logs during test runs
4. **1-hour manual smoke test**: Actual voice conversations feel natural

### Baseline Comparison Strategy

**What "matches baseline" means**:
- **Latency**: E2E response time within 10% (allows for variance)
- **Transcriptions**: Word Error Rate (WER) < 5% vs baseline
- **Responses**: Semantic similarity > 0.85 (sentence embeddings)
- **Audio**: Spectral similarity > 0.90 (MFCC comparison)
- **Errors**: No new error types in logs

**What it doesn't mean**:
- Not bit-identical audio (TTS synthesis varies)
- Not character-identical LLM responses (temperature > 0)
- Not exact memory usage (acceptable variance ±10%)

## Rollback Procedures

### Core Rollback Strategy

All code changes are disposable until a phase passes its confidence gates. Git worktrees provide the escape hatch.

**Critical Principle**: Never delete the worktree until the next phase is green.

---

### Phase 0 (Baseline Recording)
**Rollback**: N/A (read-only analysis)

---

### Phase 1 (Audio I/O + STT + TTS)
**If Confidence Gates Fail**:
1. `cd /tmp/kloros-voice-refactor-phase1`
2. `git stash` (save work for later debugging)
3. `cd /home/kloros/src`
4. Restart voice stack services: `sudo systemctl restart kloros-voice.service`
5. Run baseline tests to verify system restored

**Data Loss Risk**: None (zooids are stateless)
**Max Rollback Time**: 5 minutes

---

### Phase 2 (Intent + Emotion)
**If Confidence Gates Fail**:
1. `cd /tmp/kloros-voice-refactor-phase2`
2. `git stash`
3. Return to Phase 1 worktree: `cd /tmp/kloros-voice-refactor-phase1`
4. Restart voice stack services (now includes Audio I/O, STT, TTS zooids)
5. Verify Phase 1 tests still pass

**Data Loss Risk**: None (zooids are stateless)
**Max Rollback Time**: 5 minutes

---

### Phase 3 (Knowledge Retrieval)
**If Confidence Gates Fail**:
1. `cd /tmp/kloros-voice-refactor-phase3`
2. `git stash`
3. Check if library index corrupted: `ls -lh /home/kloros/.kloros_memory/library_index.json`
4. If corrupted, restore: `rsync -a /tmp/library_backup/ /home/kloros/.kloros_memory/`
5. Return to Phase 2 worktree
6. Restart voice stack services
7. Verify Phase 2 tests still pass

**Data Loss Risk**: Library index corruption (mitigated by backup)
**Max Rollback Time**: 10 minutes (includes index restoration)

---

### Phase 4 (LLM Integration)
**If Confidence Gates Fail**:
1. `cd /tmp/kloros-voice-refactor-phase4`
2. `git stash`
3. Return to Phase 3 worktree
4. Restart voice stack services
5. Verify Phase 3 tests still pass

**Data Loss Risk**: None (LLM is stateless)
**Max Rollback Time**: 5 minutes

---

### Phase 5 (Session Management)
**If Confidence Gates Fail**:
1. `cd /tmp/kloros-voice-refactor-phase5`
2. `git stash`
3. Restore session state:
   ```bash
   python3 /home/kloros/src/kloros_memory/toon_state_export.py \
     --restore /tmp/voice_baseline_state.toon
   ```
4. Return to Phase 4 worktree
5. Restart voice stack services
6. Verify Phase 4 tests + active conversation sessions restored

**Data Loss Risk**: Active conversation context (mitigated by TOON snapshots)
**Max Rollback Time**: 15 minutes (includes state restoration)

**Note on TOON Snapshots**: Restoration provides perception of state (conversation history, question queues) but doesn't magically rehydrate every in-memory object. Zooids will re-initialize from persisted state.

---

### Phase 6 (Final Orchestrator Reduction)
**If Confidence Gates Fail**:
1. `cd /tmp/kloros-voice-refactor-phase6`
2. `git stash`
3. Restore complete system state:
   ```bash
   python3 /home/kloros/src/kloros_memory/toon_state_export.py \
     --restore /tmp/voice_phase5_state.toon
   ```
4. Return to Phase 5 worktree
5. Restart voice stack services (now using `kloros-voice-orchestrator.service`)
6. Verify Phase 5 tests + full system state restored

**Data Loss Risk**: All conversation state, investigations, queues (mitigated by comprehensive TOON export)
**Max Rollback Time**: 15 minutes (includes full state restoration)

---

### Emergency Full Rollback

**When to Use**: Multiple phase failures, system instability, unrecoverable errors.

**Procedure**:
1. Stop all KLoROS services:
   ```bash
   sudo systemctl stop kloros-*.service
   ```
2. Return to main branch:
   ```bash
   cd /home/kloros/src
   git checkout main
   ```
3. Restore Phase 0 baseline state:
   ```bash
   python3 /home/kloros/src/kloros_memory/toon_state_export.py \
     --restore /tmp/voice_baseline_state.toon
   ```
4. Restart core services:
   ```bash
   sudo systemctl start kloros-meta-agent.service
   sudo systemctl start kloros-voice.service
   ```
5. Manual smoke test: Verify system responds to voice commands
6. Review journalctl for any boot errors

**Data Loss Risk**: All changes since Phase 0 (acceptable for emergency)
**Max Rollback Time**: 20 minutes (includes full system restart)

**Critical**: Preserve all worktrees (`/tmp/kloros-voice-refactor-phase*`) for post-mortem debugging.

## Service Removal Plan

### Deprecated Services to Remove (Phase 6)

**1. Speaker Enrollment**
- **Why**: Never worked reliably, speaker identification broken
- **Removal**: Delete all `enrollment_*` functions, speaker profile DB
- **Impact**: None (already non-functional)

**2. Mock Backends**
- **Why**: Violates system integrity values (no simulation/stubs)
- **Removal**: Delete mock LLM/TTS/STT adapters
- **Impact**: Dev testing must use real services or separate test suite

**3. D-REAM Services**
- **Why**: Being refactored separately, don't belong in voice stack
- **Removal**: Extract to separate D-REAM refactoring worktree
- **Impact**: Voice stack no longer triggers D-REAM directly (meta-agent handles)

**4. sounddevice Integration**
- **Why**: Deprecated in favor of PulseAudio (more reliable, better integration)
- **Removal**: Delete sounddevice imports, audio capture/playback functions
- **Impact**: None (PulseAudio fully replaces it)

**Total Line Reduction**: ~1200 lines removed + ~2800 lines migrated to zooids = ~800 lines orchestrator

## Success Criteria

### Quantitative Metrics
- **Orchestrator size**: <1000 lines (target: ~800)
- **Zooid count**: 8 independent services
- **Latency regression**: <10% vs baseline
- **Test coverage**: >80% per zooid
- **Deployment time**: <2 minutes for single zooid restart

### Qualitative Metrics
- **Maintainability**: Can understand any single zooid in <30 minutes
- **Fault isolation**: LLM timeout doesn't crash audio I/O
- **Evolutionary capacity**: Can swap LLM providers in <1 hour
- **Observable behavior**: All inter-zooid communication visible in ChemBus historian

### Confidence Validation
- All 6 phases pass confidence gates
- 1-week production usage with no regressions
- User (kloros) confirms voice interactions feel natural

## Risk Assessment

### High Risks (Mitigated)
1. **Orchestrator brain surgery in Phase 6**
   - Mitigation: Phases 1-5 validate zooid pattern before touching core
   - Mitigation: Comprehensive state snapshots before Phase 6
   - Mitigation: Keep Phase 5 worktree alive until confidence gates pass

2. **Session state corruption during Phase 5 migration**
   - Mitigation: TOON snapshots before any changes
   - Mitigation: Rollback script tested in Phase 0
   - Mitigation: Conversation history persisted to filesystem (durable)

### Medium Risks (Acceptable)
1. **ChemBus latency overhead**
   - Acceptance: 10% latency budget allows for IPC overhead
   - Validation: Baseline comparison in every phase

2. **Zooid startup ordering dependencies**
   - Acceptance: Orchestrator implements timeout/retry for missing zooids
   - Validation: Integration tests with delayed zooid startup

### Low Risks (Acknowledged)
1. **TOON snapshot restore imperfect**
   - Acceptance: State restoration provides perception, not perfect memory
   - Validation: E2E tests verify functionality, not bit-identical state

## Implementation Timeline

**Total Estimated Effort**: 15-20 hours

- **Phase 0**: 2 hours (baseline recording + analysis)
- **Phase 1**: 4 hours (3 zooids, most straightforward)
- **Phase 2**: 2 hours (2 stateless zooids)
- **Phase 3**: 2 hours (1 zooid with persistent state)
- **Phase 4**: 2 hours (1 zooid with complex retry logic)
- **Phase 5**: 3 hours (1 zooid with TOON state handling)
- **Phase 6**: 4 hours (orchestrator reduction + service removal + final validation)

**Confidence Gates Add**: ~1 hour per phase (manual smoke testing)

**Recommendation**: Execute 1-2 phases per day to allow production soak time between phases.

## Future Enhancements

### Post-Refactoring Opportunities
1. **Multi-LLM reasoning**: Run multiple LLM zooids in parallel, compare responses
2. **Emotional memory persistence**: Session zooid persists affective arc to disk
3. **Speaker enrollment v2**: Fix speaker identification using new enrollment algorithm
4. **Voice profile customization**: Per-user TTS voice profiles
5. **Knowledge federation**: Multiple knowledge zooids for specialized domains
6. **Intent learning**: Train custom intent classifier on conversation history

### Architectural Validation
If this refactoring succeeds, apply zooid pattern to:
- `kloros_goals.py` (goal management, PHASE integration)
- `kloros_investigations.py` (investigation lifecycle, AGOR coordination)
- `kloros_memory.py` (episodic memory, library indexing, vector DB)

## Conclusion

This design provides a safe, phased migration path from monolithic voice service to zooid-based architecture. The outside-in approach validates the zooid pattern on low-risk peripherals before touching the orchestrator core. Git worktrees + TOON state snapshots + comprehensive testing give high confidence we can "always get home" if any phase fails.

The result will be a voice system that embodies KLoROS's biological architecture: specialized zooids coordinated by a chemical nervous system (ChemBus), with graceful degradation and evolutionary flexibility.

**Proceed with Phase 0 baseline recording when ready.**
