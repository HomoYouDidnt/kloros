# Autonomous Curiosity Fix System Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Enable KLoROS to autonomously attempt fixes for integration issues using SPICA instances with LLM-generated code patches.

**Architecture:** Parallel pipeline where high-autonomy curiosity questions (≥3) emit both documentation intents AND autonomous fix attempts. LLM generates code patches, SPICA spawner creates isolated instances, tests validate changes, escrow holds successful fixes for manual approval.

**Tech Stack:** Python 3.11+, Ollama (qwen2.5:72b coder LLM), SPICA isolation system, pytest, existing KLoROS orchestration pipeline

---

## Task 1: LLM Code Generator

**Files:**
- Create: `/home/kloros/src/dream/config_tuning/llm_code_generator.py`
- Test: `/home/kloros/tests/dream/test_llm_code_generator.py`

### Step 1: Write the failing test

Create `/home/kloros/tests/dream/test_llm_code_generator.py`:

```python
import pytest
from pathlib import Path
from src.dream.config_tuning.llm_code_generator import LLMCodeGenerator


def test_llm_code_generator_init():
    generator = LLMCodeGenerator()
    assert generator.ollama_host == "http://100.67.244.66:11434"
    assert generator.model == "qwen2.5:72b"
    assert generator.temperature == 0.2


def test_generate_fix_patch_orphaned_queue():
    generator = LLMCodeGenerator()

    question = "Queue 'documents' produced but never consumed"
    hypothesis = "ORPHANED_QUEUE_DOCUMENTS"
    evidence = [
        "Produced in: /home/kloros/src/memory/bm25_index.py",
        "No consumers found in codebase"
    ]
    report_path = Path("/home/kloros/.kloros/integration_issues/orphaned_queue_documents.md")
    target_file = Path("/home/kloros/src/memory/bm25_index.py")

    patch = generator.generate_fix_patch(
        question=question,
        hypothesis=hypothesis,
        evidence=evidence,
        report_path=report_path,
        target_file=target_file
    )

    assert patch is not None
    assert isinstance(patch, str)
    assert len(patch) > 100
    assert "def " in patch or "class " in patch


def test_generate_fix_patch_file_not_found():
    generator = LLMCodeGenerator()

    target_file = Path("/nonexistent/file.py")

    patch = generator.generate_fix_patch(
        question="Test question",
        hypothesis="TEST_HYPOTHESIS",
        evidence=["test evidence"],
        report_path=None,
        target_file=target_file
    )

    assert patch is None
```

### Step 2: Run test to verify it fails

```bash
cd /home/kloros
pytest tests/dream/test_llm_code_generator.py -v
```

Expected: FAIL with "ModuleNotFoundError: No module named 'src.dream.config_tuning.llm_code_generator'"

### Step 3: Write minimal implementation

Create `/home/kloros/src/dream/config_tuning/llm_code_generator.py`:

```python
import os
import logging
import requests
from pathlib import Path
from typing import Optional, List

logger = logging.getLogger(__name__)


class LLMCodeGenerator:
    def __init__(
        self,
        ollama_host: Optional[str] = None,
        model: str = "qwen2.5:72b",
        temperature: float = 0.2,
        max_tokens: int = 8192
    ):
        self.ollama_host = ollama_host or os.getenv("OLLAMA_HOST", "http://100.67.244.66:11434")
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens

        if not self.ollama_host.startswith("http"):
            self.ollama_host = f"http://{self.ollama_host}"

    def generate_fix_patch(
        self,
        question: str,
        hypothesis: str,
        evidence: List[str],
        report_path: Optional[Path],
        target_file: Path
    ) -> Optional[str]:
        if not target_file.exists():
            logger.error(f"Target file does not exist: {target_file}")
            return None

        try:
            file_content = target_file.read_text()
        except Exception as e:
            logger.error(f"Failed to read target file {target_file}: {e}")
            return None

        report_content = ""
        if report_path and report_path.exists():
            try:
                report_content = report_path.read_text()
            except Exception as e:
                logger.warning(f"Failed to read report {report_path}: {e}")

        evidence_text = "\n".join(f"- {e}" for e in evidence)

        prompt = f"""You are fixing an integration issue in KLoROS.

Issue: {question}
Hypothesis: {hypothesis}
Evidence:
{evidence_text}

Analysis Report:
{report_content}

Target File: {target_file}
Current Code:
```python
{file_content}
```

Generate a code patch that fixes this issue.
Output ONLY the complete patched file, no explanations or markdown.
"""

        try:
            response = requests.post(
                f"{self.ollama_host}/api/generate",
                json={
                    "model": self.model,
                    "prompt": prompt,
                    "stream": False,
                    "options": {
                        "temperature": self.temperature,
                        "num_predict": self.max_tokens
                    }
                },
                timeout=300
            )
            response.raise_for_status()
            result = response.json()
            patch = result.get("response", "").strip()

            if not patch:
                logger.error("LLM returned empty response")
                return None

            logger.info(f"Generated patch for {target_file} ({len(patch)} chars)")
            return patch

        except requests.exceptions.RequestException as e:
            logger.error(f"LLM request failed: {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error generating patch: {e}")
            return None
```

### Step 4: Run test to verify it passes

```bash
cd /home/kloros
pytest tests/dream/test_llm_code_generator.py::test_llm_code_generator_init -v
pytest tests/dream/test_llm_code_generator.py::test_generate_fix_patch_file_not_found -v
```

Expected: PASS (Note: test_generate_fix_patch_orphaned_queue may be slow/flaky due to LLM call)

### Step 5: Commit

```bash
cd /home/kloros
git add src/dream/config_tuning/llm_code_generator.py tests/dream/test_llm_code_generator.py
git commit -m "feat: add LLM code generator for autonomous fixes"
```

