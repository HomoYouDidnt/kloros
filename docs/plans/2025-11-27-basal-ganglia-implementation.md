# Basal Ganglia Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a neurobiologically-grounded action selection system with D1/D2 pathway competition, dopamine-based learning, and habit formation.

**Architecture:** Striatum receives context and generates candidates, Direct/Indirect pathways compute competing activations, Globus Pallidus selects winner via competition degree ratio, Substantia Nigra generates dopamine learning signals from outcome prediction errors.

**Tech Stack:** Python 3.11+, numpy, dataclasses, pytest

---

## Phase 1: Core Types and Infrastructure

### Task 1: Create module structure and core types

**Files:**
- Create: `src/cognition/basal_ganglia/__init__.py`
- Create: `src/cognition/basal_ganglia/types.py`
- Test: `src/tests/unit/test_basal_ganglia_types.py`

**Step 1: Create directory structure**

```bash
mkdir -p /home/kloros/src/cognition/basal_ganglia/channels
mkdir -p /home/kloros/src/cognition/basal_ganglia/pathways
mkdir -p /home/kloros/src/cognition/basal_ganglia/dopamine
mkdir -p /home/kloros/src/cognition/basal_ganglia/habits
```

**Step 2: Write the failing test for core types**

```python
# src/tests/unit/test_basal_ganglia_types.py
import numpy as np
import pytest
from src.cognition.basal_ganglia.types import (
    ActionCandidate,
    DopamineSignal,
    SelectionResult,
    Outcome,
    Context,
)


class TestActionCandidate:
    def test_competition_degree_calculation(self):
        candidate = ActionCandidate(
            channel="tool",
            action_id="search",
            context_embedding=np.zeros(384),
            direct_activation=0.8,
            indirect_activation=0.4,
        )
        assert candidate.competition_degree == pytest.approx(2.0)

    def test_competition_degree_avoids_division_by_zero(self):
        candidate = ActionCandidate(
            channel="tool",
            action_id="search",
            context_embedding=np.zeros(384),
            direct_activation=0.5,
            indirect_activation=0.0,
        )
        assert candidate.competition_degree == pytest.approx(50.0)

    def test_default_values(self):
        candidate = ActionCandidate(
            channel="tool",
            action_id="search",
            context_embedding=np.zeros(384),
        )
        assert candidate.direct_activation == 0.0
        assert candidate.indirect_activation == 0.0
        assert candidate.is_novel_context is False


class TestDopamineSignal:
    def test_is_burst(self):
        signal = DopamineSignal(delta=0.5, source="tool:search", timestamp=1000.0)
        assert signal.is_burst is True
        assert signal.is_dip is False

    def test_is_dip(self):
        signal = DopamineSignal(delta=-0.3, source="tool:search", timestamp=1000.0)
        assert signal.is_burst is False
        assert signal.is_dip is True


class TestOutcome:
    def test_reward_computation_success(self):
        outcome = Outcome(success=True, latency_ms=500)
        assert outcome.reward > 0.4

    def test_reward_computation_failure(self):
        outcome = Outcome(success=False, latency_ms=500)
        assert outcome.reward < 0.1

    def test_reward_includes_user_feedback(self):
        outcome_positive = Outcome(success=True, latency_ms=500, user_feedback=1.0)
        outcome_neutral = Outcome(success=True, latency_ms=500, user_feedback=None)
        assert outcome_positive.reward > outcome_neutral.reward
```

**Step 3: Run test to verify it fails**

Run: `cd /home/kloros && python -m pytest src/tests/unit/test_basal_ganglia_types.py -v`
Expected: FAIL with "ModuleNotFoundError: No module named 'src.cognition.basal_ganglia.types'"

**Step 4: Write minimal implementation**

```python
# src/cognition/basal_ganglia/types.py
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional, List, Any
import numpy as np
import time


@dataclass
class Context:
    query: str
    conversation_history: List[dict] = field(default_factory=list)
    user_profile: Optional[dict] = None
    stakes_level: float = 0.5
    novelty_score: float = 0.0
    metadata: dict = field(default_factory=dict)


@dataclass
class ActionCandidate:
    channel: str
    action_id: str
    context_embedding: np.ndarray
    direct_activation: float = 0.0
    indirect_activation: float = 0.0
    is_novel_context: bool = False
    metadata: dict = field(default_factory=dict)

    @property
    def competition_degree(self) -> float:
        return self.direct_activation / max(self.indirect_activation, 0.01)


@dataclass
class DopamineSignal:
    delta: float
    source: str
    timestamp: float
    expected_reward: float = 0.0
    actual_reward: float = 0.0

    @property
    def is_burst(self) -> bool:
        return self.delta > 0

    @property
    def is_dip(self) -> bool:
        return self.delta < 0


@dataclass
class Outcome:
    success: bool
    latency_ms: float = 0.0
    user_feedback: Optional[float] = None
    tokens_used: Optional[int] = None
    error_message: Optional[str] = None

    @property
    def reward(self) -> float:
        r = 0.0
        r += 0.5 if self.success else 0.0
        if self.user_feedback is not None:
            r += self.user_feedback * 0.3
        latency_penalty = min(self.latency_ms / 5000, 0.2)
        r -= latency_penalty
        if self.tokens_used:
            efficiency = 1.0 - min(self.tokens_used / 10000, 1.0)
            r += efficiency * 0.1
        return np.clip(r, -1.0, 1.0)


@dataclass
class SelectionResult:
    selected: ActionCandidate
    runner_up: Optional[ActionCandidate] = None
    competition_margin: float = 0.0
    deliberation_requested: bool = False
    deliberation_reason: str = ""
    selection_method: str = "competition"
```

```python
# src/cognition/basal_ganglia/__init__.py
"""Basal Ganglia - Action selection via D1/D2 pathway competition."""
from .types import (
    ActionCandidate,
    DopamineSignal,
    SelectionResult,
    Outcome,
    Context,
)

__all__ = [
    "ActionCandidate",
    "DopamineSignal",
    "SelectionResult",
    "Outcome",
    "Context",
]
```

**Step 5: Run test to verify it passes**

Run: `cd /home/kloros && python -m pytest src/tests/unit/test_basal_ganglia_types.py -v`
Expected: PASS (all 7 tests)

**Step 6: Commit**

