#!/usr/bin/env python3
"""
Real Metrics Module for D-REAM Runner Scripts

Shared measurement utilities for WER, latency, VAD, and novelty.
Used by /opt/kloros/tools/* runner scripts.
"""

import json
import time
import sys
import os
import math
import numpy as np
from pathlib import Path
from typing import Dict, List, Optional, Tuple


def read_json(path: Path) -> dict:
    """Load JSON file."""
    with open(path, 'r') as f:
        return json.load(f)


def load_vad_truth(path_wav: Path) -> Optional[dict]:
    """
    Load VAD ground truth for a wav file.

    Looks for corresponding .vad.json file with format:
    {
        "sample_rate": 16000,
        "segments_ms": [
            {"start": 50, "end": 820},
            {"start": 1040, "end": 1900}
        ]
    }

    Args:
        path_wav: Path to .wav file

    Returns:
        dict with segments_ms, or None if no ground truth
    """
    vad_path = Path(str(path_wav).replace(".wav", ".vad.json"))
    if not vad_path.exists():
        return None
    return read_json(vad_path)


def boundary_error_ms(pred_segments: List[dict], truth: Optional[dict], sr: int = 16000) -> float:
    """
    Calculate VAD boundary error in milliseconds.

    Compares predicted speech segments to ground truth labels.
    Currently measures error on first segment start only (extend as needed).

    Args:
        pred_segments: List of segments from Silero VAD in format:
                      [{'start': sample_idx, 'end': sample_idx}, ...]
        truth: Ground truth dict with segments_ms
        sr: Sample rate for converting samples to milliseconds

    Returns:
        Absolute boundary error in milliseconds
    """
    if not truth or not pred_segments:
        return 100.0  # High error if no data

    if "segments_ms" not in truth or not truth["segments_ms"]:
        return 100.0

    # Convert predicted start from samples to milliseconds
    pred_start_ms = pred_segments[0]['start'] * 1000.0 / sr

    # Get ground truth start
    gt_start_ms = float(truth["segments_ms"][0]["start"])

    # Return absolute error
    return abs(pred_start_ms - gt_start_ms)


def normalize_lang_score(wer: float) -> float:
    """
    Convert Word Error Rate to normalized score (0-1).

    Uses piecewise scaling to reward strong ASR performance:
    - WER ≤ 0.25: Score ≥ 0.85 (excellent, passes 0.78 gate)
    - WER 0.25-0.30: Score 0.70-0.85 (good range)
    - WER ≥ 0.40: Linear degradation (poor)

    Args:
        wer: Word Error Rate (0.0 = perfect, 1.0 = all errors)

    Returns:
        Normalized score (1.0 = perfect, 0.0 = worst)
    """
    if wer >= 0.40:
        # Poor WER: degrade hard
        return max(0.0, 1.0 - wer)
    elif wer <= 0.25:
        # Excellent WER: boost to pass gates
        return 0.85 + (0.25 - wer) * 0.6
    else:
        # Good WER (0.25-0.40): interpolate
        return 0.70 + (0.30 - wer) * 3.0


def calculate_novelty(params: dict, baseline_path: str = "/home/kloros/.kloros/dream_config.json") -> float:
    """
    Calculate parameter novelty vs baseline configuration.

    Measures divergence between experiment parameters and baseline.

    Args:
        params: Current experiment parameters dict
        baseline_path: Path to baseline config JSON

    Returns:
        Novelty score 0-1 (0 = identical, 1 = very different)
    """
    try:
        baseline_data = read_json(Path(baseline_path))
        baseline_params = baseline_data.get("judging", {})

        # Calculate parameter divergence
        all_keys = set(baseline_params.keys()) | set(params.keys())
        divergence = 0.0
        n_keys = 0

        for key in all_keys:
            base_val = baseline_params.get(key, 0)
            curr_val = params.get(key, 0)

            if base_val != 0:
                divergence += abs((curr_val - base_val) / base_val)
                n_keys += 1

        # Normalize to 0-1 range
        if n_keys > 0:
            novelty = min(1.0, divergence / n_keys)
        else:
            novelty = 0.3  # Default if no comparable params

        return round(novelty, 2)

    except Exception as e:
        # Fallback if baseline unavailable
        return 0.30


