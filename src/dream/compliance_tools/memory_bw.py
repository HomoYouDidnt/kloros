"""Safe memory bandwidth test (bounded size/time) - D-REAM compliant."""
from __future__ import annotations
import time

def measure_memory_bandwidth(seconds: float = 5.0) -> dict:
    """Measure memory bandwidth using bounded numpy operations.
    
    Args:
        seconds: Maximum time budget for test
        
    Returns:
        dict with 'bandwidth_gb_s' key
    """
    try:
        import numpy as np
        
        # Bounded array size: 256MB
        size_mb = 256
        size_bytes = size_mb * 1024 * 1024
        a = np.ones(size_bytes // 8, dtype='float64')
        b = np.zeros_like(a)
        
        # Run for specified time budget
        start_time = time.perf_counter()
        iterations = 0
        total_bytes = 0
        
        while (time.perf_counter() - start_time) < seconds:
            t0 = time.perf_counter()
            b[:] = a  # Memory copy operation
            t1 = time.perf_counter()
            
            elapsed = t1 - t0
            if elapsed > 0:
                total_bytes += size_bytes
                iterations += 1
        
        total_time = time.perf_counter() - start_time
        
        if total_time > 0 and iterations > 0:
            bandwidth_gb_s = (total_bytes / 1e9) / total_time
            return {
                'bandwidth_gb_s': bandwidth_gb_s,
                'iterations': iterations,
                'total_time_s': total_time
            }
        else:
            return {'bandwidth_gb_s': 50.0, 'error': 'insufficient_iterations'}
            
    except Exception as e:
        return {'bandwidth_gb_s': 50.0, 'error': str(e)}
