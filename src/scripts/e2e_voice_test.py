#!/usr/bin/env python3
"""End-to-end voice pipeline test: Audio → VAD → faster-whisper → TTS → Audio"""
import os, sys, time
import numpy as np
import torch
os.environ.setdefault("KLR_REGISTRY", "/home/kloros/src/registry/capabilities.yaml")
sys.path.insert(0, "/home/kloros/src")
sys.path.insert(0, "/home/kloros")

# Test audio path
TEST_AUDIO = "/home/kloros/voice_files/GLaDOS_00_part1_entry-1.wav"
OUTPUT_PATH = "/tmp/e2e_voice_reply.wav"

try:
    import soundfile as sf
    from faster_whisper import WhisperModel
    from stt.whisper_backend import WhisperSttBackend
    from tts.router import TTSRouter

    print("[*] End-to-end voice pipeline test")
    print()

    # 1. Load test audio
    print(f"[1/5] Loading test audio: {TEST_AUDIO}")
    wav, sr = sf.read(TEST_AUDIO)
    if wav.ndim > 1:
        wav = wav.mean(axis=1)
    if wav.dtype != np.float32:
        wav = wav.astype(np.float32)

    # Resample to 16kHz for VAD
    if sr != 16000:
        import librosa
        wav = librosa.resample(wav, orig_sr=sr, target_sr=16000)
        sr = 16000

    print(f"    Audio: {wav.size} samples, {sr}Hz, {wav.size/sr:.2f}s duration")

    # 2. Run VAD
    print("[2/5] Running Silero VAD...")
    vad_model, vad_utils = torch.hub.load(
        repo_or_dir="snakers4/silero-vad",
        model="silero_vad",
        force_reload=False,
        onnx=False
    )
    get_speech_timestamps = vad_utils[0]

    wav_tensor = torch.from_numpy(wav)
    speech_timestamps = get_speech_timestamps(
        wav_tensor,
        vad_model,
        sampling_rate=16000,
        threshold=0.5
    )

    if not speech_timestamps:
        print("❌ VAD rejected all audio")
        sys.exit(1)

    speech_chunks = []
    for ts in speech_timestamps:
        speech_chunks.append(wav[ts["start"]:ts["end"]])

    speech = np.concatenate(speech_chunks)
    keep_ratio = speech.size / max(1, wav.size)
    print(f"    VAD: {len(speech_timestamps)} segments, kept {keep_ratio*100:.1f}% of audio")

    # 3. Transcribe with faster-whisper
    print("[3/5] Transcribing with faster-whisper...")
    MODEL = os.environ.get("KLR_ASR_MODEL", "base")
    DEVICE = os.environ.get("KLR_ASR_DEVICE", "cpu")
    COMPUTE = "float16" if DEVICE == "cuda" else "int8"

    asr = WhisperModel(MODEL, device=DEVICE, compute_type=COMPUTE)

    t0 = time.time()
    segments, info = asr.transcribe(speech, vad_filter=False, language="en")
    text = " ".join([s.text for s in segments]).strip()
    dt = time.time() - t0

    if not text:
        print("❌ Transcription empty")
        sys.exit(1)

    print(f"    Transcript: \"{text}\"")
    print(f"    Transcription time: {dt:.2f}s")

    # 4. Generate TTS response
    print("[4/5] Generating TTS response...")
    cfg_path = "/home/kloros/src/tts/config.yaml"
    router = TTSRouter(cfg_path=cfg_path)

    # Try to pick Mimic3 first (XTTS-v2 needs speaker refs which may not exist)
    backend = None
    try:
        backend = router._get("mimic3")
    except:
        pass

    if not backend:
        try:
            backend = router.pick(intent="default")
        except RuntimeError as e:
            print(f"❌ No TTS backend available: {e}")
            sys.exit(1)

    print(f"    Using TTS backend: {backend.__class__.__name__}")

    # Simple response based on transcript
    response = f"I heard you say: {text[:50]}"

    # Collect TTS audio chunks
    router.start(backend)
    audio_chunks = []
    for chunk in backend.stream_text([response]):
        if isinstance(chunk, bytes):
            audio_chunks.append(np.frombuffer(chunk, dtype=np.int16))
    router.stop(backend)

    if not audio_chunks:
        print("❌ TTS generated no audio")
        sys.exit(1)

    audio = np.concatenate(audio_chunks)
    print(f"    TTS: Generated {audio.size} samples")

    # 5. Save output
    print(f"[5/5] Saving output to {OUTPUT_PATH}")
    sample_rate = router.cfg.get("audio", {}).get("sample_rate", 22050)
    sf.write(OUTPUT_PATH, audio, sample_rate, subtype='PCM_16')

    print()
    print("[OK] End-to-end voice pipeline test passed!")
    print(f"     Play with: aplay {OUTPUT_PATH} || ffplay -autoexit -nodisp {OUTPUT_PATH}")

except ImportError as e:
    print(f"❌ Import error: {e}")
    print("   Install missing dependencies:")
    print("   pip install faster-whisper soundfile librosa torch")
    sys.exit(1)
except Exception as e:
    print(f"❌ E2E voice test failed: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
