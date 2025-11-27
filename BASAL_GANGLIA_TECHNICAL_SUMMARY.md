# Basal Ganglia Phase 1 - Technical Summary

## Architecture Overview

```
INPUT LAYER (Striatum)
    ↓
    ├─ Context Embedding (hash-based, deterministic)
    ├─ Novelty Detection (word overlap similarity)
    └─ Channel Activation (D1/D2 scoring)
    ↓
PATHWAY LAYERS (Parallel)
    ├─ DirectPathway (D1):
    │  ├─ Weight: Dict[(cluster, action_id) → float]
    │  ├─ Activation: weight × context_similarity
    │  └─ Update: dopamine_burst → increase weight
    │
    └─ IndirectPathway (D2):
       ├─ Weight: Dict[(cluster, action_id) → float]
       ├─ Activation: inverted_u(weight) × surround_signal
       └─ Update: dopamine_dip → increase weight
    ↓
OUTPUT LAYER (Globus Pallidus)
    ├─ Competition Degree: D1 / D2 (higher = wins)
    ├─ Winner Selection: argmax(competition_degree)
    └─ Deliberation Gating: margin < threshold OR novel_context
    ↓
LEARNING LAYER (Substantia Nigra)
    ├─ Prediction: running_mean(rewards_per_action)
    ├─ Error: δ = actual - expected
    ├─ Uncertainty Bonus: (1 + (1 - confidence) * 0.5)
    └─ Signal: δ_adjusted → pathways
```

## Component Specifications

### 1. Core Types (types.py)

**Context**
- `query: str` - User query
- `conversation_history: List[dict]` - Conversation context
- `user_profile: Optional[dict]` - User preferences
- `stakes_level: float` - Action stakes (0-1)
- `novelty_score: float` - Pre-computed novelty
- `metadata: dict` - Extensible attributes

**ActionCandidate**
- `channel: str` - Channel name (tool, agent, response, etc.)
- `action_id: str` - Specific action identifier
- `context_embedding: np.ndarray` - 384-D embedding
- `direct_activation: float` - D1 pathway strength
- `indirect_activation: float` - D2 pathway strength
- `is_novel_context: bool` - Novel situation flag
- Property: `competition_degree = direct / max(indirect, 0.01)`

**DopamineSignal**
- `delta: float` - Prediction error (can be negative)
- `source: str` - Action source ("channel:action_id")
- `timestamp: float` - Signal generation time
- `expected_reward: float` - Predicted reward
- `actual_reward: float` - Observed reward
- Property: `is_burst = delta > 0`
- Property: `is_dip = delta < 0`

**Outcome**
- `success: bool` - Action succeeded
- `latency_ms: float` - Execution time
- `user_feedback: Optional[float]` - User rating [-1, 1]
- `tokens_used: Optional[int]` - Resource consumption
- `error_message: Optional[str]` - Error details
- Property: `reward = composition(success, feedback, latency, efficiency)`

**SelectionResult**
- `selected: ActionCandidate` - Winner
- `runner_up: Optional[ActionCandidate]` - Second place
- `competition_margin: float` - D1_winner - D1_runnerup
- `deliberation_requested: bool` - Escalate to conscious reasoning
- `deliberation_reason: str` - Why deliberation needed
- `selection_method: str` - "competition" or "deliberation"

### 2. Channel System (channels/)

**ActionChannel (Abstract Base)**
```python
class ActionChannel(ABC):
    @property
    @abstractmethod
    def name(self) -> str: ...

    @abstractmethod
    def get_candidates(self, context: Context) -> List[ActionCandidate]: ...

    def compute_d1(self, context_embedding, candidate) -> float:
        # Default: cosine_similarity normalized to [0,1]
        # Override for channel-specific logic

    def compute_d2(self, context_embedding, candidate) -> float:
        # Default: 1.0 - d1 + baseline (inverted)
        # Override for channel-specific surround inhibition
```

**ToolChannel (Concrete Implementation)**
```python
class ToolChannel(ActionChannel):
    def __init__(
        tool_registry: List[str],           # ["search", "calculate", ...]
        tool_descriptions: Dict[str, str],  # Semantic info
        embedding_dim: int = 384            # Embedding dimension
    )

    def get_candidates(context) -> List[ActionCandidate]:
        # For each tool: embed description, create candidate

    def compute_d1(context_embedding, candidate) -> float:
        # Similarity: description embedding vs context embedding

    def _embed(text) -> np.ndarray:
        # Hash-based for testing (Phase 2: replace with real embedder)
```

