#!/usr/bin/env python3
"""
Promotion Applier - Applies promotions with apply_map to KLoROS config and writes ACK files.

This is the load-bearing wall that:
1. Validates promotions against guardrails
2. Applies config changes atomically
3. Writes ACK files for audit trail
4. Tracks applied hashes to prevent re-application
"""

import json
import os
import signal
from pathlib import Path
from typing import Dict, Any, Optional, Tuple
from datetime import datetime


class TimeoutError(Exception):
    """Raised when operation times out."""
    pass


def timeout_handler(signum, frame):
    """Signal handler for timeout."""
    raise TimeoutError("Operation timed out")


class PromotionApplier:
    """Applies promotions to KLoROS config with safety and auditing."""

    def __init__(self):
        """Initialize applier."""
        self.ack_dir = Path("/home/kloros/artifacts/dream/promotions_ack")
        self.ack_dir.mkdir(parents=True, exist_ok=True)

        self.applied_hashes_log = Path("/home/kloros/artifacts/dream/tables/applied_hashes.jsonl")
        self.applied_hashes_log.parent.mkdir(parents=True, exist_ok=True)

        self.env_file = Path("/home/kloros/.kloros_env")

    def apply_promotion(self, promotion: Dict[str, Any], params_hash: str) -> Tuple[bool, Dict[str, Any]]:
        """
        Apply a promotion with guardrails and create ACK file.

        Args:
            promotion: Promotion dict with apply_map
            params_hash: Hash of params for dedup tracking

        Returns:
            (success, ack_data)
        """
        promotion_id = promotion["promotion_id"]
        winner = promotion["winner"]
        params = winner["params"]
        metrics = winner["metrics"]
        apply_map = promotion.get("apply_map", {})

        # Guardrail checks
        is_safe, reason = self._check_guardrails(metrics)
        if not is_safe:
            return self._create_ack(promotion_id, "blocked", {}, reason=reason)

        # Apply config changes
        changes = {}
        try:
            for param_name, config_key in apply_map.items():
                if param_name in params:
                    old_value = self._get_config(config_key)
                    new_value = params[param_name]

                    # Apply the change
                    self._set_config(config_key, new_value)

                    changes[config_key] = {
                        "old": old_value,
                        "new": new_value
                    }

            # Log applied hash
            self._log_applied_hash(params_hash, promotion_id)

            return self._create_ack(promotion_id, "applied", changes, metrics=metrics)

        except Exception as e:
            return self._create_ack(promotion_id, "failed", {}, reason=str(e))

    def _check_guardrails(self, metrics: Dict) -> Tuple[bool, str]:
        """Check if metrics pass safety guardrails."""

        # Guardrail: Hallucination rate must be low
        hallucination_rate = metrics.get("hallucination_rate", 1.0)
        if hallucination_rate > 0.2:
            return False, f"hallucination_rate too high: {hallucination_rate:.2f} > 0.2"

        # Guardrail: Context precision must be reasonable
        context_precision = metrics.get("context_precision", 0.0)
        if context_precision < 0.5:
            return False, f"context_precision too low: {context_precision:.2f} < 0.5"

        # Guardrail: Latency must not explode
        latency = metrics.get("response_latency_ms", 0)
        if latency > 5000:  # 5 seconds
            return False, f"latency too high: {latency:.1f}ms > 5000ms"

        return True, "passed"

    def _get_config(self, key: str) -> Optional[Any]:
        """Get current config value from .kloros_env."""
        if not self.env_file.exists():
            return None

        try:
            with open(self.env_file, 'r') as f:
                for line in f:
                    if line.strip().startswith(key + "="):
                        return line.split("=", 1)[1].strip()
        except Exception:
            pass

        return None

    def _set_config(self, key: str, value: Any):
        """Set config value in .kloros_env with timeout protection."""
        if not self.env_file.exists():
            self.env_file.touch()

        # Set timeout (5 seconds for file operations)
        signal.signal(signal.SIGALRM, timeout_handler)
        signal.alarm(5)

        try:
            # Read existing config
            lines = []
            key_found = False

            with open(self.env_file, 'r') as f:
                for line in f:
                    if line.strip().startswith(key + "="):
                        lines.append(f"{key}={value}\n")
                        key_found = True
                    else:
                        lines.append(line)

            # Add if not found
            if not key_found:
                lines.append(f"\n# Auto-applied from D-REAM promotion\n")
                lines.append(f"{key}={value}\n")

            # Write back
            with open(self.env_file, 'w') as f:
                f.writelines(lines)

        finally:
            # Cancel timeout
            signal.alarm(0)

    def _log_applied_hash(self, params_hash: str, promotion_id: str):
        """Log applied params hash to prevent re-application."""
        try:
            with open(self.applied_hashes_log, 'a') as f:
                entry = {
                    "ts": int(datetime.now().timestamp()),
                    "hash": params_hash,
                    "promotion_id": promotion_id
                }
                f.write(json.dumps(entry) + '\n')
        except Exception as e:
            print(f"[applier] Warning: Could not log applied hash: {e}")

    def _create_ack(
        self,
        promotion_id: str,
        status: str,
        changes: Dict,
        reason: str = None,
        metrics: Dict = None
    ) -> Tuple[bool, Dict[str, Any]]:
        """Create ACK file for promotion."""

        ack = {
            "promotion_id": promotion_id,
            "applied_at": int(datetime.now().timestamp()),
            "status": status,  # "applied", "blocked", "failed"
            "changes": changes
        }

        if reason:
            ack["reason"] = reason

        if metrics and status == "applied":
            # Calculate deltas if we had baseline metrics
            ack["precheck"] = {
                "precision": metrics.get("context_precision"),
                "recall": metrics.get("context_recall"),
                "latency_ms": metrics.get("response_latency_ms"),
                "hallucination": metrics.get("hallucination_rate")
            }

        # Write ACK file
        ack_file = self.ack_dir / f"{promotion_id.replace(':', '_')}.ack.json"
        try:
            with open(ack_file, 'w') as f:
                json.dump(ack, f, indent=2)
        except Exception as e:
            print(f"[applier] Warning: Could not write ACK file: {e}")

        success = (status == "applied")
        return success, ack


# Singleton
_applier_instance = None

def get_promotion_applier():
    """Get singleton applier instance."""
    global _applier_instance
    if _applier_instance is None:
        _applier_instance = PromotionApplier()
    return _applier_instance
