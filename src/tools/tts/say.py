#!/usr/bin/env python3
"""
TTS Synthesis Tool

Synthesize text to speech using specified TTS backend.
Used for generating test audio samples.

Usage:
    python3 say.py --backend piper --text "Hello world" --out output.wav
"""

import argparse
import subprocess
import os
from pathlib import Path


def synthesize_piper(text, output_file, model_path=None):
    """Synthesize speech using Piper TTS."""
    if not model_path:
        # Try default KLoROS model path
        default_model = "/home/kloros/kloros_models/piper/glados_piper_medium.onnx"
        if os.path.exists(default_model):
            model_path = default_model
        else:
            raise FileNotFoundError("No Piper model specified and default not found")

    try:
        # Use echo to pipe text to piper
        cmd = f'echo "{text}" | piper --model "{model_path}" --output_file "{output_file}"'
        result = subprocess.run(cmd, shell=True, check=True, capture_output=True, text=True)
        return True

    except subprocess.CalledProcessError as e:
        print(f"Piper TTS failed: {e}")
        print(f"Stderr: {e.stderr}")
        return False


def synthesize_espeak(text, output_file, voice="en"):
    """Synthesize speech using eSpeak."""
    try:
        cmd = [
            "espeak",
            "-w", output_file,
            "-v", voice,
            text
        ]
        subprocess.run(cmd, check=True, capture_output=True)
        return True

    except subprocess.CalledProcessError as e:
        print(f"eSpeak TTS failed: {e}")
        return False


def synthesize_festival(text, output_file):
    """Synthesize speech using Festival."""
    try:
        # Create temporary text file
        import tempfile
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
            f.write(text)
            temp_text_file = f.name

        try:
            cmd = f'echo "({temp_text_file}) to speech | save_sound \"{output_file}\"" | festival'
            subprocess.run(cmd, shell=True, check=True, capture_output=True)
            return True

        finally:
            os.unlink(temp_text_file)

    except subprocess.CalledProcessError as e:
        print(f"Festival TTS failed: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(description="Synthesize text to speech")
    parser.add_argument("--backend", default="piper", choices=["piper", "espeak", "festival"],
                        help="TTS backend to use")
    parser.add_argument("--text", required=True, help="Text to synthesize")
    parser.add_argument("--out", required=True, help="Output audio file")
    parser.add_argument("--model", help="Path to TTS model (for Piper)")
    parser.add_argument("--voice", default="en", help="Voice to use (for eSpeak)")

    args = parser.parse_args()

    # Create output directory if needed
    output_path = Path(args.out)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    print(f"Synthesizing with {args.backend}: '{args.text}'")

    success = False

    if args.backend == "piper":
        success = synthesize_piper(args.text, args.out, args.model)
    elif args.backend == "espeak":
        success = synthesize_espeak(args.text, args.out, args.voice)
    elif args.backend == "festival":
        success = synthesize_festival(args.text, args.out)

    if success:
        print(f"Audio saved to: {args.out}")

        # Check output file
        if os.path.exists(args.out):
            file_size = os.path.getsize(args.out)
            print(f"File size: {file_size} bytes")

            # Try to get audio info if sox is available
            try:
                cmd = ["soxi", args.out]
                result = subprocess.run(cmd, capture_output=True, text=True)
                if result.returncode == 0:
                    print("Audio info:")
                    print(result.stdout)
            except FileNotFoundError:
                pass  # sox not available
        else:
            print("Warning: Output file was not created")
            success = False

    else:
        print(f"TTS synthesis failed with {args.backend}")

    return 0 if success else 1


if __name__ == "__main__":
    exit(main())