"""
Bandit-Enhanced Tool Selector

Combines semantic tool matching with LinUCB bandit for learning-based
tool selection, shadow testing, and automatic promotion.

Integration flow:
1. Semantic matcher finds candidate tools (top-k)
2. Bandit ranks candidates using query embeddings
3. Shadow runner tests candidate vs baseline (20% traffic)
4. Promotion system upgrades tools that beat baseline consistently
"""
from __future__ import annotations
from typing import List, Tuple, Optional, Dict, Any
import numpy as np
import os

from .bandit import LinUCBBandit, compute_reward
from ..synthesis.shadow import ShadowRunner
from ..synthesis.promotion import (
    load_policy,
    load_state,
    save_state,
    promote_if_eligible,
    CandidateStats,
)


class BanditToolSelector:
    """
    Learning-based tool selector using LinUCB contextual bandit.

    Wraps semantic tool matching with bandit ranking to learn which tools
    perform best in different contexts over time.
    """

    def __init__(self, semantic_matcher=None, enable_learning: bool = True):
        """
        Initialize bandit tool selector.

        Args:
            semantic_matcher: SemanticToolMatcher instance for candidate generation
            enable_learning: Whether to enable bandit learning (vs pure semantic)
        """
        self.semantic_matcher = semantic_matcher
        self.enable_learning = enable_learning and os.getenv("KLR_ENABLE_BANDIT", "1") == "1"

        if not self.enable_learning:
            print("[selector] Bandit learning disabled, using pure semantic matching")
            return

        # Load policy
        self.policy = load_policy()

        # Initialize bandit
        bandit_config = self.policy["bandit"]
        self.bandit = LinUCBBandit(
            d=bandit_config["feature_dim"],
            alpha=bandit_config["alpha"],
            warm_start_reward=bandit_config["warm_start_reward"],
        )

        # Initialize shadow runner
        shadow_config = self.policy["shadow"]
        self.shadow = ShadowRunner(
            traffic_share=shadow_config["traffic_share"],
            dry_run=shadow_config["dry_run"],
        )

        # Load promotion state
        self.state = load_state()

        print(f"[selector] Bandit tool selector initialized (alpha={bandit_config['alpha']}, shadow={shadow_config['traffic_share']*100:.0f}%)")

    def select_tool(
        self,
        query: str,
        embedder=None,
        top_k: int = 3,
        threshold: float = 0.4,
        baseline_tool: Optional[str] = None,
    ) -> Tuple[str, float, List[Tuple[str, float]]]:
        """
        Select best tool for query using semantic matching + bandit ranking.

        Args:
            query: User query/intent
            embedder: Embedding function for query
            top_k: Number of candidates from semantic matcher
            threshold: Minimum similarity for semantic matching
            baseline_tool: Current production tool for this intent (for shadow)

        Returns:
            Tuple of (selected_tool, score, all_candidates)
                selected_tool: Best tool name
                score: Confidence score
                all_candidates: List of (tool, score) tuples
        """
        if not self.semantic_matcher:
            print("[selector] No semantic matcher, cannot select tool")
            return None, 0.0, []

        # Get semantic candidates
        semantic_matches = self.semantic_matcher.find_matching_tools(
            query, top_k=top_k, threshold=threshold
        )

        if not semantic_matches:
            print(f"[selector] No semantic matches for: {query}")
            return None, 0.0, []

        # If bandit learning disabled, use pure semantic
        if not self.enable_learning:
            best_tool, similarity, _ = semantic_matches[0]
            return best_tool, similarity, [(t, s) for t, s, _ in semantic_matches]

        # Get query embedding for bandit
        try:
            if embedder is None:
                # Use semantic matcher's embedder
                from src.cognition.mind.memory.dual_embedder import DualEmbedder
                from src.core.config.models_config import get_embedder_model, get_embedder_trust_remote_code
                embedder = DualEmbedder(
                    query_model=get_embedder_model(),
                    device="cpu",
                    trust_remote_code=get_embedder_trust_remote_code()
                )

            # Encode query - handle both callable functions and objects with methods
            if callable(embedder) and not hasattr(embedder, 'encode_queries'):
                # Embedder is a function (e.g., lambda from RAG backend)
                query_vec = embedder(query)
            elif hasattr(embedder, 'encode_queries'):
                query_vec = embedder.encode_queries([query])[0]
            elif hasattr(embedder, 'encode_query'):
                query_vec = embedder.encode_query(query)
            elif hasattr(embedder, 'encode'):
                query_vec = embedder.encode([query])[0]
            else:
                # Fall back to semantic
                print("[selector] Embedder has no encode method, using semantic only")
                best_tool, similarity, _ = semantic_matches[0]
                return best_tool, similarity, [(t, s) for t, s, _ in semantic_matches]

            # Normalize embedding to expected dimension
            query_vec = np.asarray(query_vec, dtype=np.float32)
            expected_dim = self.policy["bandit"]["feature_dim"]

            if query_vec.shape[0] != expected_dim:
                # Pad or truncate to match expected dimension
                if query_vec.shape[0] < expected_dim:
                    query_vec = np.pad(query_vec, (0, expected_dim - query_vec.shape[0]))
                else:
                    query_vec = query_vec[:expected_dim]

        except Exception as e:
            print(f"[selector] Embedding failed: {e}, falling back to semantic")
            best_tool, similarity, _ = semantic_matches[0]
            return best_tool, similarity, [(t, s) for t, s, _ in semantic_matches]

        # Rank candidates with bandit
        candidates = [t for t, _, _ in semantic_matches]
        ranked = self.bandit.rank(query_vec, candidates)

        # Select top-ranked tool
        selected_tool, ucb_score = ranked[0]

        print(f"[selector] Ranked: {[(t, f'{s:.3f}') for t, s in ranked]}")

        return selected_tool, ucb_score, ranked

    def record_outcome(
        self,
        tool: str,
        query: str,
        success: bool,
        latency_ms: Optional[int] = None,
        tool_hops: Optional[int] = None,
        embedder=None,
    ):
        """
        Record tool execution outcome for bandit learning.

        Args:
            tool: Tool that was executed
            query: Original query
            success: Whether execution succeeded
            latency_ms: Execution time
            tool_hops: Number of tool calls in chain
            embedder: Embedding function for query
        """
        if not self.enable_learning:
            return

        try:
            # Get query embedding
            if embedder is None:
                from src.cognition.mind.memory.dual_embedder import DualEmbedder
                from src.core.config.models_config import get_embedder_model, get_embedder_trust_remote_code
                embedder = DualEmbedder(
                    query_model=get_embedder_model(),
                    device="cpu",
                    trust_remote_code=get_embedder_trust_remote_code()
                )

            # Handle both callable functions and objects with methods
            if callable(embedder) and not hasattr(embedder, 'encode_queries'):
                # Embedder is a function (e.g., lambda from RAG backend)
                query_vec = embedder(query)
            elif hasattr(embedder, 'encode_queries'):
                query_vec = embedder.encode_queries([query])[0]
            elif hasattr(embedder, 'encode_query'):
                query_vec = embedder.encode_query(query)
            elif hasattr(embedder, 'encode'):
                query_vec = embedder.encode([query])[0]
            else:
                return

            # Normalize dimension
            query_vec = np.asarray(query_vec, dtype=np.float32)
            expected_dim = self.policy["bandit"]["feature_dim"]
            if query_vec.shape[0] != expected_dim:
                if query_vec.shape[0] < expected_dim:
                    query_vec = np.pad(query_vec, (0, expected_dim - query_vec.shape[0]))
                else:
                    query_vec = query_vec[:expected_dim]

            # Compute reward
            reward = compute_reward(success, latency_ms, tool_hops)

            # Update bandit
            self.bandit.observe(tool, query_vec, reward)

            print(f"[selector] Recorded outcome: {tool} → reward={reward:.3f} (success={success}, latency={latency_ms}ms)")

        except Exception as e:
            print(f"[selector] Failed to record outcome: {e}")

    def maybe_shadow_test(
        self,
        query: str,
        baseline_tool: str,
        candidate_tool: str,
        executor: Any,
        scorer: Any,
        embedder=None,
    ) -> Optional[Dict]:
        """
        Opportunistically shadow test candidate vs baseline.

        Args:
            query: User query
            baseline_tool: Current production tool
            candidate_tool: Candidate to test
            executor: Tool executor function
            scorer: Reward scoring function
            embedder: Embedding function

        Returns:
            Shadow outcome dict or None if skipped
        """
        if not self.enable_learning:
            return None

        if baseline_tool == candidate_tool:
            return None  # Don't shadow test same tool

        try:
            outcome = self.shadow.run_once(
                query=query,
                baseline_plan={"tool": baseline_tool, "inputs": {}},
                candidate_plan={"tool": candidate_tool, "inputs": {}},
                executor=executor,
                scorer=scorer,
            )

            if outcome and outcome.ok:
                # Record outcome for both tools
                if embedder:
                    try:
                        if hasattr(embedder, 'encode_query'):
                            query_vec = embedder.encode_query(query)
                        else:
                            query_vec = embedder.encode([query])[0]

                        query_vec = np.asarray(query_vec, dtype=np.float32)
                        expected_dim = self.policy["bandit"]["feature_dim"]
                        if query_vec.shape[0] != expected_dim:
                            if query_vec.shape[0] < expected_dim:
                                query_vec = np.pad(query_vec, (0, expected_dim - query_vec.shape[0]))
                            else:
                                query_vec = query_vec[:expected_dim]

                        # Update bandit for candidate
                        self.bandit.observe(candidate_tool, query_vec, outcome.reward)

                        # Update promotion stats
                        self.state.record(candidate_tool, outcome.delta)
                        save_state(self.state)

                        print(f"[shadow] {candidate_tool} vs {baseline_tool}: Δ={outcome.delta:+.3f} (trials={self.state.stats[candidate_tool].trials})")

                        # Check promotion eligibility
                        if self.state.stats[candidate_tool].trials >= self.policy["promotion"]["min_shadow_trials"]:
                            promoted, reason = promote_if_eligible(
                                candidate_tool,
                                policy=self.policy,
                                state=self.state,
                            )
                            if promoted:
                                print(f"[promotion] ✓ {candidate_tool} promoted to production!")
                            elif not reason.startswith("not_enough_trials"):
                                print(f"[promotion] ✗ {candidate_tool} blocked: {reason}")

                    except Exception as e:
                        print(f"[shadow] Failed to record outcome: {e}")

                return {
                    "baseline": baseline_tool,
                    "candidate": candidate_tool,
                    "delta": outcome.delta,
                    "candidate_reward": outcome.reward,
                    "baseline_reward": outcome.baseline_reward,
                }

        except Exception as e:
            print(f"[shadow] Shadow test failed: {e}")

        return None
