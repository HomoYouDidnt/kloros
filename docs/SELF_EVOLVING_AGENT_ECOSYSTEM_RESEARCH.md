# Self-Evolving Agent Ecosystem Research

**Date**: 2025-11-24
**Purpose**: Reference knowledge for KLoROS development - comparing external self-evolving agent frameworks
**Status**: Active Research Document

---

## Executive Summary

This document catalogs external self-evolving AI agent frameworks relevant to KLoROS architecture. These projects provide comparison points, inspiration, and potential patterns for D-REAM, PHASE, SPICA, and KOSMOS development.

**Key Insight**: KLoROS already implements richer concepts (zooids, immune system, lineage tracking, bioreactor tournaments) than most external frameworks. These references validate the architectural direction while offering specific implementation patterns to consider.

---

## Tier 1: Core Self-Evolving Agent Frameworks

### 1. Agents 2.0 (aiwaves-cn/agents)

**Repository**: https://github.com/aiwaves-cn/agents

**Core Concept**: Treats agent pipelines like neural network computational graphs. Prompts and tools are "weights" that can be optimized through symbolic learning.

**Architecture**:
- **Nodes**: Individual processing units (like neural network layers)
- **Prompts/Tools**: Learnable symbolic components at each node
- **Trajectories**: Records of inputs, outputs, prompts, tool usage
- **Agent Pipeline**: Complete computational graph

**Self-Evolution Mechanism** (Three-Phase Learning):
1. **Forward Pass**: Agent executes while recording decision points
2. **Loss Computation**: Prompt-based evaluation produces "language loss"
3. **Backpropagation**: Language gradients flow backward, generating textual reflections that update prompts, tools, graph structure

**KLoROS Relevance**:
- Pattern: Treating prompts as trainable parameters
- Compare: Their "trajectory" vs our zooid fitness ledger
- Opportunity: Symbolic gradient computation for D-REAM experiments

---

### 2. EvoAgentX

**Repository**: https://github.com/EvoAgentX/EvoAgentX

**Core Concept**: Self-evolving agent ecosystem with automatic workflow construction from natural language goals.

**Architecture**:
- **WorkFlowGenerator**: Builds multi-agent workflows from goals
- **AgentManager**: Instantiates and manages agents
- **WorkFlow Orchestrator**: Executes agent pipelines
- **Automatic Evaluators**: Score agent behavior with task-specific criteria

**Key Features**:
- Modular tool integration (code interpreters, search, databases, browsers)
- Memory systems (ephemeral and persistent)
- Human-in-the-loop checkpoints
- Tool-enabled generation

**KLoROS Relevance**:
- Compare: Their "self-evolution engine" vs D-REAM's richer lifecycle/quarantine/rollback
- Pattern: How they expose evolution controls via API
- Opportunity: UI/CLI patterns for evolution management

---

### 3. Agent Lightning (Microsoft)

**Repository**: https://github.com/microsoft/agent-lightning

**Core Concept**: "The absolute trainer to light up AI agents" - zero-code-change RL training for any agent framework.

**Architecture**:
- **LightningStore**: Central hub synchronizing tasks, resources, execution traces
- **Tracer/Emitters**: Captures prompts, tool calls, rewards as structured spans
- **Algorithm Layer**: Reads spans, posts updated resources
- **Trainer**: Streams datasets, ferries resources between store and algorithm

**Training Loop**:
1. Agents run with lightweight instrumentation
2. Events flow into LightningStore as structured spans
3. Algorithm learns from spans
4. Updated resources (prompts, weights) return to inference engine
5. Continuous improvement loop

**KLoROS Relevance**:
- **HIGH VALUE**: Structural template for PHASE as RL training harness
- Pattern: Structured spans for observability
- Compare: Their resource versioning vs our niche_map.json versioning
- Opportunity: GRPO-like optimization integration

---

### 4. ART (Agent Reinforcement Trainer) - OpenPipe

**Repository**: https://github.com/OpenPipe/ART

**Core Concept**: On-the-job training for multi-step agents using GRPO algorithm.

**Architecture**:
- Client-server separation (training independent of inference)
- LoRA-based training (reduced memory, smaller checkpoints)
- OpenAI-compatible API
- W&B Serverless integration

