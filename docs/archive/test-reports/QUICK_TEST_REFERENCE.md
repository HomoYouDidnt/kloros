# Quick Test Reference Card

## Fast System Verification

To quickly verify the RAG backend and voice pipeline are working:

```bash
# Quick test (30 seconds)
python3 /home/kloros/test_voice_rag_integration.py

# Comprehensive test (2 minutes)
python3 /home/kloros/test_rag_end_to_end.py
```

## What to Look For

### Success Indicators ✓
- "ALL CRITICAL TESTS PASSED"
- "Embedding dimension is 384 (CORRECT)"
- "ZERO matmul errors detected"
- "Voice service running"
- Success rate > 90%

### Failure Indicators ✗
- "MATMUL ERROR DETECTED"
- "Embedding dimension is 768"
- "RAG backend not initialized"
- Voice service not running

## Quick Checks

### 1. Voice Service Status
```bash
ps aux | grep kloros_voice | grep -v grep
```
Expected: Process running (PID should be shown)

### 2. RAG Dimension Check
```bash
python3 -c "
import numpy as np
data = np.load('/home/kloros/rag_data/rag_store.npz', allow_pickle=True)
print(f'Embeddings shape: {data[\"embeddings\"].shape}')
print(f'Expected: (427, 384)')
print(f'Dimension: {data[\"embeddings\"].shape[1]}')
"
```
Expected output: `Dimension: 384`

### 3. Log Check for Errors
```bash
tail -100 /tmp/kloros.log | grep -i -E "matmul|dimension|error" | wc -l
```
Expected: `0` (no errors)

### 4. Healing Playbook Verification
```bash
grep -q "rag.processing_error.autofix" /home/kloros/self_heal_playbooks.yaml && echo "✓ Playbook ready" || echo "✗ Playbook missing"
```
Expected: `✓ Playbook ready`

## Test Results Interpretation

### 92.9% Success Rate (26/28 passed)
- **GOOD** - System operational
- 2 failures are non-critical (missing optional dependencies)

### 100% Success Rate (all critical tests)
- **EXCELLENT** - All systems fully operational

### < 90% Success Rate
- **ACTION NEEDED** - Investigate failures

## Common Issues

### Issue: "No module named 'qdrant_client'"
**Impact:** None (optional dependency)
**Fix (optional):** `pip install qdrant-client`

### Issue: "ChromaDB directory not found"
**Impact:** None (alternative backend not in use)
**Fix (optional):** Create directory if needed

### Issue: "Embedding dimension is 768"
**Impact:** CRITICAL - RAG will fail with matmul errors
**Fix:** Re-run embedding truncation script
**Verify:** Check `/home/kloros/rag_data/rag_store.npz`

### Issue: "Voice service not running"
**Impact:** Voice pipeline offline
**Fix:** Restart voice service
**Command:** Check startup scripts

## Performance Benchmarks

| Metric | Expected | Critical Threshold |
|--------|----------|-------------------|
| Retrieval Latency | < 0.01s | < 0.1s |
| Query Success Rate | 100% | > 95% |
| Matmul Error Rate | 0% | 0% |
| Voice Service Uptime | Continuous | N/A |

## Files and Locations

### Test Scripts
- `/home/kloros/test_rag_end_to_end.py` - Comprehensive test (28 tests)
- `/home/kloros/test_voice_rag_integration.py` - Quick integration test

### Reports
- `/home/kloros/TEST_REPORT_RAG_VOICE_PIPELINE.md` - Detailed report (389 lines)
- `/home/kloros/TESTING_SUMMARY.txt` - Executive summary

### Configuration
- `/home/kloros/self_heal_playbooks.yaml` - Healing configuration
- `/home/kloros/rag_data/rag_store.npz` - RAG embeddings and metadata

### Logs
- `/tmp/kloros.log` - Voice service log
- `~/.kloros/logs/exception_monitor.log` - Exception monitoring

## Emergency Diagnostics

If tests fail, run these diagnostics:

```bash
# 1. Check RAG file integrity
python3 -c "import numpy as np; d=np.load('/home/kloros/rag_data/rag_store.npz', allow_pickle=True); print(f'Keys: {list(d.keys())}'); print(f'Shape: {d[\"embeddings\"].shape}')"

# 2. Check voice service logs
tail -50 /tmp/kloros.log

# 3. Check for recent errors
grep -i error /tmp/kloros.log | tail -20

# 4. Verify healing playbook
grep -A 10 "rag.processing_error" /home/kloros/self_heal_playbooks.yaml
```

## Contact and Support

**System:** ASTRAEA (KLoROS)
**Test Suite Version:** 2025-11-22
**Last Verified:** 2025-11-22 19:52:00

---

**Quick Status Check:**
```bash
python3 /home/kloros/test_voice_rag_integration.py 2>&1 | grep -E "STATUS:|System Status:"
```

Expected output:
```
STATUS: ✓✓✓ ALL CRITICAL TESTS PASSED - SYSTEM OPERATIONAL ✓✓✓
System Status: READY FOR PRODUCTION
```
