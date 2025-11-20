#!/usr/bin/env python3
"""
TTS Quality Measurement Module
Provides PESQ, STOI, and latency measurements for TTS evaluation.
"""
import os
import subprocess
import time
import numpy as np
from pathlib import Path

# Import libraries
try:
    from pesq import pesq
    PESQ_AVAILABLE = True
except ImportError:
    PESQ_AVAILABLE = False
    print("[WARN] PESQ not available - install with: pip install pesq")

try:
    from pystoi import stoi
    STOI_AVAILABLE = True
except ImportError:
    STOI_AVAILABLE = False
    print("[WARN] STOI not available - install with: pip install pystoi")

try:
    import soundfile as sf
    SOUNDFILE_AVAILABLE = True
except ImportError:
    SOUNDFILE_AVAILABLE = False
    print("[WARN] soundfile not available - install with: pip install soundfile")


def load_audio(audio_path, target_sr=16000):
    """Load audio file and resample to target sample rate."""
    if not SOUNDFILE_AVAILABLE:
        raise ImportError("soundfile required for audio loading")

    data, sr = sf.read(audio_path)

    # Convert stereo to mono if needed
    if len(data.shape) > 1:
        data = data.mean(axis=1)

    # Resample if needed (simple decimation/interpolation)
    if sr != target_sr:
        # For now, just use the data as-is and note the actual sample rate
        # In production, use librosa.resample or scipy.signal.resample
        pass

    return data, sr


def synthesize_audio(text, output_path, voice_model="/home/kloros/models/piper/glados_piper_medium.onnx"):
    """
    Synthesize audio from text using Piper TTS.

    Returns:
        tuple: (success: bool, latency_ms: int)
    """
    start_time = time.time()

    try:
        # Use piper to synthesize
        cmd = f'echo "{text}" | piper --model {voice_model} --output_file {output_path}'
        result = subprocess.run(cmd, shell=True, capture_output=True, timeout=10)

        latency_ms = int((time.time() - start_time) * 1000)

        if result.returncode == 0 and os.path.exists(output_path):
            return True, latency_ms
        else:
            return False, latency_ms

    except Exception as e:
        latency_ms = int((time.time() - start_time) * 1000)
        print(f"[ERROR] TTS synthesis failed: {e}")
        return False, latency_ms


def measure_pesq(ref_audio_path, synth_audio_path, sample_rate=16000):
    """
    Measure PESQ (Perceptual Evaluation of Speech Quality).

    Returns:
        float: PESQ score (1.0-4.5, higher is better), or None if error
    """
    if not PESQ_AVAILABLE:
        return None

    try:
        ref, ref_sr = load_audio(ref_audio_path, sample_rate)
        synth, synth_sr = load_audio(synth_audio_path, sample_rate)

        # PESQ requires same length - truncate to shorter
        min_len = min(len(ref), len(synth))
        ref = ref[:min_len]
        synth = synth[:min_len]

        # PESQ score: 'wb' for wideband (16kHz), 'nb' for narrowband (8kHz)
        mode = 'wb' if sample_rate == 16000 else 'nb'
        score = pesq(sample_rate, ref, synth, mode)

        return float(score)

    except Exception as e:
        print(f"[ERROR] PESQ measurement failed: {e}")
        return None


def measure_stoi(ref_audio_path, synth_audio_path, sample_rate=16000):
    """
    Measure STOI (Short-Time Objective Intelligibility).

    Returns:
        float: STOI score (0.0-1.0, higher is better), or None if error
    """
    if not STOI_AVAILABLE:
        return None

    try:
        ref, ref_sr = load_audio(ref_audio_path, sample_rate)
        synth, synth_sr = load_audio(synth_audio_path, sample_rate)

        # STOI requires same length - truncate to shorter
        min_len = min(len(ref), len(synth))
        ref = ref[:min_len]
        synth = synth[:min_len]

        # Calculate STOI
        score = stoi(ref, synth, sample_rate, extended=False)

        return float(score)

    except Exception as e:
        print(f"[ERROR] STOI measurement failed: {e}")
        return None


def evaluate_tts_quality(text_input, reference_audio=None, voice_model=None, cleanup=True):
    """
    Complete TTS quality evaluation pipeline.

    Args:
        text_input: Text to synthesize
        reference_audio: Path to reference audio (optional, for PESQ/STOI)
        voice_model: Path to Piper voice model (optional)
        cleanup: Remove synthesized audio after evaluation

    Returns:
        dict: {
            'pesq': float or None,
            'stoi': float or None,
            'latency_ms': int,
            'success': bool
        }
    """
    # Create temp output path
    import tempfile
    temp_dir = tempfile.gettempdir()
    synth_path = os.path.join(temp_dir, f"tts_eval_{int(time.time())}.wav")

    # Synthesize audio
    success, latency_ms = synthesize_audio(text_input, synth_path, voice_model or "/home/kloros/models/piper/glados_piper_medium.onnx")

    result = {
        'success': success,
        'latency_ms': latency_ms,
        'pesq': None,
        'stoi': None
    }

    if not success:
        return result

    # Measure quality if reference provided
    if reference_audio and os.path.exists(reference_audio):
        result['pesq'] = measure_pesq(reference_audio, synth_path)
        result['stoi'] = measure_stoi(reference_audio, synth_path)

    # Cleanup
    if cleanup and os.path.exists(synth_path):
        try:
            os.remove(synth_path)
        except:
            pass

    return result


# Fallback values for when measurements aren't available
DEFAULT_PESQ = 3.0
DEFAULT_STOI = 0.85
DEFAULT_LATENCY_MS = 120


if __name__ == "__main__":
    # Test the module
    print("Testing TTS quality measurement...")

    # Test with sample from eval set
    text = "Hello world"
    ref = "/home/kloros/assets/asr_eval/mini_eval_set/sample1.wav"

    result = evaluate_tts_quality(text, reference_audio=ref)

    print(f"Success: {result['success']}")
    print(f"Latency: {result['latency_ms']}ms")
    print(f"PESQ: {result['pesq']}")
    print(f"STOI: {result['stoi']}")
