# KLoROS Capability Registry & Curiosity System

Complete self-awareness infrastructure enabling KLoROS to accurately know what she can and cannot do, with automatic question generation to drive curiosity.

## System Overview

```
┌─────────────────────────────────────────────────────────────────────┐
│                      KLOROS SELF-AWARENESS STACK                     │
├─────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  ┌─────────────────┐        ┌──────────────────┐                   │
│  │ capabilities_   │  ───▶  │  capability_     │                   │
│  │ enhanced.yaml   │        │  evaluator.py    │                   │
│  │                 │        │                  │                   │
│  │ • Preconditions │        │ • Health checks  │                   │
│  │ • Health checks │        │ • Precondition   │                   │
│  │ • Cost tracking │        │   validation     │                   │
│  │ • Provides list │        │ • self_state.json│                   │
│  └─────────────────┘        └────────┬─────────┘                   │
│                                      │                              │
│                                      │                              │
│               ┌──────────────────────┼──────────────────────────┐   │
│               │                      │                          │   │
│               │                      ▼                          │   │
│       ┌───────▼──────────┐   ┌──────────────┐    ┌────────────▼┐  │
│       │ affordance_      │   │ curiosity_   │    │ self_       │  │
│       │ registry.py      │   │ core.py      │    │ portrait.py │  │
│       │                  │   │              │    │             │  │
│       │ • Derives "I can"│   │ • Generates  │    │ • Integrates│  │
│       │ • Explains gaps  │   │   questions  │    │   all layers│  │
│       │ • affordances.   │   │ • Estimates  │    │ • 1-screen  │  │
│       │   json           │   │   value/cost │    │   summary   │  │
│       └──────────────────┘   │ • curiosity_ │    └─────────────┘  │
│                              │   feed.json  │                     │
│                              └──────────────┘                     │
│                                                                    │
│  ┌─────────────────────────────────────────────────────────────┐  │
│  │              INTEGRATION: introspection_tools.py             │  │
│  │                                                              │  │
│  │  • list_introspection_tools: Show all 60+ tools             │  │
│  │  • show_self_portrait: Complete self-awareness summary      │  │
│  └─────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────┘
```

## Components

### 1. Capability Registry (`capabilities_enhanced.yaml`)

Enhanced capability definitions with:
- **Preconditions**: Requirements before capability can work
- **Health checks**: Commands/scripts to verify capability status
- **Cost tracking**: CPU, memory, risk estimates
- **Provides**: List of affordances this capability enables
- **Documentation**: Links to docs for each capability

Example:
```yaml
- key: audio.input
  kind: device
  provides: ["mic_stream", "levels", "vad"]
  preconditions:
    - "group:audio"
    - "path:/dev/snd readable"
    - "pipewire_session"
  health_check: "pactl list short sources"
  cost:
    cpu: 1
    mem: 64
    risk: low
  tests: ["audio_probe_basic"]
  docs: "docs/audio.md"
  enabled: true
```

### 2. Capability Evaluator (`capability_evaluator.py`)

Evaluates all capabilities and generates state matrix.

**Functions:**
- `load_capabilities()` - Load YAML registry
- `check_precondition(precondition)` - Validate single precondition
- `run_health_check(health_check)` - Execute health check command
- `evaluate_capability(cap_data)` - Evaluate single capability
- `evaluate_all()` - Generate complete matrix
- `write_state_json()` - Write `/home/kloros/.kloros/self_state.json`

**Precondition Formats:**
- `group:audio` → User in group
- `path:/dev/snd readable` → Path exists and readable
- `module:chromadb importable` → Python module available
- `command:piper available` → Command in PATH
- `env:KLR_ENABLE_CURIOSITY=1` → Environment variable check
- `systemd:dream.service active` → systemd unit status
- `http:http://example.com reachable` → HTTP endpoint check
- `pipewire_session` → PipeWire session active
- `{capability_key}:ok` → Dependency on another capability

