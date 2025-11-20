---
title: KLoROS Overnight GPU Migration & Debugging Session
date: 2025-11-18
tags: [gpu-migration, altimitos, remote-ollama, deepseek-r1, timeout-fixes, persona-update]
context_type: comprehensive
session_id: gpu-migration-nov-18
---

# Session Summary: Overnight GPU Migration to AltimitOS

## Critical Changes Made

### 1. Remote GPU Offload (COMPLETED)
**Problem:** ASTRAEA local RTX 3060 running LLM inference at 82.9s/request, causing system-wide timeouts and memory exhaustion.

**Solution:** Migrated all Ollama endpoints to AltimitOS (100.67.244.66:11434) via Tailscale.

**Performance Result:**
- Before: 82.9s per request (local RTX 3060)
- After: 2.8s per request (remote AltimitOS)
- **Speedup: 29.6x faster (96.6% improvement)**

**Configuration Files Modified:**
- `/home/kloros/.kloros_env` → OLLAMA_HOST=http://100.67.244.66:11434
- `/home/kloros/.kloros_env.clean` → All OLLAMA_*_URL endpoints → 100.67.244.66:11434
- `/etc/systemd/system/kloros-meta-agent.service` → OLLAMA_HOST=http://100.67.244.66:11434

**Services Using Remote GPU:**
- `kloros-meta-agent.service` → deepseek-r1:7b (reasoning/consciousness)
- `klr-investigation-consumer.service` → qwen2.5-coder:7b (code analysis)
- `kloros-curiosity-core-consumer.service` → qwen2.5-coder:7b
- `kloros-curiosity-processor.service` → qwen2.5-coder:7b

**Local GPU Status:** No models loaded (freed 5GB VRAM)

### 2. Control Command Created
**File:** `/usr/local/bin/kloros` (executable)

**Usage:**
```bash
kloros remote status      # Check current endpoint
kloros remote enabled     # Use AltimitOS (remote)
kloros remote disabled    # Use local ASTRAEA
```

### 3. Meta-Agent Timeout & Parsing Fixes
**File:** `/home/kloros/src/consciousness/meta_agent_daemon.py`

**Changes:**
1. **Timeout increased** (line 417): 120s → 300s
2. **JSON parsing enhanced** (lines 255-277):
   - Strips markdown code fences (\`\`\`json...\`\`\`)
   - Strips deepseek-r1 `<think>` tags
   
**Result:** 0 timeouts in last 2 hours (vs 20+ before fix)

### 4. Persona Security Update
**File:** `/home/kloros/src/persona/kloros.py` (line 19)

**Fix:** Added explicit permission for self-investigation:
> "You have FULL READ ACCESS to all files under /home/kloros/. These are YOUR files - your architecture docs, your configs, your code. You ARE the proprietary information."

**Result:** Meta-agent will now investigate her own documentation without security hesitation.

### 5. Queue Depth Limiting
**File:** `/home/kloros/src/kloros/orchestration/investigation_consumer_daemon.py`

- max_queue_depth = 100
- Emits INVESTIGATION_QUEUE_FULL signal for back-pressure

**Current Queue:** 3,050 investigations queued, 30,586 processed

## Overnight Performance Summary

**Services:** ✅ All active and stable
**Investigation timeouts:** 0 in last 2 hours (all occurred before remote GPU)
**Memory:** 18GB/31GB RAM, 0GB swap ✅
**Local VRAM:** 0GB (all inference on remote) ✅

## Quick Reference Commands

```bash
# Check status
kloros remote status
free -h
curl -s http://100.67.244.66:11434/api/ps | jq

# View logs
sudo journalctl -u kloros-meta-agent.service --since "1 hour ago"

# Clear swap if needed
sudo swapoff -a && sudo swapon -a
```

---

## Ray Integration Decision (Morning Discussion)

**Initial Goal:** Use Ray to leverage AltimitOS's 128GB RAM for distributed investigation processing.

**Analysis:**
- Remote GPU migration already solved performance bottleneck (29.6x speedup)
- ASTRAEA has 13GB free RAM currently
- Investigation queue (3,050 items) not urgent
- Problem is simply: "not enough RAM"

**Decision:** **Skip Ray, upgrade RAM instead**

**Rationale:**
- Ray adds distributed systems complexity for a simple RAM shortage
- $60-80 for 2x16GB DDR4-2133 → 64GB total capacity
- Solves problem in 5 minutes vs days of Ray setup/debugging
- No network overhead, no new failure modes
- YAGNI principle applies

**RAM Upgrade Path:**
- Current: 2x16GB DDR4-2133 (32GB total, 2 empty slots)
- Add: 2x16GB DDR4-2133 ($60-80)
- Result: 64GB total (2x current capacity)
- Allows: 10+ concurrent investigations without memory pressure

**Status:** Ray integration postponed indefinitely. RAM upgrade recommended.