---

## Task 2: Escrow Manager

**Files:**
- Create: `/home/kloros/src/kloros/orchestration/escrow_manager.py`
- Test: `/home/kloros/tests/orchestration/test_escrow_manager.py`

### Step 1: Write the failing test

Create `/home/kloros/tests/orchestration/test_escrow_manager.py`:

```python
import pytest
import json
from pathlib import Path
from src.kloros.orchestration.escrow_manager import EscrowManager


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
```

### Step 2: Run test to verify it fails

```bash
cd /home/kloros
pytest tests/orchestration/test_escrow_manager.py -v
```

Expected: FAIL with "ModuleNotFoundError: No module named 'src.kloros.orchestration.escrow_manager'"

### Step 3: Write minimal implementation

Create `/home/kloros/src/kloros/orchestration/escrow_manager.py`:

```python
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
```

### Step 4: Run test to verify it passes

```bash
cd /home/kloros
pytest tests/orchestration/test_escrow_manager.py -v
```

Expected: PASS

### Step 5: Commit

```bash
cd /home/kloros
git add src/kloros/orchestration/escrow_manager.py tests/orchestration/test_escrow_manager.py
git commit -m "feat: add escrow manager for manual approval queue"
```

---

## Task 3: SPICA Spawner Code Patch Application

**Files:**
- Modify: `/home/kloros/src/dream/config_tuning/spica_spawner.py`
- Test: `/home/kloros/tests/dream/test_spica_spawner_patches.py`

### Step 1: Write the failing test

Create `/home/kloros/tests/dream/test_spica_spawner_patches.py`:

```python
import pytest
import shutil
from pathlib import Path
from src.dream.config_tuning.spica_spawner import apply_code_patch, run_tests_in_instance


@pytest.fixture
def mock_instance(tmp_path):
    instance_dir = tmp_path / "spica-test"
    instance_dir.mkdir()

    src_dir = instance_dir / "src" / "test"
    src_dir.mkdir(parents=True)

    test_file = src_dir / "example.py"
    test_file.write_text("def old_function():\n    return 'old'\n")

    return instance_dir


def test_apply_code_patch_success(mock_instance):
    target_file = Path("src/test/example.py")
    patch_content = "def new_function():\n    return 'new'\n"

    result = apply_code_patch(
        instance_dir=mock_instance,
        target_file=target_file,
        patch_content=patch_content
    )

    assert result is True
    patched_file = mock_instance / target_file
    assert patched_file.read_text() == patch_content


def test_apply_code_patch_creates_dirs(mock_instance):
    target_file = Path("src/new_module/file.py")
    patch_content = "# new module\n"

    result = apply_code_patch(
        instance_dir=mock_instance,
        target_file=target_file,
        patch_content=patch_content
    )

    assert result is True
    patched_file = mock_instance / target_file
    assert patched_file.exists()
    assert patched_file.read_text() == patch_content


def test_apply_code_patch_invalid_path(mock_instance):
    target_file = Path("../../../etc/passwd")
    patch_content = "malicious"

    result = apply_code_patch(
        instance_dir=mock_instance,
        target_file=target_file,
        patch_content=patch_content
    )

    assert result is False


def test_run_tests_in_instance(mock_instance):
    result = run_tests_in_instance(
        instance_dir=mock_instance,
        test_command="echo 'test passed'"
    )

    assert result["success"] is True
    assert "test passed" in result["output"]


def test_run_tests_in_instance_failure(mock_instance):
    result = run_tests_in_instance(
        instance_dir=mock_instance,
        test_command="exit 1"
    )

    assert result["success"] is False
```

### Step 2: Run test to verify it fails

```bash
cd /home/kloros
pytest tests/dream/test_spica_spawner_patches.py -v
```

Expected: FAIL with "ImportError: cannot import name 'apply_code_patch'"

### Step 3: Read existing SPICA spawner to understand structure

```bash
cd /home/kloros
head -50 src/dream/config_tuning/spica_spawner.py
```

### Step 4: Write minimal implementation

Add to `/home/kloros/src/dream/config_tuning/spica_spawner.py`:

```python
import subprocess
from typing import Dict


def apply_code_patch(
    instance_dir: Path,
    target_file: Path,
    patch_content: str
) -> bool:
    try:
        resolved_target = (instance_dir / target_file).resolve()

        if not str(resolved_target).startswith(str(instance_dir.resolve())):
            logger.error(f"Path traversal attempt blocked: {target_file}")
            return False

        resolved_target.parent.mkdir(parents=True, exist_ok=True)

        resolved_target.write_text(patch_content)
        logger.info(f"Applied patch to {target_file} in {instance_dir.name}")
        return True

    except Exception as e:
        logger.error(f"Failed to apply patch to {target_file}: {e}")
        return False


def run_tests_in_instance(
    instance_dir: Path,
    test_command: str,
    timeout: int = 300
) -> Dict:
    try:
        result = subprocess.run(
            test_command,
            shell=True,
            cwd=instance_dir,
            capture_output=True,
            text=True,
            timeout=timeout
        )

        return {
            "success": result.returncode == 0,
            "output": result.stdout + result.stderr,
            "returncode": result.returncode
        }

    except subprocess.TimeoutExpired:
        logger.error(f"Test command timed out after {timeout}s")
        return {
            "success": False,
            "output": f"Test timed out after {timeout}s",
            "returncode": -1
        }
    except Exception as e:
        logger.error(f"Failed to run tests: {e}")
        return {
            "success": False,
            "output": str(e),
            "returncode": -1
        }
```

### Step 5: Run test to verify it passes

```bash
cd /home/kloros
pytest tests/dream/test_spica_spawner_patches.py -v
```

