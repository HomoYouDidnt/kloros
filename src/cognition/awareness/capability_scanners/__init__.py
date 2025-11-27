"""
Capability scanner registry.

Auto-discovers scanner classes from this package.
"""

from .base import CapabilityGap, ScannerMetadata, CapabilityScanner
from .pypi_scanner import PyPIScanner
from .inference_performance_scanner import InferencePerformanceScanner
from .context_utilization_scanner import ContextUtilizationScanner
from .resource_profiler_scanner import ResourceProfilerScanner
from .bottleneck_detector_scanner import BottleneckDetectorScanner
from .comparative_analyzer_scanner import ComparativeAnalyzerScanner

__all__ = [
    'CapabilityGap',
    'ScannerMetadata',
    'CapabilityScanner',
    'PyPIScanner',
    'InferencePerformanceScanner',
    'ContextUtilizationScanner',
    'ResourceProfilerScanner',
    'BottleneckDetectorScanner',
    'ComparativeAnalyzerScanner'
]
