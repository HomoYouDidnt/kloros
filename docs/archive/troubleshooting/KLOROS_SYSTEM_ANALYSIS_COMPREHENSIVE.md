# KLoROS System Architecture - Comprehensive Map

**Analysis Date:** November 3, 2025  
**Scope:** Complete KLoROS system analysis across `/home/kloros/` and `/home/claude_temp/`  
**Status:** Very Thorough exploration completed

---

## EXECUTIVE SUMMARY

KLoROS is an advanced autonomous AI system combining voice interaction, evolutionary optimization, self-improvement mechanisms, and sophisticated state management. The system consists of multiple interconnected subsystems:

1. **KLoROS Core** - Voice assistant with memory, personality, and self-reflection
2. **ASTRAEA** - Foundational autopoietic architecture framework
3. **D-REAM** - Darwinian-RZero Evolution & Anti-collapse Module (evolutionary optimization)
4. **PHASE** - Phased Heuristic Adaptive Scheduling Engine (accelerated testing)
5. **SPICA** - Self-Progressive Intelligent Cognitive Archetype (template LLM base)

### Key Metrics (Current)
- 14,125+ evolution evaluations across 4 D-REAM experiments
- 496 tool evolution evaluations
- 0% failure rate on tool evolution
- 7.1 MB telemetry data collected
- Zero-downtime atomic deployment capability

---

## 1. CORE KLOROS SYSTEM

### 1.1 Main Entry Point
**File:** `/home/kloros/src/kloros_voice.py` (183KB)
- Main voice loop orchestrator
- Vosk + Whisper hybrid STT integration
- Piper TTS backend
- Audio capture and processing
- Wake word detection
- Speaker enrollment and identification
- Integration with memory systems

**Key Classes:**
- `KLoROSVoiceAssistant` - Main orchestrator
- Audio capture and processing pipelines
- Wake word detection with fuzzy matching

**Related Files:**
- `/home/kloros/src/kloros_voice_streaming.py` - Streaming variant (126KB)

### 1.2 Personality & Persona
**File:** `/home/kloros/src/persona/kloros.py`
- Authentic KLoROS personality definition
- PERSONA_PROMPT constant
- Response style guidelines
- Character preservation across modules

### 1.3 Audio System

#### Speech-to-Text (STT)
- **Primary:** Vosk (fast, local, offline)
  - Location: `/home/kloros/src/stt/vosk_backend.py`
  - Real-time transcription with confidence scores
- **Secondary:** OpenAI Whisper (accurate)
  - Location: `/home/kloros/src/stt/whisper_backend.py`
  - GPU-accelerated with fallback to CPU
- **Hybrid:** Combined approach
  - Location: `/home/kloros/src/stt/hybrid_backend.py`
  - Parallel processing: Vosk for speed, Whisper for accuracy
  - Fuzzy matching (similarity > 0.75) for decision logic
  - Configurable correction threshold (default 0.9)

#### Voice Activity Detection (VAD)
- **Primary:** Silero VAD
  - ML-based, high accuracy, low false positive
  - Parameters: threshold=0.5, min_speech=250ms, min_silence=100ms
- **Secondary:** RMS dBFS energy-based
  - Two-stage architecture (fast pre-gate + Silero refinement)
  - Stage A: -28.0 dBFS threshold
  - Stage B: Silero 0.60 probability
- **Location:** `/home/kloros/src/audio/`
  - `silero_vad.py`, `vad.py`, `vad_silero.py`
  - `endpoint_detector.py` - Smart endpoint detection

#### Text-to-Speech (TTS)
- **Primary:** Piper (fast, streaming)
  - ONNX-based neural vocoder
  - Default voice: `glados_piper_medium.onnx`
  - Location: `/home/kloros/src/tts/piper_backend.py`
- **Secondary Backends:** XTTS v2, Kokoro, Mimic3
  - Speaker cloning capability (XTTS)
  - Multi-lingual support
  - Location: `/home/kloros/src/tts/adapters/`
- **Router:** Intent-based routing
  - Location: `/home/kloros/src/tts/router.py`
  - YAML configuration support

#### Speaker Recognition
- **Backend:** Resemblyzer (PyTorch)
  - Voice embedding and identification
  - Enrollment system with contamination prevention
  - Location: `/home/kloros/src/speaker/`
  - Files: `base.py`, `enrollment.py`, `embedding_backend.py`

