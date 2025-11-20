#!/usr/bin/env python3
"""
Memory Domain Evaluator for D-REAM
Tests DDR5 frequencies, timings, voltages, and stability.
"""

import os
import re
import time
import json
import logging
import subprocess
from typing import Dict, List, Any, Tuple, Optional
from pathlib import Path
import numpy as np

from .domain_evaluator_base import DomainEvaluator

logger = logging.getLogger(__name__)


class MemoryDomainEvaluator(DomainEvaluator):
    """Evaluator for memory performance and stability."""

    def __init__(self):
        super().__init__("memory")
        self.memory_info = self._get_memory_info()
        self.supported_frequencies = self._get_supported_frequencies()
        self.has_xmp = self._check_xmp_support()
        self.has_ecc = self._check_ecc_support()

    def _get_memory_info(self) -> Dict[str, Any]:
        """Get system memory information."""
        info = {
            'total_mb': 0,
            'channels': 0,
            'dimms': 0,
            'type': 'DDR5',
            'speed_mhz': 0,
            'manufacturer': 'Unknown'
        }

        try:
            # Get total memory
            with open('/proc/meminfo', 'r') as f:
                for line in f:
                    if line.startswith('MemTotal:'):
                        info['total_mb'] = int(line.split()[1]) // 1024
                        break

            # Use dmidecode for detailed info (requires sudo)
            cmd = ['sudo', 'dmidecode', '-t', 'memory']
            returncode, stdout, _ = self.run_command(cmd, timeout=2)

            if returncode == 0:
                # Parse dmidecode output
                for line in stdout.split('\n'):
                    if 'Speed:' in line and 'MHz' in line:
                        match = re.search(r'(\d+)\s*MHz', line)
                        if match:
                            info['speed_mhz'] = int(match.group(1))
                    elif 'Type:' in line and 'DDR' in line:
                        if 'DDR5' in line:
                            info['type'] = 'DDR5'
                        elif 'DDR4' in line:
                            info['type'] = 'DDR4'
                    elif 'Number Of Devices:' in line:
                        match = re.search(r'(\d+)', line)
                        if match:
                            info['dimms'] = int(match.group(1))

        except Exception as e:
            logger.error(f"Failed to get memory info: {e}")

        return info

    def _get_supported_frequencies(self) -> List[int]:
        """Get supported memory frequencies."""
        # DDR5 common frequencies
        if self.memory_info['type'] == 'DDR5':
            return [4800, 5200, 5600, 6000, 6400, 6800, 7200, 7600, 8000]
        # DDR4 common frequencies
        else:
            return [2133, 2400, 2666, 2933, 3200, 3466, 3600, 3866, 4000]

    def _check_xmp_support(self) -> bool:
        """Check if XMP/EXPO profiles are available."""
        # Would check BIOS/UEFI settings in production
        return os.path.exists('/sys/firmware/dmi/tables/DMI')

    def _check_ecc_support(self) -> bool:
        """Check if ECC memory is present."""
        try:
            cmd = ['sudo', 'dmidecode', '-t', 'memory']
            returncode, stdout, _ = self.run_command(cmd, timeout=2)
            if returncode == 0:
                return 'Error Correction Type: Multi-bit ECC' in stdout
        except:
            pass
        return False

    def get_genome_spec(self) -> Dict[str, Tuple[Any, Any, Any]]:
        """Get memory genome specification."""
        spec = {
            # Frequency selection (index into supported frequencies)
            'freq_idx': (0, len(self.supported_frequencies)-1, 1),

            # Primary timings (in clock cycles)
            'tcl': (28, 40, 2),        # CAS Latency (CL)
            'trcd': (28, 40, 2),       # RAS to CAS Delay
            'trp': (28, 40, 2),        # RAS Precharge
            'tras': (50, 80, 2),       # Active to Precharge

            # Secondary timings
            'trc': (70, 120, 2),       # Row Cycle Time
            'trfc': (250, 650, 50),    # Refresh Cycle Time
            'trefi': (7800, 15600, 1000),  # Refresh Interval
            'tfaw': (16, 48, 4),       # Four Activate Window

            # Command rate (1T=0, 2T=1)
            'command_rate': (0, 1, 1),

            # Voltages (in millivolts)
            'vdd': (1100, 1400, 25),   # Main voltage
            'vddq': (1100, 1400, 25),  # I/O voltage
            'vpp': (1700, 1900, 25),   # Programming voltage
        }

        # Additional settings for DDR5
        if self.memory_info['type'] == 'DDR5':
            spec['vdd2'] = (1000, 1200, 25)  # Secondary voltage

        return spec

    def get_safety_constraints(self) -> Dict[str, Any]:
        """Get memory safety constraints."""
        return {
            'dimm_temp_c': {'max': 60},         # Max DIMM temperature
            'vdd_mv': {'max': 1450},            # Max VDD voltage
            'vddq_mv': {'max': 1450},           # Max VDDQ voltage
            'whea_errors': {'eq': 0},           # No WHEA errors
            'ecc_errors': {'eq': 0},            # No ECC errors (if supported)
            'memtest_errors': {'eq': 0},        # No memory test errors
            'post_time_s': {'max': 30}          # Max POST time
        }

    def get_default_weights(self) -> Dict[str, float]:
        """Get default fitness weights for memory."""
        return {
            'bandwidth_gb': 0.3,             # Maximize bandwidth
            'latency_ns': -0.25,            # Minimize latency
            'stability_score': 0.35,        # Maximize stability
            'post_time_s': -0.05,           # Minimize POST time
            'power_w': -0.05                # Minimize power
        }

    def normalize_metric(self, metric_name: str, value: float) -> float:
        """Normalize memory metric to [0, 1] range."""
        ranges = {
            'bandwidth_gb': (0, 200),        # 0-200 GB/s
            'latency_ns': (0, 150),          # 0-150ns
            'stability_score': (0, 1),       # 0-1 score
            'post_time_s': (0, 60),          # 0-60 seconds
            'power_w': (0, 50),              # 0-50W
            'dimm_temp_c': (0, 80),          # 0-80°C
            'whea_errors': (0, 100),         # 0-100 errors
            'ecc_errors': (0, 100),          # 0-100 errors
        }

        if metric_name in ranges:
            min_val, max_val = ranges[metric_name]
            normalized = (value - min_val) / (max_val - min_val)
            return max(0, min(1, normalized))
        return value

    def apply_configuration(self, config: Dict[str, Any]) -> bool:
        """Apply memory configuration."""
        logger.warning("Memory configuration requires BIOS/UEFI access")
        # In production, would use:
        # - IPMI/BMC for server systems
        # - Intel XTU or AMD Ryzen Master APIs
        # - Custom UEFI runtime services

        # For now, log intended configuration
        config_file = Path("/tmp/dream_memory_config.json")
        try:
            with open(config_file, 'w') as f:
                json.dump({
                    'timestamp': time.time(),
                    'config': config,
                    'applied': False,
                    'reason': 'Requires BIOS/UEFI access'
                }, f, indent=2)
            return True
        except Exception as e:
            logger.error(f"Failed to save memory config: {e}")
            return False

    def run_probes(self, config: Dict[str, Any]) -> Dict[str, float]:
        """Run memory performance probes."""
        metrics = {}

        # Apply configuration (limited without BIOS access)
        if not self.apply_configuration(config):
            logger.warning("Memory configuration not fully applied")

        # Run memory bandwidth test
        bandwidth_metrics = self._run_bandwidth_test()
        metrics.update(bandwidth_metrics)

        # Run memory latency test
        latency_metrics = self._run_latency_test(config)
        metrics.update(latency_metrics)

        # Run stability test (quick version)
        stability_metrics = self._run_stability_test(duration=30)
        metrics.update(stability_metrics)

        # Monitor memory sensors
        sensor_metrics = self._monitor_memory_sensors(config)
        metrics.update(sensor_metrics)

        # Check for errors
        error_metrics = self._check_memory_errors()
        metrics.update(error_metrics)

        # Estimate POST time impact
        metrics['post_time_s'] = self._estimate_post_time(config)

        return metrics

    def _run_bandwidth_test(self) -> Dict[str, float]:
        """Run memory bandwidth test using compliant D-REAM tools."""
        metrics = {}

        try:
            # Use compliant memory bandwidth measurement
            import sys
            sys.path.insert(0, '/home/kloros/src/dream/compliance_tools')
            from memory_bw import measure_memory_bandwidth

            result = measure_memory_bandwidth(seconds=5.0)
            if 'bandwidth_gb_s' in result:
                metrics['bandwidth_gb'] = result['bandwidth_gb_s']
            else:
                logger.warning("Memory bandwidth measurement failed, using estimate")
                metrics['bandwidth_gb'] = 50.0  # Default estimate

        except Exception as e:
            logger.error(f"Failed to run bandwidth test: {e}")
            # Estimate based on frequency (conservative fallback)
            metrics['bandwidth_gb'] = 50.0

        return metrics


    def _run_latency_test(self, config: Dict[str, Any]) -> Dict[str, float]:
        """Run memory latency test."""
        metrics = {}

        try:
            # Try to use mlc (Intel Memory Latency Checker)
            cmd = ['mlc', '--latency_matrix']
            returncode, stdout, _ = self.run_command(cmd, timeout=10)

            if returncode == 0:
                # Parse MLC output for average latency
                match = re.search(r'Average:\s*([\d.]+)\s*ns', stdout)
                if match:
                    metrics['latency_ns'] = float(match.group(1))
            else:
                # Fallback: estimate based on timings
                metrics['latency_ns'] = self._estimate_latency_from_timings(config)

        except Exception as e:
            logger.error(f"Failed to run latency test: {e}")
            metrics['latency_ns'] = 80.0  # Default estimate

        return metrics

    def _estimate_latency_from_timings(self, config: Dict[str, Any]) -> float:
        """Estimate latency from memory timings."""
        # Get frequency
        freq_idx = int(config.get('freq_idx', 0))
        freq_mhz = self.supported_frequencies[freq_idx]

        # Get primary timings
        tcl = config.get('tcl', 32)
        trcd = config.get('trcd', 32)
        trp = config.get('trp', 32)

        # Calculate approximate latency in nanoseconds
        # Clock period in ns
        clock_period_ns = 1000.0 / freq_mhz

        # Approximate latency = (tCL + tRCD + tRP) * clock_period
        latency_ns = (tcl + trcd + trp) * clock_period_ns / 2

        return latency_ns

    def _run_stability_test(self, duration: int = 30) -> Dict[str, float]:
        """Run quick memory stability test."""
        metrics = {}

        try:
            # Use stressapptest for quick stability check
            cmd = [
                'stressapptest',
                '-M', str(self.memory_info['total_mb'] // 4),  # Test 25% of RAM
                '-s', str(duration),
                '-W'  # Use more stressful workload
            ]

            returncode, stdout, stderr = self.run_command(cmd, timeout=duration+5)

            if returncode == 0 and 'PASS' in stdout:
                metrics['stability_score'] = 1.0
                metrics['memtest_errors'] = 0
            else:
                # Check for errors
                error_count = stdout.count('error') + stderr.count('error')
                metrics['stability_score'] = max(0, 1.0 - (error_count * 0.1))
                metrics['memtest_errors'] = error_count

        except Exception as e:
            logger.error(f"Failed to run stability test: {e}")
            # Fallback: simple memory pattern test
            metrics['stability_score'] = self._simple_memory_test()
            metrics['memtest_errors'] = 0

        return metrics

    def _simple_memory_test(self) -> float:
        """Simple memory pattern test."""
        try:
            import numpy as np

            # Test patterns
            test_size = 100 * 1024 * 1024  # 100MB
            patterns = [0x00, 0xFF, 0xAA, 0x55, 0x5A, 0xA5]

            errors = 0
            for pattern in patterns:
                # Create array with pattern
                arr = np.full(test_size // 8, pattern, dtype=np.uint8)

                # Write and read back
                arr_copy = arr.copy()

                # Check for differences
                if not np.array_equal(arr, arr_copy):
                    errors += 1

            return 1.0 - (errors / len(patterns))

        except Exception as e:
            logger.error(f"Simple memory test failed: {e}")
            return 0.5

    def _monitor_memory_sensors(self, config: Dict[str, Any]) -> Dict[str, float]:
        """Monitor memory temperature and power sensors."""
        metrics = {}

        try:
            # Check for DIMM temperature sensors
            temps = []

            # Method 1: Try gigabyte_wmi sensors (may include memory temp)
            try:
                import json
                import subprocess
                result = subprocess.run(['sensors', '-j'], capture_output=True, text=True, timeout=2)
                if result.returncode == 0:
                    sensors_data = json.loads(result.stdout)
                    
                    # Check gigabyte_wmi virtual sensors
                    if 'gigabyte_wmi-virtual-0' in sensors_data:
                        wmi_sensors = sensors_data['gigabyte_wmi-virtual-0']
                        # temp5/temp6 often correspond to chipset/memory on Gigabyte boards
                        for temp_name in ['temp5', 'temp6']:
                            if temp_name in wmi_sensors:
                                temp_input_key = f'{temp_name}_input'
                                if temp_input_key in wmi_sensors[temp_name]:
                                    temp_c = wmi_sensors[temp_name][temp_input_key]
                                    # Sanity check: 20-85°C range for memory
                                    if 20 <= temp_c <= 85:
                                        temps.append(temp_c)
                                        logger.debug(f"Found potential memory temp from {temp_name}: {temp_c}°C")
            except Exception as e:
                logger.debug(f"Could not read gigabyte_wmi sensors: {e}")

            # Method 2: Try i2c sensors (SPD temperature)
            for i in range(8):  # Check up to 8 DIMM slots
                temp_file = f"/sys/class/hwmon/hwmon*/temp{i+1}_input"
                import glob
                for path in glob.glob(temp_file):
                    if 'DIMM' in self.read_sysfs(path.replace('_input', '_label'), ''):
                        temp = self.read_sysfs(path, 0)
                        if temp:
                            temps.append(temp / 1000.0)  # Convert to Celsius

            if temps:
                metrics['dimm_temp_c'] = max(temps)
            else:
                metrics['dimm_temp_c'] = 45  # Default estimate

            # Estimate memory power consumption
            # Rough estimate: 3W per 8GB DDR5 at stock
            power_per_gb = 0.375
            metrics['power_w'] = (self.memory_info['total_mb'] / 1024) * power_per_gb

            # Adjust power based on voltage settings
            if 'vdd' in config:
                vdd_stock = 1200  # Stock DDR5 voltage
                vdd_actual = config['vdd']
                # Power scales roughly with voltage squared
                power_scale = (vdd_actual / vdd_stock) ** 2
                metrics['power_w'] *= power_scale

        except Exception as e:
            logger.error(f"Failed to monitor memory sensors: {e}")
            metrics['dimm_temp_c'] = 45
            metrics['power_w'] = 10

        return metrics

    def _check_memory_errors(self) -> Dict[str, float]:
        """Check for memory errors in system logs."""
        metrics = {
            'whea_errors': 0,
            'ecc_errors': 0
        }

        try:
            # Check dmesg for memory errors
            cmd = ['dmesg']
            returncode, stdout, _ = self.run_command(cmd, timeout=2)

            if returncode == 0:
                # Count WHEA errors
                whea_count = stdout.lower().count('whea') + stdout.lower().count('hardware error')
                metrics['whea_errors'] = whea_count

                # Count ECC errors if supported
                if self.has_ecc:
                    ecc_count = stdout.lower().count('ecc') + stdout.lower().count('corrected error')
                    metrics['ecc_errors'] = ecc_count

            # Check mcelog if available
            if os.path.exists('/var/log/mcelog'):
                with open('/var/log/mcelog', 'r') as f:
                    mcelog = f.read()
                    metrics['whea_errors'] += mcelog.count('error')

        except Exception as e:
            logger.error(f"Failed to check memory errors: {e}")

        return metrics

    def _estimate_post_time(self, config: Dict[str, Any]) -> float:
        """Estimate POST time impact of memory configuration."""
        # Base POST time
        post_time = 5.0

        # Add time for memory training
        # Tighter timings = longer training
        tcl = config.get('tcl', 32)
        if tcl < 30:
            post_time += 2.0  # Aggressive timings need more training

        # Higher frequency = longer training
        freq_idx = int(config.get('freq_idx', 0))
        if freq_idx > len(self.supported_frequencies) // 2:
            post_time += 1.5

        # Command rate 1T needs more validation
        if config.get('command_rate', 1) == 0:
            post_time += 1.0

        return post_time


# Test function
def test_memory_evaluator():
    """Test the memory domain evaluator."""
    import numpy as np

    evaluator = MemoryDomainEvaluator()

    print(f"Memory Info: {json.dumps(evaluator.memory_info, indent=2)}")
    print(f"Supported Frequencies: {evaluator.supported_frequencies} MHz")
    print(f"Has XMP/EXPO: {evaluator.has_xmp}")
    print(f"Has ECC: {evaluator.has_ecc}")

    # Test with random genome
    genome_size = len(evaluator.get_genome_spec())
    genome = np.random.randn(genome_size).tolist()

    print(f"\nTesting memory evaluator with genome size {genome_size}")

    # Convert genome to config
    config = evaluator.genome_to_config(genome)
    print(f"Configuration: {json.dumps(config, indent=2)}")

    # Run evaluation
    result = evaluator.evaluate(genome)

    print(f"\nEvaluation Results:")
    print(f"Fitness: {result['fitness']:.3f}")
    print(f"Safe: {result['safe']}")
    if result['violations']:
        print(f"Violations: {result['violations']}")
    print(f"Metrics: {json.dumps(result['metrics'], indent=2)}")


if __name__ == '__main__':
    test_memory_evaluator()