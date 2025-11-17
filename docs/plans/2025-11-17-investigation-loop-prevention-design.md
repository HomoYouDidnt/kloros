# Investigation Loop Prevention and Memory Management

**Date:** 2025-11-17
**Status:** Design Approved
**Related Issues:** Memory exhaustion (curiosity-core-consumer at 99.4%), 370+ duplicate questions on orphaned D-REAM queues, LLM fallback failure

## Executive Summary

KLoROS generates 370+ duplicate questions about disabled D-REAM services, exhausting memory and creating investigation loops. This design implements defense-in-depth across three layers: scanner prevention, evidence-based learning, and memory management. Additionally, we fix LLM fallback to use local Ollama instances when AltimitOS is unavailable.

## Problems Solved

### Critical Issues

1. **Memory Exhaustion**
   - curiosity-core-consumer uses 1018MB of 1024MB limit (99.4%)
   - Service risks OOM kill
   - Root cause: unbounded question generation

2. **Investigation Loop**
   - 370+ duplicate questions on `orphaned_queue_episodes`
   - 74 duplicates each for 10+ other D-REAM queues
   - All marked CRITICAL priority (ratio=4.45)
   - Questions regenerate every cycle despite no progress

3. **LLM Fallback Failure**
   - knowledge_indexer hardcodes AltimitOS endpoint (100.67.244.66:11434)
   - No fallback to local Ollama when AltimitOS unavailable
   - Blocks autonomous knowledge indexing during downtime

### Root Causes

**Investigation Loop:**
- Capability scanners report missing RabbitMQ queues as gaps
- Queues belong to intentionally disabled D-REAM services
- CuriosityCore generates questions for every gap
- No mechanism to learn "this is unsolvable"

**Memory Leak:**
- Infinite question generation fills memory
- No cleanup mechanism before hitting limits
- No memory profiling to identify consumers

**LLM Fallback:**
- knowledge_indexer bypasses LLMRouter
- Direct HTTP calls to hardcoded endpoint
- LLMRouter misconfigured (ports 8001/8002 vs actual 11434/11435)

## Architecture: Defense in Depth

### Principle

Prevent bad questions at multiple layers, with learning.

### Layer 1: Source Prevention (Capability Scanners)

Scanners check systemd service state before reporting gaps. If a service is disabled, they attach `intentionally_disabled=true` metadata.

**Data Flow:**
```
SystemD Scanner → [check if disabled] → CapabilityGap + metadata → CuriosityCore
```

**Implementation:**

1. **Systemd Helper** (`registry/systemd_helpers.py`)
   ```python
   def is_service_intentionally_disabled(service_name: str) -> bool:
       """Check if systemd service is intentionally disabled."""
       result = subprocess.run(
           ["systemctl", "is-enabled", service_name],
           capture_output=True,
           text=True
       )
       return result.stdout.strip() in ["disabled", "masked"]
   ```

2. **Scanner Enhancement** (example: RabbitMQ scanner)
   ```python
   def scan(self) -> List[CapabilityRecord]:
       records = []
       for queue in self.list_queues():
           owning_service = self.infer_service_from_queue_name(queue)

           metadata = {}
           if owning_service and is_service_intentionally_disabled(owning_service):
               metadata = {
                   "intentionally_disabled": True,
                   "reason": f"{owning_service} is disabled"
               }

           records.append(CapabilityRecord(
               name=queue,
               state=CapabilityState.MISSING,
               metadata=metadata
           ))

       return records
   ```

3. **CuriosityCore Filter** (`registry/curiosity_core.py`)
   ```python
   def generate_questions_from_matrix(self, matrix):
       questions = []
       for record in matrix.records:
           if record.metadata.get("intentionally_disabled"):
               logger.debug(f"Skipping intentionally disabled: {record.name}")
               continue

           # Generate question as normal
           questions.append(self._generate_question(record))

       return questions
   ```

