#!/usr/bin/env python3
"""
Noise Floor Analysis Tool

Analyzes recorded silence to measure system noise floor and dynamic range.
Uses A-weighting and provides detailed frequency analysis.

Usage:
    python3 noise_floor.py silence.wav --out noise_floor.json
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


def a_weighting_filter(sample_rate):
    """Design A-weighting filter for perceptual noise measurement."""
    # A-weighting filter coefficients (IIR design)
    # Simplified implementation - full A-weighting is more complex
    nyquist = sample_rate / 2

    # High-pass to remove DC and low frequencies
    sos_hp = scipy.signal.butter(2, 20 / nyquist, btype='high', output='sos')

    # Emphasis around 1-4kHz (simplified A-weighting curve)
    sos_peak = scipy.signal.butter(2, [500 / nyquist, 4000 / nyquist], btype='band', output='sos')

    return [sos_hp, sos_peak]


def apply_a_weighting(audio, sample_rate):
    """Apply A-weighting filter to audio signal."""
    filters = a_weighting_filter(sample_rate)

    # Apply high-pass
    filtered = scipy.signal.sosfilt(filters[0], audio)

    # Apply peak emphasis (reduced gain for simplified implementation)
    emphasis = scipy.signal.sosfilt(filters[1], audio) * 0.3

    # Combine
    a_weighted = filtered + emphasis

    return a_weighted


def analyze_noise_floor(audio, sample_rate, segment_duration=1.0):
    """Analyze noise floor characteristics."""
    segment_samples = int(sample_rate * segment_duration)

    # Split into segments for statistical analysis
    segments = []
    for i in range(0, len(audio) - segment_samples, segment_samples):
        segment = audio[i:i + segment_samples]
        segments.append(segment)

    if not segments:
        segments = [audio]  # Use whole signal if too short

    # RMS analysis per segment
    rms_values = []
    for segment in segments:
        rms = np.sqrt(np.mean(segment ** 2))
        rms_values.append(rms)

    rms_values = np.array(rms_values)

    # Overall statistics
    rms_mean = np.mean(rms_values)
    rms_std = np.std(rms_values)
    rms_min = np.min(rms_values)
    rms_max = np.max(rms_values)

    # Convert to dB
    rms_mean_db = 20 * np.log10(rms_mean + 1e-12)
    rms_std_db = 20 * np.log10(rms_std + 1e-12) if rms_std > 0 else -120
    rms_min_db = 20 * np.log10(rms_min + 1e-12)
    rms_max_db = 20 * np.log10(rms_max + 1e-12)

    return {
        "rms_mean_db": float(rms_mean_db),
        "rms_std_db": float(rms_std_db),
        "rms_min_db": float(rms_min_db),
        "rms_max_db": float(rms_max_db),
        "segments_analyzed": len(segments),
        "segment_duration_s": segment_duration
    }


def frequency_analysis(audio, sample_rate):
    """Analyze frequency content of noise floor."""
    # FFT analysis
    fft = np.fft.fft(audio)
    freqs = np.fft.fftfreq(len(audio), 1/sample_rate)

    # Only use positive frequencies
    positive_freqs = freqs[:len(freqs)//2]
    magnitude = np.abs(fft[:len(fft)//2])

    # Convert to dB
    magnitude_db = 20 * np.log10(magnitude + 1e-12)

    # Octave band analysis (simplified)
    octave_bands = [
        (20, 40),     # Sub-bass
        (40, 80),     # Bass
        (80, 160),    # Low-mid
        (160, 320),   # Mid
        (320, 640),   # Upper-mid
        (640, 1280),  # Presence
        (1280, 2560), # Brilliance-low
        (2560, 5120), # Brilliance-mid
        (5120, 10240), # Brilliance-high
        (10240, 20000) # Air
    ]

    band_levels = {}
    for low, high in octave_bands:
        # Find frequencies in this band
        band_mask = (positive_freqs >= low) & (positive_freqs <= high)
        if np.any(band_mask):
            band_energy = np.mean(magnitude[band_mask])
            band_db = 20 * np.log10(band_energy + 1e-12)
            band_levels[f"{low}-{high}Hz"] = float(band_db)

    # Find peak frequency
    peak_idx = np.argmax(magnitude)
    peak_freq = positive_freqs[peak_idx]
    peak_level_db = magnitude_db[peak_idx]

    return {
        "peak_frequency_hz": float(peak_freq),
        "peak_level_db": float(peak_level_db),
        "octave_bands_db": band_levels,
        "overall_bandwidth_hz": float(positive_freqs[-1])
    }


def estimate_dynamic_range(noise_floor_db, sample_rate, bit_depth=16):
    """Estimate system dynamic range based on noise floor."""
    # Theoretical maximum for given bit depth
    if bit_depth == 16:
        theoretical_max_db = 0  # 0 dBFS
        theoretical_min_db = -96  # ~16 * 6 dB
    elif bit_depth == 24:
        theoretical_max_db = 0
        theoretical_min_db = -144  # ~24 * 6 dB
    else:
        theoretical_max_db = 0
        theoretical_min_db = -bit_depth * 6

    # Practical dynamic range
    practical_max_db = -1  # Leave 1dB headroom
    usable_dynamic_range = practical_max_db - noise_floor_db
    theoretical_dynamic_range = theoretical_max_db - theoretical_min_db

    return {
        "theoretical_max_db": theoretical_max_db,
        "theoretical_min_db": theoretical_min_db,
        "theoretical_range_db": float(theoretical_dynamic_range),
        "noise_floor_db": noise_floor_db,
        "usable_range_db": float(usable_dynamic_range),
        "efficiency_percent": float(100 * usable_dynamic_range / theoretical_dynamic_range)
    }


def main():
    parser = argparse.ArgumentParser(description="Analyze audio noise floor")
    parser.add_argument("audio_file", help="Path to silence recording")
    parser.add_argument("--out", required=True, help="Output JSON file")
    parser.add_argument("--segment-duration", type=float, default=1.0,
                        help="Segment duration for analysis (seconds)")

    args = parser.parse_args()

    # Load audio
    sample_rate, audio = load_audio(args.audio_file)

    print(f"Analyzing noise floor: {args.audio_file}")
    print(f"Sample rate: {sample_rate} Hz")
    print(f"Duration: {len(audio) / sample_rate:.2f} seconds")

    results = {
        "file": str(args.audio_file),
        "sample_rate": sample_rate,
        "duration_s": len(audio) / sample_rate,
        "bit_depth_assumed": 16  # Default assumption
    }

    # Raw noise floor analysis
    raw_analysis = analyze_noise_floor(audio, sample_rate, args.segment_duration)
    results["raw"] = raw_analysis

    # A-weighted analysis
    a_weighted_audio = apply_a_weighting(audio, sample_rate)
    a_weighted_analysis = analyze_noise_floor(a_weighted_audio, sample_rate, args.segment_duration)
    results["a_weighted"] = a_weighted_analysis

    # Frequency analysis
    freq_analysis = frequency_analysis(audio, sample_rate)
    results["frequency_analysis"] = freq_analysis

    # Dynamic range estimation
    noise_floor_db = raw_analysis["rms_mean_db"]
    dynamic_range = estimate_dynamic_range(noise_floor_db, sample_rate)
    results["dynamic_range"] = dynamic_range

    # Save results
    output_path = Path(args.out)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, 'w') as f:
        json.dump(results, f, indent=2)

    print(f"Results saved to {args.out}")
    print(f"Raw noise floor: {raw_analysis['rms_mean_db']:.1f} dB")
    print(f"A-weighted noise floor: {a_weighted_analysis['rms_mean_db']:.1f} dB")
    print(f"Usable dynamic range: {dynamic_range['usable_range_db']:.1f} dB")


if __name__ == "__main__":
    main()