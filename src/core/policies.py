# src/core/policies.py
from dataclasses import dataclass

@dataclass
class DialoguePolicy:
    """
    Very light policy knobs. You can tune these at runtime via env or UI.
    """
    allow_short_answers: bool = True
    ask_clarifying_when_ambiguous: bool = True
    max_answer_chars: int = 900

    def apply(self, draft: str) -> str:
        text = draft.strip()
        if self.allow_short_answers and len(text) > self.max_answer_chars:
            # naive tightening
            text = text[: self.max_answer_chars].rsplit(". ", 1)[0] + "."
        return text
