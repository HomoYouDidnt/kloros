"""Audio capture backend abstraction for KLoROS."""

from __future__ import annotations

import threading
import time
from typing import Protocol, Optional, Iterator, Literal

import numpy as np


class AudioInputBackend(Protocol):
    """Protocol for audio input backends."""

    def open(self, sample_rate: int, channels: int, device: Optional[int] = None) -> None:
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
                data = data[-self.capacity:]
                data_len = len(data)

            # Calculate wrap-around
            end_idx = self.write_idx + data_len

            if end_idx <= self.capacity:
                # No wrap needed
                self.buffer[self.write_idx:end_idx] = data
            else:
                # Wrap around
                first_part = self.capacity - self.write_idx
                self.buffer[self.write_idx:] = data[:first_part]
                self.buffer[:end_idx - self.capacity] = data[first_part:]

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
                result[:] = self.buffer[self.read_idx:end_idx]
            else:
                # Wrap around
                first_part = self.capacity - self.read_idx
                result[:first_part] = self.buffer[self.read_idx:]
                result[first_part:] = self.buffer[:end_idx - self.capacity]

            self.read_idx = end_idx % self.capacity
            self._available_samples -= num_samples

            return result

    def available_samples(self) -> int:
        """Get number of available samples for reading."""
        with self.lock:
            return self._available_samples


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
        except ImportError as e:
            raise RuntimeError("sounddevice unavailable") from e

        self.stream = None
        self.ring_buffer = None
        self.sample_rate = None
        self.channels = None

    def open(self, sample_rate: int, channels: int, device: Optional[int] = None) -> None:
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
        self.stream = self.sd.InputStream(
            device=device,
            channels=channels,
            samplerate=sample_rate,
            callback=audio_callback,
            dtype=np.float32
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

    def close(self) -> None:
        """Close audio input stream."""
        if self.stream:
            self.stream.stop()
            self.stream.close()
            self.stream = None
        self.ring_buffer = None


class MockBackend:
    """Mock audio input backend for testing."""

    def __init__(self, max_blocks: Optional[int] = None, **kwargs):
        """Initialize mock backend.

        Args:
            max_blocks: Maximum number of blocks to yield (None for infinite)
        """
        self.max_blocks = max_blocks
        self.sample_rate = None
        self.synth_audio = None
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

    def open(self, sample_rate: int, channels: int, device: Optional[int] = None) -> None:
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

    def close(self) -> None:
        """Close mock audio input."""
        self.synth_audio = None
        self.synth_position = 0
        self.blocks_yielded = 0


BackendName = Literal["sounddevice", "mock"]


def create_audio_backend(name: BackendName, **kwargs) -> AudioInputBackend:
    """Create an audio input backend by name.

    Args:
        name: Backend name ("sounddevice" or "mock")
        **kwargs: Backend-specific arguments

    Returns:
        Audio input backend instance

    Raises:
        ValueError: If backend name is unknown
        RuntimeError: If backend cannot be initialized
    """
    if name == "sounddevice":
        return SoundDeviceBackend(**kwargs)
    elif name == "mock":
        return MockBackend(**kwargs)
    else:
        raise ValueError(f"Unknown audio backend: {name}")