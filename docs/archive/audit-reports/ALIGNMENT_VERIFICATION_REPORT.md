# KLoROS System Alignment Verification Report

**Date:** November 1, 2025, 20:10 UTC
**Purpose:** Verify all November 1st implementations align with existing KLoROS architecture
**Status:** ⚠️ **CRITICAL ISSUES FOUND**

---

## Executive Summary

**Result:** 🔴 **FAIL** - 2 critical bugs will crash autonomous loop on first tick

**Critical Issues:**
1. **Signature mismatch:** coordinator.py calls dream_trigger.run_once() with wrong parameters → **TypeError crash**
2. **Data structure mismatch:** winner_deployer.py creates wrong promotion format → **KeyError crash**

**Non-Critical Issues:**
3. Validation uses mock metrics instead of real domain evaluators
4. Winner deployer missing ACK file creation
5. No locking mechanism (race condition risk)
6. Missing schema validation

---

## Critical Issue #1: dream_trigger.run_once() Signature Mismatch

### Expected Signature
From `/home/kloros/src/kloros/orchestration/dream_trigger.py:37`:
```python
def run_once(topic: Optional[str] = None, run_tag: Optional[str] = None, timeout_s: int = DREAM_TIMEOUT_S) -> DreamResult:
```

**Parameters:** `topic`, `run_tag`, `timeout_s`

### Actual Usage
From `/home/kloros/src/kloros/orchestration/coordinator.py:206-209`:
```python
result = dream_trigger.run_once(
    experiment_name=dream_experiment.get("name", f"curiosity_{question_id}"),
    config_override=dream_experiment
)
```

**Parameters:** `experiment_name`, `config_override` ← **WRONG!**

### Impact
- **When:** First curiosity intent triggers D-REAM spawn
- **What:** `TypeError: run_once() got unexpected keyword argument 'experiment_name'`
- **Result:** Curiosity → D-REAM bridge crashes, autonomous loop breaks

### Fix Required
Change coordinator.py line 206-209 to:
```python
result = dream_trigger.run_once(
    topic=None,
    run_tag=dream_experiment.get("name", f"curiosity_{question_id}")
)
```

**Note:** D-REAM runner doesn't support dynamic experiment selection via dream_trigger. It runs ALL experiments defined in dream.yaml each cycle.

---

## Critical Issue #2: PromotionApplier Data Structure Mismatch

### Expected Format
From `/home/kloros/src/dream_promotion_applier.py:54-58`:
```python
promotion_id = promotion["promotion_id"]
winner = promotion["winner"]
params = winner["params"]
metrics = winner["metrics"]
apply_map = promotion.get("apply_map", {})
```

**Structure:**
```json
{
  "promotion_id": "...",
  "winner": {
    "params": {...},
    "metrics": {...}
  },
  "apply_map": {...}
}
```

### Actual Format
From `/home/kloros/src/kloros/orchestration/winner_deployer.py:218-226`:
```python
promotion = {
    "experiment": experiment_name,
    "apply_map": apply_map,
    "fitness": fitness,
    "timestamp": winner_data.get("updated_at"),
    "params": params,  # <-- WRONG LEVEL
    "_deployed_by": "winner_deployer",
    "_deployed_at": datetime.now().isoformat()
}
```

**Structure:**
```json
{
  "experiment": "...",
  "params": {...},     // <- Should be inside "winner"
  "fitness": 0.85,
  "apply_map": {...}
}
```

Missing: `promotion_id`, `winner` wrapper, `metrics`

### Impact
- **When:** First winner file detected by WinnerDeployer
- **What:** `KeyError: 'winner'` when PromotionApplier tries to access `promotion["winner"]`
- **Result:** Winner deployment crashes, autonomous loop breaks

### Fix Required
Change winner_deployer.py lines 218-226 to:
```python
promotion = {
    "promotion_id": f"{experiment_name}_{winner_hash}",
    "winner": {
        "params": params,
        "metrics": {"fitness": fitness}
    },
    "apply_map": apply_map,
    "timestamp": winner_data.get("updated_at", datetime.now().isoformat()),
    "_deployed_by": "winner_deployer",
    "_deployed_at": datetime.now().isoformat()
}
```

---

## Issue #3: Validation Loop Not Using Domain Evaluators

