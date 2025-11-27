#!/usr/bin/env python3
"""
Audio Latency and Jitter Analysis Tool

Analyzes recorded loopback audio to measure:
- Round-trip latency using cross-correlation
- Jitter (latency variance over time)
- Audio quality metrics

Usage:
    python3 latency_jitter.py recorded.wav --buf-ms 16 --out results.json
"""

import argparse
import json
import numpy as np
import scipy.io.wavfile
import scipy.signal
from pathlib import Path


def load_audio(filepath):
    """Load audio file and return sample rate and data."""
    sample_rate, data = scipy.io.wavfile.read(filepath)

    # Convert to float32 and normalize
    if data.dtype == np.int16:
        data = data.astype(np.float32) / 32768.0
    elif data.dtype == np.int32:
        data = data.astype(np.float32) / 2147483648.0

    # Convert stereo to mono if needed
    if len(data.shape) > 1:
        data = np.mean(data, axis=1)

    return sample_rate, data


def detect_pink_noise_bursts(audio, sample_rate, min_duration_ms=100):
    """Detect pink noise bursts in the audio signal."""
    # Simple energy-based detection
    window_size = int(sample_rate * min_duration_ms / 1000)
    hop_size = window_size // 4

    energy = []
    positions = []

    for i in range(0, len(audio) - window_size, hop_size):
        window = audio[i:i + window_size]
        rms = np.sqrt(np.mean(window ** 2))
        energy.append(rms)
        positions.append(i)

    energy = np.array(energy)
    positions = np.array(positions)

    # Find peaks above threshold
    threshold = np.mean(energy) + 2 * np.std(energy)
    peaks, _ = scipy.signal.find_peaks(energy, height=threshold, distance=sample_rate)

    return positions[peaks]


def measure_latency_cross_correlation(reference_audio, recorded_audio, sample_rate):
    """Measure latency using cross-correlation between reference and recorded audio."""
    # Ensure same length
    min_len = min(len(reference_audio), len(recorded_audio))
    ref = reference_audio[:min_len]
    rec = recorded_audio[:min_len]

    # Cross-correlation
    correlation = scipy.signal.correlate(rec, ref, mode='full')

    # Find peak
    peak_idx = np.argmax(np.abs(correlation))

    # Convert to time delay
    delay_samples = peak_idx - (len(ref) - 1)
    delay_ms = (delay_samples / sample_rate) * 1000

    # Correlation strength
    max_correlation = np.abs(correlation[peak_idx])
    normalized_correlation = max_correlation / (np.linalg.norm(ref) * np.linalg.norm(rec))

    return delay_ms, normalized_correlation


def analyze_jitter(burst_positions, sample_rate, expected_interval_ms=None):
    """Analyze timing jitter between detected bursts."""
    if len(burst_positions) < 2:
        return {"jitter_ms": 0, "intervals": [], "std_ms": 0}

    # Calculate intervals between bursts
    intervals_samples = np.diff(burst_positions)
    intervals_ms = (intervals_samples / sample_rate) * 1000

    # Jitter is standard deviation of intervals
    jitter_ms = np.std(intervals_ms)

    return {
        "jitter_ms": float(jitter_ms),
        "intervals_ms": intervals_ms.tolist(),
        "mean_interval_ms": float(np.mean(intervals_ms)),
        "std_ms": float(jitter_ms)
    }


def analyze_audio_quality(audio, sample_rate):
    """Analyze basic audio quality metrics."""
    # RMS level
    rms = np.sqrt(np.mean(audio ** 2))
    rms_db = 20 * np.log10(rms + 1e-12)

    # Peak level
    peak = np.max(np.abs(audio))
    peak_db = 20 * np.log10(peak + 1e-12)

    # THD+N estimation (simplified)
    # Use high-frequency content as noise estimate
    freq_bins = np.fft.fft(audio)
    freq_mag = np.abs(freq_bins)

    # Estimate noise floor from high frequencies
    noise_start = len(freq_mag) // 2
    noise_estimate = np.mean(freq_mag[noise_start:])
    signal_estimate = np.mean(freq_mag[:noise_start])

    thdn_ratio = noise_estimate / (signal_estimate + 1e-12)
    thdn_db = 20 * np.log10(thdn_ratio + 1e-12)

    return {
        "rms_db": float(rms_db),
        "peak_db": float(peak_db),
        "thdn_db": float(thdn_db),
        "dynamic_range_db": float(peak_db - rms_db)
    }


def main():
    parser = argparse.ArgumentParser(description="Analyze audio latency and jitter")
    parser.add_argument("audio_file", help="Path to recorded audio file")
    parser.add_argument("--buf-ms", type=int, help="Expected buffer size in ms")
    parser.add_argument("--out", required=True, help="Output JSON file")
    parser.add_argument("--reference", help="Reference audio file (if available)")

    args = parser.parse_args()

    # Load recorded audio
    sample_rate, recorded_audio = load_audio(args.audio_file)

    print(f"Analyzing {args.audio_file}")
    print(f"Sample rate: {sample_rate} Hz")
    print(f"Duration: {len(recorded_audio) / sample_rate:.2f} seconds")

    # Detect bursts in recorded audio
    burst_positions = detect_pink_noise_bursts(recorded_audio, sample_rate)
    print(f"Detected {len(burst_positions)} audio bursts")

    results = {
        "file": str(args.audio_file),
        "sample_rate": sample_rate,
        "duration_s": len(recorded_audio) / sample_rate,
        "buffer_ms": args.buf_ms,
        "bursts_detected": len(burst_positions)
    }

    # Analyze jitter
    jitter_analysis = analyze_jitter(burst_positions, sample_rate)
    results["jitter"] = jitter_analysis

    # Audio quality analysis
    quality_analysis = analyze_audio_quality(recorded_audio, sample_rate)
    results["quality"] = quality_analysis

    # If reference audio provided, measure cross-correlation latency
    if args.reference:
        ref_sample_rate, reference_audio = load_audio(args.reference)
        if ref_sample_rate == sample_rate:
            latency_ms, correlation = measure_latency_cross_correlation(
                reference_audio, recorded_audio, sample_rate
            )
            results["cross_correlation"] = {
                "latency_ms": float(latency_ms),
                "correlation_strength": float(correlation)
            }
            print(f"Cross-correlation latency: {latency_ms:.2f} ms")

    # Estimate round-trip latency from buffer size
    if args.buf_ms:
        estimated_latency = args.buf_ms * 2  # Input + output buffer
        results["estimated_latency_ms"] = estimated_latency
        print(f"Estimated round-trip latency: {estimated_latency} ms")

    # Save results
    output_path = Path(args.out)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, 'w') as f:
        json.dump(results, f, indent=2)

    print(f"Results saved to {args.out}")
    print(f"Jitter: {jitter_analysis['jitter_ms']:.2f} ms")
    print(f"Audio quality: {quality_analysis['rms_db']:.1f} dB RMS")


if __name__ == "__main__":
    main()