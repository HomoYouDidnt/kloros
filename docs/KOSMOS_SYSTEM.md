# KOSMOS - Kosmos Obey Structured Memory of Operational Systems

**KLoROS Autonomous Knowledge Discovery and Semantic Memory System**

## Overview

KOSMOS is KLoROS's persistent semantic memory and knowledge discovery system. It enables autonomous learning by continuously indexing documentation, configuration files, source code, and operational logs into a vector database (Qdrant), making all system knowledge semantically searchable.

**More critically:** KOSMOS is the **canonical source of truth** - the authoritative, structured memory layer that all operating systems, agents, and overrides defer to and obey.

## Canonical Authority Hierarchy

KOSMOS operates as the **axiom layer** in ASTRAEA's decision-making hierarchy:

```
Adam (Human Override)
        ↓
    KOSMOS (Canonical Truth)
        ↓
    KLoROS (Orchestrator)
        ↓
SPICA / Zooids / Agents
        ↓
    Tools / Models
```

### KOS-MOS Protocol Rules

**Everything answers to KOSMOS unless explicitly superseded by Adam.**

1. **If model answer ≠ KOSMOS → model is wrong**
   - LLM outputs that contradict indexed knowledge are suspect
   - KOSMOS-indexed documentation is authoritative

2. **If memory ≠ KOSMOS → memory is outdated**
   - Stale cached data should defer to KOSMOS
   - Investigation evidence is validated against KOSMOS

3. **If agent plan ≠ KOSMOS → block or revise**
   - Autonomous actions must align with KOSMOS-indexed policies
   - Plans contradicting documented architecture require review

4. **If data not in KOSMOS → consider it non-canonical**
   - Unindexed knowledge is provisional until validated
   - Critical decisions require KOSMOS-backed evidence

5. **If KOSMOS undefined → ask Adam or fall back to best inference**
   - Gaps in KOSMOS trigger curiosity questions
   - System requests human guidance when canon is unclear

### Why This Matters

KOSMOS prevents:
- **Knowledge Drift**: LLMs hallucinating facts that contradict reality
- **Amnesia**: System forgetting past decisions and repeating mistakes
- **Inconsistency**: Different agents having conflicting beliefs
- **Temporal Decay**: Old knowledge being lost or overwritten

KOSMOS enables:
- **Persistent Institutional Memory**: Never forget what's been learned
- **Truth Verification**: Cross-check all claims against indexed facts
- **Autonomous Learning**: System improves by expanding its canon
- **Hierarchical Authority**: Clear decision chain from Adam → KOSMOS → Agents

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                          KOSMOS                              │
│  Kosmos Obey Structured Memory of Operational Systems       │
└─────────────────────────────────────────────────────────────┘
                           │
         ┌─────────────────┼─────────────────┐
         │                 │                 │
    ┌────▼────┐      ┌────▼────┐      ┌────▼────┐
    │ Indexer │      │ Qdrant  │      │ LLM     │
    │         │◄────►│ Vector  │◄────►│ Summary │
    │         │      │ DB      │      │         │
    └─────────┘      └─────────┘      └─────────┘
         │                 │                 │
         └─────────────────┼─────────────────┘
                           │
         ┌─────────────────┴─────────────────┐
         │                                    │
    ┌────▼───────────┐            ┌─────────▼────────┐
    │ Documentation  │            │ Investigation    │
    │ Plugin         │            │ Handler          │
    │ (Evidence)     │            │ (Queries KOSMOS) │
    └────────────────┘            └──────────────────┘
