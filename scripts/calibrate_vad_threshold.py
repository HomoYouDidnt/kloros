#!/usr/bin/env python3
"""VAD Threshold Calibration Tool - Find optimal audio levels for your setup."""

import sys
import os
import time
import numpy as np
import sounddevice as sd
from pathlib import Path

# Add KLoROS to path
sys.path.insert(0, '/home/kloros')

def load_env():
    """Load environment variables from .kloros_env"""
    env_file = Path('/home/kloros/.kloros_env')
    if env_file.exists():
        with open(env_file) as f:
            for line in f:
                if '=' in line and not line.strip().startswith('#'):
                    key, value = line.strip().split('=', 1)
                    os.environ[key] = value

def rms_to_dbfs(rms):
    """Convert RMS amplitude to dBFS."""
    if rms == 0:
        return -120.0
    return 20 * np.log10(rms)

def analyze_audio(audio_data):
    """Analyze audio and return statistics."""
    rms = np.sqrt(np.mean(audio_data**2))
    peak = np.max(np.abs(audio_data))
    dbfs_rms = rms_to_dbfs(rms)
    dbfs_peak = rms_to_dbfs(peak)

    return {
        'rms': rms,
        'peak': peak,
        'dbfs_rms': dbfs_rms,
        'dbfs_peak': dbfs_peak,
        'clipping': peak >= 0.99
    }

def record_sample(device_index, sample_rate, duration, input_gain):
    """Record a single audio sample."""
    print(f"  Recording {duration}s... ", end='', flush=True)

    try:
        recording = sd.rec(
            int(duration * sample_rate),
            samplerate=sample_rate,
            channels=1,
            dtype='float32',
            device=device_index
        )
        sd.wait()

        # Apply input gain
        recording = recording.flatten() * input_gain

        print("✓")
        return recording
    except Exception as e:
        print(f"✗ Error: {e}")
        return None

