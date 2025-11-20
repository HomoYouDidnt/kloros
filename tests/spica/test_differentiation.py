import pytest
import yaml
from pathlib import Path
from src.spica.differentiation import DifferentiationRecipe, load_recipe, ValidationError

def test_load_valid_recipe(tmp_path):
    recipe_yaml = """
apiVersion: spica.kloros/v1
kind: DifferentiationRecipe
metadata:
  name: observer-health
  version: "1.0"
spec:
  target_capability: observer
  specialization: health-monitoring
  prompt_config:
    system_prompt: "You are a health observer."
  pipeline:
    - cell: health_monitor
      config:
        threshold: 80
  safety:
    max_tokens: 8192
    kl_drift_persona: 0.5
  resources:
    memory: "2Gi"
    cpu: "1.0"
"""
    recipe_path = tmp_path / "test.yaml"
    recipe_path.write_text(recipe_yaml)

    recipe = load_recipe(recipe_path)
    assert recipe.metadata["name"] == "observer-health"
    assert recipe.spec["target_capability"] == "observer"
    assert recipe.spec["safety"]["max_tokens"] == 8192

def test_load_invalid_recipe_missing_apiVersion(tmp_path):
    recipe_yaml = """
kind: DifferentiationRecipe
metadata:
  name: test
"""
    recipe_path = tmp_path / "bad.yaml"
    recipe_path.write_text(recipe_yaml)

    with pytest.raises(ValidationError, match="Missing required field: apiVersion"):
        load_recipe(recipe_path)

def test_load_invalid_recipe_wrong_kind(tmp_path):
    recipe_yaml = """
apiVersion: spica.kloros/v1
kind: WrongKind
metadata:
  name: test
  version: "1.0"
spec:
  target_capability: observer
  prompt_config:
    system_prompt: "test"
  pipeline: []
  safety:
    max_tokens: 8192
"""
    recipe_path = tmp_path / "bad.yaml"
    recipe_path.write_text(recipe_yaml)

    with pytest.raises(ValidationError, match="kind must be 'DifferentiationRecipe'"):
        load_recipe(recipe_path)

def test_load_invalid_recipe_missing_resources(tmp_path):
    recipe_yaml = """
apiVersion: spica.kloros/v1
kind: DifferentiationRecipe
metadata:
  name: test
  version: "1.0"
spec:
  target_capability: observer
  prompt_config:
    system_prompt: "test"
  pipeline: []
  safety:
    max_tokens: 8192
"""
    recipe_path = tmp_path / "bad.yaml"
    recipe_path.write_text(recipe_yaml)

    with pytest.raises(ValidationError, match="Missing required spec field: resources"):
        load_recipe(recipe_path)

def test_recipe_to_dict():
    recipe = DifferentiationRecipe(
        apiVersion="spica.kloros/v1",
        kind="DifferentiationRecipe",
        metadata={"name": "test"},
        spec={"target_capability": "observer"}
    )
    data = recipe.to_dict()
    assert data["metadata"]["name"] == "test"
