#!/usr/bin/env python3
"""
Wake Word Evaluation Tool

Tests wake word detection accuracy using positive and negative samples.
Measures false positive rate (FPR) and false negative rate (FNR).

Usage:
    python3 wake_eval.py --keyword "kloros" --negatives path/to/negatives --out wake_metrics.json
"""

import argparse
import json
import os
import glob
from pathlib import Path
import subprocess
import tempfile


def transcribe_with_vosk(audio_file, vosk_url="http://localhost:8080"):
    """Transcribe audio file using Vosk HTTP service."""
    try:
        # Use curl to send audio file to Vosk service
        cmd = [
            "curl", "-X", "POST",
            "-H", "Content-Type: audio/wav",
            "--data-binary", f"@{audio_file}",
            f"{vosk_url}/transcribe"
        ]

        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)

        if result.returncode == 0:
            try:
                response = json.loads(result.stdout)
                return response.get("text", "").lower().strip()
            except json.JSONDecodeError:
                return ""
        return ""

    except (subprocess.TimeoutExpired, subprocess.CalledProcessError, FileNotFoundError):
        return ""


def contains_wake_word(transcript, keyword, fuzzy_threshold=0.8):
    """Check if transcript contains wake word using fuzzy matching."""
    if not transcript:
        return False

    keyword = keyword.lower()
    transcript = transcript.lower()

    # Exact match
    if keyword in transcript:
        return True

    # Fuzzy matching using simple edit distance
    words = transcript.split()

    for word in words:
        # Simple Levenshtein-like similarity
        if len(word) == 0:
            continue

        # Calculate similarity ratio
        longer = max(len(keyword), len(word))
        shorter = min(len(keyword), len(word))

        if shorter == 0:
            continue

        # Count matching characters (simplified)
        matches = 0
        for i in range(min(len(keyword), len(word))):
            if i < len(keyword) and i < len(word) and keyword[i] == word[i]:
                matches += 1

        similarity = matches / longer

        if similarity >= fuzzy_threshold:
            return True

    return False


def evaluate_positive_samples(keyword, positive_samples=None, vosk_url="http://localhost:8080", fuzzy_threshold=0.8):
    """Evaluate wake word detection on positive samples."""
    if positive_samples is None:
        # Create synthetic positive samples using TTS
        positive_samples = create_synthetic_positives(keyword)

    results = []
    true_positives = 0
    total_positives = 0

    for sample_file in positive_samples:
        if not os.path.exists(sample_file):
            continue

        print(f"Testing positive sample: {sample_file}")

        transcript = transcribe_with_vosk(sample_file, vosk_url)
        detected = contains_wake_word(transcript, keyword, fuzzy_threshold)

        results.append({
            "file": str(sample_file),
            "transcript": transcript,
            "detected": detected,
            "expected": True
        })

        total_positives += 1
        if detected:
            true_positives += 1

    fnr = (total_positives - true_positives) / total_positives if total_positives > 0 else 0
    sensitivity = true_positives / total_positives if total_positives > 0 else 0

    return {
        "samples": results,
        "true_positives": true_positives,
        "total_positives": total_positives,
        "false_negative_rate": fnr,
        "sensitivity": sensitivity
    }


def evaluate_negative_samples(keyword, negative_dir, vosk_url="http://localhost:8080", fuzzy_threshold=0.8):
    """Evaluate wake word detection on negative samples."""
    negative_files = []

    # Find all audio files in negative directory
    for ext in ["*.wav", "*.mp3", "*.flac", "*.m4a"]:
        pattern = os.path.join(negative_dir, "**", ext)
        negative_files.extend(glob.glob(pattern, recursive=True))

    results = []
    false_positives = 0
    total_negatives = 0

    for sample_file in negative_files[:50]:  # Limit to first 50 for speed
        print(f"Testing negative sample: {sample_file}")

        transcript = transcribe_with_vosk(sample_file, vosk_url)
        detected = contains_wake_word(transcript, keyword, fuzzy_threshold)

        results.append({
            "file": str(sample_file),
            "transcript": transcript,
            "detected": detected,
            "expected": False
        })

        total_negatives += 1
        if detected:
            false_positives += 1

    fpr = false_positives / total_negatives if total_negatives > 0 else 0
    specificity = (total_negatives - false_positives) / total_negatives if total_negatives > 0 else 0

    return {
        "samples": results,
        "false_positives": false_positives,
        "total_negatives": total_negatives,
        "false_positive_rate": fpr,
        "specificity": specificity
    }


