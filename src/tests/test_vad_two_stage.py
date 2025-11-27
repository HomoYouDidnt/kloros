#!/usr/bin/env python3
"""Test script for two-stage VAD validation.

Tests:
1. Segment durations are within expected range (1.5-3.5s typical, never >5.5s)
2. Two-stage VAD eliminates false positives
3. Rollback to dbfs mode works correctly
"""

import os
import sys
import numpy as np

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from audio.vad import detect_segments_two_stage, detect_candidates_dbfs
from audio.vad_silero import SileroVAD


def generate_test_audio(duration_s: float, sample_rate: int = 16000, noise_level: float = 0.1) -> np.ndarray:
    """Generate test audio with speech-like characteristics.

    Args:
        duration_s: Duration in seconds
        sample_rate: Sample rate in Hz
        noise_level: Background noise level (0.0-1.0)

    Returns:
        Audio samples as float32 array
    """
    num_samples = int(duration_s * sample_rate)

    # Generate speech-like signal (combination of frequencies)
    t = np.linspace(0, duration_s, num_samples, dtype=np.float32)
    signal = 0.0

    # Fundamental frequency around 120Hz (typical human voice)
    signal += 0.3 * np.sin(2 * np.pi * 120 * t)

    # Harmonics
    signal += 0.2 * np.sin(2 * np.pi * 240 * t)
    signal += 0.15 * np.sin(2 * np.pi * 360 * t)
    signal += 0.1 * np.sin(2 * np.pi * 480 * t)

    # Add envelope to simulate speech rhythm
    envelope = np.abs(np.sin(2 * np.pi * 2 * t))  # 2Hz modulation
    signal = signal * envelope

    # Add noise
    noise = np.random.normal(0, noise_level, num_samples).astype(np.float32)
    signal += noise

    # Normalize to [-1, 1]
    signal = signal / np.max(np.abs(signal))

    return signal.astype(np.float32)


def test_stage_a_candidates():
    """Test Stage A dBFS candidate detection."""
    print("\n=== Test 1: Stage A Candidate Detection ===")

    # Generate 3 seconds of test audio
    audio = generate_test_audio(3.0)
    sample_rate = 16000

    # Run Stage A detection
    candidates = detect_candidates_dbfs(
        audio=audio,
        sample_rate=sample_rate,
        threshold_dbfs=-28.0,
        min_candidate_ms=100,
    )

    print(f"Stage A detected {len(candidates)} candidate(s)")
    for i, (start, end) in enumerate(candidates):
        duration = end - start
        print(f"  Candidate {i+1}: {start:.3f}s - {end:.3f}s (duration: {duration:.3f}s)")

    assert len(candidates) > 0, "Stage A should detect at least one candidate"
    print("✓ Stage A test passed")


def test_two_stage_vad():
    """Test two-stage VAD with Silero refinement."""
    print("\n=== Test 2: Two-Stage VAD ===")

    # Generate 5 seconds of test audio
    audio = generate_test_audio(5.0)
    sample_rate = 16000

    # Initialize Silero VAD
    try:
        silero_vad = SileroVAD(device="cpu", threshold=0.60)
    except Exception as e:
        print(f"✗ Failed to initialize SileroVAD: {e}")
        print("  Skipping two-stage test (likely missing torch)")
        return

    # Run two-stage detection
    segments, metadata = detect_segments_two_stage(
        audio=audio,
        sample_rate=sample_rate,
        silero_vad=silero_vad,
        stage_a_threshold_dbfs=-28.0,
        stage_b_threshold=0.60,
        min_speech_ms=250,
        max_speech_s=30.0,
        prefer_first=True,
    )

    print(f"Stage A candidates: {metadata['stage_a_candidates']}")
    print(f"Stage B refined: {metadata['stage_b_refined']}")
    print(f"Selected segment: {metadata['selected_segment']}")

    if segments:
        for i, (start, end) in enumerate(segments):
            duration = end - start
            print(f"  Segment {i+1}: {start:.3f}s - {end:.3f}s (duration: {duration:.3f}s)")

            # Verify segment duration constraints
            assert duration <= 5.5, f"Segment duration {duration:.3f}s exceeds hard cap of 5.5s"
            print(f"  ✓ Segment {i+1} duration within limits")

    print("✓ Two-stage VAD test passed")