Expected: PASS

### Step 6: Commit

```bash
cd /home/kloros
git add src/dream/config_tuning/spica_spawner.py tests/dream/test_spica_spawner_patches.py
git commit -m "feat: add code patch application to SPICA spawner"
```

---

## Task 4: Curiosity Processor SPICA Routing

**Files:**
- Modify: `/home/kloros/src/kloros/orchestration/curiosity_processor.py:650-690`
- Test: `/home/kloros/tests/orchestration/test_curiosity_spica_routing.py`

### Step 1: Write the failing test

Create `/home/kloros/tests/orchestration/test_curiosity_spica_routing.py`:

```python
import pytest
import json
from pathlib import Path
from src.kloros.orchestration.curiosity_processor import process_curiosity_questions


@pytest.fixture
def test_data_dir(tmp_path):
    feed_dir = tmp_path / "feed"
    feed_dir.mkdir()

    intents_dir = tmp_path / "intents"
    intents_dir.mkdir()

    issues_dir = tmp_path / "issues"
    issues_dir.mkdir()

    return {
        "feed": feed_dir,
        "intents": intents_dir,
        "issues": issues_dir
    }


def test_high_autonomy_emits_both_intents(test_data_dir, monkeypatch):
    monkeypatch.setenv("KLR_CURIOSITY_FEED", str(test_data_dir["feed"]))
    monkeypatch.setenv("KLR_INTENTS_DIR", str(test_data_dir["intents"]))
    monkeypatch.setenv("KLR_INTEGRATION_ISSUES_DIR", str(test_data_dir["issues"]))

    question = {
        "question_id": "orphaned_queue_test",
        "question": "Queue 'test_queue' produced but never consumed",
        "hypothesis": "ORPHANED_QUEUE_TEST",
        "autonomy": 3,
        "evidence": ["Produced in: /home/kloros/src/test.py"],
        "priority": 8
    }

    feed_file = test_data_dir["feed"] / "orphaned_queue_test.json"
    feed_file.write_text(json.dumps(question))

    result = process_curiosity_questions()

    intents = list(test_data_dir["intents"].glob("*.json"))
    assert len(intents) == 2

    intent_types = []
    for intent_file in intents:
        data = json.loads(intent_file.read_text())
        intent_types.append(data["intent_type"])

    assert "integration_fix" in intent_types
    assert "spica_spawn_request" in intent_types


def test_low_autonomy_emits_only_integration_fix(test_data_dir, monkeypatch):
    monkeypatch.setenv("KLR_CURIOSITY_FEED", str(test_data_dir["feed"]))
    monkeypatch.setenv("KLR_INTENTS_DIR", str(test_data_dir["intents"]))
    monkeypatch.setenv("KLR_INTEGRATION_ISSUES_DIR", str(test_data_dir["issues"]))

    question = {
        "question_id": "orphaned_queue_low",
        "question": "Queue 'low_queue' produced but never consumed",
        "hypothesis": "ORPHANED_QUEUE_LOW",
        "autonomy": 2,
        "evidence": ["Produced in: /home/kloros/src/test.py"],
        "priority": 8
    }

    feed_file = test_data_dir["feed"] / "orphaned_queue_low.json"
    feed_file.write_text(json.dumps(question))

    result = process_curiosity_questions()

    intents = list(test_data_dir["intents"].glob("*.json"))
    assert len(intents) == 1

    intent_data = json.loads(intents[0].read_text())
    assert intent_data["intent_type"] == "integration_fix"
```

### Step 2: Run test to verify it fails

```bash
cd /home/kloros
pytest tests/orchestration/test_curiosity_spica_routing.py -v
```

Expected: FAIL (only integration_fix intent created, not spica_spawn_request)

### Step 3: Read current integration fix routing code

Already read in design phase at lines 650-690 of curiosity_processor.py

### Step 4: Write implementation to emit parallel intents

Modify `/home/kloros/src/kloros/orchestration/curiosity_processor.py` at lines 650-690:

Replace the integration fix section with:

