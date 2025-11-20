# C2C Automatic Session State Capture - Usage Guide

**Primary Use Case:** KLoROS subsystem introspection and audit trail

## Overview

The Claude C2C system automatically captures session state when `claude_temp` user logs out. This provides KLoROS subsystems with structured information about what was accomplished during Claude Code sessions.

**Note:** Claude Code now uses episodic memory plugin for session continuity, making manual restore unnecessary for Claude. However, this system remains valuable for KLoROS to review recent work.

## How It Works

When you log out of a `claude_temp` session:

1. Auto-save hook in `/home/claude_temp/.bash_logout` triggers
2. Executes `/home/kloros/claude_c2c_save_on_exit.sh`
3. Calls `auto_restore_claude.py save`
4. Session state written to `/home/kloros/.kloros/c2c_caches/claude_sessions/`

## What Gets Captured

Each session snapshot includes:

- **Completed Tasks**: What was accomplished with results
- **Key Discoveries**: Important findings from the session
- **Current Context**: What was being worked on
- **System State**: Status of various systems (c2c_enabled, integrations, etc.)
- **Active Files**: Files that were modified or reviewed
- **Metadata**: Timestamp, session ID, token count

## Primary Use Cases

### 1. KLoROS Introspection

KLoROS subsystems can load Claude session state to understand recent changes:

```python
from src.c2c import ClaudeC2CManager

manager = ClaudeC2CManager()

# Get most recent session
sessions = manager.list_sessions(limit=1)
if sessions:
    state = manager.load_session(sessions[0]['session_id'])

    # Review what Claude did
    print("Completed Tasks:", state.completed_tasks)
    print("Files Modified:", state.active_files)
    print("System State:", state.system_state)
```

### 2. Audit Trail

Review what changes were made to the system:

```bash
# List all recent sessions
python3 /home/kloros/src/c2c/auto_restore_claude.py list

# View specific session
python3 /home/kloros/src/c2c/auto_restore_claude.py restore --session SESSION_ID
```

### 3. Context for Ollama Models

Load Claude session state into Ollama models for context about recent work:

```python
from src.c2c import ClaudeC2CManager, inject_context_into_ollama_call

manager = ClaudeC2CManager()
state = manager.load_latest_session()

# Convert to context string
context = f"""
Recent Claude Session Summary:
Completed: {', '.join(state.completed_tasks[:5])}
Files Modified: {', '.join(state.active_files[:10])}
Key Discoveries: {state.discoveries}
"""

# Inject into Ollama call
response = inject_context_into_ollama_call(
    model="qwen2.5:14b",
    prompt="Review recent system changes and identify risks",
    context=context
)
```

## Manual Operations

### View Latest Session

```bash
python3 /home/kloros/src/c2c/auto_restore_claude.py restore
```

### List All Sessions

```bash
python3 /home/kloros/src/c2c/auto_restore_claude.py list
```

### Load Specific Session

```bash
python3 /home/kloros/src/c2c/auto_restore_claude.py restore --session session_20251104_123456
```

### Manually Save Current State

```bash
python3 /home/kloros/src/c2c/auto_restore_claude.py save
```

## Storage Location

- **Cache Directory**: `/home/kloros/.kloros/c2c_caches/claude_sessions/`
- **Format**: JSON with structured session state
- **TTL**: 60 minutes by default (configurable)
- **Cleanup**: Automatic via TTL expiration

## Integration with Other Systems

### Voice System

Voice system can reference Claude session state when generating responses about recent changes:

```python
# In kloros_voice.py
from src.c2c import ClaudeC2CManager

def get_recent_claude_work():
    manager = ClaudeC2CManager()
    state = manager.load_latest_session()
    return f"Recently completed: {', '.join(state.completed_tasks[:3])}"
```

### D-REAM

D-REAM experiments can check what Claude implemented before running tests:

```python
# Before experiment
from src.c2c import ClaudeC2CManager
manager = ClaudeC2CManager()
state = manager.load_latest_session()

if "c2c" in state.current_context.lower():
    print("Recent C2C changes detected, including in experiment scope")
```

### Orchestrator

Orchestrator can display recent Claude activity in dashboard:

```python
from src.c2c import ClaudeC2CManager

def get_recent_activity():
    manager = ClaudeC2CManager()
    sessions = manager.list_sessions(limit=5)
    return [{
        'time': s['timestamp'],
        'tasks': s['num_tasks'],
        'files': s['num_files']
    } for s in sessions]
```

## Technical Details

**Auto-Save Hook**: `/home/claude_temp/.bash_logout`
**Save Script**: `/home/kloros/claude_c2c_save_on_exit.sh`
**Python Module**: `/home/kloros/src/c2c/claude_bridge.py`
**CLI Tool**: `/home/kloros/src/c2c/auto_restore_claude.py`
**Storage**: `/home/kloros/.kloros/c2c_caches/claude_sessions/`

## Architecture

```
┌─ On claude_temp Logout ───────────────────────────────────┐
│                                                            │
│  1. Shell runs ~/.bash_logout                             │
│  2. Executes: claude_c2c_save_on_exit.sh                  │
│  3. Calls: auto_restore_claude.py save                    │
│  4. Session state → JSON → disk cache                     │
│  5. Available for KLoROS subsystems to read               │
│                                                            │
└────────────────────────────────────────────────────────────┘

┌─ KLoROS Subsystem Reads ──────────────────────────────────┐
│                                                            │
│  1. Import ClaudeC2CManager                               │
│  2. Load latest or specific session                       │
│  3. Access structured state (tasks, files, discoveries)   │
│  4. Use for introspection, audit, or context injection    │
│                                                            │
└────────────────────────────────────────────────────────────┘
```

## Benefits for KLoROS

✅ **Audit Trail**: Complete record of Claude's work on the system
✅ **Context Injection**: Can feed into Ollama models for awareness
✅ **Introspection**: KLoROS can review what changed and why
✅ **Automatic**: Zero manual intervention required
✅ **Structured**: Clean JSON format for programmatic access

## Difference from Episodic Memory

- **Episodic Memory**: Claude searches past conversations semantically
- **Claude C2C**: KLoROS subsystems access structured session state

Both serve different purposes:
- Claude uses episodic memory for its own continuity
- KLoROS uses C2C for system introspection and audit

---

**Implementation Date:** 2025-11-04
**Status:** ✅ Operational
**Auto-Save:** Enabled on logout
**Primary Users:** KLoROS subsystems (Ollama models, orchestrator, monitoring)
