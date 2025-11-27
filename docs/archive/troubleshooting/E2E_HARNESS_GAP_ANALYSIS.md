# E2E Test Harness Gap Analysis

**Status**: The GPT-designed E2E harness assumes several capabilities that **don't currently exist** in KLoROS. This document identifies all mismatches between the harness design and actual implementation.

---

## ❌ CRITICAL: Missing Infrastructure

### 1. **NO MQTT / Message Bus**
**Harness Assumes**:
- MQTT broker on port 1883
- Topics: `kloros/#`, `ace/#`, `ace/summary/published`, `devops/changelog`

**Reality**:
- KLoROS has **zero MQTT integration**
- No message bus architecture at all
- No pub/sub event system

**Fix Required**: Either:
- Option A: Add MQTT client to KLoROS (`paho-mqtt`)
- Option B: Replace harness bus probe with log file monitoring

---

### 2. **NO ASR Ingress (FIFO/HTTP)**
**Harness Assumes**:
- FIFO at `/tmp/kloros_asr_in.fifo` OR
- HTTP POST endpoint at `http://127.0.0.1:8123/asr/ingest`

**Reality**:
- KLoROS uses **live audio capture** via `sounddevice` (src/audio/capture.py)
- No mechanism to inject pre-recorded WAV files
- No HTTP server for audio ingestion

**Fix Required**:
Create one of:
- FIFO reader thread that treats bytes as live audio stream
- FastAPI endpoint `/asr/ingest` that queues WAV for STT
- Alternative: Use `paplay` to inject WAV into PulseAudio virtual source

---

### 3. **NO TTS Output Tracking**
**Harness Assumes**:
- Last TTS WAV written to `/tmp/kloros_tts_out.wav`
- OR final text log at `/var/log/kloros/final_reply.jsonl`

**Reality**:
- TTS backend (Piper) generates audio but **doesn't save "last reply" file**
- No dedicated final_reply.jsonl log
- Structured logs exist but don't have a `phase="final_response"` entry

**Fix Required**:
Add to kloros_voice.py after TTS:
```python
# After generating TTS audio
if self.tts_backend:
    last_wav_path = "/tmp/kloros_tts_out.wav"
    # Copy or symlink last generated audio to this path

# Log final text
self.json_logger.log(
    level="INFO",
    phase="final_response",
    final_text=response,
    latency_ms=int((time.time() - t_start) * 1000),
    tool_calls=tool_count,
    trace_id=trace_id
)
```

---

## 📂 Path Mismatches

### Logs
| Harness Path | Actual Path |
|-------------|-------------|
| `/var/log/kloros/structured.jsonl` | `~/.kloros/logs/kloros-YYYYMMDD.jsonl` |
| `/var/log/kloros/final_reply.jsonl` | **Doesn't exist** |

**Fix**: Update `harness.toml`:
```toml
structured_log_path = "/home/kloros/.kloros/logs/kloros-current.jsonl"
# (requires rotation_mode="size" in KLR_LOG_ROTATE_MODE)
```

### Artifacts
| Harness Path | Actual Reality |
|-------------|---------------|
| `/var/kloros/out/ace_bullets.md` | **ACE bullets stored in ChromaDB only** (`~/.kloros/chroma_data`) |
| `/var/kloros/out/weekly_changelog.md` | **No changelog tool exists** |

---

## 🔧 Missing Tools

The test scenarios assume these tools exist in the introspection registry:

### ❌ Missing: `summarize_error_logs`
**What Harness Expects**:
"Summarize today's error logs and produce ACE bullets"

**What Actually Exists**:
- `check_recent_errors` - reads last N errors from memory.db (src/introspection_tools.py:696)
- Does NOT summarize
- Does NOT produce ACE bullets
- Does NOT write to `/var/kloros/out/ace_bullets.md`

**Tools You Have**:
```python
check_recent_errors(limit=10)  # Returns formatted string
get_dream_report()             # D-REAM status, not ACE
```

