#!/usr/bin/env python3
"""
D-REAM Configuration Loader

Loads dream.yaml and provides programmatic access to experiments,
evaluators, and chamber configurations.
"""

import yaml
from pathlib import Path
from typing import Dict, Any, List, Optional
import logging
import importlib

logger = logging.getLogger(__name__)


class DreamConfig:
    """
    D-REAM configuration manager.

    Loads dream.yaml and provides:
    - Experiment lookup by name
    - Chamber evaluator instantiation
    - Search space access
    - Metrics configuration
    """

    def __init__(self, config_path: Optional[Path] = None):
        """
        Initialize D-REAM config loader.

        Args:
            config_path: Path to dream.yaml (defaults to standard location)
        """
        if config_path is None:
            config_path = Path(__file__).parent / "config" / "dream.yaml"

        self.config_path = config_path
        self.config = self._load_config()
        self.experiments = {exp["name"]: exp for exp in self.config.get("experiments", [])}

        logger.info(f"[dream_config] Loaded {len(self.experiments)} experiments from {config_path}")

    def _load_config(self) -> Dict[str, Any]:
        """Load and parse dream.yaml."""
        try:
            with open(self.config_path) as f:
                config = yaml.safe_load(f)
            return config
        except Exception as e:
            logger.error(f"[dream_config] Failed to load {self.config_path}: {e}")
            return {"experiments": []}

    def get_experiment(self, name: str) -> Optional[Dict[str, Any]]:
        """
        Get experiment configuration by name.

        Args:
            name: Experiment name (e.g., "conv_quality_spica")

        Returns:
            Experiment dict or None if not found
        """
        return self.experiments.get(name)

    def get_enabled_experiments(self) -> List[Dict[str, Any]]:
        """Get list of enabled experiments."""
        return [exp for exp in self.experiments.values() if exp.get("enabled", False)]

    def list_experiment_names(self) -> List[str]:
        """Get list of all experiment names."""
        return list(self.experiments.keys())

    def get_evaluator_class(self, experiment_name: str):
        """
        Dynamically load evaluator class for an experiment.

        Args:
            experiment_name: Name of experiment

        Returns:
            Evaluator class or None if failed
        """
        experiment = self.get_experiment(experiment_name)
        if not experiment:
            logger.error(f"[dream_config] Experiment not found: {experiment_name}")
            return None

        evaluator_config = experiment.get("evaluator", {})
        module_path = evaluator_config.get("path")
        class_name = evaluator_config.get("class")

        if not module_path or not class_name:
            logger.error(f"[dream_config] Missing evaluator path/class for {experiment_name}")
            return None

        try:
            # Convert file path to module path
            # /home/kloros/src/phase/domains/spica_conversation.py -> phase.domains.spica_conversation
            module_path_obj = Path(module_path)

            # Find src directory
            parts = module_path_obj.parts
            if "src" in parts:
                src_idx = parts.index("src")
                module_parts = parts[src_idx + 1:]
            else:
                # Assume relative to src
                module_parts = module_path_obj.parts

            # Remove .py extension
            module_parts = list(module_parts)
            if module_parts[-1].endswith(".py"):
                module_parts[-1] = module_parts[-1][:-3]

            module_name = ".".join(module_parts)

            logger.info(f"[dream_config] Loading {class_name} from {module_name}")

            module = importlib.import_module(module_name)
            evaluator_class = getattr(module, class_name)

            return evaluator_class

        except Exception as e:
            logger.error(f"[dream_config] Failed to load evaluator for {experiment_name}: {e}", exc_info=True)
            return None

    def get_search_space(self, experiment_name: str) -> Dict[str, List]:
        """
        Get search space for an experiment.

        Args:
            experiment_name: Name of experiment

        Returns:
            Search space dict mapping param names to value lists
        """
        experiment = self.get_experiment(experiment_name)
        if not experiment:
            return {}

        return experiment.get("search_space", {})

    def get_evaluator_init_kwargs(self, experiment_name: str) -> Dict[str, Any]:
        """
        Get init_kwargs for evaluator instantiation.

        Args:
            experiment_name: Name of experiment

        Returns:
            Dict of kwargs to pass to evaluator constructor
        """
        experiment = self.get_experiment(experiment_name)
        if not experiment:
            return {}

        evaluator_config = experiment.get("evaluator", {})
        return evaluator_config.get("init_kwargs", {})

    def get_metrics_config(self, experiment_name: str) -> Dict[str, Any]:
        """
        Get metrics configuration for an experiment.

        Args:
            experiment_name: Name of experiment

        Returns:
            Metrics config dict
        """
        experiment = self.get_experiment(experiment_name)
        if not experiment:
            return {}

        return experiment.get("metrics", {})

    def get_selector_config(self, experiment_name: str) -> Dict[str, Any]:
        """
        Get selector configuration (tournament mechanics).

        Args:
            experiment_name: Name of experiment

        Returns:
            Selector config dict
        """
        experiment = self.get_experiment(experiment_name)
        if not experiment:
            return {"kind": "rzero", "tournament_size": 4, "survivors": 2}

        return experiment.get("selector", {})


# Singleton instance
_dream_config = None


def get_dream_config(config_path: Optional[Path] = None) -> DreamConfig:
    """
    Get singleton D-REAM config instance.

    Args:
        config_path: Optional custom config path

    Returns:
        DreamConfig instance
    """
    global _dream_config
    if _dream_config is None or config_path is not None:
        _dream_config = DreamConfig(config_path)
    return _dream_config
