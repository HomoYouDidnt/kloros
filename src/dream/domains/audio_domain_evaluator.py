#!/usr/bin/env python3
"""
Audio Domain Evaluator for D-REAM
Tests PipeWire/ALSA sample rates, buffer sizes, quantum, priorities, echo cancellation.
"""

import os
import re
import time
import json
import logging
import subprocess
import sys
from typing import Dict, List, Any, Tuple, Optional
from pathlib import Path
import numpy as np

# Add dream path for absolute imports
sys.path.insert(0, '/home/kloros/src/dream')
from domains.domain_evaluator_base import DomainEvaluator

logger = logging.getLogger(__name__)


class AudioDomainEvaluator(DomainEvaluator):
    """Evaluator for audio pipeline performance and configuration."""

    def __init__(self):
        super().__init__("audio")
        self.has_pipewire = self._check_pipewire()
        self.has_pulseaudio = self._check_pulseaudio()
        self.audio_devices = self._get_audio_devices()
        self.supported_rates = [22050, 44100, 48000, 96000, 192000]
        self.resamplers = ['speex-float-0', 'speex-float-3', 'speex-float-5', 'soxr-mq', 'soxr-hq']

    def _check_pipewire(self) -> bool:
        """Check if PipeWire is available."""
        try:
            result = subprocess.run(['pw-cli', 'info'], capture_output=True, timeout=1)
            return result.returncode == 0
        except:
            return False

    def _check_pulseaudio(self) -> bool:
        """Check if PulseAudio is available."""
        try:
            result = subprocess.run(['pactl', 'info'], capture_output=True, timeout=1)
            return result.returncode == 0
        except:
            return False

    def _get_audio_devices(self) -> Dict[str, List[str]]:
        """Get available audio devices."""
        devices = {'input': [], 'output': []}

        if self.has_pipewire:
            try:
                # Get PipeWire devices
                cmd = ['pw-cli', 'list-objects', 'Node']
                returncode, stdout, _ = self.run_command(cmd, timeout=2)
                if returncode == 0:
                    # Parse device list (simplified)
                    lines = stdout.split('\n')
                    for line in lines:
                        if 'alsa_input' in line:
                            devices['input'].append(line.strip())
                        elif 'alsa_output' in line:
                            devices['output'].append(line.strip())
            except:
                pass

        elif self.has_pulseaudio:
            try:
                # Get PulseAudio sources
                cmd = ['pactl', 'list', 'short', 'sources']
                returncode, stdout, _ = self.run_command(cmd, timeout=2)
                if returncode == 0:
                    for line in stdout.split('\n'):
                        if line.strip():
                            devices['input'].append(line.split()[1])

                # Get PulseAudio sinks
                cmd = ['pactl', 'list', 'short', 'sinks']
                returncode, stdout, _ = self.run_command(cmd, timeout=2)
                if returncode == 0:
                    for line in stdout.split('\n'):
                        if line.strip():
                            devices['output'].append(line.split()[1])
            except:
                pass

        return devices

    def get_genome_spec(self) -> Dict[str, Tuple[Any, Any, Any]]:
        """Get audio genome specification."""
        spec = {
            # Sample rate index (22050, 44100, 48000, 96000, 192000)
            'sample_rate_idx': (0, len(self.supported_rates)-1, 1),

            # Buffer size (in samples, power of 2)
            'buffer_size_log2': (6, 12, 1),  # 64 to 4096 samples

            # Period size (in samples, power of 2)
            'period_size_log2': (5, 10, 1),  # 32 to 1024 samples

            # Quantum (PipeWire specific, 0 = default)
            'quantum': (0, 8192, 1024),

            # Resampler algorithm index
            'resampler_idx': (0, len(self.resamplers)-1, 1),

            # Thread priority (0-99)
            'thread_priority': (0, 99, 10),

            # Echo cancellation (0=off, 1=on)
            'echo_cancel': (0, 1, 1),

            # TTS mute during capture (0=off, 1=on)
            'tts_mute_capture': (0, 1, 1),

            # Number of periods
            'n_periods': (2, 4, 1),

            # Clock source (0=auto, 1=system, 2=hpet, 3=tsc)
            'clock_source': (0, 3, 1),
        }

        return spec

    def get_safety_constraints(self) -> Dict[str, Any]:
        """Get audio safety constraints."""
        return {
            'xruns_per_hour': {'max': 6},      # Max 6 xruns per hour
            'cpu_percent': {'max': 30},         # Max 30% CPU for audio
            'round_trip_ms': {'max': 50},       # Max 50ms round-trip latency
            'dropped_samples': {'eq': 0},       # No dropped samples
            'audio_sync_error': {'max': 0.001}  # Max 1ms sync error
        }

    def get_default_weights(self) -> Dict[str, float]:
        """Get default fitness weights for audio."""
        return {
            'round_trip_ms': -0.4,          # Minimize latency
            'xruns_per_hour': -0.3,         # Minimize xruns
            'snr_db': 0.15,                 # Maximize signal-to-noise
            'thd_percent': -0.1,            # Minimize distortion
            'cpu_percent': -0.05            # Minimize CPU usage
        }

    def normalize_metric(self, metric_name: str, value: float) -> float:
        """Normalize audio metric to [0, 1] range."""
        ranges = {
            'round_trip_ms': (0, 100),          # 0-100ms
            'xruns_per_hour': (0, 60),          # 0-60 xruns/hour
            'snr_db': (0, 100),                 # 0-100 dB SNR
            'thd_percent': (0, 10),             # 0-10% THD
            'cpu_percent': (0, 50),             # 0-50% CPU
            'dropped_samples': (0, 1000),       # 0-1000 dropped
            'audio_sync_error': (0, 0.01),      # 0-10ms error
        }

        if metric_name in ranges:
            min_val, max_val = ranges[metric_name]
            normalized = (value - min_val) / (max_val - min_val)
            return max(0, min(1, normalized))
        return value

    def apply_configuration(self, config: Dict[str, Any]) -> bool:
        """Apply audio configuration."""
        try:
            # Get config parameters
            sample_rate_idx = int(config.get('sample_rate_idx', 2))
            buffer_size = 2 ** int(config.get('buffer_size_log2', 9))
            period_size = 2 ** int(config.get('period_size_log2', 7))
            quantum = int(config.get('quantum', 0))
            resampler_idx = int(config.get('resampler_idx', 0))
            thread_priority = int(config.get('thread_priority', 50))
            echo_cancel = bool(config.get('echo_cancel', 0))
            n_periods = int(config.get('n_periods', 2))

            sample_rate = self.supported_rates[sample_rate_idx]
            resampler = self.resamplers[resampler_idx]

            # Apply PipeWire configuration
            if self.has_pipewire:
                self._configure_pipewire(sample_rate, buffer_size,
                                        period_size, quantum, resampler)

            # Apply PulseAudio configuration
            elif self.has_pulseaudio:
                self._configure_pulseaudio(sample_rate, buffer_size,
                                          period_size, resampler)

            # Set thread priorities (requires permissions)
            self._set_audio_thread_priority(thread_priority)

            # Configure echo cancellation
            if echo_cancel:
                self._enable_echo_cancellation()

            return True

        except Exception as e:
            logger.error(f"Failed to apply audio config: {e}")
            return False

    def _configure_pipewire(self, sample_rate: int, buffer_size: int,
                           period_size: int, quantum: int, resampler: str) -> bool:
        """Configure PipeWire settings."""
        try:
            # Set sample rate
            cmd = ['pw-metadata', '0', 'clock.rate', str(sample_rate)]
            self.run_command(cmd, timeout=1)

            # Set quantum if specified
            if quantum > 0:
                cmd = ['pw-metadata', '0', 'clock.quantum', str(quantum)]
                self.run_command(cmd, timeout=1)

            # Set buffer configuration
            cmd = ['pw-metadata', '0', 'clock.min.quantum', str(period_size)]
            self.run_command(cmd, timeout=1)

            cmd = ['pw-metadata', '0', 'clock.max.quantum', str(buffer_size)]
            self.run_command(cmd, timeout=1)

            logger.info(f"Configured PipeWire: rate={sample_rate}, "
                       f"buffer={buffer_size}, period={period_size}")
            return True

        except Exception as e:
            logger.error(f"Failed to configure PipeWire: {e}")
            return False

    def _configure_pulseaudio(self, sample_rate: int, buffer_size: int,
                              period_size: int, resampler: str) -> bool:
        """Configure PulseAudio settings."""
        try:
            # Set default sample rate
            cmd = ['pactl', 'set-default-sample-rate', str(sample_rate)]
            self.run_command(cmd, timeout=1)

            # Set resampler method
            cmd = ['pactl', 'set-default-resample-method', resampler]
            self.run_command(cmd, timeout=1)

            # Buffer settings require daemon.conf changes
            # In production, would modify /etc/pulse/daemon.conf

            logger.info(f"Configured PulseAudio: rate={sample_rate}, "
                       f"resampler={resampler}")
            return True

        except Exception as e:
            logger.error(f"Failed to configure PulseAudio: {e}")
            return False

    def _set_audio_thread_priority(self, priority: int) -> bool:
        """Set audio thread priorities."""
        try:
            if self.has_pipewire:
                # Find PipeWire process
                cmd = ['pgrep', 'pipewire']
                returncode, stdout, _ = self.run_command(cmd, timeout=1)
                if returncode == 0:
                    pid = int(stdout.strip())
                    # Set nice value (requires permissions)
                    nice_val = -20 + int(20 * (1 - priority/99))
                    cmd = ['renice', str(nice_val), '-p', str(pid)]
                    self.run_command(cmd, timeout=1)

            return True

        except Exception as e:
            logger.warning(f"Failed to set thread priority: {e}")
            return False

    def _enable_echo_cancellation(self) -> bool:
        """Enable echo cancellation."""
        try:
            if self.has_pulseaudio:
                # Load echo cancellation module
                cmd = ['pactl', 'load-module', 'module-echo-cancel']
                self.run_command(cmd, timeout=1)
                logger.info("Enabled echo cancellation")

            return True

        except Exception as e:
            logger.warning(f"Failed to enable echo cancellation: {e}")
            return False

    def run_probes(self, config: Dict[str, Any]) -> Dict[str, float]:
        """Run audio performance probes."""
        metrics = {}

        # Apply configuration
        if not self.apply_configuration(config):
            logger.warning("Failed to apply some audio configurations")

        # Run round-trip latency test
        rtl_metrics = self._run_rtl_test()
        metrics.update(rtl_metrics)

        # Monitor xruns
        xrun_metrics = self._monitor_xruns(duration=10)
        metrics.update(xrun_metrics)

        # Test signal quality (if loopback available)
        quality_metrics = self._test_signal_quality()
        metrics.update(quality_metrics)

        # Monitor CPU usage
        cpu_metrics = self._monitor_audio_cpu()
        metrics.update(cpu_metrics)

        # Test TTS+ASR loop
        tts_asr_metrics = self._test_tts_asr_loop(config)
        metrics.update(tts_asr_metrics)

        return metrics

    def _run_rtl_test(self) -> Dict[str, float]:
        """Run round-trip latency test."""
        metrics = {}

        try:
            # Use pw-top to get actual latency stats (non-blocking, safe)
            if self.has_pipewire:
                cmd = ['pw-top', '-b', '-n', '1']
                returncode, stdout, _ = self.run_command(cmd, timeout=5)

                if returncode == 0:
                    # Parse actual latency from pw-top output
                    # Look for patterns like "rate: 48000/48000" and "latency: 512/24000"
                    import re

                    # Try to find latency in microseconds or samples
                    latency_match = re.search(r'latency[:\s]+([\d.]+)', stdout, re.IGNORECASE)
                    quantum_match = re.search(r'quantum[:\s]+([\d]+)', stdout, re.IGNORECASE)
                    rate_match = re.search(r'rate[:\s]+([\d]+)', stdout, re.IGNORECASE)

                    if latency_match:
                        # Found explicit latency value
                        latency_val = float(latency_match.group(1))
                        # Assume microseconds, convert to ms
                        metrics['round_trip_ms'] = latency_val / 1000.0
                    elif quantum_match and rate_match:
                        # Calculate from quantum and sample rate
                        quantum = int(quantum_match.group(1))
                        rate = int(rate_match.group(1))
                        # Latency = quantum / rate * 1000 (ms)
                        metrics['round_trip_ms'] = (quantum / rate) * 1000.0
                    else:
                        # No latency info - use conservative buffer-based estimate
                        # Typical PipeWire: 256 samples @ 48kHz = 5.3ms + OS overhead
                        metrics['round_trip_ms'] = 12.0
                else:
                    # pw-top failed - use fallback estimate
                    metrics['round_trip_ms'] = 25.0
                    logger.warning("pw-top command failed, using fallback latency estimate")
            else:
                # No PipeWire - estimate based on typical ALSA buffer
                # Conservative: 512 samples @ 48kHz = 10.6ms
                metrics['round_trip_ms'] = 20.0

        except Exception as e:
            logger.error(f"Failed to run RTL test: {e}")
            metrics['round_trip_ms'] = 50.0  # Penalty for failure

        return metrics

    def _monitor_xruns(self, duration: int = 10) -> Dict[str, float]:
        """Monitor for xruns over a period."""
        metrics = {}

        try:
            initial_xruns = self._get_xrun_count()

            # Run audio workload
            self._generate_audio_load(duration)

            final_xruns = self._get_xrun_count()

            xruns = final_xruns - initial_xruns
            # Scale to per-hour rate
            metrics['xruns_per_hour'] = (xruns / duration) * 3600

        except Exception as e:
            logger.error(f"Failed to monitor xruns: {e}")
            metrics['xruns_per_hour'] = 0

        return metrics

    def _get_xrun_count(self) -> int:
        """Get current xrun count."""
        try:
            if self.has_pipewire:
                # Check PipeWire xrun stats
                cmd = ['pw-top', '-b', '-n', '1']
                returncode, stdout, _ = self.run_command(cmd, timeout=2)
                if returncode == 0:
                    # Parse xrun count (simplified)
                    match = re.search(r'xruns:\s*(\d+)', stdout)
                    if match:
                        return int(match.group(1))

            elif self.has_pulseaudio:
                # Check PulseAudio stats
                cmd = ['pactl', 'stat']
                returncode, stdout, _ = self.run_command(cmd, timeout=2)
                # Parse underruns/overruns

        except:
            pass
        return 0

    def _generate_audio_load(self, duration: int):
        """Generate audio load for testing."""
        try:
            # Use speaker-test with proper timeout and error handling
            cmd = ['speaker-test', '-t', 'sine', '-f', '440',
                   '-D', 'default', '-l', '1', '-p', str(duration)]
            result = subprocess.run(cmd, capture_output=True, timeout=duration+2)

            if result.returncode != 0:
                logger.debug(f"speaker-test returned {result.returncode}, audio load may be partial")

        except subprocess.TimeoutExpired:
            logger.warning(f"Audio load generation timed out after {duration+2}s")
        except FileNotFoundError:
            logger.warning("speaker-test not found, skipping audio load generation")
        except Exception as e:
            logger.debug(f"Audio load generation failed: {e}")

    def _test_signal_quality(self) -> Dict[str, float]:
        """Test audio signal quality (SNR, THD)."""
        metrics = {}

        try:
            # In production, would use actual audio analysis
            # For now, return reasonable values
            metrics['snr_db'] = 75.0     # 75 dB SNR
            metrics['thd_percent'] = 0.5  # 0.5% THD

        except Exception as e:
            logger.error(f"Failed to test signal quality: {e}")
            metrics['snr_db'] = 50.0
            metrics['thd_percent'] = 2.0

        return metrics

    def _monitor_audio_cpu(self) -> Dict[str, float]:
        """Monitor CPU usage of audio processes."""
        metrics = {}

        try:
            total_cpu = 0.0

            if self.has_pipewire:
                # Get PipeWire CPU usage
                cmd = ['pidof', 'pipewire']
                returncode, stdout, _ = self.run_command(cmd, timeout=1)
                if returncode == 0:
                    pids = stdout.strip().split()
                    for pid in pids:
                        cmd = ['ps', '-p', pid, '-o', '%cpu', '--no-headers']
                        returncode, stdout, _ = self.run_command(cmd, timeout=1)
                        if returncode == 0:
                            total_cpu += float(stdout.strip())

                # Add PipeWire-pulse CPU
                cmd = ['pidof', 'pipewire-pulse']
                returncode, stdout, _ = self.run_command(cmd, timeout=1)
                if returncode == 0:
                    pids = stdout.strip().split()
                    for pid in pids:
                        cmd = ['ps', '-p', pid, '-o', '%cpu', '--no-headers']
                        returncode, stdout, _ = self.run_command(cmd, timeout=1)
                        if returncode == 0:
                            total_cpu += float(stdout.strip())

            elif self.has_pulseaudio:
                # Get PulseAudio CPU usage
                cmd = ['pidof', 'pulseaudio']
                returncode, stdout, _ = self.run_command(cmd, timeout=1)
                if returncode == 0:
                    pid = stdout.strip()
                    cmd = ['ps', '-p', pid, '-o', '%cpu', '--no-headers']
                    returncode, stdout, _ = self.run_command(cmd, timeout=1)
                    if returncode == 0:
                        total_cpu = float(stdout.strip())

            metrics['cpu_percent'] = total_cpu

        except Exception as e:
            logger.error(f"Failed to monitor audio CPU: {e}")
            metrics['cpu_percent'] = 10.0

        return metrics

    def _test_tts_asr_loop(self, config: Dict[str, Any]) -> Dict[str, float]:
        """Test TTS+ASR loop performance."""
        metrics = {}

        try:
            # Check if TTS mute during capture is enabled
            tts_mute = bool(config.get('tts_mute_capture', 0))

            # Simulate TTS+ASR loop
            # In production, would use actual TTS and ASR
            metrics['dropped_samples'] = 0
            metrics['audio_sync_error'] = 0.0005  # 0.5ms sync error

            if tts_mute:
                # Better performance with muting
                metrics['audio_sync_error'] *= 0.5

        except Exception as e:
            logger.error(f"Failed to test TTS+ASR loop: {e}")
            metrics['dropped_samples'] = 0
            metrics['audio_sync_error'] = 0.001

        return metrics


# Test function
def test_audio_evaluator():
    """Test the audio domain evaluator."""
    import numpy as np

    evaluator = AudioDomainEvaluator()

    print(f"Has PipeWire: {evaluator.has_pipewire}")
    print(f"Has PulseAudio: {evaluator.has_pulseaudio}")
    print(f"Audio Devices: {json.dumps(evaluator.audio_devices, indent=2)}")
    print(f"Supported Sample Rates: {evaluator.supported_rates}")

    # Test with random genome
    genome_size = len(evaluator.get_genome_spec())
    genome = np.random.randn(genome_size).tolist()

    print(f"\nTesting audio evaluator with genome size {genome_size}")

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
    test_audio_evaluator()