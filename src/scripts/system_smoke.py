#!/usr/bin/env python3
"""CLI wrapper for KLoROS system smoke harness."""

import argparse
import sys
from pathlib import Path

# Add project root to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.tools.system_smoke import run_smoke


def main():
    """CLI entry point for system smoke testing."""
    parser = argparse.ArgumentParser(
        description="KLoROS system smoke harness - end-to-end pipeline testing"
    )
    parser.add_argument(
        "--wav", type=str, help="Input WAV file path (generates synthetic if not provided)"
    )
    parser.add_argument("--stt", type=str, default="mock", help="STT backend name (default: mock)")
    parser.add_argument("--tts", type=str, default="mock", help="TTS backend name (default: mock)")
    parser.add_argument(
        "--reason", type=str, default="mock", help="Reasoning backend name (default: mock)"
    )
    parser.add_argument("--sr", type=int, default=16000, help="Sample rate in Hz (default: 16000)")
    parser.add_argument(
        "--out", type=str, default="tts_smoke.wav", help="Output filename (default: tts_smoke.wav)"
    )

    args = parser.parse_args()

    # Run smoke test
    result = run_smoke(
        sample_rate=args.sr,
        wav_in=args.wav,
        stt_backend=args.stt,
        tts_backend=args.tts,
        reason_backend=args.reason,
        out_basename=args.out,
    )

    # Print one-line summary
    if result.ok:
        print(
            f'OK transcript="{result.transcript}" reply="{result.reply_text}" out="{result.tts_path}"'
        )
        sys.exit(0)
    else:
        print(
            f'FAIL reason="{result.reason}" transcript="{result.transcript}" reply="{result.reply_text}"'
        )

        # Map failure reasons to exit codes
        if result.reason == "no_voice":
            sys.exit(2)
        elif "adapter_init_failure" in result.reason:
            sys.exit(3)
        else:
            sys.exit(1)


if __name__ == "__main__":
    main()
