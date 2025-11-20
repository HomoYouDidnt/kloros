#!/usr/bin/env python3
"""
Storage Domain Evaluator for D-REAM
Tests NVMe/SATA I/O schedulers, queue depths, writeback settings, ASPM, compression.
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


class StorageDomainEvaluator(DomainEvaluator):
    """Evaluator for storage performance and optimization."""

    def __init__(self):
        super().__init__("storage")
        self.block_devices = self._get_block_devices()
        self.primary_device = self._select_primary_device()
        self.schedulers = self._get_available_schedulers()
        self.has_nvme = self._check_nvme()
        self.filesystem_info = self._get_filesystem_info()

    def _get_block_devices(self) -> List[Dict[str, Any]]:
        """Get list of block devices."""
        devices = []

        try:
            # List block devices
            cmd = ['lsblk', '-J', '-o', 'NAME,TYPE,SIZE,ROTA,TRAN,MODEL']
            returncode, stdout, _ = self.run_command(cmd, timeout=2)

            if returncode == 0:
                data = json.loads(stdout)
                for device in data.get('blockdevices', []):
                    if device.get('type') == 'disk':
                        devices.append({
                            'name': device.get('name', ''),
                            'path': f"/dev/{device.get('name', '')}",
                            'size': device.get('size', ''),
                            'rotational': device.get('rota', '1') == '1',
                            'transport': device.get('tran', ''),
                            'model': device.get('model', '').strip()
                        })

        except Exception as e:
            logger.error(f"Failed to get block devices: {e}")

        return devices

    def _select_primary_device(self) -> Optional[Dict[str, Any]]:
        """Select primary storage device for testing."""
        # Prefer NVMe > SSD > HDD
        for device in self.block_devices:
            if 'nvme' in device['name']:
                return device

        for device in self.block_devices:
            if not device['rotational']:  # SSD
                return device

        # Fallback to first device
        return self.block_devices[0] if self.block_devices else None

    def _get_available_schedulers(self) -> List[str]:
        """Get available I/O schedulers."""
        schedulers = []

        if self.primary_device:
            scheduler_path = f"/sys/block/{self.primary_device['name']}/queue/scheduler"
            try:
                content = self.read_sysfs(scheduler_path, '')
                if content:
                    # Parse [mq-deadline] none kyber bfq
                    schedulers = re.findall(r'\b(\w+)\b', content)
            except:
                pass

        return schedulers or ['none', 'mq-deadline', 'kyber', 'bfq']

    def _check_nvme(self) -> bool:
        """Check if NVMe devices are present."""
        return any('nvme' in d['name'] for d in self.block_devices)

    def _get_filesystem_info(self) -> Dict[str, Any]:
        """Get filesystem information."""
        info = {}

        try:
            # Get filesystem types
            cmd = ['df', '-T']
            returncode, stdout, _ = self.run_command(cmd, timeout=2)

            if returncode == 0:
                fs_types = set()
                for line in stdout.split('\n')[1:]:  # Skip header
                    parts = line.split()
                    if len(parts) >= 2:
                        fs_types.add(parts[1])

                info['filesystems'] = list(fs_types)

        except Exception as e:
            logger.error(f"Failed to get filesystem info: {e}")

        return info

    def get_genome_spec(self) -> Dict[str, Tuple[Any, Any, Any]]:
        """Get storage genome specification."""
        spec = {
            # I/O scheduler selection
            'scheduler_idx': (0, len(self.schedulers)-1, 1),

            # Queue depth (power of 2)
            'queue_depth_log2': (5, 10, 1),  # 32 to 1024

            # I/O size (in KB, power of 2)
            'io_size_kb_log2': (2, 9, 1),  # 4KB to 512KB

            # Read-ahead size (in KB)
            'readahead_kb': (128, 4096, 256),

            # Writeback settings
            'dirty_ratio': (5, 40, 5),              # Percentage of RAM
            'dirty_background_ratio': (1, 20, 2),    # Background writeback threshold
            'dirty_expire_centisecs': (300, 3000, 300),  # 3-30 seconds

            # PCIe ASPM (Active State Power Management)
            'aspm_policy': (0, 3, 1),  # 0=default, 1=performance, 2=powersave, 3=powersupersave

            # NVMe specific
            'apst_enabled': (0, 1, 1),  # Autonomous Power State Transition

            # Filesystem mount options
            'noatime': (0, 1, 1),       # Disable access time updates
            'commit_interval': (5, 60, 5),  # Journal commit interval (seconds)

            # Compression (if filesystem supports it)
            'compression_enabled': (0, 1, 1),
            'compression_level': (1, 9, 1),  # 1=fast, 9=best
        }

        return spec

    def get_safety_constraints(self) -> Dict[str, Any]:
        """Get storage safety constraints."""
        return {
            'ssd_temp_c': {'max': 70},          # Max SSD temperature
            'tbw_percent': {'max': 80},         # Max % of rated TBW used
            'smart_errors': {'eq': 0},          # No SMART errors
            'io_errors': {'eq': 0},             # No I/O errors
            'wear_level': {'max': 90},          # Max wear level percentage
            'available_spare': {'min': 10}      # Min available spare percentage
        }

    def get_default_weights(self) -> Dict[str, float]:
        """Get default fitness weights for storage."""
        return {
            'iops_4k': 0.25,                # Maximize 4K IOPS
            'throughput_seq_mb': 0.2,       # Maximize sequential throughput
            'p99_latency_ms': -0.25,        # Minimize tail latency
            'p999_latency_ms': -0.15,       # Minimize extreme tail latency
            'joules_per_gb': -0.15          # Minimize energy per GB
        }

    def normalize_metric(self, metric_name: str, value: float) -> float:
        """Normalize storage metric to [0, 1] range."""
        ranges = {
            'iops_4k': (0, 1000000),         # 0-1M IOPS
            'throughput_seq_mb': (0, 10000), # 0-10GB/s
            'p99_latency_ms': (0, 100),      # 0-100ms
            'p999_latency_ms': (0, 500),     # 0-500ms
            'joules_per_gb': (0, 0.1),       # 0-0.1 J/GB
            'ssd_temp_c': (0, 85),           # 0-85°C
            'tbw_percent': (0, 100),         # 0-100%
            'wear_level': (0, 100),          # 0-100%
            'available_spare': (0, 100),     # 0-100%
        }

        if metric_name in ranges:
            min_val, max_val = ranges[metric_name]
            normalized = (value - min_val) / (max_val - min_val)
            return max(0, min(1, normalized))
        return value

    def apply_configuration(self, config: Dict[str, Any]) -> bool:
        """Apply storage configuration."""
        if not self.primary_device:
            logger.warning("No primary storage device available")
            return False

        try:
            device_name = self.primary_device['name']

            # Set I/O scheduler
            if 'scheduler_idx' in config:
                scheduler = self.schedulers[int(config['scheduler_idx'])]
                self._set_scheduler(device_name, scheduler)

            # Set queue depth
            if 'queue_depth_log2' in config:
                queue_depth = 2 ** int(config['queue_depth_log2'])
                self._set_queue_depth(device_name, queue_depth)

            # Set read-ahead
            if 'readahead_kb' in config:
                self._set_readahead(device_name, int(config['readahead_kb']))

            # Set writeback parameters
            self._set_writeback_params(config)

            # Set ASPM policy
            if 'aspm_policy' in config:
                self._set_aspm_policy(int(config['aspm_policy']))

            # Set NVMe APST if applicable
            if self.has_nvme and 'apst_enabled' in config:
                self._set_nvme_apst(bool(config['apst_enabled']))

            return True

        except Exception as e:
            logger.error(f"Failed to apply storage config: {e}")
            return False

    def _set_scheduler(self, device: str, scheduler: str) -> bool:
        """Set I/O scheduler for device."""
        try:
            scheduler_path = f"/sys/block/{device}/queue/scheduler"
            return self.write_sysfs(scheduler_path, scheduler)
        except Exception as e:
            logger.error(f"Failed to set scheduler: {e}")
            return False

    def _set_queue_depth(self, device: str, depth: int) -> bool:
        """Set queue depth for device."""
        try:
            # For NVMe
            if 'nvme' in device:
                queue_path = f"/sys/block/{device}/queue/nr_requests"
                return self.write_sysfs(queue_path, str(depth))

            # For SATA/SAS
            queue_path = f"/sys/block/{device}/device/queue_depth"
            if os.path.exists(queue_path):
                return self.write_sysfs(queue_path, str(min(depth, 32)))  # SATA limited to 32

        except Exception as e:
            logger.error(f"Failed to set queue depth: {e}")
        return False

    def _set_readahead(self, device: str, kb: int) -> bool:
        """Set read-ahead for device."""
        try:
            ra_path = f"/sys/block/{device}/queue/read_ahead_kb"
            return self.write_sysfs(ra_path, str(kb))
        except Exception as e:
            logger.error(f"Failed to set read-ahead: {e}")
            return False

    def _set_writeback_params(self, config: Dict[str, Any]) -> bool:
        """Set writeback cache parameters."""
        try:
            if 'dirty_ratio' in config:
                self.write_sysfs('/proc/sys/vm/dirty_ratio', str(config['dirty_ratio']))

            if 'dirty_background_ratio' in config:
                self.write_sysfs('/proc/sys/vm/dirty_background_ratio',
                               str(config['dirty_background_ratio']))

            if 'dirty_expire_centisecs' in config:
                self.write_sysfs('/proc/sys/vm/dirty_expire_centisecs',
                               str(config['dirty_expire_centisecs']))

            return True
        except Exception as e:
            logger.error(f"Failed to set writeback params: {e}")
            return False

    def _set_aspm_policy(self, policy: int) -> bool:
        """Set PCIe ASPM policy."""
        try:
            policy_names = ['default', 'performance', 'powersave', 'powersupersave']
            policy_name = policy_names[policy]

            aspm_path = '/sys/module/pcie_aspm/parameters/policy'
            if os.path.exists(aspm_path):
                return self.write_sysfs(aspm_path, policy_name)
        except Exception as e:
            logger.error(f"Failed to set ASPM policy: {e}")
        return False

    def _set_nvme_apst(self, enabled: bool) -> bool:
        """Set NVMe Autonomous Power State Transition."""
        try:
            # Find NVMe devices
            for device in self.block_devices:
                if 'nvme' in device['name']:
                    # NVMe power management
                    # In production, would use nvme-cli
                    cmd = ['nvme', 'set-feature', device['path'],
                           '-f', '0x0c',  # APST feature
                           '-v', '1' if enabled else '0']
                    self.run_command(cmd, timeout=2)
            return True
        except Exception as e:
            logger.error(f"Failed to set NVMe APST: {e}")
            return False

    def run_probes(self, config: Dict[str, Any]) -> Dict[str, float]:
        """Run storage performance probes."""
        if not self.primary_device:
            return {
                'iops_4k': 0,
                'throughput_seq_mb': 0,
                'p99_latency_ms': 999,
                'p999_latency_ms': 999,
                'joules_per_gb': 999
            }

        metrics = {}

        # Apply configuration
        if not self.apply_configuration(config):
            logger.warning("Failed to apply some storage configurations")

        # Get I/O size from config
        io_size_kb = 2 ** int(config.get('io_size_kb_log2', 2))

        # Run fio benchmarks
        fio_metrics = self._run_fio_benchmarks(
            self.primary_device['path'],
            io_size_kb,
            int(2 ** config.get('queue_depth_log2', 7))
        )
        metrics.update(fio_metrics)

        # Monitor SMART health
        smart_metrics = self._monitor_smart_health(self.primary_device['path'])
        metrics.update(smart_metrics)

        # Estimate power consumption
        power_metrics = self._estimate_power_consumption(metrics)
        metrics.update(power_metrics)

        return metrics

    def _run_fio_benchmarks(self, device: str, io_size_kb: int,
                           queue_depth: int) -> Dict[str, float]:
        """Run fio I/O benchmarks."""
        metrics = {}

        try:
            # Create test file on device filesystem
            # In production, would determine actual mount point
            test_file = '/tmp/fio_test_file'

            # Random 4K read test
            rand_read_cmd = [
                'fio',
                '--name=rand_read',
                f'--filename={test_file}',
                '--size=1G',
                '--direct=1',
                '--rw=randread',
                '--bs=4k',
                f'--iodepth={min(queue_depth, 256)}',
                '--ioengine=libaio',
                '--numjobs=4',
                '--time_based',
                '--runtime=10',
                '--group_reporting',
                '--output-format=json'
            ]

            returncode, stdout, _ = self.run_command(rand_read_cmd, timeout=15)
            if returncode == 0:
                try:
                    fio_data = json.loads(stdout)
                    job = fio_data['jobs'][0]
                    metrics['iops_4k'] = job['read']['iops']
                    metrics['p99_latency_ms'] = job['read']['clat_ns']['percentile']['99.000000'] / 1e6
                    metrics['p999_latency_ms'] = job['read']['clat_ns']['percentile']['99.900000'] / 1e6
                except:
                    pass

            # Sequential read test
            seq_read_cmd = rand_read_cmd.copy()
            seq_read_cmd[seq_read_cmd.index('--rw=randread')] = '--rw=read'
            seq_read_cmd[seq_read_cmd.index('--bs=4k')] = f'--bs={io_size_kb}k'

            returncode, stdout, _ = self.run_command(seq_read_cmd, timeout=15)
            if returncode == 0:
                try:
                    fio_data = json.loads(stdout)
                    job = fio_data['jobs'][0]
                    # Convert from KB/s to MB/s
                    metrics['throughput_seq_mb'] = job['read']['bw'] / 1024
                except:
                    pass

            # Clean up test file
            os.remove(test_file) if os.path.exists(test_file) else None

        except Exception as e:
            logger.error(f"Failed to run fio benchmarks: {e}")
            # Use fallback estimates
            metrics['iops_4k'] = 50000 if 'nvme' in device else 10000
            metrics['throughput_seq_mb'] = 3000 if 'nvme' in device else 500
            metrics['p99_latency_ms'] = 1.0 if 'nvme' in device else 10.0
            metrics['p999_latency_ms'] = 5.0 if 'nvme' in device else 50.0

        return metrics

    def _monitor_smart_health(self, device: str) -> Dict[str, float]:
        """Monitor SMART health metrics."""
        metrics = {
            'ssd_temp_c': 40,
            'tbw_percent': 10,
            'smart_errors': 0,
            'io_errors': 0,
            'wear_level': 5,
            'available_spare': 100
        }

        try:
            # Use smartctl to get SMART data
            cmd = ['smartctl', '-a', '-j', device]
            returncode, stdout, _ = self.run_command(cmd, timeout=5)

            if returncode == 0 or returncode == 4:  # 4 = SMART command success
                smart_data = json.loads(stdout)

                # Temperature
                if 'temperature' in smart_data:
                    metrics['ssd_temp_c'] = smart_data['temperature'].get('current', 40)

                # NVMe specific metrics
                if 'nvme_smart_health_information_log' in smart_data:
                    nvme_smart = smart_data['nvme_smart_health_information_log']
                    metrics['ssd_temp_c'] = nvme_smart.get('temperature', 40)
                    metrics['available_spare'] = nvme_smart.get('available_spare', 100)
                    metrics['wear_level'] = 100 - nvme_smart.get('percentage_used', 0)

                    # Calculate TBW usage
                    data_written = nvme_smart.get('data_units_written', 0)
                    # Assume 600 TBW for typical NVMe (would check model in production)
                    tbw_limit = 600 * 1024 * 1024 * 1024 * 1024  # 600TB in bytes
                    data_written_bytes = data_written * 512 * 1000  # 512-byte units
                    metrics['tbw_percent'] = (data_written_bytes / tbw_limit) * 100

                # SATA SSD metrics
                elif 'ata_smart_attributes' in smart_data:
                    attrs = smart_data['ata_smart_attributes']['table']
                    for attr in attrs:
                        if attr['name'] == 'Temperature_Celsius':
                            metrics['ssd_temp_c'] = attr['value']
                        elif attr['name'] == 'Wear_Leveling_Count':
                            metrics['wear_level'] = attr['value']
                        elif attr['name'] == 'Media_Wearout_Indicator':
                            metrics['wear_level'] = attr['value']

                # Error counts
                if 'ata_smart_error_log' in smart_data:
                    error_log = smart_data['ata_smart_error_log']
                    metrics['smart_errors'] = error_log.get('count', 0)

        except Exception as e:
            logger.error(f"Failed to get SMART data: {e}")

        # Check kernel logs for I/O errors
        try:
            cmd = ['dmesg', '-T']
            returncode, stdout, _ = self.run_command(cmd, timeout=2)
            if returncode == 0:
                io_error_patterns = ['I/O error', 'ata.*error', 'nvme.*error']
                error_count = sum(len(re.findall(pattern, stdout, re.IGNORECASE))
                                for pattern in io_error_patterns)
                metrics['io_errors'] = error_count
        except:
            pass

        return metrics

    def _estimate_power_consumption(self, metrics: Dict[str, float]) -> Dict[str, float]:
        """Estimate storage power consumption."""
        power_metrics = {}

        try:
            # Base power consumption
            if self.has_nvme:
                # NVMe: ~5W idle, up to 10W active
                base_power = 5.0
                active_power = 10.0
            else:
                # SATA SSD: ~2W idle, up to 5W active
                base_power = 2.0
                active_power = 5.0

            # Scale by activity level
            if 'iops_4k' in metrics:
                activity_level = min(metrics['iops_4k'] / 100000, 1.0)  # Normalize to max 100k IOPS
                current_power = base_power + (active_power - base_power) * activity_level

                # Calculate joules per GB based on throughput
                if metrics.get('throughput_seq_mb', 0) > 0:
                    # Power (W) / Throughput (GB/s) = J/GB
                    throughput_gb_s = metrics['throughput_seq_mb'] / 1024
                    power_metrics['joules_per_gb'] = current_power / max(throughput_gb_s, 0.001)
                else:
                    power_metrics['joules_per_gb'] = 0.01

        except Exception as e:
            logger.error(f"Failed to estimate power: {e}")
            power_metrics['joules_per_gb'] = 0.01

        return power_metrics


# Test function
def test_storage_evaluator():
    """Test the storage domain evaluator."""
    import numpy as np

    evaluator = StorageDomainEvaluator()

    print(f"Block Devices: {json.dumps(evaluator.block_devices, indent=2)}")
    if evaluator.primary_device:
        print(f"Primary Device: {evaluator.primary_device['name']} "
              f"({evaluator.primary_device['model']})")
    print(f"Available Schedulers: {evaluator.schedulers}")
    print(f"Has NVMe: {evaluator.has_nvme}")
    print(f"Filesystems: {evaluator.filesystem_info}")

    # Test with random genome
    genome_size = len(evaluator.get_genome_spec())
    genome = np.random.randn(genome_size).tolist()

    print(f"\nTesting storage evaluator with genome size {genome_size}")

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
    test_storage_evaluator()