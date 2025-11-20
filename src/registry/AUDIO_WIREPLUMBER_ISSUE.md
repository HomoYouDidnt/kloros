# Audio Input Intermittent Failure: WirePlumber Session Management

**Issue ID**: AUDIO-WIREPLUMBER-001
**Discovered**: 2025-10-23
**Severity**: Medium (intermittent loss of microphone)
**Status**: ✅ Detection improved, self-healing pattern documented

## Problem

WirePlumber (PipeWire session manager) intermittently loses track of audio input sources, causing microphone access to fail despite:
- ALSA showing capture devices
- PulseAudio daemon running
- PipeWire daemon running
- User in `audio` group

## Symptoms

```bash
# ALSA sees microphones:
$ arecord -l
card 3: CMTECK, device 0: USB Audio  ✓

# PipeWire has no input sources:
$ pactl list short sources
6321  alsa_output...monitor  ← Only output monitor, no inputs!

# PipeWire objects missing Audio/Source:
$ pw-dump | grep media.class
"Audio/Sink": 1    ✓
"Audio/Source": 0  ✗ ← Missing!
```

## Root Cause

WirePlumber fails to create Audio/Source objects from ALSA capture devices. Exact trigger unknown, but occurs:
- After system uptime > 24h
- After user session changes
- Intermittently (not 100% reproducible)

## Detection

**Old health check** (false positive):
```yaml
health_check: "pactl list short sources"  # Passes if ANY source exists (monitors count)
```

**New health check** (accurate):
```yaml
health_check: "bash:pactl list short sources | grep -v monitor | grep -q ."
# Only passes if ACTUAL input source exists (not just monitors)
```

**File**: `/home/kloros/src/registry/capabilities_enhanced.yaml:23`

## Fix (Manual)

```bash
# Restart WirePlumber to recreate sources:
sudo -u kloros XDG_RUNTIME_DIR=/run/user/1001 systemctl --user restart wireplumber

# Verify sources restored:
pactl list short sources | grep -v monitor
# Should show: alsa_input.usb-CMTECK...
```

## Autonomous Self-Healing Pattern

When capability evaluation detects this failure, the autonomous curiosity system should:

### Phase 1: Detection (Every 10 min)
```
[curiosity] Evaluating capabilities...
[curiosity] audio.input: MISSING
[curiosity] Why: Health check failed (no input sources)
[curiosity] State transition: OK → MISSING (recoverable failure)
```

### Phase 2: Investigation
```
[curiosity] Top question [8.5]: "What causes audio.input to fail intermittently?"
[curiosity] Hypothesis: WIREPLUMBER_SOURCE_LOSS

Diagnostic probes (safe, read-only):
1. Check WirePlumber status: systemctl --user status wireplumber
2. Count PipeWire sources: pw-dump | grep Audio/Source | wc -l
3. Check ALSA devices: arecord -l
4. Check runtime dir: ls /run/user/1001/

Expected findings:
- WirePlumber: RUNNING (but not creating sources)
- PipeWire sources: 0
- ALSA devices: Present
- Diagnosis: WirePlumber session desync
```

### Phase 3: Propose Fix
```
[autonomy] Detected known pattern: AUDIO-WIREPLUMBER-001
[autonomy] Proposed action: Restart wireplumber service
[autonomy] Command: systemctl --user restart wireplumber
[autonomy] Risk: low (user service, no data loss)
[autonomy] Confidence: 0.91 (based on previous success)
[autonomy] User approval required: yes (Autonomy Level 2)
```

### Phase 4: Learn Pattern
```
[memory] Logged event:
  - Failure: audio.input (wireplumber source loss)
  - Frequency: Every 18-36 hours
  - Fix: wireplumber restart (100% success rate in 3 trials)
  - Pattern: Runtime directory session cleanup related

[curiosity] Generated question:
  "What systemd service dependency prevents WirePlumber session loss?"

[autonomy] Future proposal:
  Add systemd dependency: pipewire-session-manager.target
  Or: Add watchdog to auto-restart wireplumber on source loss
```

## Prevention (Future)

Possible systemd configuration to prevent issue:

```ini
# /etc/systemd/user/wireplumber.service.d/override.conf
[Service]
Restart=on-failure
RestartSec=5s

# Restart if sources disappear
ExecStartPost=/bin/bash -c 'sleep 2 && pactl list short sources | grep -v monitor | grep -q .'
```

## Verification

After fix applied (2025-10-23):

**Before:**
```json
{
  "key": "audio.input",
  "state": "ok",  ← FALSE POSITIVE!
  "why": "OK: 6321 alsa_output...monitor"  ← Output monitor, not input
}
```

**After:**
```json
{
  "key": "audio.input",
  "state": "ok",
  "why": "Test passed",  ← Actual input source verified
  "provides": ["mic_stream", "levels", "vad"]
}
```

**When WirePlumber fails again:**
```json
{
  "key": "audio.input",
  "state": "missing",  ← CORRECTLY DETECTED
  "why": "Test failed: rc=1"  ← No input sources found
}
```

---

## For KLoROS's Autonomous Learning

**This is a perfect test case** for developing:
1. **Failure pattern recognition** - Intermittent failures that self-heal
2. **Safe remediation** - User service restart (low risk)
3. **Confidence building** - Track success rate of proposed fixes
4. **Proactive prevention** - Eventually configure systemd to prevent issue

**Next time this fails**, KLoROS should:
- Detect within 10 minutes (next capability evaluation)
- Recognize the pattern (if seen before)
- Propose the fix with high confidence
- Learn from the outcome

**Expected behavior**: After 3-5 occurrences, KLoROS should propose making it permanent via systemd configuration.

---

**Status**: ✅ Detection improved, pattern documented, waiting for autonomous learning to mature
**Last occurrence**: 2025-10-23 22:18 (fixed by manual wireplumber restart)
**Success rate**: 1/1 (100% - first detected occurrence)
