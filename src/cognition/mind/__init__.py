"""
KLoROS Mind - The Complete Cognitive Layer

Contains all mental faculties:
- cognition/     - Thinking, reasoning, curiosity, tools
- consciousness/ - Feeling, affect, interoception
- reflection/    - Self-examination, idle analysis
- memory/        - Storage, retrieval, KOSMOS
"""

from src.cognition.mind import cognition
from src.cognition.mind import consciousness
from src.cognition.mind import reflection
from src.cognition.mind import memory

__all__ = ["cognition", "consciousness", "reflection", "memory"]