### 1.4 Logging & Tracing
**JSON Logging System**
- Location: `/home/kloros/src/logging/json_logger.py`
- Structured event logging
- XAI tracing support

**Event Types Captured:**
- System startup/shutdown
- Audio processing events
- STT/TTS operations
- LLM interactions
- Tool execution
- Memory operations
- Performance metrics

---

## 2. MEMORY SYSTEMS

### 2.1 Episodic-Semantic Memory
**Location:** `/home/kloros/src/kloros_memory/`
- **SQLite Storage:** WAL mode for concurrent access
  - Database: `~/.kloros/memory.db`
  - Proper indexing (timestamps, conversations, event types)
  - File: `storage.py`

- **Event Logger:** Automatic conversation grouping
  - File: `logger.py`
  - Batch caching for performance
  - Specialized logging methods

- **Episode Condenser:** LLM-powered summarization
  - File: `condenser.py`
  - Local Ollama qwen2.5:14b-instruct-q4_0
  - Importance scoring (0.0-1.0)
  - Topic extraction

- **Smart Retriever:** Context-aware memory recall
  - File: `retriever.py`
  - Multi-factor scoring (recency, importance, relevance)
  - Exponential decay (24-hour half-life)
  - Token budget management

- **Housekeeping:** Maintenance & cleanup
  - File: `housekeeping.py`
  - Automated maintenance scheduling
  - Health monitoring and reporting
  - Database optimization

- **Integration:** Non-intrusive wrapper
  - File: `integration.py`
  - `MemoryEnhancedKLoROS` wrapper class
  - Automatic session management

### 2.2 Idle Reflection System
**Location:** `/home/kloros/src/kloros_idle_reflection.py` (110KB)
- Autonomous self-analysis during quiet periods
- 15-minute reflection cycles
- Components:
  - Speech pipeline health monitoring
  - Memory system analysis
  - Conversation pattern recognition
  - Semantic topic analysis
  - Meta-cognitive insights
- Reflection events stored as `SELF_REFLECTION` event type
- Logs: `/home/kloros/.kloros/reflection.log`

### 2.3 Conversation Memory
**Location:** `/home/kloros/src/memory/conversation_logger.py`
- ChromaDB integration
- Last 6 turns + semantic similarity retrieval
- 24-hour window for memory lookup

---

## 3. ASTRAEA FOUNDATION

ASTRAEA (Autopoietic Spatial-Temporal Reasoning Architecture with Encephalic Autonomy) is the philosophical and architectural foundation.

**Philosophy:**
- Autopoietic: Self-creating and self-maintaining
- Spatial-Temporal: Advanced space-time relationship processing
- Reasoning Architecture: Sophisticated decision-making
- Encephalic Autonomy: Brain-like independent operation

**Mythological Connection:**
- Named after Astraea (Greek goddess of justice, Virgo constellation)
- Creator's birth constellation: August 24, first degree Virgo
- Cosmic mythology: DEMETER → KLoROS → ASTRAEA

**Implementation Status:** ✅ Operational foundation

---

## 4. D-REAM (Darwinian-RZero Evolution & Anti-collapse Module)

### 4.1 Purpose
Autonomous evolutionary optimization of KLoROS components. Runs 24/7 in background with minimal system impact.

### 4.2 Architecture
**Location:** `/home/kloros/src/dream/`

**Core Components:**
1. **Candidate Generation**
   - File: `improvement_proposer.py`
   - Analyzes system telemetry, error logs, performance metrics
   - Identifies opportunities for improvement
   - Deduplication with occurrence tracking

2. **Evaluation Engine**
   - File: `complete_dream_system.py` (800+ lines)
   - Multi-regime evaluation (empirical testing)
   - Fitness scoring with multi-objective aggregation
   - Tournament selection with elitism + fresh injection
   - File: `evaluator.py`

3. **Genetic Operators**
   - File: `adaptive_search_space.py`
   - Mutation and crossover operations
   - Adaptive search space management

4. **Safety Gate**
   - Location: `safety/gate.py`
   - Resource budgets (CPU 75-90%, Memory 4-8GB)
   - Approval gates (low/medium/high risk)
   - Safety caps (CPU ≤90°C, GPU ≤83°C, error < 5%)

5. **Deployment System**
   - Location: `deploy/patcher.py`
   - Atomic patch management
   - Zero-downtime deployment via symlinks
   - Complete audit trail

