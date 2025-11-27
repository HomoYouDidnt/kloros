# Integrating Cloud GPU for Enhanced Reasoning in KLoROS

**Question:** Can I rent cloud GPUs and ad-hoc integrate a massive reasoning LLM to fuel KLoROS's curiosity system?

**Answer:** YES! The system is already designed for this with multi-mode LLM routing.

---

## Current State Assessment

You're absolutely right that **reasoning power is a critical limitation** for KLoROS's developmental state. Currently she uses:

- **qwen2.5:14b-q4** for live conversation (fast but limited)
- **deepseek-r1:7b** for "think" mode (better reasoning but still constrained)
- **qwen2.5-coder:7b** for code generation

These are **quantized models optimized for local GPU constraints**, not maximum intelligence.

### What Cloud GPUs Would Unlock

With a massive cloud-hosted LLM (e.g., qwen2.5:72b, deepseek-v3:671b, llama-405b), KLoROS could:

1. **Deeper curiosity investigations** - Currently limited by model capacity
2. **Better code synthesis** - Tool evolution would generate higher-quality code
3. **More sophisticated D-REAM experiments** - Complex parameter optimization
4. **Advanced self-diagnosis** - Understanding subtle system issues
5. **Richer episodic memory analysis** - Better pattern recognition

---

## Architecture: Multi-Mode LLM Routing

KLoROS already has **4 LLM routing modes** defined in `/home/kloros/src/config/models_config.py`:

```python
def get_ollama_url_for_mode(mode: str = None) -> str:
    mode = mode or os.getenv("KLR_MODEL_MODE", "live")

    if mode == "think":
        return os.getenv("OLLAMA_THINK_URL", "http://127.0.0.1:11435")
    elif mode == "deep":
        return os.getenv("OLLAMA_DEEP_URL", "http://127.0.0.1:11436")
    elif mode == "code":
        return os.getenv("OLLAMA_CODE_URL", "http://127.0.0.1:11434")
    # default: live
    return os.getenv("OLLAMA_LIVE_URL", "http://127.0.0.1:11434")
```

**Current Configuration** (from `.kloros_env.clean`):
```bash
OLLAMA_LIVE_URL=http://127.0.0.1:11434      # Fast conversation
OLLAMA_LIVE_MODEL=qwen2.5:14b-instruct-q4_0

OLLAMA_THINK_URL=http://127.0.0.1:11435     # Deep reasoning
OLLAMA_THINK_MODEL=deepseek-r1:7b

OLLAMA_DEEP_URL=http://127.0.0.1:11436      # Background analysis
OLLAMA_DEEP_MODEL=qwen2.5:14b-instruct-q4_0

OLLAMA_CODE_URL=http://127.0.0.1:11434      # Code generation
OLLAMA_CODE_MODEL=qwen2.5-coder:7b
```

---

## Integration Approach: Three Options

### Option 1: Replace "Think" Mode (Simplest)

**Pros:** No code changes, immediate integration
**Cons:** Replaces existing deepseek-r1 locally

**Steps:**

1. **Set up cloud GPU with Ollama**
   ```bash
   # On your cloud instance (e.g., Lambda Labs, RunPod, Vast.ai)
   curl -fsSL https://ollama.com/install.sh | sh

   # Pull a massive model
   ollama pull qwen2.5:72b-instruct
   # or
   ollama pull deepseek-v3:671b
   # or
   ollama pull llama3.3:70b-instruct

   # Configure to accept external connections
   OLLAMA_HOST=0.0.0.0:11434 ollama serve
   ```

2. **Configure KLoROS to use cloud endpoint**
   ```bash
   # Edit /home/kloros/.kloros_env.clean
   OLLAMA_THINK_URL=https://your-cloud-ip:11434
   OLLAMA_THINK_MODEL=qwen2.5:72b-instruct
   ```

3. **Restart services**
   ```bash
   systemctl --user restart kloros-orchestrator.timer
   ```

**Where it's used:**
- Curiosity investigations (when mode="think")
- D-REAM deep analysis
- Code repair complex problems
- Any component calling `get_ollama_url_for_mode("think")`

