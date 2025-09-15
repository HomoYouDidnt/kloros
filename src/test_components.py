# Test all components work
import requests
import json

# Test Ollama
response = requests.post("http://localhost:11434/api/generate", json={
    "model": "nous-hermes:13b-q4_0", 
    "prompt": "Say hello in one sentence", 
    "stream": False
})
print("LLM Test:", response.json()["response"])

# Test Piper TTS
import subprocess
result = subprocess.run([
    'echo', 'Testing GLaDOS voice'
], stdout=subprocess.PIPE)

piper_cmd = [
    'piper', 
    '--model', '/home/adam/kloros_models/piper/glados_piper_medium.onnx',
    '--output_file', 'test_voice.wav'
]
subprocess.run(piper_cmd, input=result.stdout)
print("TTS Test: Created test_voice.wav")

# Test Vosk (basic import)
import vosk
print("STT Test: Vosk imported successfully")
