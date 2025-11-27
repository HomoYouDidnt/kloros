"""
Inter-Process Communication for separated audio processing.
Implements lock-free ring buffer using shared memory for high-performance audio streaming.
"""

import multiprocessing as mp
from multiprocessing import shared_memory
import time
import struct
from typing import Optional, Tuple
import numpy as np


class SharedRingBuffer:
    """Lock-free ring buffer using shared memory for audio IPC."""

    def __init__(self, capacity_samples: int, sample_rate: int = 48000):
        """Initialize shared ring buffer.

        Args:
            capacity_samples: Buffer capacity in audio samples
            sample_rate: Audio sample rate for timing calculations
        """
        self.capacity = capacity_samples
        self.sample_rate = sample_rate
        self.sample_size = 4  # float32 = 4 bytes

        # Create shared memory for audio data + metadata
        # Buffer layout: [write_idx][read_idx][available_count][audio_data...]
        metadata_size = 3 * 8  # 3 x int64 for indices and count
        buffer_size = capacity_samples * self.sample_size
        self.total_size = metadata_size + buffer_size

        import uuid
        shm_name = f"kloros_audio_{uuid.uuid4().hex[:8]}"
        self.shared_mem = shared_memory.SharedMemory(create=True, size=self.total_size, name=shm_name)

        # Initialize metadata to zero
        self._write_metadata(0, 0, 0)  # write_idx, read_idx, available_count

        self._is_owner = True  # This process created the shared memory        # Zero out audio buffer
        audio_start = metadata_size
        audio_view = memoryview(self.shared_mem.buf)[audio_start:audio_start + buffer_size]
        audio_array = np.frombuffer(audio_view, dtype=np.float32)
        audio_array.fill(0.0)

    def _write_metadata(self, write_idx: int, read_idx: int, available_count: int):
        """Write metadata atomically using struct packing."""
        metadata = struct.pack('QQQ', write_idx, read_idx, available_count)
        self.shared_mem.buf[:24] = metadata

    def _read_metadata(self) -> Tuple[int, int, int]:
        """Read metadata atomically using struct unpacking."""
        metadata = bytes(self.shared_mem.buf[:24])
        return struct.unpack('QQQ', metadata)

    def get_audio_buffer(self) -> np.ndarray:
        """Get numpy view of the audio buffer."""
        audio_start = 24  # metadata size
        audio_end = audio_start + self.capacity * self.sample_size
        audio_view = memoryview(self.shared_mem.buf)[audio_start:audio_end]
        return np.frombuffer(audio_view, dtype=np.float32)

    def write(self, data: np.ndarray) -> bool:
        """Write audio data to ring buffer (producer side - Process A)."""
        data_len = len(data)
        if data_len > self.capacity:
            data = data[-self.capacity:]
            data_len = len(data)

        write_idx, read_idx, available_count = self._read_metadata()

        max_available = self.capacity - 1
        if available_count + data_len > max_available:
            overflow_samples = (available_count + data_len) - max_available
            read_idx = (read_idx + overflow_samples) % self.capacity
            available_count -= overflow_samples

        audio_buffer = self.get_audio_buffer()
        end_idx = write_idx + data_len

        if end_idx <= self.capacity:
            audio_buffer[write_idx:end_idx] = data
        else:
            first_part = self.capacity - write_idx
            audio_buffer[write_idx:] = data[:first_part]
            audio_buffer[:end_idx - self.capacity] = data[first_part:]

        new_write_idx = end_idx % self.capacity
        new_available = available_count + data_len
        self._write_metadata(new_write_idx, read_idx, new_available)
        return True

    def read(self, num_samples: int) -> Optional[np.ndarray]:
        """Read audio data from ring buffer (consumer side - Process B)."""
        write_idx, read_idx, available_count = self._read_metadata()

        if available_count < num_samples:
            return None

        audio_buffer = self.get_audio_buffer()
        result = np.zeros(num_samples, dtype=np.float32)

        end_idx = read_idx + num_samples

        if end_idx <= self.capacity:
            result[:] = audio_buffer[read_idx:end_idx]
        else:
            first_part = self.capacity - read_idx
            result[:first_part] = audio_buffer[read_idx:]
            result[first_part:] = audio_buffer[:end_idx - self.capacity]

        new_read_idx = end_idx % self.capacity
        new_available = available_count - num_samples
        self._write_metadata(write_idx, new_read_idx, new_available)
        return result

    def available_samples(self) -> int:
        """Get number of available samples for reading."""
        _, _, available_count = self._read_metadata()
        return available_count

    @classmethod
    def connect_to_existing(cls, shared_mem_name: str, sample_rate: int = 48000):
        """Connect to existing shared memory instead of creating new."""
        existing_shm = shared_memory.SharedMemory(name=shared_mem_name)
        instance = cls.__new__(cls)
        instance.sample_rate = sample_rate
        instance.sample_size = 4
        metadata_size = 24
        buffer_size = existing_shm.size - metadata_size
        instance.capacity = buffer_size // instance.sample_size
        instance.total_size = existing_shm.size
        instance.shared_mem = existing_shm
        instance._is_owner = False
        return instance

    def cleanup(self):
        """Clean up shared memory resources."""
        try:
            self.shared_mem.close()
            if getattr(self, "_is_owner", True):
                self.shared_mem.unlink()
        except Exception:
            pass
            pass


