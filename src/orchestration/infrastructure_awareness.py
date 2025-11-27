#!/usr/bin/env python3
"""
Infrastructure Awareness - Phase 1 of GLaDOS-Level Autonomy

Provides complete visibility into system state without modification capabilities.
READ-ONLY: Zero risk, high insight.

Features:
- Service dependency graph
- Resource economics (cost per service)
- Failure impact analysis (blast radius)
- Anomaly detection
- Integration with curiosity system
"""

import subprocess
import logging
import json
import re
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple, Any
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from collections import defaultdict

logger = logging.getLogger(__name__)


@dataclass
class ServiceInfo:
    """Complete information about a systemd service."""
    name: str
    active: bool
    enabled: bool
    memory_current: int  # bytes
    memory_limit: int    # bytes
    cpu_usage: float     # percentage
    restart_count: int
    uptime: timedelta
    dependencies: List[str] = field(default_factory=list)
    dependents: List[str] = field(default_factory=list)
    description: str = ""
    criticality: str = "unknown"  # critical, important, normal, low
    user_facing: bool = False


@dataclass
class ResourceCost:
    """Economic model for service resource usage."""
    service: str
    memory_mb: float
    cpu_percent: float
    restart_frequency: float  # restarts per day
    uptime_percent: float
    user_value: float  # 0-1, how valuable to user
    cost_score: float  # Higher = more expensive
    efficiency: float  # value per cost


@dataclass
class ImpactAnalysis:
    """Blast radius analysis for service failure."""
    service: str
    direct_dependents: List[str]
    indirect_dependents: List[str]
    user_facing_impact: bool
    estimated_recovery_time: timedelta
    severity: str  # critical, high, medium, low
    mitigation_strategies: List[str]


@dataclass
class SystemAnomaly:
    """Detected system anomaly."""
    timestamp: datetime
    anomaly_type: str  # memory_spike, cpu_spike, restart_loop, etc
    service: str
    severity: str
    description: str
    baseline_value: float
    current_value: float
    deviation: float  # standard deviations from baseline
    curiosity_question: Optional[str] = None


