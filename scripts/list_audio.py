#!/usr/bin/env python3
"""List audio devices and optionally test capture."""

import argparse
import sys
import wave
from pathlib import Path
from typing import Optional

# Add project root to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.audio.capture import create_audio_backend


def list_devices():
    """List available audio input devices."""
    try:
        import sounddevice as sd
    except ImportError:
        print("SoundDevice library not available - cannot list devices")
        return False

    try:
        devices = sd.query_devices()
        default_device = sd.default.device

        print("Available audio input devices:")
        print("=" * 50)

        for i, device in enumerate(devices):
            if device["max_input_channels"] > 0:  # Only show input devices
                default_marker = " (default)" if i == default_device[0] else ""
                print(f"  {i}: {device['name']}{default_marker}")
                print(
                    f"      Channels: {device['max_input_channels']} in, {device['max_output_channels']} out"
                )
                print(f"      Sample rate: {device['default_samplerate']} Hz")
                print()

        return True

    except Exception as e:
        print(f"Error listing devices: {e}")
        return False


def test_capture(duration_secs: int, device_index: Optional[int] = None):
    """Test audio capture for specified duration."""
    try:
        backend = create_audio_backend("sounddevice")
    except RuntimeError as e:
        print(f"Cannot create SoundDevice backend: {e}")
        return False

    sample_rate = 16000
    channels = 1
    block_ms = 30

    # Create output directory
    output_dir = Path.home() / ".kloros" / "in"
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / "capture_test.wav"

    print(f"Testing capture for {duration_secs} seconds...")
    print(f"Device: {device_index if device_index is not None else 'default'}")
    print(f"Sample rate: {sample_rate} Hz")
    print(f"Output: {output_path}")
    print()

    try:
        # Open backend
        backend.open(sample_rate, channels, device_index)

        # Collect audio chunks
        chunks = []
        total_samples = 0
        target_samples = duration_secs * sample_rate

        print("Recording...")
        for chunk in backend.chunks(block_ms):
            chunks.append(chunk)
            total_samples += len(chunk)

            # Show progress
            progress = min(100, int(100 * total_samples / target_samples))
            print(f"\rProgress: {progress}%", end="", flush=True)

            if total_samples >= target_samples:
                break

        print("\nRecording complete!")

        # Combine chunks and save to WAV
        if chunks:
            audio_data = chunks[0]
            for chunk in chunks[1:]:
                audio_data = chunk  # Just use last chunk for simplicity in this test

            # Convert to int16 for WAV
            audio_int16 = (audio_data * 32767).astype("int16")

            # Write WAV file
            with wave.open(str(output_path), "wb") as wf:
                wf.setnchannels(channels)
                wf.setsampwidth(2)  # 16-bit
                wf.setframerate(sample_rate)
                wf.writeframes(audio_int16.tobytes())

            print(f"Saved {len(chunks)} chunks ({total_samples} samples) to {output_path}")

        backend.close()
        return True

    except Exception as e:
        print(f"\nCapture test failed: {e}")
        backend.close()
        return False


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="List audio devices and test capture")
    parser.add_argument(
        "--capture-secs", type=int, help="Test capture for N seconds and save to WAV"
    )
    parser.add_argument("--device", type=int, help="Device index to use for capture test")

    args = parser.parse_args()

    # Always try to list devices first
    if not list_devices():
        print("SoundDevice unavailable - audio capture will use mock backend")
        sys.exit(3)

    # If capture test requested
    if args.capture_secs:
        if args.capture_secs <= 0:
            print("Capture duration must be positive")
            sys.exit(1)

        if not test_capture(args.capture_secs, args.device):
            sys.exit(1)

    print("Audio system check complete!")


if __name__ == "__main__":
    main()
