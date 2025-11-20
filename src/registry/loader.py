#!/usr/bin/env python3
"""
Capability Registry Loader

Loads and validates the capabilities.yaml registry, providing runtime
access to system capabilities for self-awareness and introspection.

Governance:
- Self-contained and testable
- Graceful error handling
- Structured logging
- Registered in capabilities.yaml
"""

import yaml
from pathlib import Path
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
import logging

# Setup structured logging
logger = logging.getLogger(__name__)


@dataclass
class Capability:
    """Represents a single system capability."""
    name: str
    module: str
    enabled: bool
    description: str
    guards: List[str] = field(default_factory=list)
    backends: List[Dict[str, Any]] = field(default_factory=list)
    auto_discovered: bool = False
    category: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            'name': self.name,
            'module': self.module,
            'enabled': self.enabled,
            'description': self.description,
            'guards': self.guards,
            'backends': self.backends,
            'auto_discovered': self.auto_discovered,
            'category': self.category
        }


class CapabilityRegistry:
    """
    Central registry for all KLoROS system capabilities.

    Provides runtime introspection of available systems including:
    - Memory (episodic, semantic, RAG)
    - Reasoning (brainmods, AgentFlow, TUMIX)
    - Voice (STT, TTS, VAD)
    - Tools (Browser, Dev, Scholar, XAI)
    - Evolution (D-REAM)

    Purpose:
        Enable KLoROS to have full self-awareness of her capabilities
        for accurate communication with users.

    Outcomes:
        - Loads capabilities.yaml at initialization
        - Provides enabled/disabled system inventory
        - Generates human-readable capability descriptions
        - Enables runtime capability queries
    """

    def __init__(self, registry_path: Optional[Path] = None):
        """
        Initialize capability registry.

        Parameters:
            registry_path: Path to capabilities.yaml (default: src/registry/capabilities.yaml)
        """
        if registry_path is None:
            registry_path = Path(__file__).parent / "capabilities.yaml"

        self.registry_path = registry_path
        self.capabilities: Dict[str, Capability] = {}
        self._raw_data: Dict[str, Any] = {}

        try:
            self._load()
            logger.info(f"[registry] Loaded {len(self.capabilities)} capabilities from {registry_path}")
        except Exception as e:
            logger.error(f"[registry] Failed to load capabilities: {e}")
            # Graceful degradation - empty registry
            self.capabilities = {}

    def _load(self) -> None:
        """Load and parse capabilities.yaml."""
        if not self.registry_path.exists():
            raise FileNotFoundError(f"Registry not found: {self.registry_path}")

        with open(self.registry_path, 'r') as f:
            self._raw_data = yaml.safe_load(f) or {}

        # Parse capabilities
        for key, value in self._raw_data.items():
            if isinstance(value, dict):
                # Handle nested structure (e.g., tts.backends)
                if 'module' in value:
                    # Simple capability
                    self.capabilities[key] = Capability(
                        name=key,
                        module=value.get('module', ''),
                        enabled=value.get('enabled', False),
                        description=value.get('description', ''),
                        guards=value.get('guards', []),
                        auto_discovered=value.get('auto_discovered', False),
                        category=value.get('category')
                    )
                elif 'backends' in value:
                    # Multi-backend capability (e.g., TTS)
                    backends = []
                    for backend in value.get('backends', []):
                        if isinstance(backend, dict):
                            backends.append(backend)

                    self.capabilities[key] = Capability(
                        name=key,
                        module=value.get('router', value.get('module', '')),
                        enabled=value.get('enabled', True),
                        description=value.get('description', ''),
                        backends=backends,
                        auto_discovered=value.get('auto_discovered', False),
                        category=value.get('category')
                    )
                else:
                    # Nested structure (e.g., brainmods)
                    for subkey, subvalue in value.items():
                        if isinstance(subvalue, dict) and 'module' in subvalue:
                            full_name = f"{key}.{subkey}"
                            self.capabilities[full_name] = Capability(
                                name=full_name,
                                module=subvalue.get('module', ''),
                                enabled=subvalue.get('enabled', False),
                                description=subvalue.get('description', ''),
                                auto_discovered=subvalue.get('auto_discovered', False),
                                category=subvalue.get('category')
                            )

    def get_enabled_capabilities(self) -> List[Capability]:
        """
        Get list of all enabled capabilities.

        Returns:
            List of enabled Capability objects
        """
        return [cap for cap in self.capabilities.values() if cap.enabled]

    def get_capability(self, name: str) -> Optional[Capability]:
        """
        Get specific capability by name.

        Parameters:
            name: Capability name (e.g., 'memory', 'rag', 'brainmods.tot')

        Returns:
            Capability object if found, None otherwise
        """
        return self.capabilities.get(name)

    def is_enabled(self, name: str) -> bool:
        """
        Check if a capability is enabled.

        Parameters:
            name: Capability name

        Returns:
            True if enabled, False otherwise
        """
        cap = self.capabilities.get(name)
        return cap.enabled if cap else False

    def get_system_description(self) -> str:
        """
        Generate human-readable description of active systems.

        This description is intended for the LLM's system prompt to provide
        self-awareness of available capabilities.

        Returns:
            Formatted string describing enabled systems
        """
        enabled = self.get_enabled_capabilities()

        if not enabled:
            return "No capabilities currently enabled."

        # Group by category
        categories = {
            'Memory & Knowledge': [],
            'Reasoning & Planning': [],
            'Voice & Audio': [],
            'Agent Tools': [],
            'Evolution & Learning': []
        }

        for cap in enabled:
            name = cap.name
            desc = cap.description

            # Categorize
            if any(kw in name.lower() for kw in ['memory', 'rag', 'scholar']):
                categories['Memory & Knowledge'].append(f"- {name}: {desc}")
            elif any(kw in name.lower() for kw in ['brainmod', 'agentflow', 'tumix']):
                categories['Reasoning & Planning'].append(f"- {name}: {desc}")
            elif any(kw in name.lower() for kw in ['tts', 'stt', 'vad', 'voice']):
                categories['Voice & Audio'].append(f"- {name}: {desc}")
            elif any(kw in name.lower() for kw in ['browser', 'dev', 'xai', 'tool']):
                categories['Agent Tools'].append(f"- {name}: {desc}")
            elif any(kw in name.lower() for kw in ['dream', 'selfcoder']):
                categories['Evolution & Learning'].append(f"- {name}: {desc}")
            else:
                categories['Agent Tools'].append(f"- {name}: {desc}")

        # Build description
        lines = ["ACTIVE SYSTEMS:"]
        lines.append("You are running with the following integrated capabilities:")
        lines.append("")

        for category, items in categories.items():
            if items:
                lines.append(f"{category}:")
                lines.extend(items)
                lines.append("")

        lines.append("These systems are active and integrated. You have full access to their functionality.")

        return "\n".join(lines)

    def get_summary(self) -> Dict[str, Any]:
        """
        Get summary statistics.

        Returns:
            Dictionary with total, enabled, disabled counts
        """
        total = len(self.capabilities)
        enabled = len(self.get_enabled_capabilities())

        return {
            'total': total,
            'enabled': enabled,
            'disabled': total - enabled,
            'registry_path': str(self.registry_path)
        }


