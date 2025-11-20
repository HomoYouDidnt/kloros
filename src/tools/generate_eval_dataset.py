#!/usr/bin/env python3
"""
Generate ASR Evaluation Dataset

Creates a larger evaluation dataset for D-REAM optimization testing.
Uses TTS (Piper) to generate synthetic audio with known ground truth.
"""

import os
import json
import subprocess
import random
from pathlib import Path

# Sample sentences with varying complexity
SAMPLE_SENTENCES = [
    # Short simple sentences (easy)
    "hello world",
    "how are you",
    "good morning",
    "thank you",
    "goodbye friend",

    # Medium sentences (moderate)
    "the quick brown fox jumps over the lazy dog",
    "machine learning is transforming artificial intelligence",
    "speech recognition accuracy depends on audio quality",
    "natural language processing enables human computer interaction",
    "deep learning models require large amounts of training data",

    # Longer complex sentences (challenging)
    "the revolutionary advancements in neural network architectures have dramatically improved speech recognition accuracy over the past decade",
    "conversational artificial intelligence systems must understand context intent and nuance to provide meaningful responses",
    "automated speech recognition technology has applications ranging from virtual assistants to medical transcription services",
    "optimizing hyperparameters through evolutionary algorithms can discover configurations that human experts might overlook",
    "the intersection of acoustic modeling and language modeling forms the foundation of modern speech recognition systems",

    # Technical/domain-specific
    "kubernetes orchestrates containerized applications across distributed systems",
    "python provides extensive libraries for scientific computing and data analysis",
    "microservice architectures enable independent deployment and scaling of components",
    "continuous integration and deployment pipelines automate software delivery",
    "database normalization reduces redundancy and improves data integrity",

    # With numbers and mixed content
    "there are 365 days in a year and 24 hours in a day",
    "the temperature reached 72 degrees fahrenheit this afternoon",
    "approximately 8 billion people live on earth as of 2024",
    "the meeting is scheduled for 3 pm on tuesday october 15th",
    "my phone number is 555 0123 and my address is 456 oak street",

    # Questions
    "what time does the meeting start tomorrow morning",
    "how do I configure the database connection settings",
    "where can I find the system logs for debugging",
    "why did the application crash during startup",
    "when will the new features be released to production",

    # Commands/instructions
    "please restart the service and check the logs",
    "navigate to the settings menu and update your preferences",
    "download the latest version from the official website",
    "backup your data before proceeding with the upgrade",
    "submit your changes and create a pull request",

    # Conversational
    "I really appreciate your help with this project",
    "that sounds like a great idea let me know when you are ready",
    "I am not sure I understand what you mean could you explain",
    "this has been a productive meeting thank you everyone",
    "let me think about that and get back to you tomorrow",
]

def generate_audio(text: str, output_path: str, model_path: str = "/home/kloros/models/piper/glados_piper_medium.onnx"):
    """Generate audio from text using Piper TTS"""
    cmd = [
        "piper",
        "--model", model_path,
        "--output_file", output_path
    ]

    result = subprocess.run(
        cmd,
        input=text.encode(),
        capture_output=True
    )

    if result.returncode != 0:
        raise Exception(f"Piper TTS failed: {result.stderr.decode()}")

    return True

def generate_vad_annotations(audio_path: str, output_path: str):
    """Generate VAD annotations using Silero VAD"""
    import torch
    import torchaudio

    # Load Silero VAD
    model, utils = torch.hub.load(
        repo_or_dir='snakers4/silero-vad',
        model='silero_vad',
        force_reload=False
    )

    (get_speech_timestamps, _, _, _, _) = utils

    # Load audio
    wav, sample_rate = torchaudio.load(audio_path)

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

def create_evaluation_dataset(
    output_dir: str,
    num_samples: int = 50,
    sentences: list = None
):
    """Create a complete evaluation dataset"""

    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    if sentences is None:
        # Use predefined sentences, cycling if needed
        sentences = SAMPLE_SENTENCES
        if num_samples > len(sentences):
            sentences = sentences * (num_samples // len(sentences) + 1)
        sentences = sentences[:num_samples]

    print(f"Creating evaluation dataset: {num_samples} samples")
    print(f"Output directory: {output_dir}\n")

    successful = 0
    failed = 0

    for i, text in enumerate(sentences, 1):
        sample_name = f"sample{i:03d}"

        try:
            print(f"[{i}/{num_samples}] Generating: {text[:50]}...")

            # Generate audio
            audio_path = output_path / f"{sample_name}.wav"
            generate_audio(text, str(audio_path))

            # Write transcription
            txt_path = output_path / f"{sample_name}.txt"
            with open(txt_path, 'w') as f:
                f.write(text)

            # Generate VAD annotations
            vad_path = output_path / f"{sample_name}.vad.json"
            generate_vad_annotations(str(audio_path), str(vad_path))

            successful += 1

        except Exception as e:
            print(f"  ERROR: {e}")
            failed += 1

    print(f"\n✅ Dataset creation complete!")
    print(f"   Successful: {successful}")
    print(f"   Failed: {failed}")
    print(f"\nDataset ready at: {output_dir}")
    print(f"\nUsage:")
    print(f"  /opt/kloros/tools/stt_bench '{{\"dataset_path\":\"{output_dir}\",\"beam\":3}}'")

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Generate ASR evaluation dataset")
    parser.add_argument("--output", "-o", default="/home/kloros/assets/asr_eval/large_eval_set",
                       help="Output directory for dataset")
    parser.add_argument("--samples", "-n", type=int, default=50,
                       help="Number of samples to generate")
    parser.add_argument("--custom-sentences", type=str,
                       help="Path to file with custom sentences (one per line)")

    args = parser.parse_args()

    sentences = None
    if args.custom_sentences:
        with open(args.custom_sentences) as f:
            sentences = [line.strip() for line in f if line.strip()]

    create_evaluation_dataset(
        output_dir=args.output,
        num_samples=args.samples,
        sentences=sentences
    )