### Current Implementation
From `/home/kloros/src/kloros/orchestration/validation_loop.py:221-260`:
```python
def _run_domain_tests(self, domain: str) -> Optional[Dict[str, float]]:
    # For now, return mock metrics based on domain
    # TODO: Implement actual test execution
    mock_metrics = {
        "vllm": {"throughput": 45.2, "latency_p50": 120.5, "error_rate": 0.02},
        "tts": {"quality_mos": 4.1, "latency_ms": 85.3, "wer": 0.08},
        # ...
    }
    logger.warning(f"Using mock metrics for {domain} (TODO: implement actual tests)")
    return mock_metrics[domain]
```

### Expected Pattern
From `/home/kloros/src/dream/domains/domain_evaluator_base.py:196-271`:
```python
def evaluate(self, genome_or_config, regime_config: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    config = self.genome_to_config(genome_or_config)
    metrics = self.run_probes(config)
    is_safe, violations = self.check_safety(config, metrics)
    fitness = self.calculate_fitness(metrics)
    return {
        'fitness': fitness,
        'metrics': metrics,
        'config': config,
        'safe': is_safe
    }
```

### Impact
- **Severity:** Medium (validation runs but uses fake data)
- **What:** Can't detect actual performance changes
- **Result:** May keep bad deployments or rollback good ones

### Fix Required
Import and instantiate domain evaluators:
```python
from src.dream.domains.vllm_domain_evaluator import VLLMDomainEvaluator
# ... other evaluators

domain_evaluators = {
    "vllm": VLLMDomainEvaluator(),
    "tts": TTSDomainEvaluator(),
    # ...
}

def _run_domain_tests(self, domain: str) -> Optional[Dict[str, float]]:
    if domain not in self.domain_evaluators:
        return None

    evaluator = self.domain_evaluators[domain]
    result = evaluator.evaluate({})  # Current config
    return result['metrics']
```

---

## Issue #4: Winner Deployer Missing ACK Files

### Current Implementation
winner_deployer.py does NOT create ACK files after deployment.

### Expected Pattern
From `/home/kloros/src/kloros/orchestration/promotion_daemon.py:112-146`:
```python
def create_ack(promo_path: Path, accepted: bool, phase_epoch: str, phase_sha: str, reason: str = "") -> Path:
    ACK_DIR.mkdir(parents=True, exist_ok=True)

    ack_payload = {
        "promotion_id": promo_path.stem,
        "accepted": accepted,
        "phase_epoch": phase_epoch,
        "phase_sha": phase_sha,
        "ts": int(time.time()),
        "schema": "v1"
    }

    ack_path = ACK_DIR / f"{promo_path.stem}_ack.json"
    with open(ack_path, 'w') as f:
        json.dump(ack_payload, f, indent=2)

    logger.info(f"Created ACK for {promo_path.name}: accepted={accepted}")
    return ack_path
```

### Impact
- **Severity:** Medium (breaks audit trail)
- **What:** No ACK files created for winner deployments
- **Result:** Can't track deployment history, promotion_daemon may re-scan

### Fix Required
Add ACK creation to winner_deployer.py after line 231:
```python
# Create ACK file for audit trail
ack_dir = Path("/home/kloros/artifacts/dream/promotions_ack")
ack_dir.mkdir(parents=True, exist_ok=True)
ack_path = ack_dir / f"{experiment_name}_{winner_hash}_ack.json"
ack_data = {
    "promotion_id": f"{experiment_name}_{winner_hash}",
    "accepted": True,
    "deployed_by": "winner_deployer",
    "ts": int(datetime.now().timestamp()),
    "schema": "v1",
    "fitness": fitness,
    "params": params
}
with open(ack_path, 'w') as f:
    json.dump(ack_data, f, indent=2)
```

---

## Issue #5: Winner Deployer Missing Locking

### Current Implementation
winner_deployer.py uses simple JSON state file without locks.

### Expected Pattern
From `/home/kloros/src/kloros/orchestration/state_manager.py:34-117`:
```python
def acquire(name: str, ttl_s: int = 600) -> LockHandle:
    """Acquire exclusive lock with fcntl."""
    lock_path = LOCK_DIR / f"{name}.lock"
    fd = os.open(lock_path, os.O_CREAT | os.O_RDWR, 0o600)
    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    # ... write lock metadata
    return LockHandle(...)

def release(handle: LockHandle) -> None:
    fcntl.flock(handle._fd, fcntl.LOCK_UN)
    os.close(handle._fd)
```

### Impact
- **Severity:** Low (unlikely with 60s coordinator ticks)
- **What:** Race condition if multiple coordinators run
- **Result:** Same winner deployed twice

### Fix Required
Add locking to winner_deployer.py:
```python
from .state_manager import acquire, release

def watch_and_deploy(self) -> Dict[str, Any]:
    lock = acquire("winner_deployer")
    try:
        # ... existing code
    finally:
        release(lock)
```