```bash
git add src/cognition/basal_ganglia/ src/tests/unit/test_basal_ganglia_types.py
git commit -m "feat(basal_ganglia): add core types - ActionCandidate, DopamineSignal, Outcome"
```

---

### Task 2: Implement ActionChannel base class

**Files:**
- Create: `src/cognition/basal_ganglia/channels/__init__.py`
- Create: `src/cognition/basal_ganglia/channels/base.py`
- Test: `src/tests/unit/test_basal_ganglia_channels.py`

**Step 1: Write the failing test**

```python
# src/tests/unit/test_basal_ganglia_channels.py
import numpy as np
import pytest
from src.cognition.basal_ganglia.channels.base import ActionChannel
from src.cognition.basal_ganglia.types import Context, ActionCandidate


class MockChannel(ActionChannel):
    @property
    def name(self) -> str:
        return "mock"

    def get_candidates(self, context: Context) -> list[ActionCandidate]:
        return [
            ActionCandidate(
                channel=self.name,
                action_id="action_a",
                context_embedding=np.zeros(384),
            ),
            ActionCandidate(
                channel=self.name,
                action_id="action_b",
                context_embedding=np.zeros(384),
            ),
        ]


class TestActionChannel:
    def test_channel_returns_candidates(self):
        channel = MockChannel()
        context = Context(query="test query")
        candidates = channel.get_candidates(context)
        assert len(candidates) == 2
        assert all(c.channel == "mock" for c in candidates)

    def test_compute_d1_default(self):
        channel = MockChannel()
        embedding = np.random.randn(384)
        candidate = ActionCandidate(
            channel="mock",
            action_id="test",
            context_embedding=embedding,
        )
        d1 = channel.compute_d1(embedding, candidate)
        assert 0.0 <= d1 <= 1.0

    def test_compute_d2_default(self):
        channel = MockChannel()
        embedding = np.random.randn(384)
        candidate = ActionCandidate(
            channel="mock",
            action_id="test",
            context_embedding=embedding,
        )
        d2 = channel.compute_d2(embedding, candidate)
        assert 0.0 <= d2 <= 1.0
```

**Step 2: Run test to verify it fails**

Run: `cd /home/kloros && python -m pytest src/tests/unit/test_basal_ganglia_channels.py -v`
Expected: FAIL with "ModuleNotFoundError"

**Step 3: Write minimal implementation**

```python
# src/cognition/basal_ganglia/channels/base.py
from __future__ import annotations
from abc import ABC, abstractmethod
from typing import List
import numpy as np

from src.cognition.basal_ganglia.types import Context, ActionCandidate


class ActionChannel(ABC):
    """
    Base class for action channels.

    Each channel represents a domain of actions (tools, agents, responses, etc.)
    and provides candidates with D1/D2 activation scores.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Channel identifier."""
        pass

    @abstractmethod
    def get_candidates(self, context: Context) -> List[ActionCandidate]:
        """Generate action candidates for this context."""
        pass

    def compute_d1(self, context_embedding: np.ndarray, candidate: ActionCandidate) -> float:
        """
        Compute Direct pathway (D1) activation.

        Default: cosine similarity between context and candidate embeddings.
        Override for channel-specific logic.
        """
        if np.linalg.norm(context_embedding) == 0 or np.linalg.norm(candidate.context_embedding) == 0:
            return 0.5
        similarity = np.dot(context_embedding, candidate.context_embedding) / (
            np.linalg.norm(context_embedding) * np.linalg.norm(candidate.context_embedding)
        )
        return float(np.clip((similarity + 1) / 2, 0.0, 1.0))

    def compute_d2(self, context_embedding: np.ndarray, candidate: ActionCandidate) -> float:
        """
        Compute Indirect pathway (D2) activation.

        Default: inverse of D1 with baseline.
        Override for channel-specific surround inhibition.
        """
        d1 = self.compute_d1(context_embedding, candidate)
        return float(np.clip(1.0 - d1 + 0.3, 0.1, 1.0))
```

```python
# src/cognition/basal_ganglia/channels/__init__.py
"""Action channels for basal ganglia."""
from .base import ActionChannel

__all__ = ["ActionChannel"]
```

**Step 4: Run test to verify it passes**

Run: `cd /home/kloros && python -m pytest src/tests/unit/test_basal_ganglia_channels.py -v`
Expected: PASS (all 3 tests)

**Step 5: Commit**

```bash
git add src/cognition/basal_ganglia/channels/
git add src/tests/unit/test_basal_ganglia_channels.py
git commit -m "feat(basal_ganglia): add ActionChannel base class with D1/D2 defaults"
```

---

### Task 3: Implement ToolChannel

**Files:**
- Create: `src/cognition/basal_ganglia/channels/tool_channel.py`
- Modify: `src/cognition/basal_ganglia/channels/__init__.py`
- Test: `src/tests/unit/test_tool_channel.py`

**Step 1: Write the failing test**

```python
# src/tests/unit/test_tool_channel.py
import numpy as np
import pytest
from src.cognition.basal_ganglia.channels.tool_channel import ToolChannel
from src.cognition.basal_ganglia.types import Context


class TestToolChannel:
    def test_channel_name(self):
        channel = ToolChannel()
        assert channel.name == "tool"

    def test_get_candidates_returns_available_tools(self):
        channel = ToolChannel(tool_registry=["search", "calculate", "read_file"])
        context = Context(query="search for information")
        candidates = channel.get_candidates(context)
        assert len(candidates) == 3
        assert all(c.channel == "tool" for c in candidates)
        assert {c.action_id for c in candidates} == {"search", "calculate", "read_file"}

    def test_candidates_have_embeddings(self):
        channel = ToolChannel(tool_registry=["search"])
        context = Context(query="test")
        candidates = channel.get_candidates(context)
        assert candidates[0].context_embedding.shape == (384,)

    def test_d1_higher_for_relevant_tool(self):
        channel = ToolChannel(
            tool_registry=["search", "calculate"],
            tool_descriptions={
                "search": "find information on the web",
                "calculate": "perform mathematical calculations",
            }
        )
        context = Context(query="search for python documentation")
        candidates = channel.get_candidates(context)

        search_candidate = next(c for c in candidates if c.action_id == "search")
        calc_candidate = next(c for c in candidates if c.action_id == "calculate")

        context_emb = channel._embed(context.query)
        d1_search = channel.compute_d1(context_emb, search_candidate)
        d1_calc = channel.compute_d1(context_emb, calc_candidate)

        assert d1_search > d1_calc
```