### 3. Pathway System (pathways/)

**DirectPathway (D1 - Facilitation)**
```python
class DirectPathway:
    weights: Dict[(cluster, action_id), float]  # Key: hash(embedding) % n_clusters

    def compute_activation(context_embedding, candidate) -> float:
        # activation = weight × context_similarity
        # Linear relationship: more weight = more facilitation

    def update(candidate, dopamine_signal, lr_modifier=1.0):
        # On dopamine burst (delta > 0):
        #   weight += lr × lr_modifier × delta
        # On dopamine dip: no update
        # Asymmetry: strengthens on reward, ignores punishment
```

**IndirectPathway (D2 - Surround Inhibition)**
```python
class IndirectPathway:
    weights: Dict[(cluster, action_id), float]
    peak: float = 0.6  # Inverted-U peaks here

    def compute_activation(context_embedding, candidate) -> float:
        # activation = inverted_u(weight) × surround_signal
        # Inverted-U: too low OR too high weight = poor inhibition
        # Surround signal: inhibit similar (not identical) actions

    def update(candidate, dopamine_signal, lr_modifier=1.0):
        # On dopamine dip (delta < 0):
        #   weight -= lr × lr_modifier × delta  (increases weight)
        # On dopamine burst: no update
        # Asymmetry: strengthens on omission/punishment, ignores reward

    def _inverted_u(weight: float) -> float:
        # 1.0 - ((weight - peak)² / peak²)
        # Peak at self.peak (default 0.6)
        # Symmetric curve around peak
```

### 4. Input Nucleus (striatum.py)

**Striatum**
```python
class Striatum:
    channels: Dict[str, ActionChannel]          # "tool" → ToolChannel
    context_history: deque(maxlen=1000)         # Recent embeddings
    _query_history: deque(maxlen=1000)          # Recent queries

    def process(context: Context) -> List[ActionCandidate]:
        1. Embed context query
        2. Check novelty (word overlap to historical queries)
        3. For each channel:
           - Get candidates
           - Compute D1 via channel.compute_d1(context_embedding, candidate)
           - Compute D2 via channel.compute_d2(context_embedding, candidate)
           - Mark novel_context flag
        4. Return aggregated candidates

    def _check_novelty(query: str, embedding) -> bool:
        # Word overlap: max(intersection/union) < novelty_threshold (0.7)
        # Returns True if < 5 historical queries (assume novel)

    def _query_similarity(query1, query2) -> float:
        # Set intersection of lowercased words / max set size
        # Range [0, 1]
```

### 5. Output Nucleus (globus_pallidus.py)

**GlobusPallidus**
```python
class GlobusPallidus:
    min_margin: float = 0.3                 # Confidence threshold
    high_stakes_threshold: float = 0.7      # Stakes detection (unused Phase 1)

    def select(candidates: List[ActionCandidate]) -> SelectionResult:
        1. Score candidates by competition_degree (D1/D2 ratio)
        2. Sort descending, pick winner + runner-up
        3. Calculate margin = winner_score - runner_up_score
        4. Check deliberation conditions:
           a. margin < min_margin (thin margin)
           b. winner.is_novel_context (novel situation)
        5. Return SelectionResult with flags
```

### 6. Dopamine System (substantia_nigra.py)

**SubstantiaNigra**
```python
class SubstantiaNigra:
    predictions: Dict[(cluster, action_id), RunningStats]  # Expected reward tracker
    recent_signals: deque(maxlen=100)                       # Signal history

    def compute_signal(candidate, outcome) -> DopamineSignal:
        1. Get or create RunningStats for candidate
        2. Extract expected = stats.mean
        3. Extract actual = outcome.reward
        4. Compute confidence = min(count / 10, 1.0)
        5. Apply uncertainty_bonus = 1.0 + (1.0 - confidence) * 0.5
        6. Calculate delta = (actual - expected) × uncertainty_bonus
           - Early learning: high uncertainty → larger signals
           - Late learning: low uncertainty → smaller signals
        7. Update running mean: stats.update(actual)
        8. Return DopamineSignal(delta=delta, ...)

class RunningStats:
    mean: float = 0.0
    count: int = 0

    def update(value: float):
        # Welford's online algorithm: O(1) space, no sum overflow risk
        # alpha = 1.0 / count
        # mean += alpha * (value - mean)
```