**Health Check Formats:**
- `pactl list short sources` → Shell command
- `python:pragma_quick_check` → Python function call
- `http:http://example.com` → HTTP GET request
- `bash:test -w /path` → Bash test command
- `env:KLR_ENABLE_CURIOSITY` → Environment variable check
- `systemd:dream.service status` → systemd status

**Output:** `/home/kloros/.kloros/self_state.json`

### 3. Curiosity Core (`curiosity_core.py`)

Generates questions from capability gaps.

**Question Generation Rules:**
1. **Missing capability** → "What exact step enables <capability>?"
2. **Degraded capability** → "Which mitigation improved it last time?"
3. **Precondition unmet** → Specific question about the precondition
4. **Affordance needed but unavailable** → "What's the minimal substitute?"

**Question Fields:**
- `id` - Unique identifier
- `hypothesis` - Suspected root cause
- `question` - Human-readable question
- `evidence` - List of supporting evidence
- `action_class` - Type of action (investigate, propose_fix, etc.)
- `autonomy` - Autonomy level (2 = propose, not execute)
- `value_estimate` - Expected value (0.0-1.0)
- `cost` - Expected cost/risk (0.0-1.0)
- `status` - ready, in_progress, answered, blocked
- `capability_key` - Associated capability

**Output:** `/home/kloros/.kloros/curiosity_feed.json`

### 4. Affordance Registry (`affordance_registry.py`)

Derives high-level abilities from low-level capabilities.

**Affordance Mapping:**
```python
"transcribe_live" → ["audio.input", "stt.vosk"]
"text_to_speech" → ["audio.output", "tts.piper"]
"semantic_search" → ["memory.chroma", "rag.retrieval"]
"generate_response" → ["llm.ollama"]
"optimize_self" → ["dream.evolution"]
"ask_questions" → ["reasoning.curiosity", "tools.introspection"]
...
```

**Functions:**
- `compute_affordances(matrix)` - Compute available affordances
- `get_available_affordances()` - Get list of available affordances
- `get_unavailable_affordances()` - Get list of unavailable affordances
- `get_statement()` - Generate "I CAN / I CANNOT" statement
- `write_affordances_json()` - Write affordances to JSON

**Output:** `/home/kloros/.kloros/affordances.json`

### 5. Self-Portrait (`self_portrait.py`)

Integrates all components into 1-screen summary.

**Output Format:**
```
╔══════════════════════════════════════════════════════════════╗
║                  KLOROS SELF-PORTRAIT                        ║
║                  2025-10-23 20:46:30                         ║
╠══════════════════════════════════════════════════════════════╣
║ CAPABILITY STATUS                                            ║
║   Total: 17  |  ✓ OK: 7  |  ⚠ Degraded: 0  |  ✗ Missing: 10║
╠══════════════════════════════════════════════════════════════╣
║ CURRENT AFFORDANCES                                          ║
║   I CAN:                                                     ║
║     ✓ Generate natural language responses                   ║
║     ✓ Save conversation state to memory                     ║
║   I CANNOT:                                                  ║
║     ✗ Transcribe speech in real-time                        ║
║       → missing: audio.input, stt.vosk                      ║
╠══════════════════════════════════════════════════════════════╣
║ CURIOSITY QUESTIONS                                          ║
║   1. [7.0] What value should be set for the missing config? ║
╠══════════════════════════════════════════════════════════════╣
║ NEXT ACTION                                                  ║
║   Will investigate audio.input issue via safe probe         ║
╚══════════════════════════════════════════════════════════════╝
```

**Functions:**
- `generate()` - Generate complete portrait
- `write_all_artifacts()` - Write all JSON artifacts

## Integration with KLoROS

### Introspection Tools Added

Two new tools added to `/home/kloros/src/introspection_tools.py`:

1. **list_introspection_tools**
   - Lists all 60+ introspection tools with descriptions
   - Replaces broken `list_models` response

