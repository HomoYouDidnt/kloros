# Voice Environment Testing Guide

## Current Status

**Text Interface**: ✅ Working (consciousness fully integrated and tested)
**Voice Interface**: ⚠️ Not yet tested (needs voice dependencies)

## Quick Test: Text-Only Mode (Works Now)

The consciousness integration is **fully working** in text mode:

```bash
python3 scripts/standalone_chat.py
```

You should see:
```
[consciousness] 🧠 Integrated consciousness initialized (Phase 1 + Phase 2)
[consciousness] Initial mood: Feeling seeking
[expression] 🛡️ Expression filter initialized (cooldown=5.0s)
```

Then chat normally. If the system generates a policy change, you'll see grounded expressions like:
- `[Enabling verification (uncertainty: 0.7)]`
- `[beam_width: 1→2 (curiosity: 0.8)]`

## Testing Voice Interface

### Prerequisites

#### 1. Voice Dependencies (Currently Missing ❌)

```bash
# Install Python packages
pip install vosk sounddevice webrtcvad

# Piper TTS (install separately)
# See: https://github.com/rhasspy/piper
```

#### 2. Voice Models (Currently Missing ❌)

**Vosk Model** (for speech recognition):
```bash
# Download small English model (~40MB)
mkdir -p ~/models/vosk
cd ~/models/vosk
wget https://alphacephei.com/vosk/models/vosk-model-small-en-us-0.15.zip
unzip vosk-model-small-en-us-0.15.zip
mv vosk-model-small-en-us-0.15 model

# Or use larger model for better accuracy
# https://alphacephei.com/vosk/models
```

**Piper TTS Model** (for voice output):
```bash
# Download GLaDOS voice or any Piper voice
mkdir -p ~/KLoROS/models/piper
cd ~/KLoROS/models/piper

# Example: Download a voice
# See: https://github.com/rhasspy/piper/releases
# Or use any .onnx model you prefer
```

#### 3. Microphone (Required for voice)

The system expects a USB microphone (prefers CMTECK, but will auto-detect):
```bash
# List available audio devices
python3 -c "import sounddevice; print(sounddevice.query_devices())"
```

#### 4. Ollama (Already Running ✅)

```bash
# Verify Ollama is running
curl http://localhost:11434/api/version
```

### Test Procedure (Once Dependencies Installed)

#### Option 1: Test Voice Service Directly

```bash
# Run the main voice interface
python3 src/kloros_voice.py
```

**Expected output:**
```
[consciousness] 🧠 Integrated consciousness initialized (Phase 1 + Phase 2)
[consciousness] Initial mood: Feeling seeking
[expression] 🛡️ Expression filter initialized (cooldown=5.0s)
[audio] auto-detected preferred mic: CMTECK (device 2)
[vosk] Wake word model loaded from /home/kloros/models/vosk/model
[voice] ✓ Voice stack integration verified
```

Then say "KLoROS" to trigger wake word, followed by a command.

#### Option 2: Test Streaming Voice Interface

```bash
# Run the streaming voice interface
python3 src/kloros_voice_streaming.py
```

Same expected output, but with streaming audio processing.

#### Option 3: Test Without Full Voice Stack

If you just want to verify consciousness integration without audio:

```bash
# Disable audio components but keep reasoning
export KLR_ENABLE_AUDIO=0
export KLR_ENABLE_STT=0
export KLR_ENABLE_TTS=0
export KLR_ENABLE_WAKEWORD=0
export KLR_ENABLE_AFFECT=1  # Keep consciousness enabled

# Run voice service (will use text fallback)
python3 src/kloros_voice.py
```

This will initialize consciousness but skip audio stack.

### What to Look For

#### Consciousness Initialization Messages

```
[consciousness] 🧠 Integrated consciousness initialized (Phase 1 + Phase 2)
[consciousness] Initial mood: Feeling seeking
[expression] 🛡️ Expression filter initialized (cooldown=5.0s)
```

