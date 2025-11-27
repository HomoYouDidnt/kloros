"""Audio capture backend abstraction for KLoROS."""
from __future__ import annotations
import subprocess

import threading
import time
from typing import Union, Iterator, Literal, Optional, Protocol

import numpy as np


class AudioInputBackend(Protocol):
    """Protocol for audio input backends."""

    def open(self, sample_rate: int, channels: int, device: Optional[Union[int, str]] = None) -> None:
        """Open audio input stream.

        Args:
            sample_rate: Sample rate in Hz
            channels: Number of audio channels (1 for mono)
            device: Device index (None for default)
        """
        ...

    def chunks(self, block_ms: int) -> Iterator[np.ndarray]:
        """Yield audio chunks as they become available.

        Args:
            block_ms: Block size in milliseconds

        Yields:
            Audio chunks as float32 mono arrays in range [-1, 1]
        """
        ...

    def flush(self) -> int:
        """Flush/clear audio buffer to discard old data.

        Returns:
            Number of samples or chunks cleared
        """
        ...

    def close(self) -> None:
        """Close audio input stream and clean up resources."""
        ...


class RingBuffer:
    """Thread-safe circular audio buffer."""

    def __init__(self, capacity_samples: int):
        """Initialize ring buffer.

        Args:
            capacity_samples: Buffer capacity in samples
        """
        self.capacity = capacity_samples
        self.buffer = np.zeros(capacity_samples, dtype=np.float32)
        self.write_idx = 0
        self.read_idx = 0
        self.lock = threading.Lock()
        self._available_samples = 0

    def write(self, data: np.ndarray) -> None:
        """Write audio data to the ring buffer.

        Args:
            data: Audio samples to write (float32)
        """
        with self.lock:
            data_len = len(data)

            if data_len > self.capacity:
                # If data is larger than buffer, take only the last part
                data = data[-self.capacity :]
                data_len = len(data)

            # Calculate wrap-around
            end_idx = self.write_idx + data_len

            if end_idx <= self.capacity:
                # No wrap needed
                self.buffer[self.write_idx : end_idx] = data
            else:
                # Wrap around
                first_part = self.capacity - self.write_idx
                self.buffer[self.write_idx :] = data[:first_part]
                self.buffer[: end_idx - self.capacity] = data[first_part:]

            self.write_idx = end_idx % self.capacity
            self._available_samples = min(self._available_samples + data_len, self.capacity)

            # If buffer is full and we're overwriting, advance read pointer
            if self._available_samples == self.capacity and data_len > 0:
                self.read_idx = self.write_idx

    def read(self, num_samples: int) -> Optional[np.ndarray]:
        """Read audio data from the ring buffer.

        Args:
            num_samples: Number of samples to read

        Returns:
            Audio samples or None if not enough data available
        """
        with self.lock:
            if self._available_samples < num_samples:
                return None

            result = np.zeros(num_samples, dtype=np.float32)

            # Calculate wrap-around
            end_idx = self.read_idx + num_samples

            if end_idx <= self.capacity:
                # No wrap needed
                result[:] = self.buffer[self.read_idx : end_idx]
            else:
                # Wrap around
                first_part = self.capacity - self.read_idx
                result[:first_part] = self.buffer[self.read_idx :]
                result[first_part:] = self.buffer[: end_idx - self.capacity]

            self.read_idx = end_idx % self.capacity
            self._available_samples -= num_samples

            return result

    def available_samples(self) -> int:
        """Get number of available samples for reading."""
        with self.lock:
            return self._available_samples

    def clear(self) -> int:
        """Clear all buffered audio data.

        Returns:
            Number of samples that were cleared
        """
        with self.lock:
            cleared_count = self._available_samples
            self.read_idx = self.write_idx
            self._available_samples = 0
            return cleared_count


