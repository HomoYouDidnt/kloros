# KLoROS Component Architecture Map

## Executive Summary
KLoROS is a sophisticated conversational AI system with a modular architecture that combines multiple specialized AI/ML components. The system uses a hybrid approach for robustness, combining fast local models with accurate cloud-capable models.

---

## 1. SPEECH-TO-TEXT (STT)

### Primary Backend: Vosk
- **Library**: `vosk==0.3.45`
- **Type**: Offline, local speech recognition
- **Location**: `/home/kloros/src/stt/vosk_backend.py`
- **Model Path**: `~/KLoROS/models/vosk/model` (environment variable: `KLR_VOSK_MODEL_DIR`)
- **Key Features**:
  - Fast, real-time transcription
  - Word-level confidence scores
  - KaldiRecognizer-based backend
  - PCM16 audio input format
  - Lazy initialization (shares model instances for memory efficiency)

### Secondary Backend: Whisper
- **Library**: `openai-whisper` (from requirements via transformers)
- **Type**: Transformer-based, more accurate speech recognition
- **Location**: `/home/kloros/src/stt/whisper_backend.py`
- **Model Sizes**: "tiny", "base", "small", "medium", "large-v2", "large-v3"
- **Default Size**: `"tiny"` (environment variable: `KLR_WHISPER_MODEL`)
- **Key Features**:
  - GPU/CPU auto-detection
  - Greedy decoding for speed (beam_size=1, best_of=1)
  - Optimized parameters for real-time performance:
    - No word timestamps (disabled for speed)
    - Compression ratio threshold: 2.4
    - Logprob threshold: -1.0
  - Fallback to CPU if GPU fails
  - 16kHz audio requirement (auto-resamples if needed)

### Hybrid STT Backend
- **Location**: `/home/kloros/src/stt/hybrid_backend.py`
- **Architecture**: 
  - Runs both Vosk (fast) and Whisper (accurate) in parallel
  - Uses fuzzy string matching (rapidfuzz) to compare results
  - Similarity threshold: 0.75 (configurable)
  - Confidence boost threshold: 0.9
- **Decision Logic**:
  - **High similarity (≥0.75)**: Accept whichever has higher confidence
  - **Low similarity**: Apply correction logic
  - **Whisper correction**: When Whisper confidence > 0.9 and acceptable by metrics
  - **Fallback to Vosk**: For responsiveness on ambiguous cases
- **Quality Metrics**:
  - Vosk acceptance: confidence ≥ 0.82 AND similarity ≥ 0.88
  - Whisper acceptance: logprob ≥ -0.75 OR compression_ratio ≤ 2.5
- **Correction Memory**: Maintains history of corrections for learning
- **Streaming Support**: Separate implementation in `vosk_backend_streaming.py`, `hybrid_backend_streaming.py`

### Integration Point
- `/home/kloros/src/kloros_voice.py` - Main voice loop that orchestrates STT

---

## 2. TEXT-TO-SPEECH (TTS)

### Primary Backend: Piper
- **Library**: CLI-based TTS via `piper` command
- **Type**: Fast, lightweight neural vocoder
- **Location**: `/home/kloros/src/tts/piper_backend.py`
- **Default Voice**: `"en_US-lessac-medium"` (environment variable: `KLR_PIPER_VOICE`)
- **Model Path**: `~/KLoROS/models/piper/glados_piper_medium.onnx`
- **Key Features**:
  - Supports both Python module and CLI fallback
  - Real-time streaming synthesis
  - Configurable sample rate (default: 22050 Hz)
  - ONNX model format
  - Lazy initialization via detect_piper()

### Secondary Backends

#### XTTS v2 (Multi-lingual)
- **Library**: `TTS` package (from Coqui TTS)
- **Model**: `"tts_models/multilingual/multi-dataset/xtts_v2"`
- **Location**: `/home/kloros/src/tts/adapters/xtts_v2.py`
- **Key Features**:
  - Speaker cloning capability (uses .wav reference files)
  - Multi-lingual support
  - Voice references: `~/KLoROS/voice_refs/active` (up to 32 samples)
  - Configurable speed and language
  - GPU device support

#### Kokoro
- **Model**: `kokoro-v0_19`
- **Location**: `/home/kloros/src/tts/adapters/kokoro.py`
- **Type**: CLI-based TTS
- **Key Features**:
  - Simple streaming interface
  - Dynamic voice selection (e.g., "en-us")
  - Automatic resampling to target sample rate

