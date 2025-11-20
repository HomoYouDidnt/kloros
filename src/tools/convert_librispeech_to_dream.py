#!/usr/bin/env python3
"""
Convert LibriSpeech to D-REAM Evaluation Format

Takes LibriSpeech test-clean and converts to D-REAM format:
- FLAC → 16kHz mono WAV
- Normalized transcriptions
- Real Silero VAD annotations
"""

import json
import subprocess
import os
import re
from pathlib import Path
from typing import List, Dict
import random


def normalize_text(text: str) -> str:
    """Normalize transcription for WER calculation"""
    text = text.lower()
    text = re.sub(r'[^\w\s]', '', text)
    text = ' '.join(text.split())
    return text


def convert_audio(input_path: str, output_path: str) -> bool:
    """Convert FLAC to 16kHz mono WAV"""
    cmd = [
        'ffmpeg',
        '-i', input_path,
        '-ar', '16000',
        '-ac', '1',
        '-y',
        output_path
    ]

    result = subprocess.run(cmd, capture_output=True)
    return result.returncode == 0


def generate_vad_annotations(audio_path: str, output_path: str) -> bool:
    """Generate VAD annotations using Silero VAD"""
    try:
        import torch
        import soundfile as sf

        # Load Silero VAD
        model, utils = torch.hub.load(
            repo_or_dir='snakers4/silero-vad',
            model='silero_vad',
            force_reload=False
        )

        (get_speech_timestamps, _, _, _, _) = utils

        # Load audio
        audio_data, sample_rate = sf.read(audio_path)

        # Convert to torch tensor
        wav = torch.from_numpy(audio_data).float()
        if len(wav.shape) == 1:
            wav = wav.unsqueeze(0)

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


def collect_librispeech_entries(librispeech_dir: Path) -> List[Dict]:
    """Collect all LibriSpeech utterances with paths and transcriptions"""
    entries = []

    # Find all transcription files
    trans_files = list(librispeech_dir.rglob("*.trans.txt"))

    for trans_file in trans_files:
        with open(trans_file) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue

                # Parse: UTTERANCE_ID TRANSCRIPTION
                parts = line.split(maxsplit=1)
                if len(parts) != 2:
                    continue

                utterance_id, text = parts

                # Find corresponding FLAC file
                flac_file = trans_file.parent / f"{utterance_id}.flac"

                if flac_file.exists():
                    entries.append({
                        'id': utterance_id,
                        'flac_path': str(flac_file),
                        'text': text
                    })

    return entries


def convert_librispeech_dataset(
    librispeech_dir: str,
    output_dir: str,
    num_samples: int = 200
):
    """Convert LibriSpeech to D-REAM format"""

    print(f"Converting LibriSpeech to D-REAM evaluation format")
    print(f"Source: {librispeech_dir}")
    print(f"Output: {output_dir}")
    print(f"Target samples: {num_samples}\n")

    # Collect all entries
    print("Collecting LibriSpeech entries...")
    librispeech_path = Path(librispeech_dir)
    entries = collect_librispeech_entries(librispeech_path)
    print(f"Found {len(entries)} total utterances")

    # Random sample
    if len(entries) > num_samples:
        entries = random.sample(entries, num_samples)

    print(f"Selected {len(entries)} samples for conversion\n")

    # Create output directory
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    # Convert each sample
    successful = 0
    failed = 0

    for i, entry in enumerate(entries, 1):
        sample_name = f"sample{i:03d}"

        try:
            print(f"[{i}/{len(entries)}] Converting: {entry['text'][:60]}...")

            # Convert FLAC to WAV
            audio_out = output_path / f"{sample_name}.wav"
            if not convert_audio(entry['flac_path'], str(audio_out)):
                raise Exception("Audio conversion failed")

            # Write normalized transcription
            txt_out = output_path / f"{sample_name}.txt"
            normalized_text = normalize_text(entry['text'])
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

    # Write manifest
    manifest_path = output_path / "manifest.json"
    manifest = {
        "source": "LibriSpeech test-clean",
        "total_samples": successful,
        "format": "D-REAM evaluation dataset",
        "sample_rate": 16000,
        "channels": 1,
        "attribution": "LibriSpeech ASR corpus (www.openslr.org/12)"
    }
    with open(manifest_path, 'w') as f:
        json.dump(manifest, f, indent=2)

    print(f"Manifest written to: {manifest_path}")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Convert LibriSpeech to D-REAM evaluation format"
    )
    parser.add_argument(
        "--librispeech-dir",
        default="/home/kloros/assets/asr_eval/LibriSpeech/test-clean",
        help="Path to LibriSpeech test-clean directory"
    )
    parser.add_argument(
        "--output",
        "-o",
        default="/home/kloros/assets/asr_eval/librispeech_eval_set",
        help="Output directory for D-REAM evaluation dataset"
    )
    parser.add_argument(
        "--samples",
        "-n",
        type=int,
        default=200,
        help="Number of samples to convert (default: 200)"
    )

    args = parser.parse_args()

    convert_librispeech_dataset(
        librispeech_dir=args.librispeech_dir,
        output_dir=args.output,
        num_samples=args.samples
    )