**Edge Cases:**
- Queue name doesn't map to service → Report as normal gap
- Service check times out → Report as normal gap (fail open)
- Service is "masked" → Treat as intentionally_disabled

### Layer 2: Evidence-Based Learning (SemanticEvidenceStore)

When investigations fail repeatedly, the system learns "this is unsolvable" and suppresses future questions.

**Data Structure:**
```python
# In semantic_evidence.json
{
  "orphaned_queue_episodes": {
    "purpose": "D-REAM evolution tracking",
    "suppression": {
      "suppressed": true,
      "reason": "Service intentionally disabled",
      "first_attempt": "2025-11-15T10:00:00",
      "failure_count": 5,
      "last_attempt": "2025-11-17T14:30:00",
      "suppress_until": null,
      "user_can_override": true
    }
  }
}
```

**Learning Trigger:**

Investigation consumer tracks attempts per capability_key. After 5 failed investigations, mark as suppressed.

**Definition of Failed:**
- Investigation completes without "answered" status
- Same evidence_hash as previous attempt
- Explicit "unsolvable" tag in results

**CuriosityCore Integration:**
```python
def generate_questions_from_matrix(self, matrix):
    questions = []
    for record in matrix.records:
        if self.semantic_store.is_suppressed(record.name):
            logger.debug(f"Skipping suppressed capability: {record.name}")
            continue

        # Check intentionally_disabled from Layer 1
        if record.metadata.get("intentionally_disabled"):
            continue

        questions.append(self._generate_question(record))

    return questions
```

**User Override:**

CLI command to clear suppression:
```bash
kloros unsuppress orphaned_queue_episodes
```

Use case: D-REAM gets re-enabled later, user wants to re-investigate.

### Layer 3: Memory Management (curiosity_core_consumer)

Enhanced memory monitoring with automatic cleanup triggers.

**Current State:**
- Has `_check_memory_usage()` function
- Logs warning at 900MB
- Takes no action

**Enhancement:**
```python
def _check_memory_usage(self) -> None:
    """Check memory and trigger cleanup if needed."""
    try:
        mem_info = psutil.Process().memory_info()
        mem_mb = mem_info.rss / 1024 / 1024

        if mem_mb > 950:  # 95% of 1GB limit
            logger.error(f"Memory critical: {mem_mb:.1f}MB, triggering emergency cleanup")
            self._emergency_cleanup()
        elif mem_mb > 900:  # 90% threshold
            logger.warning(f"Memory high: {mem_mb:.1f}MB, triggering proactive cleanup")
            self._proactive_cleanup()
    except Exception as e:
        logger.debug(f"Error checking memory: {e}")

def _proactive_cleanup(self):
    """Release memory before hitting limits."""
    # 1. Trim old questions from feed (keep only last 100)
    if CURIOSITY_FEED.exists():
        with open(CURIOSITY_FEED, 'r') as f:
            feed = json.load(f)

        if len(feed.get('questions', [])) > 100:
            feed['questions'] = feed['questions'][-100:]
            with open(CURIOSITY_FEED, 'w') as f:
                json.dump(feed, f, indent=2)
            logger.info(f"Trimmed curiosity feed to 100 questions")

    # 2. Clear semantic_store cache if it has one
    if hasattr(self.semantic_store, 'clear_cache'):
        self.semantic_store.clear_cache()

    # 3. Garbage collect
    import gc
    gc.collect()

def _emergency_cleanup(self):
    """Aggressive cleanup at critical memory levels."""
    # 1. Trim to last 20 questions
    if CURIOSITY_FEED.exists():
        with open(CURIOSITY_FEED, 'r') as f:
            feed = json.load(f)
        feed['questions'] = feed['questions'][-20:]
        with open(CURIOSITY_FEED, 'w') as f:
            json.dump(feed, f, indent=2)
        logger.warning(f"Emergency: Trimmed curiosity feed to 20 questions")

    # 2. Clear all caches
    if hasattr(self.semantic_store, 'clear_cache'):
        self.semantic_store.clear_cache()

    # 3. Force garbage collection
    import gc
    gc.collect()

    # 4. Emit SYSTEM_HEALTH signal for external monitoring
    if hasattr(self, 'chem_pub'):
        self.chem_pub.emit("SYSTEM_HEALTH", {
            "component": "curiosity_core_consumer",
            "status": "memory_critical",
            "memory_mb": psutil.Process().memory_info().rss / 1024 / 1024
        })
```