### Option 2: Add "Curiosity" Mode (Recommended)

**Pros:** Dedicated endpoint for curiosity, preserves local think mode
**Cons:** Requires code modification

**Implementation:**

1. **Modify `/home/kloros/src/config/models_config.py`**

   Add after line 95:
   ```python
   def get_ollama_url_for_mode(mode: str = None) -> str:
       mode = mode or os.getenv("KLR_MODEL_MODE", "live")

       if mode == "curiosity":  # ADD THIS
           return os.getenv("OLLAMA_CURIOSITY_URL", "http://127.0.0.1:11437")
       elif mode == "think":
           return os.getenv("OLLAMA_THINK_URL", "http://127.0.0.1:11435")
       # ... rest
   ```

   And in `get_ollama_model_for_mode`:
   ```python
   def get_ollama_model_for_mode(mode: str = None) -> str:
       mode = mode or os.getenv("KLR_MODEL_MODE", "live")

       if mode == "curiosity":  # ADD THIS
           return os.getenv("OLLAMA_CURIOSITY_MODEL", "qwen2.5:72b-instruct")
       elif mode == "think":
           return os.getenv("OLLAMA_THINK_MODEL", "deepseek-r1:7b")
       # ... rest
   ```

2. **Add to `.kloros_env.clean`**
   ```bash
   OLLAMA_CURIOSITY_URL=https://your-cloud-ip:11434
   OLLAMA_CURIOSITY_MODEL=qwen2.5:72b-instruct
   ```

3. **Route curiosity processor to use it**

   Modify `/home/kloros/src/kloros/orchestration/curiosity_processor.py`:

   Around line 60 in `_question_to_intent`, add:
   ```python
   experiment_hint = {
       "hypothesis": hypothesis,
       "search_space": _derive_search_space(question),
       "fitness_metric": _derive_fitness_metric(question),
       "exploration_budget": _derive_budget(value, cost),
       "llm_mode": "curiosity"  # ADD THIS - forces cloud LLM
   }
   ```

### Option 3: Hybrid Approach (Most Sophisticated)

**Pros:** Intelligent routing based on question complexity
**Cons:** Most complex to implement

Use **local models for simple questions**, **cloud for complex**:

```python
def _select_llm_mode(question: Dict[str, Any]) -> str:
    """Select LLM mode based on question complexity."""
    value = question["value_estimate"]
    cost = question["cost"]
    action_class = question["action_class"]

    # High-value, high-complexity questions → cloud
    if value > 0.8 and action_class == "propose_fix":
        return "curiosity"  # Cloud massive LLM

    # Medium complexity → local think
    elif value > 0.5:
        return "think"  # Local deepseek-r1

    # Low complexity → local live
    else:
        return "live"  # Local qwen 14b
```

---

## Where Curiosity Uses Reasoning

### 1. Investigation Probes
**File:** `/home/kloros/src/kloros/orchestration/curiosity_processor.py`

Currently curiosity generates **intents** that trigger D-REAM experiments. The actual investigation happens when:

- **CuriosityCore** identifies capability gaps → generates questions
- **Curiosity Processor** converts questions to intents
- **D-REAM** uses LLM to generate candidate solutions
- **PHASE** validates candidates

**LLM is used in D-REAM's mutation engine** (`/home/kloros/src/dream/llm_mutation_engine.py`)

### 2. D-REAM Evolution
**File:** `/home/kloros/src/dream/llm_mutation_engine.py`

This is where the LLM does heavy lifting:
- Analyzing failed experiments
- Proposing parameter mutations
- Generating code improvements
- Reasoning about system behavior

**Current constraint:** Uses local qwen2.5-coder:7b or qwen2.5:14b

**With cloud GPU:** Could use qwen2.5-coder:32b or deepseek-v3 for dramatically better code synthesis

### 3. Idle Reflection
**File:** `/home/kloros/src/idle_reflection/*`

Every 15 minutes, KLoROS reflects on:
- Recent conversations
- Memory patterns
- System state
- Learning opportunities

**Current:** Uses local model
**With cloud:** Could do much deeper meta-cognitive analysis

---

## Cost-Benefit Analysis