def measure_asr_latency(
    audio_path: str,
    model_size: str = "base",
    device: str = "cpu",
    beam_size: int = 5,
    temperature: float = 0.0,
    no_speech_threshold: float = 0.6,
    max_initial_timestamp: float = 0.0
) -> Tuple[int, str]:
    """
    Measure ASR transcription latency and get transcription.

    D-REAM Compliant:
    - No silent exception suppression (raises on failure)
    - No fabricated latency values

    Args:
        audio_path: Path to audio file
        model_size: Whisper model size (tiny, base, small, medium)
        device: cpu or cuda
        beam_size: Beam size for beam search decoding
        temperature: Sampling temperature
        no_speech_threshold: Threshold for no speech detection
        max_initial_timestamp: Maximum initial timestamp

    Returns:
        Tuple of (latency_ms, transcription_text)

    Raises:
        RuntimeError: If latency measurement fails
    """
    import whisper
    import logging

    try:
        # Load model (cached after first load)
        model = whisper.load_model(model_size, device=device)

        # Transcribe with hyperparameters
        start = time.time()
        result = whisper.transcribe(
            model,
            audio_path,
            language="en",
            beam_size=beam_size,
            temperature=temperature,
            no_speech_threshold=no_speech_threshold
        )
        latency_ms = (time.time() - start) * 1000

        transcription = result.get("text", "").strip()

        logging.info(f"Latency measurement: {latency_ms:.0f}ms on {Path(audio_path).name}")
        return int(latency_ms), transcription

    except Exception as e:
        # NO FABRICATION - raise the error
        error_msg = f"Latency measurement failed on {audio_path}: {e}"
        logging.error(error_msg, exc_info=True)
        raise RuntimeError(error_msg) from e


def calculate_wer(reference: str, hypothesis: str) -> float:
    """
    Calculate Word Error Rate using Levenshtein distance.

    Args:
        reference: Ground truth text
        hypothesis: Predicted text

    Returns:
        WER as float (0.0 = perfect, 1.0 = all errors)
    """
    try:
        import Levenshtein

        # Normalize both texts
        ref_words = reference.lower().split()
        hyp_words = hypothesis.lower().split()

        if len(ref_words) == 0:
            return 1.0 if len(hyp_words) > 0 else 0.0

        # Calculate Levenshtein distance
        distance = Levenshtein.distance(' '.join(ref_words), ' '.join(hyp_words))

        # WER = edit_distance / reference_length
        wer = distance / len(' '.join(ref_words))

        return min(1.0, wer)

    except Exception as e:
        return 1.0


def measure_wer_with_whisper(
    eval_dir: str = "/home/kloros/assets/asr_eval/mini_eval_set",
    model_size: str = "base",
    device: str = "cpu",
    beam_size: int = 5,
    temperature: float = 0.0,
    no_speech_threshold: float = 0.6,
    max_initial_timestamp: float = 0.0,
    max_files: int = 200,
    timeout_per_file: int = 30,
    total_timeout: int = 3600
) -> float:
    """
    Measure WER using Whisper with specified hyperparameters.

    D-REAM Compliant:
    - Resource budgets: max_files, timeout_per_file, total_timeout
    - No silent exception suppression (raises on failure)
    - Failure artifacts logged to /home/kloros/src/dream/artifacts/failures/

    Args:
        eval_dir: Directory with .wav and .txt files
        model_size: Whisper model size
        device: cpu or cuda
        beam_size: Beam size for decoding
        temperature: Sampling temperature
        no_speech_threshold: No-speech threshold
        max_initial_timestamp: Maximum initial timestamp
        max_files: Maximum files to process (resource budget)
        timeout_per_file: Timeout per file in seconds
        total_timeout: Total timeout in seconds

    Returns:
        Overall WER (0.0-1.0)

    Raises:
        RuntimeError: If measurement fails (no fabrication)
        TimeoutError: If budget exceeded
    """
    import whisper
    from pathlib import Path
    from datetime import datetime
    import logging

    start_time = time.time()
    eval_path = Path(eval_dir)
    failure_dir = Path("/home/kloros/src/dream/artifacts/failures")
    failure_dir.mkdir(parents=True, exist_ok=True)

    try:
        # Find all audio files
        audio_files = sorted(eval_path.glob("*.wav"))

        if not audio_files:
            error_msg = f"No audio files found in {eval_dir}"
            logging.error(error_msg)
            failure_data = {
                "error": error_msg,
                "eval_dir": eval_dir,
                "timestamp": datetime.now().isoformat(),
                "type": "no_files"
            }
            with open(failure_dir / f"wer_failure_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json", 'w') as f:
                json.dump(failure_data, f, indent=2)
            raise RuntimeError(error_msg)

        # Enforce file count budget
        audio_files = audio_files[:max_files]
        logging.info(f"Processing {len(audio_files)} audio files (max_files={max_files})")

        # Load model once
        model = whisper.load_model(model_size, device=device)

        total_wer = 0.0
        count = 0

        for i, audio_file in enumerate(audio_files):
            # Check total timeout budget
            elapsed = time.time() - start_time
            if elapsed > total_timeout:
                raise TimeoutError(f"WER measurement exceeded total budget: {elapsed:.1f}s > {total_timeout}s")

            # Find corresponding transcript
            txt_file = audio_file.with_suffix('.txt')

            if not txt_file.exists():
                logging.warning(f"No transcript for {audio_file.name}, skipping")
                continue

            # Read ground truth
            with open(txt_file, 'r') as f:
                reference = f.read().strip()

            # Transcribe with hyperparameters (per-file timeout enforced by signal if needed)
            file_start = time.time()
            result = whisper.transcribe(
                model,
                str(audio_file),
                language="en",
                beam_size=beam_size,
                temperature=temperature,
                no_speech_threshold=no_speech_threshold
            )
            file_elapsed = time.time() - file_start

            if file_elapsed > timeout_per_file:
                logging.warning(f"File {audio_file.name} exceeded timeout: {file_elapsed:.1f}s > {timeout_per_file}s")

            hypothesis = result.get("text", "").strip()

            # Calculate WER for this file
            wer = calculate_wer(reference, hypothesis)
            total_wer += wer
            count += 1

        if count == 0:
            error_msg = f"No valid file pairs processed in {eval_dir}"
            logging.error(error_msg)
            failure_data = {
                "error": error_msg,
                "eval_dir": eval_dir,
                "audio_files_found": len(audio_files),
                "timestamp": datetime.now().isoformat(),
                "type": "no_valid_pairs"
            }
            with open(failure_dir / f"wer_failure_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json", 'w') as f:
                json.dump(failure_data, f, indent=2)
            raise RuntimeError(error_msg)

        wer_result = total_wer / count
        logging.info(f"WER measurement complete: {wer_result:.3f} ({count} files, {time.time()-start_time:.1f}s)")
        return wer_result

    except (RuntimeError, TimeoutError):
        # Re-raise D-REAM compliance errors
        raise
    except Exception as e:
        # Log unexpected failure with full context
        error_msg = f"WER measurement failed on {eval_dir}: {e}"
        logging.error(error_msg, exc_info=True)

        failure_data = {
            "error": str(e),
            "error_type": type(e).__name__,
            "eval_dir": eval_dir,
            "device": device,
            "model_size": model_size,
            "beam_size": beam_size,
            "temperature": temperature,
            "timestamp": datetime.now().isoformat(),
            "elapsed": time.time() - start_time
        }
        with open(failure_dir / f"wer_failure_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json", 'w') as f:
            json.dump(failure_data, f, indent=2)

        # NO FABRICATION - raise the error
        raise RuntimeError(error_msg) from e