def create_synthetic_positives(keyword, num_samples=5):
    """Create synthetic positive samples using TTS."""
    # Try to use available TTS systems
    synthetic_files = []

    with tempfile.TemporaryDirectory() as temp_dir:
        variations = [
            keyword,
            f"hey {keyword}",
            f"{keyword} please",
            f"ok {keyword}",
            f"{keyword} listen"
        ]

        for i, phrase in enumerate(variations):
            output_file = os.path.join(temp_dir, f"positive_{i}.wav")

            # Try Piper TTS if available
            try:
                cmd = [
                    "echo", phrase, "|",
                    "piper", "--model", "/home/kloros/kloros_models/piper/glados_piper_medium.onnx",
                    "--output_file", output_file
                ]
                subprocess.run(" ".join(cmd), shell=True, check=True, capture_output=True)

                if os.path.exists(output_file):
                    # Copy to permanent location
                    perm_file = f"/tmp/wake_positive_{i}.wav"
                    subprocess.run(["cp", output_file, perm_file], check=True)
                    synthetic_files.append(perm_file)

            except (subprocess.CalledProcessError, FileNotFoundError):
                # Try espeak as fallback
                try:
                    cmd = [
                        "espeak", "-w", output_file, phrase
                    ]
                    subprocess.run(cmd, check=True, capture_output=True)

                    if os.path.exists(output_file):
                        perm_file = f"/tmp/wake_positive_{i}.wav"
                        subprocess.run(["cp", output_file, perm_file], check=True)
                        synthetic_files.append(perm_file)

                except (subprocess.CalledProcessError, FileNotFoundError):
                    continue

    return synthetic_files


def main():
    parser = argparse.ArgumentParser(description="Evaluate wake word detection")
    parser.add_argument("--keyword", required=True, help="Wake word to test")
    parser.add_argument("--negatives", help="Directory containing negative samples")
    parser.add_argument("--positives", help="Directory containing positive samples")
    parser.add_argument("--out", required=True, help="Output JSON file")
    parser.add_argument("--vosk-url", default="http://localhost:8080",
                        help="Vosk HTTP service URL")
    parser.add_argument("--fuzzy-threshold", type=float, default=0.8,
                        help="Fuzzy matching threshold (0.0-1.0)")

    args = parser.parse_args()

    print(f"Evaluating wake word: '{args.keyword}'")
    print(f"Vosk service: {args.vosk_url}")

    results = {
        "keyword": args.keyword,
        "vosk_url": args.vosk_url,
        "fuzzy_threshold": args.fuzzy_threshold,
        "timestamp": subprocess.run(["date", "-Iseconds"], capture_output=True, text=True).stdout.strip()
    }

    # Test positive samples
    positive_files = []
    if args.positives and os.path.exists(args.positives):
        for ext in ["*.wav", "*.mp3", "*.flac", "*.m4a"]:
            pattern = os.path.join(args.positives, "**", ext)
            positive_files.extend(glob.glob(pattern, recursive=True))

    if not positive_files:
        print("No positive samples found, creating synthetic samples...")

    positive_results = evaluate_positive_samples(
        args.keyword, positive_files or None, args.vosk_url, args.fuzzy_threshold
    )
    results["positive_evaluation"] = positive_results

    # Test negative samples
    if args.negatives and os.path.exists(args.negatives):
        negative_results = evaluate_negative_samples(
            args.keyword, args.negatives, args.vosk_url, args.fuzzy_threshold
        )
        results["negative_evaluation"] = negative_results
    else:
        print("No negative samples directory provided, skipping FPR evaluation")
        results["negative_evaluation"] = None

    # Calculate overall metrics
    fnr = positive_results["false_negative_rate"]
    fpr = negative_results["false_positive_rate"] if results["negative_evaluation"] else 0.0

    results["summary"] = {
        "false_negative_rate": fnr,
        "false_positive_rate": fpr,
        "sensitivity": positive_results["sensitivity"],
        "specificity": negative_results["specificity"] if results["negative_evaluation"] else 1.0,
        "accuracy": 1.0 - ((fnr + fpr) / 2)
    }

    # Save results
    output_path = Path(args.out)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, 'w') as f:
        json.dump(results, f, indent=2)

    print(f"Results saved to {args.out}")
    print(f"Wake word accuracy: {results['summary']['accuracy']:.1%}")
    print(f"False negative rate: {fnr:.1%}")
    print(f"False positive rate: {fpr:.1%}")


if __name__ == "__main__":
    main()