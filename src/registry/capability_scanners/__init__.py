"""
Capability scanner registry.

Auto-discovers scanner classes from this package.
"""

from .base import CapabilityGap, ScannerMetadata, CapabilityScanner
from .pypi_scanner import PyPIScanner
from .inference_performance_scanner import InferencePerformanceScanner

__all__ = [
    'CapabilityGap',
    'ScannerMetadata',
    'CapabilityScanner',
    'PyPIScanner',
    'InferencePerformanceScanner'
]
