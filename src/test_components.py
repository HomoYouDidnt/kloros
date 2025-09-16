"""Cross-platform smoke tests for integrations.

This script is intended for dev machines and should be tolerant when
system tools (piper/aplay/pactl) are not present. It uses environment
paths consistent with `src/kloros_voice.py`.
"""
import json
import os
import shutil
import subprocess
import requests  # type: ignore

# Test Ollama (defensive)
try:
    response = requests.post(
        "http://localhost:11434/api/generate",
        json={"model": "nous-hermes:13b-q4_0", "prompt": "Say hello in one sentence", "stream": False},
        timeout=10,
    )
    if response.status_code == 200:
        print("LLM Test:", response.json().get("response"))
    else:
        print("LLM Test: Ollama returned HTTP", response.status_code)
except Exception as e:
    print("LLM Test: failed to contact Ollama:", e)

# Test Piper TTS (cross-platform guard)
piper_exe = os.getenv("KLR_PIPER_EXE") or shutil.which("piper")
piper_model = os.path.expanduser("~/kloros_models/piper/glados_piper_medium.onnx")
if not piper_exe:
    print("TTS Test: piper not found; skipping TTS test")
elif not os.path.exists(piper_model):
    print("TTS Test: piper model not found; expected:", piper_model)
else:
    try:
        # Call piper directly, supplying text as stdin bytes (cross-platform)
        subprocess.run([piper_exe, "--model", piper_model, "--output_file", "test_voice.wav"], input=b"Testing GLaDOS voice", check=False)
        print("TTS Test: Created test_voice.wav (if piper supports this host)")
    except Exception as e:
        print("TTS Test: failed:", e)

# Test Vosk import
try:
    import vosk  # type: ignore
    print("STT Test: Vosk imported successfully")
except Exception as e:
    print("STT Test: vosk import failed:", e)
