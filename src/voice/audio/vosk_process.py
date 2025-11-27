"""
Separate Vosk process for speech recognition.
Runs in isolation to prevent threading deadlocks with audio capture.
"""

import json
from scipy import signal
import multiprocessing as mp
import os
import sys
import time
from pathlib import Path
from typing import Optional, Dict, Any

import numpy as np
import vosk

# Add the project root to path for imports
_repo_root = Path(__file__).resolve().parent.parent.parent
if str(_repo_root) not in sys.path:
    sys.path.insert(0, str(_repo_root))

from src.audio.process_ipc import AudioProcessIPC


class VoskRecognizer:
    """Isolated Vosk speech recognition process."""

    def __init__(self, ipc: AudioProcessIPC, sample_rate: int = 48000):
        """Initialize Vosk recognizer.

        Args:
            ipc: Inter-process communication interface
            sample_rate: Audio sample rate
        """
        self.ipc = ipc
        self.sample_rate = sample_rate
        self.model = None
        self.wake_rec = None
        self.general_rec = None
        
        # State management
        self.running = False
        self.recognition_mode = "wake"  # "wake" or "general"
        
        # Wake word configuration
        self.wake_phrases = ["computer"]  # Will be updated via IPC
        self.wake_grammar = json.dumps(self.wake_phrases + ["[unk]"])
        self.wake_conf_min = 0.65
        self.wake_rms_min = 350
        self.fuzzy_threshold = 0.8
        
        # Timing for debounce/cooldown
        self.last_wake_ms = 0
        self.wake_debounce_ms = 400
        self.wake_cooldown_ms = 2000

    def load_vosk_model(self, model_path: Optional[str] = None) -> bool:
        """Load Vosk model safely in isolated process.

        Args:
            model_path: Path to Vosk model directory

        Returns:
            True if model loaded successfully
        """
        if model_path is None:
            model_path = os.path.expanduser("~/KLoROS/models/vosk/model")

        try:
            if os.path.exists(model_path):
                print(f"[vosk-process] Loading model from {model_path}")
                self.model = vosk.Model(model_path)
                print("[vosk-process] Model loaded successfully")
                
                # Create recognizers
                self.general_rec = vosk.KaldiRecognizer(self.model, 16000)  # Model trained at 16 kHz
                self.wake_rec = vosk.KaldiRecognizer(self.model, 16000, self.wake_grammar)  # Model trained at 16 kHz
                
                print("[vosk-process] Recognizers created successfully")
                return True
            else:
                print(f"[vosk-process] Model path not found: {model_path}")
                return False
                
        except Exception as e:
            print(f"[vosk-process] Failed to load model: {e}")
            return False

    def update_wake_config(self, config: Dict[str, Any]):
        """Update wake word configuration.

        Args:
            config: Configuration dictionary with wake word settings
        """
        if "wake_phrases" in config:
            self.wake_phrases = config["wake_phrases"]
            self.wake_grammar = json.dumps(self.wake_phrases + ["[unk]"])
            
            # Recreate wake recognizer with new grammar
            if self.model:
                self.wake_rec = vosk.KaldiRecognizer(self.model, 16000, self.wake_grammar)  # Model trained at 16 kHz
                print(f"[vosk-process] Updated wake phrases: {self.wake_phrases}")

        if "wake_conf_min" in config:
            self.wake_conf_min = config["wake_conf_min"]
        if "wake_rms_min" in config:
            self.wake_rms_min = config["wake_rms_min"]
        if "fuzzy_threshold" in config:
            self.fuzzy_threshold = config["fuzzy_threshold"]

    def _rms16(self, audio_float32: np.ndarray) -> int:
        """Calculate RMS energy of float32 audio."""
        if len(audio_float32) == 0:
            return 0
        
        # Convert to int16 equivalent for energy calculation
        audio_int16 = (audio_float32 * 32767).astype(np.int32)
        return int(np.sqrt(np.mean(audio_int16 * audio_int16)) or 0)

    def _avg_conf(self, result: Dict[str, Any]) -> float:
        """Calculate average confidence from Vosk result."""
        segments = result.get("result", [])
        if not segments:
            return 1.0  # Some models omit confidences
        
        confidences = [seg.get("conf", 1.0) for seg in segments if isinstance(seg, dict)]
        return float(sum(confidences) / max(len(confidences), 1))

    def _fuzzy_wake_match(self, text: str, phrases: list, threshold: float = 0.8) -> tuple:
        """Simple fuzzy matching for wake phrases."""
        from difflib import SequenceMatcher
        
        text = text.lower().strip()
        best_score = 0.0
        best_phrase = ""
        
        for phrase in phrases:
            # Exact match
            if phrase in text:
                return True, 1.0, phrase
            
            # Fuzzy match
            score = SequenceMatcher(None, text, phrase).ratio()
            if score > best_score:
                best_score = score
                best_phrase = phrase
        
        is_match = best_score >= threshold
        return is_match, best_score, best_phrase

    def _resample_to_16k(self, audio_chunk: np.ndarray, orig_sr: int) -> np.ndarray:
        """Resample audio from original sample rate to 16 kHz.
        
        Args:
            audio_chunk: Audio samples at original sample rate
            orig_sr: Original sample rate
            
        Returns:
            Resampled audio at 16 kHz
        """
        if orig_sr == 16000:
            return audio_chunk
        
        # Calculate number of samples at 16 kHz
        num_samples_16k = int(len(audio_chunk) * 16000 / orig_sr)
        
        # Resample using scipy
        resampled = signal.resample(audio_chunk, num_samples_16k)
        return resampled.astype(np.float32)

    def process_audio_chunk(self, audio_chunk: np.ndarray) -> Optional[Dict[str, Any]]:
        """Process a single audio chunk for recognition.

        Args:
            audio_chunk: Float32 audio samples at original sample rate

        Returns:
            Recognition result or None
        """
        # Resample to 16 kHz if needed (Vosk model expects 16 kHz)
        if self.sample_rate != 16000:
            audio_chunk = self._resample_to_16k(audio_chunk, self.sample_rate)
        
        if self.recognition_mode == "wake":
            return self._process_wake_chunk(audio_chunk)
        else:
            return self._process_general_chunk(audio_chunk)

    def _process_wake_chunk(self, audio_chunk: np.ndarray) -> Optional[Dict[str, Any]]:
        """Process audio chunk for wake word detection."""
        if not self.wake_rec:
            return None

        # Energy gate - skip low energy chunks
        rms = self._rms16(audio_chunk)
        if rms < self.wake_rms_min:
            return None

        # Convert float32 to int16 bytes for Vosk
        audio_int16 = (audio_chunk * 32767).astype(np.int16)
        audio_bytes = audio_int16.tobytes()

        # Process with Vosk
        try:
            if self.wake_rec.AcceptWaveform(audio_bytes):
                result = json.loads(self.wake_rec.Result())
                text = (result.get("text", "") or "").lower().strip()
                
                if text:
                    avg_conf = self._avg_conf(result)
                    print(f"[vosk-process] Wake final: '{text}' (conf={avg_conf:.2f}, rms={rms})")

                    # Fuzzy wake word matching with timing controls
                    is_match, score, phrase = self._fuzzy_wake_match(
                        text, self.wake_phrases, self.fuzzy_threshold
                    )
                    
                    now_ms = time.monotonic() * 1000
                    
                    if (is_match and 
                        avg_conf >= self.wake_conf_min and
                        (now_ms - self.last_wake_ms) > self.wake_cooldown_ms):
                        
                        self.last_wake_ms = now_ms
                        print(f"[vosk-process] WAKE DETECTED: '{phrase}' (score={score:.2f})")
                        
                        # Auto-switch to general mode after wake detection
                        self.recognition_mode = "general"
                        print(f"[vosk-process] Switched to general recognition mode")
                        
                        return {
                            "type": "wake_detected",
                            "text": text,
                            "matched_phrase": phrase,
                            "confidence": avg_conf,
                            "fuzzy_score": score,
                            "rms": rms,
                            "timestamp": now_ms
                        }
            else:
                # Handle partial results
                partial = json.loads(self.wake_rec.PartialResult()).get("partial", "")
                if partial and len(partial) > 2:
                    print(f"[vosk-process] Wake partial: '{partial}'")

        except Exception as e:
            print(f"[vosk-process] Wake recognition error: {e}")

        return None

    def _process_general_chunk(self, audio_chunk: np.ndarray) -> Optional[Dict[str, Any]]:
        """Process audio chunk for general speech recognition."""
        if not self.general_rec:
            return None

        # Convert float32 to int16 bytes for Vosk
        audio_int16 = (audio_chunk * 32767).astype(np.int16)
        audio_bytes = audio_int16.tobytes()

        try:
            if self.general_rec.AcceptWaveform(audio_bytes):
                result = json.loads(self.general_rec.Result())
                text = (result.get("text", "") or "").strip()
                
                if text:
                    avg_conf = self._avg_conf(result)
                    print(f"[vosk-process] General final: '{text}' (conf={avg_conf:.2f})")
                    
                    # Auto-switch back to wake mode after recognizing speech
                    self.recognition_mode = "wake"
                    print(f"[vosk-process] Switched back to wake mode")
                    
                    return {
                        "type": "speech_recognized",
                        "text": text,
                        "confidence": avg_conf,
                        "timestamp": time.monotonic() * 1000
                    }
            else:
                # Handle partial results for general recognition
                partial = json.loads(self.general_rec.PartialResult()).get("partial", "")
                if partial:
                    return {
                        "type": "partial_recognition",
                        "text": partial,
                        "timestamp": time.monotonic() * 1000
                    }

        except Exception as e:
            print(f"[vosk-process] General recognition error: {e}")

        return None

    def run(self):
        """Main process loop - reads audio from shared buffer and processes it."""
        print("[vosk-process] Starting Vosk recognition process")
        
        # Load Vosk model
        if not self.load_vosk_model():
            print("[vosk-process] Failed to load Vosk model, exiting")
            self.ipc.send_status("error", {"message": "Failed to load Vosk model"})
            return
        self.ipc.send_status("ready", {"message": "Vosk process ready"})
        self.running = True
        
        # Audio processing parameters
        chunk_ms = 30  # Process 30ms chunks
        chunk_samples = int(chunk_ms * self.sample_rate / 1000.0)
        last_heartbeat = time.monotonic()
        print(f"[DEBUG] About to print loop start, heartbeat_interval={self.ipc.heartbeat_interval}")
        print(f"[vosk-process] Starting recognition loop, heartbeat_interval={self.ipc.heartbeat_interval}")
        
        try:
            while self.running:
                # Send heartbeat periodically
                current_time = time.monotonic()
                if current_time - last_heartbeat >= self.ipc.heartbeat_interval:
                    self.ipc.heartbeat()
                    print(f"[vosk-process] Sent heartbeat at {current_time:.1f}")
                    last_heartbeat = current_time

                # Check for commands
                # Check for commands
                cmd = self.ipc.get_command(timeout=0.01)
                if cmd and len(cmd) == 3:
                    cmd_type, data, timestamp = cmd
                    self._handle_command(cmd_type, data)
                elif cmd:
                    self._handle_command(cmd_type, data)

                # Read audio from shared buffer
                audio_chunk = self.ipc.ring_buffer.read(chunk_samples)
                if audio_chunk is None:
                    time.sleep(0.001)  # Small sleep if no audio available
                    continue

                # Process the audio chunk
                result = self.process_audio_chunk(audio_chunk)
                if result:
                    # Send recognition result back to main process
                    self.ipc.send_status("recognition", result)

        except KeyboardInterrupt:
            print("[vosk-process] Interrupted by user")
        except Exception as e:
            print(f"[vosk-process] Fatal error: {e}")
            import traceback
            traceback.print_exc()
            self.ipc.send_status("error", {"message": f"Fatal error: {e}"})
            self.ipc.send_status("error", {"message": f"Fatal error: {e}"})
        finally:
            self.running = False
            print("[vosk-process] Vosk recognition process stopped")

    def _handle_command(self, cmd_type: str, data: Any):
        """Handle commands from main process."""
        if cmd_type == "shutdown":
            print("[vosk-process] Received shutdown command")
            self.running = False
            
        elif cmd_type == "set_mode":
            mode = data.get("mode", "wake")
            if mode in ["wake", "general"]:
                self.recognition_mode = mode
                print(f"[vosk-process] Recognition mode set to: {mode}")
                
                # Reset recognizers for clean state
                if self.model:
                    if mode == "wake":
                        self.wake_rec = vosk.KaldiRecognizer(self.model, 16000, self.wake_grammar)  # Model trained at 16 kHz
                    else:
                        self.general_rec = vosk.KaldiRecognizer(self.model, 16000)  # Model trained at 16 kHz
                        
        elif cmd_type == "update_wake_config":
            self.update_wake_config(data)
            
        elif cmd_type == "reset_recognizers":
            if self.model:
                self.general_rec = vosk.KaldiRecognizer(self.model, 16000)  # Model trained at 16 kHz
                self.wake_rec = vosk.KaldiRecognizer(self.model, 16000, self.wake_grammar)  # Model trained at 16 kHz
                print("[vosk-process] Recognizers reset")


