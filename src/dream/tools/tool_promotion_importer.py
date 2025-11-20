#!/usr/bin/env python3
"""
Tool Promotion Importer - Applies evolved tool versions with atomic symlink switching.

This handles the promotion flow for tool evolution:
1. Validates promotion metrics against current version
2. Creates new version directory
3. Atomically switches 'current' symlink
4. Writes ACK file for audit trail
5. Updates meta.json with version history
"""

import json
import sys
import hashlib
import subprocess
from pathlib import Path
from datetime import datetime
from typing import Dict, Optional, Tuple


class ToolPromotionImporter:
    """Imports and applies tool promotions with atomic deployment."""

    def __init__(self):
        self.tools_dir = Path("/home/kloros/tools/audio")
        self.promotions_dir = Path("/home/kloros/artifacts/dream/promotions")
        self.ack_dir = Path("/home/kloros/artifacts/dream/promotions_ack")
        self.ack_dir.mkdir(parents=True, exist_ok=True)

    def apply_promotion(self, promotion_file: Path) -> Tuple[bool, Dict]:
        """
        Apply a tool promotion.

        Args:
            promotion_file: Path to promotion.json

        Returns:
            (success, ack_data)
        """
        # Load promotion
        try:
            promotion = json.loads(promotion_file.read_text())
        except Exception as e:
            return False, {"error": f"Failed to load promotion: {e}"}

        # Validate it's a tool promotion
        if promotion.get("type") != "tool":
            return False, {"error": "Not a tool promotion"}

        tool_name = promotion["tool"]
        candidate_version = promotion["candidate_version"]
        promotion_id = promotion["promotion_id"]
        metrics_new = promotion["metrics"]
        checksum = promotion["checksum"]

        print(f"[tool-import] Processing promotion: {promotion_id}")
        print(f"[tool-import] Tool: {tool_name}, Version: {candidate_version}")

        # Get tool directory
        tool_dir = self.tools_dir / tool_name
        if not tool_dir.exists():
            return self._create_ack(promotion_id, "failed", {},
                                   reason=f"Tool directory not found: {tool_dir}")

        # Load current meta
        meta_file = tool_dir / "meta.json"
        if not meta_file.exists():
            return self._create_ack(promotion_id, "failed", {},
                                   reason=f"Tool meta.json not found")

        meta = json.loads(meta_file.read_text())
        current_version = meta["current_version"]

        # Get current version metrics
        current_dir = tool_dir / "versions" / current_version
        current_tool_file = current_dir / f"{tool_name}.py"

        if not current_tool_file.exists():
            return self._create_ack(promotion_id, "failed", {},
                                   reason=f"Current tool file not found: {current_tool_file}")

        # Compare metrics (simple threshold check)
        # In production, would run evaluator on both versions
        is_better, reason = self._compare_metrics(metrics_new, meta)

        if not is_better:
            return self._create_ack(promotion_id, "blocked", {},
                                   reason=reason, metrics=metrics_new)

        # Get candidate tool code from promotion
        candidate_code = promotion.get("tool_code")
        if not candidate_code:
            return self._create_ack(promotion_id, "failed", {},
                                   reason="No tool_code in promotion")

        # Verify checksum
        actual_checksum = "sha256:" + hashlib.sha256(candidate_code.encode()).hexdigest()
        if actual_checksum != checksum:
            return self._create_ack(promotion_id, "failed", {},
                                   reason=f"Checksum mismatch: expected {checksum}, got {actual_checksum}")

        # Create new version directory
        new_version_dir = tool_dir / "versions" / candidate_version
        new_version_dir.mkdir(parents=True, exist_ok=True)

        new_tool_file = new_version_dir / f"{tool_name}.py"
        new_tool_file.write_text(candidate_code)
        new_tool_file.chmod(0o755)  # Make executable

        print(f"[tool-import] Created {new_version_dir}")

        # Atomic symlink switch
        current_link = tool_dir / "current"
        temp_link = tool_dir / f"current.tmp.{datetime.now().timestamp()}"

        try:
            # Create temporary symlink to new version
            temp_link.symlink_to(f"versions/{candidate_version}")

            # Atomically rename temp to current
            temp_link.rename(current_link)

            print(f"[tool-import] Switched current: {current_version} → {candidate_version}")

            # Update meta.json
            meta["current_version"] = candidate_version
            meta["history"].append({
                "version": candidate_version,
                "applied_at": int(datetime.now().timestamp()),
                "source": promotion.get("source", "unknown"),
                "mutation_id": promotion.get("mutation_id", ""),
                "checksum": checksum,
                "reason": promotion.get("reason", "Evolution improvement"),
                "metrics": metrics_new,
                "deltas": promotion.get("deltas", {})
            })

            meta_file.write_text(json.dumps(meta, indent=2))

            # Success!
            changes = {
                "tool": tool_name,
                "old_version": current_version,
                "new_version": candidate_version
            }

            return self._create_ack(promotion_id, "applied", changes,
                                   metrics=metrics_new)

        except Exception as e:
            # Clean up on failure
            if temp_link.exists():
                temp_link.unlink()

            if new_version_dir.exists():
                import shutil
                shutil.rmtree(new_version_dir)

            return self._create_ack(promotion_id, "failed", {},
                                   reason=f"Deployment failed: {e}")

    def _compare_metrics(self, metrics_new: Dict, meta: Dict) -> Tuple[bool, str]:
        """
        Compare new metrics against current version.

        Returns:
            (is_better, reason)
        """
        # Simple heuristic: new version must improve on at least one key metric
        # without regressing on critical metrics

        # Get current metrics from meta history
        current_metrics = {}
        if meta.get("history"):
            latest = meta["history"][-1]
            current_metrics = latest.get("metrics", {})

        if not current_metrics:
            # No baseline - accept if reasonable
            return True, "No baseline metrics"

        # Critical metrics (must not regress)
        fail_rate_new = metrics_new.get("fail_rate", 1.0)
        fail_rate_cur = current_metrics.get("fail_rate", 1.0)

        if fail_rate_new > fail_rate_cur + 0.05:  # Allow 5% tolerance
            return False, f"fail_rate regressed: {fail_rate_cur:.3f} → {fail_rate_new:.3f}"

        # Improvement metrics (must improve on at least one)
        improvements = []

        latency_new = metrics_new.get("latency_ms_p95", 9999)
        latency_cur = current_metrics.get("latency_ms_p95", 9999)
        if latency_new < latency_cur - 1.0:  # 1ms improvement
            improvements.append(f"latency: {latency_cur:.1f}ms → {latency_new:.1f}ms")

        f1_new = metrics_new.get("f1_score", 0.0)
        f1_cur = current_metrics.get("f1_score", 0.0)
        if f1_new > f1_cur + 0.02:  # 2% improvement
            improvements.append(f"f1_score: {f1_cur:.3f} → {f1_new:.3f}")

        qps_new = metrics_new.get("qps", 0.0)
        qps_cur = current_metrics.get("qps", 0.0)
        if qps_new > qps_cur * 1.1:  # 10% throughput improvement
            improvements.append(f"qps: {qps_cur:.1f} → {qps_new:.1f}")

        if improvements:
            return True, f"Improvements: {', '.join(improvements)}"

        return False, "No significant metric improvements"

    def _create_ack(
        self,
        promotion_id: str,
        status: str,
        changes: Dict,
        reason: str = None,
        metrics: Dict = None
    ) -> Tuple[bool, Dict]:
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
            ack["metrics"] = metrics

        # Write ACK file
        ack_file = self.ack_dir / f"{promotion_id.replace(':', '_')}.ack.json"
        try:
            ack_file.write_text(json.dumps(ack, indent=2))
        except Exception as e:
            print(f"[tool-import] Warning: Could not write ACK file: {e}")

        success = (status == "applied")

        if success:
            print(f"[tool-import] ✓ Applied promotion: {promotion_id}")
            if changes:
                print(f"[tool-import]   {changes}")
        else:
            print(f"[tool-import] ✗ {status.capitalize()}: {promotion_id}")
            if reason:
                print(f"[tool-import]   Reason: {reason}")

        return success, ack


def main():
    """Process pending tool promotions."""
    importer = ToolPromotionImporter()

    promotions_dir = Path("/home/kloros/artifacts/dream/promotions")

    # Find tool promotions
    tool_promotions = list(promotions_dir.glob("*_tool.promotion.json"))

    if not tool_promotions:
        print("[tool-import] No tool promotions found")
        return

    for promo_file in tool_promotions:
        print(f"\n[tool-import] Processing {promo_file.name}")
        success, ack = importer.apply_promotion(promo_file)

        if success:
            print(f"[tool-import] SUCCESS")
        else:
            print(f"[tool-import] SKIPPED: {ack.get('reason', 'unknown')}")


if __name__ == "__main__":
    main()