#### Mimic3
- **Type**: Traditional open-source TTS
- **Location**: `/home/kloros/src/tts/adapters/mimic3.py`
- **Default Voice**: `"en_US/vctk_low"`
- **Key Features**:
  - Binary backend (via shell command)
  - Voice selection support
  - Automatic audio format conversion

### TTS Router
- **Location**: `/home/kloros/src/tts/router.py`
- **Configuration**: YAML-based multi-backend routing
- **Default Order**: `["xtts_v2", "kokoro", "mimic3", "piper"]`
- **Intent-based Selection**: Can map specific intents to specific TTS engines
- **Enabled by Default**: Piper only (others disabled unless explicitly enabled)
- **Sample Rate Configuration**: 22050 Hz (configurable)

---

## 3. VOICE ACTIVITY DETECTION (VAD)

### Primary: Silero VAD
- **Library**: `torch`, `torchaudio` (via torch.hub)
- **Model**: `snakers4/silero-vad` (PyTorch)
- **Type**: Industry-standard ML-based VAD
- **Location**: `/home/kloros/src/audio/silero_vad.py`
- **Key Features**:
  - High accuracy with low false positive rate
  - Better noise rejection than WebRTC VAD
  - Real-time streaming optimized
  - Configurable thresholds (0.0-1.0)
  - State machine with attack/release times
  - Window sizes: 512, 1024, or 1536 samples
  - Sample rates: 8000 or 16000 Hz
- **Parameters**:
  - Default threshold: 0.5
  - Min speech duration: 250ms
  - Min silence duration: 100ms
  - Auto state reset capability

### Secondary: Frame-based RMS dBFS VAD
- **Location**: `/home/kloros/src/audio/vad.py`
- **Type**: Energy-based voice detection
- **Two-Stage Architecture**:
  - **Stage A**: Fast dBFS pre-gate (quick candidate detection)
  - **Stage B**: Silero refinement (accurate boundary detection)
- **Parameters**:
  - Stage A threshold: -28.0 dBFS
  - Stage B threshold: 0.60 probability
  - Attack time: 80ms (tolerates noise)
  - Release time: 600ms (tolerates natural pauses)
  - Min active duration: 300ms
  - Frame size: 30ms, hop: 10ms
  - Hysteresis margin: 2.0 dB
- **Output**: Segment timestamps in seconds with metadata

### Legacy: WebRTC VAD
- **Library**: `webrtcvad==2.0.10`
- **Location**: `/home/kloros/src/compat/webrtcvad.py`
- **Status**: Compatibility wrapper, superseded by Silero
- **Type**: C++ bindings to Google's WebRTC VAD

### Integration
- Combined in two-stage pipeline for optimal accuracy
- Prefers first segment for natural conversation flow
- Configurable preference (first vs. longest segment)

---

## 4. EMBEDDING MODELS (Semantic Search)

### Primary Embedder
- **Model**: `"BAAI/bge-small-en-v1.5"`
- **Library**: `sentence-transformers==5.1.0`
- **Type**: Small, fast bi-encoder optimized for semantic search
- **Embedding Dimension**: Variable (typically 384)
- **Source Location**: `/home/kloros/src/config/models_config.py` (line 32-37)
- **Configuration**: `/home/kloros/src/rag/embedders.py`

### Fallback Embedders
- `"all-MiniLM-L6-v2"` - Lightweight (6-layer distilled model)
- `"all-distilroberta-v1"` - RoBERTa-based compact model
- `"all-MiniLM-L12-v2"` - 12-layer MiniLM variant

### Advanced Embedder Features
- **DualEmbedder Class**: Separate encoders for queries vs. documents
  - Query-specific optimization
  - Document-specific optimization
  - Dimension truncation support
- **CachedEmbedder Class**: Query caching for repeated searches
  - In-memory cache (configurable size)
  - LRU eviction strategy
- **Device Selection**: Intelligent GPU selection (picks GPU with most free memory)
- **Batch Processing**: 32 queries/documents per batch
- **OOM Fallback**: Automatic downgrade to CPU on GPU failure

### ChromaDB Integration
- **Path**: `~/.kloros/chroma_data`
- **Embedder Used**: `"BAAI/bge-small-en-v1.5"`
- **Location**: `/home/kloros/src/chroma_adapters/` (multiple adapters)
- **Adapters**: 
  - ACE bullets (context engineering)
  - Artifacts management
  - Episodes tracking
  - Petri reports
  - Macro traces