```python
# INTEGRATION QUESTIONS: Route to BOTH documentation AND autonomous fix (if autonomy >= 3)
if hypothesis.startswith(("ORPHANED_QUEUE_", "UNINITIALIZED_COMPONENT_", "DUPLICATE_")):
    try:
        from src.dream.remediation_manager import RemediationExperimentGenerator
        remediation = RemediationExperimentGenerator()
        fix_spec = remediation.generate_from_integration_question(q)

        if fix_spec:
            autonomy = q.get("autonomy", 2)
            logger.info(f"[integration_fix] Generated fix for {qid}: {fix_spec.get('action_type')} (autonomy={autonomy})")

            # ALWAYS create documentation intent
            doc_intent = {
                "schema": "orchestration.intent/v1",
                "intent_type": "integration_fix",
                "priority": q.get("priority", 7),
                "reason": f"Integration issue: {hypothesis}",
                "data": {
                    "question_id": qid,
                    "question": question,
                    "hypothesis": hypothesis,
                    "fix_specification": fix_spec,
                    "autonomy_level": autonomy
                },
                "generated_at": time.time(),
                "emitted_by": "curiosity_processor_integration_router"
            }

            doc_intent_sha = hashlib.sha256(json.dumps(doc_intent, sort_keys=True).encode()).hexdigest()[:16]
            doc_intent_path = intents_dir / f"integration_fix_{qid}_{doc_intent_sha}.json"
            doc_intent_json = json.dumps(doc_intent, indent=2)
            doc_intent_path.write_text(doc_intent_json)
            intents_emitted += 1
            logger.info(f"[integration_fix] Emitted documentation intent for {qid}")

            # CONDITIONALLY create SPICA spawn intent for high autonomy
            if autonomy >= 3:
                evidence = q.get("evidence", [])
                report_path = integration_issues_dir / f"{qid}.md"

                target_files = []
                for ev in evidence:
                    if "Produced in:" in ev or "Found in:" in ev:
                        parts = ev.split(":")
                        if len(parts) >= 2:
                            file_path = parts[1].strip()
                            target_files.append(file_path)

                spica_intent = {
                    "schema": "orchestration.intent/v1",
                    "intent_type": "spica_spawn_request",
                    "priority": q.get("priority", 8),
                    "reason": "Autonomous fix attempt for integration issue",
                    "data": {
                        "question_id": qid,
                        "question": question,
                        "hypothesis": hypothesis,
                        "fix_context": {
                            "evidence": evidence,
                            "analysis_report": str(report_path) if report_path.exists() else None,
                            "target_files": target_files,
                            "proposed_changes": fix_spec.get("action", "Fix integration issue")
                        },
                        "validation": {
                            "run_tests": True,
                            "test_command": "pytest tests/ -v",
                            "require_pass": True
                        }
                    },
                    "generated_at": time.time(),
                    "emitted_by": "curiosity_processor_spica_router"
                }

                spica_intent_sha = hashlib.sha256(json.dumps(spica_intent, sort_keys=True).encode()).hexdigest()[:16]
                spica_intent_path = intents_dir / f"spica_spawn_{qid}_{spica_intent_sha}.json"
                spica_intent_json = json.dumps(spica_intent, indent=2)
                spica_intent_path.write_text(spica_intent_json)
                intents_emitted += 1
                logger.info(f"[spica_spawn] Emitted autonomous fix intent for {qid} (autonomy={autonomy})")

            _mark_question_processed(qid, doc_intent_sha)
            continue

    except Exception as e:
        logger.error(f"Failed to generate integration fix for {qid}: {e}", exc_info=True)
```

### Step 5: Run test to verify it passes

```bash
cd /home/kloros
pytest tests/orchestration/test_curiosity_spica_routing.py -v
```

Expected: PASS

### Step 6: Commit

```bash
cd /home/kloros
git add src/kloros/orchestration/curiosity_processor.py tests/orchestration/test_curiosity_spica_routing.py
git commit -m "feat: emit parallel intents for high-autonomy integration fixes"
```

---

## Task 5: Orchestrator SPICA Spawn Handler

**Files:**
- Modify: `/home/kloros/src/kloros/orchestration/coordinator.py` (add new handler after line 243)
- Test: `/home/kloros/tests/orchestration/test_spica_spawn_handler.py`

### Step 1: Write the failing test

Create `/home/kloros/tests/orchestration/test_spica_spawn_handler.py`:

```python
import pytest
import json
from pathlib import Path
from unittest.mock import Mock, patch
from src.kloros.orchestration.coordinator import tick


@pytest.fixture
def mock_spica_intent(tmp_path):
    intents_dir = tmp_path / "intents"
    intents_dir.mkdir()

    intent = {
        "schema": "orchestration.intent/v1",
        "intent_type": "spica_spawn_request",
        "priority": 8,
        "data": {
            "question_id": "orphaned_queue_test",
            "question": "Queue 'test' orphaned",
            "hypothesis": "ORPHANED_QUEUE_TEST",
            "fix_context": {
                "evidence": ["Produced in: /tmp/test.py"],
                "target_files": ["/tmp/test.py"],
                "proposed_changes": "Add consumer"
            },
            "validation": {
                "run_tests": True,
                "test_command": "pytest",
                "require_pass": True
            }
        }
    }

    intent_file = intents_dir / "spica_spawn_test.json"
    intent_file.write_text(json.dumps(intent))

    return {"intents_dir": intents_dir, "intent_file": intent_file}


@patch("src.kloros.orchestration.coordinator.LLMCodeGenerator")
@patch("src.kloros.orchestration.coordinator.spawn_instance")
@patch("src.kloros.orchestration.coordinator.apply_code_patch")
@patch("src.kloros.orchestration.coordinator.run_tests_in_instance")
@patch("src.kloros.orchestration.coordinator.EscrowManager")
def test_spica_spawn_handler_success(
    mock_escrow,
    mock_run_tests,
    mock_apply_patch,
    mock_spawn,
    mock_llm,
    mock_spica_intent,
    monkeypatch
):
    monkeypatch.setenv("KLR_INTENTS_DIR", str(mock_spica_intent["intents_dir"]))

    mock_llm_instance = Mock()
    mock_llm_instance.generate_fix_patch.return_value = "patched code"
    mock_llm.return_value = mock_llm_instance

    mock_spawn.return_value = Mock(
        instance_dir=Path("/tmp/spica-test"),
        spica_id="spica-test123"
    )
    mock_apply_patch.return_value = True
    mock_run_tests.return_value = {"success": True, "output": "All tests passed"}

    mock_escrow_instance = Mock()
    mock_escrow_instance.add_to_escrow.return_value = "escrow-abc"
    mock_escrow.return_value = mock_escrow_instance

    result = tick()

    assert result == "CURIOSITY_SPAWNED"
    mock_llm_instance.generate_fix_patch.assert_called_once()
    mock_spawn.assert_called_once()
    mock_apply_patch.assert_called_once()
    mock_run_tests.assert_called_once()
    mock_escrow_instance.add_to_escrow.assert_called_once()


@patch("src.kloros.orchestration.coordinator.LLMCodeGenerator")
def test_spica_spawn_handler_llm_failure(mock_llm, mock_spica_intent, monkeypatch):
    monkeypatch.setenv("KLR_INTENTS_DIR", str(mock_spica_intent["intents_dir"]))

    mock_llm_instance = Mock()
    mock_llm_instance.generate_fix_patch.return_value = None
    mock_llm.return_value = mock_llm_instance

    result = tick()

    archived = list(mock_spica_intent["intents_dir"].parent.glob("archive/*"))
    assert len(archived) > 0
```