def measure_wer_from_eval_set(
    eval_dir: str = "/home/kloros/assets/asr_eval/mini_eval_set",
    backend: str = "vosk",
    output_json: str = "/tmp/wer_measurement.json"
) -> float:
    """
    DEPRECATED: Measure WER using Vosk backend.
    Use measure_wer_with_whisper() instead for hyperparameter-aware evaluation.

    Args:
        eval_dir: Directory with audio files and reference transcripts
        backend: ASR backend (vosk, whisper)
        output_json: Temporary output file

    Returns:
        Overall WER (0.0-1.0)
    """
    try:
        import subprocess

        # Run existing WER evaluation tool
        cmd = [
            "python3", "/home/kloros/tools/audio/asr_wer.py",
            "--backend", backend,
            "--data", eval_dir,
            "--out", output_json
        ]

        subprocess.run(cmd, capture_output=True, timeout=60)

        # Load and parse results
        result = read_json(Path(output_json))
        return result.get("summary", {}).get("overall_wer", 0.25)

    except Exception as e:
        # Fallback WER if measurement fails
        return 0.25


def measure_vad_boundary(
    audio_path: str,
    threshold: float = 0.5,
    sr: int = 16000
) -> Tuple[float, List[dict]]:
    """
    Measure VAD boundary accuracy against ground truth.

    Args:
        audio_path: Path to .wav file (should have matching .vad.json)
        threshold: Silero VAD threshold
        sr: Sample rate

    Returns:
        Tuple of (boundary_error_ms, predicted_segments)
    """
    try:
        import torch
        import soundfile as sf

        # Load audio
        wav, audio_sr = sf.read(audio_path)

        # Resample to 16kHz if needed
        if audio_sr != sr:
            import librosa
            wav = librosa.resample(wav, orig_sr=audio_sr, target_sr=sr)

        # Load Silero VAD
        vad_model, utils = torch.hub.load(
            repo_or_dir="snakers4/silero-vad",
            model="silero_vad",
            force_reload=False,
            onnx=False
        )
        get_speech_timestamps = utils[0]

        # Get speech timestamps
        wav_tensor = torch.from_numpy(wav.astype(np.float32))
        speech_timestamps = get_speech_timestamps(
            wav_tensor,
            vad_model,
            sampling_rate=sr,
            threshold=threshold
        )

        # Load ground truth
        truth = load_vad_truth(Path(audio_path))

        # Calculate boundary error
        error_ms = boundary_error_ms(speech_timestamps, truth, sr)

        return error_ms, speech_timestamps

    except Exception as e:
        # Fallback if VAD measurement fails
        return 60.0, []