### Vector Search
- **Library**: `faiss-cpu==1.12.0`
- **Type**: Facebook AI Similarity Search (CPU-only version)
- **Integration**: Used in RAG pipeline for fast semantic search
- **Location**: `/home/kloros/src/kloros_voice.py` (dynamic import)

---

## 5. LLM INFERENCE

### Configuration Architecture
- **Source**: `/home/kloros/src/config/models_config.py` (lines 58-120)
- **SSOT Integration**: "Single Source of Truth" loader system
- **Fallback**: Environment variables if SSOT unavailable

### Multi-Mode LLM Strategy
The system supports 4 distinct inference modes, each with its own model and Ollama instance:

#### Mode 1: LIVE (Immediate Response)
- **URL**: `http://127.0.0.1:11434` (default Ollama)
- **Model**: `"qwen2.5:7b-instruct-q4_K_M"`
- **Purpose**: Fast, conversational responses
- **Quantization**: Q4_K_M (4-bit)
- **Typical Latency**: <1 second

#### Mode 2: THINK (Deep Analysis)
- **URL**: `http://127.0.0.1:11435`
- **Model**: `"deepseek-r1:7b"`
- **Purpose**: Extended reasoning with chain-of-thought
- **Type**: Reasoning-optimized model
- **Budget**: Longer token allowances

#### Mode 3: DEEP (Async Background)
- **URL**: `http://127.0.0.1:11436`
- **Model**: `"qwen2.5:14b-instruct-q4_0"`
- **Purpose**: Thorough background analysis
- **Size**: Larger (14B parameters)
- **Type**: Async task execution

#### Mode 4: CODE (Code Generation)
- **URL**: `http://127.0.0.1:11434` (shares GPU 0 with LIVE)
- **Model**: `"qwen2.5-coder:32b"`
- **Purpose**: Specialized code generation
- **Size**: Large (32B parameters)
- **Type**: Code/technical task optimization

### Ollama Configuration
- **Base URL**: `http://127.0.0.1:11434` (OLLAMA_HOST environment variable)
- **Backend**: Local Ollama inference engine
- **Multi-GPU Setup**: 
  - GPU 0 (RTX 3060): Judge/LIVE/CODE models
  - GPU 1 (GTX 1080 Ti): Performer models
- **Alternative vLLM Setup** (if available):
  - Judge Server: `http://127.0.0.1:8001` (Qwen2.5-14B-Instruct-AWQ)
  - Performer Server: `http://127.0.0.1:8002` (local Ollama models)
  - KV-cache management with 256 MiB per session limit
  - Prefix caching optimization

### Default Model
- **Fallback**: `"llama3.1:8b"` (if SSOT unavailable)
- **Environment Variable**: `OLLAMA_MODEL`

---

## 6. SEMANTIC SEARCH & RAG PIPELINE

### RAG System
- **Location**: `/home/kloros/src/simple_rag.py`
- **Type**: Lightweight, dependency-minimal RAG
- **Data Formats Supported**:
  - NPZ bundles (embeddings + metadata)
  - Parquet, CSV, JSON metadata
  - NumPy arrays for embeddings
- **Verification**: SHA256 bundle integrity checking

### Hybrid Retrieval
- **Location**: `/home/kloros/src/rag/hybrid_retriever.py`
- **Components**:
  - **BM25 Full-text Search** (traditional keyword search)
    - K1 = 1.5 (term frequency saturation)
    - B = 0.75 (length normalization)
    - K_bm25: 50 results
  - **Vector Semantic Search** (neural embedding-based)
    - K_vec: 12 results
    - Model: BAAI/bge-small-en-v1.5
  - **Reciprocal Rank Fusion** (RRF) merging
    - RRF constant (k): 60
  - **Reranking** (optional cross-encoder refinement)
    - Model: null (heuristic by default, can use cross-encoder)
    - Top-K after reranking: 6 results
- **Configuration**: `/home/kloros/src/config/kloros.yaml` (lines 183-214)

### Advanced RAG Features
- **Query Caching**: Enabled by default
  - Cache size: 1000 queries
  - Reduces redundant embedding computation
- **Self-RAG**: System introspection capability
  - Allowed roots: `~/.kloros`, `/home/kloros/src`, `/home/kloros`
  - Max file size: 128 KB
  - Secret redaction enabled
  - Live system state inclusion
- **Diversity**: Max 2 chunks per document (prevents redundancy)

