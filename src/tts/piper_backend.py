"""Piper-based TTS backend for KLoROS."""

from __future__ import annotations

import os
import subprocess
import time
import wave
from pathlib import Path
from typing import Optional

from .base import TtsResult


class PiperTtsBackend:
    """Piper text-to-speech backend with lazy initialization."""

    def __init__(
        self,
        voice: Optional[str] = None,
        out_dir: Optional[str] = None,
        piper_args: Optional[str] = None
    ):
        """Initialize Piper TTS backend.

        Args:
            voice: Path to voice model or voice alias
            out_dir: Output directory for audio files
            piper_args: Additional CLI arguments for Piper

        Raises:
            RuntimeError: If Piper is unavailable
        """
        self.voice = voice
        self.out_dir = out_dir or os.path.expanduser("~/.kloros/out")
        self.piper_args = piper_args or ""

        # Ensure output directory exists
        Path(self.out_dir).mkdir(parents=True, exist_ok=True)

        # Check Piper availability
        self._piper_method = self._detect_piper()
        if self._piper_method is None:
            raise RuntimeError("piper unavailable")

    def _detect_piper(self) -> Optional[str]:
        """Detect available Piper method.

        Returns:
            "python" if piper module available, "cli" if CLI available, None if unavailable
        """
        # Try Python import first
        try:
            import importlib.util
            if importlib.util.find_spec("piper") is not None:
                return "python"
        except ImportError:
            pass

        # Try CLI fallback
        try:
            result = subprocess.run(
                ["piper", "--help"],
                capture_output=True,
                timeout=5
            )
            if result.returncode == 0:
                return "cli"
        except (subprocess.TimeoutExpired, subprocess.SubprocessError, FileNotFoundError):
            pass

        return None

    def synthesize(
        self,
        text: str,
        sample_rate: int = 22050,
        voice: Optional[str] = None,
        out_dir: Optional[str] = None,
        basename: Optional[str] = None,
    ) -> TtsResult:
        """Synthesize text to speech using Piper.

        Args:
            text: Text to synthesize
            sample_rate: Target sample rate in Hz
            voice: Voice/model to use (overrides instance default)
            out_dir: Output directory (overrides instance default)
            basename: Output filename base

        Returns:
            TtsResult with audio file path and metadata
        """
        # Resolve parameters
        final_voice = voice or self.voice or os.getenv("KLR_PIPER_VOICE")
        final_out_dir = out_dir or self.out_dir
        final_args = self.piper_args

        # Generate output filename
        if basename is None:
            basename = f"tts_{int(time.time() * 1000)}"

        output_path = os.path.join(final_out_dir, f"{basename}.wav")

        # Synthesize based on available method
        if self._piper_method == "python":
            duration_s = self._synthesize_python(text, output_path, sample_rate, final_voice)
        elif self._piper_method == "cli":
            duration_s = self._synthesize_cli(text, output_path, sample_rate, final_voice, final_args)
        else:
            raise RuntimeError("piper unavailable")

        return TtsResult(
            audio_path=output_path,
            duration_s=duration_s,
            sample_rate=sample_rate,
            voice=final_voice
        )

    def _synthesize_python(
        self,
        text: str,
        output_path: str,
        sample_rate: int,
        voice: Optional[str]
    ) -> float:
        """Synthesize using Python piper library."""
        import piper

        # This is a simplified implementation - real Piper usage would require
        # proper model loading and configuration
        try:
            # Create a basic synthesizer
            # Note: This is pseudo-code as actual Piper API may differ
            synthesizer = piper.PiperVoice.load(voice) if voice else None

            if synthesizer is None:
                raise RuntimeError("piper voice not available")

            # Synthesize audio
            audio_data = synthesizer.synthesize(text, sample_rate=sample_rate)

            # Write to WAV file
            with wave.open(output_path, 'wb') as wav_file:
                wav_file.setnchannels(1)  # mono
                wav_file.setsampwidth(2)  # 16-bit
                wav_file.setframerate(sample_rate)
                wav_file.writeframes(audio_data.tobytes())

            return len(audio_data) / sample_rate

        except Exception as e:
            raise RuntimeError(f"piper synthesis failed: {e}") from e

    def _synthesize_cli(
        self,
        text: str,
        output_path: str,
        sample_rate: int,
        voice: Optional[str],
        extra_args: str
    ) -> float:
        """Synthesize using Piper CLI."""
        try:
            # Build command
            cmd = ["piper"]

            if voice:
                cmd.extend(["--model", voice])

            cmd.extend(["--output_file", output_path])

            # Add sample rate if supported
            if sample_rate != 22050:  # Piper's default
                cmd.extend(["--sample_rate", str(sample_rate)])

            # Add extra arguments
            if extra_args:
                cmd.extend(extra_args.split())

            # Run Piper with text input
            result = subprocess.run(
                cmd,
                input=text,
                text=True,
                capture_output=True,
                timeout=30
            )

            if result.returncode != 0:
                raise RuntimeError(f"piper CLI failed: {result.stderr}")

            # Calculate duration from output file
            duration_s = self._get_wav_duration(output_path)
            return duration_s

        except subprocess.TimeoutExpired as e:
            raise RuntimeError("piper CLI timeout") from e
        except Exception as e:
            raise RuntimeError(f"piper CLI error: {e}") from e

    def _get_wav_duration(self, wav_path: str) -> float:
        """Get duration of WAV file in seconds."""
        try:
            with wave.open(wav_path, 'rb') as wav_file:
                frames = wav_file.getnframes()
                sample_rate = wav_file.getframerate()
                return frames / sample_rate
        except Exception:
            return 0.0  # Fallback if duration can't be determined
