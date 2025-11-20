#!/usr/bin/env python3
"""
Audio Clipping and Level Scanner

Analyzes audio files for clipping, level distribution, and quality issues.
Reports peak levels, RMS levels, and clipping statistics.

Usage:
    python3 clip_scan.py file1.wav file2.wav --out levels.json
"""

import argparse
import json
import numpy as np
import scipy.io.wavfile
import glob
from pathlib import Path


def load_audio(filepath):
    """Load audio file and return sample rate and data."""
    try:
        sample_rate, data = scipy.io.wavfile.read(filepath)

        # Convert to float32 and normalize
        if data.dtype == np.int16:
            data = data.astype(np.float32) / 32768.0
        elif data.dtype == np.int32:
            data = data.astype(np.float32) / 2147483648.0
        elif data.dtype == np.uint8:
            data = (data.astype(np.float32) - 128.0) / 128.0
        elif data.dtype in [np.float32, np.float64]:
            data = data.astype(np.float32)

        # Convert stereo to mono if needed
        if len(data.shape) > 1:
            data = np.mean(data, axis=1)

        return sample_rate, data

    except Exception as e:
        print(f"Error loading {filepath}: {e}")
        return None, None


def detect_clipping(audio, threshold=0.99):
    """Detect clipping in audio signal."""
    if audio is None or len(audio) == 0:
        return {
            "clipped_samples": 0,
            "total_samples": 0,
            "clipping_percentage": 0.0,
            "consecutive_clips": []
        }

    # Find samples above threshold
    clipped_mask = np.abs(audio) >= threshold
    clipped_samples = np.sum(clipped_mask)
    total_samples = len(audio)
    clipping_percentage = (clipped_samples / total_samples) * 100

    # Find consecutive clipping regions
    consecutive_clips = []
    in_clip = False
    clip_start = 0

    for i, is_clipped in enumerate(clipped_mask):
        if is_clipped and not in_clip:
            # Start of clipping region
            in_clip = True
            clip_start = i
        elif not is_clipped and in_clip:
            # End of clipping region
            in_clip = False
            clip_length = i - clip_start
            consecutive_clips.append({
                "start_sample": clip_start,
                "length_samples": clip_length,
                "duration_ms": clip_length / (len(audio) / 1000)  # Approximate
            })

    # Handle case where clipping continues to end
    if in_clip:
        clip_length = len(audio) - clip_start
        consecutive_clips.append({
            "start_sample": clip_start,
            "length_samples": clip_length,
            "duration_ms": clip_length / (len(audio) / 1000)
        })

    return {
        "clipped_samples": int(clipped_samples),
        "total_samples": int(total_samples),
        "clipping_percentage": float(clipping_percentage),
        "consecutive_clips": consecutive_clips,
        "max_consecutive_length": max([c["length_samples"] for c in consecutive_clips]) if consecutive_clips else 0
    }


def analyze_levels(audio, sample_rate):
    """Analyze audio levels and dynamics."""
    if audio is None or len(audio) == 0:
        return {}

    # Basic levels
    rms = np.sqrt(np.mean(audio ** 2))
    peak = np.max(np.abs(audio))

    # Convert to dB
    rms_db = 20 * np.log10(rms + 1e-12)
    peak_db = 20 * np.log10(peak + 1e-12)

    # Crest factor (peak to RMS ratio)
    crest_factor = peak / (rms + 1e-12)
    crest_factor_db = 20 * np.log10(crest_factor)

    # Level histogram
    hist_bins = 50
    hist, bin_edges = np.histogram(np.abs(audio), bins=hist_bins, range=(0, 1))
    hist_percentages = (hist / len(audio)) * 100

    # Percentile levels
    abs_audio = np.abs(audio)
    percentiles = [10, 25, 50, 75, 90, 95, 99]
    level_percentiles = {}
    for p in percentiles:
        level = np.percentile(abs_audio, p)
        level_db = 20 * np.log10(level + 1e-12)
        level_percentiles[f"p{p}"] = {
            "linear": float(level),
            "db": float(level_db)
        }

    # Dynamic range estimation
    noise_floor_db = level_percentiles["p10"]["db"]
    dynamic_range_db = peak_db - noise_floor_db

    # Loudness estimation (simplified LUFS approximation)
    # This is a very rough approximation - proper LUFS requires K-weighting
    window_size = int(sample_rate * 0.4)  # 400ms windows
    hop_size = window_size // 2

    momentary_loudness = []
    for i in range(0, len(audio) - window_size, hop_size):
        window = audio[i:i + window_size]
        window_rms = np.sqrt(np.mean(window ** 2))
        window_lufs = -0.691 + 10 * np.log10(window_rms ** 2 + 1e-12)  # Rough approximation
        momentary_loudness.append(window_lufs)

    if momentary_loudness:
        integrated_loudness = np.mean(momentary_loudness)
        max_momentary = np.max(momentary_loudness)
        loudness_range = np.percentile(momentary_loudness, 95) - np.percentile(momentary_loudness, 10)
    else:
        integrated_loudness = -120
        max_momentary = -120
        loudness_range = 0

    return {
        "rms_linear": float(rms),
        "rms_db": float(rms_db),
        "peak_linear": float(peak),
        "peak_db": float(peak_db),
        "crest_factor": float(crest_factor),
        "crest_factor_db": float(crest_factor_db),
        "dynamic_range_db": float(dynamic_range_db),
        "level_percentiles": level_percentiles,
        "loudness_estimation": {
            "integrated_lufs": float(integrated_loudness),
            "max_momentary_lufs": float(max_momentary),
            "loudness_range_lu": float(loudness_range)
        },
        "level_histogram": {
            "bins": hist.tolist(),
            "bin_edges": bin_edges.tolist(),
            "percentages": hist_percentages.tolist()
        }
    }


