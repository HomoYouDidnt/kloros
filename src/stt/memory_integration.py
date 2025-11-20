"""Memory integration for hybrid ASR corrections."""

from __future__ import annotations

import time
from typing import Optional, Dict, List

try:
    from ..kloros_memory.logger import MemoryLogger
    from ..kloros_memory.models import EventType
    MEMORY_AVAILABLE = True
except ImportError:
    MEMORY_AVAILABLE = False


class ASRMemoryLogger:
    """Logger for ASR corrections and learning data."""
    
    def __init__(self, enable_logging: bool = True):
        """Initialize ASR memory logger.
        
        Args:
            enable_logging: Whether to enable memory logging
        """
        self.enable_logging = enable_logging and MEMORY_AVAILABLE
        self.memory_logger = None
        
        if self.enable_logging:
            try:
                self.memory_logger = MemoryLogger()
                print("✅ ASR Memory logging enabled")
            except Exception as e:
                print(f"⚠️ ASR Memory logging disabled: {e}")
                self.enable_logging = False
    
    def log_correction(
        self,
        vosk_transcript: str,
        whisper_transcript: str,
        similarity_score: float,
        confidence_vosk: float,
        confidence_whisper: float,
        correction_applied: bool,
        correction_reason: str,
    ):
        """Log an ASR correction event.
        
        Args:
            vosk_transcript: Original VOSK transcript
            whisper_transcript: Whisper transcript (potential correction)
            similarity_score: Similarity score between transcripts
            confidence_vosk: VOSK confidence score
            confidence_whisper: Whisper confidence score
            correction_applied: Whether correction was applied
            correction_reason: Reason for correction decision
        """
        if not self.enable_logging or not self.memory_logger:
            return
            
        try:
            metadata = {
                "asr_type": "correction",
                "vosk_transcript": vosk_transcript,
                "whisper_transcript": whisper_transcript,
                "similarity_score": similarity_score,
                "confidence_vosk": confidence_vosk,
                "confidence_whisper": confidence_whisper,
                "correction_applied": correction_applied,
                "correction_reason": correction_reason,
                "timestamp": time.time(),
            }
            
            # Create event description
            if correction_applied:
                event_text = f"ASR Correction: '{vosk_transcript}' → '{whisper_transcript}' (similarity: {similarity_score:.3f})"
            else:
                event_text = f"ASR No Correction: '{vosk_transcript}' (similarity: {similarity_score:.3f}, kept VOSK)"
            
            # Log the correction event
            self.memory_logger.log_event(
                event_type=EventType.STT_TRANSCRIPTION,
                content=event_text,
                metadata=metadata
            )
            
        except Exception as e:
            print(f"⚠️ Error logging ASR correction: {e}")
    
    def log_confidence_boost(
        self,
        transcript: str,
        original_confidence: float,
        boosted_confidence: float,
        similarity_score: float,
        boost_reason: str,
    ):
        """Log a confidence boost event.
        
        Args:
            transcript: The transcript that received a boost
            original_confidence: Original confidence score
            boosted_confidence: Boosted confidence score
            similarity_score: Similarity score that triggered boost
            boost_reason: Reason for confidence boost
        """
        if not self.enable_logging or not self.memory_logger:
            return
            
        try:
            metadata = {
                "asr_type": "confidence_boost",
                "transcript": transcript,
                "original_confidence": original_confidence,
                "boosted_confidence": boosted_confidence,
                "similarity_score": similarity_score,
                "boost_reason": boost_reason,
                "boost_factor": boosted_confidence / original_confidence,
                "timestamp": time.time(),
            }
            
            event_text = f"ASR Confidence Boost: '{transcript}' ({original_confidence:.3f} → {boosted_confidence:.3f})"
            
            self.memory_logger.log_event(
                event_type=EventType.STT_TRANSCRIPTION,
                content=event_text,
                metadata=metadata
            )
            
        except Exception as e:
            print(f"⚠️ Error logging confidence boost: {e}")
    
    def get_correction_patterns(self, days: int = 7) -> List[Dict]:
        """Get recent correction patterns for analysis.
        
        Args:
            days: Number of days to look back
            
        Returns:
            List of correction pattern data
        """
        if not self.enable_logging or not self.memory_logger:
            return []
            
        try:
            # This would require implementing a query method in the memory system
            # For now, return empty list as placeholder
            return []
        except Exception as e:
            print(f"⚠️ Error getting correction patterns: {e}")
            return []
    
    def get_accuracy_trends(self, days: int = 30) -> Dict:
        """Get accuracy trends over time.
        
        Args:
            days: Number of days to analyze
            
        Returns:
            Dictionary with accuracy trend data
        """
        if not self.enable_logging or not self.memory_logger:
            return {}
            
        try:
            # Placeholder for future implementation
            return {
                "total_corrections": 0,
                "correction_rate": 0.0,
                "average_similarity": 0.0,
                "trends": [],
            }
        except Exception as e:
            print(f"⚠️ Error getting accuracy trends: {e}")
            return {}


class AdaptiveThresholdManager:
    """Manages adaptive threshold adjustment based on memory data."""
    
    def __init__(self, memory_logger: Optional[ASRMemoryLogger] = None):
        """Initialize adaptive threshold manager.
        
        Args:
            memory_logger: ASR memory logger instance
        """
        self.memory_logger = memory_logger
        self.adjustment_history = []
    
    def suggest_threshold_adjustment(
        self, 
        current_threshold: float,
        recent_corrections: List[Dict],
        target_correction_rate: float = 0.15,
    ) -> Optional[float]:
        """Suggest threshold adjustment based on recent performance.
        
        Args:
            current_threshold: Current correction threshold
            recent_corrections: Recent correction data
            target_correction_rate: Target correction rate (0.0-1.0)
            
        Returns:
            Suggested new threshold, or None if no change needed
        """
        if not recent_corrections:
            return None
            
        try:
            # Calculate current correction rate
            total_transcriptions = len(recent_corrections)
            corrections_applied = sum(1 for c in recent_corrections if c.get("correction_applied", False))
            current_rate = corrections_applied / total_transcriptions if total_transcriptions > 0 else 0.0
            
            # Determine if adjustment is needed
            rate_diff = current_rate - target_correction_rate
            
            if abs(rate_diff) < 0.05:  # Within 5% tolerance
                return None
            
            # Calculate adjustment
            if rate_diff > 0:  # Too many corrections, raise threshold
                adjustment = min(0.1, rate_diff * 0.5)
                new_threshold = min(1.0, current_threshold + adjustment)
            else:  # Too few corrections, lower threshold
                adjustment = min(0.1, abs(rate_diff) * 0.5)
                new_threshold = max(0.0, current_threshold - adjustment)
            
            # Record adjustment suggestion
            self.adjustment_history.append({
                "timestamp": time.time(),
                "old_threshold": current_threshold,
                "new_threshold": new_threshold,
                "correction_rate": current_rate,
                "target_rate": target_correction_rate,
                "adjustment": new_threshold - current_threshold,
            })
            
            return new_threshold
            
        except Exception as e:
            print(f"⚠️ Error calculating threshold adjustment: {e}")
            return None
    
    def get_adjustment_history(self, limit: int = 10) -> List[Dict]:
        """Get recent threshold adjustment history.
        
        Args:
            limit: Maximum number of adjustments to return
            
        Returns:
            List of recent adjustment records
        """
        return self.adjustment_history[-limit:]
