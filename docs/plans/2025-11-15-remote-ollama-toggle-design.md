# Remote Ollama Toggle Switch Design

**Date:** 2025-11-15
**Status:** Approved
**Components:** AltimitOS Toggle Service, ASTRAEA Client Changes

## Problem

Currently, remote Ollama routing is automatic - if AltimitOS is reachable, it gets used. This creates two issues:
1. No visibility into whether remote is being used
2. No easy way to force local even when remote is available
3. Difficult to troubleshoot connection issues

## Solution

Add a Stream Deck button on AltimitOS that toggles remote Ollama availability via a simple HTTP service.

## Architecture

### Components

1. **AltimitOS Toggle Service** (new)
   - Tiny Flask server on Windows
   - Endpoints: `/status` (GET), `/toggle` (POST)
   - State file: `C:\Users\morga\.ollama-remote-enabled.json`
   - Default: enabled

2. **ASTRAEA Client** (modify existing)
   - `_check_remote_ollama()` in `models_config.py`
   - Check toggle state before checking Ollama availability
   - Fail-open if toggle service unreachable

### Flow

```
ASTRAEA needs LLM
  → Check http://100.67.244.66:8888/status
    → enabled=false? Use local (127.0.0.1:11434)
    → enabled=true? Check http://100.67.244.66:11434/api/tags
      → Available? Use remote
      → Unavailable? Use local
```

## AltimitOS Implementation

### Python Toggle Service

**File:** `C:\Users\morga\ollama_toggle_service.py`

```python
from flask import Flask, jsonify
import json
from pathlib import Path

app = Flask(__name__)
STATE_FILE = Path("C:/Users/morga/.ollama-remote-enabled.json")

def load_state():
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text())
    return {"enabled": True}  # Default: enabled

def save_state(state):
    STATE_FILE.write_text(json.dumps(state))

@app.route('/status')
def status():
    return jsonify(load_state())

@app.route('/toggle', methods=['POST'])
def toggle():
    state = load_state()
    state['enabled'] = not state['enabled']
    save_state(state)
    return jsonify(state)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8888)
```

### Stream Deck Configuration

- **Action Type:** Website
- **URL:** `http://localhost:8888/toggle`
- **Method:** POST

### Auto-Start (Optional)

Use Windows Task Scheduler:
- Trigger: At log on
- Action: Start program
- Program: `pythonw.exe`
- Arguments: `C:\Users\morga\ollama_toggle_service.py`

## ASTRAEA Implementation

### Modify `_check_remote_ollama()`

**File:** `/home/kloros/src/config/models_config.py`

Add toggle check before Ollama availability check:

```python
# After loading config and ollama_url:

# Check if user enabled remote via toggle service
toggle_host = ollama_url.split(':')[1].replace('//', '')  # Extract IP
try:
    status_resp = requests.get(
        f"http://{toggle_host}:8888/status",
        timeout=1  # Quick check
    )
    if status_resp.status_code == 200:
        enabled = status_resp.json().get("enabled", True)
        if not enabled:
            # User explicitly disabled remote
            _remote_ollama_cache["url"] = None
            _remote_ollama_cache["timestamp"] = now
            return None
except Exception:
    # Toggle service not reachable - assume enabled (fail-open)
    pass

# Continue with existing Ollama availability check...
```

## Error Handling

- **Toggle service down:** Fail-open (assume enabled), continue to Ollama check
- **Ollama down:** Fall back to local (existing behavior)
- **Both down:** Use local Ollama

## Testing

1. Start toggle service on AltimitOS
2. Verify `curl http://localhost:8888/status` returns `{"enabled": true}`
3. Toggle: `curl -X POST http://localhost:8888/toggle`
4. From ASTRAEA: Test model selection uses local when disabled
5. Test Stream Deck button

## Future Enhancements

- Visual feedback on Stream Deck (light up when enabled)
- Metrics: track toggle frequency, usage time
- Auto-disable during gaming hours
- Dashboard integration