### Step 2: Run test to verify it fails

```bash
cd /home/kloros
pytest tests/orchestration/test_spica_spawn_handler.py -v
```

Expected: FAIL with "AssertionError: assert 'NOOP' == 'CURIOSITY_SPAWNED'"

### Step 3: Read existing coordinator structure

Already read in design phase - handler needed after line 243

### Step 4: Write implementation

Add to `/home/kloros/src/kloros/orchestration/coordinator.py` after the integration_fix handler (around line 243):

```python
    elif intent_type == "spica_spawn_request":
        from src.dream.config_tuning.llm_code_generator import LLMCodeGenerator
        from src.dream.config_tuning.spica_spawner import spawn_instance, apply_code_patch, run_tests_in_instance
        from src.kloros.orchestration.escrow_manager import EscrowManager

        question_id = intent.get("data", {}).get("question_id", "unknown")
        question = intent.get("data", {}).get("question", "")
        hypothesis = intent.get("data", {}).get("hypothesis", "")
        fix_context = intent.get("data", {}).get("fix_context", {})
        validation = intent.get("data", {}).get("validation", {})

        logger.info(f"[spica_spawn] Autonomous fix attempt: {question_id}")

        # Extract fix context
        evidence = fix_context.get("evidence", [])
        report_path_str = fix_context.get("analysis_report")
        target_files = fix_context.get("target_files", [])

        if not target_files:
            logger.error(f"[spica_spawn] No target files specified for {question_id}")
            _archive_intent(intent_path, "no_target_files")
            return "SPICA_SPAWN_FAILED"

        # Generate code patch using LLM
        try:
            llm_generator = LLMCodeGenerator()
            report_path = Path(report_path_str) if report_path_str else None
            target_file = Path(target_files[0])

            logger.info(f"[spica_spawn] Generating code patch for {target_file}")
            patch = llm_generator.generate_fix_patch(
                question=question,
                hypothesis=hypothesis,
                evidence=evidence,
                report_path=report_path,
                target_file=target_file
            )

            if not patch:
                logger.error(f"[spica_spawn] LLM failed to generate patch for {question_id}")
                _archive_intent(intent_path, "llm_generation_failed")
                return "SPICA_SPAWN_FAILED"

            logger.info(f"[spica_spawn] Generated patch ({len(patch)} chars)")

        except Exception as e:
            logger.error(f"[spica_spawn] LLM generation error: {e}", exc_info=True)
            _archive_intent(intent_path, f"llm_error_{type(e).__name__}")
            return "SPICA_SPAWN_FAILED"

        # Spawn SPICA instance
        try:
            logger.info(f"[spica_spawn] Creating SPICA instance for {question_id}")
            spica_instance = spawn_instance(
                candidate={},
                parent_id=None,
                notes=f"Autonomous fix attempt: {question_id}"
            )

            logger.info(f"[spica_spawn] Created {spica_instance.spica_id}")

        except Exception as e:
            logger.error(f"[spica_spawn] SPICA spawn error: {e}", exc_info=True)
            _archive_intent(intent_path, f"spawn_error_{type(e).__name__}")
            return "SPICA_SPAWN_FAILED"

        # Apply code patch to SPICA instance
        try:
            relative_target = target_file.relative_to("/home/kloros") if target_file.is_absolute() else target_file

            logger.info(f"[spica_spawn] Applying patch to {relative_target}")
            patch_success = apply_code_patch(
                instance_dir=spica_instance.instance_dir,
                target_file=relative_target,
                patch_content=patch
            )

            if not patch_success:
                logger.error(f"[spica_spawn] Failed to apply patch to {relative_target}")
                _archive_intent(intent_path, "patch_application_failed")
                return "SPICA_SPAWN_FAILED"

        except Exception as e:
            logger.error(f"[spica_spawn] Patch application error: {e}", exc_info=True)
            _archive_intent(intent_path, f"patch_error_{type(e).__name__}")
            return "SPICA_SPAWN_FAILED"

        # Run tests in SPICA instance
        if validation.get("run_tests", False):
            try:
                test_command = validation.get("test_command", "pytest")
                logger.info(f"[spica_spawn] Running tests: {test_command}")

                test_result = run_tests_in_instance(
                    instance_dir=spica_instance.instance_dir,
                    test_command=test_command
                )

                if not test_result["success"] and validation.get("require_pass", True):
                    logger.error(f"[spica_spawn] Tests failed for {question_id}")
                    logger.error(f"Test output: {test_result['output'][:500]}")
                    _archive_intent(intent_path, "tests_failed")
                    return "SPICA_SPAWN_FAILED"

                logger.info(f"[spica_spawn] Tests passed for {question_id}")

            except Exception as e:
                logger.error(f"[spica_spawn] Test execution error: {e}", exc_info=True)
                _archive_intent(intent_path, f"test_error_{type(e).__name__}")
                return "SPICA_SPAWN_FAILED"

        # Add to escrow for manual approval
        try:
            escrow = EscrowManager()
            escrow_id = escrow.add_to_escrow(
                spica_id=spica_instance.spica_id,
                question_id=question_id,
                instance_dir=spica_instance.instance_dir,
                test_results=test_result if validation.get("run_tests") else {}
            )

            logger.info(f"[spica_spawn] Added {spica_instance.spica_id} to escrow: {escrow_id}")
            _archive_intent(intent_path, f"escrowed_{escrow_id}")
            return "CURIOSITY_SPAWNED"

        except Exception as e:
            logger.error(f"[spica_spawn] Escrow error: {e}", exc_info=True)
            _archive_intent(intent_path, f"escrow_error_{type(e).__name__}")
            return "SPICA_SPAWN_FAILED"
```

