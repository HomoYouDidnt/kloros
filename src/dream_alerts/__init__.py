"""
D-REAM Alert System Package
Multi-modal notification system for evolutionary improvements.
"""

__version__ = "1.0.0"
__author__ = "KLoROS D-REAM Development Team"

from .alert_manager import DreamAlertManager
from .alert_methods import AlertMethod, AlertResult, ImprovementAlert
from .alert_preferences import UserAlertPreferences

__all__ = [
    'DreamAlertManager',
    'AlertMethod',
    'AlertResult',
    'ImprovementAlert',
    'UserAlertPreferences'
]