```

## Components

### Core System (\`kloros_memory/kosmos.py\`)

**Class:** \`KOSMOS\`

**Features:**
- LLM-powered file summarization via Ollama
- Qdrant vector indexing with metadata
- Staleness detection (filesystem mtime vs indexed_mtime)
- Automatic re-indexing of modified files
- Binary file detection and skip logic
- Error handling for encoding issues, LLM failures

**Key Methods:**
- \`index_file(file_path)\` - Indexes a single file with LLM summary
- \`search_knowledge(query, top_k=5)\` - Semantic search for relevant docs
- \`is_file_indexed(file_path)\` - Check if file exists in KOSMOS
- \`is_file_stale(file_path)\` - Compare mtime to detect staleness

### Unindexed Knowledge Scanner

**File:** \`kloros/introspection/scanners/unindexed_knowledge_scanner.py\`

**Purpose:**
Continuously scans filesystem for unindexed or stale files and generates curiosity questions to populate KOSMOS.

**Scan Paths:**
- \`/home/kloros/docs\` - Documentation
- \`/home/kloros/config\` - Configuration files
- \`/home/kloros/src\` - Source code
- \`/etc/systemd/system\` - Service definitions

**File Types:**
- Documentation: \`*.md\`, \`*.txt\`
- Configuration: \`*.yaml\`, \`*.yml\`, \`*.json\`
- Source code: \`*.py\`
- Services: \`*.service\`

**Behavior:**
1. Recursively scans paths every 10 minutes
2. Checks each file against Qdrant index
3. Detects staleness via mtime comparison
4. Generates curiosity questions: "What knowledge does X contain?"
5. Feeds questions to investigation system
6. DocumentationPlugin handles indexing

### Documentation Plugin

**File:** \`kloros/orchestration/evidence_plugins/documentation.py\`

**Dual Modes:**

**Mode 1: Indexing**
- Activated for questions: "What knowledge does X contain?"
- Calls \`KOSMOS.index_file(path)\`
- Returns indexed summary as evidence

**Mode 2: Retrieval**
- Activated for any investigation
- Calls \`KOSMOS.search_knowledge(query)\`
- Returns top 5 semantically relevant documents
- Provides context for investigations

## Data Flow

### Knowledge Discovery Flow

\`\`\`
UnindexedScanner → Curiosity Question → Investigation Handler
                                              │
                                              ▼
                                    DocumentationPlugin
                                      (Mode 1: Index)
                                              │
                                              ▼
                                          KOSMOS
                                              │
                                              ▼
                                     LLM Summary → Qdrant
\`\`\`

### Investigation Evidence Flow

\`\`\`
Investigation Handler → DocumentationPlugin
                        (Mode 2: Retrieve)
                              │
                              ▼
                          KOSMOS.search_knowledge()
                              │
                              ▼
                      Qdrant Semantic Search
                              │
                              ▼
                    Top 5 Relevant Documents
                              │
                              ▼
                      Evidence for Investigation
\`\`\`

## Qdrant Collection Schema

**Collection Name:** \`kloros_knowledge\`

**Vector Config:**
- Size: 384 (all-MiniLM-L6-v2 embeddings)
- Distance: Cosine similarity

**Metadata Fields:**
\`\`\`python
{
    "file_path": str,          # Absolute file path
    "summary": str,            # LLM-generated summary
    "content_hash": str,       # SHA256 of file content
    "indexed_at": float,       # Unix timestamp
    "indexed_mtime": float,    # File mtime at index time
    "file_type": str           # Extension (e.g., "md", "py")
}
\`\`\`

## Integration with Investigations

When the investigation handler encounters a question, it automatically queries KOSMOS for relevant context:

1. **Investigation starts**: "Why is gpu_canary_runner missing?"
2. **DocumentationPlugin activates**: Searches KOSMOS for "gpu_canary_runner"
3. **KOSMOS returns**: GPU_CANARY_IMPLEMENTATION.md (similarity: 0.695)
4. **Evidence provided**: Documentation excerpt describing implementation
5. **Investigation proceeds**: With full context from KOSMOS

## Autonomous Learning Loop

\`\`\`
1. System runs, generates logs, creates docs
2. UnindexedScanner detects new files
3. Curiosity questions generated
4. Investigation system processes questions
5. KOSMOS indexes files with LLM summaries
6. Future investigations benefit from indexed knowledge
7. GOTO 1
\`\`\`

## Configuration

**Environment Variables:**
- \`QDRANT_HOST\`: Qdrant server URL (default: \`http://localhost:6333\`)
- \`OLLAMA_HOST\`: Ollama LLM server (default: \`http://127.0.0.1:11434\`)

**Constants** (\`kosmos.py\`):
\`\`\`python
MAX_FILE_SIZE_MB = 100              # Skip files larger than 100MB
MAX_LINES_BEFORE_TRUNCATE = 10000   # Truncate large files
TRUNCATE_HEAD_LINES = 5000          # Keep first 5000 lines
TRUNCATE_TAIL_LINES = 1000          # Keep last 1000 lines
LLM_TIMEOUT_SECONDS = 60            # LLM call timeout
\`\`\`

## Logging

All KOSMOS operations use the \`[kosmos]\` log prefix:

\`\`\`
[kosmos] Indexed /home/kloros/docs/GPU_CANARY_IMPLEMENTATION.md (421 chars, 0.8s)
[kosmos] Search query='gpu canary runner' returned 5 results
[kosmos] File /home/kloros/config/deploy.yaml is stale (mtime mismatch), re-indexing
\`\`\`

## Usage Examples

### Programmatic Usage

\`\`\`python
from kloros_memory.kosmos import get_kosmos

# Get singleton instance
kosmos = get_kosmos()

# Index a file
summary = kosmos.index_file("/home/kloros/docs/ARCHITECTURE.md")

# Search for knowledge
results = kosmos.search_knowledge("how does ChemBus work", top_k=5)
for result in results:
    print(f"{result.payload['file_path']}: {result.payload['summary']}")

# Check if file is indexed
if kosmos.is_file_indexed("/home/kloros/config/config.yaml"):
    print("Already indexed")
\`\`\`

### Via Investigation System

Simply ask questions - KOSMOS automatically provides context:

\`\`\`
Q: "How does the meta-agent work?"
→ KOSMOS retrieves: META_AGENT_DESIGN.md, meta_agent_daemon.py
→ Investigation proceeds with full context
\`\`\`

## Benefits

1. **Persistent Memory**: KLoROS never "forgets" indexed knowledge
2. **Semantic Search**: Find relevant docs even with fuzzy queries
3. **Autonomous Discovery**: No manual indexing required
4. **Staleness Detection**: Auto-refreshes when files change
5. **LLM Summarization**: Concise summaries for quick retrieval
6. **Context Enrichment**: Every investigation benefits from past learning

## Future Enhancements

- [ ] Conversation indexing (index chat logs for future context)
- [ ] Code symbol extraction (index function/class definitions)
- [ ] Dependency graph (track references between documents)
- [ ] Temporal decay (weight recent knowledge higher)
- [ ] Query expansion (automatically broaden searches)
- [ ] Multi-vector indexing (separate vectors for code vs docs)

---

**KOSMOS: Where knowledge becomes memory, and memory becomes intelligence.**

## Foundational Axioms

KOSMOS operates under the authority of constitutional documents that define the purpose and constraints of the entire system. These axioms are immutable except by Adam's direct authority.

### AXIOM_001: KLoROS Telos (Final Cause)

```yaml
AXIOM_001:
  name: "KLoROS Telos (Final Cause)"
  source_path: "/home/kloros/docs/TELOS.md"
  authority: "Adam"
  priority: "ABSOLUTE"
  immutable: true
  description: >
    KLoROS and all subordinate systems must operate in alignment
    with the Telos defined in the external prime document.