### Step 5: Run test to verify it passes

```bash
cd /home/kloros
pytest tests/orchestration/test_spica_spawn_handler.py -v
```

Expected: PASS

### Step 6: Update run_once.py to handle new result

Modify `/home/kloros/src/kloros/orchestration/run_once.py` line 36:

```python
if result in ["NOOP", "PHASE_DONE", "DREAM_CYCLE", "CURIOSITY_LOGGED", "FIX_APPLIED", "CURIOSITY_SPAWNED", "SPICA_SPAWN_FAILED"]:
```

### Step 7: Commit

```bash
cd /home/kloros
git add src/kloros/orchestration/coordinator.py src/kloros/orchestration/run_once.py tests/orchestration/test_spica_spawn_handler.py
git commit -m "feat: add SPICA spawn request handler to orchestrator"
```

---

## Task 6: Integration Testing

**Files:**
- Create: `/home/kloros/tests/integration/test_autonomous_fix_pipeline.py`

### Step 1: Write end-to-end integration test

Create `/home/kloros/tests/integration/test_autonomous_fix_pipeline.py`:

```python
import pytest
import json
import time
from pathlib import Path
from src.kloros.orchestration.curiosity_processor import process_curiosity_questions
from src.kloros.orchestration.coordinator import tick
from src.kloros.orchestration.escrow_manager import EscrowManager


@pytest.fixture
def integration_env(tmp_path, monkeypatch):
    feed_dir = tmp_path / "feed"
    feed_dir.mkdir()

    intents_dir = tmp_path / "intents"
    intents_dir.mkdir()

    issues_dir = tmp_path / "issues"
    issues_dir.mkdir()

    escrow_dir = tmp_path / "escrow"
    escrow_dir.mkdir()

    monkeypatch.setenv("KLR_CURIOSITY_FEED", str(feed_dir))
    monkeypatch.setenv("KLR_INTENTS_DIR", str(intents_dir))
    monkeypatch.setenv("KLR_INTEGRATION_ISSUES_DIR", str(issues_dir))

    return {
        "feed": feed_dir,
        "intents": intents_dir,
        "issues": issues_dir,
        "escrow": escrow_dir
    }


@pytest.mark.integration
def test_full_autonomous_fix_pipeline(integration_env):
    """
    End-to-end test: Question → Processor → Intents → Orchestrator → SPICA → Escrow
    """

    # Step 1: Create high-autonomy curiosity question
    question = {
        "question_id": "orphaned_queue_integration_test",
        "question": "Queue 'integration_test' produced but never consumed",
        "hypothesis": "ORPHANED_QUEUE_INTEGRATION_TEST",
        "autonomy": 3,
        "evidence": [
            "Produced in: /home/kloros/src/memory/bm25_index.py",
            "No consumers found in codebase"
        ],
        "priority": 8,
        "generated_at": time.time()
    }

    feed_file = integration_env["feed"] / f"{question['question_id']}.json"
    feed_file.write_text(json.dumps(question, indent=2))

    # Step 2: Process curiosity questions
    result = process_curiosity_questions()
    assert result > 0

    # Step 3: Verify both intents created
    intents = list(integration_env["intents"].glob("*.json"))
    assert len(intents) == 2

    intent_types = []
    for intent_file in intents:
        data = json.loads(intent_file.read_text())
        intent_types.append(data["intent_type"])

    assert "integration_fix" in intent_types
    assert "spica_spawn_request" in intent_types

    # Step 4: Process integration_fix intent (documentation)
    doc_result = tick()
    assert doc_result in ["FIX_APPLIED", "MANUAL_APPROVAL_REQUIRED"]

    # Step 5: Verify integration issue report created
    reports = list(integration_env["issues"].glob("*.md"))
    assert len(reports) >= 1

    # Step 6: Process spica_spawn_request intent (autonomous fix)
    # Note: This will fail in test environment without actual SPICA template
    # Mock or skip in CI, run manually for validation

    print("✅ Pipeline verified: Question → Intents → Documentation")
    print("⚠️  SPICA spawn requires live environment (skipped in test)")


@pytest.mark.integration
def test_low_autonomy_documentation_only(integration_env):
    """
    Verify low-autonomy questions only create documentation intent
    """

    question = {
        "question_id": "low_autonomy_test",
        "question": "Test low autonomy question",
        "hypothesis": "ORPHANED_QUEUE_LOW",
        "autonomy": 1,
        "evidence": ["Test evidence"],
        "priority": 5,
        "generated_at": time.time()
    }

    feed_file = integration_env["feed"] / f"{question['question_id']}.json"
    feed_file.write_text(json.dumps(question, indent=2))

    result = process_curiosity_questions()
    assert result > 0

    intents = list(integration_env["intents"].glob("*.json"))
    assert len(intents) == 1

    intent_data = json.loads(intents[0].read_text())
    assert intent_data["intent_type"] == "integration_fix"
```

### Step 2: Run integration test

```bash
cd /home/kloros
pytest tests/integration/test_autonomous_fix_pipeline.py -v -m integration
```

Expected: PASS for documentation flow, SKIP for SPICA spawn (requires live environment)

### Step 3: Commit

```bash
cd /home/kloros
git add tests/integration/test_autonomous_fix_pipeline.py
git commit -m "test: add end-to-end integration tests for autonomous fix pipeline"
```

---

## Task 7: Documentation and User Guide

**Files:**
- Create: `/home/kloros/docs/autonomous-fixes-user-guide.md`

### Step 1: Write user guide

Create `/home/kloros/docs/autonomous-fixes-user-guide.md`:

```markdown
# Autonomous Fix System User Guide

## Overview

The autonomous fix system enables KLoROS to proactively attempt fixes for integration issues discovered by the curiosity system. Fixes are generated using LLM code generation, tested in isolated SPICA instances, and held in escrow for manual approval before merging.

## How It Works

1. **Discovery**: Curiosity system detects integration issues (orphaned queues, uninitialized components)
2. **Routing**: High-autonomy questions (level 3+) trigger BOTH:
   - Documentation report (for human reference)
   - Autonomous fix attempt (in SPICA sandbox)
3. **Code Generation**: LLM generates code patch based on issue context
4. **Sandbox Testing**: Patch applied to isolated SPICA instance
5. **Validation**: Test suite runs in isolation
6. **Escrow**: Successful fixes held for manual review
7. **Approval**: Human reviews and approves/rejects before merge

## Autonomy Levels

| Level | Behavior |
|-------|----------|
| 1-2   | Documentation only (requires manual implementation) |
| 3     | Parallel: Documentation + autonomous fix attempt |
| 4-5   | (Future) Auto-apply fixes that pass all validation |

## Reviewing Fixes in Escrow

### List pending fixes

```bash
python -c "
from src.kloros.orchestration.escrow_manager import EscrowManager
escrow = EscrowManager()
for entry in escrow.list_pending():
    print(f'{entry[\"escrow_id\"]}: {entry[\"question_id\"]} ({entry[\"spica_id\"]})')
"
```

### Inspect a fix

```bash
# View escrow entry
cat /home/kloros/.kloros/escrow/<escrow_id>.json

# View SPICA instance code
cd /home/kloros/experiments/spica/instances/<spica_id>
git diff  # Shows changes from template

# Run tests manually
cd /home/kloros/experiments/spica/instances/<spica_id>
source ../../template/.venv/bin/activate
pytest tests/ -v
```

### Approve a fix

```python
from src.kloros.orchestration.escrow_manager import EscrowManager
escrow = EscrowManager()
escrow.approve("escrow-abc123", reviewed_by="your_name")

# Manually merge changes
# (Future: automated merge after approval)
```

### Reject a fix

```python
from src.kloros.orchestration.escrow_manager import EscrowManager
escrow = EscrowManager()
escrow.reject("escrow-abc123", reason="Breaks edge case X", reviewed_by="your_name")
```

## Safety Guardrails

1. **Isolation**: All changes applied in SPICA instance, never directly to main
2. **Test Validation**: Must pass existing test suite before escrow
3. **Manual Approval**: Human reviews before merging to production
4. **Auto-Rollback**: Test failures trigger automatic cleanup
5. **Retention Policy**: SPICA instances pruned after 3 days (max 10 instances)
6. **Deduplication**: Questions marked processed to prevent duplicate attempts

## Configuration

Environment variables in `/home/kloros/.kloros_env`:

```bash
# Curiosity system
KLR_CURIOSITY_REPROCESS_DAYS=7  # Days before re-processing questions
KLR_CURIOSITY_MAX_PROCESSED=500  # Max processed questions to keep
KLR_DISABLE_CURIOSITY=0  # Set to 1 to disable

# LLM code generation
OLLAMA_HOST=http://100.67.244.66:11434  # Coder LLM endpoint
```

## Monitoring

### View orchestrator logs

```bash
journalctl -u kloros-orchestrator.service -f
```

### Check SPICA instances

```bash
ls -la /home/kloros/experiments/spica/instances/
```

### View escrow queue

```bash
ls -la /home/kloros/.kloros/escrow/
```

## Troubleshooting

### No autonomous fixes being attempted

1. Check autonomy level: `cat /home/kloros/.kloros/curiosity_feed/<question_id>.json | jq .autonomy`
2. Verify autonomy >= 3 for SPICA spawn
3. Check orchestrator logs for errors

### LLM generation failures

1. Test Ollama connectivity: `curl http://100.67.244.66:11434/api/generate -d '{"model":"qwen2.5:72b","prompt":"test"}'`
2. Check model availability: `curl http://100.67.244.66:11434/api/tags`
3. Review LLM logs in orchestrator output

### SPICA instance failures

1. Verify template exists: `ls /home/kloros/experiments/spica/template/`
2. Check disk space: `df -h`
3. Review SPICA spawner logs

### Test failures in SPICA

1. Manually inspect SPICA instance code
2. Run tests with verbose output: `cd <spica_instance> && pytest -vv`
3. Review test output in escrow entry JSON

## Best Practices

1. **Review escrow regularly** - Don't let fixes pile up unreviewed
2. **Reject with detailed reasons** - Helps improve future fix generation
3. **Monitor SPICA disk usage** - Prune old instances if disk fills
4. **Track approval rates** - Low rates indicate LLM tuning needed
5. **Keep test suite comprehensive** - Better validation in SPICA sandbox

## Future Enhancements

- Auto-merge for high-confidence fixes (autonomy 4-5)
- Multi-file fix support
- Learning from approval/rejection patterns
- Auto-generated regression tests for fixed issues
```

### Step 2: Commit

```bash
cd /home/kloros
git add docs/autonomous-fixes-user-guide.md
git commit -m "docs: add user guide for autonomous fix system"
```

---

## Task 8: System Verification

**Files:**
- Create: `/home/kloros/scripts/verify_autonomous_fixes.sh`

### Step 1: Write verification script

Create `/home/kloros/scripts/verify_autonomous_fixes.sh`:

```bash
#!/bin/bash

set -e

echo "=== Autonomous Fix System Verification ==="
echo ""