class ServiceDependencyGraph:
    """Parse and analyze systemd service dependencies."""

    def __init__(self):
        self.services: Dict[str, ServiceInfo] = {}
        self.graph: Dict[str, Set[str]] = defaultdict(set)
        self.reverse_graph: Dict[str, Set[str]] = defaultdict(set)

    def build_graph(self) -> Dict[str, ServiceInfo]:
        """Build complete service dependency graph."""
        logger.info("[infra_awareness] Building service dependency graph...")

        # Get all services
        try:
            result = subprocess.run(
                ['systemctl', 'list-units', '--type=service', '--all', '--no-pager', '--plain'],
                capture_output=True,
                text=True,
                timeout=10
            )

            for line in result.stdout.splitlines():
                parts = line.split()
                if len(parts) >= 1 and parts[0].endswith('.service'):
                    service_name = parts[0]
                    self._load_service_info(service_name)

            logger.info(f"[infra_awareness] Loaded {len(self.services)} services")

            # Build dependency relationships
            for service_name in self.services.keys():
                self._parse_dependencies(service_name)

            # Classify criticality
            self._classify_services()

            return self.services

        except Exception as e:
            logger.error(f"[infra_awareness] Failed to build service graph: {e}")
            return {}

    def _load_service_info(self, service_name: str):
        """Load detailed information about a service."""
        try:
            # Get service status
            status_result = subprocess.run(
                ['systemctl', 'show', service_name,
                 '--property=ActiveState,UnitFileState,Description,MemoryCurrent,MemoryMax,'
                 'NRestarts,ActiveEnterTimestamp'],
                capture_output=True,
                text=True,
                timeout=5
            )

            properties = {}
            for line in status_result.stdout.splitlines():
                if '=' in line:
                    key, value = line.split('=', 1)
                    properties[key] = value

            # Parse properties
            active = properties.get('ActiveState', 'unknown') == 'active'
            enabled = properties.get('UnitFileState', 'unknown') == 'enabled'
            memory_current = int(properties.get('MemoryCurrent', '0'))
            memory_max = int(properties.get('MemoryMax', '0'))
            restart_count = int(properties.get('NRestarts', '0'))
            description = properties.get('Description', '')

            # Calculate uptime
            uptime = timedelta(0)
            enter_timestamp = properties.get('ActiveEnterTimestamp', '')
            if enter_timestamp and enter_timestamp != '0':
                try:
                    from datetime import datetime
                    enter_time = datetime.strptime(enter_timestamp, '%a %Y-%m-%d %H:%M:%S %Z')
                    uptime = datetime.now() - enter_time
                except:
                    pass

            # Get CPU usage (if available)
            cpu_usage = 0.0
            try:
                cpu_result = subprocess.run(
                    ['systemctl', 'show', service_name, '--property=CPUUsageNSec'],
                    capture_output=True,
                    text=True,
                    timeout=2
                )
                # This is cumulative, would need sampling for rate
                cpu_usage = 0.0
            except:
                pass

            service_info = ServiceInfo(
                name=service_name,
                active=active,
                enabled=enabled,
                memory_current=memory_current,
                memory_limit=memory_max if memory_max > 0 else 0,
                cpu_usage=cpu_usage,
                restart_count=restart_count,
                uptime=uptime,
                description=description
            )

            self.services[service_name] = service_info

        except Exception as e:
            logger.debug(f"[infra_awareness] Could not load {service_name}: {e}")

    def _parse_dependencies(self, service_name: str):
        """Parse service dependencies from unit file."""
        try:
            # Get dependencies
            result = subprocess.run(
                ['systemctl', 'show', service_name,
                 '--property=Requires,Wants,After,Before'],
                capture_output=True,
                text=True,
                timeout=5
            )

            requires = []
            wants = []
            for line in result.stdout.splitlines():
                if line.startswith('Requires='):
                    requires = [s.strip() for s in line[9:].split() if s.strip()]
                elif line.startswith('Wants='):
                    wants = [s.strip() for s in line[6:].split() if s.strip()]

            # Store dependencies
            all_deps = set(requires + wants)
            if service_name in self.services:
                self.services[service_name].dependencies = list(all_deps)
                self.graph[service_name] = all_deps

                # Build reverse graph (dependents)
                for dep in all_deps:
                    self.reverse_graph[dep].add(service_name)

        except Exception as e:
            logger.debug(f"[infra_awareness] Could not parse dependencies for {service_name}: {e}")

    def _classify_services(self):
        """Classify services by criticality and user-facing nature."""
        # Critical services (system-level)
        critical_patterns = [
            'systemd-', 'dbus', 'network', 'sshd', 'getty',
            'polkit', 'udev', 'journal'
        ]

        # User-facing KLoROS services
        user_facing_patterns = [
            'kloros.service', 'kloros-voice'
        ]

        # Important but not critical
        important_patterns = [
            'kloros-observer', 'dream', 'phase'
        ]

        for service_name, service_info in self.services.items():
            # Check criticality
            if any(pattern in service_name for pattern in critical_patterns):
                service_info.criticality = 'critical'
            elif any(pattern in service_name for pattern in important_patterns):
                service_info.criticality = 'important'
            elif any(pattern in service_name for pattern in user_facing_patterns):
                service_info.criticality = 'important'
                service_info.user_facing = True
            elif service_name.startswith('user@'):
                service_info.criticality = 'normal'
            else:
                service_info.criticality = 'low'

            # Check user-facing
            if any(pattern in service_name for pattern in user_facing_patterns):
                service_info.user_facing = True

    def get_transitive_dependents(self, service_name: str) -> Set[str]:
        """Get all services that depend on this service (transitively)."""
        visited = set()
        to_visit = {service_name}

        while to_visit:
            current = to_visit.pop()
            if current in visited:
                continue
            visited.add(current)

            # Add direct dependents
            for dependent in self.reverse_graph.get(current, []):
                if dependent not in visited:
                    to_visit.add(dependent)

        visited.discard(service_name)  # Remove self
        return visited


