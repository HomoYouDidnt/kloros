#!/usr/bin/env python3
"""
Convert GLaDOS Voice Files to D-REAM Evaluation Dataset

Takes the GLaDOS Portal voice files with metadata.json and converts them
to the D-REAM evaluation format (.wav, .txt, .vad.json).
"""

import json
import subprocess
import os
import re
from pathlib import Path
from typing import List, Dict


def load_metadata(metadata_path: str) -> List[Dict]:
    """Load metadata.json and return entries"""
    with open(metadata_path) as f:
        return json.load(f)


def normalize_text(text: str) -> str:
    """
    Normalize transcription for WER calculation
    - Lowercase
    - Remove punctuation
    - Remove extra whitespace
    """
    # Lowercase
    text = text.lower()

    # Remove punctuation
    text = re.sub(r'[^\w\s]', '', text)

    # Normalize whitespace
    text = ' '.join(text.split())

    return text


def convert_audio(input_path: str, output_path: str) -> bool:
    """
    Convert audio to 16kHz mono WAV format
    Returns True on success
    """
    cmd = [
        'ffmpeg',
        '-i', input_path,
        '-ar', '16000',  # 16kHz sample rate
        '-ac', '1',       # Mono
        '-y',             # Overwrite
        output_path
    ]

    result = subprocess.run(
        cmd,
        capture_output=True
    )

    return result.returncode == 0


def generate_vad_annotations(audio_path: str, output_path: str) -> bool:
    """
    Generate VAD annotations using Silero VAD
    Returns True on success
    """
    try:
        import torch
        import soundfile as sf
        import numpy as np

        # Load Silero VAD
        model, utils = torch.hub.load(
            repo_or_dir='snakers4/silero-vad',
            model='silero_vad',
            force_reload=False
        )

        (get_speech_timestamps, _, _, _, _) = utils

        # Load audio using soundfile
        audio_data, sample_rate = sf.read(audio_path)

        # Convert to torch tensor and ensure correct shape
        wav = torch.from_numpy(audio_data).float()
        if len(wav.shape) == 1:
            wav = wav.unsqueeze(0)  # Add batch dimension

        # Get speech timestamps
        speech_timestamps = get_speech_timestamps(
            wav,
            model,
            sampling_rate=sample_rate,
            threshold=0.5,
            min_silence_duration_ms=100
        )

        # Convert to milliseconds
        segments_ms = [
            {
                "start": int(seg['start'] / sample_rate * 1000),
                "end": int(seg['end'] / sample_rate * 1000)
            }
            for seg in speech_timestamps
        ]

        # Write VAD JSON
        vad_data = {
            "sample_rate": sample_rate,
            "segments_ms": segments_ms
        }

        with open(output_path, 'w') as f:
            json.dump(vad_data, f, indent=2)

        return True

    except Exception as e:
        print(f"  VAD generation failed: {e}")
        return False


def get_audio_duration(audio_path: str) -> float:
    """Get audio duration in seconds using ffprobe"""
    try:
        cmd = [
            'ffprobe',
            '-v', 'error',
            '-show_entries', 'format=duration',
            '-of', 'default=noprint_wrappers=1:nokey=1',
            audio_path
        ]

        result = subprocess.run(cmd, capture_output=True, text=True)
        return float(result.stdout.strip())
    except:
        return 0.0