---

## Issue #6: Winner Deployer Missing Schema Validation

### Current Implementation
winner_deployer.py loads JSON without validation.

### Expected Pattern
From `/home/kloros/src/kloros/orchestration/promotion_daemon.py:45-104`:
```python
def validate_promotion(promo_path: Path, registry: Optional[PromotionRegistry] = None) -> Tuple[bool, str]:
    # Check schema version
    schema = promo.get("schema")
    if schema not in ["v1", "v2"]:
        return False, f"Unsupported schema version: {schema}"

    # Check required fields
    required = ["id", "timestamp", "fitness", "changes"]
    for field in required:
        if field not in promo:
            return False, f"Missing required field: {field}"

    # Bounds checking
    for param, value in changes.items():
        if param in registry.min_values:
            if value < registry.min_values[param]:
                return False, f"{param} below minimum"
```

### Impact
- **Severity:** Low (D-REAM should produce valid winners)
- **What:** Corrupt winner files could crash deployment
- **Result:** Unexpected errors

### Fix Required
Add validation to winner_deployer.py before line 159:
```python
# Validate winner schema
required_fields = ["best", "updated_at"]
if not all(field in winner_data for field in required_fields):
    logger.error(f"Invalid winner schema: {winner_file}")
    failed_count += 1
    continue

best = winner_data["best"]
if "params" not in best or "fitness" not in best:
    logger.error(f"Invalid winner.best schema: {winner_file}")
    failed_count += 1
    continue
```

---

## Conversation System Alignment ✅

### Verified Components

**repetition_prevention.py:**
- ✅ Follows memory system patterns
- ✅ Uses SequenceMatcher (standard library)
- ✅ Clear/add/check interface matches existing checkers
- ✅ Logging format consistent

**topic_tracker.py:**
- ✅ Counter-based keyword tracking (standard pattern)
- ✅ Entity extraction using simple heuristics
- ✅ Stopword filtering matches RAG patterns
- ✅ get_context_for_prompt() returns formatted string

**integration.py changes:**
- ✅ Imports follow existing patterns
- ✅ Initialization in __init__ (lines 45-52)
- ✅ Clear on conversation start (lines 109-115)
- ✅ Update on user input/response (lines 142, 303)
- ✅ Context formatting unchanged (lines 195-217)

**Config changes (.kloros_env):**
- ✅ All config keys follow KLR_ prefix convention
- ✅ Comments use `#` format consistently
- ✅ Float values use decimal notation
- ✅ No syntax errors

---

## Test Results

### KLoROS Voice Status
```
✅ Running (PID 2650686)
⚠️  Disk I/O errors (non-blocking)
✅ Conversation system active
✅ Memory integration functional
```

### Autonomous Loop Status
```
⏳ Coordinator not ticked yet
❌ WILL CRASH on first curiosity intent (Issue #1)
❌ WILL CRASH on first winner deployment (Issue #2)
```

### Winners Directory Status
```bash
$ ls /home/kloros/artifacts/dream/winners/*.json | wc -l
14  # <- 14 winners waiting to deploy
```

**Impact:** When coordinator ticks (every 60s), winner_deployer will attempt to deploy all 14 winners and crash on the first one.

---

## Recommendations

### Immediate (Before Next Coordinator Tick)
1. **FIX Issue #1** - Correct dream_trigger.run_once() call (5 min)
2. **FIX Issue #2** - Fix promotion data structure (10 min)
3. **TEST** - Run winner_deployer manually to verify (5 min)

### High Priority (Today)
4. Fix validation to use real domain evaluators (2 hours)
5. Add ACK file creation to winner_deployer (30 min)
6. Add locking to winner_deployer (30 min)

### Medium Priority (This Week)
7. Add schema validation to winner_deployer (1 hour)
8. Implement actual rollback mechanism (2 hours)

---

## Coordinator Tick Schedule

**Frequency:** Every 60 seconds
**Last Tick:** Unknown (before session started)
**Next Tick:** **Within next 5 minutes** ⚠️
**Risk:** Critical bugs will trigger on next tick

---

## Conclusion

**Overall Alignment:** 🔴 **70% aligned, 2 critical bugs**

**Conversation System:** ✅ 100% aligned, working correctly
**Autonomous Loop:** ❌ 0% functional, will crash on first execution

**Action Required:** Fix Issues #1 and #2 immediately before coordinator ticks

**Estimated Time to Fix:** 15-20 minutes

---

**Report Generated:** November 1, 2025, 20:10 UTC
**Next Review:** After critical fixes applied