**Step 2: Run test to verify it fails**

Run: `cd /home/kloros && python -m pytest src/tests/unit/test_tool_channel.py -v`
Expected: FAIL with "ModuleNotFoundError"

**Step 3: Write minimal implementation**

```python
# src/cognition/basal_ganglia/channels/tool_channel.py
from __future__ import annotations
from typing import List, Dict, Optional
import numpy as np
import hashlib

from .base import ActionChannel
from src.cognition.basal_ganglia.types import Context, ActionCandidate


class ToolChannel(ActionChannel):
    """
    Channel for tool selection.

    Generates candidates from available tools and scores them
    based on query-tool relevance.
    """

    def __init__(
        self,
        tool_registry: Optional[List[str]] = None,
        tool_descriptions: Optional[Dict[str, str]] = None,
        embedding_dim: int = 384,
    ):
        self.tool_registry = tool_registry or []
        self.tool_descriptions = tool_descriptions or {}
        self.embedding_dim = embedding_dim
        self._embedding_cache: Dict[str, np.ndarray] = {}

    @property
    def name(self) -> str:
        return "tool"

    def get_candidates(self, context: Context) -> List[ActionCandidate]:
        candidates = []
        for tool_id in self.tool_registry:
            desc = self.tool_descriptions.get(tool_id, tool_id)
            embedding = self._embed(desc)
            candidates.append(
                ActionCandidate(
                    channel=self.name,
                    action_id=tool_id,
                    context_embedding=embedding,
                    metadata={"description": desc},
                )
            )
        return candidates

    def compute_d1(self, context_embedding: np.ndarray, candidate: ActionCandidate) -> float:
        """D1 activation based on semantic similarity."""
        if np.linalg.norm(context_embedding) == 0 or np.linalg.norm(candidate.context_embedding) == 0:
            return 0.5
        similarity = np.dot(context_embedding, candidate.context_embedding) / (
            np.linalg.norm(context_embedding) * np.linalg.norm(candidate.context_embedding)
        )
        return float(np.clip((similarity + 1) / 2, 0.0, 1.0))

    def _embed(self, text: str) -> np.ndarray:
        """
        Generate embedding for text.

        Uses deterministic hash-based embedding for testing.
        Production should use real embedder.
        """
        if text in self._embedding_cache:
            return self._embedding_cache[text]

        h = hashlib.sha256(text.encode()).digest()
        seed = int.from_bytes(h[:4], "big")
        rng = np.random.RandomState(seed)
        embedding = rng.randn(self.embedding_dim).astype(np.float32)
        embedding = embedding / np.linalg.norm(embedding)

        self._embedding_cache[text] = embedding
        return embedding
```

**Step 4: Update channels __init__.py**

```python
# src/cognition/basal_ganglia/channels/__init__.py
"""Action channels for basal ganglia."""
from .base import ActionChannel
from .tool_channel import ToolChannel

__all__ = ["ActionChannel", "ToolChannel"]
```

**Step 5: Run test to verify it passes**

Run: `cd /home/kloros && python -m pytest src/tests/unit/test_tool_channel.py -v`
Expected: PASS (all 4 tests)

**Step 6: Commit**

```bash
git add src/cognition/basal_ganglia/channels/
git add src/tests/unit/test_tool_channel.py
git commit -m "feat(basal_ganglia): add ToolChannel for tool selection"
```

---

### Task 4: Implement Direct Pathway

**Files:**
- Create: `src/cognition/basal_ganglia/pathways/__init__.py`
- Create: `src/cognition/basal_ganglia/pathways/direct.py`
- Test: `src/tests/unit/test_direct_pathway.py`

**Step 1: Write the failing test**

```python
# src/tests/unit/test_direct_pathway.py
import numpy as np
import pytest
from src.cognition.basal_ganglia.pathways.direct import DirectPathway
from src.cognition.basal_ganglia.types import ActionCandidate, DopamineSignal


class TestDirectPathway:
    def test_initial_activation_neutral(self):
        pathway = DirectPathway()
        candidate = ActionCandidate(
            channel="tool",
            action_id="search",
            context_embedding=np.random.randn(384),
        )
        activation = pathway.compute_activation(candidate.context_embedding, candidate)
        assert 0.4 <= activation <= 0.6

    def test_dopamine_burst_increases_weight(self):
        pathway = DirectPathway(learning_rate=0.1)
        candidate = ActionCandidate(
            channel="tool",
            action_id="search",
            context_embedding=np.random.randn(384),
        )

        initial = pathway.compute_activation(candidate.context_embedding, candidate)

        burst = DopamineSignal(delta=0.5, source="tool:search", timestamp=1000.0)
        pathway.update(candidate, burst)

        after = pathway.compute_activation(candidate.context_embedding, candidate)
        assert after > initial

    def test_dopamine_dip_does_not_affect_direct(self):
        pathway = DirectPathway(learning_rate=0.1)
        candidate = ActionCandidate(
            channel="tool",
            action_id="search",
            context_embedding=np.random.randn(384),
        )

        initial = pathway.compute_activation(candidate.context_embedding, candidate)

        dip = DopamineSignal(delta=-0.5, source="tool:search", timestamp=1000.0)
        pathway.update(candidate, dip)

        after = pathway.compute_activation(candidate.context_embedding, candidate)
        assert after == pytest.approx(initial, abs=0.01)

    def test_learning_rate_modifier_scales_update(self):
        pathway = DirectPathway(learning_rate=0.1)
        candidate = ActionCandidate(
            channel="tool",
            action_id="search",
            context_embedding=np.random.randn(384),
        )

        burst = DopamineSignal(delta=0.5, source="tool:search", timestamp=1000.0)

        pathway_fast = DirectPathway(learning_rate=0.1)
        pathway_fast.update(candidate, burst, lr_modifier=2.0)

        pathway_slow = DirectPathway(learning_rate=0.1)
        pathway_slow.update(candidate, burst, lr_modifier=0.5)

        fast_weight = pathway_fast.weights.get(pathway_fast._key(candidate), 0.5)
        slow_weight = pathway_slow.weights.get(pathway_slow._key(candidate), 0.5)

        assert fast_weight > slow_weight
```

**Step 2: Run test to verify it fails**

Run: `cd /home/kloros && python -m pytest src/tests/unit/test_direct_pathway.py -v`
Expected: FAIL with "ModuleNotFoundError"