**Fix Required**: Add new tool:
```python
def _summarize_and_export_ace_bullets(self, kloros_instance, **kwargs):
    """Summarize recent errors and export ACE bullets to markdown."""
    # 1. Call check_recent_errors(limit=50)
    # 2. Analyze patterns (group by component, error_type)
    # 3. Generate ACE bullets via ace.generator.BulletGenerator
    # 4. Write to /var/kloros/out/ace_bullets.md
    # 5. Optionally publish to MQTT if implemented
    return "Summary saved to ace_bullets.md"
```

### ❌ Missing: `generate_changelog`
**What Harness Expects**:
"Draft weekly changelog since last tag and save as markdown"

**Reality**:
- No git log parsing tool
- No changelog formatting tool
- No tool to write markdown artifacts

**Fix Required**: Add tool:
```python
def _generate_changelog(self, kloros_instance, since="last_tag", **kwargs):
    """Generate changelog from git log."""
    import subprocess, re

    # Get last tag
    result = subprocess.run(
        ["git", "describe", "--tags", "--abbrev=0"],
        capture_output=True, text=True, cwd="/home/kloros"
    )
    last_tag = result.stdout.strip()

    # Get commits since tag
    result = subprocess.run(
        ["git", "log", f"{last_tag}..HEAD", "--oneline"],
        capture_output=True, text=True, cwd="/home/kloros"
    )

    # Format as markdown
    changelog = f"# Changelog\n\n## Since {last_tag}\n\n"
    for line in result.stdout.splitlines():
        match = re.match(r"^([a-f0-9]+) (.+)$", line)
        if match:
            sha, msg = match.groups()
            # Categorize: feat|fix|refactor|docs|test
            if msg.startswith("feat"):
                changelog += f"### Added\n- {msg}\n"
            # ... etc

    # Write to file
    Path("/var/kloros/out/weekly_changelog.md").parent.mkdir(exist_ok=True)
    Path("/var/kloros/out/weekly_changelog.md").write_text(changelog)

    return f"Changelog saved ({len(result.stdout.splitlines())} commits)"
```

---

## 📊 Structured Log Format

### What Harness Expects
```json
{
  "ts": "2025-10-13T...",
  "trace_id": "abc123",
  "phase": "final_response",
  "latency_ms": 3120,
  "tool_calls": 5,
  "final_text": "I've summarized today's errors..."
}
```

### What KLoROS Actually Logs
Currently (src/logging/json_logger.py:192):
- Writes JSONL with `timestamp`, `level`, `message`, `trace_id`, but **no `phase` field**
- No `latency_ms` or `tool_calls` tracking in final turn

**Fix Required**:
Update kloros_voice.py `chat()` method to emit:
```python
self.json_logger.log(
    level="INFO",
    phase="final_response",  # NEW
    trace_id=trace_id,
    latency_ms=latency,      # NEW
    tool_calls=tool_count,   # NEW
    final_text=response      # NEW
)
```

---

## 🛠️ Systemd Service Names

### Harness Assumes
```python
inject_fault("kill:tts_service")  # systemctl restart kloros-tts.service
inject_fault("kill:whisper")      # pkill -f whisper
```

### What Actually Exists
- `kloros-dream.service` (D-REAM runner, logs to `/var/log/kloros/dream.log`)
- No `kloros-tts.service`
- No separate whisper service

**Current KLoROS Services**:
```bash
$ ls /home/kloros/systemd/
kloros-dream.service  # Only one
```

**Fix Required**:
Create systemd units if you want fault injection:
```ini
# ~/.config/systemd/user/kloros-tts.service
[Unit]
Description=KLoROS TTS Service

[Service]
Type=simple
ExecStart=/home/kloros/.venv/bin/python /home/kloros/src/tts_service.py
Restart=always

[Install]
WantedBy=default.target
```

Then update `harness/faults.py` mapping.

---

## ✅ What DOES Exist and Matches

### Logs
- ✅ JsonFileLogger at `~/.kloros/logs/` (configurable via `KLR_LOG_DIR`)
- ✅ Daily rotation mode with `kloros-YYYYMMDD.jsonl`
- ✅ Size rotation mode with `kloros-current.jsonl`

### ACE System
- ✅ ACE BulletStore (ChromaDB) at `~/.kloros/chroma_data`
- ✅ BulletGenerator (src/ace/generator.py)
- ⚠️ BUT: No export-to-markdown functionality

