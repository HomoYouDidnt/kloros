#!/usr/bin/env python3
"""Test audio capture and quality - USER RUNS THIS (REQUIRES MICROPHONE)"""
import sys
sys.path.insert(0, '/home/kloros')

print("=" * 60)
print("KLoROS Audio Quality Test")
print("=" * 60)
print()
print("⚠️  This test will capture audio from your microphone")
print("⚠️  Speak for 3 seconds when prompted")
print()

input("Press ENTER to start audio test...")
print()

try:
    import numpy as np

    # Try to import sounddevice
    try:
        import sounddevice as sd
        has_sounddevice = True
    except ImportError:
        has_sounddevice = False
        print("❌ sounddevice not installed")
        print("   Install with: pip install sounddevice")
        print()

    if has_sounddevice:
        # Get audio configuration
        import os
        sample_rate = int(os.getenv('KLR_CAPTURE_RATE', '48000'))
        duration = 3  # seconds

        print(f"📡 Capturing {duration} seconds at {sample_rate}Hz...")
        print("🎤 SPEAK NOW!")
        print()

        # Capture audio
        recording = sd.rec(
            int(duration * sample_rate),
            samplerate=sample_rate,
            channels=1,
            dtype='float32'
        )
        sd.wait()

        print("✅ Capture complete. Analyzing...")
        print()

        # Calculate metrics
        rms = np.sqrt(np.mean(recording**2))
        peak = np.max(np.abs(recording))

        # Convert to dBFS
        if rms > 0:
            dbfs_rms = 20 * np.log10(rms)
        else:
            dbfs_rms = float('-inf')

        if peak > 0:
            dbfs_peak = 20 * np.log10(peak)
        else:
            dbfs_peak = float('-inf')

        # Calculate activity
        threshold_rms = 0.01
        active_frames = np.sum(np.abs(recording) > threshold_rms)
        activity_ratio = active_frames / len(recording)

        # Display results
        print("📊 Audio Quality Results:")
        print("=" * 60)
        print(f"   RMS Level:     {dbfs_rms:.2f} dBFS")
        print(f"   Peak Level:    {dbfs_peak:.2f} dBFS")
        print(f"   Activity:      {activity_ratio*100:.1f}%")
        print(f"   Sample Rate:   {sample_rate} Hz")
        print()

        # Assess quality
        print("💡 Assessment:")
        if dbfs_peak < -30:
            print("   ❌ Audio too quiet")
            print("      → Increase KLR_INPUT_GAIN in .kloros_env")
            print("      → Move closer to microphone")
        elif dbfs_peak > -6:
            print("   ⚠️  Audio too loud (may clip)")
            print("      → Decrease KLR_INPUT_GAIN in .kloros_env")
            print("      → Move further from microphone")
        else:
            print("   ✅ Audio levels good")

        if activity_ratio < 0.2:
            print("   ⚠️  Low voice activity detected")
            print("      → Speak more clearly/loudly")
            print("      → Check microphone positioning")
        else:
            print("   ✅ Voice activity detected")

        print()

        # STT test (if available)
        print("🔍 Testing STT recognition...")
        try:
            # Convert to int16 for STT
            audio_int16 = (recording * 32767).astype(np.int16)

            # Try Vosk
            try:
                from vosk import Model, KaldiRecognizer
                import json

                model_path = os.getenv('KLR_VOSK_MODEL_DIR', '/home/kloros/models/vosk/model')
                model = Model(model_path)
                recognizer = KaldiRecognizer(model, sample_rate)

                recognizer.AcceptWaveform(audio_int16.tobytes())
                result = json.loads(recognizer.FinalResult())

                if result.get('text'):
                    print(f"   ✅ Vosk recognized: \"{result['text']}\"")
                else:
                    print(f"   ⚠️  Vosk did not recognize any speech")

            except ImportError:
                print("   ⚠️  Vosk not available (expected in venv)")
            except Exception as e:
                print(f"   ❌ STT test failed: {e}")

        except Exception as e:
            print(f"   ⚠️  STT test skipped: {e}")

        print()

    print("=" * 60)
    print("Test Complete")
    print("=" * 60)
    print()
    print("📝 Notes:")
    print("   - Optimal levels: -20 to -10 dBFS")
    print("   - Voice activity should be >30%")
    print("   - If STT didn't recognize speech, audio may be too quiet")
    print()

except ImportError as e:
    print(f"❌ Import error: {e}")
    print()
    print("Required packages:")
    print("  - numpy: pip install numpy")
    print("  - sounddevice: pip install sounddevice")
    print()
except Exception as e:
    print(f"❌ Test failed: {e}")
    import traceback
    traceback.print_exc()
