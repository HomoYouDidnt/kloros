#!/usr/bin/env python3
"""
ASR Word Error Rate (WER) Evaluation Tool

Measures speech recognition accuracy by comparing transcripts to reference text.
Calculates WER, substitutions, insertions, and deletions.

Usage:
    python3 asr_wer.py --backend vosk --data eval_set_dir --out wer.json
"""

import argparse
import json
import os
import glob
from pathlib import Path
import subprocess
import Levenshtein


def transcribe_with_vosk(audio_file, vosk_url="http://localhost:8080"):
    """Transcribe audio file using Vosk HTTP service."""
    try:
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


def normalize_text(text):
    """Normalize text for WER calculation."""
    if not text:
        return ""

    text = text.lower().strip()

    # Remove punctuation
    import string
    text = text.translate(str.maketrans('', '', string.punctuation))

    # Normalize whitespace
    text = ' '.join(text.split())

    return text


def calculate_wer(reference, hypothesis):
    """Calculate Word Error Rate using Levenshtein distance."""
    ref_words = reference.split()
    hyp_words = hypothesis.split()

    # Handle empty cases
    if not ref_words and not hyp_words:
        return {
            "wer": 0.0,
            "substitutions": 0,
            "insertions": 0,
            "deletions": 0,
            "total_words": 0,
            "correct_words": 0
        }

    if not ref_words:
        return {
            "wer": float('inf') if hyp_words else 0.0,
            "substitutions": 0,
            "insertions": len(hyp_words),
            "deletions": 0,
            "total_words": len(hyp_words),
            "correct_words": 0
        }

    if not hyp_words:
        return {
            "wer": 1.0,
            "substitutions": 0,
            "insertions": 0,
            "deletions": len(ref_words),
            "total_words": len(ref_words),
            "correct_words": 0
        }

    # Calculate edit distance with operation tracking
    operations = Levenshtein.editops(ref_words, hyp_words)

    # Count operations
    substitutions = sum(1 for op in operations if op[0] == 'replace')
    insertions = sum(1 for op in operations if op[0] == 'insert')
    deletions = sum(1 for op in operations if op[0] == 'delete')

    total_errors = substitutions + insertions + deletions
    total_words = len(ref_words)
    correct_words = total_words - deletions - substitutions

    wer = total_errors / total_words if total_words > 0 else 0.0

    return {
        "wer": wer,
        "substitutions": substitutions,
        "insertions": insertions,
        "deletions": deletions,
        "total_words": total_words,
        "correct_words": correct_words
    }


def load_reference_text(audio_file):
    """Load reference text for an audio file."""
    # Try different reference text file patterns
    audio_path = Path(audio_file)
    base_name = audio_path.stem

    # Common patterns for reference files
    possible_ref_files = [
        audio_path.with_suffix('.txt'),
        audio_path.with_suffix('.ref'),
        audio_path.with_suffix('.transcript'),
        audio_path.parent / f"{base_name}.txt",
        audio_path.parent / f"{base_name}.ref",
        audio_path.parent / "transcripts" / f"{base_name}.txt"
    ]

    for ref_file in possible_ref_files:
        if ref_file.exists():
            try:
                with open(ref_file, 'r', encoding='utf-8') as f:
                    return f.read().strip()
            except (IOError, UnicodeDecodeError):
                continue

    return None


def evaluate_dataset(data_dir, backend="vosk", vosk_url="http://localhost:8080"):
    """Evaluate ASR performance on a dataset."""
    # Find all audio files
    audio_files = []
    for ext in ["*.wav", "*.mp3", "*.flac", "*.m4a"]:
        pattern = os.path.join(data_dir, "**", ext)
        audio_files.extend(glob.glob(pattern, recursive=True))

    if not audio_files:
        print(f"No audio files found in {data_dir}")
        return {"error": "No audio files found"}

    print(f"Found {len(audio_files)} audio files")

    results = []
    total_wer = 0.0
    total_files = 0
    total_substitutions = 0
    total_insertions = 0
    total_deletions = 0
    total_words = 0
    files_with_references = 0

    for audio_file in audio_files:
        print(f"Processing: {audio_file}")

        # Load reference text
        reference = load_reference_text(audio_file)
        if not reference:
            print(f"  No reference text found, skipping")
            continue

        reference = normalize_text(reference)

        # Transcribe audio
        if backend == "vosk":
            hypothesis = transcribe_with_vosk(audio_file, vosk_url)
        else:
            print(f"  Unsupported backend: {backend}")
            continue

        hypothesis = normalize_text(hypothesis)

        # Calculate WER
        wer_result = calculate_wer(reference, hypothesis)

        result = {
            "file": str(audio_file),
            "reference": reference,
            "hypothesis": hypothesis,
            "wer": wer_result
        }

        results.append(result)

        # Accumulate statistics
        if wer_result["wer"] != float('inf'):
            total_wer += wer_result["wer"]
            files_with_references += 1

        total_substitutions += wer_result["substitutions"]
        total_insertions += wer_result["insertions"]
        total_deletions += wer_result["deletions"]
        total_words += wer_result["total_words"]
        total_files += 1

        print(f"  WER: {wer_result['wer']:.2%}")

    # Calculate overall statistics
    avg_wer = total_wer / files_with_references if files_with_references > 0 else 0.0
    overall_wer = (total_substitutions + total_insertions + total_deletions) / total_words if total_words > 0 else 0.0

    summary = {
        "total_files": total_files,
        "files_with_references": files_with_references,
        "average_wer": avg_wer,
        "overall_wer": overall_wer,
        "total_words": total_words,
        "total_errors": total_substitutions + total_insertions + total_deletions,
        "total_substitutions": total_substitutions,
        "total_insertions": total_insertions,
        "total_deletions": total_deletions,
        "accuracy": 1.0 - overall_wer
    }

    return {
        "summary": summary,
        "detailed_results": results
    }


def main():
    parser = argparse.ArgumentParser(description="Evaluate ASR Word Error Rate")
    parser.add_argument("--backend", default="vosk", choices=["vosk"],
                        help="ASR backend to evaluate")
    parser.add_argument("--data", required=True, help="Path to evaluation dataset directory")
    parser.add_argument("--out", required=True, help="Output JSON file")
    parser.add_argument("--vosk-url", default="http://localhost:8080",
                        help="Vosk HTTP service URL")

    args = parser.parse_args()

    print(f"Evaluating {args.backend} ASR on dataset: {args.data}")

    # Evaluate dataset
    results = evaluate_dataset(args.data, args.backend, args.vosk_url)

    # Add metadata
    results["metadata"] = {
        "backend": args.backend,
        "dataset_path": str(args.data),
        "vosk_url": args.vosk_url,
        "timestamp": subprocess.run(["date", "-Iseconds"], capture_output=True, text=True).stdout.strip()
    }

    # Save results
    output_path = Path(args.out)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, 'w') as f:
        json.dump(results, f, indent=2)

    if "error" not in results:
        summary = results["summary"]
        print(f"\nResults saved to {args.out}")
        print(f"Overall WER: {summary['overall_wer']:.2%}")
        print(f"Accuracy: {summary['accuracy']:.2%}")
        print(f"Files processed: {summary['files_with_references']}/{summary['total_files']}")
    else:
        print(f"Evaluation failed: {results['error']}")


if __name__ == "__main__":
    main()