#!/usr/bin/env python3
"""
Tool Domain Evaluator for D-REAM
Evolves KLoROS tools through empirical testing and genetic programming.
"""

import os
import sys
import json
import time
import logging
import subprocess
import tempfile
import traceback
from typing import Dict, List, Any, Tuple, Optional
from pathlib import Path
import numpy as np

# Add dream path for absolute imports
sys.path.insert(0, '/home/kloros/src/dream')
from domains.domain_evaluator_base import DomainEvaluator

logger = logging.getLogger(__name__)


class ToolDomainEvaluator(DomainEvaluator):
    """Evaluates and optimizes KLoROS tool implementations."""

    def __init__(self):
        super().__init__("tool")
        self.tools_dir = Path("/home/kloros/src/tools")
        self.test_data_dir = Path("/home/kloros/artifacts/dream/tool_test_data")
        self.test_data_dir.mkdir(parents=True, exist_ok=True)

        # Available tools to evolve
        self.evolvable_tools = [
            "latency_jitter",
            "noise_floor",
            "clip_scan",
            "asr_wer",
        ]

        # Update tools dir to actual location
        self.tools_dir = Path("/home/kloros/tools/audio")

        # Test scenarios for each tool
        self.test_scenarios = self._load_test_scenarios()

        # Current tool being evaluated (set by apply_configuration)
        self.current_tool_name = None
        self.current_tool_code = None

    def _load_test_scenarios(self) -> Dict[str, List[Dict]]:
        """Load test scenarios for tool evaluation."""
        # Match actual tool names in evolvable_tools list
        return {
            "latency_jitter": [
                {"name": "basic_test", "args": {}, "expected_keys": ["jitter_ms", "avg_latency"]},
            ],
            "noise_floor": [
                {"name": "basic_test", "args": {}, "expected_keys": ["noise_db", "snr"]},
            ],
            "clip_scan": [
                {"name": "basic_test", "args": {}, "expected_keys": ["clips_found", "clip_rate"]},
            ],
            "asr_wer": [
                {"name": "basic_test", "args": {}, "expected_keys": ["wer", "word_count"]},
            ],
        }

    def get_genome_spec(self) -> Dict[str, Tuple[Any, Any, Any]]:
        """
        Get tool genome specification.

        For tool evolution, we use categorical parameters representing
        different code variants/mutations rather than continuous values.
        """
        return {
            # Which tool to evolve
            'tool_idx': (0, len(self.evolvable_tools) - 1, 1),

            # Mutation toggles (binary features)
            'add_caching': (0, 1, 1),           # Add LRU cache
            'add_logging': (0, 1, 1),           # Add detailed logging
            'optimize_imports': (0, 1, 1),      # Move imports inside functions
            'add_error_handling': (0, 1, 1),    # Add comprehensive try-except
            'add_input_validation': (0, 1, 1),  # Add parameter validation
            'add_type_hints': (0, 1, 1),        # Add type annotations
            'reduce_complexity': (0, 1, 1),     # Simplify logic
            'add_timeout': (0, 1, 1),           # Add timeout protection

            # Performance parameters
            'cache_size': (16, 256, 16),        # LRU cache size
            'timeout_seconds': (1, 30, 1),      # Timeout in seconds
        }

    def get_safety_constraints(self) -> Dict[str, Any]:
        """Get tool safety constraints."""
        return {
            'max_execution_time_ms': {'max': 5000},    # Max 5 seconds
            'max_memory_mb': {'max': 100},              # Max 100MB memory
            'min_success_rate': {'min': 0.8},           # 80% success rate
            'no_dangerous_imports': {'eq': True},       # No dangerous modules
            'max_code_lines': {'max': 200},             # Max 200 lines
        }

    def get_default_weights(self) -> Dict[str, float]:
        """Get default fitness weights for tools."""
        return {
            'success_rate': 0.35,           # Correctness is critical
            'avg_latency_ms': -0.25,        # Faster is better
            'code_quality': 0.20,           # Maintainability matters
            'safety_score': 0.20,           # Safety is important
        }

    def normalize_metric(self, metric_name: str, value: float) -> float:
        """Normalize tool metric to [0, 1] range."""
        ranges = {
            'success_rate': (0, 1),             # Already normalized
            'avg_latency_ms': (0, 5000),        # 0-5000ms
            'code_quality': (0, 1),             # Already normalized
            'safety_score': (0, 1),             # Already normalized
            'memory_usage_mb': (0, 100),        # 0-100MB
        }

        if metric_name in ranges:
            min_val, max_val = ranges[metric_name]
            normalized = (value - min_val) / (max_val - min_val)
            return max(0, min(1, normalized))
        return value

    def apply_configuration(self, config: Dict[str, Any]) -> bool:
        """
        Apply tool configuration by generating modified tool code.

        Note: This doesn't permanently modify tools - just generates
        variants for testing.
        """
        try:
            # Get tool to evolve
            tool_idx = int(config.get('tool_idx', 0))
            tool_name = self.evolvable_tools[tool_idx]

            # Load original tool code
            tool_file = self.tools_dir / f"{tool_name}.py"
            if not tool_file.exists():
                logger.warning(f"Tool file not found: {tool_file}")
                return False

            with open(tool_file, 'r') as f:
                original_code = f.read()

            # Apply mutations based on config
            modified_code = self._apply_mutations(original_code, config)

            # Store modified code for testing
            self.current_tool_name = tool_name
            self.current_tool_code = modified_code

            return True

        except Exception as e:
            logger.error(f"Failed to apply tool configuration: {e}")
            return False

    def _apply_mutations(self, code: str, config: Dict[str, Any]) -> str:
        """Apply code mutations based on configuration."""
        modified = code

        # Add caching
        if config.get('add_caching', 0) == 1:
            cache_size = int(config.get('cache_size', 128))
            if '@lru_cache' not in modified and 'from functools import lru_cache' not in modified:
                # Add import
                lines = modified.split('\n')
                import_idx = next((i for i, line in enumerate(lines) if line.strip().startswith('import ') or line.strip().startswith('from ')), 0)
                lines.insert(import_idx, 'from functools import lru_cache')

                # Add decorator to main function
                func_idx = next((i for i, line in enumerate(lines) if line.strip().startswith('def ')), -1)
                if func_idx != -1:
                    lines.insert(func_idx, f'@lru_cache(maxsize={cache_size})')

                modified = '\n'.join(lines)

        # Add logging
        if config.get('add_logging', 0) == 1:
            if 'import logging' not in modified:
                lines = modified.split('\n')
                lines.insert(0, 'import logging')
                lines.insert(1, 'logger = logging.getLogger(__name__)')
                modified = '\n'.join(lines)

        # Add error handling
        if config.get('add_error_handling', 0) == 1:
            modified = self._wrap_in_try_except(modified)

        # Add timeout
        if config.get('add_timeout', 0) == 1:
            timeout_sec = int(config.get('timeout_seconds', 5))
            modified = self._add_timeout_protection(modified, timeout_sec)

        return modified

    def _wrap_in_try_except(self, code: str) -> str:
        """Wrap function body in try-except."""
        lines = code.split('\n')

        # Find main function
        func_idx = -1
        for i, line in enumerate(lines):
            if line.strip().startswith('def ') and not line.strip().startswith('def _'):
                func_idx = i
                break

        if func_idx == -1:
            return code

        # Find function body start (after def line and docstring)
        body_start = func_idx + 1
        if body_start < len(lines) and '"""' in lines[body_start]:
            # Skip docstring
            for i in range(body_start + 1, len(lines)):
                if '"""' in lines[i]:
                    body_start = i + 1
                    break

        # Wrap body in try-except
        indent = '    '
        wrapped = lines[:body_start]
        wrapped.append(f'{indent}try:')

        # Indent existing body
        for line in lines[body_start:]:
            if line.strip():
                wrapped.append(f'    {line}')
            else:
                wrapped.append(line)

        wrapped.append(f'{indent}except Exception as e:')
        wrapped.append(f'{indent}    logger.error(f"Tool error: {{e}}")')
        wrapped.append(f'{indent}    return {{"error": str(e)}}')

        return '\n'.join(wrapped)

    def _add_timeout_protection(self, code: str, timeout_sec: int) -> str:
        """Add timeout protection to function."""
        # Simple approach: add signal-based timeout
        if 'import signal' in code:
            return code

        timeout_wrapper = f"""
import signal
import functools

def timeout(seconds):
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            def handler(signum, frame):
                raise TimeoutError(f"Function timed out after {{seconds}} seconds")

            signal.signal(signal.SIGALRM, handler)
            signal.alarm(seconds)
            try:
                result = func(*args, **kwargs)
            finally:
                signal.alarm(0)
            return result
        return wrapper
    return decorator

"""
        return timeout_wrapper + code

    def run_probes(self, config: Dict[str, Any]) -> Dict[str, float]:
        """
        Run tool performance probes.

        Args:
            config: Tool configuration parameters

        Returns:
            Dict of measured metrics
        """
        metrics = {}

        # Apply configuration first (generates modified tool code)
        if not self.apply_configuration(config):
            logger.error("Failed to apply configuration")
            return {
                'success_rate': 0.0,
                'avg_latency_ms': 5000.0,
                'code_quality': 0.0,
                'safety_score': 0.0,
            }

        # Get test scenarios for current tool
        scenarios = self.test_scenarios.get(self.current_tool_name, [])

        if not scenarios:
            logger.warning(f"No test scenarios for {self.current_tool_name}")
            return {
                'success_rate': 0.0,
                'avg_latency_ms': 5000.0,
                'code_quality': 0.5,
                'safety_score': 0.5,
            }

        # Run test scenarios
        successes = 0
        latencies = []

        for scenario in scenarios:
            success, latency = self._run_tool_scenario(scenario)
            if success:
                successes += 1
            if latency is not None:
                latencies.append(latency)

        # Calculate metrics
        metrics['success_rate'] = successes / len(scenarios) if scenarios else 0.0
        metrics['avg_latency_ms'] = np.mean(latencies) if latencies else 5000.0
        metrics['code_quality'] = self._measure_code_quality(self.current_tool_code)
        metrics['safety_score'] = self._measure_safety(self.current_tool_code)

        return metrics

    def _run_tool_scenario(self, scenario: Dict) -> Tuple[bool, Optional[float]]:
        """
        Run a single test scenario for the tool.

        Returns:
            (success, latency_ms)
        """
        try:
            # Create temporary module file
            with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
                f.write(self.current_tool_code)
                temp_module = f.name

            # Execute tool in subprocess with timeout
            start_time = time.time()

            cmd = [
                sys.executable,
                '-c',
                f"""
import sys
sys.path.insert(0, '{self.tools_dir}')

# Load and execute tool
with open('{temp_module}', 'r') as f:
    code = f.read()

exec(code)

# Call main function
result = {self.current_tool_name}(**{scenario['args']})
print(result)
"""
            ]

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=10
            )

            latency_ms = (time.time() - start_time) * 1000

            # Clean up
            os.unlink(temp_module)

            # Check result
            if result.returncode != 0:
                logger.warning(f"Tool execution failed: {result.stderr}")
                return False, latency_ms

            # Verify expected keys in output
            # (simplified - real implementation would parse and validate)
            success = result.returncode == 0

            return success, latency_ms

        except subprocess.TimeoutExpired:
            logger.warning(f"Tool execution timed out")
            return False, 10000.0
        except Exception as e:
            logger.error(f"Tool scenario failed: {e}")
            return False, None

    def _measure_code_quality(self, code: str) -> float:
        """Measure code quality (0-1 scale)."""
        quality = 0.5  # Base score

        # Positive indicators
        if '"""' in code or "'''" in code:
            quality += 0.1  # Has docstrings

        if 'type hint' in code or ': str' in code or ': int' in code:
            quality += 0.1  # Has type hints

        if 'logging' in code:
            quality += 0.05  # Has logging

        # Negative indicators
        line_count = len([l for l in code.split('\n') if l.strip()])
        if line_count > 150:
            quality -= 0.15  # Too complex

        # Count indentation levels (complexity proxy)
        max_indent = max((len(l) - len(l.lstrip()) for l in code.split('\n')), default=0)
        if max_indent > 16:
            quality -= 0.1  # Deep nesting

        return max(0.0, min(1.0, quality))

    def _measure_safety(self, code: str) -> float:
        """Measure code safety (0-1 scale)."""
        safety = 1.0  # Start with perfect score

        # Dangerous patterns
        dangerous = ['eval(', 'exec(', 'os.system', '__import__', 'subprocess.call']
        for pattern in dangerous:
            if pattern in code:
                safety -= 0.3

        # Positive safety indicators
        if 'try:' in code and 'except' in code:
            safety += 0.1  # Error handling

        if 'if ' in code and 'is None' in code:
            safety += 0.05  # Input validation

        return max(0.0, min(1.0, safety))


# Test function
def test_tool_evaluator():
    """Test the tool domain evaluator."""
    evaluator = ToolDomainEvaluator()

    # Test with config
    test_config = {
        'tool_idx': 0,  # system_diagnostic
        'add_caching': 1,
        'add_logging': 1,
        'add_error_handling': 1,
        'cache_size': 128,
        'timeout_seconds': 5,
    }

    print(f"Testing Tool evaluator with config: {json.dumps(test_config, indent=2)}")

    # Run evaluation
    result = evaluator.evaluate(test_config)

    print(f"\nEvaluation Results:")
    print(f"Fitness: {result['fitness']:.3f}")
    print(f"Safe: {result['safe']}")
    if result.get('violations'):
        print(f"Violations: {result['violations']}")
    print(f"Metrics: {json.dumps(result['metrics'], indent=2)}")


if __name__ == '__main__':
    test_tool_evaluator()
