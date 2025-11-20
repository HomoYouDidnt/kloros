#!/usr/bin/env python3
"""
D-REAM Winner Consumer - Reads winning experiments from external runner and feeds them to KLoROS

This bridges the external D-REAM runner (genetic algorithm experiments) with KLoROS's
internal evolution manager. Winners from external experiments become improvement candidates
for autonomous deployment.
"""

import json
import time
import hashlib
from pathlib import Path
from typing import Dict, List, Any, Optional
from datetime import datetime, timedelta


class DreamWinnerConsumer:
    """Consumes winning experiments from external D-REAM runner."""

    def __init__(self):
        """Initialize winner consumer."""
        self.winners_dir = Path("/home/kloros/artifacts/dream/winners")
        self.promotions_dir = Path("/home/kloros/artifacts/dream/promotions")
        self.logs_dir = Path("/home/kloros/logs/dream")
        self.consumed_log = Path("/home/kloros/.kloros/dream_consumed_winners.jsonl")
        self.consumed_log.parent.mkdir(parents=True, exist_ok=True)

        # Track what we've already processed
        self.consumed_winners = self._load_consumed()

        # Track applied parameter hashes to prevent re-applying identical configs
        self.applied_hashes_log = Path("/home/kloros/artifacts/dream/tables/applied_hashes.jsonl")
        self.applied_hashes_log.parent.mkdir(parents=True, exist_ok=True)
        self.applied_hashes = self._load_applied_hashes()

    def _load_consumed(self) -> set:
        """Load set of already-consumed winner IDs."""
        consumed = set()
        if self.consumed_log.exists():
            try:
                with open(self.consumed_log, 'r') as f:
                    for line in f:
                        entry = json.loads(line)
                        consumed.add(entry.get("winner_id"))
            except Exception as e:
                print(f"[dream-consumer] Error loading consumed log: {e}")
        return consumed

    def _load_applied_hashes(self) -> set:
        """Load set of already-applied parameter hashes (novelty/tabu tracking)."""
        hashes = set()
        if self.applied_hashes_log.exists():
            try:
                with open(self.applied_hashes_log, 'r') as f:
                    for line in f:
                        entry = json.loads(line)
                        hashes.add(entry.get("hash"))
            except Exception as e:
                print(f"[dream-consumer] Error loading applied hashes: {e}")
        return hashes

    def _hash_params(self, params: Dict) -> str:
        """Hash parameter dict for deduplication."""
        return hashlib.sha256(json.dumps(params, sort_keys=True).encode()).hexdigest()

    def _mark_consumed(self, winner_id: str, experiment: str):
        """Mark a winner as consumed."""
        try:
            with open(self.consumed_log, 'a') as f:
                entry = {
                    "timestamp": datetime.now().isoformat(),
                    "winner_id": winner_id,
                    "experiment": experiment
                }
                f.write(json.dumps(entry) + '\n')
            self.consumed_winners.add(winner_id)
        except Exception as e:
            print(f"[dream-consumer] Error marking consumed: {e}")

    def get_new_winners(self, max_age_hours: int = 24) -> List[Dict[str, Any]]:
        """
        Get new winning experiments that haven't been consumed yet.
        Prefers promotions with apply_map, falls back to raw winners.

        Args:
            max_age_hours: Only consider winners from last N hours

        Returns:
            List of winner dicts with improvement candidates
        """
        new_winners = []
        cutoff_time = time.time() - (max_age_hours * 3600)

        # PRIORITY 1: Check for explicit promotions with apply_map
        if self.promotions_dir.exists():
            for promo_file in self.promotions_dir.glob("*.promotion.json"):
                try:
                    promo = json.loads(promo_file.read_text())

                    # Check TTL
                    if time.time() > promo["updated_at"] + promo.get("ttl_seconds", 604800):
                        continue

                    promotion_id = promo["promotion_id"]
                    if promotion_id in self.consumed_winners:
                        continue

                    # Check params hash
                    params = promo["winner"].get("params", {})
                    params_hash = self._hash_params(params)
                    if params_hash in self.applied_hashes:
                        print(f"[dream-consumer] Skipping promotion {promotion_id} - params already applied")
                        self._mark_consumed(promotion_id, promo["experiment"])
                        continue

                    # Convert promotion to candidate (with apply_map!)
                    candidate = self._promotion_to_candidate(promo)
                    if candidate:
                        candidate["params_hash"] = params_hash
                        new_winners.append(candidate)
                        self._mark_consumed(promotion_id, promo["experiment"])

                except Exception as e:
                    print(f"[dream-consumer] Error reading {promo_file}: {e}")

        # PRIORITY 2: Fallback to raw winners (legacy)
        if not self.winners_dir.exists():
            return new_winners

        for winner_file in self.winners_dir.glob("*.json"):
            experiment_name = winner_file.stem

            try:
                with open(winner_file, 'r') as f:
                    data = json.load(f)

                # Check if recent enough
                updated_at = data.get("updated_at", 0)
                if updated_at < cutoff_time:
                    continue

                # Create unique ID for this winner
                best = data.get("best", {})
                winner_id = f"{experiment_name}_{updated_at}"

                # Skip if already consumed
                if winner_id in self.consumed_winners:
                    continue

                # Skip if parameter hash already applied (novelty/tabu pressure)
                params = best.get("params", {})
                params_hash = self._hash_params(params)
                if params_hash in self.applied_hashes:
                    print(f"[dream-consumer] Skipping {experiment_name} - params already applied (hash: {params_hash[:8]})")
                    self._mark_consumed(winner_id, experiment_name)
                    continue

                # Convert to improvement candidate
                candidate = self._winner_to_candidate(experiment_name, best, updated_at)
                if candidate:
                    candidate["params_hash"] = params_hash  # Track for dedup after apply
                    new_winners.append(candidate)
                    self._mark_consumed(winner_id, experiment_name)

            except Exception as e:
                print(f"[dream-consumer] Error reading {winner_file}: {e}")

        return new_winners

    def _promotion_to_candidate(self, promo: Dict) -> Optional[Dict[str, Any]]:
        """
        Convert a promotion (with apply_map) to KLoROS improvement candidate.

        Args:
            promo: Promotion dict with apply_map

        Returns:
            Improvement candidate dict
        """
        experiment = promo.get("experiment")
        winner = promo.get("winner", {})
        params = winner.get("params", {})
        metrics = winner.get("metrics", {})
        fitness = winner.get("fitness")
        apply_map = promo.get("apply_map", {})

        if not params or fitness is None:
            return None

        # Map experiment to component
        component_map = {
            "rag_opt_baseline": "rag",
            "audio_latency_trim": "audio",
            "conv_quality_tune": "reasoning"
        }
        component = component_map.get(experiment, "system")

        # Create candidate with explicit apply_map
        candidate = {
            "task_id": promo["promotion_id"],
            "text": f"Apply winning configuration from {experiment} evolution",
            "component": component,
            "priority": self._calculate_priority(fitness, metrics),
            "evidence": "external_dream_promotion",
            "parameter_recommendations": {
                "apply_type": "direct_config_update",
                "apply_map": apply_map,  # <-- KEY: Explicit mapping
                "params": params,
                "metrics": metrics,
                "experiment": experiment
            },
            "source": "external_dream_promotion",
            "fitness": fitness
        }

        return candidate

    def _winner_to_candidate(self, experiment: str, best: Dict, timestamp: int) -> Optional[Dict[str, Any]]:
        """
        Convert a winner from external runner to KLoROS improvement candidate.

        Args:
            experiment: Experiment name (e.g., "rag_opt_baseline")
            best: Best params/metrics from winner file
            timestamp: When winner was found

        Returns:
            Improvement candidate dict or None
        """
        if not best:
            return None

        params = best.get("params", {})
        metrics = best.get("metrics", {})
        fitness = best.get("fitness")

        if not params or fitness is None:
            return None

        # Map experiment to component
        component_map = {
            "rag_opt_baseline": "rag",
            "audio_latency_trim": "audio",
            "conv_quality_tune": "reasoning"
        }
        component = component_map.get(experiment, "system")

        # Create candidate
        candidate = {
            "task_id": f"external_dream_{experiment}_{timestamp}",
            "text": f"Apply winning configuration from {experiment} evolution",
            "component": component,
            "priority": self._calculate_priority(fitness, metrics),
            "evidence": "external_dream_runner",
            "parameter_recommendations": self._extract_recommendations(experiment, params, metrics),
            "source": "external_dream",
            "experiment": experiment,
            "fitness": fitness,
            "metrics": metrics,
            "params": params
        }

        return candidate

    def _calculate_priority(self, fitness: float, metrics: Dict) -> int:
        """Calculate priority (1-10) based on fitness and metrics."""
        if fitness > 0.8:
            return 9
        elif fitness > 0.6:
            return 7
        elif fitness > 0.4:
            return 5
        else:
            return 3

    def _extract_recommendations(self, experiment: str, params: Dict, metrics: Dict) -> Dict[str, Any]:
        """Extract parameter recommendations from winning config."""
        recommendations = {
            "apply_type": "config_update",
            "experiment_source": experiment,
            "winning_params": params,
            "performance_metrics": metrics
        }

        # Add experiment-specific recommendations
        if experiment == "rag_opt_baseline":
            recommendations["rag_config_updates"] = {
                "top_k": params.get("top_k_values"),
                "chunk_size": params.get("chunk_sizes"),
                "similarity_threshold": params.get("similarity_thresholds"),
                "embedder": params.get("embedder")
            }
        elif experiment == "audio_latency_trim":
            recommendations["audio_config_updates"] = {
                "sample_rate": params.get("sample_rates"),
                "frame_size": params.get("frame_sizes"),
                "buffering_strategy": params.get("buffering_strategy"),
                "resampler": params.get("resampler")
            }
        elif experiment == "conv_quality_tune":
            recommendations["conversation_config_updates"] = {
                "max_context_turns": params.get("max_context_turns"),
                "response_length_tokens": params.get("response_length_tokens"),
                "anti_hallucination_mode": params.get("anti_hallucination_mode"),
                "cite_threshold": params.get("cite_threshold")
            }

        return recommendations


# Singleton instance
_consumer_instance = None

def get_winner_consumer():
    """Get singleton consumer instance."""
    global _consumer_instance
    if _consumer_instance is None:
        _consumer_instance = DreamWinnerConsumer()
    return _consumer_instance
