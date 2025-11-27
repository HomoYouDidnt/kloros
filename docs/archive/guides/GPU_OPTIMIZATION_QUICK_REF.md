# GPU Optimization - Quick Reference Card

**Date**: 2025-10-28  
**Status**: ✅ DEPLOYED & OPERATIONAL

---

## What Changed

✅ **Whisper Model**: small → **tiny** (4-6x faster STT)  
❌ **VLLM Allocation**: 50% → 40% (failed, rolled back)

---

## Performance Gains

| Metric | Before | After |
|--------|--------|-------|
| STT Latency | 300ms | 50-85ms |
| Model Memory | 1.5GB | 500MB |
| GPU Free | 931MB | 4167MB |

---

## Current Config

```
Whisper: tiny model on cuda:0
VLLM: 50% GPU allocation
Status: All services active ✅
```

---

## Rollback (if needed)

```bash
# Quick rollback to small Whisper
sudo sed -i 's/ASR_WHISPER_SIZE=tiny/ASR_WHISPER_SIZE=small/' /etc/systemd/system/kloros.service
sudo sed -i 's/ASR_WHISPER_SIZE=tiny/ASR_WHISPER_SIZE=small/' /home/kloros/.kloros_env.clean
sudo systemctl daemon-reload && sudo systemctl restart kloros
```

---

## Monitor

```bash
# Check STT performance
sudo journalctl -u kloros -f | grep stt

# GPU memory
nvidia-smi

# Service health
systemctl status kloros judge
```

---

## Documentation

- `FINAL_DEPLOYMENT_REPORT.md` - Full analysis
- `DEPLOYMENT_SUMMARY.md` - Quick overview
- `VLLM_ALLOCATION_TEST_REPORT.md` - Why 40% failed
- `GPU_FIX_REPORT.md` - Bug fix details

---

**Autonomous Discovery**: KLoROS found this optimization via D-REAM experiments  
**Net Impact**: Voice interactions significantly faster 🚀
