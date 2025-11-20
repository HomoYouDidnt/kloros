"""
Dependency injection resolver for wrapper zooid instantiation.

Provides minimal dependency objects needed by legacy implementations
when wrapping them as zooids.
"""

import ast
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Any, Optional, List, Tuple


@dataclass
class ParameterSpec:
    name: str
    has_default: bool
    default_value: Optional[str]
    position: int


class DependencyResolver:
    """Resolves constructor dependencies for legacy class wrapping."""

    def __init__(self):
        self._providers = {
            "kloros_instance": self._provide_mock_kloros,
            "store": self._provide_none,
            "config": self._provide_none,
            "update_interval_minutes": lambda: 60,
            "interval": lambda: 60,
        }

    def _provide_mock_kloros(self) -> Any:
        """Provide a minimal mock KLoROS instance."""
        class MockKLoROS:
            def __init__(self):
                self.memory_system = None

        return MockKLoROS()

    def _provide_none(self) -> None:
        """Provide None for optional parameters."""
        return None

    def resolve(self, param_name: str) -> Any:
        """Resolve a parameter dependency."""
        if param_name in self._providers:
            return self._providers[param_name]()
        return None

    def register_provider(self, param_name: str, provider_func):
        """Register a custom provider for a parameter."""
        self._providers[param_name] = provider_func


def analyze_constructor(file_path: Path, class_name: str) -> Optional[List[ParameterSpec]]:
    """
    Analyze constructor signature to extract parameter requirements.

    Args:
        file_path: Path to Python file containing the class
        class_name: Name of class to analyze

    Returns:
        List of ParameterSpec objects, or None if class not found
    """
    try:
        with open(file_path, 'r') as f:
            tree = ast.parse(f.read())

        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef) and node.name == class_name:
                for item in node.body:
                    if isinstance(item, ast.FunctionDef) and item.name == "__init__":
                        return _extract_parameters(item)

        return None
    except Exception as e:
        print(f"[deps] Failed to analyze {file_path}: {e}")
        return None


def _extract_parameters(init_func: ast.FunctionDef) -> List[ParameterSpec]:
    """Extract parameter specifications from __init__ function."""
    params = []
    args = init_func.args.args[1:]  # Skip 'self'
    defaults = init_func.args.defaults

    num_defaults = len(defaults)
    num_args = len(args)
    first_default_idx = num_args - num_defaults

    for i, arg in enumerate(args):
        has_default = i >= first_default_idx
        default_value = None

        if has_default:
            default_idx = i - first_default_idx
            try:
                default_value = ast.unparse(defaults[default_idx])
            except:
                default_value = "None"

        params.append(ParameterSpec(
            name=arg.arg,
            has_default=has_default,
            default_value=default_value,
            position=i
        ))

    return params


def generate_init_call(
    legacy_class: str,
    params: List[ParameterSpec],
    resolver: Optional[DependencyResolver] = None
) -> str:
    """
    Generate initialization code for legacy class with dependency resolution.

    Args:
        legacy_class: Name of legacy class to instantiate
        params: Parameter specifications from analyze_constructor
        resolver: Dependency resolver (uses default if None)

    Returns:
        Python code string for initialization (no indentation)
    """
    if not params:
        return f"self._impl = {legacy_class}()"

    if resolver is None:
        resolver = DependencyResolver()

    init_args = []
    setup_code = []

    for param in params:
        if param.has_default:
            value = param.default_value if param.default_value != "None" else "None"
            init_args.append(f"{param.name}={value}")
        else:
            var_name = f"_{param.name}"
            setup_code.append(
                f"{var_name} = resolver.resolve('{param.name}')"
            )
            init_args.append(f"{param.name}={var_name}")

    args_str = ", ".join(init_args)

    if setup_code:
        setup_lines = "\n".join(setup_code)
        code = f"from kloros.dream.wrapper_dependencies import DependencyResolver\nresolver = DependencyResolver()\n{setup_lines}\nself._impl = {legacy_class}({args_str})"
    else:
        code = f"self._impl = {legacy_class}({args_str})"

    return code


def infer_init_strategy(file_path: Path, class_name: str) -> Tuple[str, List[ParameterSpec]]:
    """
    Infer initialization strategy for a legacy class.

    Args:
        file_path: Path to file containing the class
        class_name: Name of class to wrap

    Returns:
        (init_code, param_specs) tuple
    """
    params = analyze_constructor(file_path, class_name)

    if params is None:
        return f"self._impl = {class_name}()", []

    init_code = generate_init_call(class_name, params)
    return init_code, params


if __name__ == "__main__":
    test_cases = [
        ("/home/kloros/src/housekeeping_scheduler.py", "HousekeepingScheduler"),
        ("/home/kloros/src/kloros_memory/decay_daemon.py", "DecayDaemon"),
    ]

    for file_path, class_name in test_cases:
        print(f"\n{class_name}:")
        init_code, params = infer_init_strategy(Path(file_path), class_name)
        print(f"  Parameters: {len(params)}")
        for p in params:
            default = f"={p.default_value}" if p.has_default else " (required)"
            print(f"    - {p.name}{default}")
        print(f"\n  Init code:")
        for line in init_code.split('\n'):
            print(f"    {line}")
