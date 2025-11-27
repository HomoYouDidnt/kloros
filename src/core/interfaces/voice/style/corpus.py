"""
Style Corpus Loader

Loads and queries tone-labeled speech samples for voice style guidance.
"""

from __future__ import annotations
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import List, Optional, Dict
import csv
import random


class ToneCategory(Enum):
    DEADPAN = "deadpan"
    SARCASTIC = "sarcastic"
    INQUISITIVE = "inquisitive"
    CHEERFUL = "cheerful"
    THREATENING = "threatening"
    ANNOYED = "annoyed"
    CONTEMPTUOUS = "contemptuous"
    TAUNTING = "taunting"
    DIRECTIVE = "directive"
    ERROR_SYSTEM = "error/system"

    @classmethod
    def from_string(cls, s: str) -> Optional["ToneCategory"]:
        s = s.lower().strip()
        for cat in cls:
            if cat.value == s:
                return cat
        return None


@dataclass
class StyleExample:
    id: str
    text: str
    tone: ToneCategory
    tone_confidence: float
    context: str
    game: str
    section: str
    prev_quote: Optional[str]
    next_quote: Optional[str]
    audio_path: Optional[Path]
    tags: List[str]


class StyleCorpus:
    """
    Corpus of tone-labeled speech samples for style guidance.

    Provides methods to:
    - Query examples by tone category
    - Sample random examples for style enrichment
    - Get contextual examples (with prev/next quotes)
    - Count distribution of tones
    """

    def __init__(self, corpus_path: Optional[Path] = None, audio_dir: Optional[Path] = None):
        self._style_dir = Path(__file__).parent
        self._corpus_path = corpus_path or self._style_dir / "glados_corpus.csv"
        self._audio_dir = audio_dir or self._style_dir / "audio"
        self._examples: List[StyleExample] = []
        self._by_tone: Dict[ToneCategory, List[StyleExample]] = {}
        self._loaded = False

    def load(self) -> "StyleCorpus":
        if self._loaded:
            return self

        if not self._corpus_path.exists():
            raise FileNotFoundError(f"Corpus not found: {self._corpus_path}")

        with open(self._corpus_path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                tone = ToneCategory.from_string(row.get("tone", ""))
                if tone is None:
                    continue

                example = StyleExample(
                    id=row.get("id", ""),
                    text=row.get("text", ""),
                    tone=tone,
                    tone_confidence=float(row.get("tone_confidence", 1.0)),
                    context=row.get("context", ""),
                    game=row.get("game", ""),
                    section=row.get("section", ""),
                    prev_quote=row.get("prev_quote") or None,
                    next_quote=row.get("next_quote") or None,
                    audio_path=self._resolve_audio(row.get("filename")),
                    tags=[t.strip() for t in row.get("tags", "").split(",") if t.strip()],
                )
                self._examples.append(example)

                if tone not in self._by_tone:
                    self._by_tone[tone] = []
                self._by_tone[tone].append(example)

        self._loaded = True
        return self

    def _resolve_audio(self, filename: Optional[str]) -> Optional[Path]:
        if not filename or not self._audio_dir.exists():
            return None
        base = filename.replace(".wav", "").replace("GLaDOS_", "").replace("_", "")
        for ext in [".wav", ".mp3", ".ogg"]:
            for prefix in ["sample", ""]:
                candidates = list(self._audio_dir.glob(f"{prefix}*{ext}"))
                if candidates:
                    return candidates[0]
        return None

    def by_tone(self, tone: ToneCategory, limit: Optional[int] = None) -> List[StyleExample]:
        self.load()
        examples = self._by_tone.get(tone, [])
        if limit:
            return examples[:limit]
        return examples

    def sample(
        self,
        tone: Optional[ToneCategory] = None,
        count: int = 1,
        high_confidence: bool = False,
    ) -> List[StyleExample]:
        self.load()

        if tone:
            pool = self._by_tone.get(tone, [])
        else:
            pool = self._examples

        if high_confidence:
            pool = [e for e in pool if e.tone_confidence >= 0.9]

        if not pool:
            return []

        return random.sample(pool, min(count, len(pool)))

    def distribution(self) -> Dict[ToneCategory, int]:
        self.load()
        return {tone: len(examples) for tone, examples in self._by_tone.items()}

    def search_text(self, query: str, limit: int = 10) -> List[StyleExample]:
        self.load()
        query_lower = query.lower()
        matches = [e for e in self._examples if query_lower in e.text.lower()]
        return matches[:limit]

    def get_sarcasm_examples(self, count: int = 5) -> List[str]:
        examples = self.sample(ToneCategory.SARCASTIC, count, high_confidence=True)
        return [e.text for e in examples]

    def get_deadpan_examples(self, count: int = 5) -> List[str]:
        examples = self.sample(ToneCategory.DEADPAN, count, high_confidence=True)
        return [e.text for e in examples]

    def get_style_prompt_examples(self, tones: Optional[List[ToneCategory]] = None) -> str:
        if tones is None:
            tones = [ToneCategory.DEADPAN, ToneCategory.SARCASTIC, ToneCategory.INQUISITIVE]

        lines = []
        for tone in tones:
            examples = self.sample(tone, 3, high_confidence=True)
            if examples:
                lines.append(f"\n{tone.value.upper()} tone examples:")
                for ex in examples:
                    lines.append(f'  - "{ex.text}"')

        return "\n".join(lines)

    def __len__(self) -> int:
        self.load()
        return len(self._examples)

    def __repr__(self) -> str:
        return f"<StyleCorpus samples={len(self)} tones={len(self._by_tone)}>"