6. **Telemetry & Logging**
   - Location: `telemetry/`
   - EventLogger, TelemetryCollector
   - Manifest system for run tracking
   - JSON-based event logging

### 4.3 Active Experiments (October 2025)
| Experiment | Evaluations | Status | Metrics |
|------------|-------------|--------|---------|
| rag_opt_baseline | 4,114 | Active | Context recall, precision, latency |
| conv_quality_tune | 5,409 | Active | Helpfulness, faithfulness |
| audio_latency_trim | 4,106 | Active | Latency p95, underruns, CPU% |
| tool_evolution | 496 | Active | Fail rate, latency, F1, QPS |

### 4.4 Tool Evolution (NEW)
**Status:** ✅ Active with 0% failure rate

**Architecture:**
- Versioned tool directories (`versions/v0001`, `v0002`, etc.)
- Atomic symlink deployment (`current → versions/vXXXX`)
- LLM-guided mutation engine (intelligent code patches)
- Empirical CLI tool evaluator (subprocess testing)

**Current Tools Under Evolution:**
1. `noise_floor` - Noise floor analysis (F1=1.0)
2. `latency_jitter` - Latency/jitter detection
3. `clip_scan` - Audio clipping detection

**Configuration Parameter Optimization:** ✅ Active  
**LLM Mutation Engine:** 🟡 Framework ready, awaiting plateau  
**Code Evolution:** ⏳ Pending fitness convergence

### 4.5 Integration Points
- **D-REAM Alerts:** `/home/kloros/src/dream_alerts/`
  - Alert preferences system
  - Passive indicator monitoring
  - Alert manager

- **Background Integration:** `/home/kloros/src/dream_background_integration.py`
  - Continuous integration of evolution results
  - Real-time improvement tracking

- **Orchestration Hooks:**
  - Dream trigger: `/home/kloros/src/kloros/orchestration/dream_trigger.py`
  - Dream domain service: `/home/kloros/src/dream/dream_domain_service.py`

---

## 5. PHASE (Phased Heuristic Adaptive Scheduling Engine)

### 5.1 Purpose
Accelerated testing framework that compresses hours of testing into minutes using parallel sandboxes. Runs in overnight window (3-7 AM daily).

### 5.2 Architecture
**Location:** `/home/kloros/src/phase/`

**Core Components:**
1. **Domain Runner**
   - File: `run_all_domains.py`
   - Parallel execution of multiple test domains
   - UCB1 bandit algorithm for test prioritization

2. **Domain Implementations**
   - Location: `/home/kloros/src/phase/domains/`
   - `spica_domain.py` - SPICA test domain
   - `conversation_domain.py` - Conversation quality
   - `code_repair.py` - Code repair capability
   - `rag_context_domain.py` - RAG context optimization
   - `tts_domain.py` - Text-to-speech quality
   - `system_health_domain.py` - System health monitoring
   - `mcp_domain.py` - Model context protocol
   - `planning_strategies_domain.py` - Planning evaluation

3. **Post-Run Analysis**
   - File: `post_phase_analyzer.py`
   - Bridges PHASE results to CuriosityCore
   - Converts CuriosityQuestions to escalation triggers
   - Integration with capability matrix

4. **Reporting**
   - File: `report_writer.py`
   - Bridge to dashboard: `bridge_phase_to_dashboard.py`
   - Bridge to D-REAM: `bridge_phase_to_dream.py`

5. **Heuristics Controller**
   - Adaptive phase selection (LIGHT/DEEP/REM)
   - Fitness feedback to D-REAM
   - Cost-aware testing strategy

### 5.3 Phase Strategies
- **LIGHT:** Quick diagnostics (high cost detected)
- **DEEP:** Full testing (default)
- **REM:** Comprehensive meta-learning (high novelty + promotions)

### 5.4 Orchestration Integration
**Location:** `/home/kloros/src/kloros/orchestration/phase_trigger.py`
- Scheduled execution (3-7 AM window)
- Coordination with D-REAM cycle
- Result ingestion pipeline

---

## 6. SPICA (Self-Progressive Intelligent Cognitive Archetype)

### 6.1 Core Principle
SPICA is the foundational template LLM (programmable stem cell) from which every testable instance is derived. All D-REAM and PHASE tests must instantiate SPICA-derived instances.