class ResourceEconomics:
    """Calculate resource cost and value for services."""

    def __init__(self, service_graph: ServiceDependencyGraph):
        self.service_graph = service_graph
        self.baseline: Dict[str, Dict[str, float]] = {}

    def calculate_costs(self) -> Dict[str, ResourceCost]:
        """Calculate resource economics for all services."""
        logger.info("[infra_awareness] Calculating resource economics...")

        costs = {}
        for service_name, service_info in self.service_graph.services.items():
            if not service_info.active:
                continue

            # Calculate metrics
            memory_mb = service_info.memory_current / (1024 * 1024)
            cpu_percent = service_info.cpu_usage

            # Restart frequency (restarts per day)
            if service_info.uptime.total_seconds() > 0:
                restart_freq = (service_info.restart_count /
                              (service_info.uptime.total_seconds() / 86400))
            else:
                restart_freq = 0

            # Uptime percentage (rough estimate)
            uptime_percent = 1.0 if service_info.restart_count < 5 else 0.9

            # User value (heuristic based on service type)
            user_value = self._estimate_user_value(service_info)

            # Cost score (higher = more expensive)
            cost_score = (memory_mb / 1000) + (cpu_percent / 100) + (restart_freq * 10)

            # Efficiency (value per cost)
            efficiency = user_value / max(cost_score, 0.01)

            cost = ResourceCost(
                service=service_name,
                memory_mb=memory_mb,
                cpu_percent=cpu_percent,
                restart_frequency=restart_freq,
                uptime_percent=uptime_percent,
                user_value=user_value,
                cost_score=cost_score,
                efficiency=efficiency
            )

            costs[service_name] = cost

        return costs

    def _estimate_user_value(self, service_info: ServiceInfo) -> float:
        """Estimate user-facing value of a service."""
        if service_info.user_facing:
            return 1.0  # Maximum value
        elif service_info.criticality == 'critical':
            return 0.9  # Critical system services
        elif service_info.criticality == 'important':
            return 0.7  # Important but not user-facing
        elif service_info.criticality == 'normal':
            return 0.4
        else:
            return 0.2  # Low priority


class FailureImpactAnalyzer:
    """Analyze blast radius of service failures."""

    def __init__(self, service_graph: ServiceDependencyGraph):
        self.service_graph = service_graph

    def analyze_impact(self, service_name: str) -> ImpactAnalysis:
        """Analyze impact of service failure."""
        service_info = self.service_graph.services.get(service_name)
        if not service_info:
            return ImpactAnalysis(
                service=service_name,
                direct_dependents=[],
                indirect_dependents=[],
                user_facing_impact=False,
                estimated_recovery_time=timedelta(seconds=0),
                severity='unknown',
                mitigation_strategies=[]
            )

        # Direct dependents
        direct_deps = list(self.service_graph.reverse_graph.get(service_name, []))

        # Indirect dependents (transitive)
        all_deps = self.service_graph.get_transitive_dependents(service_name)
        indirect_deps = list(all_deps - set(direct_deps))

        # User-facing impact
        user_facing_impact = service_info.user_facing
        for dep in all_deps:
            dep_info = self.service_graph.services.get(dep)
            if dep_info and dep_info.user_facing:
                user_facing_impact = True
                break

        # Estimated recovery time
        recovery_time = timedelta(seconds=30)  # Base restart time
        if len(all_deps) > 5:
            recovery_time += timedelta(seconds=10 * len(all_deps))

        # Severity
        if service_info.criticality == 'critical':
            severity = 'critical'
        elif user_facing_impact or len(all_deps) > 10:
            severity = 'high'
        elif len(all_deps) > 3 or service_info.criticality == 'important':
            severity = 'medium'
        else:
            severity = 'low'

        # Mitigation strategies
        strategies = []
        if len(direct_deps) == 0:
            strategies.append("No dependents - safe to restart")
        if not user_facing_impact:
            strategies.append("Not user-facing - minimal user disruption")
        if service_info.restart_count > 5:
            strategies.append("Investigate recurring restarts before action")
        if len(all_deps) > 10:
            strategies.append("Consider maintenance window for restart")

        return ImpactAnalysis(
            service=service_name,
            direct_dependents=direct_deps,
            indirect_dependents=indirect_deps,
            user_facing_impact=user_facing_impact,
            estimated_recovery_time=recovery_time,
            severity=severity,
            mitigation_strategies=strategies
        )


