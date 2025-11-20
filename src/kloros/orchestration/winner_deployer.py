"""
D-REAM Winner Deployment Daemon

Purpose:
    Watches D-REAM winners directory and automatically deploys winning
    configurations to close the autonomous learning loop

Workflow:
    1. Watch /home/kloros/artifacts/dream/winners/*.json
    2. Extract best params from new winners
    3. Map params to config keys using domain metadata
    4. Call PromotionApplier to deploy to .kloros_env
    5. (Future: Trigger validation and feedback)

This is the CRITICAL missing link that closes the autonomous loop:
    Observer → Curiosity → D-REAM → 🔗 Winner Deployer → Validation → Learning
"""

import json
import hashlib
import logging
from pathlib import Path
from typing import Dict, Any, Optional, Set
from datetime import datetime
import yaml

logger = logging.getLogger(__name__)


class WinnerDeployer:
    """
    Automatically deploys D-REAM winners to close the autonomous loop.

    Purpose:
        Monitor winners directory and deploy new winning configurations
        without manual intervention (at autonomy level 2+)

    Design:
        - Tracks deployed winners by content hash (prevents re-deployment)
        - Maps D-REAM params to config keys using domain metadata
        - Calls PromotionApplier for actual deployment
        - Logs all deployments for audit trail
    """

    def __init__(
        self,
        winners_dir: Path = Path("/home/kloros/artifacts/dream/winners"),
        dream_config_path: Path = Path("/home/kloros/src/dream/config/dream.yaml"),
        state_path: Path = Path("/home/kloros/.kloros/winner_deployer_state.json"),
        autonomy_level: int = 2
    ):
        """
        Initialize winner deployer.

        Parameters:
            winners_dir: Directory containing winner JSON files
            dream_config_path: Path to dream.yaml for parameter mappings
            state_path: Path to track deployed winners
            autonomy_level: Current autonomy level
        """
        self.winners_dir = winners_dir
        self.dream_config_path = dream_config_path
        self.state_path = state_path
        self.autonomy_level = autonomy_level

        # Track deployed winners
        self.deployed_hashes: Set[str] = set()
        self._load_state()

        # Load dream config for param mappings
        self.dream_config = self._load_dream_config()

        # Import PromotionApplier
        try:
            import sys
            src_path = Path(__file__).parent.parent.parent
            if str(src_path) not in sys.path:
                sys.path.insert(0, str(src_path))

            from dream_promotion_applier import PromotionApplier
            self.promotion_applier = PromotionApplier()
            logger.info("[winner_deployer] PromotionApplier initialized")
        except ImportError as e:
            logger.error(f"[winner_deployer] Failed to import PromotionApplier: {e}")
            self.promotion_applier = None

    def _load_state(self):
        """Load previously deployed winner hashes."""
        if not self.state_path.exists():
            return

        try:
            with open(self.state_path, 'r') as f:
                state = json.load(f)
            self.deployed_hashes = set(state.get("deployed_hashes", []))
            logger.info(f"[winner_deployer] Loaded state: {len(self.deployed_hashes)} previously deployed")
        except Exception as e:
            logger.error(f"[winner_deployer] Failed to load state: {e}")

    def _save_state(self):
        """Save deployed winner hashes."""
        try:
            state = {
                "deployed_hashes": list(self.deployed_hashes),
                "last_updated": datetime.now().isoformat()
            }
            self.state_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.state_path, 'w') as f:
                json.dump(state, f, indent=2)
        except Exception as e:
            logger.error(f"[winner_deployer] Failed to save state: {e}")

    def _load_dream_config(self) -> Dict[str, Any]:
        """Load dream.yaml configuration."""
        if not self.dream_config_path.exists():
            logger.warning(f"[winner_deployer] Dream config not found: {self.dream_config_path}")
            return {}

        try:
            with open(self.dream_config_path, 'r') as f:
                return yaml.safe_load(f)
        except Exception as e:
            logger.error(f"[winner_deployer] Failed to load dream config: {e}")
            return {}

    def _hash_winner(self, winner_data: Dict) -> str:
        """Compute content hash of winner data."""
        # Hash based on params to detect changes
        params = winner_data.get("best", {}).get("params", {})
        params_str = json.dumps(params, sort_keys=True)
        return hashlib.sha256(params_str.encode()).hexdigest()[:16]

    def watch_and_deploy(self) -> Dict[str, Any]:
        """
        Watch winners directory and deploy new winners.

        Returns:
            Dict with deployment summary
        """
        if not self.winners_dir.exists():
            logger.warning(f"[winner_deployer] Winners directory not found: {self.winners_dir}")
            return {"status": "error", "message": "Winners directory not found"}

        deployed_count = 0
        skipped_count = 0
        failed_count = 0

        for winner_file in self.winners_dir.glob("*.json"):
            try:
                # Load winner data
                with open(winner_file, 'r') as f:
                    winner_data = json.load(f)

                # Check if already deployed
                winner_hash = self._hash_winner(winner_data)
                if winner_hash in self.deployed_hashes:
                    skipped_count += 1
                    continue

                # Deploy the winner
                experiment_name = winner_file.stem
                logger.info(f"[winner_deployer] Deploying winner: {experiment_name} (hash={winner_hash})")

                success = self.deploy_winner(experiment_name, winner_data, winner_hash)

                if success:
                    deployed_count += 1
                    self.deployed_hashes.add(winner_hash)
                    self._save_state()
                else:
                    failed_count += 1

            except Exception as e:
                logger.error(f"[winner_deployer] Error processing {winner_file}: {e}")
                failed_count += 1

        return {
            "status": "success",
            "deployed": deployed_count,
            "skipped": skipped_count,
            "failed": failed_count
        }

    def deploy_winner(self, experiment_name: str, winner_data: Dict, winner_hash: str) -> bool:
        """
        Deploy a D-REAM winner.

        Parameters:
            experiment_name: Name of the experiment
            winner_data: Winner JSON data
            winner_hash: Content hash for tracking

        Returns:
            True if deployment successful
        """
        if self.promotion_applier is None:
            logger.error("[winner_deployer] PromotionApplier not available, cannot deploy")
            return False

        # Check autonomy level
        if self.autonomy_level < 2:
            logger.info(f"[winner_deployer] Autonomy level {self.autonomy_level} < 2, skipping auto-deployment")
            return False

        # Extract params
        best = winner_data.get("best", {})
        params = best.get("params", {})
        fitness = best.get("fitness")

        if not params:
            logger.warning(f"[winner_deployer] No params in winner for {experiment_name}")
            return False

        # Map params to apply_map
        apply_map = self._params_to_apply_map(experiment_name, params)

        if not apply_map:
            logger.error(f"[winner_deployer] Could not map params for {experiment_name}")
            logger.error(f"[winner_deployer] Params: {params}")
            return False

        # Create promotion (matches PromotionApplier expected format)
        promotion = {
            "promotion_id": f"{experiment_name}_{winner_hash}",
            "winner": {
                "params": params,
                "metrics": {"fitness": fitness}  # PromotionApplier expects metrics dict
            },
            "apply_map": apply_map,
            "timestamp": winner_data.get("updated_at", datetime.now().isoformat()),
            "_deployed_by": "winner_deployer",
            "_deployed_at": datetime.now().isoformat()
        }

        # Apply via PromotionApplier
        try:
            self.promotion_applier.apply_promotion(promotion, winner_hash)
            logger.info(f"[winner_deployer] ✅ Deployed {experiment_name}: {apply_map}")
            logger.info(f"[winner_deployer]    Fitness: {fitness:.4f}")

            # Trigger hot-reload to apply changes immediately (no restart needed)
            try:
                from src.config.hot_reload import get_config_reloader
                reloader = get_config_reloader()
                reloader.force_reload()
                logger.info(f"[winner_deployer] 🔄 Triggered config hot-reload")
            except Exception as e:
                logger.warning(f"[winner_deployer] Hot-reload trigger failed (non-fatal): {e}")

            # Trigger validation (Priority 2.2: Close learning loop)
            try:
                from . import validation_loop
                domain = self._extract_domain_from_experiment(experiment_name)
                if domain:
                    logger.info(f"[winner_deployer] Triggering validation for {experiment_name} (domain={domain})")
                    validation_result = validation_loop.validate_deployment(
                        deployment_id=winner_hash,
                        experiment_name=experiment_name,
                        domain=domain,
                        deployed_params=params
                    )
                    logger.info(f"[winner_deployer] Validation result: {validation_result['status']}")
                else:
                    logger.warning(f"[winner_deployer] Could not determine domain for {experiment_name}, skipping validation")
            except Exception as e:
                logger.error(f"[winner_deployer] Validation failed (non-fatal): {e}")

            return True
        except Exception as e:
            logger.error(f"[winner_deployer] ❌ Failed to deploy {experiment_name}: {e}")
            return False

    def _params_to_apply_map(self, experiment_name: str, params: Dict) -> Dict[str, Any]:
        """
        Map D-REAM params to config keys using domain metadata.

        Parameters:
            experiment_name: Name of the experiment
            params: D-REAM parameter dict

        Returns:
            apply_map dict mapping config keys to values
        """
        # Try to find param_mapping in dream config
        experiments = self.dream_config.get("experiments", {})

        if experiment_name not in experiments:
            logger.warning(f"[winner_deployer] Experiment {experiment_name} not in dream config")
            return self._fallback_param_mapping(experiment_name, params)

        exp_config = experiments[experiment_name]
        param_mapping = exp_config.get("param_mapping", {})

        if not param_mapping:
            logger.warning(f"[winner_deployer] No param_mapping for {experiment_name}")
            return self._fallback_param_mapping(experiment_name, params)

        # Map params using param_mapping
        apply_map = {}
        for param_name, param_value in params.items():
            config_key = param_mapping.get(param_name)
            if config_key:
                apply_map[config_key] = param_value
            else:
                logger.warning(f"[winner_deployer] No mapping for param '{param_name}' in {experiment_name}")

        return apply_map

    def _fallback_param_mapping(self, experiment_name: str, params: Dict) -> Dict[str, Any]:
        """
        Fallback param mapping using naming conventions.

        Attempts to map params to config keys based on common patterns.
        """
        apply_map = {}

        # Common mapping patterns
        # Format: param_name → KLR_ENVVAR_NAME
        common_mappings = {
            # VLLM
            "context_length": "VLLM_CONTEXT_LENGTH",
            "gpu_layers": "VLLM_GPU_LAYERS",
            "max_tokens": "VLLM_MAX_TOKENS",
            "temperature": "VLLM_TEMPERATURE",

            # TTS
            "speed": "KLR_TTS_SPEED",
            "quality": "KLR_TTS_QUALITY",

            # VAD
            "threshold": "KLR_VAD_THRESHOLD",
            "sensitivity": "KLR_VAD_SENSITIVITY",

            # Conversation
            "max_context_turns": "KLR_MAX_CONTEXT_EVENTS",
            "conversation_timeout": "KLR_CONVERSATION_TIMEOUT",

            # RAG
            "top_k_values": "KLR_RAG_TOP_K",
            "chunk_sizes": "KLR_RAG_CHUNK_SIZE",

            # ASR
            "asr_correction_threshold": "ASR_CORRECTION_THRESHOLD",
        }

        for param_name, param_value in params.items():
            if param_name in common_mappings:
                apply_map[common_mappings[param_name]] = param_value
            else:
                # Try uppercase with KLR_ prefix
                config_key = f"KLR_{param_name.upper()}"
                logger.info(f"[winner_deployer] Fallback mapping: {param_name} → {config_key}")
                apply_map[config_key] = param_value

        return apply_map

    def _extract_domain_from_experiment(self, experiment_name: str) -> Optional[str]:
        """
        Extract domain from experiment name.

        Examples:
            vllm_config_tuning → vllm
            tts_quality_opt → tts
            conversation_tuning → conversation
        """
        # Common domain prefixes
        domains = ["vllm", "tts", "conversation", "rag", "asr", "audio"]

        for domain in domains:
            if experiment_name.lower().startswith(domain):
                return domain

        # Try to extract from name
        parts = experiment_name.lower().split("_")
        if parts and parts[0] in domains:
            return parts[0]

        return None


def run_deployment_cycle():
    """
    Run one deployment cycle (called by coordinator or systemd timer).
    """
    import os
    autonomy_level = int(os.getenv("KLR_AUTONOMY_LEVEL", "0"))

    deployer = WinnerDeployer(autonomy_level=autonomy_level)
    result = deployer.watch_and_deploy()

    logger.info(f"[winner_deployer] Deployment cycle complete: {result}")
    return result


if __name__ == "__main__":
    # Self-test
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    print("=== Winner Deployer Self-Test ===\n")

    deployer = WinnerDeployer()

    print(f"Winners directory: {deployer.winners_dir}")
    print(f"Autonomy level: {deployer.autonomy_level}")
    print(f"Previously deployed: {len(deployer.deployed_hashes)}\n")

    # Run deployment cycle
    result = deployer.watch_and_deploy()

    print("\nDeployment Results:")
    print(f"  Deployed: {result['deployed']}")
    print(f"  Skipped: {result['skipped']}")
    print(f"  Failed: {result['failed']}")
    print(f"  Status: {result['status']}")
