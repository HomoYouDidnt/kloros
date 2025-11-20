"""
ToolGen SPICA Domain: Autonomous tool synthesis evaluator for D-REAM.

Wraps ToolGenEvaluator in SPICA interface for evolutionary optimization.
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Dict, Any, Tuple, Optional
import pathlib
import sys
import time
import json

# Add toolgen to path
sys.path.insert(0, str(pathlib.Path.home()))

from toolgen.evaluator import ToolGenEvaluator as ToolGenEvaluatorCore

@dataclass
class ToolSpec:
    """D-REAM variant representing a tool specification."""
    spec_id: str

    def __hash__(self):
        return hash(self.spec_id)

@dataclass
class ToolGenVariant:
    """
    Extended variant with implementation strategy parameters.

    Supports annealing and diversity exploration via impl_style.
    Phase 5: Added adaptive fitness weights.
    """
    spec_id: str
    impl_style: str = "set"  # set/trie/lsh/suffixarray
    anneal_temp: float = 1.0
    weights: Dict[str, float] | None = None  # Phase 5: adaptive weights

    def __hash__(self):
        # Include weights in hash for variant tracking
        w_tuple = tuple(sorted(self.weights.items())) if self.weights else ()
        return hash((self.spec_id, self.impl_style, self.anneal_temp, w_tuple))

class ToolGenEvaluatorSPICA:
    """
    SPICA-compliant wrapper for ToolGen evaluator.
    
    Integrates with D-REAM for evolutionary tool synthesis.
    """
    
    def __init__(self, weights: Dict[str, float] | None = None, epoch: int = 0):
        """
        Initialize evaluator with fitness weights and epoch.

        Args:
            weights: Dict mapping dimension → weight
            epoch: Current epoch number for annealing
        """
        self.evaluator = ToolGenEvaluatorCore(weights=weights)
        self.bundles_root = pathlib.Path.home() / "artifacts" / "toolgen_bundles"
        self.bundles_root.mkdir(parents=True, exist_ok=True)
        self.epoch = epoch
        self.challenger_queue = pathlib.Path("/tmp/toolgen_challengers")

    @staticmethod
    def _sbom_chain_append(bundle_dir: pathlib.Path, lineage_meta: Dict[str, Any]) -> None:
        """
        Extend SBOM.json with supply-chain provenance.

        Args:
            bundle_dir: Path to tool bundle directory
            lineage_meta: Dict with keys:
                - parent: previous artifact SHA256
                - repair: { strategy, pattern_id, attempts }
                - promotion: { winner_epoch, winner_fitness }
        """
        sbom_file = bundle_dir / "SBOM.json"
        sbom = json.loads(sbom_file.read_text()) if sbom_file.exists() else {}

        # Add lineage chain
        sbom.setdefault("lineage", []).append({
            "ts": time.time(),
            "parent": lineage_meta.get("parent"),
            "repair": lineage_meta.get("repair"),
            "promotion": lineage_meta.get("promotion")
        })

        sbom_file.write_text(json.dumps(sbom, indent=2))

    @staticmethod
    def _spec_id_from_path(spec_path: pathlib.Path) -> str:
        """Extract spec ID from spec file path."""
        return spec_path.stem  # e.g., "text_deduplicate"

    def _next_challenger_for(self, spec_id: str) -> Optional[Tuple[Dict[str, Any], pathlib.Path]]:
        """
        Find oldest challenger for this spec ID.

        Args:
            spec_id: Tool specification ID to match

        Returns:
            Tuple of (challenger_metadata, challenger_path) or None if no match
        """
        if not self.challenger_queue.exists():
            return None

        best_challenger = None
        best_ts = None

        for challenger_file in sorted(self.challenger_queue.glob("challenger_*.json")):
            try:
                meta = json.loads(challenger_file.read_text())
                ch_spec_path = meta.get("spec_path", "")

                # Match by spec ID
                if self._spec_id_from_path(pathlib.Path(ch_spec_path)) == spec_id:
                    ts = float(meta.get("ts", challenger_file.stat().st_mtime))

                    # Keep oldest challenger
                    if best_ts is None or ts < best_ts:
                        best_ts = ts
                        best_challenger = (meta, challenger_file)
            except Exception:
                # Skip malformed challenger files
                continue

        return best_challenger

    def _mark_processed(self, challenger_path: pathlib.Path, success: bool, tag: str = "used") -> None:
        """
        Move processed challenger to processed/ subdirectory.

        Args:
            challenger_path: Path to challenger JSON file
            success: Whether evaluation succeeded
            tag: Tag to add to filename
        """
        processed_dir = challenger_path.parent / "processed"
        processed_dir.mkdir(parents=True, exist_ok=True)

        suffix = f".{tag}.ok" if success else f".{tag}.fail"
        new_path = processed_dir / (challenger_path.name + suffix)

        challenger_path.rename(new_path)

    def _load_promotion(self, spec_id: str) -> Optional[Dict[str, Any]]:
        """
        Load promotion for this spec ID if available.

        Args:
            spec_id: Tool specification ID

        Returns:
            Promotion metadata dict or None if no promotion
        """
        promo_file = pathlib.Path("/home/kloros/artifacts/dream/promotions/spica_toolgen.promotion.json")

        if not promo_file.exists():
            return None

        try:
            promo = json.loads(promo_file.read_text())
            apply_map = promo.get("apply_map", {})

            ref_bundle = apply_map.get("TOOLGEN_REFERENCE_BUNDLE")
            promo_spec = apply_map.get("TOOLGEN_ACTIVE_SPEC")

            if not ref_bundle or not promo_spec:
                return None

            # Check if promotion matches this spec
            if spec_id != promo_spec:
                return None

            # Verify bundle still exists
            bundle_path = pathlib.Path(ref_bundle)
            if not bundle_path.exists():
                return None

            return {
                "bundle_dir": ref_bundle,
                "promo_ts": promo.get("ts"),
                "sha256": promo.get("metadata", {}).get("sha256"),
                "winner_fitness": promo.get("winner_fitness")
            }
        except Exception:
            # Skip malformed promotions
            return None

    def evaluate(self, test_input: Dict[str, Any], context: Dict[str, Any] | None = None) -> Dict[str, Any]:
        """
        Evaluate tool synthesis for given parameters.

        Args:
            test_input: Dict with "spec_id" key
            context: Optional context from D-REAM

        Returns:
            Dict with keys:
                - fitness: float [0.0, 1.0]
                - correctness: float
                - safety: float
                - performance: float
                - robustness: float
                - documentation: float
                - bundle_path: str
                - tool_id: str
        """
        # Convert dict params to variant object
        spec_id = test_input.get("spec_id", "")
        impl_style = test_input.get("impl_style", "set")
        anneal_temp = test_input.get("anneal_temp", 1.0)
        weights = test_input.get("weights", None)  # Phase 5: adaptive weights

        variant = ToolGenVariant(
            spec_id=spec_id,
            impl_style=impl_style,
            anneal_temp=anneal_temp,
            weights=weights
        )

        spec_path = pathlib.Path.home() / "toolgen" / "specs" / f"{variant.spec_id}.json"

        if not spec_path.exists():
            return {
                "fitness": 0.0,
                "correctness": 0.0,
                "safety": 0.0,
                "performance": 0.0,
                "robustness": 0.0,
                "documentation": 0.0,
                "bundle_path": "",
                "tool_id": variant.spec_id,
                "error": f"Spec file not found: {spec_path}"
            }

        # Extract variant parameters
        if isinstance(variant, ToolGenVariant):
            impl_style = variant.impl_style
            anneal_temp = variant.anneal_temp
        else:
            impl_style = "set"
            anneal_temp = 1.0

        # 🔁 PHASE 1: Challenger Re-Evaluation Loop
        # Check for repaired tools from RepairLab before synthesizing new ones
        challenger = self._next_challenger_for(variant.spec_id)

        if challenger is not None:
            meta, ch_path = challenger
            bundle_dir = pathlib.Path(meta.get("bundle_dir", ""))

            # Re-evaluate the repaired tool using existing evaluation pipeline
            try:
                result = self.evaluator.evaluate(
                    spec_path,
                    bundle_dir,
                    epoch=self.epoch,
                    impl_style=impl_style,
                    anneal_temp=anneal_temp
                )

                # Add SBOM chain metadata for supply-chain provenance
                self._sbom_chain_append(bundle_dir, {
                    "parent": meta.get("bundle_sha256"),
                    "repair": {
                        "strategy": meta.get("repair_strategy"),
                        "pattern_id": meta.get("repair_pattern_id"),
                        "attempts": meta.get("repair_attempts")
                    },
                    "promotion": None
                })

                # Add challenger lineage metadata for telemetry
                result_dict = {
                    "fitness": result["fitness"],
                    "correctness": result["components"]["correctness"],
                    "safety": result["components"]["safety"],
                    "performance": result["components"]["performance"],
                    "robustness": result["components"]["robustness"],
                    "documentation": result["components"]["documentation"],
                    "diversity_bonus": result["components"]["diversity_bonus"],
                    "bundle_path": result["bundle_path"],
                    "tool_id": result["tool_id"],
                    "test_output": result["test_output"],
                    "violations": result["violations"],
                    "budgets": result["budgets"],
                    "impl_style": result["impl_style"],
                    "epoch": result["epoch"],
                    "median_ms": result.get("median_ms", 0.0),
                    "handoff": result.get("handoff"),
                    # Challenger-specific metadata
                    "lineage": meta.get("lineage", "repairlab_fixed"),
                    "challenger_path": str(ch_path),
                    "challenger_ts": meta.get("ts"),
                    "original_fitness": meta.get("original_fitness", 0.0),
                    # Phase 6 repair telemetry
                    "repair_strategy": meta.get("repair_strategy"),
                    "repair_pattern_id": meta.get("repair_pattern_id"),
                    "repair_attempts": meta.get("repair_attempts"),
                    "repair_details": meta.get("repair_details"),
                    "bundle_sha256": meta.get("bundle_sha256"),
                    # Tournament analytics tag
                    "meta_repair": meta.get("repair_strategy") is not None
                }

                # Mark challenger as processed (success)
                self._mark_processed(ch_path, success=True)

                return result_dict

            except Exception as e:
                # If challenger evaluation fails, mark it and fall back to synthesis
                self._mark_processed(ch_path, success=False)
                # Continue to normal synthesis below

        # 🏅 PHASE 2: Promotion Baseline
        # Use promoted winner as baseline if available
        promotion = self._load_promotion(variant.spec_id)

        if promotion is not None:
            promo_bundle = pathlib.Path(promotion["bundle_dir"])

            # Re-evaluate the promoted winner using existing evaluation pipeline
            try:
                result = self.evaluator.evaluate(
                    spec_path,
                    promo_bundle,
                    epoch=self.epoch,
                    impl_style=impl_style,
                    anneal_temp=anneal_temp
                )

                # Add SBOM chain metadata for promotion provenance
                self._sbom_chain_append(promo_bundle, {
                    "parent": promotion.get("sha256"),
                    "repair": None,
                    "promotion": {
                        "winner_epoch": self.epoch - 1,  # Previous epoch winner
                        "winner_fitness": promotion.get("winner_fitness", 0.0)
                    }
                })

                # Add promotion lineage metadata for telemetry
                result_dict = {
                    "fitness": result["fitness"],
                    "correctness": result["components"]["correctness"],
                    "safety": result["components"]["safety"],
                    "performance": result["components"]["performance"],
                    "robustness": result["components"]["robustness"],
                    "documentation": result["components"]["documentation"],
                    "diversity_bonus": result["components"]["diversity_bonus"],
                    "bundle_path": result["bundle_path"],
                    "tool_id": result["tool_id"],
                    "test_output": result["test_output"],
                    "violations": result["violations"],
                    "budgets": result["budgets"],
                    "impl_style": result["impl_style"],
                    "epoch": result["epoch"],
                    "median_ms": result.get("median_ms", 0.0),
                    "handoff": result.get("handoff"),
                    # Promotion-specific metadata
                    "lineage": "promoted",
                    "promotion_bundle": str(promo_bundle),
                    "promotion_ts": promotion.get("promo_ts"),
                    "original_winner_fitness": promotion.get("winner_fitness", 0.0),
                    # Tournament analytics tag
                    "meta_repair": False
                }

                return result_dict

            except Exception as e:
                # If promotion evaluation fails, fall back to synthesis
                pass

        # Generate unique output directory
        timestamp = int(time.time())
        output_dir = self.bundles_root / f"{variant.spec_id}_{timestamp}"

        try:
            result = self.evaluator.evaluate(
                spec_path,
                output_dir,
                epoch=self.epoch,
                impl_style=impl_style,
                anneal_temp=anneal_temp
            )

            # Add SBOM chain metadata for fresh synthesis
            self._sbom_chain_append(output_dir, {
                "parent": None,  # Fresh synthesis has no parent
                "repair": None,
                "promotion": None
            })

            return {
                "fitness": result["fitness"],
                "correctness": result["components"]["correctness"],
                "safety": result["components"]["safety"],
                "performance": result["components"]["performance"],
                "robustness": result["components"]["robustness"],
                "documentation": result["components"]["documentation"],
                "diversity_bonus": result["components"]["diversity_bonus"],
                "bundle_path": result["bundle_path"],
                "tool_id": result["tool_id"],
                "test_output": result["test_output"],
                "violations": result["violations"],
                "budgets": result["budgets"],
                "impl_style": result["impl_style"],
                "epoch": result["epoch"],
                "median_ms": result.get("median_ms", 0.0),
                "handoff": result.get("handoff"),
                # Tournament analytics tag
                "meta_repair": False
            }
        except Exception as e:
            return {
                "fitness": 0.0,
                "correctness": 0.0,
                "safety": 0.0,
                "performance": 0.0,
                "robustness": 0.0,
                "documentation": 0.0,
                "bundle_path": "",
                "tool_id": variant.spec_id,
                "error": str(e)
            }

def build(config: Dict[str, Any]) -> ToolGenEvaluatorSPICA:
    """
    Build evaluator from D-REAM config.

    Args:
        config: Dict with keys:
            - weights: Optional[Dict[str, float]]
            - epoch: int (default 0)

    Returns:
        Configured ToolGenEvaluatorSPICA instance
    """
    weights = config.get("weights", None)
    epoch = config.get("epoch", 0)
    return ToolGenEvaluatorSPICA(weights=weights, epoch=epoch)

# Convenience alias for D-REAM config
ToolGenEvaluator = ToolGenEvaluatorSPICA