class SoundDeviceBackend:
    """Audio input backend using SoundDevice library."""

    def __init__(self, **kwargs):
        """Initialize SoundDevice backend.

        Raises:
            RuntimeError: If sounddevice is not available
        """
        try:
            import sounddevice as sd

            self.sd = sd
        except (ImportError, OSError) as e:
            raise RuntimeError("sounddevice unavailable") from e

        self.stream = None
        self.ring_buffer = None
        self.sample_rate = None
        self.channels = None

    def open(self, sample_rate: int, channels: int, device: Optional[Union[int, str]] = None) -> None:
        """Open audio input stream."""
        self.sample_rate = sample_rate
        self.channels = channels

        # Create ring buffer for 2 seconds of audio by default
        ring_capacity = int(sample_rate * 2.0)
        self.ring_buffer = RingBuffer(ring_capacity)

        def audio_callback(indata, frames, time_info, status):
            """Callback for audio input."""
            if status:
                print(f"Audio input status: {status}")

            # Convert to mono if needed and write to ring buffer
            if indata.shape[1] == 1:
                audio_data = indata[:, 0].astype(np.float32)
            else:
                # Convert multi-channel to mono by averaging
                audio_data = np.mean(indata, axis=1).astype(np.float32)

            self.ring_buffer.write(audio_data)

        # Open the input stream
        # Configure buffer size based on device type for PipeWire compatibility
        # Device names or high indices indicate virtual/PipeWire devices
        is_virtual = isinstance(device, str) or (isinstance(device, int) and device >= 12)
        
        if is_virtual:
            # Larger buffers for PipeWire/virtual devices to prevent overflow
            blocksize = int(sample_rate * 0.05)  # 50ms buffer
            latency = 0.1  # 100ms total latency
            print(f"[audio] Using large buffers for virtual device {device}: blocksize={blocksize}, latency={latency}")
        else:
            # Smaller buffers for direct hardware devices
            blocksize = int(sample_rate * 0.02)  # 20ms buffer
            latency = 0.05  # 50ms total latency
            print(f"[audio] Using small buffers for hardware device {device}: blocksize={blocksize}, latency={latency}")

        # Open the input stream with device-specific buffer configuration
        self.stream = self.sd.InputStream(
            device=device,
            channels=channels,
            samplerate=sample_rate,
            callback=audio_callback,
            dtype=np.float32,
            blocksize=blocksize,
            latency=latency,
        )
        self.stream.start()

    def chunks(self, block_ms: int) -> Iterator[np.ndarray]:
        """Yield audio chunks from the ring buffer."""
        if not self.ring_buffer or not self.sample_rate:
            raise RuntimeError("Backend not opened")

        block_samples = int(block_ms * self.sample_rate / 1000.0)

        while True:
            # Wait until we have enough samples
            while self.ring_buffer.available_samples() < block_samples:
                time.sleep(0.001)  # Small sleep to avoid busy waiting

            chunk = self.ring_buffer.read(block_samples)
            if chunk is not None:
                yield chunk

    def flush(self) -> int:
        """Flush/clear the audio ring buffer.

        Returns:
            Number of samples cleared
        """
        if self.ring_buffer:
            return self.ring_buffer.clear()
        return 0

    def close(self) -> None:
        """Close audio input stream."""
        if self.stream:
            self.stream.stop()
            self.stream.close()
            self.stream = None
        self.ring_buffer = None



