#!/usr/bin/env python3
"""TTS end-to-end smoke test - use Mimic3 backend."""
import os, sys
os.environ.setdefault("COQUI_TOS_AGREED", "1")
sys.path.insert(0, "/home/kloros/src")
sys.path.insert(0, "/home/kloros")

try:
    from tts.adapters.mimic3 import Mimic3Backend
    import yaml
    
    # Load config
    with open("/home/kloros/src/tts/config.yaml") as f:
        cfg = yaml.safe_load(f)
    
    print("[*] Initializing Mimic3 backend...")
    backend = Mimic3Backend(cfg)
    
    print("[*] Generating audio: KLoROS online.")
    text = "KLoROS online."
    
    # Start backend
    backend.start()
    
    # Generate audio
    audio_chunks = list(backend.stream_text([text]))
    
    if not audio_chunks:
        print("❌ No audio generated")
        sys.exit(1)
    
    # Concatenate chunks
    audio_data = b"".join(audio_chunks)
    
    # Write to file
    out = "/tmp/tts_test.wav"
    
    import wave
    with wave.open(out, "wb") as wf:
        wf.setnchannels(1)  # mono
        wf.setsampwidth(2)  # 16-bit
        wf.setframerate(cfg.get("audio", {}).get("sample_rate", 22050))
        wf.writeframes(audio_data)
    
    print(f"[OK] wrote {out}")
    print(f"[*] Audio size: {len(audio_data)} bytes, {len(audio_chunks)} chunks")
    
except Exception as e:
    print(f"❌ TTS test failed: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
