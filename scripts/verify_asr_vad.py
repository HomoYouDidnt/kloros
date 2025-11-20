#!/usr/bin/env python3
"""Verify faster-whisper + VAD integration."""
import os, sys, time
import numpy as np
import torch
os.environ.setdefault("KLR_REGISTRY", "/home/kloros/src/registry/capabilities.yaml")
sys.path.insert(0, "/home/kloros/src")
sys.path.insert(0, "/home/kloros")

# Config
MODEL = os.environ.get("KLR_ASR_MODEL", "base")
DEVICE = os.environ.get("KLR_ASR_DEVICE", "cpu")
COMPUTE = "float16" if DEVICE == "cuda" else "int8"

try:
    from faster_whisper import WhisperModel
    import soundfile as sf
    
    print(f"[*] loading faster-whisper model={MODEL} device={DEVICE} compute={COMPUTE}")
    asr = WhisperModel(MODEL, device=DEVICE, compute_type=COMPUTE)
    
    print("[*] loading Silero VAD model...")
    vad_model, vad_utils = torch.hub.load(
        repo_or_dir="snakers4/silero-vad",
        model="silero_vad",
        force_reload=False,
        onnx=False
    )
    get_speech_timestamps = vad_utils[0]
    
    if len(sys.argv) < 2:
        print("Usage: python verify_asr_vad.py /path/to/file.wav")
        sys.exit(2)
    
    # Load audio
    wav_path = sys.argv[1]
    print(f"[*] loading audio from {wav_path}")
    wav, sr = sf.read(wav_path)
    
    if wav.ndim > 1:
        wav = wav.mean(axis=1)
    
    if wav.dtype != np.float32:
        wav = wav.astype(np.float32)
    
    # Resample to 16kHz for VAD
    if sr != 16000:
        print(f"[*] resampling from {sr}Hz to 16000Hz")
        import librosa
        wav = librosa.resample(wav, orig_sr=sr, target_sr=16000)
        sr = 16000
    
    # Convert to torch tensor
    wav_tensor = torch.from_numpy(wav)
    
    # Get speech timestamps
    print("[*] running VAD...")
    speech_timestamps = get_speech_timestamps(
        wav_tensor,
        vad_model,
        sampling_rate=16000,
        threshold=0.5
    )
    
    if not speech_timestamps:
        print("❌ VAD rejected all audio")
        sys.exit(1)
    
    print(f"[*] VAD found {len(speech_timestamps)} speech segments")
    
    # Extract speech segments
    speech_chunks = []
    for ts in speech_timestamps:
        start = ts["start"]
        end = ts["end"]
        speech_chunks.append(wav[start:end])
    
    speech = np.concatenate(speech_chunks)
    keep_ratio = speech.size / max(1, wav.size)
    print(f"[*] VAD kept {keep_ratio*100:.1f}% of audio")
    
    # Transcribe
    print("[*] transcribing with faster-whisper...")
    t0 = time.time()
    segments, info = asr.transcribe(speech, vad_filter=False, language="en")
    text = " ".join([s.text for s in segments])
    dt = time.time() - t0
    
    print()
    print("[OK] transcript:")
    print(text.strip() or "(empty)")
    print()
    print(f"[*] info: duration={info.duration:.2f}s device={DEVICE} transcribe_time={dt:.2f}s")
    
except Exception as e:
    print(f"❌ ASR/VAD test failed: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