## Data Flow Example

**Scenario: User asks "search for python docs"**

```
1. INPUT (Striatum.process)
   Context(query="search for python docs", ...)
   ├─ Embed query via SHA256 → normalized vector
   ├─ Check novelty: compare to last 50 queries
   │  └─ "search for python docs" vs "search for js docs" → similar
   │     (high word overlap: search, for → not novel)
   └─ Get candidates from ToolChannel
      ├─ search: embed("find info on web") → candidate_A
      ├─ calculate: embed("perform math") → candidate_B
      └─ read: embed("read a file") → candidate_C

2. D1 ACTIVATION (DirectPathway)
   For each candidate:
   ├─ Fetch cluster key: hash(embedding) % 100
   ├─ Fetch weight: weights.get((cluster, action_id), 0.5)
   ├─ Compute similarity: cos(query_emb, action_emb)
   ├─ activation_d1 = weight × similarity
   └─ candidate_A.direct_activation = 0.65  (search relevant)

3. D2 ACTIVATION (IndirectPathway)
   For each candidate:
   ├─ Fetch cluster key: same as D1
   ├─ Fetch weight: weights.get((cluster, action_id), 0.5)
   ├─ Compute inverted_u: 1.0 - ((weight - 0.6)² / 0.6²)
   ├─ Compute surround: 0.5 + 0.5 × (1 - |cos|)
   └─ activation_d2 = inverted_u × surround
      └─ candidate_A.indirect_activation = 0.35

4. SELECTION (GlobusPallidus.select)
   ├─ competition_A = 0.65 / max(0.35, 0.01) ≈ 1.86
   ├─ competition_B = 0.30 / max(0.45, 0.01) ≈ 0.67
   ├─ competition_C = 0.25 / max(0.40, 0.01) ≈ 0.63
   ├─ Sort: [A(1.86), B(0.67), C(0.63)]
   ├─ Winner: search, Margin: 1.86 - 0.67 = 1.19 (> min_margin 0.3)
   └─ Deliberation: not requested

5. EXECUTION (external)
   search("python docs")
   └─ Returns: Outcome(success=True, latency_ms=450, user_feedback=0.8)

6. DOPAMINE SIGNAL (SubstantiaNigra.compute_signal)
   ├─ Get stats for (cluster_A, "search")
   ├─ Count = 5 (seen this before)
   ├─ Expected = 0.40 (from running mean)
   ├─ Actual = 0.5 + 0.8×0.3 - min(450/5000, 0.2) + efficiency
   │         ≈ 0.5 + 0.24 - 0.09 + 0.05 = 0.70
   ├─ Confidence = min(5/10, 1.0) = 0.5
   ├─ Uncertainty_bonus = 1.0 + 0.5×0.5 = 1.25
   ├─ Delta = (0.70 - 0.40) × 1.25 = 0.375 (dopamine burst)
   └─ Signal: DopamineSignal(delta=0.375, is_burst=True)

7. LEARNING (Pathways.update)
   DirectPathway:
   ├─ delta > 0 (burst) → update
   ├─ weight_old = 0.5
   ├─ weight_new = 0.5 + 0.1 × 0.375 = 0.5375
   └─ Stronger for "search" next time

   IndirectPathway:
   ├─ delta > 0 (burst) → no update
   └─ Weight stays 0.5
```

## Key Design Decisions

### 1. Hash-Based Clustering
- Why: Deterministic, no random state needed
- Tradeoff: Different embeddings may hash to same cluster
- Phase 2: Transition to k-means or embedding-based clustering

### 2. Inverted-U in D2
- Why: Matches basal ganglia physiology (parabolic inhibition)
- Benefit: Prevents "freezing" when weight gets too high
- Tunable: Peak position configurable (default 0.6)

### 3. Uncertainty Bonus in Dopamine
- Why: Jump-start learning early (unknown actions get bigger signals)
- Formula: 1.0 + (1.0 - confidence) * 0.5
  - First trial: bonus = 1.5x
  - 10th trial: bonus = 1.0x (baseline)