**Step 3: Write minimal implementation**

```python
# src/cognition/basal_ganglia/pathways/direct.py
from __future__ import annotations
from typing import Dict, Tuple
import numpy as np
import hashlib

from src.cognition.basal_ganglia.types import ActionCandidate, DopamineSignal


class DirectPathway:
    """
    D1 'Go' pathway - facilitates selected actions.

    Linear relationship: higher activation = stronger facilitation.
    Strengthened by dopamine bursts (unexpected rewards).
    """

    def __init__(self, learning_rate: float = 0.01, n_clusters: int = 100):
        self.learning_rate = learning_rate
        self.n_clusters = n_clusters
        self.weights: Dict[Tuple[int, str], float] = {}

    def compute_activation(self, context_embedding: np.ndarray, candidate: ActionCandidate) -> float:
        """Linear activation: weight × context_similarity."""
        key = self._key(candidate)
        weight = self.weights.get(key, 0.5)

        similarity = self._context_similarity(context_embedding, candidate)
        return float(np.clip(weight * similarity, 0.0, 1.0))

    def update(
        self,
        candidate: ActionCandidate,
        dopamine: DopamineSignal,
        lr_modifier: float = 1.0,
    ) -> None:
        """Update weights based on dopamine signal (bursts only)."""
        if dopamine.delta <= 0:
            return

        key = self._key(candidate)
        current = self.weights.get(key, 0.5)
        effective_lr = self.learning_rate * lr_modifier

        self.weights[key] = float(np.clip(
            current + effective_lr * dopamine.delta,
            0.0,
            1.0
        ))

    def _key(self, candidate: ActionCandidate) -> Tuple[int, str]:
        """Generate (cluster, action_id) key."""
        cluster = self._cluster(candidate.context_embedding)
        return (cluster, candidate.action_id)

    def _cluster(self, embedding: np.ndarray) -> int:
        """Assign embedding to cluster via hash."""
        h = hashlib.md5(embedding.tobytes()).digest()
        return int.from_bytes(h[:2], "big") % self.n_clusters

    def _context_similarity(self, context_emb: np.ndarray, candidate: ActionCandidate) -> float:
        """Cosine similarity normalized to [0, 1]."""
        if np.linalg.norm(context_emb) == 0 or np.linalg.norm(candidate.context_embedding) == 0:
            return 0.5
        cos_sim = np.dot(context_emb, candidate.context_embedding) / (
            np.linalg.norm(context_emb) * np.linalg.norm(candidate.context_embedding)
        )
        return float((cos_sim + 1) / 2)
```

```python
# src/cognition/basal_ganglia/pathways/__init__.py
"""D1/D2/Striosomal pathways for basal ganglia."""
from .direct import DirectPathway

__all__ = ["DirectPathway"]
```

**Step 4: Run test to verify it passes**

Run: `cd /home/kloros && python -m pytest src/tests/unit/test_direct_pathway.py -v`
Expected: PASS (all 4 tests)

**Step 5: Commit**

```bash
git add src/cognition/basal_ganglia/pathways/
git add src/tests/unit/test_direct_pathway.py
git commit -m "feat(basal_ganglia): add DirectPathway (D1) with dopamine burst learning"
```

---

### Task 5: Implement Indirect Pathway

**Files:**
- Create: `src/cognition/basal_ganglia/pathways/indirect.py`
- Modify: `src/cognition/basal_ganglia/pathways/__init__.py`
- Test: `src/tests/unit/test_indirect_pathway.py`

**Step 1: Write the failing test**

```python
# src/tests/unit/test_indirect_pathway.py
import numpy as np
import pytest
from src.cognition.basal_ganglia.pathways.indirect import IndirectPathway
from src.cognition.basal_ganglia.types import ActionCandidate, DopamineSignal


class TestIndirectPathway:
    def test_inverted_u_peaks_at_moderate_weight(self):
        pathway = IndirectPathway()

        low = pathway._inverted_u(0.2)
        mid = pathway._inverted_u(0.6)
        high = pathway._inverted_u(0.9)

        assert mid > low
        assert mid > high

    def test_dopamine_dip_increases_weight(self):
        pathway = IndirectPathway(learning_rate=0.1)
        candidate = ActionCandidate(
            channel="tool",
            action_id="search",
            context_embedding=np.random.randn(384),
        )

        initial_weight = pathway.weights.get(pathway._key(candidate), 0.5)

        dip = DopamineSignal(delta=-0.5, source="tool:search", timestamp=1000.0)
        pathway.update(candidate, dip)

        after_weight = pathway.weights.get(pathway._key(candidate), 0.5)
        assert after_weight > initial_weight

    def test_dopamine_burst_does_not_affect_indirect(self):
        pathway = IndirectPathway(learning_rate=0.1)
        candidate = ActionCandidate(
            channel="tool",
            action_id="search",
            context_embedding=np.random.randn(384),
        )

        burst = DopamineSignal(delta=0.5, source="tool:search", timestamp=1000.0)
        pathway.update(candidate, burst)

        weight = pathway.weights.get(pathway._key(candidate), 0.5)
        assert weight == pytest.approx(0.5, abs=0.01)

    def test_activation_uses_inverted_u(self):
        pathway = IndirectPathway()
        candidate = ActionCandidate(
            channel="tool",
            action_id="search",
            context_embedding=np.random.randn(384),
        )

        activation = pathway.compute_activation(candidate.context_embedding, candidate)
        assert 0.0 <= activation <= 1.0
```

**Step 2: Run test to verify it fails**

Run: `cd /home/kloros && python -m pytest src/tests/unit/test_indirect_pathway.py -v`
Expected: FAIL with "ModuleNotFoundError"

**Step 3: Write minimal implementation**

