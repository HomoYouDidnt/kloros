#!/usr/bin/env python3
"""
Power/Thermal Domain Evaluator for D-REAM
Tests CPU/GPU power limits, fan curves, undervolting, and thermal management.
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


class PowerThermalDomainEvaluator(DomainEvaluator):
    """Evaluator for power consumption and thermal management."""

    def __init__(self):
        super().__init__("power_thermal")
        self.cpu_info = self._get_cpu_info()
        self.has_nvidia_gpu = self._check_nvidia_gpu()
        self.has_amd_gpu = self._check_amd_gpu()
        self.cooling_devices = self._get_cooling_devices()
        self.power_sensors = self._get_power_sensors()
        self.has_rapl = self._check_rapl_support()

    def _get_cpu_info(self) -> Dict[str, Any]:
        """Get CPU information relevant to power management."""
        info = {
            'vendor': 'unknown',
            'model': 'unknown',
            'tdp': 65,  # Default TDP
            'cores': 0,
            'max_freq_mhz': 0
        }

        try:
            # Parse /proc/cpuinfo
            with open('/proc/cpuinfo', 'r') as f:
                for line in f:
                    if 'vendor_id' in line:
                        if 'Intel' in line:
                            info['vendor'] = 'intel'
                        elif 'AMD' in line or 'AuthenticAMD' in line:
                            info['vendor'] = 'amd'
                    elif 'model name' in line:
                        info['model'] = line.split(':')[1].strip()
                    elif 'cpu cores' in line:
                        info['cores'] = int(line.split(':')[1].strip())
                    elif 'cpu MHz' in line and info['max_freq_mhz'] == 0:
                        info['max_freq_mhz'] = float(line.split(':')[1].strip())

            # Try to determine TDP
            if 'Ryzen' in info['model']:
                # AMD Ryzen TDP detection
                if '5950X' in info['model'] or '5900X' in info['model']:
                    info['tdp'] = 105
                elif '5800X' in info['model'] or '5700X' in info['model']:
                    info['tdp'] = 65
                elif '7950X' in info['model'] or '7900X' in info['model']:
                    info['tdp'] = 170
            elif 'Intel' in info['model']:
                # Intel TDP detection
                if 'i9' in info['model']:
                    info['tdp'] = 125
                elif 'i7' in info['model']:
                    info['tdp'] = 95
                elif 'i5' in info['model']:
                    info['tdp'] = 65

        except Exception as e:
            logger.error(f"Failed to get CPU info: {e}")

        return info

    def _check_nvidia_gpu(self) -> bool:
        """Check for NVIDIA GPU."""
        try:
            result = subprocess.run(['nvidia-smi'], capture_output=True, timeout=2)
            return result.returncode == 0
        except:
            return False

    def _check_amd_gpu(self) -> bool:
        """Check for AMD GPU."""
        try:
            result = subprocess.run(['rocm-smi'], capture_output=True, timeout=2)
            return result.returncode == 0
        except:
            # Also check for AMDGPU driver
            return os.path.exists('/sys/class/drm/card0/device/pp_dpm_sclk')

    def _get_cooling_devices(self) -> List[Dict[str, Any]]:
        """Get available cooling devices (fans)."""
        devices = []

        try:
            # Check hwmon devices
            hwmon_path = Path('/sys/class/hwmon')
            for hwmon in hwmon_path.iterdir():
                name_file = hwmon / 'name'
                if name_file.exists():
                    name = self.read_sysfs(str(name_file), 'unknown')

                    # Check for fan controls
                    for fan_input in hwmon.glob('fan*_input'):
                        fan_num = re.search(r'fan(\d+)_input', fan_input.name)
                        if fan_num:
                            fan_id = fan_num.group(1)
                            rpm = self.read_sysfs(str(fan_input), 0)

                            device = {
                                'name': f"{name}_fan{fan_id}",
                                'path': str(hwmon),
                                'fan_num': fan_id,
                                'current_rpm': rpm,
                                'controllable': (hwmon / f'pwm{fan_id}').exists()
                            }

                            # Get min/max if available
                            min_file = hwmon / f'fan{fan_id}_min'
                            max_file = hwmon / f'fan{fan_id}_max'
                            if min_file.exists():
                                device['min_rpm'] = self.read_sysfs(str(min_file), 0)
                            if max_file.exists():
                                device['max_rpm'] = self.read_sysfs(str(max_file), 5000)

                            devices.append(device)

        except Exception as e:
            logger.error(f"Failed to get cooling devices: {e}")

        return devices

    def _get_power_sensors(self) -> List[Dict[str, Any]]:
        """Get available power sensors."""
        sensors = []

        try:
            # Check for Intel RAPL
            rapl_path = Path('/sys/class/powercap/intel-rapl')
            if rapl_path.exists():
                for domain in rapl_path.glob('intel-rapl:*'):
                    name = self.read_sysfs(str(domain / 'name'), 'unknown')
                    sensors.append({
                        'name': f"rapl_{name}",
                        'type': 'rapl',
                        'path': str(domain)
                    })

            # Check for battery sensors
            battery_path = Path('/sys/class/power_supply')
            for battery in battery_path.glob('BAT*'):
                sensors.append({
                    'name': battery.name,
                    'type': 'battery',
                    'path': str(battery)
                })

        except Exception as e:
            logger.error(f"Failed to get power sensors: {e}")

        return sensors

    def _check_rapl_support(self) -> bool:
        """Check if Intel RAPL is available."""
        return os.path.exists('/sys/class/powercap/intel-rapl')

    def get_genome_spec(self) -> Dict[str, Tuple[Any, Any, Any]]:
        """Get power/thermal genome specification."""
        spec = {
            # CPU Power Management
            'cpu_ppt': (35, self.cpu_info['tdp'] * 1.5, 5),  # Package Power Tracking
            'cpu_edc': (50, 200, 10),   # Electrical Design Current (AMD)
            'cpu_tdc': (40, 160, 10),   # Thermal Design Current (AMD)
            'cpu_pl1': (15, self.cpu_info['tdp'], 5),     # Power Limit 1 (Intel)
            'cpu_pl2': (self.cpu_info['tdp'], self.cpu_info['tdp'] * 2, 10),  # Power Limit 2

            # GPU Power Management
            'gpu_power_limit_pct': (50, 120, 5),  # % of default power limit

            # Fan Control (PWM 0-255)
            'cpu_fan_idle': (50, 100, 10),    # Idle fan PWM
            'cpu_fan_load': (100, 255, 10),   # Load fan PWM
            'cpu_fan_temp_low': (30, 50, 5),  # Low temp threshold
            'cpu_fan_temp_high': (60, 85, 5), # High temp threshold

            'case_fan_idle': (30, 80, 10),
            'case_fan_load': (80, 255, 10),

            # Voltage Offsets (millivolts)
            'cpu_undervolt_mv': (-150, 0, 10),    # CPU undervolt
            'gpu_undervolt_mv': (-100, 0, 10),    # GPU undervolt
            'cache_undervolt_mv': (-100, 0, 10),  # Cache/uncore undervolt

            # Power States
            'c_states_enabled': (0, 1, 1),        # C-states on/off
            'package_c_state_limit': (0, 8, 1),   # Package C-state limit

            # Boost behavior
            'boost_duration_ms': (1000, 60000, 1000),  # Turbo boost duration
            'boost_enabled': (0, 1, 1),                # Turbo boost on/off
        }

        return spec

    def get_safety_constraints(self) -> Dict[str, Any]:
        """Get power/thermal safety constraints."""
        return {
            'cpu_temp_c': {'max': 95},          # Max CPU temperature
            'gpu_temp_c': {'max': 87},          # Max GPU temperature
            'vrm_temp_c': {'max': 105},         # Max VRM temperature
            'thermal_throttle_events': {'eq': 0}, # No thermal throttling
            'power_throttle_events': {'eq': 0},   # No power throttling
            'system_power_w': {'max': 500},     # Max total system power
            'fan_failure': {'eq': 0}            # No fan failures
        }

    def get_default_weights(self) -> Dict[str, float]:
        """Get default fitness weights for power/thermal."""
        return {
            'perf_per_watt': 0.35,           # Maximize performance per watt
            'steady_state_temp_c': -0.15,    # Minimize steady-state temperature
            'temp_delta_c': -0.1,            # Minimize temperature swings
            'noise_level_db': -0.2,          # Minimize noise (estimated from RPM)
            'total_power_w': -0.2            # Minimize total power
        }

    def normalize_metric(self, metric_name: str, value: float) -> float:
        """Normalize power/thermal metric to [0, 1] range."""
        ranges = {
            'perf_per_watt': (0, 100),          # 0-100 ops/watt
            'steady_state_temp_c': (20, 100),   # 20-100°C
            'temp_delta_c': (0, 30),            # 0-30°C swing
            'noise_level_db': (20, 60),         # 20-60 dB
            'total_power_w': (0, 500),          # 0-500W
            'cpu_temp_c': (0, 110),             # 0-110°C
            'gpu_temp_c': (0, 100),             # 0-100°C
            'vrm_temp_c': (0, 120),             # 0-120°C
        }

        if metric_name in ranges:
            min_val, max_val = ranges[metric_name]
            normalized = (value - min_val) / (max_val - min_val)
            return max(0, min(1, normalized))
        return value

    def apply_configuration(self, config: Dict[str, Any]) -> bool:
        """Apply power/thermal configuration."""
        try:
            # Apply CPU power limits
            self._apply_cpu_power_limits(config)

            # Apply GPU power limits
            if self.has_nvidia_gpu:
                self._apply_nvidia_gpu_power(config)
            elif self.has_amd_gpu:
                self._apply_amd_gpu_power(config)

            # Apply fan curves
            self._apply_fan_curves(config)

            # Apply undervolt (requires special tools)
            self._apply_undervolt(config)

            # Apply C-states configuration
            self._apply_c_states(config)

            return True

        except Exception as e:
            logger.error(f"Failed to apply power/thermal config: {e}")
            return False

    def _apply_cpu_power_limits(self, config: Dict[str, Any]) -> bool:
        """Apply CPU power limits."""
        try:
            if self.cpu_info['vendor'] == 'intel' and self.has_rapl:
                # Intel RAPL power limits
                pl1 = int(config.get('cpu_pl1', self.cpu_info['tdp']))
                pl2 = int(config.get('cpu_pl2', self.cpu_info['tdp'] * 1.25))

                # Convert watts to microjoules
                pl1_uj = pl1 * 1000000
                pl2_uj = pl2 * 1000000

                # Write to RAPL interface
                rapl_path = Path('/sys/class/powercap/intel-rapl/intel-rapl:0')
                if rapl_path.exists():
                    self.write_sysfs(str(rapl_path / 'constraint_0_power_limit_uw'),
                                   str(pl1_uj))
                    self.write_sysfs(str(rapl_path / 'constraint_1_power_limit_uw'),
                                   str(pl2_uj))

            elif self.cpu_info['vendor'] == 'amd':
                # AMD power limits via ryzenadj (if available)
                ppt = int(config.get('cpu_ppt', self.cpu_info['tdp']))
                edc = int(config.get('cpu_edc', 140))
                tdc = int(config.get('cpu_tdc', 95))

                cmd = ['ryzenadj', '--stapm-limit', str(ppt*1000),
                       '--fast-limit', str(ppt*1000),
                       '--slow-limit', str(ppt*1000),
                       '--tctl-temp', '90',
                       '--vrmmax-current', str(edc*1000),
                       '--vrmsocmax-current', str(tdc*1000)]

                self.run_command(cmd, timeout=2)

            return True

        except Exception as e:
            logger.error(f"Failed to apply CPU power limits: {e}")
            return False

    def _apply_nvidia_gpu_power(self, config: Dict[str, Any]) -> bool:
        """Apply NVIDIA GPU power limits."""
        try:
            power_pct = config.get('gpu_power_limit_pct', 100)

            # Get default power limit
            cmd = ['nvidia-smi', '--query-gpu=power.default_limit',
                   '--format=csv,noheader,nounits']
            returncode, stdout, _ = self.run_command(cmd, timeout=2)

            if returncode == 0:
                # Handle multiple GPUs - take first line
                first_line = stdout.strip().split('\n')[0]
                default_power = float(first_line.strip())
                new_power = int(default_power * power_pct / 100)

                # Apply new power limit to all GPUs
                cmd = ['nvidia-smi', '-pl', str(new_power)]
                self.run_command(cmd, timeout=2)

            return True

        except Exception as e:
            logger.error(f"Failed to apply NVIDIA GPU power: {e}")
            return False

    def _apply_amd_gpu_power(self, config: Dict[str, Any]) -> bool:
        """Apply AMD GPU power limits."""
        try:
            power_pct = config.get('gpu_power_limit_pct', 100)

            # AMD GPU power via sysfs
            power_cap_path = '/sys/class/drm/card0/device/hwmon/hwmon*/power1_cap'
            import glob
            for path in glob.glob(power_cap_path):
                if os.path.exists(path):
                    # Get max power
                    max_path = path.replace('_cap', '_cap_max')
                    max_power = self.read_sysfs(max_path, 200000000)  # microWatts

                    # Calculate new power limit
                    new_power = int(max_power * power_pct / 100)
                    self.write_sysfs(path, str(new_power))

            return True

        except Exception as e:
            logger.error(f"Failed to apply AMD GPU power: {e}")
            return False

    def _apply_fan_curves(self, config: Dict[str, Any]) -> bool:
        """Apply fan curve configuration."""
        try:
            # CPU fan curve
            cpu_fan_idle = int(config.get('cpu_fan_idle', 80))
            cpu_fan_load = int(config.get('cpu_fan_load', 200))
            cpu_temp_low = int(config.get('cpu_fan_temp_low', 40))
            cpu_temp_high = int(config.get('cpu_fan_temp_high', 75))

            # Find CPU fan control
            for device in self.cooling_devices:
                if 'cpu' in device['name'].lower() and device['controllable']:
                    pwm_path = Path(device['path']) / f"pwm{device['fan_num']}"
                    enable_path = Path(device['path']) / f"pwm{device['fan_num']}_enable"

                    # Enable manual PWM control
                    self.write_sysfs(str(enable_path), '1')

                    # Get current temperature
                    cpu_temp = self._get_cpu_temperature()

                    # Calculate PWM based on temperature
                    if cpu_temp <= cpu_temp_low:
                        pwm = cpu_fan_idle
                    elif cpu_temp >= cpu_temp_high:
                        pwm = cpu_fan_load
                    else:
                        # Linear interpolation
                        ratio = (cpu_temp - cpu_temp_low) / (cpu_temp_high - cpu_temp_low)
                        pwm = int(cpu_fan_idle + ratio * (cpu_fan_load - cpu_fan_idle))

                    self.write_sysfs(str(pwm_path), str(pwm))

            # Case fan curve (similar logic)
            case_fan_idle = int(config.get('case_fan_idle', 50))
            case_fan_load = int(config.get('case_fan_load', 150))

            for device in self.cooling_devices:
                if 'case' in device['name'].lower() and device['controllable']:
                    pwm_path = Path(device['path']) / f"pwm{device['fan_num']}"
                    self.write_sysfs(str(pwm_path), str(case_fan_idle))

            return True

        except Exception as e:
            logger.error(f"Failed to apply fan curves: {e}")
            return False

    def _apply_undervolt(self, config: Dict[str, Any]) -> bool:
        """Apply CPU/GPU undervolt."""
        try:
            cpu_uv = int(config.get('cpu_undervolt_mv', 0))
            cache_uv = int(config.get('cache_undervolt_mv', 0))
            gpu_uv = int(config.get('gpu_undervolt_mv', 0))

            # Intel undervolt via undervolt tool
            if self.cpu_info['vendor'] == 'intel' and cpu_uv != 0:
                # Would require intel-undervolt tool
                cmd = ['intel-undervolt', 'apply',
                       f'CPU {cpu_uv}',
                       f'Cache {cache_uv}',
                       f'GPU {gpu_uv}']
                self.run_command(cmd, timeout=2)

            # AMD undervolt via p-state control
            elif self.cpu_info['vendor'] == 'amd' and cpu_uv != 0:
                # Requires kernel support for p-state voltage control
                pass

            return True

        except Exception as e:
            logger.warning(f"Failed to apply undervolt: {e}")
            return False

    def _apply_c_states(self, config: Dict[str, Any]) -> bool:
        """Apply C-state configuration."""
        try:
            c_states = bool(config.get('c_states_enabled', 1))
            c_limit = int(config.get('package_c_state_limit', 8))

            if not c_states:
                # Disable C-states
                self.write_sysfs('/sys/module/intel_idle/parameters/max_cstate', '0')
            else:
                # Set C-state limit
                self.write_sysfs('/sys/module/intel_idle/parameters/max_cstate', str(c_limit))

            return True

        except Exception as e:
            logger.warning(f"Failed to apply C-states: {e}")
            return False

    def run_probes(self, config: Dict[str, Any]) -> Dict[str, float]:
        """Run power/thermal performance probes."""
        metrics = {}

        # Apply configuration
        if not self.apply_configuration(config):
            logger.warning("Failed to apply some power/thermal configurations")

        # Run stress test with monitoring
        stress_metrics = self._run_thermal_stress_test(duration=30)
        metrics.update(stress_metrics)

        # Monitor steady-state thermals
        steady_metrics = self._monitor_steady_state(duration=10)
        metrics.update(steady_metrics)

        # Measure power efficiency
        efficiency_metrics = self._measure_power_efficiency()
        metrics.update(efficiency_metrics)

        # Estimate noise level from fan speeds
        noise_metrics = self._estimate_noise_level()
        metrics.update(noise_metrics)

        # Check for throttling
        throttle_metrics = self._check_throttling()
        metrics.update(throttle_metrics)

        return metrics

    def _run_thermal_stress_test(self, duration: int = 30) -> Dict[str, float]:
        """Run thermal stress test."""
        metrics = {}

        try:
            # Start stress test
            stress_cmd = ['stress-ng', '--cpu', str(self.cpu_info['cores']),
                         '--timeout', f'{duration}s']

            # Run stress test in background
            stress_proc = subprocess.Popen(stress_cmd, stdout=subprocess.DEVNULL,
                                         stderr=subprocess.DEVNULL)

            # Monitor temperatures during stress
            temps = []
            start_time = time.time()

            while time.time() - start_time < duration:
                cpu_temp = self._get_cpu_temperature()
                gpu_temp = self._get_gpu_temperature()
                vrm_temp = self._get_vrm_temperature()

                temps.append({
                    'cpu': cpu_temp,
                    'gpu': gpu_temp,
                    'vrm': vrm_temp,
                    'time': time.time() - start_time
                })

                time.sleep(1)

            # Wait for stress test to complete
            stress_proc.wait()

            # Calculate metrics
            cpu_temps = [t['cpu'] for t in temps]
            metrics['steady_state_temp_c'] = np.mean(cpu_temps[-10:])  # Last 10 seconds
            metrics['temp_delta_c'] = max(cpu_temps) - min(cpu_temps)
            metrics['cpu_temp_c'] = max(cpu_temps)
            metrics['gpu_temp_c'] = max(t['gpu'] for t in temps)
            metrics['vrm_temp_c'] = max(t['vrm'] for t in temps)

        except Exception as e:
            logger.error(f"Failed to run thermal stress test: {e}")
            metrics['steady_state_temp_c'] = 70
            metrics['temp_delta_c'] = 10
            metrics['cpu_temp_c'] = 75
            metrics['gpu_temp_c'] = 70
            metrics['vrm_temp_c'] = 80

        return metrics

    def _monitor_steady_state(self, duration: int = 10) -> Dict[str, float]:
        """Monitor steady-state power and temperature."""
        metrics = {}

        try:
            power_readings = []

            for _ in range(duration):
                power = self._get_system_power()
                power_readings.append(power)
                time.sleep(1)

            metrics['total_power_w'] = np.mean(power_readings)

        except Exception as e:
            logger.error(f"Failed to monitor steady state: {e}")
            metrics['total_power_w'] = 100

        return metrics

    def _measure_power_efficiency(self) -> Dict[str, float]:
        """Measure performance per watt."""
        metrics = {}

        try:
            # Run quick benchmark
            cmd = ['sysbench', 'cpu', '--cpu-max-prime=10000',
                   '--threads=1', 'run']
            start_time = time.time()
            start_power = self._get_system_power()

            returncode, stdout, _ = self.run_command(cmd, timeout=10)

            end_time = time.time()
            end_power = self._get_system_power()

            if returncode == 0:
                # Parse sysbench output for events per second
                match = re.search(r'events per second:\s*([\d.]+)', stdout)
                if match:
                    events_per_sec = float(match.group(1))
                    avg_power = (start_power + end_power) / 2
                    metrics['perf_per_watt'] = events_per_sec / max(avg_power, 1)
                else:
                    metrics['perf_per_watt'] = 10
            else:
                metrics['perf_per_watt'] = 10

        except Exception as e:
            logger.error(f"Failed to measure power efficiency: {e}")
            metrics['perf_per_watt'] = 10

        return metrics

    def _estimate_noise_level(self) -> Dict[str, float]:
        """Estimate noise level from fan speeds."""
        metrics = {}

        try:
            total_rpm = 0
            fan_count = 0

            for device in self.cooling_devices:
                fan_input = Path(device['path']) / f"fan{device['fan_num']}_input"
                if fan_input.exists():
                    rpm = self.read_sysfs(str(fan_input), 0)
                    total_rpm += rpm
                    fan_count += 1

            if fan_count > 0:
                avg_rpm = total_rpm / fan_count
                # Rough estimate: 20dB at 0 RPM, +10dB per 1000 RPM
                metrics['noise_level_db'] = 20 + (avg_rpm / 1000) * 10
            else:
                metrics['noise_level_db'] = 30  # Default

        except Exception as e:
            logger.error(f"Failed to estimate noise level: {e}")
            metrics['noise_level_db'] = 35

        return metrics

    def _check_throttling(self) -> Dict[str, float]:
        """Check for thermal and power throttling."""
        metrics = {
            'thermal_throttle_events': 0,
            'power_throttle_events': 0,
            'fan_failure': 0
        }

        try:
            # Check CPU thermal throttle
            for cpu in range(self.cpu_info['cores']):
                throttle_path = f"/sys/devices/system/cpu/cpu{cpu}/thermal_throttle/core_throttle_count"
                if os.path.exists(throttle_path):
                    count = self.read_sysfs(throttle_path, 0)
                    metrics['thermal_throttle_events'] += count

            # Check power throttle via dmesg
            cmd = ['dmesg', '-T']
            returncode, stdout, _ = self.run_command(cmd, timeout=2)
            if returncode == 0:
                power_throttle_count = stdout.count('power limit')
                metrics['power_throttle_events'] = power_throttle_count

            # Check for fan failures
            for device in self.cooling_devices:
                fan_input = Path(device['path']) / f"fan{device['fan_num']}_input"
                if fan_input.exists():
                    rpm = self.read_sysfs(str(fan_input), 0)
                    if rpm == 0 and device.get('min_rpm', 0) > 0:
                        metrics['fan_failure'] += 1

        except Exception as e:
            logger.error(f"Failed to check throttling: {e}")

        return metrics

    def _get_cpu_temperature(self) -> float:
        """Get current CPU temperature."""
        try:
            # Try coretemp
            for hwmon in Path('/sys/class/hwmon').iterdir():
                name_file = hwmon / 'name'
                if name_file.exists():
                    name = self.read_sysfs(str(name_file), '')
                    if 'coretemp' in name or 'k10temp' in name:
                        # Find temp inputs
                        temps = []
                        for temp_input in hwmon.glob('temp*_input'):
                            temp = self.read_sysfs(str(temp_input), 0)
                            if temp > 0:
                                temps.append(temp / 1000)  # Convert to Celsius
                        if temps:
                            return max(temps)

            # Fallback to thermal zones
            thermal_zone = Path('/sys/class/thermal/thermal_zone0/temp')
            if thermal_zone.exists():
                return self.read_sysfs(str(thermal_zone), 50000) / 1000

        except:
            pass
        return 50  # Default

    def _get_gpu_temperature(self) -> float:
        """Get current GPU temperature."""
        try:
            if self.has_nvidia_gpu:
                cmd = ['nvidia-smi', '--query-gpu=temperature.gpu',
                       '--format=csv,noheader,nounits']
                returncode, stdout, _ = self.run_command(cmd, timeout=2)
                if returncode == 0:
                    return float(stdout.strip())

            elif self.has_amd_gpu:
                # AMD GPU temp via hwmon
                for hwmon in Path('/sys/class/hwmon').iterdir():
                    name_file = hwmon / 'name'
                    if name_file.exists():
                        name = self.read_sysfs(str(name_file), '')
                        if 'amdgpu' in name:
                            temp_input = hwmon / 'temp1_input'
                            if temp_input.exists():
                                return self.read_sysfs(str(temp_input), 50000) / 1000

        except:
            pass
        return 50  # Default

    def _get_vrm_temperature(self) -> float:
        """Get VRM temperature if available."""
        try:
            # Look for motherboard sensors
            for hwmon in Path('/sys/class/hwmon').iterdir():
                name_file = hwmon / 'name'
                if name_file.exists():
                    name = self.read_sysfs(str(name_file), '')
                    if 'nct' in name or 'it87' in name:  # Common Super I/O chips
                        # Look for VRM temp (often labeled as temp2 or temp3)
                        for temp_num in [2, 3, 4]:
                            temp_input = hwmon / f'temp{temp_num}_input'
                            temp_label = hwmon / f'temp{temp_num}_label'
                            if temp_input.exists() and temp_label.exists():
                                label = self.read_sysfs(str(temp_label), '')
                                if 'VRM' in label or 'VR' in label:
                                    return self.read_sysfs(str(temp_input), 60000) / 1000

        except:
            pass
        return 60  # Default estimate

    def _get_system_power(self) -> float:
        """Get total system power consumption."""
        try:
            total_power = 0

            # CPU power via RAPL
            if self.has_rapl:
                rapl_path = Path('/sys/class/powercap/intel-rapl/intel-rapl:0/energy_uj')
                if rapl_path.exists():
                    energy1 = self.read_sysfs(str(rapl_path), 0)
                    time.sleep(0.1)
                    energy2 = self.read_sysfs(str(rapl_path), 0)
                    cpu_power = (energy2 - energy1) / 100000  # Convert to watts
                    total_power += cpu_power

            # GPU power
            if self.has_nvidia_gpu:
                cmd = ['nvidia-smi', '--query-gpu=power.draw',
                       '--format=csv,noheader,nounits']
                returncode, stdout, _ = self.run_command(cmd, timeout=2)
                if returncode == 0:
                    total_power += float(stdout.strip())

            # Add estimate for rest of system (motherboard, RAM, storage)
            total_power += 30  # Base system power

            return total_power

        except:
            return 100  # Default estimate


# Test function
def test_power_thermal_evaluator():
    """Test the power/thermal domain evaluator."""
    import numpy as np

    evaluator = PowerThermalDomainEvaluator()

    print(f"CPU Info: {json.dumps(evaluator.cpu_info, indent=2)}")
    print(f"Has NVIDIA GPU: {evaluator.has_nvidia_gpu}")
    print(f"Has AMD GPU: {evaluator.has_amd_gpu}")
    print(f"Has RAPL: {evaluator.has_rapl}")
    print(f"Cooling Devices: {len(evaluator.cooling_devices)}")
    print(f"Power Sensors: {len(evaluator.power_sensors)}")

    # Test with random genome
    genome_size = len(evaluator.get_genome_spec())
    genome = np.random.randn(genome_size).tolist()

    print(f"\nTesting power/thermal evaluator with genome size {genome_size}")

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
    test_power_thermal_evaluator()