import json
import logging
import uuid
from pathlib import Path
from typing import Dict, List, Optional
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


class EscrowManager:
    def __init__(self, escrow_dir: Optional[Path] = None):
        self.escrow_dir = escrow_dir or Path("/home/kloros/.kloros/escrow")
        self.escrow_dir.mkdir(parents=True, exist_ok=True)

    def add_to_escrow(
        self,
        spica_id: str,
        question_id: str,
        instance_dir: Path,
        test_results: Dict
    ) -> str:
        escrow_id = f"escrow-{uuid.uuid4().hex[:12]}"

        escrow_entry = {
            "schema": "escrow.entry/v1",
            "escrow_id": escrow_id,
            "spica_id": spica_id,
            "question_id": question_id,
            "instance_dir": str(instance_dir),
            "test_results": test_results,
            "status": "pending_review",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "reviewed_at": None,
            "reviewed_by": None,
            "rejection_reason": None
        }

        escrow_file = self.escrow_dir / f"{escrow_id}.json"
        escrow_file.write_text(json.dumps(escrow_entry, indent=2))

        logger.info(f"Added {spica_id} to escrow: {escrow_id}")
        return escrow_id

    def list_pending(self) -> List[Dict]:
        pending = []
        for escrow_file in self.escrow_dir.glob("escrow-*.json"):
            try:
                data = json.loads(escrow_file.read_text())
                if data.get("status") == "pending_review":
                    pending.append(data)
            except Exception as e:
                logger.warning(f"Failed to read escrow file {escrow_file}: {e}")

        return sorted(pending, key=lambda x: x.get("created_at", ""), reverse=True)

    def approve(self, escrow_id: str, reviewed_by: str = "manual") -> bool:
        escrow_file = self.escrow_dir / f"{escrow_id}.json"

        if not escrow_file.exists():
            logger.error(f"Escrow entry not found: {escrow_id}")
            return False

        try:
            data = json.loads(escrow_file.read_text())
            data["status"] = "approved"
            data["reviewed_at"] = datetime.now(timezone.utc).isoformat()
            data["reviewed_by"] = reviewed_by

            escrow_file.write_text(json.dumps(data, indent=2))
            logger.info(f"Approved escrow entry: {escrow_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to approve {escrow_id}: {e}")
            return False

    def reject(self, escrow_id: str, reason: str, reviewed_by: str = "manual") -> bool:
        escrow_file = self.escrow_dir / f"{escrow_id}.json"

        if not escrow_file.exists():
            logger.error(f"Escrow entry not found: {escrow_id}")
            return False

        try:
            data = json.loads(escrow_file.read_text())
            data["status"] = "rejected"
            data["reviewed_at"] = datetime.now(timezone.utc).isoformat()
            data["reviewed_by"] = reviewed_by
            data["rejection_reason"] = reason

            escrow_file.write_text(json.dumps(data, indent=2))
            logger.info(f"Rejected escrow entry: {escrow_id} - {reason}")
            return True
        except Exception as e:
            logger.error(f"Failed to reject {escrow_id}: {e}")
            return False

    def get_entry(self, escrow_id: str) -> Optional[Dict]:
        escrow_file = self.escrow_dir / f"{escrow_id}.json"

        if not escrow_file.exists():
            return None

        try:
            return json.loads(escrow_file.read_text())
        except Exception as e:
            logger.error(f"Failed to read escrow entry {escrow_id}: {e}")
            return None
