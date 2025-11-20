"""Hybrid VOSK-Whisper STT backend with real-time feedback loop."""

from __future__ import annotations

import asyncio
import threading
import queue
import time
from typing import Optional, Tuple, Union

import numpy as np
from rapidfuzz import fuzz
from concurrent.futures import ThreadPoolExecutor

from .memory_integration import ASRMemoryLogger, AdaptiveThresholdManager

from .base import SttResult
from .vosk_backend_streaming import VoskSttBackend
from .whisper_backend import WhisperSttBackend


class HybridSttBackend:
    """Hybrid STT backend combining VOSK speed with Whisper accuracy."""

    def __init__(
        self,
        vosk_model_dir: Optional[str] = None,
        whisper_model_size: str = "small",
        whisper_device: str = "auto",
        whisper_device_index: Union[int, list] = 0,
        correction_threshold: float = 0.75,
        confidence_boost_threshold: float = 0.9,
        enable_corrections: bool = True,
        **kwargs,
    ):
        """Initialize hybrid STT backend.

        Args:
            vosk_model_dir: VOSK model directory
            whisper_model_size: Whisper model size
            whisper_device: Whisper device ("auto", "cuda", "cpu")
            whisper_device_index: GPU device index for Whisper
            correction_threshold: Similarity threshold for corrections (0.0-1.0)
            confidence_boost_threshold: Confidence threshold for trust boosting
            enable_corrections: Whether to enable Whisper corrections
            **kwargs: Additional arguments
        """
        # Initialize both backends
        self.vosk_backend = VoskSttBackend(model_dir=vosk_model_dir)
        
        self.whisper_backend = WhisperSttBackend(
            model_size=whisper_model_size,
            device=whisper_device,
            device_index=whisper_device_index,
        )

        # Configuration
        self.correction_threshold = correction_threshold
        self.confidence_boost_threshold = confidence_boost_threshold
        self.enable_corrections = enable_corrections

        # Statistics tracking
        self.stats = {
            "total_transcriptions": 0,
            "corrections_applied": 0,
            "confidence_boosts": 0,
            "vosk_wins": 0,
            "whisper_wins": 0,
        }

        # Correction history for learning
        self.correction_history = []

        # Initialize memory integration
        self.memory_logger = ASRMemoryLogger(enable_logging=True)
        self.threshold_manager = AdaptiveThresholdManager(self.memory_logger)

        # Lock for thread-safe audio buffer access
        self._audio_buffer_lock = threading.Lock()

    def transcribe(
        self, audio: np.ndarray, sample_rate: int, lang: Optional[str] = None
    ) -> SttResult:
        """Transcribe audio using hybrid VOSK-Whisper approach.

        Args:
            audio: Audio samples as float32 mono array in range [-1, 1]
            sample_rate: Sample rate in Hz
            lang: Language code (optional)

        Returns:
            SttResult with the best transcript and metadata
        """
        self.stats["total_transcriptions"] += 1

        # Step 1: Get immediate VOSK result (fast path)
        vosk_result = self.vosk_backend.transcribe(audio, sample_rate, lang)

        # If corrections are disabled, return VOSK result immediately
        if not self.enable_corrections:
            self.stats["vosk_wins"] += 1
            return vosk_result

        # Step 2: Get Whisper result (accurate path)
        whisper_result = self.whisper_backend.transcribe(audio, sample_rate, lang)

        # Step 3: Apply hybrid logic to determine best result
        final_result = self._apply_hybrid_logic(vosk_result, whisper_result, audio)

        return final_result

    def _apply_hybrid_logic(
        self, vosk_result: SttResult, whisper_result: SttResult, audio: np.ndarray
    ) -> SttResult:
        """Apply hybrid logic to combine VOSK and Whisper results.

        Args:
            vosk_result: VOSK transcription result
            whisper_result: Whisper transcription result
            audio: Original audio for metadata

        Returns:
            Best combined result
        """
        vosk_text = vosk_result.transcript.strip().lower()
        whisper_text = whisper_result.transcript.strip().lower()

        # Calculate similarity between transcripts
        similarity = fuzz.ratio(vosk_text, whisper_text) / 100.0

        # Decision logic
        if similarity >= self.correction_threshold:
            # Transcripts are similar - boost confidence and prefer higher confidence
            if whisper_result.confidence > vosk_result.confidence:
                result = self._create_boosted_result(whisper_result, similarity, "whisper_confidence")
                self.stats["whisper_wins"] += 1
            else:
                result = self._create_boosted_result(vosk_result, similarity, "vosk_confidence")
                self.stats["vosk_wins"] += 1
        else:
            # Transcripts differ significantly - apply correction logic
            if whisper_result.confidence > self.confidence_boost_threshold:
                # High-confidence Whisper correction
                result = self._create_correction_result(
                    whisper_result, vosk_result, similarity, "whisper_correction"
                )
                self.stats["corrections_applied"] += 1
                self.stats["whisper_wins"] += 1
                
                # Log correction for learning
                self._log_correction(vosk_text, whisper_text, similarity)
            else:
                # Low confidence - prefer VOSK for responsiveness
                result = vosk_result
                self.stats["vosk_wins"] += 1

        return result

    def _create_boosted_result(
        self, base_result: SttResult, similarity: float, reason: str
    ) -> SttResult:
        """Create a confidence-boosted result.

        Args:
            base_result: Base STT result
            similarity: Similarity score between transcripts
            reason: Reason for confidence boost

        Returns:
            Boosted STT result
        """
        # Boost confidence based on similarity
        boosted_confidence = min(1.0, base_result.confidence * (1.0 + similarity * 0.2))
        
        self.stats["confidence_boosts"] += 1

        # Log confidence boost to memory
        self.memory_logger.log_confidence_boost(
            transcript=base_result.transcript,
            original_confidence=base_result.confidence,
            boosted_confidence=boosted_confidence,
            similarity_score=similarity,
            boost_reason=reason,
        )

        return SttResult(
            transcript=base_result.transcript,
            confidence=boosted_confidence,
            lang=base_result.lang,
            raw={
                **base_result.raw,
                "hybrid_info": {
                    "method": "confidence_boost",
                    "reason": reason,
                    "original_confidence": base_result.confidence,
                    "similarity": similarity,
                    "boost_factor": boosted_confidence / base_result.confidence,
                },
            },
        )

    def _create_correction_result(
        self, 
        whisper_result: SttResult, 
        vosk_result: SttResult, 
        similarity: float, 
        reason: str
    ) -> SttResult:
        """Create a correction result using Whisper to correct VOSK.

        Args:
            whisper_result: Whisper transcription result
            vosk_result: VOSK transcription result
            similarity: Similarity score between transcripts
            reason: Reason for correction

        Returns:
            Corrected STT result
        """
        return SttResult(
            transcript=whisper_result.transcript,
            confidence=whisper_result.confidence,
            lang=whisper_result.lang,
            raw={
                **whisper_result.raw,
                "hybrid_info": {
                    "method": "correction",
                    "reason": reason,
                    "original_transcript": vosk_result.transcript,
                    "original_confidence": vosk_result.confidence,
                    "similarity": similarity,
                    "correction_applied": True,
                },
            },
        )

    def _log_correction(self, vosk_text: str, whisper_text: str, similarity: float):
        """Log a correction for learning purposes.

        Args:
            vosk_text: Original VOSK transcript
            whisper_text: Corrected Whisper transcript
            similarity: Similarity score
        """
        correction_entry = {
            "timestamp": time.time(),
            "vosk_text": vosk_text,
            "whisper_text": whisper_text,
            "similarity": similarity,
        }
        
        self.correction_history.append(correction_entry)

        # Log correction to memory
        self.memory_logger.log_correction(
            vosk_transcript=vosk_text,
            whisper_transcript=whisper_text,
            similarity_score=similarity,
            confidence_vosk=0.0,  # Will be updated in calling method
            confidence_whisper=0.0,  # Will be updated in calling method
            correction_applied=True,
            correction_reason="similarity_threshold",
        )
        
        # Keep only recent corrections (last 100)
        if len(self.correction_history) > 100:
            self.correction_history = self.correction_history[-100:]

    def get_stats(self) -> dict:
        """Get hybrid backend statistics.

        Returns:
            Dictionary with performance statistics
        """
        total = self.stats["total_transcriptions"]
        if total == 0:
            return self.stats

        return {
            **self.stats,
            "correction_rate": self.stats["corrections_applied"] / total,
            "confidence_boost_rate": self.stats["confidence_boosts"] / total,
            "vosk_win_rate": self.stats["vosk_wins"] / total,
            "whisper_win_rate": self.stats["whisper_wins"] / total,
        }

    def get_recent_corrections(self, limit: int = 10) -> list:
        """Get recent corrections for analysis.

        Args:
            limit: Maximum number of corrections to return

        Returns:
            List of recent correction entries
        """
        return self.correction_history[-limit:]

    def update_thresholds(
        self, 
        correction_threshold: Optional[float] = None,
        confidence_boost_threshold: Optional[float] = None
    ):
        """Update correction thresholds for adaptive tuning.

        Args:
            correction_threshold: New similarity threshold for corrections
            confidence_boost_threshold: New confidence threshold for trust boosting
        """
        if correction_threshold is not None:
            self.correction_threshold = max(0.0, min(1.0, correction_threshold))
        
        if confidence_boost_threshold is not None:
            self.confidence_boost_threshold = max(0.0, min(1.0, confidence_boost_threshold))

    def get_info(self) -> dict:
        """Get backend information.

        Returns:
            Dictionary with backend details
        """
        return {
            "backend": "hybrid",
            "vosk_info": self.vosk_backend.get_info() if hasattr(self.vosk_backend, 'get_info') else {},
            "whisper_info": self.whisper_backend.get_info(),
            "correction_threshold": self.correction_threshold,
            "confidence_boost_threshold": self.confidence_boost_threshold,
            "enable_corrections": self.enable_corrections,
            "stats": self.get_stats(),
        }

    # ======================== PHASE 3: STREAMING METHODS ========================

    def start_streaming(self, sample_rate: int = 16000) -> None:
        """Start hybrid streaming transcription mode.

        Initializes VOSK for real-time feedback and prepares Whisper audio accumulation.

        Args:
            sample_rate: Audio sample rate in Hz
        """
        # Start VOSK streaming for immediate feedback
        if hasattr(self.vosk_backend, 'start_streaming'):
            self.vosk_backend.start_streaming(sample_rate)
        else:
            raise RuntimeError("VOSK backend does not support streaming")

        # Initialize Whisper audio accumulation
        self._streaming_audio_chunks = []
        self._streaming_sample_rate = sample_rate
        self._streaming_mode = True

        print("🎯 Hybrid streaming transcription started (VOSK + Whisper)", flush=True)

    def stream_chunk(self, audio_chunk: np.ndarray) -> str:
        """Process audio chunk with hybrid streaming approach.

        Sends chunk to VOSK for immediate partial transcription while accumulating
        audio for later Whisper validation.

        Args:
            audio_chunk: Audio samples as float32 mono array

        Returns:
            Current partial transcript from VOSK
        """
        if not self._streaming_mode:
            raise RuntimeError("Streaming mode not initialized - call start_streaming() first")

        # 1. Send chunk to VOSK for immediate feedback
        partial_transcript = ""
        if hasattr(self.vosk_backend, 'stream_chunk'):
            partial_transcript = self.vosk_backend.stream_chunk(audio_chunk)

        # 2. Accumulate audio chunk for later Whisper processing (thread-safe)
        with self._audio_buffer_lock:
            self._streaming_audio_chunks.append(audio_chunk.copy())

        # 3. Show hybrid processing indicator
        if partial_transcript:
            print(f"🎯 {partial_transcript}...", end="\r", flush=True)

        return partial_transcript

    def end_streaming(self) -> SttResult:
        """End streaming mode and return hybrid result.

        Finalizes VOSK streaming and processes accumulated audio with Whisper IN PARALLEL.
        Handles Whisper errors gracefully with fallback to VOSK-only result.

        Returns:
            Best combined result with detailed streaming metadata
        """
        if not self._streaming_mode:
            raise RuntimeError("Streaming mode not active")

        # Prevent new chunks from being accepted during finalization
        self._streaming_mode = False

        try:
            # 1. Snapshot audio buffer under lock (prevents race with stream_chunk)
            with self._audio_buffer_lock:
                audio_snapshot = self._streaming_audio_chunks.copy()
                audio_sample_rate = self._streaming_sample_rate

            # 2. Define worker functions for parallel execution
            def get_vosk_result():
                """Finalize VOSK streaming transcription."""
                if hasattr(self.vosk_backend, 'end_streaming'):
                    return self.vosk_backend.end_streaming()
                else:
                    partial = self.vosk_backend.get_partial_result() if hasattr(self.vosk_backend, 'get_partial_result') else ""
                    return SttResult(
                        transcript=partial,
                        confidence=0.8,
                        lang="en",
                        raw={"source": "vosk_streaming_fallback"}
                    )

            def get_whisper_result():
                """Transcribe accumulated audio with Whisper."""
                if not self.enable_corrections or not audio_snapshot:
                    return None

                full_audio = np.concatenate(audio_snapshot)

                try:
                    result = self.whisper_backend.transcribe(
                        full_audio,
                        audio_sample_rate,
                        lang=None
                    )
                    return result
                except Exception as e:
                    return ("ERROR", str(e))

            # 3. Execute VOSK and Whisper in parallel
            vosk_result = None
            whisper_result = None
            whisper_error = None

            with ThreadPoolExecutor(max_workers=2) as executor:
                vosk_future = executor.submit(get_vosk_result)
                whisper_future = executor.submit(get_whisper_result) if self.enable_corrections else None

                # Wait for VOSK (always needed)
                vosk_result = vosk_future.result()
                print(f"\nVOSK final: {vosk_result.transcript}", flush=True)

                # Wait for Whisper if launched
                if whisper_future:
                    whisper_result_or_error = whisper_future.result()

                    if isinstance(whisper_result_or_error, tuple) and whisper_result_or_error[0] == "ERROR":
                        whisper_error = whisper_result_or_error[1]
                        print(f"Whisper transcription failed: {whisper_error}", flush=True)
                        print("Falling back to VOSK-only result", flush=True)
                    else:
                        whisper_result = whisper_result_or_error
                        print(f"Whisper final: {whisper_result.transcript}", flush=True)

            # 4. Apply hybrid logic if Whisper succeeded
            if whisper_result is not None:
                full_audio = np.concatenate(audio_snapshot)
                final_result = self._apply_hybrid_logic(vosk_result, whisper_result, full_audio)
                final_result.raw["streaming_info"] = {
                    "vosk_transcript": vosk_result.transcript,
                    "whisper_transcript": whisper_result.transcript,
                    "chunks_processed": len(audio_snapshot),
                    "total_audio_seconds": len(full_audio) / audio_sample_rate,
                    "mode": "hybrid_streaming_parallel"
                }
            else:
                # Whisper failed or disabled - use VOSK result
                final_result = vosk_result
                final_result.raw["streaming_info"] = {
                    "vosk_transcript": vosk_result.transcript,
                    "whisper_error": whisper_error,
                    "chunks_processed": len(audio_snapshot),
                    "mode": "vosk_fallback" if whisper_error else "vosk_streaming_only",
                    "corrections_enabled": self.enable_corrections
                }

            print(f"Final hybrid result: {final_result.transcript} (confidence: {final_result.confidence:.2f})", flush=True)

            # 5. Update stats
            self.stats["total_transcriptions"] += 1

            return final_result

        finally:
            # Cleanup streaming state (always runs)
            with self._audio_buffer_lock:
                self._streaming_audio_chunks = []
            self._streaming_sample_rate = None

    def get_partial_result(self) -> str:
        """Get current partial transcript from VOSK streaming."""
        if hasattr(self.vosk_backend, 'get_partial_result'):
            return self.vosk_backend.get_partial_result()
        return ""

    def get_confidence(self) -> float:
        """Get current confidence score from VOSK streaming backend."""
        if hasattr(self.vosk_backend, 'get_confidence'):
            return self.vosk_backend.get_confidence()
        return 0.8  # Default fallback confidence
