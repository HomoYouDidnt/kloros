#!/usr/bin/env python3
"""
Rollback Promotion - Revert a promotion using its ACK file.

Usage: rollback_promotion.py <promotion_id>
"""

import json
import sys
from pathlib import Path
from datetime import datetime


def rollback_promotion(promotion_id: str) -> bool:
    """
    Rollback a promotion by reading its ACK file and reverting config changes.

    Args:
        promotion_id: Promotion ID to rollback

    Returns:
        True if successful, False otherwise
    """
    ack_dir = Path("/home/kloros/artifacts/dream/promotions_ack")
    env_file = Path("/home/kloros/.kloros_env")

    # Find ACK file
    ack_file = ack_dir / f"{promotion_id.replace(':', '_')}.ack.json"
    if not ack_file.exists():
        print(f"❌ ACK file not found: {ack_file}")
        return False

    # Load ACK
    try:
        with open(ack_file, 'r') as f:
            ack = json.load(f)
    except Exception as e:
        print(f"❌ Failed to load ACK file: {e}")
        return False

    # Check status
    if ack["status"] != "applied":
        print(f"⚠️  Promotion {promotion_id} was not applied (status: {ack['status']})")
        print(f"   Reason: {ack.get('reason', 'N/A')}")
        return False

    changes = ack.get("changes", {})
    if not changes:
        print(f"⚠️  No changes to rollback for {promotion_id}")
        return True

    # Read current config
    if not env_file.exists():
        print(f"❌ Config file not found: {env_file}")
        return False

    with open(env_file, 'r') as f:
        lines = f.readlines()

    # Revert changes
    reverted = []
    for config_key, change in changes.items():
        old_value = change["old"]

        # Update config lines
        found = False
        for i, line in enumerate(lines):
            if line.strip().startswith(config_key + "="):
                lines[i] = f"{config_key}={old_value}\n"
                found = True
                reverted.append(f"{config_key}: {change['new']} → {old_value}")
                break

        if not found:
            print(f"⚠️  Config key not found: {config_key}")

    # Write back
    try:
        with open(env_file, 'w') as f:
            f.writelines(lines)
    except Exception as e:
        print(f"❌ Failed to write config: {e}")
        return False

    # Log rollback
    rollback_log = Path("/home/kloros/artifacts/dream/tables/rollbacks.jsonl")
    rollback_log.parent.mkdir(parents=True, exist_ok=True)

    try:
        with open(rollback_log, 'a') as f:
            entry = {
                "ts": int(datetime.now().timestamp()),
                "promotion_id": promotion_id,
                "changes_reverted": len(reverted)
            }
            f.write(json.dumps(entry) + '\n')
    except Exception as e:
        print(f"⚠️  Failed to log rollback: {e}")

    # Success
    print(f"✓ Rolled back promotion: {promotion_id}")
    for change in reverted:
        print(f"  - {change}")
    print(f"\n⚠️  Restart KLoROS service for changes to take effect:")
    print(f"   sudo systemctl restart kloros.service")

    return True


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: rollback_promotion.py <promotion_id>")
        print("\nExample:")
        print("  rollback_promotion.py rag_opt_baseline:1761087721")
        sys.exit(1)

    promotion_id = sys.argv[1]
    success = rollback_promotion(promotion_id)
    sys.exit(0 if success else 1)