**Training Pattern**:
- Agents execute parallel rollouts gathering trajectory data
- Code assigns rewards for performance quality
- Trajectories batched for training iterations
- System blocks inference during training, resumes with updated weights

**KLoROS Relevance**:
- Pattern: "Training mode" vs "production mode" for D-REAM
- Compare: Their trajectory structure vs our phase_fitness.jsonl
- Opportunity: Tight feedback loops without external datasets

---

### 5. Agent-R1

**Repository**: https://github.com/0russwest0/Agent-R1

**Core Concept**: End-to-end RL for tool-augmented agents with nuanced reward shaping.

**Key Abstractions**:
- **BaseTool**: Individual capabilities agents can invoke
- **BaseToolEnv**: State transition mechanisms for tool interactions

**Reward Design**:
- **Process Rewards**: Feedback for each tool call based on effectiveness
- **Outcome Rewards**: Terminal feedback on final results
- **Normalization**: Balancing process and outcome signals (PRIME-inspired)

**Supported Algorithms**: PPO, GRPO, REINFORCE++

**KLoROS Relevance**:
- **HIGH VALUE**: Reference for D-REAM reward/feedback shaping
- Pattern: Process vs outcome rewards distinction
- Compare: Multi-tool coordination training
- Opportunity: Multimodal capabilities for vision-language zooids

---

### 6. AgentK

**Repository**: https://github.com/mikekelly/AgentK

**Core Concept**: "Self-evolving AGI made of agents that collaborate and build new agents as needed."

**Kernel Agents**:
- **Hermes**: Orchestrates human interaction and task coordination
- **AgentSmith**: Architects new agents, validates functionality
- **ToolMaker**: Develops tools for agent tasks
- **WebResearcher**: Gathers online information

**Self-Evolution**:
- Agents and tools stored as Python files in dedicated directories
- AgentK writes tests validating its own behavior
- New agents validated before deployment

**KLoROS Relevance**:
- **PARALLEL UNIVERSE**: Very close to SPICA → zooid differentiation
- Compare: Their skill representation vs our genome/niche structure
- Compare: How they spawn agents vs our bioreactor tournaments
- Opportunity: Naming and public-facing narrative patterns

---

### 7. Agent0

**Repository**: https://github.com/aiming-lab/Agent0

**Core Concept**: Fully autonomous framework evolving agents via curriculum-executor co-evolution with zero external data.

**Architecture**:
- **Curriculum Agent**: Proposes increasingly challenging tasks
- **Executor Agent**: Solves tasks with tool integration
- Antagonistic objectives create "self-reinforcing cycle of improvement"

**Key Innovation**: Eliminates dependency on external data or human annotations - generates training signal through internal competition.

**Results**: +18% mathematical reasoning, +24% general reasoning on Qwen3-8B-Base

**KLoROS Relevance**:
- Compare: Their curriculum/challenger vs our bioreactor death matches
- Pattern: Antagonistic design for autonomous improvement
- Opportunity: Document how KLoROS goes further (lineage, quarantine, fitness history)

---

### 8. Seer (Moonshot AI)

