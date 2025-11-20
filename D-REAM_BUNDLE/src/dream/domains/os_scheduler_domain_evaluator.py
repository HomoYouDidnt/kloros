#!/usr/bin/env python3
"""
OS/Scheduler Domain Evaluator for D-REAM
Tests kernel schedulers, IRQ affinity, cgroups, vm settings, hugepages, and system tuning.
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
import psutil

from .domain_evaluator_base import DomainEvaluator

logger = logging.getLogger(__name__)


class OSSchedulerDomainEvaluator(DomainEvaluator):
    """Evaluator for OS and scheduler performance."""

    def __init__(self):
        super().__init__("os_scheduler")
        self.cpu_count = psutil.cpu_count()
        self.memory_gb = psutil.virtual_memory().total / (1024**3)
        self.kernel_version = self._get_kernel_version()
        self.available_governors = self._get_cpu_governors()
        self.has_cgroups_v2 = self._check_cgroups_v2()
        self.has_zram = self._check_zram()
        self.irq_info = self._get_irq_info()

    def _get_kernel_version(self) -> str:
        """Get kernel version."""
        try:
            with open('/proc/version', 'r') as f:
                version = f.read().strip()
                match = re.search(r'Linux version (\S+)', version)
                if match:
                    return match.group(1)
        except:
            pass
        return "unknown"

    def _get_cpu_governors(self) -> List[str]:
        """Get available CPU governors."""
        try:
            gov_file = '/sys/devices/system/cpu/cpu0/cpufreq/scaling_available_governors'
            if os.path.exists(gov_file):
                with open(gov_file, 'r') as f:
                    return f.read().strip().split()
        except:
            pass
        return ['performance', 'powersave', 'schedutil', 'ondemand']

    def _check_cgroups_v2(self) -> bool:
        """Check if cgroups v2 is available."""
        return os.path.exists('/sys/fs/cgroup/cgroup.controllers')

    def _check_zram(self) -> bool:
        """Check if zram is available."""
        return os.path.exists('/sys/class/zram-control')

    def _get_irq_info(self) -> Dict[str, Any]:
        """Get IRQ information."""
        info = {
            'total_irqs': 0,
            'network_irqs': [],
            'storage_irqs': [],
            'usb_irqs': []
        }

        try:
            with open('/proc/interrupts', 'r') as f:
                for line in f:
                    if ':' in line:
                        info['total_irqs'] += 1
                        # Identify device IRQs
                        if 'eth' in line or 'enp' in line or 'wlan' in line:
                            irq_num = line.split(':')[0].strip()
                            info['network_irqs'].append(int(irq_num))
                        elif 'nvme' in line or 'ahci' in line or 'sata' in line:
                            irq_num = line.split(':')[0].strip()
                            info['storage_irqs'].append(int(irq_num))
                        elif 'usb' in line or 'xhci' in line:
                            irq_num = line.split(':')[0].strip()
                            info['usb_irqs'].append(int(irq_num))
        except:
            pass

        return info

    def get_genome_spec(self) -> Dict[str, Tuple[Any, Any, Any]]:
        """Get OS/scheduler genome specification."""
        spec = {
            # CPU scheduler and governor
            'cpu_governor_idx': (0, len(self.available_governors)-1, 1),
            'sched_migration_cost_ns': (100000, 10000000, 100000),  # 0.1-10ms
            'sched_min_granularity_ns': (1000000, 10000000, 500000),  # 1-10ms
            'sched_wakeup_granularity_ns': (1000000, 20000000, 1000000),  # 1-20ms

            # IRQ affinity (CPU mask as percentage)
            'irq_cpu_isolation': (0.0, 0.5, 0.1),  # Isolate up to 50% CPUs for IRQs
            'irq_balance_enabled': (0, 1, 1),      # IRQ balancing on/off

            # Memory management
            'vm_swappiness': (0, 100, 10),           # Swap tendency
            'vm_vfs_cache_pressure': (50, 200, 25),  # Cache vs memory pressure
            'vm_dirty_ratio': (5, 40, 5),            # Dirty page threshold
            'vm_dirty_background_ratio': (1, 20, 2),  # Background writeback
            'vm_min_free_kbytes': (16384, 524288, 32768),  # Min free memory

            # Transparent hugepages
            'thp_enabled': (0, 2, 1),  # 0=never, 1=madvise, 2=always
            'thp_defrag': (0, 2, 1),   # 0=never, 1=defer, 2=always

            # NUMA settings
            'numa_balancing': (0, 1, 1),  # NUMA balancing on/off
            'zone_reclaim_mode': (0, 1, 1),  # Zone reclaim on/off

            # ZRAM settings (if available)
            'zram_enabled': (0, 1, 1),
            'zram_size_pct': (0, 50, 10),  # % of RAM for zram
            'zram_compression': (0, 3, 1),  # 0=lzo, 1=lz4, 2=zstd, 3=lzo-rle

            # Process scheduling
            'autogroup_enabled': (0, 1, 1),  # Process autogroups
            'sched_child_runs_first': (0, 1, 1),  # Child process priority
        }

        return spec

    def get_safety_constraints(self) -> Dict[str, Any]:
        """Get OS/scheduler safety constraints."""
        return {
            'memory_pressure': {'max': 0.8},      # Max 80% memory pressure
            'oom_kills': {'eq': 0},               # No OOM kills
            'load_average': {'max': self.cpu_count * 2},  # Max 2x CPU count
            'context_switches_sec': {'max': 100000},  # Max context switches/sec
            'fork_failures': {'eq': 0},           # No fork failures
            'irq_storms': {'eq': 0}               # No IRQ storms
        }

    def get_default_weights(self) -> Dict[str, float]:
        """Get default fitness weights for OS/scheduler."""
        return {
            'target_latency_ms': -0.3,          # Minimize target workload latency
            'context_switches_sec': -0.15,      # Minimize context switches
            'cache_hit_rate': 0.2,              # Maximize cache hit rate
            'memory_bandwidth_gb': 0.15,        # Maximize memory bandwidth
            'scheduler_efficiency': 0.2         # Maximize scheduler efficiency
        }

    def normalize_metric(self, metric_name: str, value: float) -> float:
        """Normalize OS/scheduler metric to [0, 1] range."""
        ranges = {
            'target_latency_ms': (0, 100),           # 0-100ms
            'context_switches_sec': (0, 200000),     # 0-200k/sec
            'cache_hit_rate': (0, 1),                # 0-100%
            'memory_bandwidth_gb': (0, 100),         # 0-100 GB/s
            'scheduler_efficiency': (0, 1),          # 0-100%
            'memory_pressure': (0, 1),               # 0-100%
            'load_average': (0, self.cpu_count * 4), # 0-4x CPUs
            'oom_kills': (0, 10),                    # 0-10 kills
        }

        if metric_name in ranges:
            min_val, max_val = ranges[metric_name]
            normalized = (value - min_val) / (max_val - min_val)
            return max(0, min(1, normalized))
        return value

    def apply_configuration(self, config: Dict[str, Any]) -> bool:
        """Apply OS/scheduler configuration."""
        try:
            # Apply CPU governor
            self._apply_cpu_governor(config)

            # Apply scheduler tunables
            self._apply_scheduler_tunables(config)

            # Apply IRQ affinity
            self._apply_irq_affinity(config)

            # Apply VM settings
            self._apply_vm_settings(config)

            # Apply transparent hugepages
            self._apply_thp_settings(config)

            # Apply NUMA settings
            self._apply_numa_settings(config)

            # Configure ZRAM if available
            if self.has_zram:
                self._configure_zram(config)

            # Apply process scheduling settings
            self._apply_process_scheduling(config)

            return True

        except Exception as e:
            logger.error(f"Failed to apply OS/scheduler config: {e}")
            return False

    def _apply_cpu_governor(self, config: Dict[str, Any]) -> bool:
        """Apply CPU governor setting."""
        try:
            gov_idx = int(config.get('cpu_governor_idx', 0))
            governor = self.available_governors[gov_idx]

            for cpu in range(self.cpu_count):
                gov_path = f"/sys/devices/system/cpu/cpu{cpu}/cpufreq/scaling_governor"
                if os.path.exists(gov_path):
                    self.write_sysfs(gov_path, governor)

            return True
        except Exception as e:
            logger.error(f"Failed to apply CPU governor: {e}")
            return False

    def _apply_scheduler_tunables(self, config: Dict[str, Any]) -> bool:
        """Apply scheduler tunables."""
        try:
            # CFS scheduler tunables
            tunables = {
                'sched_migration_cost_ns': '/proc/sys/kernel/sched_migration_cost_ns',
                'sched_min_granularity_ns': '/proc/sys/kernel/sched_min_granularity_ns',
                'sched_wakeup_granularity_ns': '/proc/sys/kernel/sched_wakeup_granularity_ns'
            }

            for param, path in tunables.items():
                if param in config and os.path.exists(path):
                    value = int(config[param])
                    self.write_sysfs(path, str(value))

            # Child runs first
            if 'sched_child_runs_first' in config:
                path = '/proc/sys/kernel/sched_child_runs_first'
                if os.path.exists(path):
                    self.write_sysfs(path, str(int(config['sched_child_runs_first'])))

            return True
        except Exception as e:
            logger.error(f"Failed to apply scheduler tunables: {e}")
            return False

    def _apply_irq_affinity(self, config: Dict[str, Any]) -> bool:
        """Apply IRQ affinity settings."""
        try:
            irq_isolation = config.get('irq_cpu_isolation', 0.0)
            irq_balance = config.get('irq_balance_enabled', 1)

            # Configure irqbalance
            if irq_balance:
                subprocess.run(['systemctl', 'start', 'irqbalance'],
                             capture_output=True)
            else:
                subprocess.run(['systemctl', 'stop', 'irqbalance'],
                             capture_output=True)

                # Manual IRQ affinity if balancing disabled
                if irq_isolation > 0:
                    # Isolate IRQs to specific CPUs
                    isolated_cpus = int(self.cpu_count * irq_isolation)
                    irq_cpus = list(range(isolated_cpus))
                    cpu_mask = sum(1 << cpu for cpu in irq_cpus)

                    # Apply to network IRQs
                    for irq in self.irq_info['network_irqs']:
                        affinity_path = f"/proc/irq/{irq}/smp_affinity"
                        if os.path.exists(affinity_path):
                            self.write_sysfs(affinity_path, f"{cpu_mask:x}")

                    # Apply to storage IRQs
                    for irq in self.irq_info['storage_irqs']:
                        affinity_path = f"/proc/irq/{irq}/smp_affinity"
                        if os.path.exists(affinity_path):
                            self.write_sysfs(affinity_path, f"{cpu_mask:x}")

            return True
        except Exception as e:
            logger.error(f"Failed to apply IRQ affinity: {e}")
            return False

    def _apply_vm_settings(self, config: Dict[str, Any]) -> bool:
        """Apply VM settings."""
        try:
            vm_settings = {
                'vm_swappiness': '/proc/sys/vm/swappiness',
                'vm_vfs_cache_pressure': '/proc/sys/vm/vfs_cache_pressure',
                'vm_dirty_ratio': '/proc/sys/vm/dirty_ratio',
                'vm_dirty_background_ratio': '/proc/sys/vm/dirty_background_ratio',
                'vm_min_free_kbytes': '/proc/sys/vm/min_free_kbytes'
            }

            for param, path in vm_settings.items():
                if param in config and os.path.exists(path):
                    value = int(config[param])
                    self.write_sysfs(path, str(value))

            # Zone reclaim mode
            if 'zone_reclaim_mode' in config:
                path = '/proc/sys/vm/zone_reclaim_mode'
                if os.path.exists(path):
                    self.write_sysfs(path, str(int(config['zone_reclaim_mode'])))

            return True
        except Exception as e:
            logger.error(f"Failed to apply VM settings: {e}")
            return False

    def _apply_thp_settings(self, config: Dict[str, Any]) -> bool:
        """Apply transparent hugepages settings."""
        try:
            thp_enabled = int(config.get('thp_enabled', 1))
            thp_defrag = int(config.get('thp_defrag', 1))

            # THP enabled setting
            enabled_values = ['never', 'madvise', 'always']
            thp_enabled_path = '/sys/kernel/mm/transparent_hugepage/enabled'
            if os.path.exists(thp_enabled_path):
                self.write_sysfs(thp_enabled_path, enabled_values[thp_enabled])

            # THP defrag setting
            defrag_values = ['never', 'defer', 'always']
            thp_defrag_path = '/sys/kernel/mm/transparent_hugepage/defrag'
            if os.path.exists(thp_defrag_path):
                self.write_sysfs(thp_defrag_path, defrag_values[thp_defrag])

            # Khugepaged settings
            khugepaged_path = '/sys/kernel/mm/transparent_hugepage/khugepaged'
            if os.path.exists(khugepaged_path):
                # Tune khugepaged for better performance
                self.write_sysfs(f"{khugepaged_path}/scan_sleep_millisecs", "1000")
                self.write_sysfs(f"{khugepaged_path}/alloc_sleep_millisecs", "60000")
                self.write_sysfs(f"{khugepaged_path}/pages_to_scan", "4096")

            return True
        except Exception as e:
            logger.error(f"Failed to apply THP settings: {e}")
            return False

    def _apply_numa_settings(self, config: Dict[str, Any]) -> bool:
        """Apply NUMA settings."""
        try:
            numa_balancing = config.get('numa_balancing', 1)

            # NUMA balancing
            numa_path = '/proc/sys/kernel/numa_balancing'
            if os.path.exists(numa_path):
                self.write_sysfs(numa_path, str(int(numa_balancing)))

            return True
        except Exception as e:
            logger.error(f"Failed to apply NUMA settings: {e}")
            return False

    def _configure_zram(self, config: Dict[str, Any]) -> bool:
        """Configure ZRAM swap."""
        try:
            zram_enabled = config.get('zram_enabled', 0)

            if not zram_enabled:
                # Disable zram
                subprocess.run(['swapoff', '/dev/zram0'], capture_output=True)
                return True

            zram_size_pct = config.get('zram_size_pct', 25)
            zram_compression = int(config.get('zram_compression', 1))

            # Calculate zram size
            zram_size_mb = int(self.memory_gb * 1024 * zram_size_pct / 100)

            # Compression algorithms
            algorithms = ['lzo', 'lz4', 'zstd', 'lzo-rle']
            algorithm = algorithms[zram_compression]

            # Reset zram device
            subprocess.run(['swapoff', '/dev/zram0'], capture_output=True)
            self.write_sysfs('/sys/block/zram0/reset', '1')

            # Configure zram
            self.write_sysfs('/sys/block/zram0/comp_algorithm', algorithm)
            self.write_sysfs('/sys/block/zram0/disksize', str(zram_size_mb * 1024 * 1024))

            # Enable zram swap
            subprocess.run(['mkswap', '/dev/zram0'], capture_output=True)
            subprocess.run(['swapon', '/dev/zram0'], capture_output=True)

            return True
        except Exception as e:
            logger.error(f"Failed to configure ZRAM: {e}")
            return False

    def _apply_process_scheduling(self, config: Dict[str, Any]) -> bool:
        """Apply process scheduling settings."""
        try:
            # Autogroups
            autogroup = config.get('autogroup_enabled', 1)
            autogroup_path = '/proc/sys/kernel/sched_autogroup_enabled'
            if os.path.exists(autogroup_path):
                self.write_sysfs(autogroup_path, str(int(autogroup)))

            return True
        except Exception as e:
            logger.error(f"Failed to apply process scheduling: {e}")
            return False

    def run_probes(self, config: Dict[str, Any]) -> Dict[str, float]:
        """Run OS/scheduler performance probes."""
        metrics = {}

        # Apply configuration
        if not self.apply_configuration(config):
            logger.warning("Failed to apply some OS/scheduler configurations")

        # Run workload latency test
        latency_metrics = self._test_workload_latency()
        metrics.update(latency_metrics)

        # Monitor context switches
        context_metrics = self._monitor_context_switches()
        metrics.update(context_metrics)

        # Test memory performance
        memory_metrics = self._test_memory_performance()
        metrics.update(memory_metrics)

        # Measure scheduler efficiency
        scheduler_metrics = self._measure_scheduler_efficiency()
        metrics.update(scheduler_metrics)

        # Check system health
        health_metrics = self._check_system_health()
        metrics.update(health_metrics)

        return metrics

    def _test_workload_latency(self) -> Dict[str, float]:
        """Test target workload latency."""
        metrics = {}

        try:
            # Run cyclictest for latency measurement
            cmd = ['cyclictest', '-m', '-n', '-q', '-l', '1000', '-h', '100']
            returncode, stdout, stderr = self.run_command(cmd, timeout=10)

            if returncode == 0:
                # Parse cyclictest output
                lines = stdout.split('\n')
                for line in lines:
                    if 'Max Latencies' in line:
                        match = re.search(r'(\d+)', line)
                        if match:
                            metrics['target_latency_ms'] = float(match.group(1)) / 1000
                            break
            else:
                # Fallback: use hackbench for latency test
                metrics['target_latency_ms'] = self._run_hackbench()

        except Exception as e:
            logger.error(f"Failed to test workload latency: {e}")
            metrics['target_latency_ms'] = 10.0

        return metrics

    def _run_hackbench(self) -> float:
        """Run hackbench for scheduling latency test."""
        try:
            # Run hackbench
            cmd = ['hackbench', '-l', '1000', '-g', '10']
            start_time = time.time()
            returncode, _, _ = self.run_command(cmd, timeout=30)
            elapsed = time.time() - start_time

            if returncode == 0:
                # Convert to approximate latency
                return elapsed * 10  # Rough scaling

        except:
            pass
        return 20.0  # Default

    def _monitor_context_switches(self) -> Dict[str, float]:
        """Monitor context switch rate."""
        metrics = {}

        try:
            # Get initial stats
            stats1 = psutil.cpu_stats()
            time.sleep(1)
            stats2 = psutil.cpu_stats()

            # Calculate rate
            ctx_switches = stats2.ctx_switches - stats1.ctx_switches
            metrics['context_switches_sec'] = ctx_switches

        except Exception as e:
            logger.error(f"Failed to monitor context switches: {e}")
            metrics['context_switches_sec'] = 10000

        return metrics

    def _test_memory_performance(self) -> Dict[str, float]:
        """Test memory performance with current settings."""
        metrics = {}

        try:
            # Simple memory bandwidth test
            test_script = """