class AnomalyDetector:
    """Detect anomalies in system behavior."""

    def __init__(self, service_graph: ServiceDependencyGraph):
        self.service_graph = service_graph
        self.baseline_file = Path("/home/kloros/.kloros/infra_baseline.json")
        self.baseline: Dict[str, Dict[str, float]] = {}
        self._load_baseline()

    def _load_baseline(self):
        """Load baseline metrics from disk."""
        if self.baseline_file.exists():
            try:
                with open(self.baseline_file) as f:
                    self.baseline = json.load(f)
                logger.info(f"[infra_awareness] Loaded baseline for {len(self.baseline)} services")
            except Exception as e:
                logger.warning(f"[infra_awareness] Could not load baseline: {e}")

    def _save_baseline(self):
        """Save baseline metrics to disk."""
        try:
            self.baseline_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self.baseline_file, 'w') as f:
                json.dump(self.baseline, f, indent=2)
        except Exception as e:
            logger.error(f"[infra_awareness] Could not save baseline: {e}")

    def update_baseline(self):
        """Update baseline with current metrics."""
        logger.info("[infra_awareness] Updating baseline metrics...")

        for service_name, service_info in self.service_graph.services.items():
            if not service_info.active:
                continue

            memory_mb = service_info.memory_current / (1024 * 1024)

            if service_name not in self.baseline:
                self.baseline[service_name] = {
                    'memory_mb': memory_mb,
                    'restart_count': service_info.restart_count,
                    'samples': 1
                }
            else:
                # Exponential moving average
                alpha = 0.1
                self.baseline[service_name]['memory_mb'] = (
                    alpha * memory_mb +
                    (1 - alpha) * self.baseline[service_name]['memory_mb']
                )
                self.baseline[service_name]['samples'] += 1

        self._save_baseline()

    def detect_anomalies(self) -> List[SystemAnomaly]:
        """Detect anomalies compared to baseline."""
        anomalies = []

        if not self.baseline:
            logger.info("[infra_awareness] No baseline yet, updating...")
            self.update_baseline()
            return []

        logger.info("[infra_awareness] Detecting anomalies...")

        for service_name, service_info in self.service_graph.services.items():
            if not service_info.active or service_name not in self.baseline:
                continue

            baseline = self.baseline[service_name]
            current_memory_mb = service_info.memory_current / (1024 * 1024)
            baseline_memory_mb = baseline['memory_mb']

            # Memory spike detection (2x baseline)
            if current_memory_mb > baseline_memory_mb * 2 and baseline_memory_mb > 100:
                deviation = (current_memory_mb - baseline_memory_mb) / baseline_memory_mb
                anomaly = SystemAnomaly(
                    timestamp=datetime.now(),
                    anomaly_type='memory_spike',
                    service=service_name,
                    severity='high' if current_memory_mb > 10000 else 'medium',
                    description=f"{service_name} memory: {current_memory_mb:.0f}MB vs baseline {baseline_memory_mb:.0f}MB",
                    baseline_value=baseline_memory_mb,
                    current_value=current_memory_mb,
                    deviation=deviation,
                    curiosity_question=f"Why is {service_name} using {current_memory_mb:.0f}MB of memory when baseline is {baseline_memory_mb:.0f}MB?"
                )
                anomalies.append(anomaly)

            # Restart loop detection
            baseline_restarts = baseline.get('restart_count', 0)
            if service_info.restart_count > baseline_restarts + 3:
                anomaly = SystemAnomaly(
                    timestamp=datetime.now(),
                    anomaly_type='restart_loop',
                    service=service_name,
                    severity='high',
                    description=f"{service_name} restart count: {service_info.restart_count} vs baseline {baseline_restarts}",
                    baseline_value=baseline_restarts,
                    current_value=service_info.restart_count,
                    deviation=service_info.restart_count - baseline_restarts,
                    curiosity_question=f"Why has {service_name} restarted {service_info.restart_count - baseline_restarts} times since baseline?"
                )
                anomalies.append(anomaly)

        if anomalies:
            logger.info(f"[infra_awareness] Detected {len(anomalies)} anomalies")
        else:
            logger.info("[infra_awareness] No anomalies detected")

        return anomalies


