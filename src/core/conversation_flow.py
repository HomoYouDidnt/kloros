# src/core/conversation_flow.py
from __future__ import annotations
from dataclasses import dataclass, field
from collections import deque
from typing import Deque, Dict, List, Optional, Tuple
import re
import time
import uuid

PRONOUNS = {"it", "this", "that", "they", "them", "those", "these", "he", "she", "him", "her"}
FOLLOWUP_HINTS = {
    "also", "and", "what about", "how about", "same", "yeah", "yep", "yup",
    "ok but", "but", "btw", "btw,", "btw.", "btw -", "btw—", "btw…",
    "btw:", "btw;", "btw)", "btw]"
}

@dataclass
class Turn:
    role: str  # "user" | "assistant" | "system"
    text: str
    ts: float = field(default_factory=time.time)

@dataclass
class TopicSummary:
    """Compact summary that grows as the thread evolves."""
    title: str
    bullet_points: List[str] = field(default_factory=list)
    last_updated: float = field(default_factory=time.time)

    def add_fact(self, fact: str, max_len: int = 240) -> None:
        fact = fact.strip()
        if not fact:
            return
        # Avoid spammy duplicates
        if fact.lower() in (bp.lower() for bp in self.bullet_points):
            return
        self.bullet_points.append(fact[:max_len])
        self.last_updated = time.time()

    def to_text(self, max_points: int = 10) -> str:
        pts = self.bullet_points[-max_points:]
        if not pts:
            return self.title
        return f"{self.title}\n- " + "\n- ".join(pts)

@dataclass
class ConversationalState:
    """Short-term working memory for a single live thread."""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    turns: Deque[Turn] = field(default_factory=lambda: deque(maxlen=16))
    entities: Dict[str, str] = field(default_factory=dict)     # e.g. {"gpu": "RTX 3080", "project": "KLoROS"}
    slots: Dict[str, str] = field(default_factory=dict)        # task-specific slots: {"output_device": "iec958-stereo"}
    topic_summary: TopicSummary = field(default_factory=lambda: TopicSummary("Thread summary"))
    # Idle cutoff: if silent past this, start a fresh thread
    idle_cutoff_s: int = 180

    def push(self, role: str, text: str) -> None:
        self.turns.append(Turn(role=role, text=text))
    
    def last_user_utterance(self) -> Optional[str]:
        for t in reversed(self.turns):
            if t.role == "user":
                return t.text
        return None

    def is_idle(self, now: Optional[float] = None) -> bool:
        now = now or time.time()
        if not self.turns:
            return False
        return (now - self.turns[-1].ts) > self.idle_cutoff_s

    def extract_entities(self, text: str) -> None:
        """
        Extremely lightweight entity capture:
        - anything like key: value
        - common tech tokens we care about
        """
        # key: value lines
        for m in re.finditer(r"\b([a-zA-Z0-9_\-/]+)\s*:\s*([^\s,;]+)", text):
            k, v = m.group(1).lower(), m.group(2)
            self.entities[k] = v
        
        # Heuristic: remember last mentioned project / device phrases
        tech_keys = ["gpu", "cpu", "project", "router", "modem", "audio", "device", "mic", "output", "input"]
        for k in tech_keys:
            pat = rf"\b{k}\b[:=]?\s*([A-Za-z0-9_\-./]+)"
            m = re.search(pat, text, re.IGNORECASE)
            if m:
                self.entities[k] = m.group(1)

    def resolve_pronouns(self, user_text: str) -> str:
        """If the user uses 'it/this/that/they' etc., rewrite with last known entities."""
        tokens = re.findall(r"\b\w+\b|\S", user_text)
        if not any(tok.lower() in PRONOUNS for tok in tokens):
            return user_text  # nothing to fix

        # Try to fill 'it/this/that' → most salient entity
        # Salience order: slots > entities > last assistant noun-ish token
        preferred = None
        if self.slots:
            # grab last updated slot
            preferred = next(reversed(self.slots.values()))
        if not preferred and self.entities:
            preferred = next(reversed(self.entities.values()))
        if not preferred:
            return user_text  # nothing known

        replaced = []
        for tok in tokens:
            if tok.lower() in {"it", "this", "that"}:
                replaced.append(preferred)
            elif tok.lower() in {"they", "them", "those", "these"}:
                # crude plural → same replacement
                replaced.append(preferred)
            else:
                replaced.append(tok)
        return re.sub(r"\s+", " ", "".join(
            [(" " + t) if re.match(r"\w", t) else t for t in replaced]
        )).strip()

    def maybe_followup(self, text: str) -> bool:
        """Detect if user input is likely continuing the current topic."""
        low = text.strip().lower()
        if not low:
            return False
        if any(h in low for h in FOLLOWUP_HINTS):
            return True
        # If starts with pronoun or coordination, assume follow-up
        if re.match(r"^(and|also|then|but|so|it|this|that|they|ok|yeah|yep)\b", low):
            return True
        # Short fragments like "what about output?" are also follow-ups
        if len(low.split()) <= 6:
            return True
        return False

    def summarize_if_needed(self) -> None:
        """
        Keep a rolling, lossy summary to pass to the LLM,
        so we don't inflate prompt tokens.
        """
        if len(self.turns) < 6:
            return
        # take every 2nd user + assistant pair and extract a brief fact (very naive)
        harvested: List[str] = []
        for t in list(self.turns)[-8:]:
            if t.role == "user":
                u = t.text.strip()
                if len(u) <= 180:
                    harvested.append(f"User: {u}")
            elif t.role == "assistant":
                a = t.text.strip()
                if len(a) <= 180:
                    harvested.append(f"You: {a}")
        if harvested:
            self.topic_summary.add_fact(" / ".join(harvested[-2:]))

    def build_prompt_context(self, system_preamble: str = "") -> str:
        """
        Render a compact context block for your reasoning backend.
        """
        self.summarize_if_needed()
        history = []
        for t in self.turns:
            if t.role == "system":
                continue
            name = "User" if t.role == "user" else "Assistant"
            history.append(f"{name}: {t.text}")
        ent = "; ".join(f"{k}={v}" for k, v in self.entities.items()) or "none"
        slots = "; ".join(f"{k}={v}" for k, v in self.slots.items()) or "none"
        summary = self.topic_summary.to_text()

        pre = system_preamble.strip()
        if pre:
            pre += "\n\n"

        return (
            f"{pre}"
            f"Thread-ID: {self.id}\n"
            f"Known entities: {ent}\n"
            f"Task/slots: {slots}\n"
            f"Summary:\n{summary}\n\n"
            "Recent turns:\n" + "\n".join(history[-12:])
        )

