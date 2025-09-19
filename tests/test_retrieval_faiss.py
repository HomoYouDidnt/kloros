import shutil
import sys
from pathlib import Path
from typing import Any, Dict

import numpy as np
import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

pytest.importorskip('faiss')
pytest.importorskip('sentence_transformers')

from kloROS_accuracy_stack.retrieval import embedder
from scripts.index_build import build_index


class DummyModel:
    def __init__(self, *args, **kwargs) -> None:
        pass

    def encode(self, texts, convert_to_numpy=True, normalize_embeddings=True):
        arr = []
        for text in texts:
            base = float(len(text.split()) + 1)
            arr.append([base, base / 2])
        return np.asarray(arr, dtype=np.float32)


@pytest.fixture()
def fixture_corpus(tmp_path: Path) -> Path:
    corpus = tmp_path / 'corpus'
    corpus.mkdir()
    src = Path('kloROS_accuracy_stack/fixtures/mini/docs')
    for path in src.glob('*.md'):
        shutil.copy(path, corpus / path.name)
    return corpus


def test_build_index_and_retrieve_faiss(monkeypatch: pytest.MonkeyPatch, fixture_corpus: Path, tmp_path: Path) -> None:
    monkeypatch.setattr(
        'sentence_transformers.SentenceTransformer',  # type: ignore[attr-defined]
        lambda *a, **k: DummyModel(),
    )
    index_dir = tmp_path / 'index'
    build_index(fixture_corpus, index_dir, model_name='dummy-model')

    monkeypatch.setattr(embedder, '_get_sentence_transformer', lambda path, name: DummyModel())
    cfg = {
        'retrieval': {
            'provider': 'faiss',
            'top_k': 3,
            'index_path': str(index_dir),
            'model_path': None,
            'embedder': ['dummy-model'],
        }
    }
    trace: Dict[str, Any] = {}
    results = embedder.retrieve('What pipeline does KLoROS use?', cfg, trace)
    assert results
    assert all('id' in doc and 'text' in doc and isinstance(doc['score'], float) for doc in results)
    assert trace['retrieval']['queries'][0]['provider'] == 'faiss'