```python
# src/cognition/basal_ganglia/pathways/indirect.py
from __future__ import annotations
from typing import Dict, Tuple
import numpy as np
import hashlib

from src.cognition.basal_ganglia.types import ActionCandidate, DopamineSignal


class IndirectPathway:
    """
    D2 'NoGo' pathway - surround inhibition.

    Nonlinear inverted-U: moderate activation provides good inhibition,
    but too much causes over-inhibition (freezing).
    Strengthened by dopamine dips (omissions/punishments).
    """

    def __init__(
        self,
        learning_rate: float = 0.01,
        n_clusters: int = 100,
        peak: float = 0.6,
    ):
        self.learning_rate = learning_rate
        self.n_clusters = n_clusters
        self.peak = peak
        self.weights: Dict[Tuple[int, str], float] = {}

    def compute_activation(self, context_embedding: np.ndarray, candidate: ActionCandidate) -> float:
        """Inverted-U activation for surround inhibition."""
        key = self._key(candidate)
        weight = self.weights.get(key, 0.5)

        inverted_u = self._inverted_u(weight)
        surround = self._surround_signal(context_embedding, candidate)

        return float(np.clip(inverted_u * surround, 0.01, 1.0))

    def update(
        self,
        candidate: ActionCandidate,
        dopamine: DopamineSignal,
        lr_modifier: float = 1.0,
    ) -> None:
        """Update weights based on dopamine signal (dips only)."""
        if dopamine.delta >= 0:
            return

        key = self._key(candidate)
        current = self.weights.get(key, 0.5)
        effective_lr = self.learning_rate * lr_modifier

        self.weights[key] = float(np.clip(
            current - effective_lr * dopamine.delta,
            0.0,
            1.0
        ))

    def _inverted_u(self, x: float) -> float:
        """Inverted-U curve peaking at self.peak."""
        return float(1.0 - ((x - self.peak) ** 2) / (self.peak ** 2))

    def _surround_signal(self, context_emb: np.ndarray, candidate: ActionCandidate) -> float:
        """Surround inhibition signal - inhibit similar but not identical."""
        if np.linalg.norm(context_emb) == 0 or np.linalg.norm(candidate.context_embedding) == 0:
            return 0.5
        cos_sim = np.dot(context_emb, candidate.context_embedding) / (
            np.linalg.norm(context_emb) * np.linalg.norm(candidate.context_embedding)
        )
        return float((1 - abs(cos_sim)) * 0.5 + 0.5)

    def _key(self, candidate: ActionCandidate) -> Tuple[int, str]:
        """Generate (cluster, action_id) key."""
        cluster = self._cluster(candidate.context_embedding)
        return (cluster, candidate.action_id)

    def _cluster(self, embedding: np.ndarray) -> int:
        """Assign embedding to cluster via hash."""
        h = hashlib.md5(embedding.tobytes()).digest()
        return int.from_bytes(h[:2], "big") % self.n_clusters
```

**Step 4: Update pathways __init__.py**

```python
# src/cognition/basal_ganglia/pathways/__init__.py
"""D1/D2/Striosomal pathways for basal ganglia."""
from .direct import DirectPathway
from .indirect import IndirectPathway

__all__ = ["DirectPathway", "IndirectPathway"]
```

**Step 5: Run test to verify it passes**

Run: `cd /home/kloros && python -m pytest src/tests/unit/test_indirect_pathway.py -v`
Expected: PASS (all 4 tests)

**Step 6: Commit**

```bash
git add src/cognition/basal_ganglia/pathways/
git add src/tests/unit/test_indirect_pathway.py
git commit -m "feat(basal_ganglia): add IndirectPathway (D2) with inverted-U and dip learning"
```

---

### Task 6: Implement Substantia Nigra (Dopamine)

**Files:**
- Create: `src/cognition/basal_ganglia/substantia_nigra.py`
- Modify: `src/cognition/basal_ganglia/__init__.py`
- Test: `src/tests/unit/test_substantia_nigra.py`

**Step 1: Write the failing test**

```python
# src/tests/unit/test_substantia_nigra.py
import numpy as np
import pytest
from src.cognition.basal_ganglia.substantia_nigra import SubstantiaNigra
from src.cognition.basal_ganglia.types import ActionCandidate, Outcome


class TestSubstantiaNigra:
    def test_positive_prediction_error_creates_burst(self):
        sn = SubstantiaNigra()
        candidate = ActionCandidate(
            channel="tool",
            action_id="search",
            context_embedding=np.random.randn(384),
        )
        outcome = Outcome(success=True, latency_ms=100)

        signal = sn.compute_signal(candidate, outcome)

        assert signal.delta > 0
        assert signal.is_burst

    def test_negative_prediction_error_creates_dip(self):
        sn = SubstantiaNigra()
        candidate = ActionCandidate(
            channel="tool",
            action_id="search",
            context_embedding=np.random.randn(384),
        )

        good_outcome = Outcome(success=True, latency_ms=100)
        sn.compute_signal(candidate, good_outcome)
        sn.compute_signal(candidate, good_outcome)
        sn.compute_signal(candidate, good_outcome)

        bad_outcome = Outcome(success=False, latency_ms=100)
        signal = sn.compute_signal(candidate, bad_outcome)

        assert signal.delta < 0
        assert signal.is_dip

    def test_predictions_improve_over_time(self):
        sn = SubstantiaNigra()
        candidate = ActionCandidate(
            channel="tool",
            action_id="search",
            context_embedding=np.random.randn(384),
        )

        deltas = []
        for _ in range(10):
            outcome = Outcome(success=True, latency_ms=100)
            signal = sn.compute_signal(candidate, outcome)
            deltas.append(abs(signal.delta))

        assert deltas[-1] < deltas[0]

    def test_signal_contains_metadata(self):
        sn = SubstantiaNigra()
        candidate = ActionCandidate(
            channel="tool",
            action_id="search",
            context_embedding=np.random.randn(384),
        )
        outcome = Outcome(success=True, latency_ms=100)

        signal = sn.compute_signal(candidate, outcome)

        assert signal.source == "tool:search"
        assert signal.timestamp > 0
```

**Step 2: Run test to verify it fails**

Run: `cd /home/kloros && python -m pytest src/tests/unit/test_substantia_nigra.py -v`
Expected: FAIL with "ModuleNotFoundError"

**Step 3: Write minimal implementation**