def select_diverse_samples(metadata: List[Dict], count: int = 100) -> List[Dict]:
    """
    Select diverse samples from metadata ensuring quality variation
    - Filter by duration (1-10 seconds ideal)
    - Ensure mix of clean (studio) and degraded (PotatOS) samples
    - Stratified sampling across sections
    """
    import random

    # First pass: get durations and filter
    valid_entries = []
    potato_entries = []

    for entry in metadata:
        file_path = entry['file']
        if not os.path.exists(file_path):
            continue

        duration = get_audio_duration(file_path)
        if 1.0 <= duration <= 10.0:  # 1-10 second range
            entry['_duration'] = duration
            # Separate PotatOS (degraded quality) from clean samples
            if 'potato' in entry.get('filename', '').lower():
                potato_entries.append(entry)
            else:
                valid_entries.append(entry)

    print(f"Filtered to {len(valid_entries)} clean entries + {len(potato_entries)} PotatOS entries")

    # Reserve 30% for PotatOS samples to ensure quality variation
    potato_count = min(len(potato_entries), int(count * 0.3))
    clean_count = count - potato_count

    print(f"Selecting {clean_count} clean + {potato_count} PotatOS samples")

    # Select PotatOS samples (degraded quality)
    random.shuffle(potato_entries)
    selected = potato_entries[:potato_count]

    # Group clean samples by section for stratified sampling
    by_section = {}
    for entry in valid_entries:
        section = entry.get('section', 'Unknown')
        if section not in by_section:
            by_section[section] = []
        by_section[section].append(entry)

    print(f"Found {len(by_section)} unique sections (clean samples)")

    # Stratified random sampling from clean samples
    total_clean = len(valid_entries)

    for section, entries in by_section.items():
        # Calculate proportional sample size for this section
        proportion = len(entries) / total_clean
        section_count = max(1, int(clean_count * proportion))

        # Randomly sample from this section
        random.shuffle(entries)
        selected.extend(entries[:section_count])

    # Trim to exact count if over
    if len(selected) > count:
        random.shuffle(selected)
        selected = selected[:count]

    # Fill from clean samples if under
    elif len(selected) < count:
        remaining = [e for e in valid_entries if e not in selected]
        random.shuffle(remaining)
        selected.extend(remaining[:count - len(selected)])

    # Final shuffle
    random.shuffle(selected)

    return selected


def convert_dataset(
    metadata_path: str,
    output_dir: str,
    num_samples: int = 100
):
    """
    Convert GLaDOS dataset to D-REAM evaluation format
    """

    print(f"Converting GLaDOS voice files to D-REAM evaluation format")
    print(f"Output directory: {output_dir}")
    print(f"Target samples: {num_samples}\n")

    # Load metadata
    print("Loading metadata...")
    metadata = load_metadata(metadata_path)
    print(f"Loaded {len(metadata)} entries from metadata.json")

    # Select diverse samples
    print("\nSelecting diverse samples...")
    selected = select_diverse_samples(metadata, num_samples)
    print(f"Selected {len(selected)} samples for conversion")

    # Create output directory
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    # Convert each sample
    successful = 0
    failed = 0

    for i, entry in enumerate(selected, 1):
        sample_name = f"sample{i:03d}"
        source_file = entry['file']
        text = entry['text']

        try:
            print(f"[{i}/{len(selected)}] Converting: {text[:60]}...")

            # Convert audio to 16kHz mono
            audio_out = output_path / f"{sample_name}.wav"
            if not convert_audio(source_file, str(audio_out)):
                raise Exception("Audio conversion failed")

            # Write normalized transcription
            txt_out = output_path / f"{sample_name}.txt"
            normalized_text = normalize_text(text)
            with open(txt_out, 'w') as f:
                f.write(normalized_text)

            # Generate VAD annotations
            vad_out = output_path / f"{sample_name}.vad.json"
            if not generate_vad_annotations(str(audio_out), str(vad_out)):
                raise Exception("VAD generation failed")

            successful += 1

        except Exception as e:
            print(f"  ERROR: {e}")
            failed += 1

    print(f"\n✅ Conversion complete!")
    print(f"   Successful: {successful}")
    print(f"   Failed: {failed}")
    print(f"\nDataset ready at: {output_dir}")
    print(f"\nUsage:")
    print(f"  /opt/kloros/tools/stt_bench '{{\"dataset_path\":\"{output_dir}\",\"beam\":3}}'")

    # Write a manifest file
    manifest_path = output_path / "manifest.json"
    manifest = {
        "source": "GLaDOS Portal voice lines",
        "total_samples": successful,
        "format": "D-REAM evaluation dataset",
        "sample_rate": 16000,
        "channels": 1,
        "attribution": "Portal Wiki (CC BY 4.0)"
    }
    with open(manifest_path, 'w') as f:
        json.dump(manifest, f, indent=2)

    print(f"Manifest written to: {manifest_path}")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Convert GLaDOS voice files to D-REAM evaluation format"
    )
    parser.add_argument(
        "--metadata",
        default="/home/kloros/voice_files/samples/metadata.json",
        help="Path to metadata.json"
    )
    parser.add_argument(
        "--output",
        "-o",
        default="/home/kloros/assets/asr_eval/glados_eval_set",
        help="Output directory for D-REAM evaluation dataset"
    )
    parser.add_argument(
        "--samples",
        "-n",
        type=int,
        default=100,
        help="Number of samples to convert (default: 100)"
    )

    args = parser.parse_args()

    convert_dataset(
        metadata_path=args.metadata,
        output_dir=args.output,
        num_samples=args.samples
    )