### Reranking
- **Location**: `/home/kloros/src/rag/reranker.py`
- **Heuristic Mode**: Length + keyword relevance scoring
- **Cross-Encoder Mode**: Optional neural reranking
  - Model: "cross-encoder/ms-marco-MiniLM-L-6-v2" (if enabled)
- **Span Extraction**: Best answer span identification

### Ingest Pipeline
- **Cleaner**: Text normalization and code block removal
- **Chunker**: Multiple strategies
  - Fixed-size chunking
  - Sentence-based splitting
  - Paragraph-based splitting
  - Smart chunking (semantic boundaries)
- **Location**: `/home/kloros/src/rag/ingest/`

---

## 7. ADDITIONAL AI/ML COMPONENTS

### Speaker Identification
- **Model**: `"speechbrain/spkrec-ecapa-voxceleb"`
- **Type**: ECAPA-TDNN speaker embedding model
- **Purpose**: Speaker diarization and identification
- **Location**: Referenced in `/home/kloros/src/config/models_config.py` (line 179)

### Advanced Cognitive Features
- **Tree of Thought (ToT)**: Beam search reasoning
  - Beam width: 3
  - Max depth: 3
- **Multi-Agent Debate**: Consensus-based reasoning
- **Value of Information**: Decides whether additional information seeking is worth cost
- **Safety Value Learning**: Frequentist/Bayesian risk assessment
- **Provenance Tracking**: Source attribution for responses

### Quality Assurance Components
- **PETRI**: Petri-net based security/safety testing
  - Risk threshold: 0.3
  - Conservative policy (any probe failure = unsafe)
- **Uncertainty Quantification**: Confidence estimation
  - Base: 0.5, Agreement weight: 0.25, Retrieval weight: 0.20
  - Contradiction penalty: -0.30, Verifier weight: 0.35
- **ACE (Agentic Context Engineering)**: 
  - Bullet retrieval: K=12
  - Max bullets: 24 per domain, 8 per task
  - Cosine similarity threshold: 0.88
  - Min evidence score: 0.6

---

## 8. DEPENDENCY SUMMARY

### Core Dependencies
```
vosk==0.3.45                      # Speech-to-text
openai-whisper                    # (via transformers)
sentence-transformers==5.1.0      # Embeddings
sounddevice==0.5.2                # Audio capture
webrtcvad==2.0.10                 # Legacy VAD
faiss-cpu==1.12.0                 # Vector similarity
torch==2.8.0                       # ML backend
transformers==4.53.0              # Model loading
numpy==2.3.3                       # Array operations
requests==2.32.5                  # HTTP client
PyYAML==6.0.2                      # Config files
```

### Optional/Feature-Specific
- `scipy` - Audio resampling (Whisper)
- `librosa` - Audio processing (TTS adapters)
- `soundfile` - Audio I/O (TTS adapters)
- `pandas` - Parquet support (RAG)
- `rapidfuzz` - String matching (Hybrid STT)
- `piper` - TTS CLI backend
- `TTS` - Coqui TTS for XTTS v2

---

## 9. CONFIGURATION FILES

### Main Configuration
- **Path**: `/home/kloros/src/config/kloros.yaml`
- **Coverage**: RAG, ACE, PETRI, RA³, D-REAM, brainmods, governance, caching

### Model Configuration
- **Path**: `/home/kloros/src/config/models_config.py`
- **Type**: Python module with getters (environment variable fallback)

### Inference Configuration
- **Path**: `/home/kloros/src/inference/config.py`
- **Coverage**: vLLM server topology, KV-cache budgeting, telemetry

### TTS Configuration
- **Path**: `/home/kloros/src/tts/config.yaml`
- **Contains**: Router settings, voice assignments

---

## 10. ARCHITECTURE DIAGRAM