```python
# src/cognition/basal_ganglia/substantia_nigra.py
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, Tuple
from collections import deque
import numpy as np
import hashlib
import time

from src.cognition.basal_ganglia.types import ActionCandidate, Outcome, DopamineSignal


@dataclass
class RunningStats:
    """Running mean and count for predictions."""
    mean: float = 0.0
    count: int = 0

    def update(self, value: float) -> None:
        self.count += 1
        alpha = 1.0 / self.count
        self.mean += alpha * (value - self.mean)


class SubstantiaNigra:
    """
    Dopamine neuron population - generates reward prediction error.

    Core computation: δ = actual_reward - expected_reward
    Positive δ (burst) → strengthen Direct pathway
    Negative δ (dip) → strengthen Indirect pathway
    """

    def __init__(self, n_clusters: int = 100):
        self.n_clusters = n_clusters
        self.predictions: Dict[Tuple[int, str], RunningStats] = {}
        self.recent_signals: deque = deque(maxlen=100)

    def compute_signal(self, candidate: ActionCandidate, outcome: Outcome) -> DopamineSignal:
        """Compute dopamine signal from prediction error."""
        key = self._key(candidate)

        if key not in self.predictions:
            self.predictions[key] = RunningStats()

        stats = self.predictions[key]
        expected = stats.mean if stats.count > 0 else 0.0
        actual = outcome.reward

        confidence = min(stats.count / 10, 1.0)
        uncertainty_bonus = 1.0 + (1.0 - confidence) * 0.5

        delta = (actual - expected) * uncertainty_bonus

        signal = DopamineSignal(
            delta=float(delta),
            source=f"{candidate.channel}:{candidate.action_id}",
            timestamp=time.time(),
            expected_reward=expected,
            actual_reward=actual,
        )

        stats.update(actual)
        self.recent_signals.append(signal)

        return signal

    def _key(self, candidate: ActionCandidate) -> Tuple[int, str]:
        """Generate (cluster, action_id) key."""
        cluster = self._cluster(candidate.context_embedding)
        return (cluster, candidate.action_id)

    def _cluster(self, embedding: np.ndarray) -> int:
        """Assign embedding to cluster via hash."""
        h = hashlib.md5(embedding.tobytes()).digest()
        return int.from_bytes(h[:2], "big") % self.n_clusters
```

**Step 4: Update main __init__.py**

```python
# src/cognition/basal_ganglia/__init__.py
"""Basal Ganglia - Action selection via D1/D2 pathway competition."""
from .types import (
    ActionCandidate,
    DopamineSignal,
    SelectionResult,
    Outcome,
    Context,
)
from .substantia_nigra import SubstantiaNigra

__all__ = [
    "ActionCandidate",
    "DopamineSignal",
    "SelectionResult",
    "Outcome",
    "Context",
    "SubstantiaNigra",
]
```

**Step 5: Run test to verify it passes**

Run: `cd /home/kloros && python -m pytest src/tests/unit/test_substantia_nigra.py -v`
Expected: PASS (all 4 tests)

**Step 6: Commit**

```bash
git add src/cognition/basal_ganglia/substantia_nigra.py
git add src/cognition/basal_ganglia/__init__.py
git add src/tests/unit/test_substantia_nigra.py
git commit -m "feat(basal_ganglia): add SubstantiaNigra for dopamine signal generation"
```

---

### Task 7: Implement Globus Pallidus (Selection)

**Files:**
- Create: `src/cognition/basal_ganglia/globus_pallidus.py`
- Modify: `src/cognition/basal_ganglia/__init__.py`
- Test: `src/tests/unit/test_globus_pallidus.py`

**Step 1: Write the failing test**

```python
# src/tests/unit/test_globus_pallidus.py
import numpy as np
import pytest
from src.cognition.basal_ganglia.globus_pallidus import GlobusPallidus
from src.cognition.basal_ganglia.types import ActionCandidate, SelectionResult


class TestGlobusPallidus:
    def test_selects_highest_competition_degree(self):
        gp = GlobusPallidus()

        candidates = [
            ActionCandidate(
                channel="tool",
                action_id="a",
                context_embedding=np.zeros(384),
                direct_activation=0.8,
                indirect_activation=0.4,
            ),
            ActionCandidate(
                channel="tool",
                action_id="b",
                context_embedding=np.zeros(384),
                direct_activation=0.5,
                indirect_activation=0.5,
            ),
        ]

        result = gp.select(candidates)

        assert result.selected.action_id == "a"
        assert result.selection_method == "competition"

    def test_thin_margin_requests_deliberation(self):
        gp = GlobusPallidus(min_margin=0.5)

        candidates = [
            ActionCandidate(
                channel="tool",
                action_id="a",
                context_embedding=np.zeros(384),
                direct_activation=0.6,
                indirect_activation=0.5,
            ),
            ActionCandidate(
                channel="tool",
                action_id="b",
                context_embedding=np.zeros(384),
                direct_activation=0.55,
                indirect_activation=0.5,
            ),
        ]

        result = gp.select(candidates)

        assert result.deliberation_requested is True
        assert "thin_margin" in result.deliberation_reason

    def test_novel_context_requests_deliberation(self):
        gp = GlobusPallidus()

        candidates = [
            ActionCandidate(
                channel="tool",
                action_id="a",
                context_embedding=np.zeros(384),
                direct_activation=0.9,
                indirect_activation=0.1,
                is_novel_context=True,
            ),
        ]

        result = gp.select(candidates)

        assert result.deliberation_requested is True
        assert "novel_context" in result.deliberation_reason

    def test_runner_up_tracked(self):
        gp = GlobusPallidus()

        candidates = [
            ActionCandidate(
                channel="tool",
                action_id="winner",
                context_embedding=np.zeros(384),
                direct_activation=0.9,
                indirect_activation=0.1,
            ),
            ActionCandidate(
                channel="tool",
                action_id="second",
                context_embedding=np.zeros(384),
                direct_activation=0.7,
                indirect_activation=0.3,
            ),
        ]

        result = gp.select(candidates)

        assert result.runner_up is not None
        assert result.runner_up.action_id == "second"
```

**Step 2: Run test to verify it fails**

Run: `cd /home/kloros && python -m pytest src/tests/unit/test_globus_pallidus.py -v`
Expected: FAIL with "ModuleNotFoundError"

**Step 3: Write minimal implementation**

