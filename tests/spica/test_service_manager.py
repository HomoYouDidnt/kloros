import pytest
import json
import socket
from pathlib import Path
from src.spica.service_manager import SPICAServiceManager
from src.spica.lifecycle import LifecycleState

@pytest.fixture
def test_recipe(tmp_path):
    recipe_path = tmp_path / "test_recipe.yaml"
    recipe_content = """apiVersion: spica.kloros/v1
kind: DifferentiationRecipe
metadata:
  name: test-reasoner
  version: "1.0.0"
  description: Test recipe for reasoner capability
spec:
  target_capability: reasoning
  specialization: logical
  prompt_config:
    system_prompt: "You are a logical reasoning specialist."
    temperature: 0.7
    max_tokens: 2000
  pipeline:
    - analyze_problem
    - generate_hypotheses
    - evaluate_solutions
  safety:
    max_memory_mb: 512
    timeout_seconds: 60
  resources:
    cpu_shares: 1024
"""
    recipe_path.write_text(recipe_content)
    return recipe_path

@pytest.fixture
def manager(tmp_path):
    socket_path = tmp_path / "test.sock"
    registry_path = tmp_path / "registry.json"

    manager = SPICAServiceManager(
        role="test",
        socket_path=str(socket_path),
        registry_path=registry_path
    )

    return manager

def test_manager_initialization(tmp_path):
    socket_path = tmp_path / "test.sock"
    registry_path = tmp_path / "registry.json"

    manager = SPICAServiceManager(
        role="test",
        socket_path=str(socket_path),
        registry_path=registry_path
    )

    status = manager.get_status()
    assert status["role"] == "test"
    assert status["state"] == "pluripotent"
    assert status["recipe"] is None
    assert status["socket"] == str(socket_path)

def test_differentiate_flow(manager, test_recipe):
    result = manager.differentiate(str(test_recipe))

    assert result["success"] is True
    assert result["capability"] == "reasoning"
    assert result["specialization"] == "logical"
    assert result["state"] == "integrated"

    assert manager.lifecycle.current_state == LifecycleState.INTEGRATED

    entry = manager.registry.query("reasoning", "logical")
    assert entry is not None
    assert entry["provider"] == "test"
    assert entry["state"] == "INTEGRATED"

def test_reprogram_from_integrated(manager, test_recipe):
    manager.differentiate(str(test_recipe))

    assert manager.lifecycle.current_state == LifecycleState.INTEGRATED
    assert manager.recipe is not None

    result = manager.reprogram()

    assert result["success"] is True
    assert result["state"] == "pluripotent"
    assert manager.lifecycle.current_state == LifecycleState.PLURIPOTENT
    assert manager.recipe is None

    entry = manager.registry.query("reasoning", "logical")
    assert entry is None

def test_rpc_methods_registered(manager):
    assert "differentiate" in manager.rpc_server.methods
    assert "query_state" in manager.rpc_server.methods
    assert "reprogram" in manager.rpc_server.methods

def test_rpc_differentiate_method(manager, test_recipe):
    manager.start()

    try:
        client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        client.connect(manager.socket_path)

        request = {
            "jsonrpc": "2.0",
            "method": "differentiate",
            "params": {"recipe_path": str(test_recipe)},
            "id": 1
        }

        client.sendall(json.dumps(request).encode())
        response_data = client.recv(4096)
        response = json.loads(response_data.decode())

        assert "result" in response
        assert response["result"]["success"] is True
        assert response["result"]["capability"] == "reasoning"

        client.close()
    finally:
        manager.stop()

def test_rpc_query_state_method(manager):
    manager.start()

    try:
        client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        client.connect(manager.socket_path)

        request = {
            "jsonrpc": "2.0",
            "method": "query_state",
            "params": {},
            "id": 1
        }

        client.sendall(json.dumps(request).encode())
        response_data = client.recv(4096)
        response = json.loads(response_data.decode())

        assert "result" in response
        assert response["result"]["role"] == "test"
        assert response["result"]["state"] == "pluripotent"

        client.close()
    finally:
        manager.stop()

def test_stop_deregisters_when_integrated(manager, test_recipe):
    manager.differentiate(str(test_recipe))

    entry = manager.registry.query("reasoning", "logical")
    assert entry is not None

    manager.start()
    manager.stop()

    entry = manager.registry.query("reasoning", "logical")
    assert entry is None