### Tools
- ✅ `check_recent_errors` - reads from memory.db
- ✅ `get_dream_report` - D-REAM evolution status
- ✅ `system_diagnostic` - full health check
- ✅ `explain_reasoning` - XAI trace

---

## 🎯 Recommended Implementation Path

### Phase 1: Minimum Viable E2E (No MQTT, No FIFO)
Replace message bus with log monitoring:

1. **TTS Output Tracking**:
   - Save last TTS to `/tmp/kloros_tts_out.wav`
   - OR append to `final_reply.jsonl`

2. **Structured Logs**:
   - Add `phase="final_response"` log entry
   - Include `latency_ms`, `tool_calls`, `final_text`

3. **Simplified Harness**:
   - Remove MQTT probe
   - Remove ASR ingress (use text-mode chat for now)
   - Use log file polling instead of events

4. **Test Scenarios**:
   - Text-based prompts (bypass ASR)
   - Assert on log entries + artifact files
   - Skip speech synthesis verification

### Phase 2: Full Audio Path
1. Add HTTP ASR endpoint:
```python
# src/api/asr_ingress.py
from fastapi import FastAPI, UploadFile
app = FastAPI()

@app.post("/asr/ingest")
async def ingest_audio(audio: UploadFile):
    # Save to temp, feed to STT, enqueue transcript
    ...
```

2. Piper TTS wrapper to save output WAV
3. Harness uses real audio synthesis + injection

### Phase 3: Event Bus (Optional)
- Add `paho-mqtt` client
- Publish events: `kloros/turn/completed`, `ace/bullets/generated`
- Enable MQTT probe in harness

---

## 🧪 Quick Test (Without Fixes)

To verify harness *structure* works, stub the missing pieces:

```python
# tests/e2e/test_scenarios_minimal.py
import pytest
from pathlib import Path

def test_harness_loads():
    """Verify scenario YAML parsing works."""
    from harness.scenario import load_scenario
    s = load_scenario(Path("tests/scenarios/summarize_errors_and_ace.yaml"))
    assert s.name == "Summarize daily error logs and produce ACE bullets"
    assert len(s.steps) == 1
    assert len(s.artifacts) == 1

def test_log_probe():
    """Verify log tail mechanism works."""
    from harness.logs import LogProbe
    probe = LogProbe("/home/kloros/.kloros/logs")
    # Write test entry, verify tail_until() finds it
    ...

def test_speech_probe_stub():
    """Verify speech probe doesn't crash."""
    from harness.speech import SpeechProbe
    probe = SpeechProbe()
    # Will fail gracefully if paths don't exist
    assert probe.wav_duration() >= 0.0
```

Run: `pytest tests/e2e/test_scenarios_minimal.py -v`

---

## 📋 Summary: Required Changes

| Component | Status | Work Required |
|-----------|--------|---------------|
| MQTT Bus | ❌ Missing | Add paho-mqtt client + publish events |
| ASR Ingress (FIFO/HTTP) | ❌ Missing | FastAPI endpoint or FIFO reader |
| TTS Last File | ❌ Missing | Save WAV to `/tmp/kloros_tts_out.wav` |
| Final Reply Log | ❌ Missing | Add `phase="final_response"` JSONL entry |
| ACE Export Tool | ❌ Missing | Export ChromaDB bullets to markdown |
| Changelog Tool | ❌ Missing | Parse git log, format as markdown |
| Structured Log Format | ⚠️ Partial | Add `phase`, `latency_ms`, `tool_calls` |
| Service Files | ⚠️ Partial | Only `kloros-dream.service` exists |
| Path Mappings | ❌ Wrong | Update harness.toml paths |

---

## ✅ Next Steps

1. **Decide on architecture**:
   - Full (MQTT + audio ingress + all tools)
   - Minimal (logs + text input only)

2. **Update harness.toml** with actual paths

3. **Add missing tools** to introspection_tools.py

4. **Implement TTS tracking + final log entry**

5. **Run simplified tests** to verify structure

6. **Iterate** based on test failures