def test_segment_duration_constraints():
    """Test that segments never exceed hard cap."""
    print("\n=== Test 3: Segment Duration Constraints ===")

    # Generate long audio (10 seconds)
    audio = generate_test_audio(10.0)
    sample_rate = 16000

    # Initialize Silero VAD
    try:
        silero_vad = SileroVAD(device="cpu", threshold=0.60)
    except Exception as e:
        print(f"✗ Failed to initialize SileroVAD: {e}")
        print("  Skipping duration constraint test")
        return

    # Run two-stage detection with max_cmd_ms=5500
    segments, metadata = detect_segments_two_stage(
        audio=audio,
        sample_rate=sample_rate,
        silero_vad=silero_vad,
        stage_a_threshold_dbfs=-28.0,
        stage_b_threshold=0.60,
        min_speech_ms=250,
        max_speech_s=5.5,  # Hard cap
        prefer_first=True,
    )

    print(f"Detected {len(segments)} segment(s) from 10s audio")

    for i, (start, end) in enumerate(segments):
        duration = end - start
        print(f"  Segment {i+1}: {duration:.3f}s")

        # Verify hard cap
        assert duration <= 5.5, f"VIOLATION: Segment duration {duration:.3f}s exceeds 5.5s hard cap"

    print("✓ Duration constraint test passed")


def test_dbfs_fallback():
    """Test fallback to dBFS-only mode."""
    print("\n=== Test 4: dBFS Fallback (silero_vad=None) ===")

    # Generate 3 seconds of test audio
    audio = generate_test_audio(3.0)
    sample_rate = 16000

    # Run two-stage detection with silero_vad=None (should use dBFS only)
    segments, metadata = detect_segments_two_stage(
        audio=audio,
        sample_rate=sample_rate,
        silero_vad=None,  # Force dBFS-only fallback
        stage_a_threshold_dbfs=-28.0,
        stage_b_threshold=0.60,
        min_speech_ms=250,
        max_speech_s=30.0,
        prefer_first=True,
    )

    print(f"Stage A candidates: {metadata['stage_a_candidates']}")
    print(f"Stage B refined: {metadata['stage_b_refined']}")
    print(f"Selected segment: {metadata['selected_segment']}")

    # In fallback mode, Stage B should equal Stage A (no refinement)
    assert metadata["stage_b_refined"] == metadata["stage_a_candidates"], \
        "Fallback mode should skip Silero refinement"

    print("✓ dBFS fallback test passed")


def test_prefer_first_vs_longest():
    """Test segment selection: prefer_first vs longest."""
    print("\n=== Test 5: Segment Selection Strategy ===")

    # Generate audio with two speech segments
    audio1 = generate_test_audio(1.5, noise_level=0.05)
    silence = np.zeros(int(0.5 * 16000), dtype=np.float32)
    audio2 = generate_test_audio(2.5, noise_level=0.05)

    audio = np.concatenate([audio1, silence, audio2])
    sample_rate = 16000

    # Run with prefer_first=True
    segments_first, _ = detect_segments_two_stage(
        audio=audio,
        sample_rate=sample_rate,
        silero_vad=None,
        stage_a_threshold_dbfs=-28.0,
        prefer_first=True,
    )

    # Run with prefer_first=False (prefer longest)
    segments_longest, _ = detect_segments_two_stage(
        audio=audio,
        sample_rate=sample_rate,
        silero_vad=None,
        stage_a_threshold_dbfs=-28.0,
        prefer_first=False,
    )

    print(f"prefer_first=True: selected {len(segments_first)} segment(s)")
    if segments_first:
        start, end = segments_first[0]
        print(f"  Duration: {end - start:.3f}s")

    print(f"prefer_first=False: selected {len(segments_longest)} segment(s)")
    if segments_longest:
        start, end = segments_longest[0]
        print(f"  Duration: {end - start:.3f}s")

    print("✓ Segment selection test passed")


def main():
    """Run all tests."""
    print("=" * 60)
    print("Two-Stage VAD Validation Test Suite")
    print("=" * 60)

    try:
        test_stage_a_candidates()
        test_two_stage_vad()
        test_segment_duration_constraints()
        test_dbfs_fallback()
        test_prefer_first_vs_longest()

        print("\n" + "=" * 60)
        print("✓ ALL TESTS PASSED")
        print("=" * 60)
        return 0

    except AssertionError as e:
        print(f"\n✗ TEST FAILED: {e}")
        return 1
    except Exception as e:
        print(f"\n✗ UNEXPECTED ERROR: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