```
┌─────────────────────────────────────────────────────────────┐
│                    KLOROS VOICE LOOP                         │
│              /home/kloros/src/kloros_voice.py                │
└────────────────────┬────────────────────────────────────────┘
                     │
        ┌────────────┼────────────┐
        │            │            │
        ▼            ▼            ▼
    ┌────────┐  ┌────────┐  ┌──────────┐
    │ AUDIO  │  │ VAD    │  │ STT      │
    │ CAPTURE│  │PIPELINE│  │ PIPELINE │
    └────────┘  └────────┘  └──────────┘
        │            │            │
        │       ┌────┴────┐       │
        │       ▼         ▼       │
        │    Silero   RMS dBFS    │
        │              VAD        │
        │                         │
        │       ┌─────────────────┤
        │       ▼                 ▼
        │   ┌──────────┐   ┌──────────┐
        │   │  Vosk    │   │ Whisper  │
        │   │ (Fast)   │   │(Accurate)│
        │   └──────┬───┘   └────┬─────┘
        │          │            │
        │          └────┬───────┘
        │               ▼
        │         ┌──────────────┐
        │         │ Hybrid Logic │
        │         │(Fuzzy Match) │
        │         └──────┬───────┘
        │                │
        ▼                ▼
    ┌──────────────────────────────┐
    │   LLM INFERENCE (Ollama)     │
    │  4 Modes (LIVE/THINK/DEEP/CODE)
    │   Various Models & GPUs      │
    └────────────┬─────────────────┘
                 │
        ┌────────┴──────────┐
        │                   │
        ▼                   ▼
    ┌─────────┐        ┌──────────────┐
    │ RAG     │        │ TTS Router   │
    │ Pipeline│        │              │
    └────┬────┘        └──────┬───────┘
         │                    │
    ┌────┴──────────┐     ┌───┴─────────────┐
    │               │     │     │      │    │
    ▼               ▼     ▼     ▼      ▼    ▼
┌─────────┐   ┌────────┐ Piper XTTS Kokoro Mimic3
│ Embedder│   │BM25 +  │
│ (BAAI)  │   │Vector  │
└─────────┘   │Search  │
              │+ Rerank│
              └────────┘
```

---

## 11. PERFORMANCE CONSIDERATIONS

### STT Trade-offs
- **Vosk**: <100ms latency, acceptable accuracy, offline
- **Whisper**: 500-2000ms latency, high accuracy, requires more computation
- **Hybrid**: Optimal for responsive, accurate real-time transcription

### VAD Trade-offs
- **WebRTC VAD**: Fast but prone to false positives
- **RMS dBFS (Stage A)**: Quick pre-filtering, handles silence/noise
- **Silero (Stage B)**: Accurate but computationally heavier
- **Two-stage**: Best balance (speed + accuracy)

### Embedding Trade-offs
- **BAAI/bge-small-en-v1.5**: 384-dim, fast, good quality
- **Fallbacks**: Even lighter for edge cases
- **Cache**: Avoids re-embedding repeated queries

### LLM Trade-offs
- **LIVE (Qwen 7B)**: <1s response, conversational
- **THINK (DeepSeek-R1 7B)**: Reasoning-focused
- **DEEP (Qwen 14B)**: Background analysis
- **CODE (Qwen-Coder 32B)**: Technical specialization

---

## 12. KNOWN ISSUES & COMMENTS

### From Source Code
- VAD release time increased from 200ms to 600ms to tolerate natural pauses
- VAD attack time increased from 50ms to 80ms for noise resilience
- Whisper configured for speed (greedy decoding, no word timestamps)
- Vosk confidence calculation averages word-level confidences
- Hybrid STT maintains correction history for learning
- RAG bundles require SHA256 verification for integrity
- Chrome DB available but RAG is primary retrieval method

---

## 13. ENVIRONMENT VARIABLES (Key Ones)

```bash
KLR_VOSK_MODEL_DIR         # Path to Vosk model
KLR_WHISPER_MODEL          # Whisper model size (default: "tiny")
KLR_PIPER_VOICE            # Piper voice model
KLR_EMBEDDER_MODEL         # Embedder model name
OLLAMA_MODEL               # Default Ollama model
OLLAMA_HOST                # Ollama API base URL
OLLAMA_THINK_URL           # THINK mode Ollama URL
OLLAMA_DEEP_URL            # DEEP mode Ollama URL
OLLAMA_CODE_URL            # CODE mode Ollama URL
WHISPER_CACHE_DIR          # Whisper model download location
CUDA_VISIBLE_DEVICES       # GPU selection
KLR_INPUT_IDX              # Audio input device index
KLR_WAKE_PHRASES           # Custom wake word variants
KLR_MODEL_MODE             # Inference mode (live/think/deep/code)
```

---

## CONCLUSION

KLoROS employs a sophisticated multi-component architecture that balances speed, accuracy, and resource efficiency. The use of hybrid approaches (Vosk+Whisper STT, two-stage VAD, hybrid RAG retrieval) and multiple inference modes enables responsive, high-quality conversational AI. The modular design allows for easy swapping of components and graceful degradation when preferred components are unavailable.

Key architectural strength: **Intelligent fallback chains and adaptive routing** ensure the system remains functional across various hardware and load conditions.