# PulseAudio Backend Implementation
class PulseAudioBackend:
    """PulseAudio backend using pacat subprocess for reliable audio capture."""

    def __init__(self, **kwargs):
        """Initialize PulseAudio backend."""
        self.source_name = None  # Use default source
        self.process: Optional[subprocess.Popen] = None
        self.capture_thread: Optional[threading.Thread] = None
        self.running = False
        self.paused = False  # Pause audio capture during TTS
        self.ring_buffer: Optional[RingBuffer] = None
        self.sample_rate = None
        self.chunk_size_samples = None

    def _activate_source(self):
        """Activate PulseAudio source if suspended."""
        if self.source_name is None:
            return  # Skip activation for default source
        try:
            # Try multiple times as PipeWire can be slow to respond
            for attempt in range(3):
                result = subprocess.run(["pactl", "suspend-source", self.source_name, "0"],
                             capture_output=True, timeout=2)
                if result.returncode == 0:
                    break
                time.sleep(0.5)
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
            print(f"[PulseAudio] Warning: Could not activate source: {e}")

    def open(self, sample_rate: int, channels: int, device: Optional[Union[int, str]] = None) -> None:
        """Open PulseAudio capture stream."""
        if self.running:
            return

        self.sample_rate = sample_rate
        self.chunk_size_samples = int(sample_rate * 0.008)  # 8ms chunks
        self.ring_buffer = RingBuffer(sample_rate * 2)  # 2 second buffer

        # Activate source
        self._activate_source()

        # Start pacat subprocess
        cmd = [
            "pacat", "--record", "--raw",
            f"--format=s16le", f"--rate={sample_rate}", "--channels=1",
        ]
        if self.source_name is not None:
            cmd.append(f"--device={self.source_name}")

        try:
            self.process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            self.running = True
        except Exception as e:
            raise RuntimeError(f"Failed to start pacat: {e}")

        # Start capture thread
        def capture_loop():
            bytes_per_chunk = self.chunk_size_samples * 2  # 16-bit = 2 bytes per sample
            while self.running and self.process and self.process.poll() is None:
                try:
                    data = self.process.stdout.read(bytes_per_chunk)

                    # Skip writing to ring buffer if paused (but keep reading to prevent buffer buildup)
                    if self.paused:
                        continue

                    if data and len(data) == bytes_per_chunk:
                        # Convert to float32 numpy array
                        int16_array = np.frombuffer(data, dtype=np.int16)
                        float32_array = int16_array.astype(np.float32) / 32768.0
                        self.ring_buffer.write(float32_array)
                    elif len(data) > 0:
                        # Handle partial reads
                        padded = data + b"\x00" * (bytes_per_chunk - len(data))
                        int16_array = np.frombuffer(padded, dtype=np.int16)
                        float32_array = int16_array.astype(np.float32) / 32768.0
                        self.ring_buffer.write(float32_array)
                    else:
                        time.sleep(0.001)
                except Exception as e:
                    print(f"[PulseAudio] Capture error: {e}")
                    break

        self.capture_thread = threading.Thread(target=capture_loop, daemon=True)
        self.capture_thread.start()

    def chunks(self, block_ms: int) -> Iterator[np.ndarray]:
        """Yield audio chunks from PulseAudio capture."""
        if not self.running or not self.ring_buffer or not self.sample_rate:
            raise RuntimeError("Backend not opened")

        block_samples = int(self.sample_rate * block_ms / 1000.0)

        while self.running:
            chunk = self.ring_buffer.read(block_samples)
            if chunk is not None:
                yield chunk
            else:
                time.sleep(block_ms / 2000.0)  # Wait half block duration

    def flush(self) -> int:
        """Flush/clear the audio ring buffer.

        Returns:
            Number of samples cleared
        """
        if self.ring_buffer:
            return self.ring_buffer.clear()
        return 0

    def pause(self) -> None:
        """Pause audio capture (for TTS playback - prevents echo)."""
        if not self.paused:
            self.paused = True
            print("[audio] Capture PAUSED (TTS playing)")

    def resume(self) -> None:
        """Resume audio capture after TTS playback."""
        if self.paused:
            self.paused = False
            print("[audio] Capture RESUMED (TTS done)")

    def close(self) -> None:
        """Close PulseAudio capture and cleanup."""
        self.running = False
        if self.process:
            try:
                self.process.terminate()
                self.process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                self.process.kill()
            except Exception:
                pass
            self.process = None
        if self.capture_thread:
            self.capture_thread.join(timeout=1)
            self.capture_thread = None
        self.ring_buffer = None

