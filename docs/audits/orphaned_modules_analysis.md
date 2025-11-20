# KLoROS Orphaned Modules Analysis

**Date**: 2025-11-20
**Total Orphaned**: 35 modules (no imports found in src/)

---

## Category A: INTEGRATE ✅
**High-value modules that should be wired into the active system**

| Module | Size | Files | Purpose | Priority |
|--------|------|-------|---------|----------|
| **mcp** | 164K | 6 | Model Context Protocol - system introspection & capability awareness | **CRITICAL** |
| **self_heal** | 260K | 18 | Event-driven self-healing: detect→triage→fix→validate→learn | **CRITICAL** |
| **tool_synthesis** | 336K | 26 | Autonomous tool creation and capability expansion | **HIGH** |
| **dev_agent** | 260K | 22 | Coding agent for surgical code repair and synthesis | **HIGH** |
| **scholar** | 60K | 11 | Report generation with citations and TUMIX reviewers | **HIGH** |
| **meta_cognition** | 72K | 5 | Conversational self-awareness and dialogue quality monitoring | **HIGH** |
| **petri** | 92K | 7 | Safety sandbox for tool execution (PETRI nets) | **HIGH** |
| **dream_lab** | 140K | 9 | Chaos/failure injection testing for resilience | **MEDIUM** |
| **ace** | 60K | 5 | Agentic Context Engineering - self-improving context hints | **MEDIUM** |
| **stt** | 200K | 13 | Speech-to-text processing (Vosk/Whisper backends) | **MEDIUM** |
| **c2c** | 36K | 4 | Cache-to-cache semantic communication between LLM subsystems | **MEDIUM** |
| **core** | 84K | 4 | Conversation flow and dialogue management | **MEDIUM** |

**Total**: 12 modules, ~1.8MB, 145 .py files

---

## Category B: INVESTIGATE/DEPRECATE ⚠️
**Modules requiring investigation before decision**

### B1: Potentially Redundant/Overlapping
| Module | Size | Files | Purpose | Investigation Needed |
|--------|------|-------|---------|----------------------|
| **toolforge** | 40K | 5 | Tool management system | May overlap with tool_synthesis |
| **tool_curation** | 28K | 2 | Tool curation system | May overlap with tool_synthesis |
| **selfcoder** | 20K | 3 | Self-coding capabilities | May overlap with dev_agent |
| **speaker** | 56K | 5 | Voice output/TTS | Check if superseded by existing TTS |
| **voice** | 12K | 2 | Voice processing | May overlap with stt/speaker |

### B2: Legacy/Deprecated
| Module | Size | Files | Notes |
|--------|------|-------|-------|
| **dream_legacy_domains** | 164K | 7 | Contains "DEPRECATED_README.md" - legacy D-REAM |
| **compat** | 24K | 2 | Compatibility layer - may be temporary |

### B3: Unclear Purpose (Need Deep Dive)
| Module | Size | Files | Notes |
|--------|------|-------|-------|
| **ra3** | 84K | 6 | Unknown acronym/purpose |
| **tumix** | 72K | 8 | Unknown purpose |
| **cognition** | 40K | 3 | May overlap with meta_cognition |
| **governance** | 56K | 4 | Policy/oversight layer? |
| **logic** | 28K | 2 | Logic system component |
| **common** | 20K | 3 | Generic utilities (may be redundant) |
| **routing** | 20K | 2 | Message/request routing |
| **reporting** | 20K | 2 | System reporting |
| **observer** | 8K | 1 | Observation/monitoring |
| **gpu_workers** | 8K | 1 | GPU worker management |
| **scripts** | 8K | 1 | Utility scripts |
| **style** | 40K | 6 | Code style/formatting |
| **ux** | 24K | 2 | User experience layer |
| **experiments** | 20K | 1 | Experimental/research code |

**Total**: 22 modules, ~784K, 64 .py files

---

## Category C: REMOVE 🗑️
**Empty directories with no Python files**

| Module | Size | Files | Action |
|--------|------|-------|--------|
| **synthesized_tools** | 4K | 0 | DELETE - empty directory |
| **vad** | 4K | 0 | DELETE - empty directory (VAD = Voice Activity Detection, likely moved elsewhere) |

**Total**: 2 modules, 8K, 0 .py files

---

## Integration Priority

### Phase 1: Critical Safety & Infrastructure (Week 1)
1. **mcp** - Enable system introspection first
2. **self_heal** - Core resilience capability
3. **petri** - Safety sandbox before enabling other tools

### Phase 2: Core Capabilities (Week 2)
4. **tool_synthesis** - Enable autonomous capability expansion
5. **dev_agent** - Self-repair coding capabilities
6. **meta_cognition** - Conversational self-awareness

### Phase 3: Enhanced Features (Week 3)
7. **scholar** - Report generation
8. **dream_lab** - Chaos testing infrastructure
9. **ace** - Context engineering
10. **stt** - Speech-to-text (if voice interaction needed)
11. **c2c** - Semantic communication
12. **core** - Conversation flow (if not already integrated)

---

## Next Steps

1. **Immediate Actions**:
   - Delete `synthesized_tools/` and `vad/` (empty directories)
   - Mark `dream_legacy_domains/` as deprecated in docs
   - Create integration tickets for Category A modules

2. **Investigation Required** (Category B):
   - Deep dive into each B3 module to understand purpose
   - Check for feature overlap with active modules
   - Consult git history for context on why they're orphaned
   - Decision matrix: integrate, deprecate, or archive

3. **Documentation Updates**:
   - Update capabilities.yaml to mark orphaned modules as `enabled: false`
   - Add integration plan to project roadmap
   - Document deprecation decisions

4. **Technical Debt**:
   - ~145 Python files (~1.8MB of high-value code) sitting idle
   - Represents significant capability gap in current system
   - MCP and self_heal are particularly critical gaps

---

## Gemini's Diagnostic Confirmation

Gemini 3's analysis correctly identified that many "enabled" modules in capabilities.yaml have no actual imports:
- ✅ Confirmed: scholar_pack, chroma_adapters, inference, test_discovery_module
- ✅ Our analysis found 35 total orphaned modules
- ✅ Many are high-value features (self-healing, tool synthesis, MCP)

**Root Cause**: Modules exist on disk and are registered in capabilities.yaml but were never wired into the import graph or startup sequence.
