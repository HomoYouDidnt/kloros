# KLoROS System Documentation Index

**Analysis Completed:** November 3, 2025  
**Comprehensiveness:** Very Thorough (200+ files, 72 directories)

---

## PRIMARY ANALYSIS DOCUMENTS (Just Created)

### 1. **KLOROS_SYSTEM_ANALYSIS_COMPREHENSIVE.md** (997 lines, 30KB)
**Best For:** Complete understanding of entire system  
**Contents:**
- Detailed breakdown of all 5 subsystems (KLoROS, ASTRAEA, D-REAM, PHASE, SPICA)
- Complete architecture documentation for all major components
- Integration points and data flows
- Configuration system details
- Known issues and areas for improvement
- Recommended next steps

**Use When:** You need to understand how something works in detail, debug system behavior, or plan architecture changes.

### 2. **KLOROS_ARCHITECTURE_QUICK_SUMMARY.txt** (252 lines)
**Best For:** Quick reference and executive overview  
**Contents:**
- System overview and subsystem status
- Memory systems at a glance
- Orchestration & control systems
- Active experiments and metrics
- Key configuration values
- Known issues and completion status
- Recommended next steps

**Use When:** You need a quick understanding, status check, or want to find something fast.

---

## EXISTING COMPREHENSIVE DOCUMENTATION

### System & Architecture
- **COMPONENT_ARCHITECTURE.md** (533 lines, 21KB)
  - Deep dive into STT, TTS, VAD, embedders, LLM inference, RAG
  - Performance characteristics and constraints
  - Detailed configuration documentation

- **COMPONENT_QUICK_REFERENCE.txt** (213 lines, 7.5KB)
  - One-liner components with configuration
  - Quick lookup for environment variables
  - Performance expectations
  - Failure recovery chains

- **ARCHITECTURE_INDEX.md** 
  - Navigation guide for architecture documents
  - How to use the documentation
  - Document versioning

### Core Subsystems
- **ASTRAEA_SYSTEM_THESIS.md** (in `/home/kloros/docs/`)
  - Complete ASTRAEA architectural thesis
  - D-REAM evolution engine details
  - Tool evolution (new breakthrough)
  - PHASE adaptive testing
  - Safety & governance framework
  - Current status and roadmap

- **SYSTEM_ARCHITECTURE_OVERVIEW.md** (in `/home/kloros/docs/`)
  - Critical system overview
  - Core evolution systems (D-REAM, PHASE)
  - LLM context loss issues
  - Memory systems architecture
  - Tool synthesis details
  - File ownership and systemd services

- **SPICA_ARCHITECTURE.md**
  - SPICA core principle
  - Template LLM design
  - Migration checklist (60% complete)
  - SPICA derivatives structure
  - Current status (tests disabled)

### Implementation & Operation
- **AUTOMATION_GUIDE.md** (in `/home/kloros/src/dream/`)
  - D-REAM automation procedures
  - Evolution cycle orchestration

- **OBSERVER_ORCHESTRATOR_INTEGRATION.md** (in `/home/kloros/docs/`)
  - Observer infrastructure details
  - Integration patterns

- **AUTONOMOUS_LOOP_INTEGRATION.md** (in `/home/kloros/docs/`)
  - Autonomous operation patterns
  - Self-improvement loops

### Memory & Persistence
- **MEMORY_SYSTEM_GUIDE.md** (in `/home/kloros/docs/`)
  - Episodic-semantic memory architecture
  - Implementation details
  - Configuration and tuning

- **CHROMADB_INTEGRATION_COMPLETE.md**
  - ChromaDB integration status
  - Knowledge base structure

---

## HOW TO USE THIS DOCUMENTATION

### If you need to...

**Understand the overall system architecture:**
→ Start with `KLOROS_ARCHITECTURE_QUICK_SUMMARY.txt` (5 min read)  
→ Then read `KLOROS_SYSTEM_ANALYSIS_COMPREHENSIVE.md` (full deep dive)