def run_vosk_process(ipc_shared_mem_name: str, sample_rate: int = 48000):
    """Entry point for Vosk recognition process.

    Args:
        ipc_shared_mem_name: Name of shared memory block for IPC
        sample_rate: Audio sample rate
    """
    print(f"[vosk-process] Starting with shared memory: {ipc_shared_mem_name}")
    
    # Create IPC connection using existing shared memory
    # Note: This is a simplified interface - in practice, we'd pass the shared memory name
    # and recreate the IPC object to connect to existing shared resources
    try:
        # For now, create a new IPC instance (this would need to be modified to 
        # connect to existing shared memory)
        ipc = AudioProcessIPC(buffer_seconds=2.0, sample_rate=sample_rate)
        
        # Create and run the recognizer
        recognizer = VoskRecognizer(ipc, sample_rate)
        recognizer.run()
        
    except Exception as e:
        print(f"[vosk-process] Failed to start: {e}")
    finally:
        print("[vosk-process] Process terminated")


if __name__ == "__main__":
    # For testing - in production this would be called by the main process
    if len(sys.argv) > 1:
        shared_mem_name = sys.argv[1]
        sample_rate = int(sys.argv[2]) if len(sys.argv) > 2 else 48000
        run_vosk_process(shared_mem_name, sample_rate)
    else:
        print("Usage: python vosk_process.py <shared_mem_name> [sample_rate]")