class MockBackend:
    """Mock audio input backend for testing."""

    def __init__(self, max_blocks: Optional[int] = None, **kwargs):
        """Initialize mock backend.

        Args:
            max_blocks: Maximum number of blocks to yield (None for infinite)
        """
        self.max_blocks = max_blocks
        self.sample_rate: Optional[int] = None
        self.synth_audio: Optional[np.ndarray] = None
        self.synth_position = 0
        self.blocks_yielded = 0

    def _generate_synth_audio(self, sample_rate: int) -> np.ndarray:
        """Generate deterministic synthetic audio (reuse from system_smoke)."""
        # Calculate samples for each segment
        noise1_samples = int(0.5 * sample_rate)
        tone_samples = int(0.8 * sample_rate)
        noise2_samples = int(0.5 * sample_rate)

        # Generate noise segments at -60 dBFS
        # Use fixed seed for deterministic output
        np.random.seed(42)
        noise_amplitude = 10 ** (-60 / 20)
        noise1 = np.random.normal(0, noise_amplitude, noise1_samples).astype(np.float32)

        np.random.seed(43)  # Different seed for second noise segment
        noise2 = np.random.normal(0, noise_amplitude, noise2_samples).astype(np.float32)

        # Generate 440Hz tone at -20 dBFS
        tone_amplitude = 10 ** (-20 / 20)
        t = np.linspace(0, 0.8, tone_samples, endpoint=False)
        tone = (tone_amplitude * np.sin(2 * np.pi * 440 * t)).astype(np.float32)

        # Concatenate all segments
        return np.concatenate([noise1, tone, noise2])

    def open(self, sample_rate: int, channels: int, device: Optional[Union[int, str]] = None) -> None:
        """Open mock audio input."""
        self.sample_rate = sample_rate
        self.synth_audio = self._generate_synth_audio(sample_rate)
        self.synth_position = 0
        self.blocks_yielded = 0

    def chunks(self, block_ms: int) -> Iterator[np.ndarray]:
        """Yield audio chunks from synthetic audio."""
        if not self.sample_rate or self.synth_audio is None:
            raise RuntimeError("Backend not opened")

        block_samples = int(block_ms * self.sample_rate / 1000.0)

        while True:
            if self.max_blocks is not None and self.blocks_yielded >= self.max_blocks:
                break

            # Get next chunk from synthetic audio (loop when reaching end)
            start_pos = self.synth_position
            end_pos = start_pos + block_samples

            if end_pos <= len(self.synth_audio):
                chunk = self.synth_audio[start_pos:end_pos].copy()
                self.synth_position = end_pos
            else:
                # Wrap around to beginning
                remaining = len(self.synth_audio) - start_pos
                chunk = np.zeros(block_samples, dtype=np.float32)
                chunk[:remaining] = self.synth_audio[start_pos:]

                # Fill the rest from the beginning
                needed = block_samples - remaining
                chunk[remaining:] = self.synth_audio[:needed]
                self.synth_position = needed

            self.blocks_yielded += 1
            yield chunk

            # Small delay to simulate real-time audio
            time.sleep(block_ms / 1000.0)

    def flush(self) -> int:
        """Flush mock backend (no-op for mock)."""
        return 0

    def close(self) -> None:
        """Close mock audio input."""
        self.synth_audio = None
        self.synth_position = 0
        self.blocks_yielded = 0


BackendName = Literal["pulseaudio", "sounddevice", "mock"]


def create_audio_backend(name: BackendName, **kwargs) -> AudioInputBackend:
    """Create an audio input backend by name.

    Args:
        name: Backend name ("pulseaudio", "sounddevice", or "mock")
        **kwargs: Backend-specific arguments

    Returns:
        Audio input backend instance

    Raises:
        ValueError: If backend name is unknown
        RuntimeError: If backend cannot be initialized
    """
    if name == "pulseaudio":
        return PulseAudioBackend(**kwargs)
    if name == "sounddevice":
        return SoundDeviceBackend(**kwargs)
    elif name == "mock":
        return MockBackend(**kwargs)
    else:
        raise ValueError(f"Unknown audio backend: {name}")