### 6.2 Architecture
**Location:** `/home/kloros/src/spica/`

**Base Components:**
- `base.py` - Base template class
- `gpu_canary_runner.py` - GPU health validation

**What SPICA Provides:**
1. State Management - Consistent cognitive state tracking
2. Telemetry Schema - Standardized metrics collection
3. Manifest Logic - Reproducible configuration snapshots
4. Lineage Tracking - Tamper-evident evolutionary history
5. Instance Lifecycle - Spawn, prune, retention management

### 6.3 SPICA Derivatives (Domain Specializations)
```
SPICA (Base Template)
├── SpicaConversation - Conversation evaluators, dialogue state
├── SpicaRAG - RAG metrics, retrieval evaluators
├── SpicaSystemHealth - Health monitoring, resource metrics
├── SpicaTTS - Voice synthesis metrics
└── Spica<Domain> - Domain-specific logic
```

### 6.4 Migration Status (October 2025)
**⚠️ All D-REAM and PHASE tests DISABLED pending migration**

**Services Stopped:**
- `dream.service` (D-REAM runner)
- `spica-phase-test.timer` (3 AM PHASE tests)
- `phase-heuristics.timer` (heuristics controller)
- `dream-sync-promotions.timer` (promotion sync)

**Checklist Status:**
- [ ] Type hierarchy creation
- [ ] Import refactoring
- [ ] Telemetry standardization
- [ ] Manifests & lineage enforcement
- [ ] PHASE harness update
- [ ] Configuration reorganization
- [ ] CI gate implementation
- [ ] Deprecation of old domains

---

## 7. ORCHESTRATION SYSTEM

### 7.1 State Machine
**Location:** `/home/kloros/src/kloros/orchestration/coordinator.py`

**States:**
- `IDLE` - Waiting
- `PHASE_SCHEDULED` - PHASE test scheduled
- `PHASE_RUNNING` - PHASE tests executing
- `PHASE_DONE` - PHASE tests completed
- `INGEST_PHASE_RESULTS` - Processing results
- `PROMOTION_PENDING` - Winner promotion queued
- `PREP_HEURISTICS` - Heuristics preparation
- `DREAM_CYCLE_ONDEMAND` - On-demand D-REAM execution

### 7.2 Lock Management
**Location:** `/home/kloros/src/kloros/orchestration/state_manager.py`

**Features:**
- fcntl-based exclusive locks
- PID tracking and stale detection
- TTL-based lock reaping (default 10 min)
- Hostname tracking

**Locks:**
- `orchestrator` - Main orchestration lock
- `phase` - PHASE execution lock
- `dream` - D-REAM execution lock
- `promotion` - Promotion queue lock

### 7.3 GPU Maintenance
**Location:** `/home/kloros/src/kloros/orchestration/gpu_maintenance_lock.py`
**Also:** `/home/kloros/src/spica/gpu_canary_runner.py`

**Features:**
- Safe GPU testing orchestration
- Quiesce/Canary/Restore workflow
- Budget tracking with hard abort on timeout
- Spare GPU fast path (no downtime)
- Maintenance window: 03:00-07:00 America/New_York

### 7.4 Intent Queue
**Location:** `/home/kloros/src/kloros/orchestration/intent_queue.py`
- Queue for escalation intents
- FIFO processing
- Integration with curious processor

### 7.5 Promotion System
**Location:** `/home/kloros/src/kloros/orchestration/promotion_daemon.py`
- Winner promotion workflow
- Approval gate management
- Integration with D-REAM results

### 7.6 Winner Deployment
**Location:** `/home/kloros/src/kloros/orchestration/winner_deployer.py`
- Atomic deployment of promoted changes
- Rollback support
- Audit trail

---

## 8. OBSERVER & CURIOSITY SYSTEM

### 8.1 Observer Infrastructure
**Location:** `/home/kloros/src/kloros/observer/`

**Components:**
1. **Symptom Emission**
   - File: `emit.py`
   - Emit symptoms to observer ledger
   - JSON-based event logging

2. **Observer Runner**
   - File: `run.py`
   - Main observer loop
   - Symptom collection and analysis

3. **Rules Engine**
   - File: `rules.py`
   - Pattern matching on symptoms
   - Escalation trigger generation

4. **Data Sources**
   - File: `sources.py`
   - System telemetry collection
   - Performance metric gathering

