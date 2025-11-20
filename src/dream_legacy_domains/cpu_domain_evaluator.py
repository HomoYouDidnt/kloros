#!/usr/bin/env python3
"""
CPU Domain Evaluator for D-REAM
Tests CPU governors, pinning, turbo, EPP, thread counts, etc.
"""

import os
import re
import time
import psutil
import logging
from typing import Dict, List, Any, Tuple, Optional
from pathlib import Path

from .domain_evaluator_base import DomainEvaluator

logger = logging.getLogger(__name__)


class CPUDomainEvaluator(DomainEvaluator):
    """Evaluator for CPU performance and configuration."""

    def __init__(self):
        super().__init__("cpu")
        self.cpu_count = psutil.cpu_count(logical=True)
        self.physical_cores = psutil.cpu_count(logical=False)
        self.available_governors = self._get_available_governors()
        self.has_epp = self._check_epp_support()
        self.has_turbo = self._check_turbo_support()

    def _get_available_governors(self) -> List[str]:
        """Get list of available CPU governors."""
        try:
            gov_path = "/sys/devices/system/cpu/cpu0/cpufreq/scaling_available_governors"
            governors = self.read_sysfs(gov_path, "performance schedutil powersave")
            if isinstance(governors, str):
                return governors.split()
            return ["performance", "schedutil", "powersave"]
        except:
            return ["performance", "schedutil", "powersave"]

    def _check_epp_support(self) -> bool:
        """Check if Energy Performance Preference is supported."""
        epp_path = "/sys/devices/system/cpu/cpu0/cpufreq/energy_performance_preference"
        return os.path.exists(epp_path)

    def _check_turbo_support(self) -> bool:
        """Check if turbo boost control is available."""
        intel_turbo = "/sys/devices/system/cpu/intel_pstate/no_turbo"
        amd_turbo = "/sys/devices/system/cpu/cpufreq/boost"
        return os.path.exists(intel_turbo) or os.path.exists(amd_turbo)

    def get_genome_spec(self) -> Dict[str, Tuple[Any, Any, Any]]:
        """Get CPU genome specification."""
        spec = {
            # Core affinity mask (0-1 representing which cores to use)
            'core_utilization': (0.25, 1.0, 0.25),  # Use 25-100% of cores

            # SMT control (0=off, 1=on)
            'smt_enabled': (0, 1, 1),

            # Governor selection (index into available governors)
            'governor_idx': (0, len(self.available_governors)-1, 1),

            # Thread count for workload
            'thread_count': (1, self.cpu_count, 1),

            # Hugepages allocation (MB)
            'hugepages_mb': (0, 2048, 256),
        }

        # Add EPP if supported (0=performance, 255=power)
        if self.has_epp:
            spec['epp_value'] = (0, 255, 15)

        # Add turbo control if supported
        if self.has_turbo:
            spec['turbo_enabled'] = (0, 1, 1)

        return spec

    def get_safety_constraints(self) -> Dict[str, Any]:
        """Get CPU safety constraints."""
        return {
            'cpu_temp_c': {'max': 90},      # Max 90°C
            'package_power_w': {'max': 150}, # Max package power (adjust for your CPU)
            'thermal_throttle': {'eq': 0},   # No thermal throttling allowed
            'cpu_usage_percent': {'max': 95} # Leave some headroom
        }

    def get_default_weights(self) -> Dict[str, float]:
        """Get default fitness weights."""
        return {
            'throughput_ops': 0.4,      # Maximize throughput
            'p95_latency_ms': -0.2,     # Minimize latency
            'p99_latency_ms': -0.1,     # Minimize tail latency
            'context_switches': -0.05,  # Minimize context switches
            'cache_miss_rate': -0.1,    # Minimize cache misses
            'watts_per_op': -0.15       # Minimize energy per operation
        }

    def normalize_metric(self, metric_name: str, value: float) -> float:
        """Normalize metric to [0, 1] range."""
        # Define expected ranges for normalization
        ranges = {
            'throughput_ops': (0, 1000000),     # 0-1M ops/s
            'p95_latency_ms': (0, 100),         # 0-100ms
            'p99_latency_ms': (0, 200),         # 0-200ms
            'context_switches': (0, 100000),    # 0-100k/s
            'cache_miss_rate': (0, 0.5),        # 0-50% miss rate
            'watts_per_op': (0, 0.001),         # 0-1mW per op
            'cpu_temp_c': (0, 100),             # 0-100°C
            'package_power_w': (0, 200),        # 0-200W
        }

        if metric_name in ranges:
            min_val, max_val = ranges[metric_name]
            normalized = (value - min_val) / (max_val - min_val)
            return max(0, min(1, normalized))
        return value

    def apply_configuration(self, config: Dict[str, Any]) -> bool:
        """Apply CPU configuration to the system."""
        try:
            # Set CPU governor
            if 'governor_idx' in config:
                governor = self.available_governors[int(config['governor_idx'])]
                self._set_governor(governor)

            # Set core affinity (simplified - would need proper taskset in real use)
            if 'core_utilization' in config:
                active_cores = int(self.physical_cores * config['core_utilization'])
                active_cores = max(1, min(self.physical_cores, active_cores))
                # In production, would use taskset to pin processes

            # Set EPP if available
            if self.has_epp and 'epp_value' in config:
                self._set_epp(int(config['epp_value']))

            # Set turbo if available
            if self.has_turbo and 'turbo_enabled' in config:
                self._set_turbo(bool(config['turbo_enabled']))

            # Set hugepages
            if 'hugepages_mb' in config:
                self._configure_hugepages(int(config['hugepages_mb']))

            return True

        except Exception as e:
            logger.error(f"Failed to apply CPU config: {e}")
            return False

    def _set_governor(self, governor: str) -> bool:
        """Set CPU governor for all cores."""
        try:
            for cpu in range(self.cpu_count):
                gov_path = f"/sys/devices/system/cpu/cpu{cpu}/cpufreq/scaling_governor"
                if not self.write_sysfs(gov_path, governor):
                    return False
            logger.info(f"Set CPU governor to {governor}")
            return True
        except Exception as e:
            logger.error(f"Failed to set governor: {e}")
            return False

    def _set_epp(self, epp_value: int) -> bool:
        """Set Energy Performance Preference."""
        try:
            for cpu in range(self.cpu_count):
                epp_path = f"/sys/devices/system/cpu/cpu{cpu}/cpufreq/energy_performance_preference"
                # EPP can be numeric or string like "balance_performance"
                if epp_value <= 64:
                    epp_str = "performance"
                elif epp_value <= 128:
                    epp_str = "balance_performance"
                elif epp_value <= 192:
                    epp_str = "balance_power"
                else:
                    epp_str = "power"

                if not self.write_sysfs(epp_path, epp_str):
                    return False
            return True
        except Exception as e:
            logger.error(f"Failed to set EPP: {e}")
            return False

    def _set_turbo(self, enabled: bool) -> bool:
        """Enable/disable turbo boost."""
        try:
            # Intel path
            intel_path = "/sys/devices/system/cpu/intel_pstate/no_turbo"
            if os.path.exists(intel_path):
                # Intel uses inverted logic (no_turbo)
                return self.write_sysfs(intel_path, "0" if enabled else "1")

            # AMD path
            amd_path = "/sys/devices/system/cpu/cpufreq/boost"
            if os.path.exists(amd_path):
                return self.write_sysfs(amd_path, "1" if enabled else "0")

            return False
        except Exception as e:
            logger.error(f"Failed to set turbo: {e}")
            return False

    def _configure_hugepages(self, mb: int) -> bool:
        """Configure hugepages allocation."""
        try:
            # Calculate number of 2MB hugepages
            pages = mb // 2
            hugepage_path = "/proc/sys/vm/nr_hugepages"
            return self.write_sysfs(hugepage_path, str(pages))
        except Exception as e:
            logger.error(f"Failed to configure hugepages: {e}")
            return False

    def run_probes(self, config: Dict[str, Any]) -> Dict[str, float]:
        """Run CPU performance probes."""
        metrics = {}

        # Apply configuration
        if not self.apply_configuration(config):
            logger.warning("Failed to apply some CPU configurations")

        # Get regime-specific workload
        regime = self.current_regime or {'workload': 'script', 'args': 'scripts/cpu_idle.sh 10'}
        workload_type = regime.get('workload', 'script')
        workload_args = regime.get('args', '')
        
        logger.info(f"Regime workload: {workload_type} {workload_args}")

        # Capture pre-test system state
        ctx_switches_before = psutil.cpu_stats().ctx_switches
        cpu_percent_start = psutil.cpu_percent(interval=0.1)  # Prime the pump

        # Execute workload based on regime
        if workload_type == 'stress-ng':
            # Parse stress-ng args and run
            args_list = workload_args.split() if workload_args else []
            stress_metrics = self._run_stress_ng_with_args(args_list)
            metrics.update(stress_metrics)
        elif workload_type == 'script':
            # Script workload - skip stress-ng
            logger.info(f"Script workload configured: {workload_args} (stress-ng disabled)")
            # Use lightweight CPU metrics only
            metrics['cpu_percent'] = psutil.cpu_percent(interval=1.0)
            metrics['throughput_ops'] = 0.0  # No benchmark run
        else:
            # Default workload - skip stress-ng
            logger.info("Default workload (stress-ng disabled)")
            metrics['cpu_percent'] = psutil.cpu_percent(interval=1.0)
            metrics['throughput_ops'] = 0.0  # No benchmark run

        # Run y-cruncher quick benchmark
        ycruncher_metrics = self._run_ycruncher()
        metrics.update(ycruncher_metrics)

        # Collect system metrics during/after load
        system_metrics = self._collect_system_metrics()
        metrics.update(system_metrics)

        # Calculate context switch delta
        ctx_switches_after = psutil.cpu_stats().ctx_switches
        metrics['context_switches'] = ctx_switches_after - ctx_switches_before

        # Calculate derived metrics
        if 'throughput_ops' in metrics and 'package_power_w' in metrics:
            if metrics['throughput_ops'] > 0:
                metrics['watts_per_op'] = metrics['package_power_w'] / metrics['throughput_ops']

        return metrics

    def _run_stress_ng_with_args(self, args_list: List[str]) -> Dict[str, float]:
        """Run stress-ng with custom args from regime."""
        metrics = {}
        
        try:
            # Capture CPU usage before
            cpu_before = psutil.cpu_percent(interval=None, percpu=False)
            
            # Build command
            cmd = ['stress-ng'] + args_list + ['--yaml', '/tmp/stress_ng_output.yaml']
            
            # Add metrics flag if not present
            if '--metrics' not in args_list and '--metrics-brief' not in args_list:
                cmd.append('--metrics-brief')
            
            # Extract timeout for command timeout
            timeout = 30  # default
            for i, arg in enumerate(args_list):
                if arg == '--timeout' and i + 1 < len(args_list):
                    timeout_str = args_list[i + 1]
                    timeout = int(timeout_str.replace('s', '').replace('m', '')) + 5
                    break
            
            logger.debug(f"Running: {' '.join(cmd)}")
            returncode, stdout, stderr = self.run_command(cmd, timeout=timeout)

            # Capture CPU usage during/after
            cpu_after = psutil.cpu_percent(interval=0.5, percpu=False)
            metrics['cpu_usage_percent'] = cpu_after

            if returncode == 0:
                # Parse stress-ng YAML output
                metrics['throughput_ops'] = self._parse_stress_ng_output()
            else:
                logger.warning(f"stress-ng failed: {stderr}")
                metrics['throughput_ops'] = 0

        except Exception as e:
            logger.error(f"Failed to run stress-ng with args: {e}")
            metrics['throughput_ops'] = 0
            metrics['cpu_usage_percent'] = 0

        return metrics

    def _run_stress_ng(self, thread_count: int, duration: int = 10) -> Dict[str, float]:
        """Run stress-ng CPU benchmark."""
        metrics = {}

        try:
            # Capture CPU usage before
            cpu_before = psutil.cpu_percent(interval=None, percpu=False)
            
            # Run stress-ng with matrix operations
            cmd = [
                'stress-ng',
                '--cpu', str(thread_count),
                '--cpu-method', 'matrixprod',
                '--metrics',
                '--timeout', f'{duration}s',
                '--yaml', '/tmp/stress_ng_output.yaml'
            ]

            returncode, stdout, stderr = self.run_command(cmd, timeout=duration+5)

            # Capture CPU usage during/after
            cpu_after = psutil.cpu_percent(interval=0.5, percpu=False)
            metrics['cpu_usage_percent'] = cpu_after

            if returncode == 0:
                # Parse stress-ng YAML output
                metrics['throughput_ops'] = self._parse_stress_ng_output()
            else:
                logger.warning(f"stress-ng failed: {stderr}")
                metrics['throughput_ops'] = 0

        except Exception as e:
            logger.error(f"Failed to run stress-ng: {e}")
            metrics['throughput_ops'] = 0
            metrics['cpu_usage_percent'] = 0

        return metrics

    def _parse_stress_ng_output(self) -> float:
        """Parse stress-ng YAML output for throughput."""
        try:
            # In production, properly parse YAML
            # For now, use a simple extraction
            with open('/tmp/stress_ng_output.yaml', 'r') as f:
                content = f.read()
                # Look for bogo ops/s (note: field is 'bogo-ops-per-second-real-time')
                match = re.search(r'bogo-ops-per-second-real-time:\s*([\d.]+)', content)
                if match:
                    return float(match.group(1))
        except:
            pass
        return 0

    def _run_ycruncher(self) -> Dict[str, float]:
        """Run y-cruncher quick benchmark."""
        metrics = {}

        try:
            # Run y-cruncher component stress test
            cmd = [
                'y-cruncher', 'stress',
                '-M', '1',  # 1GB memory
                '-t', '5'   # 5 second test
            ]

            returncode, stdout, stderr = self.run_command(cmd, timeout=10)

            if returncode == 0:
                # Parse y-cruncher output for latency metrics
                # In production, would parse actual output format
                metrics['p95_latency_ms'] = 5.0  # Placeholder
                metrics['p99_latency_ms'] = 10.0  # Placeholder

        except Exception as e:
            logger.error(f"Failed to run y-cruncher: {e}")
            metrics['p95_latency_ms'] = 999
            metrics['p99_latency_ms'] = 999

        return metrics

    def _collect_system_metrics(self) -> Dict[str, float]:
        """Collect system metrics during benchmark."""
        metrics = {}

        try:
            # CPU temperature (try multiple sources)
            metrics['cpu_temp_c'] = self._get_cpu_temperature()

            # Cache misses (would use perf stat in production)
            metrics['cache_miss_rate'] = self._get_cache_miss_rate()

            # Power consumption (from RAPL if available)
            metrics['package_power_w'] = self._get_package_power()

            # Check for thermal throttling
            metrics['thermal_throttle'] = self._check_thermal_throttle()

        except Exception as e:
            logger.error(f"Failed to collect system metrics: {e}")

        return metrics

    def _get_cpu_temperature(self) -> float:
        """Get CPU temperature from available sensors."""
        try:
            # Try psutil first
            temps = psutil.sensors_temperatures()
            if 'coretemp' in temps:
                max_temp = max(t.current for t in temps['coretemp'])
                return max_temp
            elif 'k10temp' in temps:  # AMD
                max_temp = max(t.current for t in temps['k10temp'])
                return max_temp
            elif temps:  # Any sensor
                all_temps = [t.current for sensor_temps in temps.values() for t in sensor_temps]
                if all_temps:
                    return max(all_temps)
            
            # Fallback to hwmon sysfs
            hwmon_base = "/sys/class/hwmon"
            if os.path.exists(hwmon_base):
                for hwmon_dir in os.listdir(hwmon_base):
                    temp_path = f"{hwmon_base}/{hwmon_dir}/temp1_input"
                    if os.path.exists(temp_path):
                        with open(temp_path, 'r') as f:
                            temp_millic = int(f.read().strip())
                            return temp_millic / 1000.0
        except Exception as e:
            logger.debug(f"Could not read CPU temperature: {e}")
        
        # Return default if all methods fail
        return 50.0

    def _get_cache_miss_rate(self) -> float:
        """Get cache miss rate using perf stat."""
        try:
            cmd = ['perf', 'stat', '-e', 'cache-misses,cache-references',
                   '--', 'sleep', '1']
            returncode, stdout, stderr = self.run_command(cmd, timeout=2)

            # Parse perf output
            if returncode == 0:
                # Extract cache miss rate from stderr
                match = re.search(r'([\d.]+)%.*cache-misses', stderr)
                if match:
                    return float(match.group(1)) / 100.0
        except:
            pass
        return 0.05  # Default 5% miss rate

    def _get_package_power(self) -> float:
        """Get package power from RAPL."""
        try:
            # Intel RAPL path
            rapl_path = "/sys/class/powercap/intel-rapl/intel-rapl:0/energy_uj"
            if os.path.exists(rapl_path):
                # Read energy twice with delay to calculate power
                energy1 = self.read_sysfs(rapl_path)
                time.sleep(0.1)
                energy2 = self.read_sysfs(rapl_path)

                if energy1 and energy2:
                    # Convert microjoules to watts
                    power_w = (energy2 - energy1) / 100000.0  # 0.1 second interval
                    return power_w
        except:
            pass
        return 50.0  # Default 50W if not available

    def _check_thermal_throttle(self) -> int:
        """Check if CPU is thermally throttling."""
        try:
            # Check Intel throttle status
            for cpu in range(self.cpu_count):
                throttle_path = f"/sys/devices/system/cpu/cpu{cpu}/thermal_throttle/core_throttle_count"
                if os.path.exists(throttle_path):
                    count = self.read_sysfs(throttle_path, 0)
                    if count > 0:
                        return 1  # Throttling detected
        except:
            pass
        return 0  # No throttling

    def map_metrics_to_scoring(self, metrics: Dict[str, float]) -> Dict[str, float]:
        """Map CPU-specific metrics to generic scoring names."""
        # Create a copy to avoid modifying original
        mapped = dict(metrics)
        
        # Map CPU metrics to scoring keys
        if 'throughput_ops' in metrics:
            mapped['perf'] = metrics['throughput_ops']
        
        if 'p95_latency_ms' in metrics:
            mapped['p95_ms'] = metrics['p95_latency_ms']
        
        if 'package_power_w' in metrics:
            mapped['watts'] = metrics['package_power_w']
        
        return mapped


# Test function
def test_cpu_evaluator():
    """Test the CPU domain evaluator."""
    import numpy as np

    evaluator = CPUDomainEvaluator()

    # Test with random genome
    genome_size = len(evaluator.get_genome_spec())
    genome = np.random.randn(genome_size).tolist()

    print(f"Testing CPU evaluator with genome size {genome_size}")
    print(f"Available governors: {evaluator.available_governors}")
    print(f"Has EPP support: {evaluator.has_epp}")
    print(f"Has turbo support: {evaluator.has_turbo}")

    # Convert genome to config
    config = evaluator.genome_to_config(genome)
    print(f"Configuration: {json.dumps(config, indent=2)}")

    # Run evaluation (dry run without actual system changes)
    result = evaluator.evaluate(genome)

    print(f"\nEvaluation Results:")
    print(f"Fitness: {result['fitness']:.3f}")
    print(f"Safe: {result['safe']}")
    if result['violations']:
        print(f"Violations: {result['violations']}")
    print(f"Metrics: {json.dumps(result['metrics'], indent=2)}")


if __name__ == '__main__':
    import json
    test_cpu_evaluator()