```python
# src/cognition/basal_ganglia/globus_pallidus.py
from __future__ import annotations
from dataclasses import dataclass
from typing import List, Optional

from src.cognition.basal_ganglia.types import ActionCandidate, SelectionResult


@dataclass
class GlobusPallidusConfig:
    min_margin: float = 0.3
    high_stakes_threshold: float = 0.7


class GlobusPallidus:
    """
    Output nucleus - final action selection via competition.

    Selects action with highest competition degree (D1/D2 ratio).
    Requests deliberation when margin is thin or context is novel.
    """

    def __init__(
        self,
        min_margin: float = 0.3,
        high_stakes_threshold: float = 0.7,
    ):
        self.min_margin = min_margin
        self.high_stakes_threshold = high_stakes_threshold

    def select(self, candidates: List[ActionCandidate]) -> SelectionResult:
        """Select best action from candidates."""
        if not candidates:
            raise ValueError("No candidates provided")

        scored = [
            (c.competition_degree, c)
            for c in candidates
        ]
        scored.sort(key=lambda x: x[0], reverse=True)

        winner_score, winner = scored[0]
        runner_up_score, runner_up = scored[1] if len(scored) > 1 else (0.0, None)

        margin = winner_score - runner_up_score

        deliberation_reasons = []

        if margin < self.min_margin:
            deliberation_reasons.append(f"thin_margin:{margin:.2f}")

        if winner.is_novel_context:
            deliberation_reasons.append("novel_context")

        deliberation_requested = len(deliberation_reasons) > 0

        return SelectionResult(
            selected=winner,
            runner_up=runner_up,
            competition_margin=margin,
            deliberation_requested=deliberation_requested,
            deliberation_reason="|".join(deliberation_reasons),
            selection_method="deliberation" if deliberation_requested else "competition",
        )
```

**Step 4: Update main __init__.py**

```python
# src/cognition/basal_ganglia/__init__.py
"""Basal Ganglia - Action selection via D1/D2 pathway competition."""
from .types import (
    ActionCandidate,
    DopamineSignal,
    SelectionResult,
    Outcome,
    Context,
)
from .substantia_nigra import SubstantiaNigra
from .globus_pallidus import GlobusPallidus

__all__ = [
    "ActionCandidate",
    "DopamineSignal",
    "SelectionResult",
    "Outcome",
    "Context",
    "SubstantiaNigra",
    "GlobusPallidus",
]
```

**Step 5: Run test to verify it passes**

Run: `cd /home/kloros && python -m pytest src/tests/unit/test_globus_pallidus.py -v`
Expected: PASS (all 4 tests)

**Step 6: Commit**

```bash
git add src/cognition/basal_ganglia/globus_pallidus.py
git add src/cognition/basal_ganglia/__init__.py
git add src/tests/unit/test_globus_pallidus.py
git commit -m "feat(basal_ganglia): add GlobusPallidus for action selection"
```

---

### Task 8: Implement Striatum (Input Nucleus)

**Files:**
- Create: `src/cognition/basal_ganglia/striatum.py`
- Modify: `src/cognition/basal_ganglia/__init__.py`
- Test: `src/tests/unit/test_striatum.py`

**Step 1: Write the failing test**

```python
# src/tests/unit/test_striatum.py
import numpy as np
import pytest
from src.cognition.basal_ganglia.striatum import Striatum
from src.cognition.basal_ganglia.channels.tool_channel import ToolChannel
from src.cognition.basal_ganglia.types import Context


class TestStriatum:
    def test_processes_context_into_candidates(self):
        channel = ToolChannel(tool_registry=["search", "calculate"])
        striatum = Striatum(channels=[channel])

        context = Context(query="find information")
        candidates = striatum.process(context)

        assert len(candidates) == 2
        assert all(c.channel == "tool" for c in candidates)

    def test_candidates_have_d1_d2_scores(self):
        channel = ToolChannel(tool_registry=["search"])
        striatum = Striatum(channels=[channel])

        context = Context(query="test")
        candidates = striatum.process(context)

        assert candidates[0].direct_activation > 0
        assert candidates[0].indirect_activation > 0

    def test_detects_novel_context(self):
        channel = ToolChannel(tool_registry=["search"])
        striatum = Striatum(channels=[channel], novelty_threshold=0.5)

        context1 = Context(query="first query about apples")
        striatum.process(context1)

        context2 = Context(query="completely different topic about quantum physics")
        candidates = striatum.process(context2)

        assert candidates[0].is_novel_context is True

    def test_familiar_context_not_novel(self):
        channel = ToolChannel(tool_registry=["search"])
        striatum = Striatum(channels=[channel])

        for _ in range(5):
            context = Context(query="search for python docs")
            striatum.process(context)

        context = Context(query="search for python documentation")
        candidates = striatum.process(context)

        assert candidates[0].is_novel_context is False
```

**Step 2: Run test to verify it fails**

Run: `cd /home/kloros && python -m pytest src/tests/unit/test_striatum.py -v`
Expected: FAIL with "ModuleNotFoundError"

**Step 3: Write minimal implementation**

```python
# src/cognition/basal_ganglia/striatum.py
from __future__ import annotations
from dataclasses import dataclass
from typing import List, Dict
from collections import deque
import numpy as np
import hashlib

from src.cognition.basal_ganglia.types import Context, ActionCandidate
from src.cognition.basal_ganglia.channels.base import ActionChannel


@dataclass
class StriatumConfig:
    embedding_dim: int = 384
    novelty_threshold: float = 0.7
    history_size: int = 1000


class Striatum:
    """
    Input nucleus - transforms context into channel activations.

    Receives context, generates candidates from each channel,
    computes D1/D2 activations, and flags novel contexts.
    """

    def __init__(
        self,
        channels: List[ActionChannel],
        embedding_dim: int = 384,
        novelty_threshold: float = 0.7,
        history_size: int = 1000,
    ):
        self.channels = {ch.name: ch for ch in channels}
        self.embedding_dim = embedding_dim
        self.novelty_threshold = novelty_threshold
        self.context_history: deque = deque(maxlen=history_size)

    def process(self, context: Context) -> List[ActionCandidate]:
        """Transform context into scored action candidates."""
        context_embedding = self._embed_context(context)
        is_novel = self._check_novelty(context_embedding)

        candidates = []
        for channel in self.channels.values():
            channel_candidates = channel.get_candidates(context)
            for candidate in channel_candidates:
                candidate.direct_activation = channel.compute_d1(
                    context_embedding, candidate
                )
                candidate.indirect_activation = channel.compute_d2(
                    context_embedding, candidate
                )
                candidate.is_novel_context = is_novel
                candidates.append(candidate)

        self.context_history.append(context_embedding)
        return candidates

    def _embed_context(self, context: Context) -> np.ndarray:
        """Generate embedding for context."""
        text = context.query
        h = hashlib.sha256(text.encode()).digest()
        seed = int.from_bytes(h[:4], "big")
        rng = np.random.RandomState(seed)
        embedding = rng.randn(self.embedding_dim).astype(np.float32)
        return embedding / np.linalg.norm(embedding)

    def _check_novelty(self, embedding: np.ndarray) -> bool:
        """Check if context is novel compared to history."""
        if len(self.context_history) < 5:
            return True

        similarities = []
        for hist_emb in list(self.context_history)[-50:]:
            if np.linalg.norm(hist_emb) > 0:
                sim = np.dot(embedding, hist_emb) / (
                    np.linalg.norm(embedding) * np.linalg.norm(hist_emb)
                )
                similarities.append(sim)

        if not similarities:
            return True

        max_similarity = max(similarities)
        return max_similarity < self.novelty_threshold

    def get_context_embedding(self, context: Context) -> np.ndarray:
        """Public method to get embedding for a context."""
        return self._embed_context(context)
```

