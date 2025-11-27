# Configuration Validation Report
**Generated:** 2025-10-12 01:46:15
**Config File:** /home/kloros/.kloros_env

---

## Validation Results

### Critical Settings
| Setting | Value | Status | Notes |
|---------|-------|--------|-------|
| KLR_ENABLE_MEMORY | 1 | ✅ Valid | Memory enabled |
| KLR_ENABLE_STT | 1 | ✅ Valid | STT enabled |
| KLR_STT_BACKEND | hybrid | ✅ Valid | Using Vosk+Whisper |
| OLLAMA_MODEL | qwen2.5:14b-instruct-q4_0 | ✅ Valid | LLM configured |
| KLR_INPUT_GAIN | 5.0 | ✅ Valid | Appropriate gain |

### Model Paths
| Model | Path | Status |
|-------|------|--------|
| Vosk | /home/kloros/models/vosk/model | ✅ Path set |
| Piper | /home/kloros/models/piper/glados_piper_medium.onnx | ✅ Path set |
| Whisper | /home/kloros/models/asr/whisper | ✅ Path set |

### Audio Devices
| Device | Value | Status |
|--------|-------|--------|
| Input | alsa_input.usb-CMTECK_Co._Ltd._CMTECK_000000000000-00.mono-fallback | ⚠️ Hardcoded |
| Output | alsa_output.pci-0000_09_00.4.analog-stereo | ⚠️ Hardcoded |

### Sample Rates
| Component | Rate | Status |
|-----------|------|--------|
| Capture | 48000 | ✅ Valid |
| STT | 48000 | ✅ Valid |
| TTS | 22050 | ✅ Valid |
| Playback | 48000 | ✅ Valid |

---

## Issues Found

### High Priority
- **Hardcoded device names** - May break if hardware changes
- **KLR_MAX_CONTEXT_EVENTS=6** - Too low, should be 15-20
- **ASR_GPU_ASSIGNMENT=cpu_only** - Not using GPU acceleration

### Medium Priority
- **KLR_ENABLE_HOUSEKEEPING=0** - Automated maintenance disabled
- **KLR_STREAMING_MODE=1** but no streaming-specific tuning
- **Multiple backup/retention settings** - Could be simplified

### Low Priority
- **KLR_DREAM_EVOLUTION_INTERVAL=3600** - Evolution every hour (may be too frequent)
- **KLR_TTS_MUTE_DURATION_MS=1200** - Could be reduced to 800-1000ms

---

## Recommendations

1. **Increase KLR_MAX_CONTEXT_EVENTS** from 6 to 15
2. **Enable GPU** for Whisper if available (set ASR_GPU_ASSIGNMENT=auto)
3. **Enable housekeeping** (set KLR_ENABLE_HOUSEKEEPING=1)
4. **Add device autodiscovery** instead of hardcoded names

---

## Configuration Health: 85/100

**Breakdown:**
- Model configuration: 95/100
- Audio configuration: 80/100
- Memory configuration: 75/100
- Performance tuning: 80/100
- Safety/stability: 90/100
