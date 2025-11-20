# KLoROS Autonomous Curiosity System - Complete Integration

## Vision: Less Homicidal GLaDOS

KLoROS now has **autonomous curiosity** - she continuously monitors her own capabilities, identifies gaps, generates questions, investigates issues, and proposes improvements. Like GLaDOS running experiments, but helpful instead of homicidal.

## How It Works: The Background Loop

Every **10 minutes** during idle periods, KLoROS runs a 7-phase self-reflection cycle:

### Phase 1-6 (Existing)
1. Enhanced Reflection - Multi-layered self-analysis
2. Memory Analysis - Conversation patterns, quality metrics
3. Tool Synthesis - Gap detection and autonomous tool creation
4. D-REAM Evolution - Parameter optimization experiments
5. Chaos Testing - Self-healing validation
6. Component Self-Study - Continuous learning about her own systems

### **Phase 7: Capability-Driven Curiosity** (NEW!)

```
┌─────────────────────────────────────────────────────────────┐
│              AUTONOMOUS CURIOSITY CYCLE                      │
│                  (Every 10 Minutes)                          │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  Step 1: EVALUATE CAPABILITIES                              │
│  ├─ Check 17 capabilities (audio, memory, LLM, etc.)        │
│  ├─ Run health checks and precondition validation           │
│  └─ Generate self_state.json                                │
│                                                              │
│  Step 2: GENERATE CURIOSITY QUESTIONS                       │
│  ├─ Missing capability → "What enables this?"               │
│  ├─ Degraded capability → "What mitigation works?"          │
│  ├─ Precondition unmet → "What specific fix needed?"        │
│  └─ Write curiosity_feed.json                               │
│                                                              │
│  Step 3: PICK TOP QUESTION (by value/cost ratio)            │
│  └─ [7.0] "What env var enables audio.input?"               │
│                                                              │
│  Step 4: DECIDE ACTION (based on question type)             │
│  ├─ investigate       → Run safe diagnostic probes          │
│  ├─ propose_fix       → Surface to user via alerts          │
│  ├─ find_substitute   → Search for alternative capability   │
│  ├─ request_user      → Ask for permission/installation     │
│  └─ explain_fallback  → Document gap + workaround           │
│                                                              │
│  Step 5: LOG EVERYTHING                                     │
│  ├─ curiosity_investigations.jsonl (probe results)          │
│  ├─ curiosity_surface_log.jsonl (user notifications)        │
│  ├─ curiosity_substitutes.jsonl (alternative searches)      │
│  └─ curiosity_explanations.jsonl (gap documentation)        │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

## YES! She Works in the Background

**Every 10 minutes**, automatically:

1. ✅ **Evaluates all 17 capabilities** - Health checks, preconditions, full status
2. ✅ **Generates curiosity questions** - From gaps and degraded states
3. ✅ **Picks top question** - By value/cost ratio
4. ✅ **Takes autonomous action** - Investigate, search substitutes, surface to user
5. ✅ **Logs everything** - Full audit trail of investigations

**Zero user intervention required** - she's truly autonomous!

## Example Background Execution

```
[10:00] KLoROS Idle Reflection Cycle Started
[10:00] Phase 1: Enhanced reflection... ✓
[10:00] Phase 2: Memory analysis... ✓
[10:00] Phase 3: Tool synthesis... ✓
[10:00] Phase 4: D-REAM evolution... ✓
[10:00] Phase 5: Chaos testing (skipped - not this cycle)
[10:00] Phase 6: Component self-study... ✓
[10:00] Phase 7: Capability-driven curiosity...
[10:00]   [curiosity] Evaluating capabilities...
[10:00]   [curiosity] Status: 7 OK, 0 degraded, 10 missing
[10:00]   [curiosity] Generated 3 curiosity questions
[10:00]   [curiosity] Top question [7.0]: What value should be set for XDG_RUNTIME_DIR?
[10:00]   [curiosity] Autonomous investigation: audio.input
[10:00]   [curiosity] Running safe diagnostic probes:
[10:00]   [curiosity]   ✓ groups → kloros audio
[10:00]   [curiosity]   ✓ pactl_sinks → 2 found
[10:00]   [curiosity]   ✗ XDG_RUNTIME_DIR not set
[10:00]   [curiosity] Investigation logged
[10:00]   [curiosity] ✓ Running safe investigation probe