**Step 4: Update main __init__.py**

```python
# src/cognition/basal_ganglia/__init__.py
"""Basal Ganglia - Action selection via D1/D2 pathway competition."""
from .types import (
    ActionCandidate,
    DopamineSignal,
    SelectionResult,
    Outcome,
    Context,
)
from .substantia_nigra import SubstantiaNigra
from .globus_pallidus import GlobusPallidus
from .striatum import Striatum

__all__ = [
    "ActionCandidate",
    "DopamineSignal",
    "SelectionResult",
    "Outcome",
    "Context",
    "SubstantiaNigra",
    "GlobusPallidus",
    "Striatum",
]
```

**Step 5: Run test to verify it passes**

Run: `cd /home/kloros && python -m pytest src/tests/unit/test_striatum.py -v`
Expected: PASS (all 4 tests)

**Step 6: Commit**

```bash
git add src/cognition/basal_ganglia/striatum.py
git add src/cognition/basal_ganglia/__init__.py
git add src/tests/unit/test_striatum.py
git commit -m "feat(basal_ganglia): add Striatum for input processing and novelty detection"
```

---

### Task 9: Integration Test - Full Selection Loop

**Files:**
- Test: `src/tests/integration/test_basal_ganglia_integration.py`

**Step 1: Write the integration test**

```python
# src/tests/integration/test_basal_ganglia_integration.py
import numpy as np
import pytest
from src.cognition.basal_ganglia.striatum import Striatum
from src.cognition.basal_ganglia.globus_pallidus import GlobusPallidus
from src.cognition.basal_ganglia.substantia_nigra import SubstantiaNigra
from src.cognition.basal_ganglia.pathways.direct import DirectPathway
from src.cognition.basal_ganglia.pathways.indirect import IndirectPathway
from src.cognition.basal_ganglia.channels.tool_channel import ToolChannel
from src.cognition.basal_ganglia.types import Context, Outcome


class TestBasalGangliaIntegration:
    def test_full_selection_and_learning_loop(self):
        channel = ToolChannel(
            tool_registry=["search", "calculate", "read"],
            tool_descriptions={
                "search": "find information on the web",
                "calculate": "perform math",
                "read": "read a file",
            }
        )

        striatum = Striatum(channels=[channel])
        direct = DirectPathway(learning_rate=0.1)
        indirect = IndirectPathway(learning_rate=0.1)
        gp = GlobusPallidus()
        sn = SubstantiaNigra()

        context = Context(query="search for python documentation")
        candidates = striatum.process(context)

        context_emb = striatum.get_context_embedding(context)
        for c in candidates:
            c.direct_activation = direct.compute_activation(context_emb, c)
            c.indirect_activation = indirect.compute_activation(context_emb, c)

        selection = gp.select(candidates)

        assert selection.selected is not None
        assert selection.selection_method in ["competition", "deliberation"]

        outcome = Outcome(success=True, latency_ms=200)
        dopamine = sn.compute_signal(selection.selected, outcome)

        direct.update(selection.selected, dopamine)
        indirect.update(selection.selected, dopamine)

        assert dopamine.delta != 0

    def test_learning_improves_selection(self):
        channel = ToolChannel(
            tool_registry=["good_tool", "bad_tool"],
            tool_descriptions={
                "good_tool": "always works",
                "bad_tool": "never works",
            }
        )

        striatum = Striatum(channels=[channel])
        direct = DirectPathway(learning_rate=0.2)
        indirect = IndirectPathway(learning_rate=0.2)
        gp = GlobusPallidus()
        sn = SubstantiaNigra()

        for _ in range(10):
            context = Context(query="do the task")
            candidates = striatum.process(context)
            context_emb = striatum.get_context_embedding(context)

            for c in candidates:
                c.direct_activation = direct.compute_activation(context_emb, c)
                c.indirect_activation = indirect.compute_activation(context_emb, c)

            selection = gp.select(candidates)

            success = selection.selected.action_id == "good_tool"
            outcome = Outcome(success=success, latency_ms=100)
            dopamine = sn.compute_signal(selection.selected, outcome)

            direct.update(selection.selected, dopamine)
            indirect.update(selection.selected, dopamine)

        final_context = Context(query="do the task")
        final_candidates = striatum.process(final_context)
        final_emb = striatum.get_context_embedding(final_context)

        for c in final_candidates:
            c.direct_activation = direct.compute_activation(final_emb, c)
            c.indirect_activation = indirect.compute_activation(final_emb, c)

        good = next(c for c in final_candidates if c.action_id == "good_tool")
        bad = next(c for c in final_candidates if c.action_id == "bad_tool")

        assert good.competition_degree > bad.competition_degree
```

**Step 2: Run test**

Run: `cd /home/kloros && python -m pytest src/tests/integration/test_basal_ganglia_integration.py -v`
Expected: PASS (both tests)

**Step 3: Commit**

```bash
git add src/tests/integration/test_basal_ganglia_integration.py
git commit -m "test(basal_ganglia): add integration tests for full selection loop"
```

---

## Phase 1 Complete Checkpoint

Run all Phase 1 tests:

```bash
cd /home/kloros && python -m pytest src/tests/unit/test_basal_ganglia*.py src/tests/unit/test_*pathway*.py src/tests/unit/test_*channel*.py src/tests/integration/test_basal_ganglia*.py -v
```

Expected: All tests PASS

---

## Phase 2-5: Future Tasks

Phase 2 (Habits), Phase 3 (Striosomal), Phase 4 (Multi-channel), and Phase 5 (Orchestrator) will be planned after Phase 1 is validated.