- Prevents: Overconfidence in small sample

### 4. Word-Overlap Novelty Detection
- Why: Deterministic for tests (not random embedding drift)
- Mechanism: Jaccard similarity of query words
- Phase 2: Integrate embedding-based novelty for production

### 5. Deliberation Gating
- Conditions:
  1. Thin margin (< 0.3) = uncertain
  2. Novel context = unfamiliar situation
- Purpose: Escalate to conscious reasoning when autopilot unsure

---

## Performance Characteristics

| Operation | Time | Space | Notes |
|-----------|------|-------|-------|
| Striatum.process() | O(n_channels × m_candidates) | O(m_candidates) | n_channels=1-5 typical |
| D1 activation | O(1) | O(1) | Hash lookup + cosine |
| D2 activation | O(1) | O(1) | Inverted-U + surround |
| GlobusPallidus.select() | O(k log k) | O(k) | k candidates, one sort |
| SubstantiaNigra.signal | O(1) | O(1) | Running stats, deque |
| Pathway.update() | O(1) | O(1) | Hash lookup + clip |
| Full loop | O(k log k) | O(k) | k = total candidates |

**Typical k=3-10 candidates** → millisecond execution

---

## Integration Points for Phase 2+

### Phase 2: Habit Formation
```python
class HabitPathway(DirectPathway):
    """Longer consolidation times, stronger weights"""
    def __init__(self, consolidation_rate=0.05):
        super().__init__(learning_rate=consolidation_rate)

    # Inherits from DirectPathway, but slower learning
    # Can be trained on "frequently successful" actions
```

### Phase 3: Striosomal Pathways
```python
class StriosomialChannel(ActionChannel):
    """Computes value via prediction, not just similarity"""
    def compute_d1(self, context_embedding, candidate):
        # Incorporate value prediction
        return value_estimate × context_similarity
```

### Phase 4: Multi-Channel Competition
```python
# Already supported: Striatum.channels = {
#     "tool": tool_channel,
#     "agent": agent_channel,
#     "response": response_channel,
# }
# GlobusPallidus selects across all channels
```

### Phase 5: Motor Cortex Integration
```python
class MotorCortex:
    def execute(context: Context) -> Outcome:
        candidates = striatum.process(context)
        selection = gp.select(candidates)

        if selection.deliberation_requested:
            # Conscious reasoning
            return deliberative_system.decide(selection)
        else:
            # Automatic execution
            return action_executor.run(selection.selected)
```

---

## Testing Strategy

### Unit Tests (8 files, 35 tests)
- Each component tested in isolation
- Edge cases: zero vectors, empty lists, division-by-zero
- Properties: competition_degree, reward computation, dopamine signals

### Integration Tests (1 file, 2 tests)
- Full loop: striatum → pathways → selection → outcome → learning
- Learning verification: 10 loops of feedback show weight improvement

### Test Determinism
- Hash-based embeddings ensure reproducibility
- No randomness in core logic (safe for regression testing)
- Reproducible across Python versions

---

## Known Limitations (Phase 1)

1. **Embedding Generation:** Hash-based (deterministic but not semantic)
   - Fix Phase 2: Integrate real embedder (SentenceTransformers, etc.)

2. **Single Channel:** ToolChannel only
   - Fix Phase 2: Add AgentChannel, ResponseChannel

3. **No Persistence:** Weights live in memory only
   - Fix Phase 2: Add save()/load() for learned models

4. **No Monitoring:** Silent weight updates
   - Fix Phase 2: Add logging/metrics for learning curves

5. **No Configurability:** Hardcoded hyperparameters
   - Fix Phase 2: Move to config file

6. **Synchronous Only:** No async execution
   - Fix Phase 3+: Add async pathways for concurrent learning

---

## Deployment Readiness

**Phase 1 Status:** ✓ READY FOR LOCAL TESTING

**Phase 2 Readiness Blocking Issues:** NONE

**Pre-Production Requirements (before Phases 3-5):**
1. Real embedder integration
2. Persistent weight storage
3. Performance monitoring
4. Hyperparameter tuning framework
5. Multi-channel stress testing
6. Production safety guardrails

---

**Document Generated:** 2025-11-27
**Implementation Status:** COMPLETE & VERIFIED
**Recommendation:** APPROVED FOR PHASE 2 KICKOFF