class ConversationFlow:
    """
    Manages live threads. If the user pauses beyond `idle_cutoff_s`,
    a new thread will be started implicitly; otherwise we keep rolling.
    """
    def __init__(self, idle_cutoff_s: int = 180):
        self.current: Optional[ConversationalState] = None
        self.idle_cutoff_s = idle_cutoff_s

    def _fresh(self) -> ConversationalState:
        st = ConversationalState(idle_cutoff_s=self.idle_cutoff_s)
        # Seed system style once per thread
        st.push("system", "Stay concise, practical, and keep troubleshooting grounded in the current session's facts.")
        return st

    def ensure_thread(self) -> ConversationalState:
        if self.current is None:
            self.current = self._fresh()
            return self.current
        if self.current.is_idle():
            self.current = self._fresh()
        return self.current

    def ingest_user(self, raw_text: str) -> Tuple[ConversationalState, str]:
        """
        Called by your turn orchestrator when STT produces final text.
        Returns (state, normalized_text) that should be fed to the reasoner.
        """
        st = self.ensure_thread()
        # Heuristic: if this *looks* like a follow-up, try pronoun resolution
        text = raw_text.strip()
        norm = st.resolve_pronouns(text) if st.maybe_followup(text) else text
        st.push("user", text)
        st.extract_entities(text)
        return st, norm

    def ingest_assistant(self, text: str) -> ConversationalState:
        st = self.ensure_thread()
        st.push("assistant", text)
        st.extract_entities(text)
        return st

    def set_slot(self, key: str, value: str) -> None:
        st = self.ensure_thread()
        st.slots[key] = value

    def context_block(self, preamble: str = "") -> str:
        st = self.ensure_thread()
        return st.build_prompt_context(preamble)
