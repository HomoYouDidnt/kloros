#!/usr/bin/env python3
"""Simple microphone RMS level tester."""
import subprocess
import struct
import numpy as np
import sys

# Configuration matching KLoROS
SAMPLE_RATE = 48000
BLOCK_MS = 8
BLOCK_SIZE = int(SAMPLE_RATE * BLOCK_MS / 1000)
INPUT_GAIN = 5.0
DEVICE_INDEX = 11

def rms16(data: bytes) -> float:
    """Calculate RMS of int16 audio data."""
    if len(data) == 0:
        return 0.0
    samples = struct.unpack(f"{len(data)//2}h", data)
    return float(np.sqrt(np.mean(np.array(samples, dtype=np.float32)**2)))

def main():
    """Listen to microphone and report RMS values."""
    print(f"[test_mic] Starting microphone RMS test")
    print(f"[test_mic] Device: {DEVICE_INDEX}, Sample Rate: {SAMPLE_RATE}, Block: {BLOCK_MS}ms, Gain: {INPUT_GAIN}x")
    print(f"[test_mic] Press Ctrl+C to stop")
    print()

    # Start pacat to capture audio
    cmd = [
        "pacat",
        "--record",
        f"--rate={SAMPLE_RATE}",
        "--channels=1",
        "--format=s16le",
        f"--latency-msec={BLOCK_MS}",
        f"--device={DEVICE_INDEX}"
    ]

    try:
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

        counter = 0
        while True:
            # Read one block of audio
            bytes_per_block = BLOCK_SIZE * 2  # 2 bytes per int16 sample
            data = proc.stdout.read(bytes_per_block)

            if len(data) < bytes_per_block:
                break

            # Apply gain (simulate KLoROS processing)
            int16_data = np.frombuffer(data, dtype=np.int16)
            float32_data = int16_data.astype(np.float32) / 32767.0
            gained_data = float32_data * INPUT_GAIN
            gained_data = np.clip(gained_data, -1.0, 1.0)
            gained_int16 = (gained_data * 32767).astype(np.int16)
            gained_bytes = gained_int16.tobytes()

            # Calculate RMS
            rms = rms16(gained_bytes)

            counter += 1
            if counter % 10 == 0:  # Log every 10 blocks (~80ms)
                print(f"[rms] {rms:6.1f}  {'█' * min(int(rms/10), 50)}")

    except KeyboardInterrupt:
        print("\n[test_mic] Stopped")
    finally:
        if proc:
            proc.terminate()
            proc.wait()

if __name__ == "__main__":
    main()
