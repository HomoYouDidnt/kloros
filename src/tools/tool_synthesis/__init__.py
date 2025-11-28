"""
Tool Synthesis System for KLoROS

Enables autonomous tool creation and capability expansion.
"""

from .synthesizer import ToolSynthesizer
from .templates import ToolTemplateEngine
from .validator import ToolValidator
from .storage import SynthesizedToolStorage

__version__ = "1.0.0"
__all__ = [
    "ToolSynthesizer",
    "ToolTemplateEngine", 
    "ToolValidator",
    "SynthesizedToolStorage"
]