**Find a specific component (STT/TTS/VAD/etc):**
→ Use `COMPONENT_QUICK_REFERENCE.txt` for location  
→ Use `COMPONENT_ARCHITECTURE.md` for technical details  
→ Check source code in `/home/kloros/src/`

**Debug a specific subsystem:**
→ Find in `KLOROS_SYSTEM_ANALYSIS_COMPREHENSIVE.md` section (indexed by subsystem)  
→ Check relevant source files listed in documentation  
→ Cross-reference with logs in `/home/kloros/logs/`

**Understand D-REAM evolution:**
→ Read `ASTRAEA_SYSTEM_THESIS.md` section 2-4  
→ Check active experiments status in metrics section  
→ Review experiment configs in `/home/kloros/src/dream/config/`

**Understand PHASE testing:**
→ Read `KLOROS_SYSTEM_ANALYSIS_COMPREHENSIVE.md` section 5  
→ Check domain implementations in `/home/kloros/src/phase/domains/`

**Understand SPICA template:**
→ Read `SPICA_ARCHITECTURE.md`  
→ Review migration status and checklist  
→ Check base implementation in `/home/kloros/src/spica/base.py`

**Configure the system:**
→ See "Configuration System" section (section 11)  
→ Check `/home/kloros/.kloros_env` for current values  
→ Review `/home/kloros/src/config/` for model and routing configs

**Fix an issue:**
→ Check "Known Issues & Areas Needing Work" (section 15)  
→ Search issue name in comprehensive analysis  
→ Cross-reference with source code

**Understand memory systems:**
→ Read section 2 of comprehensive analysis  
→ Check `/home/kloros/src/kloros_memory/` directory  
→ Review `MEMORY_SYSTEM_GUIDE.md`

**Plan improvements:**
→ Read section 15 (known issues)  
→ Review section 18 (recommended next steps)  
→ Check D-REAM active experiments for optimization opportunities

---

## DOCUMENT LOCATIONS ON DISK

```
/home/kloros/
├── KLOROS_SYSTEM_ANALYSIS_COMPREHENSIVE.md  ← Start here for deep dive
├── KLOROS_ARCHITECTURE_QUICK_SUMMARY.txt    ← Start here for quick ref
├── KLOROS_DOCUMENTATION_INDEX.md            ← This file
├── ARCHITECTURE_INDEX.md
├── COMPONENT_ARCHITECTURE.md
├── COMPONENT_QUICK_REFERENCE.txt
├── SPICA_ARCHITECTURE.md
├── ASTRAEA_SYSTEM_THESIS.md                 ← Also in /docs/
│
├── docs/
│   ├── ASTRAEA_SYSTEM_THESIS.md
│   ├── SYSTEM_ARCHITECTURE_OVERVIEW.md
│   ├── MEMORY_SYSTEM_GUIDE.md
│   ├── OBSERVER_ORCHESTRATOR_INTEGRATION.md
│   ├── AUTONOMOUS_LOOP_INTEGRATION.md
│   └── HEMISPHERIC_ARCHITECTURE.md
│
├── src/
│   ├── kloros_voice.py (183KB)              ← Main voice pipeline
│   ├── dream/
│   │   ├── AUTOMATION_GUIDE.md
│   │   ├── complete_dream_system.py
│   │   └── ...
│   ├── phase/
│   │   └── domains/
│   ├── spica/
│   │   └── base.py
│   ├── kloros_memory/
│   ├── reasoning/
│   ├── rag/
│   ├── kloros/orchestration/
│   └── ...
│
└── .kloros/
    └── memory.db                            ← Runtime state
```

---

## KEY FACTS AT A GLANCE

### What's Complete (100%)
- KLoROS voice pipeline with hybrid STT
- Memory systems (episodic-semantic + idle reflection)
- D-REAM evolution engine (4 active experiments)
- PHASE testing framework (paused for SPICA)
- Orchestration & scheduling
- RAG with hybrid retrieval
- Tool synthesis (50+ tools)
- Observer & curiosity system