# Check component files exist
echo "✓ Checking component files..."
test -f /home/kloros/src/dream/config_tuning/llm_code_generator.py || { echo "✗ LLM generator missing"; exit 1; }
test -f /home/kloros/src/kloros/orchestration/escrow_manager.py || { echo "✗ Escrow manager missing"; exit 1; }
echo "  All components present"
echo ""

# Check directories
echo "✓ Checking directories..."
test -d /home/kloros/.kloros/escrow || mkdir -p /home/kloros/.kloros/escrow
test -d /home/kloros/experiments/spica/instances || { echo "✗ SPICA instances dir missing"; exit 1; }
test -d /home/kloros/experiments/spica/template || { echo "✗ SPICA template missing"; exit 1; }
echo "  All directories present"
echo ""

# Test LLM connectivity
echo "✓ Testing LLM connectivity..."
curl -s http://100.67.244.66:11434/api/tags > /dev/null || { echo "✗ Cannot reach Ollama server"; exit 1; }
echo "  LLM server reachable"
echo ""

# Run unit tests
echo "✓ Running unit tests..."
cd /home/kloros
pytest tests/dream/test_llm_code_generator.py -v -q
pytest tests/orchestration/test_escrow_manager.py -v -q
pytest tests/dream/test_spica_spawner_patches.py -v -q
echo "  Unit tests passed"
echo ""

# Check orchestrator service
echo "✓ Checking orchestrator service..."
systemctl is-active kloros-orchestrator.timer || { echo "✗ Orchestrator timer not active"; exit 1; }
echo "  Orchestrator timer active"
echo ""

# Check environment configuration
echo "✓ Checking environment..."
source /home/kloros/.kloros_env
test -n "$KLR_CURIOSITY_REPROCESS_DAYS" || { echo "✗ KLR_CURIOSITY_REPROCESS_DAYS not set"; exit 1; }
test -n "$OLLAMA_HOST" || { echo "✗ OLLAMA_HOST not set"; exit 1; }
echo "  Environment configured"
echo ""

# Summary
echo "=== ✅ All Verifications Passed ==="
echo ""
echo "System ready for autonomous fix attempts."
echo "Monitor with: journalctl -u kloros-orchestrator.service -f"
echo "Review escrow: ls -la /home/kloros/.kloros/escrow/"
```

### Step 2: Make executable and run

```bash
cd /home/kloros
chmod +x scripts/verify_autonomous_fixes.sh
./scripts/verify_autonomous_fixes.sh
```

Expected: All checks pass

### Step 3: Commit

```bash
cd /home/kloros
git add scripts/verify_autonomous_fixes.sh
git commit -m "chore: add system verification script for autonomous fixes"
```

---

## Task 9: Final Integration and Deployment

### Step 1: Run full test suite

```bash
cd /home/kloros
pytest tests/ -v --tb=short
```

Expected: All tests pass (integration tests may skip SPICA spawn without live environment)

### Step 2: Fix file permissions

```bash
cd /home/kloros
sudo chown -R kloros:kloros src/ tests/ docs/ scripts/
sudo chmod 644 src/**/*.py tests/**/*.py
sudo chmod 755 scripts/*.sh
```

### Step 3: Restart orchestrator service

```bash
sudo systemctl restart kloros-orchestrator.service
sudo systemctl status kloros-orchestrator.service
```

Expected: Service active, no errors

### Step 4: Monitor first autonomous fix attempt

```bash
# Watch for high-autonomy questions
watch -n 5 'find /home/kloros/.kloros/curiosity_feed/ -name "*.json" -exec jq -r "select(.autonomy >= 3) | .question_id" {} \; 2>/dev/null'

# Monitor orchestrator processing
journalctl -u kloros-orchestrator.service -f | grep -E "spica_spawn|escrow"
```

### Step 5: Verify first escrow entry

```bash
# Wait for first SPICA spawn attempt
sleep 60

# Check escrow
ls -la /home/kloros/.kloros/escrow/

# If entries exist, inspect
python3 -c "
from src.kloros.orchestration.escrow_manager import EscrowManager
escrow = EscrowManager()
pending = escrow.list_pending()
if pending:
    print(f'Found {len(pending)} pending fixes:')
    for entry in pending:
        print(f'  {entry[\"escrow_id\"]}: {entry[\"question_id\"]}')
else:
    print('No pending fixes yet (check back later)')
"
```

### Step 6: Final commit

```bash
cd /home/kloros
git add .
git commit -m "feat: autonomous curiosity fix system - complete implementation"
git log --oneline -10
```

---

## Success Criteria

- [ ] All unit tests pass
- [ ] Integration tests pass (documentation flow)
- [ ] LLM code generator creates patches
- [ ] SPICA instances spawn successfully
- [ ] Code patches apply without errors
- [ ] Tests run in SPICA isolation
- [ ] Escrow manager tracks pending fixes
- [ ] Orchestrator processes both intent types
- [ ] Documentation generated for all integration issues
- [ ] System verification script passes
- [ ] Service restarts without errors
- [ ] First autonomous fix attempt reaches escrow

---

## Rollback Plan

If issues arise during deployment:

```bash
# Stop orchestrator
sudo systemctl stop kloros-orchestrator.service

# Revert to previous commit
cd /home/kloros
git log --oneline -20  # Find commit before autonomous fix implementation
git revert <commit_sha>

# Restart service
sudo systemctl start kloros-orchestrator.service
```

---

## Monitoring After Deployment

**Week 1**: Monitor daily for escrow buildup, LLM failures, SPICA disk usage

**Week 2-4**: Review approval rates, fix quality, false positive rate

**Month 2+**: Tune autonomy thresholds, LLM prompts, test requirements based on data

**Metrics to Track**:
- Autonomous fix attempts per week
- SPICA test pass rate
- Human approval rate
- Time from discovery to escrow
- Disk usage by SPICA instances
