"""Reflexion schemas for critic feedback."""
from typing import Dict, Any, List, Optional
from dataclasses import dataclass


@dataclass
class CriticNote:
    """Critique note from reflexion critic."""
    diagnosis: str
    suggested_fix: str
    confidence: float
    safety_flags: List[str]
    bullet_candidate: Optional[str] = None


def as_note(
    diagnosis: str,
    fix: str,
    confidence: float,
    safety_flags: Optional[List[str]] = None,
    bullet_candidate: Optional[str] = None
) -> Dict[str, Any]:
    """Create a critic note dict.

    Args:
        diagnosis: Diagnosis of the issue
        fix: Suggested fix
        confidence: Confidence in the critique (0-1)
        safety_flags: Optional safety flags
        bullet_candidate: Optional ACE bullet candidate

    Returns:
        Critic note dict
    """
    return {
        "diagnosis": diagnosis,
        "suggested_fix": fix,
        "confidence": confidence,
        "safety_flags": safety_flags or [],
        "bullet_candidate": bullet_candidate
    }