def main():
    print("\n" + "="*70)
    print("KLoROS VAD Threshold Calibration Tool")
    print("="*70)
    print("\nThis tool will help you find optimal audio settings for your setup.")
    print("You'll speak at different distances and we'll measure audio levels.\n")

    # Load environment
    load_env()

    # Get current settings
    device_index = int(os.getenv('KLR_INPUT_IDX', '11'))
    sample_rate = int(os.getenv('KLR_CAPTURE_RATE', '48000'))
    current_gain = float(os.getenv('KLR_INPUT_GAIN', '4.0'))
    current_threshold = float(os.getenv('KLR_VAD_THRESHOLD_DBFS', '-42.0'))

    print(f"Current Settings:")
    print(f"  Device Index: {device_index}")
    print(f"  Sample Rate: {sample_rate} Hz")
    print(f"  Input Gain: {current_gain}x")
    print(f"  VAD Threshold: {current_threshold} dBFS")
    print()

    # Test different scenarios
    scenarios = [
        {
            'name': 'Normal Speaking Distance',
            'description': 'Speak at your typical distance (probably 1-2 feet)',
            'samples': 3
        },
        {
            'name': 'Quiet Speaking',
            'description': 'Speak quietly at normal distance',
            'samples': 2
        },
        {
            'name': 'Loud Speaking',
            'description': 'Speak louder at normal distance',
            'samples': 2
        }
    ]

    all_results = []

    for scenario in scenarios:
        print("-" * 70)
        print(f"\n{scenario['name']}")
        print(f"Instructions: {scenario['description']}")
        print(f"You'll record {scenario['samples']} samples. Say anything for 3 seconds.\n")

        input("Press ENTER when ready to start...")

        scenario_results = []
        for i in range(scenario['samples']):
            print(f"\nSample {i+1}/{scenario['samples']}:")
            time.sleep(1)  # Brief pause

            audio = record_sample(device_index, sample_rate, 3.0, current_gain)
            if audio is not None:
                stats = analyze_audio(audio)
                scenario_results.append(stats)

                print(f"  RMS: {stats['rms']:.4f} ({stats['dbfs_rms']:.1f} dBFS)")
                print(f"  Peak: {stats['peak']:.4f} ({stats['dbfs_peak']:.1f} dBFS)")
                if stats['clipping']:
                    print(f"  ⚠️  CLIPPING DETECTED - Audio too loud!")

        all_results.extend(scenario_results)

        # Scenario summary
        if scenario_results:
            avg_dbfs = np.mean([s['dbfs_rms'] for s in scenario_results])
            peak_dbfs = np.max([s['dbfs_peak'] for s in scenario_results])
            print(f"\n{scenario['name']} Summary:")
            print(f"  Average: {avg_dbfs:.1f} dBFS")
            print(f"  Peak: {peak_dbfs:.1f} dBFS")

    # Overall analysis
    print("\n" + "="*70)
    print("CALIBRATION RESULTS")
    print("="*70)

    if not all_results:
        print("No valid samples recorded. Please try again.")
        return

    # Calculate statistics
    normal_samples = all_results[:scenarios[0]['samples']]
    quiet_samples = all_results[scenarios[0]['samples']:scenarios[0]['samples']+scenarios[1]['samples']]

    normal_avg = np.mean([s['dbfs_rms'] for s in normal_samples])
    normal_peak = np.max([s['dbfs_peak'] for s in normal_samples])
    quiet_avg = np.mean([s['dbfs_rms'] for s in quiet_samples]) if quiet_samples else normal_avg - 10

    clipping_detected = any(s['clipping'] for s in all_results)

    print(f"\nMeasured Levels:")
    print(f"  Normal speaking: {normal_avg:.1f} dBFS (peak: {normal_peak:.1f} dBFS)")
    print(f"  Quiet speaking: {quiet_avg:.1f} dBFS")

    # Generate recommendations
    print("\n" + "-"*70)
    print("RECOMMENDATIONS:")
    print("-"*70)

    # Input gain recommendation
    if clipping_detected:
        recommended_gain = current_gain * 0.6
        print(f"\n⚠️  CLIPPING DETECTED")
        print(f"  Current gain ({current_gain}x) is too high.")
        print(f"  Recommended: KLR_INPUT_GAIN={recommended_gain:.1f}")
    elif normal_peak < -20:
        recommended_gain = current_gain * 1.5
        print(f"\n📊 Audio levels are low")
        print(f"  Current gain: {current_gain}x")
        print(f"  Recommended: KLR_INPUT_GAIN={recommended_gain:.1f}")
    else:
        recommended_gain = current_gain
        print(f"\n✓ Input gain is appropriate: {current_gain}x")

    # VAD threshold recommendation
    # Set threshold 8-10 dB below quiet speaking level for good detection
    recommended_threshold = quiet_avg - 8

    print(f"\n📊 VAD Threshold Recommendation:")
    print(f"  Your quiet speaking: {quiet_avg:.1f} dBFS")
    print(f"  Recommended threshold: {recommended_threshold:.1f} dBFS")
    print(f"  (This allows detection of quiet speech with margin)")

    # Threshold sanity checks
    if recommended_threshold > -30:
        print(f"  ⚠️  Warning: Threshold very high, may trigger on background noise")
    if recommended_threshold < -60:
        print(f"  ⚠️  Warning: Threshold very low, may miss quiet speech")

    # Target levels explanation
    print(f"\n📋 Target Levels (with recommended gain):")
    adjusted_normal = normal_avg + (20 * np.log10(recommended_gain / current_gain))
    adjusted_peak = normal_peak + (20 * np.log10(recommended_gain / current_gain))
    print(f"  Normal speaking: ~{adjusted_normal:.1f} dBFS")
    print(f"  Peak: ~{adjusted_peak:.1f} dBFS")
    print(f"  Target range: -25 to -15 dBFS for optimal STT")

    # Summary of changes
    print(f"\n" + "="*70)
    print("SUGGESTED .kloros_env CHANGES:")
    print("="*70)

    changes = []
    if abs(recommended_gain - current_gain) > 0.2:
        changes.append(f"KLR_INPUT_GAIN={recommended_gain:.1f}")
    if abs(recommended_threshold - current_threshold) > 2:
        changes.append(f"KLR_VAD_THRESHOLD_DBFS={recommended_threshold:.1f}")

    if changes:
        print()
        for change in changes:
            print(f"  {change}")
        print()

        apply = input("Apply these changes to .kloros_env? (yes/no): ").strip().lower()
        if apply == 'yes':
            env_file = Path('/home/kloros/.kloros_env')
            content = env_file.read_text()

            for change in changes:
                key, value = change.split('=')
                # Replace existing line or add new one
                lines = content.split('\n')
                found = False
                for i, line in enumerate(lines):
                    if line.startswith(f"{key}="):
                        lines[i] = change
                        found = True
                        break
                if not found:
                    # Add after related settings
                    for i, line in enumerate(lines):
                        if 'KLR_INPUT_GAIN' in line or 'KLR_VAD' in line:
                            lines.insert(i+1, change)
                            break
                content = '\n'.join(lines)

            env_file.write_text(content)
            print("\n✓ Changes applied to .kloros_env")
            print("  Restart KLoROS service for changes to take effect:")
            print("  sudo systemctl restart kloros.service")
        else:
            print("\nChanges not applied. You can manually update .kloros_env")
    else:
        print("\n✓ Current settings are already optimal!")

    print()

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\nCalibration cancelled.")
    except Exception as e:
        print(f"\nError: {e}")
        import traceback
        traceback.print_exc()
