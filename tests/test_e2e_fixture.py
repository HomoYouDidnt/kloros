import json
from copy import deepcopy
from pathlib import Path

import yaml

from kloROS_accuracy_stack.pipeline.qa import answer

CFG_PATH = Path("kloROS_accuracy_stack/config/accuracy.yml")
QA_PATH = Path("kloROS_accuracy_stack/fixtures/mini/qa.jsonl")


def test_e2e_fixture_pipeline_returns_answers_or_abstains() -> None:
    base_cfg = yaml.safe_load(CFG_PATH.read_text(encoding="utf-8"))
    records = [json.loads(line) for line in QA_PATH.read_text(encoding="utf-8").splitlines() if line]
    assert records
    for record in records:
        cfg = deepcopy(base_cfg)
        result, trace = answer(record["q"], cfg)
        assert trace.get("retrieval")
        assert trace.get("decode_mode")
        assert trace.get("reranked_full")
        assert (result.get("answer") or result.get("abstained"))
