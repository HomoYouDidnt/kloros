# Instructions for Windows Claude - Ollama Toggle Service

## Goal
Create a simple Flask HTTP service that allows Stream Deck to toggle remote Ollama availability on/off.

## Step 1: Create the Toggle Service

Create a file at `C:\Users\morga\ollama_toggle_service.py`:

```python
from flask import Flask, jsonify
import json
from pathlib import Path

app = Flask(__name__)
STATE_FILE = Path("C:/Users/morga/.ollama-remote-enabled.json")

def load_state():
    """Load the enabled state from file, default to enabled."""
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text())
    return {"enabled": True}

def save_state(state):
    """Save the enabled state to file."""
    STATE_FILE.write_text(json.dumps(state, indent=2))

@app.route('/status')
def status():
    """Return current enabled state."""
    return jsonify(load_state())

@app.route('/toggle', methods=['POST'])
def toggle():
    """Toggle the enabled state and return new state."""
    state = load_state()
    state['enabled'] = not state['enabled']
    save_state(state)
    print(f"Toggle: Remote Ollama now {'ENABLED' if state['enabled'] else 'DISABLED'}")
    return jsonify(state)

if __name__ == '__main__':
    print("Starting Ollama Toggle Service on port 8888...")
    print("Stream Deck can POST to http://localhost:8888/toggle")
    app.run(host='0.0.0.0', port=8888)
```

## Step 2: Install Flask (if not already installed)

```powershell
pip install flask
```

## Step 3: Test the Service

```powershell
# Start the service
python C:\Users\morga\ollama_toggle_service.py

# In another PowerShell window, test it:
curl http://localhost:8888/status
curl -Method POST http://localhost:8888/toggle
curl http://localhost:8888/status
```

## Step 4: Configure Stream Deck

1. Add a new button to your Stream Deck
2. Action Type: **System > Website**
3. URL: `http://localhost:8888/toggle`
4. Access: `POST`

Optional: Add visual feedback by using a Multi-Action that hits the endpoint and then displays the result.

## Step 5: Auto-Start on Login (Optional)

**Option A: Task Scheduler**
1. Open Task Scheduler
2. Create Basic Task
3. Name: "Ollama Toggle Service"
4. Trigger: "When I log on"
5. Action: "Start a program"
6. Program: `pythonw.exe` (no console window)
7. Arguments: `C:\Users\morga\ollama_toggle_service.py`
8. Start in: `C:\Users\morga`

**Option B: Startup Folder**
Create a shortcut to a batch file in `%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup`

Batch file contents:
```batch
@echo off
pythonw C:\Users\morga\ollama_toggle_service.py
```

## Testing

After setup, verify:
1. Service starts and listens on port 8888
2. Stream Deck button toggles the state
3. Check state file: `C:\Users\morga\.ollama-remote-enabled.json`
4. ASTRAEA should respect the toggle (you'll see it use local when disabled)

## Troubleshooting

**Port 8888 already in use:**
Change the port in the Python script and Stream Deck URL.

**Flask not found:**
Run `pip install flask` in PowerShell.

**Stream Deck can't reach localhost:**
Ensure Windows Firewall allows connections on port 8888 (should be fine for localhost).