import numpy as np
import time

# Test array size (1GB)
size = 128 * 1024 * 1024  # 128M float64 = 1GB
a = np.ones(size, dtype=np.float64)
b = np.ones(size, dtype=np.float64)
c = np.zeros(size, dtype=np.float64)

# Warmup
for _ in range(2):
    c[:] = a + b

# Measure
start = time.time()
iterations = 10
for _ in range(iterations):
    c[:] = a + b
elapsed = time.time() - start

# Calculate bandwidth (3 arrays * 8 bytes * iterations / time)
bandwidth_gb = (3 * size * 8 * iterations / 1e9) / elapsed
print(f"memory_bandwidth_gb={bandwidth_gb:.2f}")
"""

            # Write and run test
            script_path = '/tmp/memory_test.py'
            with open(script_path, 'w') as f:
                f.write(test_script)

            returncode, stdout, _ = self.run_command(
                ['python3', script_path], timeout=30
            )

            if returncode == 0:
                match = re.search(r'memory_bandwidth_gb=([\d.]+)', stdout)
                if match:
                    metrics['memory_bandwidth_gb'] = float(match.group(1))
            else:
                metrics['memory_bandwidth_gb'] = 20.0

            # Check cache hit rate via perf
            metrics['cache_hit_rate'] = self._get_cache_hit_rate()

        except Exception as e:
            logger.error(f"Failed to test memory performance: {e}")
            metrics['memory_bandwidth_gb'] = 20.0
            metrics['cache_hit_rate'] = 0.8

        return metrics

    def _get_cache_hit_rate(self) -> float:
        """Get CPU cache hit rate."""
        try:
            # Use perf stat to measure cache references and misses
            cmd = ['perf', 'stat', '-e', 'cache-references,cache-misses',
                   'sleep', '1']
            returncode, _, stderr = self.run_command(cmd, timeout=2)

            if returncode == 0:
                # Parse perf output
                references = 0
                misses = 0
                for line in stderr.split('\n'):
                    if 'cache-references' in line:
                        match = re.search(r'([\d,]+)\s+cache-references', line)
                        if match:
                            references = int(match.group(1).replace(',', ''))
                    elif 'cache-misses' in line:
                        match = re.search(r'([\d,]+)\s+cache-misses', line)
                        if match:
                            misses = int(match.group(1).replace(',', ''))

                if references > 0:
                    return 1.0 - (misses / references)

        except:
            pass
        return 0.85  # Default

    def _measure_scheduler_efficiency(self) -> Dict[str, float]:
        """Measure scheduler efficiency."""
        metrics = {}

        try:
            # Run parallel workload to test scheduler
            cmd = ['sysbench', 'cpu', '--threads=' + str(self.cpu_count),
                   '--time=5', 'run']
            returncode, stdout, _ = self.run_command(cmd, timeout=10)

            if returncode == 0:
                # Parse sysbench output
                match = re.search(r'events per second:\s*([\d.]+)', stdout)
                if match:
                    events_per_sec = float(match.group(1))
                    # Normalize to efficiency metric (higher is better)
                    # Assume 10000 events/sec/core is good efficiency
                    expected = 10000 * self.cpu_count
                    metrics['scheduler_efficiency'] = min(events_per_sec / expected, 1.0)
                else:
                    metrics['scheduler_efficiency'] = 0.5
            else:
                metrics['scheduler_efficiency'] = 0.5

        except Exception as e:
            logger.error(f"Failed to measure scheduler efficiency: {e}")
            metrics['scheduler_efficiency'] = 0.5

        return metrics

    def _check_system_health(self) -> Dict[str, float]:
        """Check overall system health."""
        metrics = {}

        try:
            # Memory pressure
            mem = psutil.virtual_memory()
            metrics['memory_pressure'] = mem.percent / 100.0

            # Load average
            load1, load5, load15 = os.getloadavg()
            metrics['load_average'] = load1

            # Check for OOM kills
            metrics['oom_kills'] = self._check_oom_kills()

            # Check for fork failures
            metrics['fork_failures'] = self._check_fork_failures()

            # Check for IRQ storms
            metrics['irq_storms'] = self._check_irq_storms()

        except Exception as e:
            logger.error(f"Failed to check system health: {e}")
            metrics['memory_pressure'] = 0.5
            metrics['load_average'] = 1.0
            metrics['oom_kills'] = 0
            metrics['fork_failures'] = 0
            metrics['irq_storms'] = 0

        return metrics

    def _check_oom_kills(self) -> int:
        """Check for recent OOM kills."""
        try:
            # Check dmesg for OOM kills
            cmd = ['dmesg', '-T']
            returncode, stdout, _ = self.run_command(cmd, timeout=2)
            if returncode == 0:
                oom_count = stdout.count('Out of memory')
                return oom_count
        except:
            pass
        return 0

    def _check_fork_failures(self) -> int:
        """Check for fork failures."""
        try:
            # Check kernel log for fork failures
            cmd = ['dmesg', '-T']
            returncode, stdout, _ = self.run_command(cmd, timeout=2)
            if returncode == 0:
                fork_failures = stdout.count('fork failed')
                return fork_failures
        except:
            pass
        return 0

    def _check_irq_storms(self) -> int:
        """Check for IRQ storms."""
        try:
            # Monitor IRQ rate
            with open('/proc/interrupts', 'r') as f:
                irqs1 = f.read()

            time.sleep(1)

            with open('/proc/interrupts', 'r') as f:
                irqs2 = f.read()

            # Check for excessive IRQ rate (>100k/sec on any IRQ)
            storm_count = 0
            lines1 = irqs1.split('\n')
            lines2 = irqs2.split('\n')

            for l1, l2 in zip(lines1, lines2):
                if ':' in l1 and ':' in l2:
                    # Parse IRQ counts
                    counts1 = [int(x) for x in l1.split()[1:] if x.isdigit()]
                    counts2 = [int(x) for x in l2.split()[1:] if x.isdigit()]

                    if counts1 and counts2:
                        diff = sum(counts2) - sum(counts1)
                        if diff > 100000:  # >100k IRQs/sec
                            storm_count += 1

            return storm_count

        except:
            pass
        return 0


# Test function
def test_os_scheduler_evaluator():
    """Test the OS/scheduler domain evaluator."""
    import numpy as np

    evaluator = OSSchedulerDomainEvaluator()

    print(f"CPU Count: {evaluator.cpu_count}")
    print(f"Memory: {evaluator.memory_gb:.1f} GB")
    print(f"Kernel: {evaluator.kernel_version}")
    print(f"Available Governors: {evaluator.available_governors}")
    print(f"Has cgroups v2: {evaluator.has_cgroups_v2}")
    print(f"Has ZRAM: {evaluator.has_zram}")
    print(f"IRQ Info: Total={evaluator.irq_info['total_irqs']}, "
          f"Network={len(evaluator.irq_info['network_irqs'])}, "
          f"Storage={len(evaluator.irq_info['storage_irqs'])}")

    # Test with random genome
    genome_size = len(evaluator.get_genome_spec())
    genome = np.random.randn(genome_size).tolist()

    print(f"\nTesting OS/scheduler evaluator with genome size {genome_size}")

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
    test_os_scheduler_evaluator()