class AudioProcessIPC:
    """Manages IPC between audio capture and Vosk recognition processes."""

    def __init__(self, buffer_seconds: float = 2.0, sample_rate: int = 48000, mp_context=None):
        self.sample_rate = sample_rate
        buffer_samples = int(buffer_seconds * sample_rate)
        self.ring_buffer = SharedRingBuffer(buffer_samples, sample_rate)
        
        # Use provided context or default
        ctx = mp_context if mp_context is not None else mp
        self.cmd_queue = ctx.Queue(maxsize=10)
        self.status_queue = ctx.Queue(maxsize=50)  # Larger buffer for status messages
        self.shutdown_event = ctx.Event()
        self.pause_event = ctx.Event()
        self.ready_event = ctx.Event()  # Child signals when ready
        self.last_heartbeat_time = time.monotonic()
        self.heartbeat_interval = 1.0
        self.heartbeat_timeout = 5.0

    def send_command(self, cmd: str, data=None):
        try:
            self.cmd_queue.put_nowait((cmd, data, time.monotonic()))
        except:
            pass

    def get_command(self, timeout=0.1):
        try:
            return self.cmd_queue.get(timeout=timeout)
        except:
            return None

    def send_status(self, status: str, data=None):
        try:
            self.status_queue.put_nowait((status, data, time.monotonic()))
        except:
            pass

    def get_status(self, timeout=0.1):
        try:
            return self.status_queue.get(timeout=timeout)
        except:
            return None

    def heartbeat(self):
        self.send_status("heartbeat", {"time": time.monotonic()})

    def check_heartbeat(self) -> bool:
        import queue as pyqueue
        current_time = time.monotonic()
        
        # Drain all available heartbeat messages from queue
        while True:
            try:
                status = self.status_queue.get_nowait()
                if status:
                    status_type, data, timestamp = status
                    if status_type == "heartbeat":
                        self.last_heartbeat_time = timestamp
            except pyqueue.Empty:
                break  # No more messages available
        
        return (current_time - self.last_heartbeat_time) < self.heartbeat_timeout

    def cleanup(self):
        self.shutdown_event.set()
        self.ring_buffer.cleanup()
        while not self.cmd_queue.empty():
            try:
                self.cmd_queue.get_nowait()
            except:
                break
        while not self.status_queue.empty():
            try:
                self.status_queue.get_nowait()
            except:
                break
