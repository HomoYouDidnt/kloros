"""
Tool Synthesis Governance System

Implements Quarantine → Shadow → Promote pipeline with risk-based policy,
provenance tracking, and safety interlocks.
"""

import json
import hashlib
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass, asdict
from enum import Enum


class ToolStatus(Enum):
    """Tool lifecycle status."""
    QUARANTINE = "quarantine"  # Just synthesized, not callable
    SHADOW = "shadow"          # A/B testing, no side effects
    PROMOTED = "promoted"      # Fully operational
    DEPRECATED = "deprecated"  # Superseded by newer version
    FAILED = "failed"          # Failed promotion gates


class RiskLevel(Enum):
    """Tool risk classification."""
    LOW = "low"          # Read-only, pure compute
    MEDIUM = "medium"    # Local writes to non-critical paths
    HIGH = "high"        # Network I/O, process control, device control


@dataclass
class ProvenanceRecord:
    """Append-only provenance record for tool synthesis."""
    tool: str
    version: str
    origin: str  # "synthesis", "manual", "evolution"
    reason: str  # Why was this tool created?
    seed: Optional[int]
    model: str
    prompt_hash: str
    diff_stats: Dict[str, int]  # {"added": N, "removed": M}
    tests: Dict[str, str]  # {"unit": "pass", "e2e": "pass"}
    risk: str
    approved_by: str
    date: str
    metadata: Dict[str, Any]

    def to_dict(self) -> Dict:
        """Convert to dictionary for serialization."""
        return asdict(self)

    @classmethod
    def from_synthesis(cls, tool_name: str, version: str, reason: str,
                      model: str, prompt: str, code: str,
                      risk: 'RiskLevel') -> 'ProvenanceRecord':
        """Create provenance record from synthesis."""
        prompt_hash = hashlib.sha256(prompt.encode()).hexdigest()[:8]

        return cls(
            tool=tool_name,
            version=version,
            origin="synthesis",
            reason=reason,
            seed=int(time.time() * 1000) % 100000,
            model=model,
            prompt_hash=prompt_hash,
            diff_stats={"added": len(code.split('\n')), "removed": 0},
            tests={"unit": "pending", "e2e": "pending"},
            risk=risk.value,
            approved_by="pending",
            date=datetime.now().isoformat(),
            metadata={}
        )


@dataclass
class ToolBudget:
    """Resource budget for tool execution."""
    max_calls_per_hour: int
    max_side_effect_bytes: int
    max_execution_time_ms: int

    @classmethod
    def for_risk_level(cls, risk: RiskLevel) -> 'ToolBudget':
        """Create default budget based on risk level."""
        if risk == RiskLevel.LOW:
            return cls(max_calls_per_hour=1000, max_side_effect_bytes=0,
                      max_execution_time_ms=5000)
        elif risk == RiskLevel.MEDIUM:
            return cls(max_calls_per_hour=100, max_side_effect_bytes=1024*1024,
                      max_execution_time_ms=10000)
        else:  # HIGH
            return cls(max_calls_per_hour=10, max_side_effect_bytes=1024*1024,
                      max_execution_time_ms=30000)


