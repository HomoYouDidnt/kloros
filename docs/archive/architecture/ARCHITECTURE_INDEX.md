# KLoROS Architecture Documentation Index

## Overview
This folder contains comprehensive documentation of the KLoROS component architecture, technologies, and configurations.

## Documents

### 1. COMPONENT_ARCHITECTURE.md (533 lines, 21KB)
**Comprehensive architectural reference** - The main detailed document covering:

- **Section 1-2**: Speech-to-Text (STT) - Vosk + Whisper hybrid backend
- **Section 3**: Text-to-Speech (TTS) - Piper, XTTS, Kokoro, Mimic3 options
- **Section 4**: Voice Activity Detection (VAD) - Silero + two-stage pipeline
- **Section 5**: Embedding Models - BAAI/bge-small-en-v1.5 with fallbacks
- **Section 6**: LLM Inference - 4-mode Ollama setup (LIVE/THINK/DEEP/CODE)
- **Section 7**: Semantic Search & RAG - Hybrid retrieval with BM25+Vector
- **Section 8**: Additional AI/ML - Speaker ID, ToT, debate, uncertainty quantification
- **Section 9-13**: Dependencies, configs, architecture diagrams, environment variables

**Best for**: Deep understanding, architecture decisions, troubleshooting

### 2. COMPONENT_QUICK_REFERENCE.txt (213 lines, 7.5KB)
**Quick lookup reference** - Organized hierarchically covering:

- **Sections 1-8**: Component summary (one-liners + configs)
- **Key Files**: Where to find each component
- **Environment Variables**: Configuration options
- **Performance Characteristics**: Latency expectations
- **Known Constraints**: Tuning parameters
- **Multimodal Architecture**: GPU distribution
- **Failure Recovery**: Fallback chains

**Best for**: Quick lookups, quick reference during debugging, onboarding

## How to Use

### If you need to...

**Understand the overall system architecture:**
→ Read COMPONENT_ARCHITECTURE.md (full document) or QUICK_REFERENCE.txt (overview)

**Find a specific component (STT/TTS/VAD/etc):**
→ Use QUICK_REFERENCE.txt (Section 1-8) for location and quick details
→ Use COMPONENT_ARCHITECTURE.md for deep dive

**Find configuration or environment variables:**
→ QUICK_REFERENCE.txt has organized list
→ COMPONENT_ARCHITECTURE.md has detailed explanations

**Debug performance issues:**
→ Check QUICK_REFERENCE.txt "Performance Characteristics" section
→ Check COMPONENT_ARCHITECTURE.md "Performance Considerations" (Section 11)
→ Review "Known Constraints & Tuning" section

**Handle failures:**
→ See QUICK_REFERENCE.txt "Failure Recovery" section
→ Check COMPONENT_ARCHITECTURE.md for fallback chains and error handling

**Set up new models or swap components:**
→ Reference models_config.py location and COMPONENT_ARCHITECTURE.md Section 5/6

**Optimize for your hardware:**
→ Check "Multimodal Architecture" in QUICK_REFERENCE.txt
→ Review GPU distribution and CPU tasks

## Key Takeaways

### Architecture Philosophy
- **Hybrid approaches**: Combines fast (Vosk) with accurate (Whisper)
- **Multi-tier fallbacks**: Graceful degradation across all components
- **Modular design**: Easy component swapping without system redesign
- **Configurable**: Almost everything can be tuned via environment variables

### Current Stack
```
STT:       Vosk (fast) + Whisper (accurate) → Hybrid selection
TTS:       Piper (default) → Fallback to XTTS/Kokoro/Mimic3
VAD:       Silero (ML) + RMS dBFS (energy) → Two-stage pipeline
Embedder:  BAAI/bge-small-en-v1.5 → Fallbacks to MiniLM variants
LLM:       4-mode Ollama (LIVE/THINK/DEEP/CODE) on dual GPU
RAG:       Hybrid BM25 + Vector → RRF Fusion → Reranking
```

### Performance Profile
- STT: <500ms (hybrid), Vosk <100ms, Whisper 500-2000ms
- TTS: Real-time streaming (Piper) to slower but higher quality
- VAD: ~130ms total (30ms stage A + 100ms stage B)
- LLM: <1s (LIVE), 1-3s (THINK), 2-10s (DEEP)
- Embedder: 10-20ms single, 50-100ms batch

### Critical Configuration Files
1. `/home/kloros/src/config/models_config.py` - All model definitions
2. `/home/kloros/src/config/kloros.yaml` - System configuration
3. `/home/kloros/src/inference/config.py` - Inference topology
4. `/home/kloros/src/tts/config.yaml` - TTS routing

### Hardware Requirements
- **CPU**: Required for audio processing, VAD, embeddings fallback
- **GPU 0** (RTX 3060 12GB): LIVE/CODE modes
- **GPU 1** (GTX 1080 Ti 11GB): THINK/DEEP modes
- **RAM**: 16GB+ for comfortable operation with all models loaded

## Document Versioning

**Last Updated**: November 2, 2025
**Scope**: KLoROS source tree as of `/home/kloros/src/` (Nov 2, 2025)
**Based on**: Direct code inspection of all major components

## Related Documentation

Within the codebase:
- Component docstrings in respective files (best for implementation details)
- /home/kloros/src/KLOROS_CAPABILITIES_v2.2.md - Feature capabilities
- Individual component config files for specific tuning

## Questions or Updates?

If you find outdated information or want to add details:
1. Check the original source files listed in "Key Files" section
2. Verify against actual environment variables and configurations
3. Test assumptions with quick verification commands

## Quick Verification Commands

```bash
# Check installed versions
pip show vosk sentence-transformers faiss-cpu

# Verify model paths
echo $KLR_VOSK_MODEL_DIR
ls -la ~/KLoROS/models/

# Check Ollama availability
curl http://127.0.0.1:11434/api/tags

# List GPU availability
nvidia-smi

# Check environment variables
env | grep KLR_
env | grep OLLAMA_
```

---
**Document Structure**: Index → Quick Reference (browsing) → Full Architecture (reading) → Source Code (implementation)