### What's In Progress (60%)
- SPICA migration (type hierarchy TBD)

### What's Planned
- Camera integration
- Physical embodiment
- Greenhouse automation

### Metrics (October 2025)
- 14,125+ evolution evaluations
- 496 tool evolution tests (0% failure)
- 4 active D-REAM experiments
- 3 tools under evolution
- 50+ introspection tools
- 7.1 MB telemetry collected

### Critical Configuration
```
Audio:  CMTECK USB mic, 4.0x gain, hybrid STT
LLM:    qwen2.5 (live), deepseek-r1 (think), qwen-coder (code)
GPU:    RTX 3060 (LIVE/CODE), GTX 1080 Ti (THINK/DEEP)
Memory: SQLite WAL mode, ChromaDB
Window: PHASE & GPU maintenance 03:00-07:00 America/New_York
```

### Known Issues to Address
1. **SPICA Type Hierarchy** - Tests disabled, needs finalization
2. **Context Loss** - max_ctx_chars=3000 should be 8000
3. **RAG Expansion** - Consider larger knowledge base

### Recommended Next Actions
1. Complete SPICA type hierarchy and CI gate
2. Increase RAG context window
3. Monitor tool evolution convergence
4. Re-enable D-REAM/PHASE tests after SPICA
5. Track GPU isolation effectiveness
6. Plan camera integration

---

## QUICK REFERENCE

### Main Entry Points
- **Voice Pipeline:** `/home/kloros/src/kloros_voice.py`
- **D-REAM Evolution:** `/home/kloros/src/dream/complete_dream_system.py`
- **Orchestration:** `/home/kloros/src/kloros/orchestration/coordinator.py`
- **RAG Engine:** `/home/kloros/src/simple_rag.py`

### Critical Directories
- Config: `/home/kloros/src/config/`
- Models: `/home/kloros/models/`
- Runtime: `/home/kloros/.kloros/`
- Logs: `/home/kloros/logs/`
- Artifacts: `/home/kloros/artifacts/dream/`

### Important Files
- Environment: `/home/kloros/.kloros_env` (22 variables)
- Model configs: `/home/kloros/src/config/models_config.py`
- Routing: `/home/kloros/src/config/routing.py`
- Tools: `/home/kloros/src/introspection_tools.py` (166KB)
- Memory: `/home/kloros/.kloros/memory.db`

### Useful Commands
```bash
# Check system status
grep -E "✅|🟡|📅" /home/kloros/KLOROS_ARCHITECTURE_QUICK_SUMMARY.txt

# View current config
source /home/kloros/.kloros_env && env | grep KLR_

# Check D-REAM status
ls -la /home/kloros/var/dream/

# Monitor memory system
sqlite3 ~/.kloros/memory.db "SELECT COUNT(*) FROM events;"

# View logs
tail -f /home/kloros/logs/dream/runner.log
```

---

## VERSION INFORMATION

**Analysis Date:** November 3, 2025  
**Analysis Scope:** Complete KLoROS system  
**Files Analyzed:** 200+ Python files across 72 directories  
**Thoroughness:** Very Thorough  

**System Status Summary:**
- ✅ 7 major subsystems fully operational
- 🟡 1 subsystem in progress (SPICA, 60%)
- 📅 3 subsystems planned (camera, embodiment, greenhouse)
- 🚀 Ready for continued evolution and improvement

---

## GETTING HELP

If you can't find what you're looking for:

1. **Check section 11 (Configuration)** in comprehensive analysis
2. **Check section 15 (Known Issues)** in comprehensive analysis
3. **Search for your topic** in `/home/kloros/docs/` or `/home/kloros/src/`
4. **Review source code** in relevant `/home/kloros/src/` subdirectory
5. **Check logs** in `/home/kloros/logs/` for runtime details

---

**Generated:** November 3, 2025  
**By:** Comprehensive codebase analysis tool  
**Next Review:** When SPICA migration completes or major changes occur
