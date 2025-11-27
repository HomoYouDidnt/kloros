"""
Separated audio architecture with isolated Vosk process.
Implements Process A (audio capture) + Process B (Vosk recognition) + Watchdog.
"""

import multiprocessing as mp
import os
import signal
import sys
import time
from pathlib import Path
from typing import Optional, Dict, Any, Callable

import numpy as np

# Add project root to path
_repo_root = Path(__file__).resolve().parent.parent.parent
if str(_repo_root) not in sys.path:
    sys.path.insert(0, str(_repo_root))

from src.audio.capture import create_audio_backend, AudioInputBackend
from src.audio.process_ipc import AudioProcessIPC
from src.audio.vosk_process import VoskRecognizer


class SeparatedAudioSystem:
    """Manages separated audio capture and Vosk recognition processes."""

    def __init__(
        self,
        sample_rate: int = 48000,
        buffer_seconds: float = 2.0,
        audio_backend: str = "sounddevice",
        audio_device: Optional[int] = None,
    ):
        """Initialize separated audio system.

        Args:
            sample_rate: Audio sample rate
            buffer_seconds: Ring buffer size in seconds
            audio_backend: Audio backend to use ("sounddevice" or "mock")
            audio_device: Audio device index (None for auto-detect)
        """
        self.sample_rate = sample_rate
        self.buffer_seconds = buffer_seconds
        self.audio_backend_name = audio_backend
        self.audio_device = audio_device

        # IPC system
        self.ipc = AudioProcessIPC(buffer_seconds, sample_rate)

        # Processes
        self.audio_process: Optional[mp.Process] = None
        self.vosk_process: Optional[mp.Process] = None

        # State
        self.running = False
        self.wake_detected_callback: Optional[Callable] = None
        self.recognition_callback: Optional[Callable] = None

        # Configuration
        self.wake_phrases = ["kloros"]
        self.wake_conf_min = 0.65
        self.wake_rms_min = 350
        self.fuzzy_threshold = 0.8

    def set_wake_config(
        self,
        phrases: Optional[list] = None,
        conf_min: Optional[float] = None,
        rms_min: Optional[int] = None,
        fuzzy_threshold: Optional[float] = None,
    ):
        """Update wake word configuration."""
        if phrases is not None:
            self.wake_phrases = phrases
        if conf_min is not None:
            self.wake_conf_min = conf_min
        if rms_min is not None:
            self.wake_rms_min = rms_min
        if fuzzy_threshold is not None:
            self.fuzzy_threshold = fuzzy_threshold

        # Send update to Vosk process if running
        if self.vosk_process and self.vosk_process.is_alive():
            config = {
                "wake_phrases": self.wake_phrases,
                "wake_conf_min": self.wake_conf_min,
                "wake_rms_min": self.wake_rms_min,
                "fuzzy_threshold": self.fuzzy_threshold,
            }
            self.ipc.send_command("update_wake_config", config)

    def set_callbacks(
        self,
        wake_detected: Optional[Callable] = None,
        recognition: Optional[Callable] = None,
    ):
        """Set callbacks for audio events."""
        self.wake_detected_callback = wake_detected
        self.recognition_callback = recognition

    def start(self) -> bool:
        """Start the separated audio system."""
        if self.running:
            print("[audio-sep] System already running")
            return True

        print("[audio-sep] Starting separated audio system")

        try:
            # Start Vosk process first
            self.vosk_process = mp.Process(
                target=self._run_vosk_process,
                args=(self.ipc.ring_buffer.shared_mem.name,),
                daemon=True,
            )
            self.vosk_process.start()

            # Wait for Vosk process to be ready
            ready_timeout = 30.0  # seconds - increased for Vosk model loading
            start_time = time.monotonic()
            vosk_ready = False

            while time.monotonic() - start_time < ready_timeout:
                status = self.ipc.get_status(timeout=0.1)
                if status:
                    status_type, data, timestamp = status
                    if status_type == "ready":
                        vosk_ready = True
                        print("[audio-sep] Vosk process ready")
                        break
                    elif status_type == "error":
                        print(f"[audio-sep] Vosk process error: {data.get('message', 'Unknown error')}")
                        self.stop()
                        return False

            if not vosk_ready:
                print("[audio-sep] Vosk process failed to start within timeout")
                self.stop()
                return False

            # Send initial configuration to Vosk process
            config = {
                "wake_phrases": self.wake_phrases,
                "wake_conf_min": self.wake_conf_min,
                "wake_rms_min": self.wake_rms_min,
                "fuzzy_threshold": self.fuzzy_threshold,
            }
            self.ipc.send_command("update_wake_config", config)

            # Start audio capture process
            self.audio_process = mp.Process(
                target=self._run_audio_process,
                daemon=True,
            )
            self.audio_process.start()

            self.running = True
            print("[audio-sep] Separated audio system started successfully")
            return True

        except Exception as e:
            print(f"[audio-sep] Failed to start system: {e}")
            self.stop()
            return False

    def stop(self):
        """Stop the separated audio system."""
        if not self.running:
            return

        print("[audio-sep] Stopping separated audio system")
        self.running = False

        # Signal shutdown to processes
        self.ipc.send_command("shutdown", {})

        # Stop processes
        if self.audio_process and self.audio_process.is_alive():
            self.audio_process.terminate()
            self.audio_process.join(timeout=2.0)
            if self.audio_process.is_alive():
                self.audio_process.kill()

        if self.vosk_process and self.vosk_process.is_alive():
            self.vosk_process.terminate()
            self.vosk_process.join(timeout=2.0)
            if self.vosk_process.is_alive():
                self.vosk_process.kill()

        # Clean up IPC resources
        self.ipc.cleanup()

        print("[audio-sep] Separated audio system stopped")

    def set_recognition_mode(self, mode: str):
        """Set recognition mode: 'wake' or 'general'."""
        if mode in ["wake", "general"]:
            self.ipc.send_command("set_mode", {"mode": mode})
            print(f"[audio-sep] Recognition mode set to: {mode}")

    def reset_recognizers(self):
        """Reset Vosk recognizers for clean state."""
        self.ipc.send_command("reset_recognizers", {})

    def process_events(self, timeout: float = 0.1) -> int:
        """Process events from Vosk process.

        Args:
            timeout: Maximum time to wait for events

        Returns:
            Number of events processed
        """
        events_processed = 0

        while True:
            status = self.ipc.get_status(timeout=timeout if events_processed == 0 else 0.0)
            if status is None:
                break

            status_type, data, timestamp = status
            events_processed += 1

            if status_type == "recognition":
                self._handle_recognition_result(data)
            elif status_type == "error":
                print(f"[audio-sep] Vosk process error: {data.get('message', 'Unknown error')}")
            elif status_type == "heartbeat":
                # Heartbeat received - Vosk process is alive
                pass

        return events_processed

    def _handle_recognition_result(self, result: Dict[str, Any]):
        """Handle recognition result from Vosk process."""
        result_type = result.get("type", "unknown")

        if result_type == "wake_detected" and self.wake_detected_callback:
            self.wake_detected_callback(result)
        elif result_type in ["speech_recognized", "partial_recognition"] and self.recognition_callback:
            self.recognition_callback(result)

    def is_healthy(self) -> bool:
        """Check if system is healthy (processes alive, heartbeat OK)."""
        if not self.running:
            return False

        # Check if processes are alive
        if self.audio_process and not self.audio_process.is_alive():
            print("[audio-sep] Audio process died")
            return False

        if self.vosk_process and not self.vosk_process.is_alive():
            print("[audio-sep] Vosk process died")
            return False

        # Check heartbeat
        if not self.ipc.check_heartbeat():
            print("[audio-sep] Vosk process heartbeat timeout")
            return False

        return True

    def _run_audio_process(self):
        """Audio capture process (Process A) - minimal callback work."""
        try:
            print("[audio-process] Starting audio capture process")

            # Create audio backend with better error handling
            max_retries = 3
            for attempt in range(max_retries):
                try:
                    backend = create_audio_backend(self.audio_backend_name)
                    backend.open(
                        sample_rate=self.sample_rate,
                        channels=1,
                        device=self.audio_device,
                    )
                    print(f"[audio-process] Audio backend opened: {self.audio_backend_name}")
                    break
                except Exception as e:
                    print(f"[audio-process] Attempt {attempt + 1}/{max_retries} failed: {e}")
                    if attempt == max_retries - 1:
                        # Last attempt - try default device
                        try:
                            backend = create_audio_backend(self.audio_backend_name)
                            backend.open(
                                sample_rate=self.sample_rate,
                                channels=1,
                                device=None,  # Use default device
                            )
                            print(f"[audio-process] Using default device as fallback")
                            break
                        except Exception as e2:
                            print(f"[audio-process] Default device also failed: {e2}")
                            # Try mock backend as final fallback
                            try:
                                backend = create_audio_backend("mock")
                                backend.open(
                                    sample_rate=self.sample_rate,
                                    channels=1,
                                    device=None,
                                )
                                print(f"[audio-process] Using mock backend as final fallback")
                                break
                            except Exception as e3:
                                print(f"[audio-process] All backends failed: {e3}")
                                return
                    else:
                        import time
                        time.sleep(1.0)  # Wait before retry

            # Process audio chunks and write to ring buffer
            # Adjust block size based on device type for PipeWire compatibility
            if self.audio_device is not None and self.audio_device >= 12:  # ALSA virtual devices (default, etc.)
                block_ms = 50  # Larger blocks for PipeWire/virtual devices to prevent overflow
                print(f"[audio-process] Using {block_ms}ms blocks for virtual device {self.audio_device} (PipeWire compatible)")
            else:
                block_ms = 20  # Small blocks for direct hardware devices
                print(f"[audio-process] Using {block_ms}ms blocks for hardware device {self.audio_device}")
            for chunk in backend.chunks(block_ms):
                if self.ipc.shutdown_event.is_set():
                    break

                # Write to shared ring buffer - this is the ONLY work in the audio callback
                self.ipc.ring_buffer.write(chunk)

        except Exception as e:
            print(f"[audio-process] Audio process error: {e}")
        finally:
            if 'backend' in locals():
                backend.close()
            print("[audio-process] Audio capture process stopped")

    def _run_vosk_process(self, shared_mem_name: str):
        """Vosk recognition process (Process B) - isolated from audio capture."""
        try:
            print(f"[vosk-process] Starting Vosk process with shared memory: {shared_mem_name}")
            
            # Create Vosk recognizer with existing IPC connection
            recognizer = VoskRecognizer(self.ipc, self.sample_rate)
            recognizer.run()

        except Exception as e:
            print(f"[vosk-process] Vosk process error: {e}")
            self.ipc.send_status("error", {"message": f"Vosk process error: {e}"})
        finally:
            print("[vosk-process] Vosk recognition process stopped")

    def __enter__(self):
        """Context manager entry."""
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.stop()


def main():
    """Example usage of separated audio system."""
    def on_wake_detected(result):
        print(f"WAKE DETECTED: {result['matched_phrase']} (confidence: {result['confidence']:.2f})")

    def on_recognition(result):
        if result['type'] == 'speech_recognized':
            print(f"RECOGNIZED: {result['text']} (confidence: {result['confidence']:.2f})")
        elif result['type'] == 'partial_recognition':
            print(f"PARTIAL: {result['text']}")

    # Create separated audio system
    audio_system = SeparatedAudioSystem(
        sample_rate=48000,
        audio_backend="mock",  # Use mock for testing
    )

    audio_system.set_callbacks(
        wake_detected=on_wake_detected,
        recognition=on_recognition,
    )

    try:
        if audio_system.start():
            print("System started successfully. Processing events...")

            # Process events for demonstration
            for i in range(100):  # Run for ~10 seconds
                events = audio_system.process_events(timeout=0.1)
                if not audio_system.is_healthy():
                    print("System unhealthy, stopping...")
                    break
                time.sleep(0.1)

        else:
            print("Failed to start system")

    except KeyboardInterrupt:
        print("Interrupted by user")
    finally:
        audio_system.stop()


if __name__ == "__main__":
    main()