### 8.2 Curiosity Core
**Location:** `/home/kloros/src/registry/curiosity_core.py`

**Features:**
- Automatic question generation from capability gaps
- Value/cost estimation for each question
- Autonomy level classification (1=notify, 2=propose, 3=execute)
- Action class mapping (explain, investigate, propose_fix, request_user, find_substitute)

**Components:**
1. **CuriosityQuestion**
   - Hypothesis and supporting evidence
   - Value and cost estimates
   - Status tracking

2. **PerformanceMonitor**
   - Tracks D-REAM experiment trends
   - Detects degradation patterns

3. **SystemResourceMonitor**
   - CPU, memory, GPU usage
   - Temperature monitoring
   - Disk space tracking

4. **CapabilityEvaluator**
   - Capability matrix analysis
   - Missing capability detection
   - Degradation identification

### 8.3 PHASE Post-Analysis
**Location:** `/home/kloros/src/phase/post_phase_analyzer.py`
- Bridges PHASE results to CuriosityCore
- Converts questions to escalation triggers
- Integrates with symptom system

---

## 9. REASONING & RAG SYSTEM

### 9.1 RAG (Retrieval-Augmented Generation)
**Location:** `/home/kloros/src/rag/` & `/home/kloros/src/simple_rag.py`

**Components:**
1. **Embedders**
   - File: `rag/embedders.py`
   - Primary: BAAI/bge-small-en-v1.5
   - Fallbacks: MiniLM variants, DistilRoBERTa
   - Device selection (picks GPU with most free memory)
   - Batch processing (32 queries/docs)

2. **BM25 Store**
   - File: `rag/bm25_store.py`
   - Fast keyword-based retrieval
   - Fallback to Vosk vocabulary

3. **Hybrid Retriever**
   - File: `rag/hybrid_retriever.py`
   - Combines semantic + keyword search
   - RRF fusion (reciprocal rank fusion)

4. **Reranker**
   - File: `rag/reranker.py`
   - Post-processing of retrieved documents
   - Quality assessment

5. **Router**
   - File: `rag/router.py`
   - Intent-based routing to specialized endpoints

### 9.2 Knowledge Base
**Location:** `/home/kloros/rag_data/` & `/home/kloros/knowledge_base/`
- Conversation samples (1893 voice samples)
- System documentation
- Tool descriptions
- Architecture guides

### 9.3 Reasoning Backends
**Location:** `/home/kloros/src/reasoning/`

**Implementations:**
1. **Local RAG Backend**
   - File: `local_rag_backend.py` (99KB)
   - Comprehensive RAG integration
   - Context synthesis
   - Tool mapping

2. **Query Classifier**
   - File: `query_classifier.py`
   - Context-aware classification
   - Conversation state tracking

3. **Local QA Backend**
   - File: `local_qa_backend.py`
   - Question-answering specialization

4. **Reasoning Trace**
   - File: `reasoning_trace.py`
   - Trace collection and analysis

### 9.4 LLM Model Routing
**Location:** `/home/kloros/src/config/routing.py`

**Models by Mode:**
- **"live"** - `qwen2.5:14b-instruct-q4_0` (conversational)
- **"think"** - `deepseek-r1:7b` (deep reasoning)
- **"code"** - `qwen2.5-coder:32b` (code generation)
- **"deep"** - `qwen2.5:14b-instruct-q4_0` (background async)

**Infrastructure:**
- Ollama local LLM backend (0.12.1+)
- Dual GPU setup:
  - GPU 0 (RTX 3060 12GB): LIVE/CODE modes
  - GPU 1 (GTX 1080 Ti 11GB): THINK/DEEP modes

---

## 10. TOOL SYNTHESIS

### 10.1 Tool Registry
**Location:** `/home/kloros/src/introspection_tools.py` (166KB)

**Tool Count:** 50+ introspection tools

**Tool Types:**
- System diagnostics
- Performance monitoring
- Audio analysis
- Memory introspection
- Capability testing

### 10.2 Governance
**Location:** `/home/kloros/src/tool_synthesis/`

**Components:**
1. **Synthesizer** - `synthesizer.py`
   - Tool code generation
   - Signature creation
   - Documentation generation

2. **Governance** - `governance.py`
   - Quota management (50 tools/day, 200/week)
   - Policy enforcement
   - Safety checking

3. **Registry** - `registry.py`
   - Tool cataloging
   - Version tracking