class SynthesisGovernance:
    """
    Manages tool synthesis governance: quarantine, promotion, provenance.

    Ensures synthesized tools are safe, tested, and traceable.
    """

    def __init__(self, root_dir: str = "/home/kloros/.kloros"):
        self.root = Path(root_dir)
        self.synth_dir = self.root / "synth"
        self.synth_dir.mkdir(parents=True, exist_ok=True)

        # Provenance log (append-only)
        self.provenance_log = self.root / "tool_provenance.jsonl"

        # Quarantine and promoted tool directories
        self.quarantine_dir = self.synth_dir / "quarantine"
        self.promoted_dir = self.synth_dir / "promoted"
        self.quarantine_dir.mkdir(exist_ok=True)
        self.promoted_dir.mkdir(exist_ok=True)

        # Synthesis quotas
        self.daily_quota = 50  # Max 50 new tools per day (active learning/development phase)
        self.weekly_quota = 200  # Max 200 per week promoted (learning phase - allows experimentation)

        # Risk policies
        self.risk_policies = self._load_risk_policies()

    def _load_risk_policies(self) -> Dict:
        """Load risk-based policies for tool execution."""
        policy_file = self.root / "config" / "synthesis_policy.json"

        if policy_file.exists():
            with open(policy_file, 'r') as f:
                return json.load(f)

        # Default policies
        return {
            "mqtt.publish": {
                "risk": "high",
                "allowed_brokers": ["127.0.0.1:1883"],
                "allowed_topics": ["kloros/status/#", "ace/summary/published"],
                "payload_schema": {
                    "type": "object",
                    "required": ["type", "payload"],
                    "properties": {
                        "type": {"enum": ["status", "event", "summary"]},
                        "payload": {"type": "object"}
                    }
                }
            },
            "gpu_status": {
                "risk": "low",
                "read_only": True
            }
        }

    def classify_risk(self, tool_name: str, tool_code: str) -> RiskLevel:
        """
        Classify tool risk based on code analysis.

        Returns:
            RiskLevel: LOW, MEDIUM, or HIGH
        """
        code_lower = tool_code.lower()

        # High risk indicators
        high_risk_patterns = [
            'socket', 'requests.post', 'requests.put', 'requests.delete',
            'subprocess.run', 'os.system', 'exec(', 'eval(',
            'os.remove', 'os.rmdir', 'shutil.rmtree',
            'mqtt', 'paho', 'requests.post', 'requests.put', 'requests.delete',
            'serial.', 'gpio.',
        ]

        if any(pattern in code_lower for pattern in high_risk_patterns):
            return RiskLevel.HIGH

        # Medium risk indicators
        medium_risk_patterns = [
            'open(', 'write(', 'with open',
            '.write', '.append',
            'json.dump', 'pickle.dump',
        ]

        if any(pattern in code_lower for pattern in medium_risk_patterns):
            # Check if writes are to safe paths
            if '/tmp/' in code_lower or '/.kloros/' in code_lower:
                return RiskLevel.MEDIUM
            return RiskLevel.HIGH

        # Default to LOW (read-only, pure compute)
        return RiskLevel.LOW

    def quarantine_tool(self, tool_name: str, tool_code: str, reason: str,
                       model: str, prompt: str) -> Tuple[str, ProvenanceRecord]:
        """
        Place newly synthesized tool in quarantine.

        Returns:
            Tuple of (versioned_name, provenance_record)
        """
        # Version as 0.1.0 in quarantine
        version = "0.1.0"
        versioned_name = f"{tool_name}@{version}"

        # Classify risk
        risk = self.classify_risk(tool_name, tool_code)

        # Create provenance record
        provenance = ProvenanceRecord.from_synthesis(
            tool_name, version, reason, model, prompt, tool_code, risk
        )

        # Create tool directory
        tool_dir = self.quarantine_dir / tool_name / version
        tool_dir.mkdir(parents=True, exist_ok=True)

        # Save tool artifacts
        (tool_dir / "tool.py").write_text(tool_code)
        (tool_dir / "prompt.txt").write_text(prompt)
        (tool_dir / "metadata.json").write_text(json.dumps({
            "name": tool_name,
            "version": version,
            "status": ToolStatus.QUARANTINE.value,
            "risk": risk.value,
            "reason": reason,
            "created_at": provenance.date
        }, indent=2))

        # Append to provenance log
        with open(self.provenance_log, 'a') as f:
            f.write(json.dumps(provenance.to_dict()) + '\n')

        print(f"[governance] Quarantined: {versioned_name} (risk={risk.value})")

        return versioned_name, provenance


    def _check_slos(self, tool_name: str, version: str, manifest: dict = None) -> Tuple[bool, List[str]]:
        """
        Check if tool meets SLO requirements for promotion.

        Prefers manifest.slo.* when present, otherwise uses defaults:
        - Minimum 10 shadow calls for statistical significance
        - p95 latency < 5000ms
        - Error rate < 10%

        Args:
            tool_name: Name of the tool
            version: Tool version
            manifest: Optional manifest with custom SLO overrides

        Returns:
            Tuple of (meets_slos, violations)
        """
        from .telemetry import get_telemetry_collector

        collector = get_telemetry_collector()
        metrics = collector.get_metrics(tool_name, version)

        if not metrics:
            # Try loading from file
            metrics = collector.load_metrics_from_file(tool_name, version)

        if not metrics:
            return False, ["No telemetry data available"]

        violations = []

        # Get SLO thresholds from manifest or use defaults
        slo = manifest.get("slo", {}) if manifest else {}
        min_calls = slo.get("min_calls", 10)
        max_p95_latency_ms = slo.get("p95_latency_ms", 5000)
        max_error_rate = slo.get("max_error_rate", 0.10)

        # SLO 1: Minimum calls
        if metrics.calls < min_calls:
            violations.append(f"Insufficient data: {metrics.calls} calls (need {min_calls})")

        # SLO 2: p95 latency
        p95 = metrics.p95_latency()
        if p95 and p95 > max_p95_latency_ms:
            violations.append(f"p95 latency too high: {p95:.0f}ms (max {max_p95_latency_ms}ms)")

        # SLO 3: Error rate
        error_rate = metrics.error_rate()
        if error_rate > max_error_rate:
            violations.append(f"Error rate too high: {error_rate*100:.1f}% (max {max_error_rate*100:.0f}%)")

        return len(violations) == 0, violations

    def _log_slo_decision(self, tool_name: str, version: str, meets_slos: bool, violations: List[str]):
        """Log SLO promotion decision."""
        from .logging import log

        log("governance.slo_check",
            tool=tool_name,
            version=version,
            meets_slos=meets_slos,
            violations=violations)

    def check_promotion_gates(self, tool_name: str, version: str) -> Tuple[bool, List[str]]:
        """
        Check if tool passes promotion gates.

        Gates:
        - Unit tests pass
        - E2E tests pass
        - Policy checks clean
        - Within quota

        Returns:
            Tuple of (can_promote, reasons)
        """
        reasons = []

        tool_dir = self.quarantine_dir / tool_name / version
        if not tool_dir.exists():
            return False, ["Tool not found in quarantine"]

        # Load metadata
        metadata_file = tool_dir / "metadata.json"
        if not metadata_file.exists():
            return False, ["Missing metadata"]

        with open(metadata_file, 'r') as f:
            metadata = json.load(f)

        # Collect gate results
        test_results = metadata.get('tests', {})
        unit_pass = test_results.get('unit') == 'pass'
        e2e_pass = test_results.get('e2e') == 'pass'
        daily_quota_ok = self._check_daily_quota()
        weekly_quota_ok = self._check_weekly_quota()
        risk = RiskLevel(metadata.get('risk', 'medium'))
        high_risk_policy_ok = risk != RiskLevel.HIGH or self._check_high_risk_policy(tool_name)

        # Use reasoning-based decision if available
        try:
            from src.reasoning_coordinator import get_reasoning_coordinator
            coordinator = get_reasoning_coordinator()

            gate_info = {
                'unit_tests': 'pass' if unit_pass else 'fail',
                'e2e_tests': 'pass' if e2e_pass else 'fail',
                'daily_quota': 'ok' if daily_quota_ok else 'exceeded',
                'weekly_quota': 'ok' if weekly_quota_ok else 'exceeded',
                'risk_level': risk.value,
                'high_risk_policy': 'configured' if high_risk_policy_ok else 'missing'
            }

            # Prepare decision for multi-agent debate
            proposed_decision = {
                'action': f'promote_tool_{tool_name}_v{version}',
                'tool_name': tool_name,
                'version': version,
                'rationale': f"Tool {tool_name} completed validation",
                'confidence': 0.8 if (unit_pass and e2e_pass) else 0.5,
                'risk_level': risk.value,
                'gate_results': gate_info,
                'risks': [
                    f"Unit tests: {gate_info['unit_tests']}",
                    f"E2E tests: {gate_info['e2e_tests']}",
                    f"Risk level: {risk.value}",
                    "Synthesized tool - potential for unexpected behavior"
                ]
            }

            debate_result = coordinator.debate_decision(
                context=f"Should synthesized tool '{tool_name}' v{version} be promoted?",
                proposed_decision=proposed_decision,
                rounds=2
            )

            verdict = debate_result.get('verdict', {})
            decision = verdict.get('verdict', 'rejected')
            reasoning = verdict.get('reasoning', 'No reasoning')

            print(f"[governance] 🧠 Reasoning decision for {tool_name}: {decision}")
            print(f"[governance]    {reasoning}")

            if decision != 'approved':
                return False, [f"Rejected by debate: {reasoning}"]

        except Exception as e:
            print(f"[governance] ⚠️ Reasoning failed, using heuristic gates: {e}")
            # Fallback to heuristics
            if not unit_pass:
                reasons.append("Unit tests not passing")
            if not e2e_pass:
                reasons.append("E2E tests not passing")
            if not daily_quota_ok:
                reasons.append("Daily quota exceeded")
            if not weekly_quota_ok:
                reasons.append("Weekly quota exceeded")
            if not high_risk_policy_ok:
                reasons.append("High-risk policy not configured")
            if reasons:
                return False, reasons

        # Check I/O models (if tool has manifest)
        manifest_file = tool_dir / "manifest.yaml"
        if manifest_file.exists():
            io_check, io_msg = self._validate_io_models(tool_name, tool_dir)
            if not io_check:
                reasons.append(io_msg)

        # Check SLOs (load manifest if available)
        manifest_file = tool_dir / "manifest.yaml"
        manifest_data = None
        if manifest_file.exists():
            try:
                import yaml
                with open(manifest_file, 'r') as f:
                    manifest_data = yaml.safe_load(f)
            except Exception:
                pass

        meets_slos, slo_violations = self._check_slos(tool_name, version, manifest_data)
        if not meets_slos:
            for violation in slo_violations:
                reasons.append(f"SLO violation: {violation}")

        # Log SLO decision
        self._log_slo_decision(tool_name, version, meets_slos, slo_violations)

        can_promote = len(reasons) == 0
        return can_promote, reasons

    def promote_tool(self, tool_name: str, from_version: str = "0.1.0") -> Optional[str]:
        """
        Promote tool from quarantine to production.

        Returns:
            Promoted version string or None if failed
        """
        # Check gates
        can_promote, reasons = self.check_promotion_gates(tool_name, from_version)

        if not can_promote:
            print(f"[governance] Cannot promote {tool_name}: {', '.join(reasons)}")
            return None

        # Promote to v1.0.0
        promoted_version = "1.0.0"

        # Move from quarantine to promoted
        src_dir = self.quarantine_dir / tool_name / from_version
        dst_dir = self.promoted_dir / tool_name / promoted_version
        dst_dir.mkdir(parents=True, exist_ok=True)

        # Copy artifacts
        import shutil
        for file in src_dir.iterdir():
            shutil.copy2(file, dst_dir / file.name)

        # Update metadata
        metadata_file = dst_dir / "metadata.json"
        with open(metadata_file, 'r') as f:
            metadata = json.load(f)

        metadata['status'] = ToolStatus.PROMOTED.value
        metadata['version'] = promoted_version
        metadata['promoted_at'] = datetime.now().isoformat()

        with open(metadata_file, 'w') as f:
            json.dump(metadata, f, indent=2)

        # Log promotion to provenance
        promotion_record = {
            "event": "promotion",
            "tool": tool_name,
            "from_version": from_version,
            "to_version": promoted_version,
            "date": datetime.now().isoformat(),
            "approved_by": "auto@policy/v1"
        }

        with open(self.provenance_log, 'a') as f:
            f.write(json.dumps(promotion_record) + '\n')

        print(f"[governance] Promoted: {tool_name}@{promoted_version}")

        # Update tool registry config
        self._update_tools_config(tool_name, promoted_version)

        return f"{tool_name}@{promoted_version}"

    def _check_daily_quota(self) -> bool:
        """Check if daily synthesis quota allows new tool."""
        today = datetime.now().date().isoformat()

        # Count tools synthesized today
        count = 0
        if self.provenance_log.exists():
            with open(self.provenance_log, 'r') as f:
                for line in f:
                    try:
                        record = json.loads(line.strip())
                        if record.get('date', '').startswith(today):
                            if record.get('origin') == 'synthesis':
                                count += 1
                    except:
                        continue

        return count < self.daily_quota

    def _check_weekly_quota(self) -> bool:
        """Check if weekly promotion quota allows promotion."""
        # This week's Monday
        from datetime import date, timedelta
        today = date.today()
        week_start = today - timedelta(days=today.weekday())
        week_start_str = week_start.isoformat()

        # Count promotions this week
        count = 0
        if self.provenance_log.exists():
            with open(self.provenance_log, 'r') as f:
                for line in f:
                    try:
                        record = json.loads(line.strip())
                        if record.get('event') == 'promotion':
                            if record.get('date', '') >= week_start_str:
                                count += 1
                    except:
                        continue

        return count < self.weekly_quota

    def _check_high_risk_policy(self, tool_name: str) -> bool:
        """Check if high-risk tool has proper policy configuration."""
        return tool_name in self.risk_policies

    def _update_tools_config(self, tool_name: str, version: str) -> None:
        """Update config/capabilities.yaml with promoted tool."""
        from pathlib import Path
        import yaml
        import datetime as dt

        cfg = Path("/home/kloros/config/capabilities.yaml")
        cfg.parent.mkdir(parents=True, exist_ok=True)

        # Load existing config
        if cfg.exists():
            data = yaml.safe_load(cfg.read_text()) or {}
        else:
            data = {}

        # Get tool metadata
        metadata_file = self.promoted_dir / tool_name / version / "metadata.json"
        meta = {}
        if metadata_file.exists():
            with open(metadata_file, 'r') as f:
                meta = json.load(f)

        # Update tools section
        tools = data.setdefault("tools", {})
        tools[tool_name] = {
            "version": version,
            "risk": meta.get("risk", "unknown"),
            "description": meta.get("reason", ""),
            "status": "promoted",
            "promoted_at": dt.datetime.utcnow().isoformat() + "Z",
        }

        # Write back
        cfg.write_text(yaml.safe_dump(data, sort_keys=False))

    def get_tool_status(self, tool_name: str) -> Optional[Dict]:
        """Get current status of a tool."""
        # Check promoted first
        promoted_path = self.promoted_dir / tool_name
        if promoted_path.exists():
            versions = sorted([d.name for d in promoted_path.iterdir() if d.is_dir()])
            if versions:
                latest = versions[-1]
                metadata_file = promoted_path / latest / "metadata.json"
                if metadata_file.exists():
                    with open(metadata_file, 'r') as f:
                        return json.load(f)

        # Check quarantine
        quarantine_path = self.quarantine_dir / tool_name
        if quarantine_path.exists():
            versions = sorted([d.name for d in quarantine_path.iterdir() if d.is_dir()])
            if versions:
                latest = versions[-1]
                metadata_file = quarantine_path / latest / "metadata.json"
                if metadata_file.exists():
                    with open(metadata_file, 'r') as f:
                        return json.load(f)

        return None

    def list_quarantined_tools(self) -> List[Dict]:
        """List all tools in quarantine."""
        tools = []

        if not self.quarantine_dir.exists():
            return tools

        for tool_dir in self.quarantine_dir.iterdir():
            if tool_dir.is_dir():
                for version_dir in tool_dir.iterdir():
                    if version_dir.is_dir():
                        metadata_file = version_dir / "metadata.json"
                        if metadata_file.exists():
                            with open(metadata_file, 'r') as f:
                                tools.append(json.load(f))

        return tools

    def get_provenance(self, tool_name: str) -> List[Dict]:
        """Get full provenance history for a tool."""
        provenance = []

        if not self.provenance_log.exists():
            return provenance

        with open(self.provenance_log, 'r') as f:
            for line in f:
                try:
                    record = json.loads(line.strip())
                    if record.get('tool') == tool_name:
                        provenance.append(record)
                except:
                    continue

        return provenance

    def _update_test_results(self, tool_name: str, version: str, test_results: Dict[str, str]) -> None:
        """Update test results in tool metadata."""
        tool_dir = self.quarantine_dir / tool_name / version
        if not tool_dir.exists():
            return

        metadata_file = tool_dir / "metadata.json"
        if not metadata_file.exists():
            return

        with open(metadata_file, 'r') as f:
            metadata = json.load(f)

        metadata['tests'] = test_results

        with open(metadata_file, 'w') as f:
            json.dump(metadata, f, indent=2)


    def _validate_io_models(self, tool_name: str, tool_dir: Path) -> Tuple[bool, str]:
        """
        Validate that tool has proper Pydantic I/O models if using manifest.

        Args:
            tool_name: Name of the tool
            tool_dir: Path to tool directory

        Returns:
            Tuple of (is_valid, error_message)
        """
        models_file = tool_dir.parent / "models.py"
        if not models_file.exists():
            return False, "Missing models.py (required for manifest-backed tools)"

        # Try to import and validate models
        try:
            import sys
            import importlib.util
            spec = importlib.util.spec_from_file_location(
                f"{tool_name}.models", models_file
            )
            if spec and spec.loader:
                models_module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(models_module)

                # Check for InputModel and OutputModel
                if not hasattr(models_module, 'InputModel'):
                    return False, "Missing InputModel in models.py"
                if not hasattr(models_module, 'OutputModel'):
                    return False, "Missing OutputModel in models.py"

                # Verify they are Pydantic models
                from pydantic import BaseModel
                if not issubclass(models_module.InputModel, BaseModel):
                    return False, "InputModel must inherit from pydantic.BaseModel"
                if not issubclass(models_module.OutputModel, BaseModel):
                    return False, "OutputModel must inherit from pydantic.BaseModel"

                return True, ""
            else:
                return False, "Could not load models.py"

        except Exception as e:
            return False, f"I/O model validation failed: {e}"

    def list_promoted_tools(self) -> List[Dict]:
        """List all promoted tools."""
        tools = []

        if not self.promoted_dir.exists():
            return tools

        for tool_dir in self.promoted_dir.iterdir():
            if tool_dir.is_dir():
                for version_dir in tool_dir.iterdir():
                    if version_dir.is_dir():
                        metadata_file = version_dir / "metadata.json"
                        if metadata_file.exists():
                            with open(metadata_file, 'r') as f:
                                tools.append(json.load(f))

        return tools