class InfrastructureAwareness:
    """Main infrastructure awareness system - Phase 1 GLaDOS autonomy."""

    def __init__(self):
        self.service_graph = ServiceDependencyGraph()
        self.resource_economics: Optional[ResourceEconomics] = None
        self.impact_analyzer: Optional[FailureImpactAnalyzer] = None
        self.anomaly_detector: Optional[AnomalyDetector] = None
        self.last_update = datetime.min

    def initialize(self):
        """Initialize all awareness subsystems."""
        logger.info("[infra_awareness] ============================================")
        logger.info("[infra_awareness] Infrastructure Awareness - Phase 1 GLaDOS")
        logger.info("[infra_awareness] ============================================")

        # Build service graph
        services = self.service_graph.build_graph()

        if services:
            # Initialize subsystems
            self.resource_economics = ResourceEconomics(self.service_graph)
            self.impact_analyzer = FailureImpactAnalyzer(self.service_graph)
            self.anomaly_detector = AnomalyDetector(self.service_graph)

            # Initial analysis
            self._run_analysis()

            logger.info("[infra_awareness] ✅ Infrastructure Awareness initialized")
            return True
        else:
            logger.error("[infra_awareness] ❌ Failed to initialize")
            return False

    def _run_analysis(self):
        """Run complete infrastructure analysis."""
        # Resource economics
        costs = self.resource_economics.calculate_costs() if self.resource_economics else {}

        # Log high-cost services
        high_cost = sorted(costs.items(), key=lambda x: x[1].cost_score, reverse=True)[:5]
        logger.info("[infra_awareness] Top 5 resource consumers:")
        for service_name, cost in high_cost:
            logger.info(f"[infra_awareness]   {service_name}: "
                       f"{cost.memory_mb:.0f}MB, cost={cost.cost_score:.2f}, "
                       f"efficiency={cost.efficiency:.2f}")

        # Log critical services
        critical_services = [
            name for name, info in self.service_graph.services.items()
            if info.criticality == 'critical' and info.active
        ]
        logger.info(f"[infra_awareness] Critical services: {len(critical_services)}")

        # Detect anomalies
        if self.anomaly_detector:
            anomalies = self.anomaly_detector.detect_anomalies()
            if anomalies:
                logger.warning(f"[infra_awareness] ⚠️ Detected {len(anomalies)} anomalies")
                for anomaly in anomalies:
                    logger.warning(f"[infra_awareness]   {anomaly.anomaly_type}: {anomaly.description}")

    def update(self):
        """Update infrastructure awareness (call periodically)."""
        # Rate limit: only update every 5 minutes
        if (datetime.now() - self.last_update).total_seconds() < 300:
            return

        logger.info("[infra_awareness] Updating infrastructure awareness...")
        self.service_graph.build_graph()
        self._run_analysis()

        # Update baseline
        if self.anomaly_detector:
            self.anomaly_detector.update_baseline()

        self.last_update = datetime.now()

    def get_service_info(self, service_name: str) -> Optional[ServiceInfo]:
        """Get detailed info about a service."""
        return self.service_graph.services.get(service_name)

    def get_impact_analysis(self, service_name: str) -> Optional[ImpactAnalysis]:
        """Get failure impact analysis for a service."""
        if not self.impact_analyzer:
            return None
        return self.impact_analyzer.analyze_impact(service_name)

    def get_resource_cost(self, service_name: str) -> Optional[ResourceCost]:
        """Get resource cost for a service."""
        if not self.resource_economics:
            return None
        costs = self.resource_economics.calculate_costs()
        return costs.get(service_name)

    def get_anomalies(self) -> List[SystemAnomaly]:
        """Get current anomalies."""
        if not self.anomaly_detector:
            return []
        return self.anomaly_detector.detect_anomalies()

    def generate_curiosity_questions(self) -> List[str]:
        """Generate curiosity questions from anomalies."""
        questions = []
        anomalies = self.get_anomalies()

        for anomaly in anomalies:
            if anomaly.curiosity_question:
                questions.append(anomaly.curiosity_question)

        return questions


# Singleton instance
_infrastructure_awareness: Optional[InfrastructureAwareness] = None


def get_infrastructure_awareness() -> InfrastructureAwareness:
    """Get or create infrastructure awareness singleton."""
    global _infrastructure_awareness
    if _infrastructure_awareness is None:
        _infrastructure_awareness = InfrastructureAwareness()
        _infrastructure_awareness.initialize()
    return _infrastructure_awareness