**Memory Profiling (Diagnostic):**
```python
import tracemalloc

def __init__(self, ...):
    # Start memory profiling
    tracemalloc.start()
    self.last_memory_snapshot = time.time()

def _log_memory_top_consumers(self):
    """Log top memory consumers for diagnostics."""
    if time.time() - self.last_memory_snapshot < 300:  # Every 5 minutes
        return

    snapshot = tracemalloc.take_snapshot()
    top_stats = snapshot.statistics('lineno')

    logger.debug("[memory_profile] Top 10 memory consumers:")
    for stat in top_stats[:10]:
        logger.debug(f"  {stat}")

    self.last_memory_snapshot = time.time()
```

## LLM Fallback Fix

### Problem

**LLMRouter misconfiguration:**
- Configured for ports 8001/8002 (don't exist)
- Actual Ollama instances: 11434 (ollama-live, GPU 0), 11435 (ollama-think, GPU 1)

**knowledge_indexer bypass:**
- Hardcodes AltimitOS endpoint: `http://100.67.244.66:11434`
- No fallback when AltimitOS down
- Blocks autonomous knowledge indexing

### Solution

**1. Fix LLMRouter Port Configuration** (`reasoning/llm_router.py:63-88`)

```python
SERVICES = {
    LLMMode.LIVE: LLMService(
        name="ollama-live",
        port=11434,  # Changed from 8001
        model="llama3.1:8b",
        description="Fast chat and general queries (GPU 0)"
    ),
    LLMMode.THINK: LLMService(
        name="ollama-think",
        port=11435,  # Changed from 8001
        model="llama3.1:8b",
        description="Deep reasoning (GPU 1)"
    ),
    LLMMode.DEEP: LLMService(
        name="ollama-live",
        port=11434,
        model="llama3.1:8b",
        description="Deep analysis (GPU 0)"
    ),
    LLMMode.CODE: LLMService(
        name="ollama-think",
        port=11435,
        model="qwen2.5-coder:14b",
        description="Code generation (GPU 1)"
    ),
}
```

**2. Integrate knowledge_indexer with LLMRouter** (`kloros_memory/knowledge_indexer.py`)

```python
# Remove hardcoded config
# DELETE: self.llm_url, self.llm_model

from reasoning.llm_router import get_router, LLMMode

def _generate_summary(self, file_path: Path, content: str, file_type: str) -> str:
    """Generate LLM summary of file content."""
    prompt = self._build_summary_prompt(file_path, content, file_type)

    router = get_router()
    success, response, source = router.query(
        prompt=prompt,
        mode=LLMMode.DEEP,  # Documentation needs deep analysis
        prefer_remote=True   # Still prefer AltimitOS if available
    )

    if success:
        logger.info(f"[knowledge_indexer] Summary generated via {source}")
        return response.strip()
    else:
        logger.error(f"[knowledge_indexer] Summary generation failed: {response}")
        return "[Summary generation failed]"
```

**3. Remove Environment Variables**

Delete from service files and environment:
- `KLR_KNOWLEDGE_LLM_URL`
- `KLR_KNOWLEDGE_LLM_MODEL`

LLMRouter handles all routing decisions.

**Result:**

When AltimitOS is down, knowledge_indexer falls back to ollama-live/ollama-think automatically. Single source of truth for LLM routing.

## Implementation Phases

### Phase 1: Immediate Stopgap (Memory Relief)

Deploy Layer 3 memory management first.

**Changes:**
- Add `_proactive_cleanup()` and `_emergency_cleanup()` to curiosity_core_consumer
- Enhanced `_check_memory_usage()` with triggers
- Add memory profiling with tracemalloc

**Risk:** Low - only adds safety, no behavior changes

**Deployment:**
1. Edit `kloros/orchestration/curiosity_core_consumer_daemon.py`
2. Restart `kloros-curiosity-core-consumer.service`
3. Monitor logs for cleanup triggers
4. Monitor memory usage: `systemctl status kloros-curiosity-core-consumer.service`

**Success Metric:** Memory stays below 900MB for 1 hour

### Phase 2: Scanner Prevention (Root Cause)

Stop generating questions for disabled services.

**Changes:**
1. Create `registry/systemd_helpers.py` with `is_service_intentionally_disabled()`
2. Update capability scanners to check service state
3. Add CuriosityCore filter for `intentionally_disabled` metadata

**Files Modified:**
- `registry/systemd_helpers.py` (new)
- `registry/capability_scanners/*.py` (multiple scanners)
- `registry/curiosity_core.py`

**Risk:** Medium - changes question generation logic

**Deployment:**
1. Deploy code changes
2. Restart `kloros-curiosity-core-consumer.service`
3. Monitor question count: should drop immediately
4. Check logs for "Skipping intentionally disabled" messages

**Success Metric:** Zero new questions on orphaned_queue_episodes

### Phase 3: Evidence Learning (Self-Healing)

Add learning mechanism for unsolvable patterns.

**Changes:**
1. Add suppression tracking to `registry/semantic_evidence.py`
2. Implement `is_suppressed()` check
3. Update investigation consumer to track failures
4. Integrate suppression check into CuriosityCore

**Files Modified:**
- `registry/semantic_evidence.py`
- `kloros/orchestration/investigation_consumer_daemon.py`
- `registry/curiosity_core.py`

**Risk:** Medium - new learning mechanism

**Deployment:**
1. Deploy code changes
2. Restart investigation and curiosity consumers
3. Monitor semantic_evidence.json for suppression entries
4. Verify suppression prevents duplicate questions

**Success Metric:** After 5 failed attempts, capability marked suppressed and questions stop

### Phase 4: LLM Fallback (Resilience)

Enable local Ollama fallback for knowledge indexing.

**Changes:**
1. Fix LLMRouter port configuration (11434/11435)
2. Integrate knowledge_indexer with LLMRouter
3. Remove hardcoded AltimitOS endpoints

**Files Modified:**
- `reasoning/llm_router.py`
- `kloros_memory/knowledge_indexer.py`

**Risk:** Low - improves reliability, no new behavior

**Deployment:**
1. Deploy code changes
2. No service restart needed (kloros-memory is library)
3. Test: temporarily block AltimitOS endpoint, verify fallback
4. Monitor logs for "via local:ollama-live" messages

**Success Metric:** Knowledge indexing completes with local Ollama when AltimitOS down

## Testing Strategy

### Layer 1 Testing (Scanner Prevention)

**Unit Tests:**
```python
def test_is_service_intentionally_disabled():
    # Mock systemctl output
    assert is_service_intentionally_disabled("disabled-service") == True
    assert is_service_intentionally_disabled("enabled-service") == False
    assert is_service_intentionally_disabled("masked-service") == True

def test_scanner_marks_disabled_capabilities():
    scanner = RabbitMQScanner()
    records = scanner.scan()

    orphaned_queue = [r for r in records if r.name == "orphaned_queue_episodes"][0]
    assert orphaned_queue.metadata["intentionally_disabled"] == True

def test_curiosity_core_filters_disabled():
    core = CuriosityCore()
    matrix = CapabilityMatrix([
        CapabilityRecord(name="test", metadata={"intentionally_disabled": True})
    ])

    feed = core.generate_questions_from_matrix(matrix)
    assert len(feed.questions) == 0  # Filtered out
```

**Integration Test:**
1. Create test systemd service and disable it
2. Run capability scanner
3. Verify scanner marks capability as intentionally_disabled
4. Run CuriosityCore
5. Verify no questions generated

### Layer 2 Testing (Evidence Learning)

**Unit Tests:**
```python
def test_suppression_after_failures():
    store = SemanticEvidenceStore()

    # Simulate 5 failed investigations
    for _ in range(5):
        store.record_failure("orphaned_queue_episodes")

    assert store.is_suppressed("orphaned_queue_episodes") == True
    assert store.evidence["orphaned_queue_episodes"]["suppression"]["failure_count"] == 5

def test_user_override():
    store = SemanticEvidenceStore()
    store.suppress("test_capability")

    store.unsuppress("test_capability")
    assert store.is_suppressed("test_capability") == False
```

**Integration Test:**
1. Trigger 5 failed investigations on test capability
2. Verify suppression metadata appears in semantic_evidence.json
3. Verify CuriosityCore skips suppressed capability
4. Run unsuppress command
5. Verify capability no longer suppressed

### Layer 3 Testing (Memory Management)

**Unit Tests:**
```python
def test_proactive_cleanup_triggers():
    daemon = CuriosityCoreConsumerDaemon()

    # Mock memory at 90%
    with patch.object(psutil.Process, 'memory_info') as mock:
        mock.return_value.rss = 900 * 1024 * 1024
        daemon._check_memory_usage()

    # Verify proactive cleanup called
    assert cleanup_called

def test_emergency_cleanup_triggers():
    daemon = CuriosityCoreConsumerDaemon()

    # Mock memory at 95%
    with patch.object(psutil.Process, 'memory_info') as mock:
        mock.return_value.rss = 950 * 1024 * 1024
        daemon._check_memory_usage()

    # Verify emergency cleanup called and signal emitted
    assert emergency_cleanup_called
    assert system_health_signal_emitted
```

**Memory Profiling:**
1. Run daemon with memory profiling enabled
2. Generate 1000 questions
3. Trigger proactive cleanup
4. Verify memory reduction in logs
5. Check tracemalloc snapshots show reduction

### LLM Fallback Testing

**Unit Tests:**
```python
def test_llm_router_local_fallback():
    router = LLMRouter()

    # Mock AltimitOS timeout
    with patch('requests.get', side_effect=Timeout):
        success, response, source = router.query("test prompt")

    assert success == True
    assert source == "local:ollama-live"

def test_knowledge_indexer_uses_router():
    indexer = KnowledgeIndexer()

    with patch.object(LLMRouter, 'query') as mock:
        mock.return_value = (True, "Test summary", "local:ollama-live")
        summary = indexer._generate_summary(Path("test.md"), "content", "markdown")

    assert mock.called
    assert summary == "Test summary"
```

**Integration Test:**
1. Block AltimitOS endpoint with firewall rule
2. Trigger knowledge indexing
3. Verify summary generated via ollama-live
4. Check logs show "via local:ollama-live"
5. Unblock AltimitOS
6. Verify fallback to remote on next run

### End-to-End Test

**Scenario:** Disabled D-REAM services with orphaned queues

**Steps:**
1. Verify D-REAM services are disabled
2. Clear curiosity feed
3. Run full curiosity cycle (proactive generation)
4. Verify zero questions on orphaned queues
5. Monitor memory usage over 30 minutes
6. Block AltimitOS and trigger knowledge scan
7. Verify knowledge indexing completes via local Ollama

**Success Criteria:**
- No duplicate questions on orphaned_queue_episodes
- Memory stays below 800MB
- Knowledge indexing works with AltimitOS down
- All layers working together

## Success Metrics

**Memory Usage:**
- Target: Below 800MB steady state
- Warning threshold: 900MB
- Critical threshold: 950MB

**Question Generation:**
- Zero duplicate questions on disabled service capabilities
- Suppression kicks in after 5 failures
- Question count drops by 90% after Layer 2 deployment

**LLM Fallback:**
- Knowledge indexing completes with local Ollama when AltimitOS down
- Logs show successful fallback: "via local:ollama-live"
- No timeout errors in knowledge_indexer

**System Stability:**
- No OOM kills on curiosity-core-consumer
- No crash loops from investigation attempts
- Semantic evidence store grows bounded (suppression prevents unbounded growth)

## Migration Notes

**Configuration Changes:**
- Remove `KLR_KNOWLEDGE_LLM_URL` and `KLR_KNOWLEDGE_LLM_MODEL` from environment
- LLMRouter ports updated: 8001/8002 → 11434/11435

**Data Structure Changes:**
- `semantic_evidence.json` gains `suppression` metadata per capability
- `CapabilityRecord.metadata` may contain `intentionally_disabled` flag

**Service Restarts Required:**
- Phase 1: `kloros-curiosity-core-consumer.service`
- Phase 2: `kloros-curiosity-core-consumer.service`
- Phase 3: `kloros-curiosity-core-consumer.service`, `kloros-investigation-consumer.service`
- Phase 4: None (library change)

**Rollback Procedure:**

If issues arise:
1. Revert code changes via git
2. Restart affected services
3. Restore old curiosity_feed.json from backup
4. Monitor for stability

**Backup Before Migration:**
```bash
cp /home/kloros/.kloros/curiosity_feed.json /home/kloros/.kloros/curiosity_feed.json.backup
cp /home/kloros/.kloros/semantic_evidence.json /home/kloros/.kloros/semantic_evidence.json.backup
```

## Future Enhancements

**CLI Tool for Suppression Management:**
```bash
kloros suppress list                    # Show all suppressed capabilities
kloros suppress show <capability>       # Show suppression details
kloros unsuppress <capability>          # Clear suppression
kloros suppress add <capability> <reason>  # Manual suppression
```

**Adaptive Failure Threshold:**
- Currently hardcoded: 5 failures → suppress
- Could adapt based on capability priority
- CRITICAL capabilities: require 10 failures
- LOW capabilities: suppress after 3 failures

**Memory Leak Detection:**
- Track memory growth rate over time
- Alert if growth exceeds threshold (e.g., 10MB/hour)
- Automatic tracemalloc snapshot on leak detection

**GPU Layout Migration:**
- Current: ollama-live (GPU 0), ollama-think (GPU 1)
- Future: Migrate to different layout (pending separate design)
- LLMRouter abstraction makes this transparent to consumers

## Related Documentation

- ChemBus Implementation: `/home/kloros/src/kloros/orchestration/chem_proxy.py`
- Capability Evaluator: `/home/kloros/src/registry/capability_evaluator.py`
- CuriosityCore: `/home/kloros/src/registry/curiosity_core.py`
- LLM Router: `/home/kloros/src/reasoning/llm_router.py`
- Knowledge Indexer: `/home/kloros/src/kloros_memory/knowledge_indexer.py`

## Notes

**Why defense-in-depth?**

Single-layer fixes fail when assumptions break. Scanner prevention assumes we know all service mappings. Evidence learning handles unknown patterns. Memory management is the final safety net.

**Why 5 failures for suppression?**

Balance between learning and false positives. Too low (2-3) risks suppressing temporary issues. Too high (10+) wastes resources on truly unsolvable problems.

**Why Layer 3 first?**

Immediate risk mitigation. OOM kill is catastrophic. Memory management buys time while implementing deeper fixes.

**Why not fix LLMRouter ports first?**

Investigation loop is the critical issue driving memory exhaustion. LLM fallback is important but secondary to system stability.