def analyze_audio_file(filepath):
    """Analyze a single audio file for clipping and levels."""
    sample_rate, audio = load_audio(filepath)

    if audio is None:
        return {
            "file": str(filepath),
            "error": "Could not load audio file",
            "sample_rate": None,
            "duration_s": None
        }

    duration_s = len(audio) / sample_rate

    # Clipping analysis
    clipping_analysis = detect_clipping(audio)

    # Level analysis
    level_analysis = analyze_levels(audio, sample_rate)

    # Quality assessment
    quality_issues = []

    if clipping_analysis["clipping_percentage"] > 0.1:
        quality_issues.append(f"Clipping detected: {clipping_analysis['clipping_percentage']:.2f}%")

    if level_analysis["peak_db"] > -1:
        quality_issues.append(f"Peak level too high: {level_analysis['peak_db']:.1f} dB")

    if level_analysis["peak_db"] < -20:
        quality_issues.append(f"Peak level too low: {level_analysis['peak_db']:.1f} dB")

    if level_analysis["crest_factor_db"] < 3:
        quality_issues.append(f"Low crest factor (over-compressed): {level_analysis['crest_factor_db']:.1f} dB")

    if level_analysis["dynamic_range_db"] < 6:
        quality_issues.append(f"Limited dynamic range: {level_analysis['dynamic_range_db']:.1f} dB")

    return {
        "file": str(filepath),
        "sample_rate": sample_rate,
        "duration_s": float(duration_s),
        "clipping_analysis": clipping_analysis,
        "level_analysis": level_analysis,
        "quality_issues": quality_issues,
        "overall_quality": "good" if not quality_issues else "issues_detected"
    }


def main():
    parser = argparse.ArgumentParser(description="Scan audio files for clipping and level issues")
    parser.add_argument("files", nargs="+", help="Audio files to analyze (supports wildcards)")
    parser.add_argument("--out", required=True, help="Output JSON file")
    parser.add_argument("--threshold", type=float, default=0.99,
                        help="Clipping detection threshold (0.0-1.0)")

    args = parser.parse_args()

    # Expand wildcards
    all_files = []
    for file_pattern in args.files:
        if '*' in file_pattern or '?' in file_pattern:
            all_files.extend(glob.glob(file_pattern))
        else:
            all_files.append(file_pattern)

    if not all_files:
        print("No files found to analyze")
        return

    print(f"Analyzing {len(all_files)} audio files...")

    results = []
    summary_stats = {
        "total_files": len(all_files),
        "files_with_clipping": 0,
        "files_with_issues": 0,
        "avg_peak_db": 0.0,
        "avg_rms_db": 0.0,
        "avg_dynamic_range_db": 0.0
    }

    valid_files = 0
    total_peak_db = 0.0
    total_rms_db = 0.0
    total_dynamic_range_db = 0.0

    for filepath in all_files:
        print(f"Analyzing: {filepath}")
        result = analyze_audio_file(filepath)
        results.append(result)

        if "error" not in result:
            valid_files += 1

            if result["clipping_analysis"]["clipping_percentage"] > 0:
                summary_stats["files_with_clipping"] += 1

            if result["quality_issues"]:
                summary_stats["files_with_issues"] += 1

            total_peak_db += result["level_analysis"]["peak_db"]
            total_rms_db += result["level_analysis"]["rms_db"]
            total_dynamic_range_db += result["level_analysis"]["dynamic_range_db"]

    if valid_files > 0:
        summary_stats["avg_peak_db"] = total_peak_db / valid_files
        summary_stats["avg_rms_db"] = total_rms_db / valid_files
        summary_stats["avg_dynamic_range_db"] = total_dynamic_range_db / valid_files

    summary_stats["valid_files"] = valid_files

    # Save results
    output_data = {
        "summary": summary_stats,
        "detailed_results": results,
        "analysis_parameters": {
            "clipping_threshold": args.threshold
        }
    }

    output_path = Path(args.out)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, 'w') as f:
        json.dump(output_data, f, indent=2)

    print(f"\nResults saved to {args.out}")
    print(f"Files analyzed: {valid_files}/{len(all_files)}")
    print(f"Files with clipping: {summary_stats['files_with_clipping']}")
    print(f"Files with quality issues: {summary_stats['files_with_issues']}")
    print(f"Average peak level: {summary_stats['avg_peak_db']:.1f} dB")


if __name__ == "__main__":
    main()