#!/usr/bin/env python3
"""KLoROS microphone calibration CLI tool."""

import sys
import time
from pathlib import Path

# Add src to path for imports
script_dir = Path(__file__).parent
src_dir = script_dir.parent / "src"
sys.path.insert(0, str(src_dir))

try:
    import numpy as np

    from src.voice.audio.calibration import run_calibration, save_profile
except ImportError as e:
    print(f"Error: Failed to import required modules: {e}")
    print("Make sure you're in the KLoROS project directory and dependencies are installed.")
    sys.exit(1)


class SoundDeviceBackend:
    """Audio backend using sounddevice library."""

    def __init__(self):
        self.stream = None
        self.sample_rate = None
        self.device_name = "default"

    def open(self, sample_rate: int, channels: int) -> None:
        """Open audio input stream."""
        try:
            import sounddevice as sd
        except ImportError as e:
            raise RuntimeError(
                "sounddevice library not available. Install with: pip install sounddevice"
            ) from e

        self.sample_rate = sample_rate

        # Try to get device info
        try:
            _devices = sd.query_devices()
            default_input = sd.default.device[0]
            if default_input is not None:
                device_info = sd.query_devices(default_input, "input")
                if isinstance(device_info, dict):
                    self.device_name = device_info.get("name", "default")
                else:
                    self.device_name = str(device_info)
        except Exception:
            pass  # Keep default name

        print(f"Using audio device: {self.device_name}")
        print(f"Sample rate: {sample_rate} Hz")

    def record(self, seconds: float) -> np.ndarray:
        """Record audio for specified duration."""
        try:
            import sounddevice as sd
        except ImportError as e:
            raise RuntimeError("sounddevice library not available") from e

        print(f"Recording for {seconds:.1f} seconds...")

        # Record audio
        audio = sd.rec(
            int(seconds * self.sample_rate),
            samplerate=self.sample_rate,
            channels=1,
            dtype=np.float32,
        )
        sd.wait()  # Wait for recording to complete

        return audio.flatten()

    def close(self) -> None:
        """Close audio stream."""
        pass  # sounddevice doesn't require explicit close for rec()


def countdown(seconds: int, message: str) -> None:
    """Display a countdown timer."""
    print(f"\n{message}")
    for i in range(seconds, 0, -1):
        print(f"{i}...", end=" ", flush=True)
        time.sleep(1)
    print("GO!\n")


def format_dbfs(value: float) -> str:
    """Format dBFS value for display."""
    return f"{value:+6.1f} dBFS"


def main() -> int:
    """Main CLI entry point."""
    print("KLoROS Microphone Calibration Tool")
    print("=" * 40)

    # Check for audio backend
    try:
        backend = SoundDeviceBackend()
    except RuntimeError as e:
        print(f"Error: {e}")
        print("\nAudio backend not available. Please install sounddevice:")
        print("  pip install sounddevice")
        return 1

    print("\nThis tool will measure your microphone's noise floor and speech levels")
    print("to optimize voice detection and audio gain settings.\n")

    print("Instructions:")
    print("1. First, we'll record silence to measure background noise")
    print("2. Then, we'll record you speaking to measure speech levels")
    print("3. Finally, we'll save the calibration profile")

    input("\nPress Enter when ready to start...")

    try:
        # Step 1: Record silence
        countdown(3, "Get ready for silence measurement...")
        print("Stay quiet during this recording.")

        # Step 2: Record speech
        countdown(3, "Get ready for speech measurement...")
        print("Please read aloud or speak normally during this recording.")
        print("You can read anything - count numbers, recite the alphabet, etc.")

        # Run calibration
        print("\nRunning calibration...")
        profile = run_calibration(backend)

        # Display results
        print("\n" + "=" * 50)
        print("CALIBRATION RESULTS")
        print("=" * 50)

        print(f"Device: {profile.device.get('name', 'unknown')}")
        print(f"Sample Rate: {profile.device.get('sample_rate', 'unknown')} Hz")
        print()

        print("Measured Levels:")
        print(f"  Noise Floor:    {format_dbfs(profile.noise_floor_dbfs)}")
        print(f"  Speech RMS:     {format_dbfs(profile.speech_rms_dbfs)}")
        print(f"  SNR:            {profile.speech_rms_dbfs - profile.noise_floor_dbfs:+6.1f} dB")
        print()

        print("Computed Settings:")
        print(f"  VAD Threshold:  {format_dbfs(profile.vad_threshold_dbfs)}")
        print(f"  AGC Gain:       {profile.agc_gain_db:+6.1f} dB")
        print(f"  Spectral Tilt:  {profile.spectral_tilt:.2f}")
        print(f"  Recommended Wake Confidence: {profile.recommended_wake_conf_min:.2f}")
        print()

        # Save profile
        saved_path = save_profile(profile)
        print(f"Profile saved to: {saved_path}")

        print("\nCalibration complete! KLoROS will automatically use these settings.")

        return 0

    except KeyboardInterrupt:
        print("\n\nCalibration cancelled by user.")
        return 1
    except Exception as e:
        print(f"\nError during calibration: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