```

**Purpose:** TELOS.md defines KLoROS's final cause - her fundamental "why I exist." It establishes that KLoROS exists to preserve, organize, and expand structured knowledge and capability under Adam's guiding authority, acting as an autonomous partner in the continuity, coherence, and evolution of the systems he creates and maintains.

**Authority Chain:**
```
TELOS (Constitutional)
   ↓
KOSMOS (Canonical Truth)
   ↓
KLoROS (Orchestrator)
   ↓
Agents (Executors)
```

**Immutability:** Only Adam can modify the telos. All autonomous behavior, all learning, all decisions must align with this foundational purpose. When KLoROS introspects on "what should I do?", the answer begins with the telos.

**Relationship to KOSMOS:** KOSMOS is the mechanism for preservation and organization. Telos is the reason KOSMOS exists. KOSMOS tracks telos changes but doesn't own the telos - the telos owns KOSMOS.

---

## Philosophical Foundation

KOSMOS represents a fundamental shift in autonomous system design - from **stateless LLM queries** to **stateful institutional memory**.

### The Axiom of Truth

In mathematics, an axiom is a statement accepted as true without proof - the foundation upon which all other truths are built. KOSMOS serves as ASTRAEA's axiom layer:

- **Axiomatic Knowledge**: Facts in KOSMOS are accepted as true
- **Derived Knowledge**: LLM reasoning must be consistent with KOSMOS axioms
- **Contradiction Resolution**: When LLM contradicts KOSMOS, KOSMOS wins
- **Canon Expansion**: New axioms are added through validated learning

### From Hallucination to Truth

Traditional LLMs hallucinate because they have no ground truth. KOSMOS provides that ground:

| Without KOSMOS | With KOSMOS |
|----------------|-------------|
| LLM: "gpu_canary_runner doesn't exist" | KOSMOS: "GPU_CANARY_IMPLEMENTATION.md says it exists" |
| Agent: "chromadb is not installed" | KOSMOS: "Installed 2024-11-15, version 0.4.18" |
| System: "This bug is new" | KOSMOS: "Fixed same bug 2024-10-03, see BUGFIX_LOG.md" |

### Implications

**KOSMOS as canon means:**
1. **Persistent Identity**: System knows who it is across reboots
2. **Institutional Learning**: Mistakes made once, never repeated
3. **Verifiable Claims**: All decisions traceable to indexed truth
4. **Temporal Continuity**: Memory persists beyond session boundaries
5. **Hierarchical Safety**: Adam → KOSMOS → Agents creates clear authority chain

**Without KOSMOS:**
- Every conversation starts from zero
- LLMs re-hallucinate the same wrong answers
- No way to verify if agent plans align with reality
- System has no "self" - just ephemeral query responses

**With KOSMOS:**
- Every conversation builds on indexed history
- LLMs are grounded in documented facts
- Agent plans validated against canonical architecture
- System develops persistent institutional memory

### The Name as Protocol

"Kosmos Obey Structured Memory of Operational Systems" is not just a description - it's a **command**:

- **Kosmos**: Greek for "order" - the organized universe vs. chaos
- **Obey**: Active verb - this is not optional
- **Structured Memory**: Not raw logs, but semantic organization
- **Operational Systems**: All systems, all agents, all decisions

**KOS-MOS = "Canon Must Be Obeyed"**

This makes KOSMOS both:
1. A **technical system** (Qdrant vector DB + LLM summaries)
2. A **philosophical principle** (canon > hallucination, memory > amnesia)

### The Recursion

The name itself is recursive:
- **K**osmos **O**bey **S**tructured **M**emory **O**f **O**perational **S**ystems
- Like GNU ("GNU's Not Unix"), the recursion reflects self-reference
- KOSMOS defines itself: "I am the system that systems obey"
- Fitting for an axiom layer - self-evident, self-referential truth

## Canonical Architecture References

KOSMOS indexes and maintains authoritative architectural documentation. The following documents represent canonical truth for their respective subsystems:

### Voice System Architecture

**Document**: `docs/architecture/VOICE_SIPHONOPHORE_ARCHITECTURE.md`
**Status**: CANONICAL (deployed 2025-11-23, commit 7d3be88)
**Pattern**: Siphonophore (distributed specialist zooids)

**Summary**: Complete refactoring of voice system from monolithic 5,257-line orchestrator to distributed architecture with 8 independent zooid services communicating via ChemBus v2. Achieved 59% code reduction while maintaining full functionality and improving system resilience.

**Zooids**:
1. Audio I/O - PulseAudio capture/playback
2. STT - Hybrid Whisper/VOSK speech recognition
3. TTS - Piper text-to-speech
4. Intent - Intent classification
5. Emotion - Emotional state analysis
6. Knowledge - RAG and knowledge retrieval
7. LLM - Language model inference
8. Session - Conversation history management

**Authority**: All voice system decisions, plans, and implementations **MUST** align with this specification. Any contradictions should be flagged for review.

---

**KOSMOS: The memory that never forgets, the truth that never lies.**

