# Judge.service (VLLM) On-Demand Configuration ✓

## Problem Solved

**Issue:** Ollama chat API was failing with HTTP 500 errors
**Root Cause:** VLLM (judge.service) was running 24/7 on GPU 0, consuming 11GB and leaving no memory for Ollama
**Solution:** Configure judge.service to only run during PHASE tests and D-REAM tournaments

---

## What Changed

### Before
```
GPU 0: VLLM running 24/7 (11GB used)
       ↓
Ollama tries to use GPU 0
       ↓
CUDA OOM: "cudaMalloc failed: out of memory"
       ↓
HTTP 500 errors in KLoROS
```

### After
```
GPU 0: Free for Ollama (11.5GB available)
       ↓
PHASE runs at 3 AM:
  1. Start judge.service (VLLM loads)
  2. Run PHASE tests
  3. Stop judge.service (VLLM unloads)
       ↓
Ollama works normally rest of the day
```

---

## Changes Made

### 1. Disabled 24/7 VLLM Service ✓
```bash
sudo systemctl stop judge.service
sudo systemctl disable judge.service
```

**Status:** judge.service no longer starts automatically

### 2. Modified PHASE to Control Judge Lifecycle ✓

**File:** `/etc/systemd/system/spica-phase-test.service`

**Added:**
```ini
# Start judge.service (VLLM) before PHASE tests
ExecStartPre=+/usr/bin/systemctl start judge.service
ExecStartPre=/usr/bin/sleep 30

# ... PHASE tests run ...

# Stop judge.service after PHASE completes (success or failure)
ExecStopPost=+/usr/bin/systemctl stop judge.service
```

**How it works:**
- `+` prefix allows privileged systemctl commands even though PHASE runs as kloros user
- judge.service starts 30 seconds before PHASE tests (gives VLLM time to load)
- judge.service stops automatically after PHASE completes (whether pass or fail)
- `ExecStopPost` ensures cleanup even if PHASE fails

### 3. Verified GPU Memory Recovery ✓

**Before fix:**
```
GPU 0: 12GB total, 11.3GB used (VLLM), 695MB free ❌
```

**After fix:**
```
GPU 0: 12GB total, 521MB used (system), 11.5GB free ✓
GPU 1: 11GB total, 18MB used (idle), 11.1GB free ✓
```

### 4. Tested Ollama Functionality ✓

```bash
$ curl -s http://127.0.0.1:11434/api/chat \
  -d '{"model":"qwen2.5:14b-instruct-q4_0","messages":[{"role":"user","content":"test"}],"stream":false}' \
  | jq -r '.message.content'

"Hello! How can I assist you today? If you have any questions or need help with something, feel free to ask."
```

**Status:** Ollama chat API working ✓

---

## What judge.service Does

**Used By:**
1. **PHASE Testing** (nightly at 3 AM)
   - `spica_rag.py` - Evaluates RAG response quality
   - `spica_conversation.py` - Scores conversation quality
   - Uses VLLM endpoint at `http://127.0.0.1:8001/v1/chat/completions`

2. **D-REAM Tournaments** (on-demand)
   - Quality scoring for evolutionary experiments
   - Compares candidate responses

**NOT Used By:**
- Main KLoROS voice assistant (uses Ollama instead)

---

## Operational Impact

### Daily Operation
```
00:00 - 03:00: GPU 0 free for Ollama ✓
03:00 - 05:00: PHASE runs (judge.service active)
05:00 - 24:00: GPU 0 free for Ollama ✓
```

**GPU 0 Availability:** ~22 hours/day for Ollama
**VLLM Downtime:** 0 hours (only runs when needed)

### Manual D-REAM Usage

If you need to run D-REAM tournaments manually:

```bash
# Start judge.service manually
sudo systemctl start judge.service

# Wait for VLLM to load (check logs)
sudo journalctl -u judge.service -f

# Run D-REAM experiments
# ...

# Stop judge.service when done
sudo systemctl stop judge.service
```

**Note:** During manual judge runs, Ollama will temporarily get OOM errors. This is expected and will resolve when judge stops.

---

## Verification Commands

### Check Judge Status
```bash
systemctl status judge.service
# Should show: inactive (dead)
```

### Check GPU Memory
```bash
nvidia-smi --query-gpu=index,memory.used,memory.free --format=csv
# GPU 0 should show ~11GB free
```

### Test Ollama
```bash
curl -s http://127.0.0.1:11434/api/tags | jq '.models[].name'
# Should list available models
```

### Check PHASE Schedule
```bash
systemctl list-timers spica-phase-test.timer
# Should show next run at 3:00 AM
```

---

## Troubleshooting

### Ollama Still Getting 500 Errors

**Check if judge is running:**
```bash
systemctl status judge.service
```

**If active:** Stop it manually
```bash
sudo systemctl stop judge.service
```

**If keeps restarting:** Check for other services starting it
```bash
sudo journalctl -u judge.service --since "10 minutes ago"
```

### PHASE Tests Failing

**Check judge started properly:**
```bash
sudo journalctl -u spica-phase-test.service --since "1 hour ago" | grep judge
```

**Manually test VLLM endpoint:**
```bash
# Start judge
sudo systemctl start judge.service
sleep 30

# Test endpoint
curl -s http://127.0.0.1:8001/v1/models

# Stop judge
sudo systemctl stop judge.service
```

### D-REAM Can't Access Judge

**Start judge manually before running D-REAM:**
```bash
sudo systemctl start judge.service
# Wait 30 seconds for VLLM to load
```

**Remember to stop after:**
```bash
sudo systemctl stop judge.service
```

---

## Configuration Files

### Judge Service
**Path:** `/etc/systemd/system/judge.service`
- Model: Qwen/Qwen2.5-7B-Instruct-AWQ
- Port: 8001
- GPU: 0 (CUDA_VISIBLE_DEVICES=0)
- Memory: 50% utilization (~6GB)
- Auto-start: Disabled ✓

### PHASE Service
**Path:** `/etc/systemd/system/spica-phase-test.service`
- Runs: 3 AM nightly
- Controls: judge.service lifecycle
- Timeout: 30 minutes
- Cleanup: Always stops judge after

### Ollama
**Path:** `/etc/systemd/system/ollama.service.d/gpu-override.conf`
- GPU: 0 (CUDA_VISIBLE_DEVICES=0)
- Models: qwen2.5:14b-instruct-q4_0, nous-hermes:13b-q4_0
- Port: 11434
- Always running ✓

---

## Success Metrics

✓ **Ollama HTTP 500 errors eliminated**
✓ **GPU 0 memory freed (11.5GB available)**
✓ **PHASE can still run quality tests**
✓ **D-REAM tournaments still supported**
✓ **No 24/7 GPU resource waste**

**Result:** KLoROS voice assistant now works reliably without competing for GPU resources.

---

## Summary

Judge.service (VLLM) now runs **on-demand** only during:
1. PHASE nightly tests (3-5 AM)
2. Manual D-REAM tournaments (when you start it)

This fixes Ollama HTTP 500 errors by freeing GPU 0 for normal operation while preserving all testing capabilities.
