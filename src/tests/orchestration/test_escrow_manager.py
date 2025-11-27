import pytest
import json
from pathlib import Path
from src.orchestration.core.escrow_manager import EscrowManager


@pytest.fixture
def escrow_dir(tmp_path):
    escrow = tmp_path / "escrow"
    escrow.mkdir()
    return escrow


def test_escrow_manager_init(escrow_dir):
    manager = EscrowManager(escrow_dir=escrow_dir)
    assert manager.escrow_dir == escrow_dir
    assert escrow_dir.exists()


def test_add_to_escrow(escrow_dir):
    manager = EscrowManager(escrow_dir=escrow_dir)

    spica_id = "spica-test123"
    question_id = "orphaned_queue_documents"
    instance_dir = Path("/home/kloros/experiments/spica/instances/spica-test123")
    test_results = {"passed": 10, "failed": 0}

    escrow_id = manager.add_to_escrow(
        spica_id=spica_id,
        question_id=question_id,
        instance_dir=instance_dir,
        test_results=test_results
    )

    assert escrow_id is not None
    escrow_file = escrow_dir / f"{escrow_id}.json"
    assert escrow_file.exists()

    data = json.loads(escrow_file.read_text())
    assert data["spica_id"] == spica_id
    assert data["question_id"] == question_id
    assert data["status"] == "pending_review"


def test_list_pending(escrow_dir):
    manager = EscrowManager(escrow_dir=escrow_dir)

    manager.add_to_escrow("spica-1", "q1", Path("/tmp/sp1"), {})
    manager.add_to_escrow("spica-2", "q2", Path("/tmp/sp2"), {})

    pending = manager.list_pending()
    assert len(pending) == 2


def test_approve_fix(escrow_dir):
    manager = EscrowManager(escrow_dir=escrow_dir)

    escrow_id = manager.add_to_escrow("spica-1", "q1", Path("/tmp/sp1"), {})
    result = manager.approve(escrow_id)

    assert result is True
    escrow_file = escrow_dir / f"{escrow_id}.json"
    data = json.loads(escrow_file.read_text())
    assert data["status"] == "approved"


def test_reject_fix(escrow_dir):
    manager = EscrowManager(escrow_dir=escrow_dir)

    escrow_id = manager.add_to_escrow("spica-1", "q1", Path("/tmp/sp1"), {})
    result = manager.reject(escrow_id, reason="Tests incomplete")

    assert result is True
    escrow_file = escrow_dir / f"{escrow_id}.json"
    data = json.loads(escrow_file.read_text())
    assert data["status"] == "rejected"
    assert data["rejection_reason"] == "Tests incomplete"
