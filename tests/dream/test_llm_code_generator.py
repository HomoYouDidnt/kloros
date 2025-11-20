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