If you see these, consciousness is working!

#### Expression Generation During Use

When the system's affect changes enough to trigger a policy change, you'll see expressions in responses:

```
User: "What is the weather?"
KLoROS: [Enabling verification (uncertainty: 0.7)] I don't have access to weather data, but I can help you find that information...
```

The `[Enabling verification (uncertainty: 0.7)]` part is the grounded affective expression showing:
- **What changed**: Enabling verification
- **Why**: Uncertainty level at 0.7
- **Guardrails**: Must cite measurement, must have policy change, respects cooldown

### Verification Without Voice

If you can't/don't want to set up the full voice stack, you can verify the integration exists:

```bash
# Check that integration calls are present
grep -n "integrate_consciousness" src/kloros_voice.py
grep -n "process_consciousness_and_express" src/kloros_voice.py

# Should show:
# Line 554: from src.consciousness.integration import integrate_consciousness
# Line 555: integrate_consciousness(self, cooldown=5.0, max_expressions=10)
# Line 1599: from src.consciousness.integration import process_consciousness_and_express
# Line 3404: from src.consciousness.integration import process_consciousness_and_express
```

## Troubleshooting

### "No module named 'vosk'"
Install dependencies: `pip install vosk sounddevice webrtcvad`

### "Wake word model load failed"
Download Vosk model to `~/models/vosk/model/`

### "TTS backend initialization failed"
Install Piper TTS and download a voice model

### "auto-detected preferred mic: None"
- Check USB mic is plugged in
- Run `python3 -c "import sounddevice; print(sounddevice.query_devices())"`
- Set manually: `export KLR_INPUT_IDX=2` (use correct device index)

### Consciousness doesn't initialize
Check environment variable: `echo $KLR_ENABLE_AFFECT` (should be "1" or unset)

### No expressions appearing
This is normal! Expressions only appear when:
1. Affect changes enough to trigger policy change
2. Cooldown period (5s) has passed since last expression
3. Haven't hit session limit (10 expressions)

To trigger expressions, try tasks that create uncertainty, curiosity, or fatigue.

## Testing Checklist

- [ ] Install voice dependencies (`pip install vosk sounddevice webrtcvad`)
- [ ] Download Vosk model to `~/models/vosk/model/`
- [ ] Install Piper TTS (optional, for voice output)
- [ ] Download Piper voice model (optional)
- [ ] Verify Ollama is running (`curl http://localhost:11434/api/version`)
- [ ] Plug in USB microphone
- [ ] Run text interface test first: `python3 scripts/standalone_chat.py`
- [ ] Run voice interface: `python3 src/kloros_voice.py`
- [ ] Look for consciousness init messages
- [ ] Try triggering expressions through conversation

## Minimal Test (No Audio)

If you just want to confirm the integration code works:

```bash
# Set environment to skip audio but enable consciousness
export KLR_ENABLE_AUDIO=0
export KLR_ENABLE_STT=0
export KLR_ENABLE_TTS=0
export KLR_ENABLE_AFFECT=1

# Check integration is present
python3 -c "
import sys
sys.path.insert(0, '/home/kloros')
from src.consciousness.integration import integrate_consciousness
print('✅ Integration module loads successfully')
"
```

## Summary

**Right now**: Text interface fully working ✅
- Run: `python3 scripts/standalone_chat.py`
- Consciousness + expressions working

**To test voice**: Need dependencies + models
- Install: `pip install vosk sounddevice webrtcvad`
- Download: Vosk model + optionally Piper TTS
- Run: `python3 src/kloros_voice.py`

**Integration status**:
- Code is integrated in all entry points ✅
- Text mode verified working ✅
- Voice mode needs environment setup ⚠️

---

**Need help?** Check existing logs or run diagnostics:
```bash
python3 scripts/standalone_chat.py
# Then in chat: "Show me your affective diagnostics"
```