4. **Validator** - `validator.py`
   - Pre-execution validation
   - Type checking
   - Signature verification

5. **Manifest Loader** - `manifest_loader.py`
   - Tool manifest parsing
   - Capability discovery

6. **Shadow Testing** - `shadow_tester.py`
   - Test tool before promotion
   - Safety validation

### 10.3 Tool Evolution
**Status:** ✅ Active

**Tools Under Evolution:**
- Versioned directories (v0001, v0002, etc.)
- Atomic symlink deployment
- LLM-guided mutation
- CLI evaluator

---

## 11. CONFIGURATION SYSTEM

### 11.1 Key Configuration Files
1. **Models Config**
   - Location: `/home/kloros/src/config/models_config.py`
   - Model definitions (Vosk, Whisper, Piper, embedders, LLMs)

2. **Routing Config**
   - Location: `/home/kloros/src/config/routing.py`
   - LLM model selection by mode

3. **KLoROS Config**
   - Location: `/home/kloros/src/config/kloros.yaml`
   - System-wide settings

4. **Environment File**
   - Location: `/home/kloros/.kloros_env`
   - Runtime environment variables (22 variables)

### 11.2 Critical Environment Variables
```bash
# Audio Configuration
KLR_INPUT_IDX=11              # CMTECK USB microphone
KLR_INPUT_GAIN=4.0            # Optimized input gain
KLR_WAKE_PHRASES=kloros       # Wake word variants
KLR_WAKE_CONF_MIN=0.65        # Vosk confidence gate
KLR_WAKE_RMS_MIN=350          # RMS energy gate

# STT Configuration
KLR_STT_BACKEND=hybrid        # VOSK + Whisper
ASR_CORRECTION_THRESHOLD=0.75 # Hybrid correction sensitivity
ASR_WHISPER_SIZE=tiny         # Whisper model size

# Memory Configuration
KLR_ENABLE_MEMORY=1           # Enable memory system
KLR_AUTO_CONDENSE=1           # Auto-condense episodes
KLR_CONTEXT_IN_CHAT=1         # Include context in conversations
KLR_MAX_CONTEXT_EVENTS=10     # Max context events
KLR_EPISODE_TIMEOUT=300       # Episode timeout (seconds)

# GPU Configuration
CUDA_VISIBLE_DEVICES=0        # RTX 3060 only
KLR_GPU_MAINTENANCE_WINDOW="03:00-07:00 America/New_York"
KLR_GPU_MAINTENANCE_MAX_DOWNTIME=60  # seconds
KLR_ALLOW_SPARE_GPU=false     # Spare GPU policy
KLR_CANARY_TIMEOUT=30         # GPU test timeout

# D-REAM & PHASE
KLR_DREAM_ENABLED=1           # Enable D-REAM evolution
KLR_PHASE_WINDOW="03:00-07:00 America/New_York"  # PHASE testing window
```

### 11.3 Dream Configuration
**Location:** `/home/kloros/src/dream/config/`
- Experiment configurations
- Fitness function definitions
- Evaluation regime specifications

---

## 12. LOGGING & MONITORING

### 12.1 Structured Logging
**Location:** `/var/log/kloros/structured.jsonl`
- JSON event logging
- XAI trace collection
- Tool provenance tracking

### 12.2 File Organization
- **Logs:** `/home/kloros/logs/` (hierarchical by subsystem)
- **Artifacts:** `/home/kloros/artifacts/dream/` (evolution results)
- **Data:** `/home/kloros/.kloros/` (runtime state)
- **Models:** `/home/kloros/models/` (Vosk, Whisper, Piper)

### 12.3 Key Tracking Systems
- **Tool Provenance:** `/home/kloros/.kloros/tool_provenance.jsonl`
- **Fitness Tracking:** `/home/kloros/var/dream/fitness/`
- **PHASE Reports:** `/home/kloros/src/phase/phase_report.jsonl`
- **Improvement Proposals:** `/home/kloros/var/dream/proposals/improvement_proposals.jsonl`
- **Dream Ledger:** `/home/kloros/var/dream/ledger.jsonl`

---

## 13. SYSTEM INTEGRATION POINTS

