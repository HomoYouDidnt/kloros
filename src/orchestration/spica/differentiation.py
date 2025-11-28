import yaml
from pathlib import Path
from typing import Dict, Any, List
from dataclasses import dataclass, field

class ValidationError(Exception):
    pass

@dataclass
class DifferentiationRecipe:
    apiVersion: str
    kind: str
    metadata: Dict[str, Any]
    spec: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "apiVersion": self.apiVersion,
            "kind": self.kind,
            "metadata": self.metadata,
            "spec": self.spec
        }

    def validate(self):
        if self.apiVersion != "spica.kloros/v1":
            raise ValidationError(f"Unsupported apiVersion: {self.apiVersion}")

        if self.kind != "DifferentiationRecipe":
            raise ValidationError(f"kind must be 'DifferentiationRecipe', got: {self.kind}")

        required_metadata = ["name", "version"]
        for field in required_metadata:
            if field not in self.metadata:
                raise ValidationError(f"Missing required metadata field: {field}")

        required_spec = ["target_capability", "prompt_config", "pipeline", "safety", "resources"]
        for field in required_spec:
            if field not in self.spec:
                raise ValidationError(f"Missing required spec field: {field}")

def load_recipe(path: Path) -> DifferentiationRecipe:
    if not path.exists():
        raise FileNotFoundError(f"Recipe not found: {path}")

    with open(path) as f:
        data = yaml.safe_load(f)

    required_top_level = ["apiVersion", "kind", "metadata", "spec"]
    for field in required_top_level:
        if field not in data:
            raise ValidationError(f"Missing required field: {field}")

    recipe = DifferentiationRecipe(
        apiVersion=data["apiVersion"],
        kind=data["kind"],
        metadata=data["metadata"],
        spec=data["spec"]
    )

    recipe.validate()
    return recipe