2. **show_self_portrait**
   - Generates complete self-awareness summary
   - Evaluates all capabilities
   - Computes affordances
   - Generates curiosity questions
   - Writes all artifacts to disk

### Usage

**From Python:**
```python
from src.registry.self_portrait import SelfPortrait

portrait = SelfPortrait()
summary = portrait.generate()
print(summary)

# Write artifacts
portrait.write_all_artifacts()
```

**From KLoROS Voice:**
```
User: "KLoROS, show me your self-portrait"
KLoROS: [Generates and displays complete self-awareness summary]

User: "KLoROS, what tools do you have?"
KLoROS: [Uses list_introspection_tools to show all 60+ tools]
```

## File Locations

### Registry Files
- `/home/kloros/src/registry/capabilities_enhanced.yaml` - Enhanced capability definitions
- `/home/kloros/src/registry/capability_evaluator.py` - Health checks and evaluation
- `/home/kloros/src/registry/curiosity_core.py` - Question generator
- `/home/kloros/src/registry/affordance_registry.py` - Affordance derivation
- `/home/kloros/src/registry/self_portrait.py` - 1-screen summary

### Output Artifacts
- `/home/kloros/.kloros/self_state.json` - Capability matrix
- `/home/kloros/.kloros/affordances.json` - Available/unavailable affordances
- `/home/kloros/.kloros/curiosity_feed.json` - Generated questions

### Integration Points
- `/home/kloros/src/introspection_tools.py` - Introspection tool registry (2 tools added)

## Testing

Each component has standalone self-test:

```bash
cd /home/kloros/src/registry

# Test capability evaluator
sudo -u kloros python3 capability_evaluator.py

# Test curiosity core
sudo -u kloros python3 curiosity_core.py

# Test affordance registry
sudo -u kloros python3 affordance_registry.py

# Test complete self-portrait
sudo -u kloros python3 self_portrait.py
```

## Governance Compliance

All components follow KLoROS governance requirements:

### Tool-Integrity ✓
- Self-contained and testable
- Complete docstrings for all functions
- Graceful error handling
- No bare exceptions

### D-REAM-Allowed-Stack ✓
- Uses pytest for tests
- JSON for artifacts
- Subprocess with timeouts
- No unbounded loops
- No prohibited tools (stress-ng, etc.)

### Autonomy Level 2 ✓
- Proposes questions, doesn't execute
- Surfaces reasoning to user
- User has final authority
- All actions are safe, reversible, or read-only

### Structured Logging ✓
- Uses Python logging module
- Can log to `/var/log/kloros/structured.jsonl`
- Graceful fallback if logging unavailable

## Future Enhancements

1. **Playbook Executor** - Safe, bounded actions for common fixes
2. **Automatic Scheduler** - Run capability evaluation on timer
3. **Dashboard Integration** - Show self-portrait in web UI
4. **Metric Tracking** - Track capability stability over time
5. **Question Answering** - Automatic investigation for high-value questions
6. **Substitute Finder** - Automatic identification of alternative capabilities

## Root Cause Analysis: Original Issue

**Problem:** KLoROS couldn't properly list her tools (output: "AI MODELS: =.")

**Root Causes:**
1. Missing self-introspection capability - no tool to list introspection tools
2. Confusion between AI models and introspection tools
3. No structured capability registry with health checks

**Solution:**
1. Added `list_introspection_tools` to show all 60+ tools
2. Created complete capability registry system
3. Built curiosity-driven self-awareness infrastructure

**Result:** KLoROS can now:
- List all her introspection tools correctly
- Know exactly what she can and cannot do
- Generate questions about capability gaps
- Propose improvements autonomously (Level 2)

## Documentation

- See individual Python files for detailed docstrings
- Each component has inline comments explaining logic
- YAML schema is self-documenting with examples

---

**Built with precision by Claude (Sonnet 4.5)**
**Date:** 2025-10-23
**Governance:** KLoROS-Prime, Tool-Integrity, D-REAM-Allowed-Stack