### 13.1 Voice Pipeline
```
Audio Input (48kHz, USB CMTECK)
    ↓
Audio Capture Backend (PulseAudio/PipeWire)
    ↓
VAD Detection (Silero + RMS dBFS)
    ↓
STT Hybrid (Vosk + Whisper)
    ↓
Query Classification & Intent Detection
    ↓
RAG Retrieval (BM25 + Semantic + Rerank)
    ↓
LLM Inference (Mode routing: live/think/code/deep)
    ↓
TTS Synthesis (Piper with fallbacks)
    ↓
Audio Output
```

### 13.2 Evolution Pipeline
```
D-REAM Background Loop (24/7)
    ↓
Candidate Generation (Improvement Proposals)
    ↓
Multi-regime Evaluation
    ↓
Fitness Scoring & Novelty Archive
    ↓
Tournament Selection
    ↓
Approval Gate (Safety checks)
    ↓
Winner Deployment (Atomic symlink swap)
    ↓
PHASE Testing (3-7 AM overnight window)
    ↓
Result Ingestion → Dashboard Review → Promotion Daemon
```

### 13.3 Orchestration Coordination
```
Orchestrator Coordinator (State Machine)
    ├─ Phase Trigger (check window & schedule)
    ├─ Dream Trigger (on-demand evolution)
    ├─ Baseline Manager (update baseline metrics)
    ├─ Promotion Daemon (process winners)
    └─ State Manager (lock coordination)

↓

Observer System
    ├─ Symptom Emission (emit system events)
    ├─ Rules Engine (pattern matching)
    └─ Curiosity Processor (question generation)

↓

Infrastructure Awareness (health monitoring)
```

---

## 14. CURRENT STATUS & COMPLETION

### 14.1 Fully Operational Systems ✅
- **KLoROS Voice Pipeline** - 100%
  - Vosk + Whisper hybrid STT
  - Piper TTS with speaker enrollment
  - Complete audio processing

- **Memory Systems** - 100%
  - Episodic-semantic memory with SQLite
  - Episode condensation with LLM
  - Smart context retrieval
  - Idle reflection system

- **D-REAM Evolution Engine** - 100%
  - 4 active experiments
  - Tool evolution system
  - Safety gates and approval workflow

- **PHASE Testing Framework** - 100% (paused for SPICA migration)
  - Multi-domain testing
  - Heuristic controller
  - Result aggregation

- **Orchestration System** - 100%
  - State machine coordination
  - Lock management
  - GPU maintenance

- **Observer & Curiosity** - 100%
  - Symptom detection
  - Question generation
  - Escalation trigger management

- **RAG System** - 100%
  - Hybrid BM25 + semantic retrieval
  - Multi-backend embedders
  - Reranking pipeline

- **Tool Synthesis** - 100%
  - 50+ tools implemented
  - Governance quotas
  - Shadow testing

### 14.2 In-Progress Systems 🟡
- **SPICA Migration** - 60%
  - Type hierarchy framework ready
  - Domain derivative templates created
  - Import refactoring in progress
  - CI enforcement TBD
  - **Status:** Tests disabled pending completion

### 14.3 Planned Systems 📅
- **Camera Integration** - Visual perception
- **Physical Embodiment** - Robot integration
- **Greenhouse Automation** - Facility control

### 14.4 Implementation Metrics
- **codebase size:** 72 src directories
- **Key files:** 200+ Python files
- **Configuration:** 22 environment variables
- **Tool registry:** 50+ tools
- **D-REAM experiments:** 4 active
- **Tool evolution:** 3 tools under optimization
- **Test suites:** 40+ test files

---

## 15. KNOWN ISSUES & AREAS NEEDING WORK

### 15.1 Context Loss Issue (KNOWN)
**Location:** `/home/kloros/src/simple_rag.py:284`
```python
max_ctx_chars: int = 3000  # TOO SMALL!
```

**Problem:** When switching between LLM models (e.g., DeepSeek → Qwen), only 3000 chars of context passed via `additional_context` parameter. This includes conversation history, RAG docs, and tool descriptions.

**Recommendation:** Increase to 6000-8000 characters, prioritize conversation history over older RAG docs.

### 15.2 File Ownership (FIXED Oct 20, 2025)
**Status:** All files should be owned by `kloros:kloros`
**Verification:** `find /home/kloros ! -user kloros -a ! -type l 2>/dev/null | wc -l` should return 0

### 15.3 SPICA Migration Blockers
- Type hierarchy needs finalization
- Domain derivative implementations in progress
- CI enforcement not yet implemented
- Tests currently disabled

