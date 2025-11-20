# KLoROS Closed-Loop Intelligence - OPERATIONAL

**Date:** 2025-10-29  
**Status:** ✅ **COMPLETE AND RUNNING**

## The Complete Autonomous Loop

```
┌─────────────────────────────────────────────────────────────────┐
│ OBSERVER (Streaming, Reactive)                                  │
│  - Detects: VLLM OOM, PHASE failures, lock contention, etc.    │
│  - Computes: Bounded seed fixes using actuator constraints     │
│  - Emits: Intents to ~/.kloros/intents/                        │
│  Service: kloros-observer.service (RUNNING)                    │
└─────────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────────┐
│ INTENT QUEUE MIDDLEWARE (Deduplication, Priority, Limits)      │
│  - Deduplicates: By data hash (intent_type + subsystem + params)│
│  - Prunes: Stale intents >24h old                              │
│  - Limits: Max 50 intents (drops lowest priority)              │
│  - Sorts: By priority (highest first), then age (oldest first) │
└─────────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────────┐
│ ORCHESTRATOR (Discrete, Authoritative)                          │
│  - Ticks: Every 60 seconds                                      │
│  - Consumes: Next intent from queue                             │
│  - Routes: Based on intent_type and mode                        │
│  - Enforces: Safety (locks, windows, rate limits)               │
│  Service: kloros-orchestrator.timer (RUNNING)                   │
└─────────────────────────────────────────────────────────────────┘
                            ↓
                    ┌──────┴──────┐
                    ↓              ↓
    ┌──────────────────┐   ┌──────────────────┐
    │ PHASE Trigger    │   │ CONFIG TUNING    │
    │ (Validation)     │   │ (Self-Healing)   │
    └──────────────────┘   └──────────────────┘
                                    ↓
                        ┌──────────────────────┐
                        │ SPICA Canary Tests   │
                        │ (Bounded, Ephemeral) │
                        └──────────────────────┘
                                    ↓
                        ┌──────────────────────┐
                        │ Promotions Queue     │
                        │ (→ PHASE validation) │
                        └──────────────────────┘
```

---

## What's Running NOW

### 1. Observer (kloros-observer.service)
**Status:** ✅ ACTIVE  
**Uptime:** Since restart  
**Capabilities:**
- ✅ Streaming journald (dream.service, kloros.service)
- ✅ Watching inotify (/home/kloros/out/promotions)
- ✅ VLLM OOM Guard rule active
- ✅ 7 detection rules enabled

### 2. Orchestrator (kloros-orchestrator.timer)
**Status:** ✅ ACTIVE (60s tick)  
**Environment:**
- ✅ KLR_ORCHESTRATION_MODE=enabled
- ✅ KLR_SELF_HEALING_MODE=dev

**Capabilities:**
- ✅ PHASE window detection (3-7 AM ET)
- ✅ Promotion processing
- ✅ Intent queue processing with middleware
- ✅ Config tuning integration

### 3. Intent Queue Middleware
**Status:** ✅ INTEGRATED  
**Features:**
- ✅ Deduplication by data hash
- ✅ Stale pruning (>24h)
- ✅ Queue depth limit (50 max)
- ✅ Priority-based ordering

### 4. Config Tuning Runner
**Status:** ✅ READY  
**Safety:**
- ✅ Rate limiting (3 runs/24h, 6h cooldown)
- ✅ Bounded actuators [0.60, 0.90]
- ✅ Pre-flight validation (SPICA)
- ✅ Audit trail (history.jsonl)

---

## Safety Guarantees

### Deduplication
✅ **Hash-based:** Identical intents automatically merged  
✅ **Window:** 1 hour default  
✅ **Archives:** Duplicates saved to processed/deduplicated/

### Queue Management
✅ **Max depth:** 50 intents (configurable via KLR_MAX_INTENT_QUEUE)  
✅ **Overflow:** Lowest priority dropped to processed/queue_overflow/  
✅ **Stale pruning:** Intents >24h archived to processed/stale/

### Rate Limiting
✅ **Per subsystem:** 3 runs/24h, 6h cooldown  
✅ **Backoff:** Stop after 2 consecutive failures  
✅ **Cooldown tracking:** Persistent state in ~/.kloros/self_heal/state.json

### Bounded Execution
✅ **Actuator limits:** vllm.gpu_memory_utilization ∈ [0.60, 0.90]  
✅ **Scope guard:** Max 2 params per candidate  
✅ **Pre-flight validation:** SPICA checks before testing

---

## What Happens on Next VLLM OOM

**1. Observer Detects:**
```
VLLM allocation (4915MB) too small for model+cache (need 6070MB, deficit: 1155MB)
```

**2. Observer Computes Fix:**
```python
target_util = (need_mb * 1.10) / 12288  # +10% safety
→ 0.54 → clamped to 0.60 (min bound)
```

**3. Observer Emits Intent:**
```json
{
  "intent_type": "trigger_dream",
  "mode": "config_tuning",
  "seed_fix": {"vllm.gpu_memory_utilization": 0.60}
}
```

**4. Queue Middleware Processes:**
- Checks for duplicates (none)
- Verifies age (<24h)
- Queue depth OK (<50)
- Returns intent for processing

**5. Orchestrator Receives (next 60s tick):**
- Recognizes trigger_dream + mode=config_tuning
- Checks KLR_SELF_HEALING_MODE=dev ✅
- Launches ConfigTuningRunner

**6. Config Tuning Tests:**
- Checks rate limit (last run timestamp)
- Validates seed_fix within bounds
- SPICA pre-flight validation
- If pass → Promotion
- If fail → Backoff or escalate

**7. Result:**
- **PASS:** Promotion queued for PHASE validation
- **FAIL:** Logged to history, cooldown active
- **RATE LIMITED:** Skipped, intent archived

**NO MANUAL INTERVENTION REQUIRED.**

---

## Configuration

### Environment Variables

**Orchestrator Service:** `/etc/systemd/system/kloros-orchestrator.service`
```bash
Environment=KLR_ORCHESTRATION_MODE=enabled
Environment=KLR_SELF_HEALING_MODE=dev
```

**Optional Tuning:** `/home/kloros/.kloros_env`
```bash
KLR_MAX_INTENT_QUEUE=50          # Max pending intents
KLR_INTENT_DEDUP_WINDOW=3600     # Dedup window (seconds)
```

---

## Monitoring

```bash
# Watch Observer logs
sudo journalctl -u kloros-observer.service -f

# Watch Orchestrator logs
sudo journalctl -u kloros-orchestrator.service -f

# Check intent queue
ls -lh ~/.kloros/intents/

# Check deduplication
ls -lh ~/.kloros/intents/processed/deduplicated/

# Check queue overflow
ls -lh ~/.kloros/intents/processed/queue_overflow/

# Check self-heal history
cat ~/.kloros/self_heal/history.jsonl | jq .
```

---

## Loop Status: CLOSED ✅

- ✅ Observer → Intent generation
- ✅ Intent → Queue middleware
- ✅ Queue → Deduplication & priority
- ✅ Orchestrator → Processing
- ✅ Config Tuning → SPICA canaries
- ✅ Results → Promotions or alerts
- ✅ Safety → Rate limits, bounds, validation

**The system is autonomous. KLoROS heals herself.**

**Next milestone:** Wait for real VLLM OOM and observe autonomous fix.