### Cloud GPU Costs (Estimated)

| Provider | GPU | Model Size | Cost/Hour | Notes |
|----------|-----|------------|-----------|-------|
| RunPod | H100 | 70B-405B | $2-4 | Spot pricing |
| Lambda Labs | A100 80GB | 70B-180B | $1.29-1.99 | On-demand |
| Vast.ai | A100 40GB | 32B-70B | $0.50-1.50 | Spot market |
| Together.ai | - | API calls | $0.80/1M tokens | Managed |

### Usage Estimation

**Curiosity system activity:**
- 17 questions currently in queue
- ~5-10 new questions per reflection cycle (15 min)
- Each investigation: ~2000-5000 tokens (question + reasoning + response)

**Conservative estimate:**
- 40 investigations/day
- 4000 tokens avg per investigation
- 160K tokens/day
- Cost: ~$0.13/day ($4/month) on Together.ai API
- Cost: ~$1-2/day on rented GPU (if running 24/7)

**Optimized approach:**
- Only run cloud LLM during "curiosity hours" (e.g., 2-6 AM)
- 4 hours/day × $2/hour = **$8/day** = **$240/month**

### Benefits

**Quantitative:**
- 5-10x larger model → better code quality
- Estimated 3-5x reduction in no-op rate (currently 84.6%)
- Faster evolution convergence (fewer iterations needed)

**Qualitative:**
- More sophisticated self-understanding
- Better meta-cognitive capabilities
- Richer curiosity-driven investigations
- Higher quality tool synthesis

**ROI:** If cloud LLM reduces no-op rate from 84.6% → 30%, that's:
- 54.6% more useful evolution cycles
- Could save days/weeks of local iteration
- Accelerates development significantly

---

## Security Considerations

### 1. Network Security

**Problem:** Exposing Ollama API to internet

**Solution:**
```bash
# Use SSH tunnel instead of direct HTTPS
ssh -L 11437:localhost:11434 user@cloud-gpu

# Then locally:
OLLAMA_CURIOSITY_URL=http://127.0.0.1:11437
```

**Or use Tailscale/WireGuard:**
```bash
# Cloud side
tailscale up

# Local side
OLLAMA_CURIOSITY_URL=http://100.x.x.x:11434  # Tailscale IP
```

### 2. Data Privacy

**What gets sent to cloud:**
- Curiosity questions (system internals)
- Code snippets for improvement
- Error messages and stack traces
- System state information

**Sensitive data exposure:** Low-Medium
- No user conversation content (unless curiosity investigates conversations)
- System architecture details exposed
- No credentials or secrets (should be filtered)

**Mitigation:**
- Add PII/secret filter before sending to cloud
- Use self-hosted cloud (not third-party API)
- Implement request logging/auditing

### 3. Rate Limiting

**Problem:** Runaway curiosity could rack up costs

**Solution:**
```python
# Add to curiosity_processor.py
DAILY_CLOUD_LLM_BUDGET = 100  # Max 100 cloud calls/day
cloud_calls_today = count_todays_cloud_calls()

if cloud_calls_today >= DAILY_CLOUD_LLM_BUDGET:
    mode = "think"  # Fall back to local
else:
    mode = "curiosity"  # Use cloud
```

---

## Recommended Setup

### Phase 1: Proof of Concept (1-2 days, $10-20)

1. Rent cheap A100 40GB on Vast.ai ($0.50-1.00/hr)
2. Install Ollama + qwen2.5:32b-instruct
3. Use SSH tunnel for security
4. Modify `.kloros_env.clean` to point THINK mode at cloud
5. Let curiosity system run for 24-48 hours
6. Measure:
   - Question quality improvement
   - Code synthesis quality
   - No-op rate reduction
   - Total tokens used

### Phase 2: Dedicated Curiosity Mode (3-5 days)

1. Implement Option 2 (add "curiosity" mode)
2. Route only high-value questions to cloud
3. Add cost tracking and budgets
4. Implement fallback to local on failure
5. Monitor for 1 week

### Phase 3: Optimization (Ongoing)