**Paper**: [arXiv:2511.14617](https://arxiv.org/abs/2511.14617) (November 2025)

**Core Concept**: Online context learning system for fast synchronous LLM RL rollouts. Exploits intra-group similarities in GRPO-like training to achieve 74-97% throughput improvement.

**Problem Addressed**:
- Rollout phase consumes 63-87% of RL training iteration time
- Long-CoT requests expand from hundreds of MB to tens of GB during decoding
- Final 10% of requests consume up to 50% of execution time (long-tail effect)

**Three Key Techniques**:

1. **Divided Rollout with Global KVCache**
   - Breaks group-level scheduling into fine-grained request chunks
   - Global KVCache pool (DRAM/SSD) eliminates prefill recomputation
   - Maintains nearly constant memory footprints

2. **Context-Aware Scheduling**
   - "Speculative requests" estimate generation length early
   - Shortest-first for early long-tail detection
   - Longest-job-first for remaining requests
   - Achieves 95% of oracle (perfect info) performance

3. **Adaptive Grouped Speculative Decoding**
   - Distributed Grouped Draft Server with Compressed Suffix Trees
   - Aggregates token patterns across same-prompt requests
   - Multi-path drafting for long-tail acceleration
   - Mean acceptance length reaches 3.5+ tokens in late-stage

**Results** (32 nodes × 8 H800 GPUs):
- 74-97% throughput improvement vs synchronous veRL
- 75-93% tail latency reduction
- Tested on Moonlight 32GB, Qwen2-VL-72B, Kimi-K2 1TB

**Key Insight**: "Responses within a group tend to exhibit similar length profiles and recurring local token patterns" - this intra-group similarity enables online learning while maintaining strict on-policy guarantees.

**KLoROS Relevance**:
- **CRITICAL**: Direct application to PHASE synthetic workload testing
- Pattern: Global KVCache pool for zooid evaluation runs
- Pattern: Speculative scheduling for D-REAM batch processing
- Opportunity: Long-tail mitigation in bioreactor tournaments

---

## Tier 2: Specialized Building Blocks

### 9. Sotopia

**Repository**: https://github.com/sotopia-lab/sotopia

**Purpose**: Open-ended social learning environment for evaluating social intelligence in language agents.

**Features**:
- Agent-to-agent interactions in configurable scenarios
- Extensible and scalable multi-agent simulations
- ICLR 2024 spotlight paper
- Sampler-based interaction management

**KLoROS Relevance**:
- Pattern: Social ecology testbeds for zooid interaction
- Opportunity: Multi-agent evaluation beyond pure task success
- Future: Zooids negotiating or collaborating

---

### 10. OpenPaL

**Repository**: https://github.com/opendilab/OpenPaL

**Purpose**: Open-ended embodied agent via LLM+RL bidirectional adaptation (tested in Contra FPS environment).

**Architecture**:
- Two-stage LLM + RL coupling
- LLM fine-tuned to translate instructions into planning goals
- Goal-conditioned policy for decision-making
- Co-training for mutual adaptation

**Skill Acquisition**: Sequential development from basic locomotion to complex abilities (item collection, enemy evasion, teammate coordination).

**KLoROS Relevance**:
- Pattern: Language-policy bidirectional adaptation
- Compare: Policy-level zooids learning "how to act"
- Opportunity: Embodiment patterns for future hardware zooids

---

### 11. CALMS

**Repository**: https://github.com/mcherukara/CALMS

**Purpose**: Retrieval and tool-augmented LLM for scientific instrumentation control.

**Architecture**:
- ReAct framework with Chain-of-Thought prompting
- Materials Project API integration
- Instrument control software (spec) integration
- Domain-specific tool definitions

**Example Use Case**: User requests diffractometer movement → LLM parses query → calls Materials Project for lattice info → uses Spec software to calculate motor positions → moves instrument.

**KLoROS Relevance**:
- Pattern: Domain-specific, tool-rich agent controlling real systems
- **MIRROR**: Future KLoROS "hardware operator" zooids
- Opportunity: Safety rules for high-risk hardware actions

---

### 12. DeepAnalyze

**Repository**: https://github.com/ruc-datalab/DeepAnalyze

**Purpose**: First agentic LLM for autonomous data science - 8B parameters outperforming workflow-based agents on proprietary LLMs.

**Training Approach**:
- Curriculum-based agentic training emulating human data scientist learning
- Data-grounded trajectory synthesis
- Progressive capability integration

**Pipeline**: Data preparation → analysis → modeling → visualization → report generation

**KLoROS Relevance**:
- Pattern: What a "data scientist zooid" might look like
- Compare: Their curriculum training vs our PHASE heuristics
- Opportunity: Specialist zooid archetypes

---

## Tier 3: Meta-Resources and Surveys

### 13. Awesome-Self-Evolving-Agents

**Repository**: https://github.com/EvoAgentX/Awesome-Self-Evolving-Agents

**Survey Scope**: Comprehensive taxonomy of self-evolving agents (2023-2025).

**Categories**:
- **Single-Agent**: LLM behavior, prompt, memory, tool, unified optimization
- **Multi-Agent**: Automatic construction, MAS optimization, workflow orchestration
- **Domain-Specific**: Specialized applications

**Key Frameworks Referenced**:
- DSPy (ICLR'24): Compiling declarative LM calls into pipelines
- MetaGPT (ICLR'24): Multi-agent collaborative programming
- AutoGen (COLM'24): Multi-agent conversation systems

**KLoROS Relevance**:
- Validate: KLoROS touches all "expected" capabilities + extras
- Pattern: How field carves up the design space
- Opportunity: Positioning documentation

---

### 14. Awesome-Open-Ended

**Repository**: https://github.com/jennyzzt/awesome-open-ended

**Core Principle**: "Greatness cannot be planned" - open-ended systems invent ever-more complex tasks without predetermined endpoints.

**Key Algorithms**:
- **POET** (Paired Open-Ended Trailblazer): Environment generators and agent solvers co-evolve
- **Quality-Diversity**: Maintaining diverse solution populations
- **Novelty Search**: Valuing behavioral diversity over fitness

**Concepts**:
- Intrinsic motivation driving exploration
- Self-improvement enabling capability enhancement
- Tensions between control and creativity

**KLoROS Relevance**:
- **HIGH VALUE**: Conceptual overlap with never-converging D-REAM goals
- Pattern: POET for PHASE tournament strategies
- Compare: Quality-Diversity vs our lineage-based diversity

---

### 15. Awesome-RL-for-Agents

**Repository**: https://github.com/Necolizer/awesome-rl-for-agents

**Scope**: RL pipelines, frameworks, and toolkits for LLM/MLLM agents.

**Key Frameworks**:
- **DeepSeek-R1**: Incentivizing reasoning via RL
- **DAPO**: Large-scale LLM RL training
- **veRL**: Volcano Engine's LLM RL framework
- **SkyRL-v0**: Long-horizon agents in real-world settings

**Environments**:
- **OSWorld**: Open-ended real-world computer tasks
- **BrowseComp**: Web-browsing agent evaluation
- **Computer Agent Arena**: Community evaluation platform

**KLoROS Relevance**:
- One-stop shop for RL training patterns
- Reward shaping ideas, rollout tricks
- Environment design for PHASE domains

---

### 16. Self-Evolving-Agents Survey

**Repository**: https://github.com/CharlesQ9/Self-Evolving-Agents

**Framework**: What/When/How/Where of agent evolution.

**Memory-Augmented Approaches**:
- **Mem0**: Production-ready agents with scalable long-term memory
- **MemInsight**: Autonomous memory augmentation
- **Agent Workflow Memory**: Structured retention of interaction patterns

**Reflective Mechanisms**:
- **Reflexion**: Verbal reinforcement learning for iterative refinement
- **Self-Refine**: Iterative refinement with self-feedback
- **AdaPlanner**: Adaptive planning from feedback

**Temporal Dimensions**:
- Intra-test evolution (within single tasks)
- Inter-test evolution (across multiple instances)

**KLoROS Relevance**:
- Cross-check introspection + memory + capability registry ideas
- Pattern: Temporal evolution dimensions
- Compare: Their reflection vs our curiosity/reasoning systems

---

## Tier 4: Niche Inspiration

### 17. Awesome-Tool-LLM

**Repository**: https://github.com/zorazrw/awesome-tool-llm

**Key Benchmarks**:
- **API-Bank**: Comprehensive tool-augmented LLM benchmark
- **ToolLLM**: Master 16000+ real-world APIs
- **MetaTool**: Deciding whether/which tools to use
- **TaskBench**: Task automation benchmarking
- **ToolQA**: LLM question answering with external tools

**Safety Benchmarks**:
- **RoTBench**: Robustness in tool learning
- **R-Judge**: Safety risk awareness
- **AgentDojo**: Prompt injection attacks
- **ToolSword**: Safety issues in tool learning

**KLoROS Relevance**:
- Pattern: Tool-learning evaluation design
- Opportunity: Safety benchmarks for zooid tool use

---

### 18. CoALA / Awesome-Language-Agents

**Repository**: https://github.com/ysymyth/awesome-language-agents

**Framework**: Cognitive Architectures for Language Agents (CoALA).

**Action Space**:
- **External**: Interact with external environments (grounding)
- **Internal**: Interact with internal memories (reasoning, retrieval, learning)

**Memory Types**:
- Short-term working memory
- Long-term episodic (experience)
- Long-term semantic (knowledge)
- Long-term procedural (code/LLM)

**Notable Agents**:
- **Voyager**: Open-ended embodied Minecraft agent with procedural memory
- **Reflexion**: Verbal reinforcement learning
- **SwiftSage, Tree of Thoughts, InterCode, Mind2Web, RestGPT**

**KLoROS Relevance**:
- Pattern: Memory type classification for zooid design
- Compare: Their procedural memory vs our zooid genomes
- Inspiration: Specific reasoning patterns (ToT, etc.)

---

## Agentic Parallelism Checklist (vs KLoROS)

Comparison against the [14 Core Patterns of Agentic Parallelism](https://github.com/FareedKhan-dev/agentic-parallelism):

| # | Pattern | KLoROS Status | Implementation |
|---|---------|---------------|----------------|
| 1 | **Parallel Tool Use** | ✅ FULL | UMN signals let zooids call multiple tools simultaneously; `rag/hybrid_retriever.py` |
| 2 | **Parallel Hypothesis** | ✅ FULL | Investigation runs **4 concurrent** (`max_concurrent_investigations=4`); `tumix/committee_runner.py` |
| 3 | **Parallel Evaluation** | ✅ FULL | PHASE runs multiple candidates through fitness evaluation; `tumix/aggregators.py` |
| 4 | **Speculative Execution** | ✅ FULL | `orchestration/speculative_executor.py` - Background prefetch with prediction, LRU cache, Prometheus metrics |
| 5 | **Hierarchical Teams** | ✅ FULL | Orchestrator → zooids → sub-agents (SPICA); `agentflow/runner.py` |
| 6 | **Competitive Ensembles** | ✅ FULL+ | Bioreactor tournaments (richer than standard: lineage, quarantine, rollback) |
| 7 | **Agent Assembly Line** | ✅ FULL | Voice pipeline: Audio→STT→Intent→Emotion→LLM→TTS; `tournament_consumer_daemon.py` |
| 8 | **Decentralized Blackboard** | ✅ FULL+ | UMN pub/sub is exactly this pattern - ZMQ chemical signals |
| 9 | **Redundant Execution** | ✅ FULL | `orchestration/redundant_executor.py` - Retry with exponential backoff + fallback chain, async support |
| 10 | **Parallel Query Expansion** | ✅ FULL | `rag/query_expander.py` - Hybrid rule-based + LLM expansion with KLoROS-specific terms |
| 11 | **Sharded Retrieval** | ✅ FULL | `rag/sharded_retriever.py` - Domain-based routing with parallel ThreadPoolExecutor + RRF fusion |
| 12 | **Hybrid Search Fusion** | ✅ FULL | `bm25_store.py` (inverted index + IDF) + `hybrid_retriever.py` + `rrf_fusion.py` + `reranker.py` |
| 13 | **Context Pre-processing** | ✅ FULL | `rag/ingest/cleaner.py` + `chunker.py` - content cleaning, intelligent chunking |
| 14 | **Multi-Hop Retrieval** | ✅ FULL | `rag/multihop_retriever.py` - Query decomposition with parallel sub-queries + result synthesis |

**Score: 14/14 Full ✅ (Implemented 2024-11-24)**

### KLoROS Unique Additions (Beyond the 14)

| Pattern | KLoROS Implementation | Notes |
|---------|----------------------|-------|
| **Evolutionary Pressure Model** | `dream/bioreactor.py` | Niches compute pressure from failure rates + incident volume |
| **Confidence-Gated Fitness Fusion** | `dream/bioreactor.py:160-216` | MIN_PROD_CASES/MIN_PHASE_CASES gates, exponential time decay |
| **Chemical Signal Communication** | `umn_bus_v2.py` | Q_CURIOSITY, synthesis channels - biological signaling metaphor |
| **Committee Judge LLM** | `tumix/judge.py` | Real LLM evaluates committee outputs on correctness/completeness/clarity |
| **Bracket Tournament Parallelization** | `evaluators/bracket_tournament.py` | 8→4→2→1 with ThreadPoolExecutor (20min→7.5sec) |

---

## Synthesis: How KLoROS Compares

### KLoROS Unique Strengths (Not Found Elsewhere)

| Feature | KLoROS Implementation | External Equivalent |
|---------|----------------------|---------------------|
| **Zooid Ecology** | Organisms with lifecycle, lineage, genomes | None - most use static agent definitions |
| **Bioreactor Tournaments** | Death match evolution with quarantine | Agent0 has curriculum competition, but no quarantine/rollback |
| **PHASE Temporal Dilation** | 100-hour synthetic workload testing | Agent Lightning has spans, but not time-dilated testing |
| **Immune System (Prod Guard)** | N failures in M minutes → quarantine | None have production-aware safety gates |
| **Niche Ecology** | Ecosystem/niche/zooid hierarchy with DORMANT→ACTIVE gating | EvoAgentX has workflows, but not ecological classification |
| **SPICA Subagent Production** | Iteratively-trained specialist agents via nanochat | Most use static agent definitions; none have hackable LLM subagent factories |

### Patterns to Consider Adopting

| Pattern | Source | Potential KLoROS Application |
|---------|--------|------------------------------|
| Symbolic gradients | Agents 2.0 | D-REAM prompt optimization |
| Process + Outcome rewards | Agent-R1 | PHASE fitness scoring refinement |
| LightningStore spans | Agent Lightning | Observability for PHASE runs |
| Curriculum-executor antagonism | Agent0 | Bioreactor challenger generation |
| Bidirectional LLM-policy adaptation | OpenPaL | Language-behavior zooid co-evolution |
| Quality-Diversity | POET/Open-Ended | Lineage diversity maintenance |
| Divided Rollout + Global KVCache | Seer | PHASE batch processing optimization |
| Context-Aware Scheduling | Seer | Long-tail mitigation in bioreactor |
| Grouped Speculative Decoding | Seer | Accelerate similar-prompt zooid evaluations |

### Validation Points

External research validates KLoROS architectural decisions:
1. **Self-evolution is the future** - Major labs (Microsoft, OpenPipe) investing heavily
2. **Lifecycle gating matters** - Multiple frameworks struggling with uncontrolled proliferation
3. **Memory/reflection is essential** - Every survey emphasizes memory-augmented abilities
4. **Open-endedness is hard** - Few achieve truly never-converging evolution (KLoROS goal)

---

## Action Items for KLoROS Development

### Immediate Reference Value
1. **Seer** → PHASE batch optimization (74-97% throughput gains possible)
2. **Agent Lightning** → PHASE observability patterns
3. **Agent-R1** → D-REAM reward shaping
4. **Awesome-Open-Ended** → POET tournament strategies

### Medium-Term Consideration
1. **AgentK** → Public-facing narrative and naming
2. **DeepAnalyze** → Specialist zooid archetypes
3. **CALMS** → Hardware operator zooid safety patterns

### Long-Term Inspiration
1. **Sotopia** → Multi-zooid social dynamics
2. **OpenPaL** → Embodied zooid co-training
3. **Agent0** → Document KLoROS advantages for research positioning

---

## References

### Primary Repositories
- Agents 2.0: https://github.com/aiwaves-cn/agents
- EvoAgentX: https://github.com/EvoAgentX/EvoAgentX
- Agent Lightning: https://github.com/microsoft/agent-lightning
- ART: https://github.com/OpenPipe/ART
- Agent-R1: https://github.com/0russwest0/Agent-R1
- AgentK: https://github.com/mikekelly/AgentK
- Agent0: https://github.com/aiming-lab/Agent0
- Seer: https://arxiv.org/abs/2511.14617 (Moonshot AI, no public repo yet)
- Sotopia: https://github.com/sotopia-lab/sotopia
- OpenPaL: https://github.com/opendilab/OpenPaL
- CALMS: https://github.com/mcherukara/CALMS
- DeepAnalyze: https://github.com/ruc-datalab/DeepAnalyze

### Survey/Meta Repositories
- Awesome-Self-Evolving-Agents: https://github.com/EvoAgentX/Awesome-Self-Evolving-Agents
- Awesome-Open-Ended: https://github.com/jennyzzt/awesome-open-ended
- Awesome-RL-for-Agents: https://github.com/Necolizer/awesome-rl-for-agents
- Self-Evolving-Agents: https://github.com/CharlesQ9/Self-Evolving-Agents
- Awesome-Tool-LLM: https://github.com/zorazrw/awesome-tool-llm
- Awesome-Language-Agents (CoALA): https://github.com/ysymyth/awesome-language-agents
- Agentic Parallelism (14 Patterns): https://github.com/FareedKhan-dev/agentic-parallelism

---

**Document Version**: 1.0
**Created**: 2025-11-24
**For**: KOSMOS Knowledge Base / KLoROS Reference