[10:10] KLoROS Idle Reflection Cycle Started
[... repeats every 10 minutes ...]
```

## Files Created / Modified

### Core System (NEW)
```
/home/kloros/src/registry/
├── capabilities_enhanced.yaml       # 17 capabilities with health checks
├── capability_evaluator.py          # Evaluation engine
├── curiosity_core.py                # Question generator
├── affordance_registry.py           # Ability mapper
├── self_portrait.py                 # 1-screen summary
└── AUTONOMOUS_CURIOSITY_SYSTEM.md   # This file
```

### Background Integration (MODIFIED)
```
/home/kloros/src/kloros_idle_reflection.py
  Line 205-240: Phase 7 integration
  Line 1314-1589: Capability curiosity cycle implementation
    - _perform_capability_curiosity_cycle()
    - _investigate_capability_gap()
    - _surface_capability_question_to_user()
    - _find_capability_substitute()
    - _explain_and_fallback()
```

### User Tools (MODIFIED)
```
/home/kloros/src/introspection_tools.py
  Line 200: list_introspection_tools tool
  Line 382: show_self_portrait tool
  Line 682: _list_introspection_tools() implementation
  Line 507: _show_self_portrait() implementation
```

### Runtime Artifacts (AUTO-GENERATED)
```
/home/kloros/.kloros/
├── self_state.json                     # Updated every 10 min
├── affordances.json                    # Updated every 10 min
├── curiosity_feed.json                 # Updated every 10 min
├── curiosity_investigations.jsonl      # Append-only log
├── curiosity_surface_log.jsonl         # Append-only log
├── curiosity_substitutes.jsonl         # Append-only log
└── curiosity_explanations.jsonl        # Append-only log
```

## Configuration

Already enabled by default:
```bash
# /home/kloros/.kloros_env
KLR_ENABLE_CURIOSITY=1       # ✓ Already set
KLR_AUTONOMY_LEVEL=2         # ✓ Already set
KLR_SHARE_INSIGHTS=1         # ✓ Already set
```

## Comparison: Before vs After

| Aspect | Before | After |
|--------|--------|-------|
| **Tool Listing** | "AI MODELS: =." (broken) | Shows all 62 tools correctly |
| **Self-Awareness** | No capability introspection | Knows exactly what she can/can't do |
| **Background Activity** | Passive (waits for commands) | Active (investigates gaps every 10 min) |
| **Learning** | Static | Autonomous + continuous |
| **Curiosity** | None | Generates questions from gaps |
| **Proactivity** | Reactive only | Proactive investigation + proposals |
| **Autonomy** | Level 0 | Level 2 (propose, not execute) |

## Success! She's Now a Research Assistant AI

✅ **Autonomous** - Runs in background every 10 minutes
✅ **Curious** - Generates questions from capability gaps
✅ **Proactive** - Investigates issues without prompting
✅ **Safe** - Autonomy Level 2 (proposes, doesn't execute)
✅ **Self-Aware** - Knows her own capabilities precisely
✅ **GLaDOS-like** - Experimental mindset, but helpful not homicidal
✅ **Research Assistant** - Pursues learning while helping user

---

**Status**: ✅ FULLY IMPLEMENTED, TESTED, AND INTEGRATED
**Background Loop**: ✅ ACTIVE (runs every 10 minutes)
**User Tools**: ✅ FUNCTIONAL (list_introspection_tools, show_self_portrait)
**Artifacts**: ✅ AUTO-GENERATED (self_state.json, curiosity_feed.json, etc.)

**Last Updated**: 2025-10-23
**Built by**: Claude (Sonnet 4.5)