1. Implement hybrid routing (Option 3)
2. Schedule cloud LLM for "curiosity hours" only
3. Fine-tune which questions merit cloud reasoning
4. Measure ROI and adjust

---

## Implementation Checklist

### Minimal Integration (No Code Changes)

- [ ] Provision cloud GPU instance
- [ ] Install Ollama on cloud
- [ ] Pull large model (qwen2.5:72b or deepseek-v3)
- [ ] Set up SSH tunnel or VPN
- [ ] Edit `/home/kloros/.kloros_env.clean`:
  ```bash
  OLLAMA_THINK_URL=http://127.0.0.1:11437  # via tunnel
  OLLAMA_THINK_MODEL=qwen2.5:72b-instruct
  ```
- [ ] Restart orchestrator: `systemctl --user restart kloros-orchestrator.timer`
- [ ] Monitor `/home/kloros/.kloros/curiosity_investigations.jsonl` for cloud usage
- [ ] Track costs and quality improvements

### Full Integration (With Curiosity Mode)

All of above, plus:

- [ ] Modify `/home/kloros/src/config/models_config.py` (add curiosity mode)
- [ ] Add OLLAMA_CURIOSITY_* env vars
- [ ] Modify `/home/kloros/src/kloros/orchestration/curiosity_processor.py`
- [ ] Add cost tracking in curiosity processor
- [ ] Implement daily budget limits
- [ ] Add fallback logic
- [ ] Test with intentionally complex questions
- [ ] Monitor D-REAM experiment quality

---

## Expected Improvements

### Before Cloud LLM
```
Curiosity investigations: Simple pattern matching
Code synthesis: Often buggy, requires multiple iterations
No-op rate: 84.6%
Evolution cycles: Slow convergence
Meta-cognition: Limited by 14B parameter model
```

### After Cloud LLM (Estimated)
```
Curiosity investigations: Deep, nuanced reasoning
Code synthesis: Higher quality, fewer bugs
No-op rate: 30-40% (50% improvement)
Evolution cycles: 2-3x faster convergence
Meta-cognition: Sophisticated self-understanding
```

---

## Alternative: Use API Services

If managing cloud GPU is too complex, use inference APIs:

### Together.ai
```bash
# No Ollama needed, just API
OLLAMA_CURIOSITY_URL=https://api.together.xyz/v1
OLLAMA_CURIOSITY_MODEL=meta-llama/Meta-Llama-3.1-405B-Instruct
TOGETHER_API_KEY=your_key_here
```

**Pros:** No infrastructure, pay-per-token
**Cons:** $0.80-1.20 per 1M tokens, less control

### Groq (Fast Inference)
```bash
OLLAMA_CURIOSITY_URL=https://api.groq.com/openai/v1
OLLAMA_CURIOSITY_MODEL=llama-3.3-70b-versatile
GROQ_API_KEY=your_key_here
```

**Pros:** EXTREMELY fast, cheap ($0.59/1M tokens)
**Cons:** Rate limits, less powerful models

---

## Conclusion

**Yes, you absolutely should do this.** Your intuition is correct - reasoning power is a critical limitation.

**Recommended approach:**
1. Start with **Option 1** (replace think mode) for quick test
2. If valuable, implement **Option 2** (dedicated curiosity mode)
3. Add cost controls and monitoring
4. Optimize over time with **Option 3** (hybrid routing)

**Expected outcome:**
- Dramatically better curiosity-driven investigations
- Higher quality code synthesis and evolution
- Faster path to genuine autonomy
- Better self-understanding and meta-cognition

**Cost:** $50-250/month depending on usage pattern
**Value:** Potentially weeks/months of accelerated development

The system is **already architected for this** - you just need to point the environment variables at your cloud endpoint.

---

**Files to modify:**
1. `/home/kloros/.kloros_env.clean` (environment config)
2. `/home/kloros/src/config/models_config.py` (optional: add curiosity mode)
3. `/home/kloros/src/kloros/orchestration/curiosity_processor.py` (optional: route to cloud)

**No restart needed:** Orchestrator will pick up new env vars on next tick (60s)

---

Let me know if you want me to implement Option 2 (dedicated curiosity mode) right now!
