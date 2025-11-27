import pytest
import json
from pathlib import Path
from src.spica.registry import CapabilityRegistry, RegistrationError

def test_registry_initialization(tmp_path):
    registry_path = tmp_path / "registry.json"
    registry = CapabilityRegistry(registry_path)
    assert registry.storage_path == registry_path
    assert registry_path.exists()

def test_register_capability(tmp_path):
    registry_path = tmp_path / "registry.json"
    registry = CapabilityRegistry(registry_path)

    registry.register(
        capability="observer",
        specialization="health",
        provider="spica-observer@health",
        socket="/run/spica/observer-health.sock",
        version="1.0"
    )

    result = registry.query("observer", "health")
    assert result["provider"] == "spica-observer@health"
    assert result["state"] == "INTEGRATED"
    assert result["socket"] == "/run/spica/observer-health.sock"

def test_query_nonexistent_capability(tmp_path):
    registry_path = tmp_path / "registry.json"
    registry = CapabilityRegistry(registry_path)

    result = registry.query("nonexistent", "capability")
    assert result is None

def test_heartbeat_updates_timestamp(tmp_path):
    registry_path = tmp_path / "registry.json"
    registry = CapabilityRegistry(registry_path)

    registry.register(
        capability="observer",
        specialization="health",
        provider="spica-observer@health",
        socket="/run/spica/observer-health.sock",
        version="1.0"
    )

    first_heartbeat = registry.query("observer", "health")["last_heartbeat"]
    registry.heartbeat("spica-observer@health")
    second_heartbeat = registry.query("observer", "health")["last_heartbeat"]

    assert second_heartbeat > first_heartbeat

def test_deregister_capability(tmp_path):
    registry_path = tmp_path / "registry.json"
    registry = CapabilityRegistry(registry_path)

    registry.register(
        capability="observer",
        specialization="health",
        provider="spica-observer@health",
        socket="/run/spica/observer-health.sock",
        version="1.0"
    )

    assert registry.query("observer", "health") is not None
    registry.deregister("spica-observer@health")
    assert registry.query("observer", "health") is None

def test_list_all_capabilities(tmp_path):
    registry_path = tmp_path / "registry.json"
    registry = CapabilityRegistry(registry_path)

    registry.register("observer", "health", "provider1", "/sock1", "1.0")
    registry.register("observer", "gpu", "provider2", "/sock2", "1.0")
    registry.register("ranker", "default", "provider3", "/sock3", "1.0")

    capabilities = registry.list_all()
    assert len(capabilities) == 2
    assert "observer" in capabilities
    assert len(capabilities["observer"]) == 2

def test_update_state(tmp_path):
    registry_path = tmp_path / "registry.json"
    registry = CapabilityRegistry(registry_path)

    registry.register(
        capability="observer",
        specialization="health",
        provider="spica-observer@health",
        socket="/run/spica/observer-health.sock",
        version="1.0",
        state="SPECIALIZED"
    )

    registry.update_state("spica-observer@health", "INTEGRATED")
    result = registry.query("observer", "health")
    assert result["state"] == "INTEGRATED"