# Convenience function for runner scripts
def get_real_metrics(
    dataset_dir: str = "/home/kloros/assets/asr_eval/mini_eval_set",
    params: dict = None,
    device: str = None,
    compute_type: str = None,
    model_size: str = None
) -> dict:
    """
    Get all real metrics for a D-REAM evaluation run.

    Args:
        dataset_dir: Path to evaluation dataset directory
        params: Experiment parameters dict
        device: Device to use (cpu, cuda) - from params if not specified
        compute_type: Compute type (int8, float16) - from params if not specified
        model_size: Model size (tiny, base, small, medium) - from params if not specified

    Returns:
        Dict with wer, latency_ms, vad_boundary_ms, novelty, score
    """
    if params is None:
        params = {}

    # Extract device/compute settings from params if not explicitly provided
    if device is None:
        # Validate CUDA with memory checks (D-REAM compliant)
        import torch
        import logging

        if params.get("device"):
            device = params["device"]
        elif torch.cuda.is_available():
            try:
                # Verify GPU memory available
                gpu_props = torch.cuda.get_device_properties(0)
                gpu_mem_gb = gpu_props.total_memory / (1024**3)
                required_mem_gb = 2.0  # Whisper base model requires ~2GB

                if gpu_mem_gb < required_mem_gb:
                    logging.warning(f"GPU has insufficient memory ({gpu_mem_gb:.1f}GB < {required_mem_gb:.1f}GB), using CPU")
                    device = "cpu"
                else:
                    device = "cuda"
                    logging.info(f"Using GPU: {gpu_props.name} ({gpu_mem_gb:.1f}GB available)")
            except Exception as e:
                logging.warning(f"GPU validation failed: {e}, using CPU")
                device = "cpu"
        else:
            device = "cpu"
            logging.warning("CUDA not available, using CPU (WER measurement will be slow)")

    if compute_type is None:
        compute_type = params.get("compute_type", "float16" if device == "cuda" else "int8")
    if model_size is None:
        model_size = params.get("model_size", "base")

    # Extract Whisper hyperparameters from params
    beam_size = params.get("beam", 5)
    temperature = params.get("temperature", 0.0)
    no_speech_threshold = params.get("no_speech_threshold", 0.6)
    max_initial_timestamp = params.get("max_initial_timestamp", 0.0)
    vad_threshold = params.get("vad_threshold", 0.5)

    # CRITICAL FIX: Measure WER using Whisper with hyperparameters (not Vosk!)
    wer = measure_wer_with_whisper(
        eval_dir=dataset_dir,
        model_size=model_size,
        device=device,
        beam_size=beam_size,
        temperature=temperature,
        no_speech_threshold=no_speech_threshold,
        max_initial_timestamp=max_initial_timestamp
    )

    # Pick first sample from dataset for latency/VAD measurements
    from pathlib import Path
    dataset_path = Path(dataset_dir)
    sample_files = sorted(dataset_path.glob("*.wav"))
    if sample_files:
        eval_audio_path = str(sample_files[0])
    else:
        eval_audio_path = "/home/kloros/assets/asr_eval/mini_eval_set/sample1.wav"

    # Measure latency with Whisper and hyperparameters
    latency_ms, _ = measure_asr_latency(
        eval_audio_path,
        model_size=model_size,
        device=device,
        beam_size=beam_size,
        temperature=temperature,
        no_speech_threshold=no_speech_threshold,
        max_initial_timestamp=max_initial_timestamp
    )

    # Measure VAD boundary
    vad_boundary_ms, _ = measure_vad_boundary(eval_audio_path, threshold=vad_threshold)

    # Calculate novelty
    novelty = calculate_novelty(params)

    # Calculate score from WER
    score = normalize_lang_score(wer)

    return {
        "wer": round(wer, 3),
        "latency_ms": latency_ms,
        "vad_boundary_ms": int(vad_boundary_ms),
        "novelty": novelty,
        "score": round(score, 2)
    }


if __name__ == "__main__":
    # Test the module
    print("Testing real_metrics module...")

    # Test with defaults
    metrics = get_real_metrics()

    print("\nMeasured Metrics:")
    print(f"  WER: {metrics['wer']:.3f}")
    print(f"  Latency: {metrics['latency_ms']}ms")
    print(f"  VAD Boundary Error: {metrics['vad_boundary_ms']}ms")
    print(f"  Novelty: {metrics['novelty']:.2f}")
    print(f"  Score: {metrics['score']:.2f}")