# Singleton instance for global access
_registry: Optional[CapabilityRegistry] = None


def get_registry() -> CapabilityRegistry:
    """
    Get or create the global capability registry instance.

    Returns:
        CapabilityRegistry singleton
    """
    global _registry
    if _registry is None:
        _registry = CapabilityRegistry()
    return _registry


def reload_registry() -> CapabilityRegistry:
    """
    Force reload the capability registry.

    Returns:
        Fresh CapabilityRegistry instance
    """
    global _registry
    _registry = CapabilityRegistry()
    return _registry


if __name__ == "__main__":
    # Self-test
    print("=== Capability Registry Self-Test ===\n")

    registry = get_registry()
    summary = registry.get_summary()

    print(f"Registry: {summary['registry_path']}")
    print(f"Total capabilities: {summary['total']}")
    print(f"Enabled: {summary['enabled']}")
    print(f"Disabled: {summary['disabled']}")
    print()

    print(registry.get_system_description())
    print()

    # Test specific lookups
    print("=== Specific Capability Lookups ===")
    test_caps = ['memory', 'rag', 'dream', 'nonexistent']
    for cap_name in test_caps:
        cap = registry.get_capability(cap_name)
        if cap:
            print(f"✓ {cap_name}: {cap.description} (enabled={cap.enabled})")
        else:
            print(f"✗ {cap_name}: Not found")
