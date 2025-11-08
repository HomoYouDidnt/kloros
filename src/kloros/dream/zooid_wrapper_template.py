"""
Zooid wrapper template generator for v0 migrations.

Creates first-generation zooids that delegate to legacy implementations
using the strangler pattern. These wrappers preserve existing behavior
while enabling evolutionary improvements in future generations.
"""

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional

from kloros.dream.wrapper_dependencies import infer_init_strategy


@dataclass
class WrapperSpec:
    system_name: str
    niche: str
    legacy_module: str
    legacy_class: str
    legacy_file_path: str
    entry_method: str
    genome_id: str


def generate_wrapper_code(spec: WrapperSpec) -> str:
    """Generate Python code for a v0 wrapper zooid."""

    init_code, params = infer_init_strategy(Path(spec.legacy_file_path), spec.legacy_class)

    if "\n" in init_code:
        lines = init_code.split("\n")
        init_code_indented = "\n        ".join(lines)
    else:
        init_code_indented = init_code

    template = f'''"""
Zooid wrapper for {spec.system_name} (v0 - legacy delegation).

This is a first-generation zooid that delegates to the legacy
{spec.legacy_class} implementation. Future generations can modify
or replace internal behavior while maintaining the zooid interface.
"""

import time
from pathlib import Path
from typing import Dict, Any, Optional

from {spec.legacy_module} import {spec.legacy_class}


class {spec.legacy_class.replace("Scheduler", "Zooid").replace("Daemon", "Zooid")}:
    """
    Wrapper zooid for {spec.niche} niche.

    Genome metadata:
    - genome_id: {spec.genome_id}
    - parent_lineage: []
    - niche: {spec.niche}
    - generation: 0 (wrapper)
    """

    def __init__(self):
        """Initialize the zooid by wrapping legacy implementation."""
        self.genome_id = "{spec.genome_id}"
        self.niche = "{spec.niche}"
        self.generation = 0

        {init_code_indented}

        self.poll_interval_sec = 60.0
        self.batch_size = 10
        self.timeout_sec = 30
        self.log_level = "INFO"

    def tick(self, now: float, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Execute one tick of the zooid behavior.

        This v0 implementation delegates directly to the legacy code.

        Args:
            now: Current timestamp
            context: Optional context dictionary

        Returns:
            Dictionary with tick results
        """
        try:
            result = self._impl.{spec.entry_method}()

            return {{
                "status": "success",
                "timestamp": now,
                "genome_id": self.genome_id,
                "result": result if result else {{}},
            }}

        except Exception as e:
            return {{
                "status": "error",
                "timestamp": now,
                "genome_id": self.genome_id,
                "error": str(e),
            }}

    def main_loop(self):
        """
        Main execution loop for standalone zooid operation.

        This allows the zooid to run independently as a service.
        """
        print(f"[{{self.genome_id}}] Starting zooid loop for niche: {{self.niche}}")

        while True:
            try:
                now = time.time()
                result = self.tick(now)

                if result["status"] == "success":
                    print(f"[{{self.genome_id}}] Tick completed successfully")
                else:
                    print(f"[{{self.genome_id}}] Tick failed: {{result.get('error')}}")

                time.sleep(self.poll_interval_sec)

            except KeyboardInterrupt:
                print(f"[{{self.genome_id}}] Shutdown requested")
                break
            except Exception as e:
                print(f"[{{self.genome_id}}] Unexpected error: {{e}}")
                time.sleep(self.poll_interval_sec)


if __name__ == "__main__":
    zooid = {spec.legacy_class.replace("Scheduler", "Zooid").replace("Daemon", "Zooid")}()
    zooid.main_loop()
'''

    return template


def infer_wrapper_spec(system: dict) -> Optional[WrapperSpec]:
    """
    Infer wrapper specification from system metadata.

    Args:
        system: System dictionary from discovery + policy

    Returns:
        WrapperSpec if inferable, None otherwise
    """
    name = system['name']
    niche = system.get('suggested_niche')
    path = Path(system['path'])

    if not niche:
        return None

    legacy_module = str(path.relative_to("/home/kloros/src")).replace("/", ".").replace(".py", "")

    legacy_class = None
    entry_method = "run_scheduled_maintenance"

    if "scheduler" in name.lower():
        class_suffix = "Scheduler"
        entry_method = "run_scheduled_maintenance"
    elif "daemon" in name.lower():
        class_suffix = "Daemon"
        entry_method = "start"
    elif "service" in name.lower():
        class_suffix = "Service"
        entry_method = "run"
    else:
        class_suffix = "Handler"
        entry_method = "process"

    parts = name.replace("_scheduler", "").replace("_daemon", "").replace("_service", "")
    legacy_class = "".join(word.capitalize() for word in parts.split("_")) + class_suffix

    if system.get('entry_point'):
        if "." in system['entry_point']:
            legacy_class, entry_method = system['entry_point'].rsplit(".", 1)

    genome_id = f"{niche}_v0_wrapper"

    return WrapperSpec(
        system_name=name,
        niche=niche,
        legacy_module=legacy_module,
        legacy_class=legacy_class,
        legacy_file_path=str(path),
        entry_method=entry_method,
        genome_id=genome_id
    )


def generate_wrapper_zooid(system: dict, output_dir: Path) -> Optional[Path]:
    """
    Generate wrapper zooid code for a system.

    Args:
        system: System dictionary from discovery + policy
        output_dir: Directory to write generated code

    Returns:
        Path to generated file, or None if generation failed
    """
    spec = infer_wrapper_spec(system)
    if not spec:
        print(f"[wrapper] Could not infer spec for {system['name']}")
        return None

    code = generate_wrapper_code(spec)

    output_dir.mkdir(parents=True, exist_ok=True)
    output_file = output_dir / f"{spec.genome_id}.py"

    with open(output_file, 'w') as f:
        f.write(code)

    print(f"[wrapper] Generated wrapper: {output_file}")

    metadata_file = output_dir / f"{spec.genome_id}.json"
    with open(metadata_file, 'w') as f:
        json.dump({
            "genome_id": spec.genome_id,
            "niche": spec.niche,
            "generation": 0,
            "parent_lineage": [],
            "legacy_system": spec.system_name,
            "legacy_module": spec.legacy_module,
            "legacy_class": spec.legacy_class,
            "wrapper": True,
        }, f, indent=2)

    return output_file


def generate_all_wrappers(policy_result: dict, output_dir: Path = Path("/home/kloros/src/zooids/wrappers")) -> list:
    """
    Generate wrapper zooids for all approved systems.

    Args:
        policy_result: Result from apply_migration_policy()
        output_dir: Base directory for wrapper code

    Returns:
        List of generated file paths
    """
    generated = []

    approved = policy_result.get('approved_for_migration', [])

    for system in approved:
        wrapper_file = generate_wrapper_zooid(system, output_dir)
        if wrapper_file:
            generated.append(wrapper_file)

    return generated


if __name__ == "__main__":
    import json
    from pathlib import Path

    policy_file = Path("/tmp/migration_policy_result.json")
    if policy_file.exists():
        with open(policy_file, 'r') as f:
            policy_result = json.load(f)

        generated = generate_all_wrappers(policy_result)

        print(f"\n[wrapper] Generated {len(generated)} wrapper zooids:")
        for path in generated:
            print(f"  - {path}")
    else:
        print(f"[wrapper] Policy file not found: {policy_file}")
        print(f"[wrapper] Run niche_policy.py first")
