#!/usr/bin/env python3

import hashlib
import json
import logging
import re
import subprocess
import time
from pathlib import Path
from typing import Any, Dict, List
from collections import OrderedDict

from src.orchestration.daemons.base_streaming_daemon import BaseStreamingDaemon

try:
    from src.orchestration.core.umn_bus import UMNPub
except ImportError:
    UMNPub = None

logger = logging.getLogger(__name__)


class ExplorationScannerDaemon(BaseStreamingDaemon):
    """
    Timer-based scanning daemon for hardware and optimization discovery.

    NOTE: This daemon overrides _watch_files() to implement periodic scanning
    instead of file-watching. The process_file_event() method is unused.

    Architecture Decision Record (ADR):
    - Extends BaseStreamingDaemon to reuse worker pool, signal handling, and health checks
    - watch_path is set to /tmp but not actually monitored (required by base class)
    - Timer-based scanning pattern may be extracted to TimerBasedDaemon ABC in future
    - Scans system state every scan_interval seconds (default: 300s)

    Discovery Scope:
    - GPU availability and utilization
    - CPU features (AVX, AVX2, SSE)
    - Optimization opportunities (underutilized hardware)

    Deduplication:
    - Opportunities tracked by content hash (type + evidence)
    - Only NEW opportunities emitted to UMN
    - Existing opportunities update last_seen timestamp
    """

    def __init__(
        self,
        state_file: Path = Path("/home/kloros/.kloros/exploration_scanner_state.json"),
        scan_interval: int = 300,
        max_workers: int = 2,
        max_opportunities: int = 100,
        min_emission_interval: int = 60
    ):
        super().__init__(
            watch_path=Path("/tmp"),  # Dummy path, not used for scanning
            max_workers=max_workers
        )

        self.state_file = state_file
        self.scan_interval = scan_interval
        self.last_scan = 0.0
        self.max_opportunities = max_opportunities
        self.min_emission_interval = min_emission_interval
        self.last_emission_time = 0.0
        self.discovered_opportunities: OrderedDict[str, Dict[str, Any]] = OrderedDict()
        self.chem_pub = None
        self.scan_count = 0

        self.load_state()

    def _watch_files(self):
        while self.running:
            self._check_and_scan()
            time.sleep(10)

    def _check_and_scan(self):
        current_time = time.time()
        if current_time - self.last_scan >= self.scan_interval:
            logger.info("[exploration_scanner] Starting periodic system scan")
            self._perform_system_scan()
            self.last_scan = current_time
            self.scan_count += 1

            if self.scan_count % 10 == 0:
                logger.info("[exploration_scanner] Periodic state save")
                self.save_state()

    def _perform_system_scan(self):
        try:
            opportunities = self._detect_optimization_opportunities()

            if opportunities:
                logger.info(
                    f"[exploration_scanner] Found {len(opportunities)} optimization opportunities"
                )

                new_opportunities = []
                for opp in opportunities:
                    opp_id = self._get_opportunity_id(opp)

                    if opp_id not in self.discovered_opportunities:
                        self.discovered_opportunities[opp_id] = {
                            'type': opp['type'],
                            'severity': opp['severity'],
                            'evidence': opp['evidence'],
                            'suggestion': opp['suggestion'],
                            'first_seen': time.time(),
                            'last_seen': time.time()
                        }
                        new_opportunities.append(opp)
                    else:
                        # Update last_seen for existing opportunities
                        self.discovered_opportunities[opp_id]['last_seen'] = time.time()

                if new_opportunities:
                    logger.info(
                        f"[exploration_scanner] Emitting {len(new_opportunities)} new opportunities"
                    )
                    self._emit_questions_to_umn(new_opportunities)
                else:
                    logger.debug("[exploration_scanner] No new opportunities to emit")

            self._evict_opportunity_cache_if_needed()

        except Exception as e:
            logger.error(f"[exploration_scanner] System scan failed: {e}", exc_info=True)

    def _get_opportunity_id(self, opportunity: Dict[str, Any]) -> str:
        """Generate stable ID for opportunity based on type and evidence."""
        evidence_str = ','.join(sorted(opportunity['evidence']))
        evidence_hash = hashlib.sha256(evidence_str.encode()).hexdigest()[:8]
        return f"{opportunity['type']}_{evidence_hash}"

    def _detect_gpu_availability(self) -> Dict[str, Any]:
        try:
            result = subprocess.run(
                ['nvidia-ml', 'query'],
                capture_output=True,
                text=True,
                timeout=5
            )

            if result.returncode == 0:
                output = result.stdout

                # Robust regex parsing for GPU utilization
                utilization_match = re.search(
                    r'utilization[:\s]+(\d+(?:\.\d+)?)%',
                    output,
                    re.IGNORECASE
                )

                utilization = 0.0
                if utilization_match:
                    util_value = float(utilization_match.group(1))
                    # Clamp to valid range
                    utilization = max(0.0, min(100.0, util_value))

                # Extract GPU name
                name = "Unknown GPU"
                name_match = re.search(r'gpu[:\s]+(.+?)(?:\(|$)', output, re.IGNORECASE)
                if name_match:
                    name = name_match.group(1).strip()

                return {
                    'has_gpu': True,
                    'utilization': utilization,
                    'name': name
                }

        except FileNotFoundError:
            logger.debug("[exploration_scanner] nvidia-ml not found")
        except subprocess.TimeoutExpired:
            logger.warning("[exploration_scanner] nvidia-ml query timeout")
        except Exception as e:
            logger.debug(f"[exploration_scanner] GPU detection error: {e}")

        return {'has_gpu': False}

    def _detect_cpu_features(self) -> Dict[str, Any]:
        cpuinfo_path = Path('/proc/cpuinfo')

        if not cpuinfo_path.exists():
            return {}

        try:
            with open(cpuinfo_path, 'r') as f:
                cpuinfo = f.read().lower()

            return {
                'has_avx': 'avx' in cpuinfo,
                'has_avx2': 'avx2' in cpuinfo,
                'has_sse': 'sse' in cpuinfo,
                'has_sse2': 'sse2' in cpuinfo
            }

        except Exception as e:
            logger.debug(f"[exploration_scanner] CPU feature detection error: {e}")
            return {}

    def _detect_optimization_opportunities(self) -> List[Dict[str, Any]]:
        opportunities = []

        gpu_status = self._detect_gpu_availability()

        if gpu_status.get('has_gpu'):
            utilization = gpu_status.get('utilization', 0)

            if utilization < 20:
                opportunities.append({
                    'type': 'gpu_underutilization',
                    'severity': 'high' if utilization < 10 else 'medium',
                    'evidence': [
                        f"GPU available: {gpu_status.get('name', 'Unknown')}",
                        f"Current utilization: {utilization}%"
                    ],
                    'suggestion': 'Consider GPU acceleration for compute-heavy tasks'
                })

        cpu_features = self._detect_cpu_features()

        if cpu_features:
            if not cpu_features.get('has_avx2') and cpu_features.get('has_avx'):
                opportunities.append({
                    'type': 'cpu_optimization_avx',
                    'severity': 'low',
                    'evidence': [
                        'AVX available but AVX2 not detected',
                        'Modern workloads could benefit from AVX2'
                    ],
                    'suggestion': 'Consider upgrading CPU or enabling AVX2 instructions'
                })

            if not cpu_features.get('has_avx') and cpu_features.get('has_sse2'):
                opportunities.append({
                    'type': 'cpu_optimization_simd',
                    'severity': 'medium',
                    'evidence': [
                        'Only SSE/SSE2 available',
                        'AVX not detected'
                    ],
                    'suggestion': 'Consider using SIMD optimizations or upgrading CPU'
                })

        return opportunities

    def _emit_questions_to_umn(self, opportunities: List[Dict[str, Any]]):
        if not UMNPub:
            logger.warning("[exploration_scanner] UMN not available, skipping emission")
            return

        # Rate limiting: Don't spam UMN more than once per min_emission_interval
        current_time = time.time()
        if current_time - self.last_emission_time < self.min_emission_interval:
            logger.debug(
                f"[exploration_scanner] Skipping emission - too soon "
                f"(last emission {current_time - self.last_emission_time:.0f}s ago)"
            )
            return

        if not self.chem_pub:
            try:
                self.chem_pub = UMNPub()
            except Exception as e:
                logger.error(f"[exploration_scanner] Failed to create UMNPub: {e}")
                return

        for opp in opportunities:
            try:
                timestamp = int(time.time())
                question_id = f"exploration_{opp['type']}_{timestamp}"

                severity_intensity = {
                    'low': 0.60,
                    'medium': 0.75,
                    'high': 0.90
                }

                self.chem_pub.emit(
                    signal="curiosity.exploration_question",
                    ecosystem="curiosity",
                    intensity=severity_intensity.get(opp['severity'], 0.75),
                    facts={
                        'question_id': question_id,
                        'hypothesis': f"Optimization opportunity: {opp['type']}",
                        'question': f"Should we optimize {opp['type']}?",
                        'evidence': opp['evidence'],
                        'severity': opp['severity'],
                        'suggestion': opp['suggestion'],
                        'category': 'exploration_discovery',
                        'source': 'exploration_scanner_daemon',
                        'timestamp': time.time()
                    }
                )
                logger.info(f"[exploration_scanner] Emitted question: {question_id}")

            except Exception as e:
                logger.error(
                    f"[exploration_scanner] Failed to emit question for {opp['type']}: {e}"
                )

        # Update last emission time after successful emission batch
        self.last_emission_time = time.time()

    def _evict_opportunity_cache_if_needed(self):
        if len(self.discovered_opportunities) > self.max_opportunities:
            to_remove = len(self.discovered_opportunities) - self.max_opportunities
            for _ in range(to_remove):
                self.discovered_opportunities.popitem(last=False)
            logger.debug(
                f"[exploration_scanner] Evicted {to_remove} old opportunities from cache"
            )

    def process_file_event(self, event_type: str, file_path: Path):
        pass

    def save_state(self):
        try:
            self.state_file.parent.mkdir(parents=True, exist_ok=True)

            state = {
                'last_scan': self.last_scan,
                'discovered_opportunities': dict(self.discovered_opportunities),
                'scan_count': self.scan_count,
                'timestamp': time.time()
            }

            with open(self.state_file, 'w') as f:
                json.dump(state, f)

            logger.info(f"[exploration_scanner] Saved state to {self.state_file}")

        except Exception as e:
            logger.error(f"[exploration_scanner] Failed to save state: {e}")

        finally:
            if self.chem_pub is not None:
                try:
                    logger.info("[exploration_scanner] Cleaning up UMN connection")
                    self.chem_pub = None
                except Exception as e:
                    logger.warning(f"[exploration_scanner] UMN cleanup error: {e}")

    def load_state(self):
        if not self.state_file.exists():
            logger.info("[exploration_scanner] No previous state found, starting fresh")
            return

        try:
            with open(self.state_file, 'r') as f:
                state = json.load(f)

            self.last_scan = state.get('last_scan', 0.0)
            self.discovered_opportunities = OrderedDict(
                state.get('discovered_opportunities', {})
            )
            self.scan_count = state.get('scan_count', 0)

            logger.info(
                f"[exploration_scanner] Loaded state: "
                f"{len(self.discovered_opportunities)} opportunities, "
                f"{self.scan_count} scans performed"
            )

        except Exception as e:
            logger.error(f"[exploration_scanner] Failed to load state: {e}")
            self.last_scan = 0.0
            self.discovered_opportunities = OrderedDict()
            self.scan_count = 0

    def get_health_status(self) -> Dict[str, Any]:
        base_status = super().get_health_status()

        base_status.update({
            'last_scan': self.last_scan,
            'opportunities_found': len(self.discovered_opportunities),
            'scan_count': self.scan_count,
            'next_scan_in': max(0, self.scan_interval - (time.time() - self.last_scan))
        })

        return base_status


def main():
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s [%(levelname)s] %(message)s'
    )

    daemon = ExplorationScannerDaemon()

    logger.info("[exploration_scanner] Starting daemon...")
    daemon.start()


if __name__ == "__main__":
    main()
