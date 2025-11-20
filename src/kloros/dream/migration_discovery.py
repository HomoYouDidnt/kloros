"""
Migration discovery system for identifying unmigrated services.

Scans codebase for daemon/service patterns and identifies candidates
for migration to evolvable zooid infrastructure.
"""

import ast
import json
import subprocess
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import List, Dict, Optional


@dataclass
class UnmigratedSystem:
    name: str
    path: str
    type: str
    entry_point: Optional[str]
    systemd_unit: Optional[str]
    key_functions: List[str]
    core_infrastructure: bool

    def to_dict(self) -> dict:
        return asdict(self)


class MigrationDiscovery:

    def __init__(self, src_root: Path = Path("/home/kloros/src")):
        self.src_root = src_root

    def discover_all(self) -> Dict[str, List[UnmigratedSystem]]:
        systems = []

        systems.extend(self._scan_daemons())
        systems.extend(self._scan_schedulers())
        systems.extend(self._scan_services())

        systemd_units = self._query_systemd_units()
        self._link_systemd_units(systems, systemd_units)

        return {
            "unmigrated_systems": [s.to_dict() for s in systems]
        }

    def _scan_daemons(self) -> List[UnmigratedSystem]:
        daemons = []
        for daemon_file in self.src_root.rglob("*_daemon.py"):
            system = self._analyze_python_file(daemon_file, "daemon")
            if system:
                daemons.append(system)
        return daemons

    def _scan_schedulers(self) -> List[UnmigratedSystem]:
        schedulers = []
        for scheduler_file in self.src_root.rglob("*_scheduler.py"):
            system = self._analyze_python_file(scheduler_file, "scheduler")
            if system:
                schedulers.append(system)
        return schedulers

    def _scan_services(self) -> List[UnmigratedSystem]:
        services = []
        for service_file in self.src_root.rglob("*_service.py"):
            system = self._analyze_python_file(service_file, "service")
            if system:
                services.append(system)
        return services

    def _analyze_python_file(self, file_path: Path, system_type: str) -> Optional[UnmigratedSystem]:
        try:
            with open(file_path, 'r') as f:
                tree = ast.parse(f.read())

            classes = [node.name for node in ast.walk(tree) if isinstance(node, ast.ClassDef)]
            functions = [node.name for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)]

            entry_point = self._infer_entry_point(classes, functions, system_type)
            key_functions = self._extract_key_functions(functions, system_type)

            name = file_path.stem
            core = self._is_core_infrastructure(name, file_path)

            return UnmigratedSystem(
                name=name,
                path=str(file_path),
                type=system_type,
                entry_point=entry_point,
                systemd_unit=None,
                key_functions=key_functions,
                core_infrastructure=core
            )
        except Exception as e:
            print(f"[discovery] Failed to analyze {file_path}: {e}")
            return None

    def _infer_entry_point(self, classes: List[str], functions: List[str], system_type: str) -> Optional[str]:
        if system_type == "daemon":
            for cls in classes:
                if "Daemon" in cls:
                    return f"{cls}.start"
        elif system_type == "scheduler":
            for cls in classes:
                if "Scheduler" in cls:
                    return f"{cls}.run_scheduled_maintenance"

        if "main" in functions:
            return "main"

        return None

    def _extract_key_functions(self, functions: List[str], system_type: str) -> List[str]:
        key_patterns = {
            "daemon": ["start", "run", "tick", "update", "process"],
            "scheduler": ["run", "schedule", "execute", "should_run"],
            "service": ["start", "handle", "process", "execute"]
        }

        patterns = key_patterns.get(system_type, [])
        key_funcs = []

        for func in functions:
            if any(pattern in func.lower() for pattern in patterns):
                key_funcs.append(func)

        return key_funcs[:5]

    def _is_core_infrastructure(self, name: str, path: Path) -> bool:
        core_keywords = [
            "dream_domain",
            "consumer_daemon",
            "remediation_service",
            "cycle_coordinator",
            "bioreactor",
            "graduator",
            "selector"
        ]

        if any(keyword in name for keyword in core_keywords):
            return True

        if "dream" in str(path) and ("domain" in name or "cycle" in name):
            return True

        return False

    def _query_systemd_units(self) -> Dict[str, str]:
        try:
            result = subprocess.run(
                ["systemctl", "list-units", "--all", "--type=service", "--no-pager"],
                capture_output=True,
                text=True,
                timeout=5
            )

            units = {}
            for line in result.stdout.split('\n'):
                if 'klr-' in line:
                    parts = line.split()
                    if parts:
                        unit_name = parts[0]
                        units[unit_name] = line

            return units
        except Exception as e:
            print(f"[discovery] Failed to query systemd: {e}")
            return {}

    def _link_systemd_units(self, systems: List[UnmigratedSystem], units: Dict[str, str]):
        for system in systems:
            unit_name = f"klr-{system.name.replace('_', '-')}.service"
            if unit_name in units:
                system.systemd_unit = unit_name


def discover_unmigrated_systems(output_file: Optional[str] = None) -> Dict:
    discovery = MigrationDiscovery()
    result = discovery.discover_all()

    if output_file:
        with open(output_file, 'w') as f:
            json.dump(result, f, indent=2)
        print(f"[discovery] Wrote results to {output_file}")

    return result


if __name__ == "__main__":
    result = discover_unmigrated_systems("/tmp/unmigrated_systems.json")

    print(f"\n[discovery] Found {len(result['unmigrated_systems'])} unmigrated systems")

    core = [s for s in result['unmigrated_systems'] if s['core_infrastructure']]
    non_core = [s for s in result['unmigrated_systems'] if not s['core_infrastructure']]

    print(f"[discovery] Core infrastructure: {len(core)}")
    print(f"[discovery] Migration candidates: {len(non_core)}")

    print("\n[discovery] Migration candidates:")
    for system in non_core:
        print(f"  - {system['name']} ({system['type']})")