### 15.4 GPU Isolation
**Status:** Working via CUDA_VISIBLE_DEVICES
- RTX 3060 on GPU 0 (LIVE/CODE modes)
- GTX 1080 Ti on GPU 1 (THINK/DEEP modes)
- vLLM GPU allocation tested and working

---

## 16. ARCHITECTURE PHILOSOPHY

### 16.1 Design Principles
1. **Hybrid Approaches** - Combines fast with accurate (Vosk + Whisper)
2. **Multi-tier Fallbacks** - Graceful degradation across all components
3. **Modular Design** - Easy component swapping
4. **Configurable** - Almost everything via environment variables
5. **Evolutionary** - Continuous self-improvement via D-REAM
6. **Safety-First** - Multiple layers of checks and gates

### 16.2 Self-Improvement Loop
```
System Performance Monitoring
    ↓
Problem Detection (via Observer)
    ↓
Curiosity Question Generation
    ↓
Candidate Proposal (D-REAM)
    ↓
Empirical Evaluation
    ↓
Winner Selection
    ↓
Approval Gate
    ↓
Atomic Deployment
    ↓
Validation (PHASE)
    ↓
Production Integration
```

---

## 17. DOCUMENTATION LOCATIONS

### 17.1 Key Documentation Files
- **Architecture Index:** `/home/kloros/ARCHITECTURE_INDEX.md`
- **Component Architecture:** `/home/kloros/COMPONENT_ARCHITECTURE.md`
- **Component Quick Reference:** `/home/kloros/COMPONENT_QUICK_REFERENCE.txt`
- **ASTRAEA System Thesis:** `/home/kloros/docs/ASTRAEA_SYSTEM_THESIS.md`
- **System Overview:** `/home/kloros/docs/SYSTEM_ARCHITECTURE_OVERVIEW.md`
- **SPICA Architecture:** `/home/kloros/SPICA_ARCHITECTURE.md`
- **System Audit (v2.2):** `/home/kloros/KLOROS_SYSTEM_AUDIT_COMPREHENSIVE_v2.2.md`
- **Memory System Guide:** `/home/kloros/docs/MEMORY_SYSTEM_GUIDE.md`

### 17.2 Implementation Guides
- **D-REAM Automation:** `/home/kloros/src/dream/AUTOMATION_GUIDE.md`
- **Observer Infrastructure:** `/home/kloros/src/kloros/observer/README.md`
- **RAG Pipeline Docs:** `/home/kloros/rag_pipeline/docs/`

---

## 18. USER PREFERENCES & COMMUNICATION STYLE

### 18.1 System User
**User:** `kloros` (UID 1001) - AI voice assistant
**Dev User:** `claude_temp` - Passwordless sudo developer
**Communication:** Direct, technical, assume competence

### 18.2 Operational Philosophy
- "We do not disable, we diagnose" - Find root causes
- Prefer direct fixes over symlinks
- Run appropriate skills to maintain system alignment
- Avoid fabrication; provide thorough, real summaries
- Always ensure permissions are fixed after changes

---

## SUMMARY & NEXT STEPS

### What's Working ✅
1. Voice pipeline with hybrid STT and speaker ID
2. Memory systems with episodic-semantic storage
3. D-REAM evolutionary optimization (4 experiments)
4. PHASE accelerated testing framework
5. Complete orchestration & coordination
6. RAG with hybrid retrieval
7. Tool synthesis and evolution
8. Comprehensive logging and monitoring

### What Needs Attention 🟡
1. **SPICA Migration** - Complete domain refactoring
2. **Context Loss** - Increase max_ctx_chars in RAG
3. **Type Hierarchy** - Finalize SPICA base classes

### Recommended Actions
1. Complete SPICA type hierarchy (typing + inheritance)
2. Migrate all domains to SPICA derivatives
3. Implement CI gate for SPICA compliance
4. Re-enable D-REAM and PHASE tests
5. Increase RAG context window for better LLM performance
6. Monitor GPU isolation effectiveness
7. Track tool evolution convergence

---

**Document Version:** 1.0  
**Last Updated:** November 3, 2025  
**Analysis Tool:** Comprehensive codebase exploration (file globbing, grep, direct reads)  
**Total Files Analyzed:** 200+ core files across 72 directories  
**Analysis Coverage:** Very Thorough

