"""
Semantic Tool Matching System for KLoROS.

Uses sentence embeddings to find the most relevant tools for user queries,
improving tool selection accuracy beyond keyword matching.
"""

import numpy as np
from typing import List, Dict, Tuple, Optional
import json
import os

# XAI integration for explainable routing
try:
    from .xai import log_routing_trace, build_routing_decisions
    XAI_AVAILABLE = True
except ImportError:
    XAI_AVAILABLE = False


class SemanticToolMatcher:
    """Matches user queries to tools using semantic similarity."""

    def __init__(self, tool_registry=None, model_name: str = None):
        """
        Initialize semantic tool matcher.

        Args:
            tool_registry: IntrospectionToolRegistry instance
            model_name: Sentence-transformers model to use (default: from config)
        """
        # Import config for single source of truth
        if model_name is None:
            from src.config.embedder_config import get_embedder_model
            model_name = get_embedder_model()

        self.tool_registry = tool_registry
        self.model_name = model_name
        self.model = None
        self.tool_embeddings = {}
        self.tool_metadata = {}

        # Cache file for tool embeddings
        self.cache_file = "/home/kloros/.kloros/tool_embeddings_cache.json"

        # Initialize model and embeddings
        self._initialize_model()
        self._load_or_create_embeddings()

    def _initialize_model(self):
        """Initialize the sentence-transformers model using shared embedding engine."""
        try:
            from src.memory.embeddings import get_embedding_engine
            print(f"[semantic] Using shared embedding engine (singleton)")
            self.embedding_engine = get_embedding_engine()
            # Keep self.model for backwards compatibility with existing code
            if self.embedding_engine:
                self.model = self.embedding_engine.model
                print(f"[semantic] Shared embedding engine initialized")
            else:
                print(f"[semantic] WARNING: Embedding engine unavailable")
                self.model = None
        except Exception as e:
            print(f"[semantic] Failed to initialize shared embedding engine: {e}")
            self.model = None
            self.embedding_engine = None

    def _load_or_create_embeddings(self):
        """Load cached embeddings or create new ones."""
        if not self.tool_registry or not self.model:
            return

        # Try to load from cache
        if os.path.exists(self.cache_file):
            try:
                with open(self.cache_file, 'r') as f:
                    cache_data = json.load(f)

                # Check if cache matches current tools
                current_tools = set(self.tool_registry.tools.keys())
                cached_tools = set(cache_data.get('tools', {}).keys())

                if current_tools == cached_tools:
                    print(f"[semantic] Loaded {len(cached_tools)} tool embeddings from cache")
                    # Convert lists back to numpy arrays
                    for tool_name, embedding_list in cache_data['embeddings'].items():
                        self.tool_embeddings[tool_name] = np.array(embedding_list)
                    self.tool_metadata = cache_data['tools']
                    return
                else:
                    print(f"[semantic] Cache outdated (tools changed), regenerating embeddings")
            except Exception as e:
                print(f"[semantic] Failed to load cache: {e}")

        # Create new embeddings
        print(f"[semantic] Generating embeddings for {len(self.tool_registry.tools)} tools...")
        self._create_tool_embeddings()
        self._save_embeddings_cache()

    def _create_tool_embeddings(self):
        """Create embeddings for all registered tools."""
        if not self.tool_registry or not self.model:
            return

        for tool_name, tool_obj in self.tool_registry.tools.items():
            # Create rich description for embedding
            description = self._get_tool_description(tool_name, tool_obj)

            # Generate embedding using shared engine
            try:
                # Use embedding engine's embed() method for consistency
                embedding = self.embedding_engine.embed(description, normalize=True) if self.embedding_engine else self.model.encode(description, normalize_embeddings=True)
                self.tool_embeddings[tool_name] = embedding
                self.tool_metadata[tool_name] = {
                    'name': tool_name,
                    'description': description,
                    'short_desc': tool_obj.description if hasattr(tool_obj, 'description') else tool_name
                }
            except Exception as e:
                print(f"[semantic] Failed to embed tool '{tool_name}': {e}")

    def _get_tool_description(self, tool_name: str, tool_obj) -> str:
        """
        Create a rich description for tool embedding.

        Combines tool name, description, intent_tags, and inferred functionality.
        """
        parts = []

        # Add tool name (converted to natural language)
        name_natural = tool_name.replace('_', ' ').replace('-', ' ')
        parts.append(name_natural)

        # Add official description if available
        if hasattr(tool_obj, 'description'):
            parts.append(tool_obj.description)

        # Add intent_tags from manifest (if available)
        if hasattr(tool_obj, 'manifest') and isinstance(tool_obj.manifest, dict):
            intent_tags = tool_obj.manifest.get('intent_tags', [])
            if intent_tags:
                parts.append(f"Intent: {', '.join(intent_tags)}")

        # Add parameter information
        if hasattr(tool_obj, 'parameters') and tool_obj.parameters:
            param_names = [p.name if hasattr(p, 'name') else str(p) for p in tool_obj.parameters]
            parts.append(f"Parameters: {', '.join(param_names)}")

        # Add keywords based on tool name
        keywords = self._extract_keywords_from_name(tool_name)
        if keywords:
            parts.append(f"Keywords: {', '.join(keywords)}")

        return ". ".join(parts)


    def _extract_keywords_from_name(self, tool_name: str) -> List[str]:
        """Extract meaningful keywords from tool name."""
        # Common tool categories
        category_keywords = {
            'memory': ['recall', 'remember', 'storage', 'retrieve', 'history'],
            'audio': ['sound', 'voice', 'microphone', 'speaker', 'recording'],
            'system': ['diagnostic', 'status', 'health', 'monitor', 'check'],
            'conversation': ['chat', 'dialogue', 'talk', 'discussion', 'exchange'],
            'user': ['operator', 'person', 'account', 'identity', 'profile'],
            'diagnostic': ['analyze', 'inspect', 'examine', 'troubleshoot', 'debug'],
            'status': ['state', 'condition', 'health', 'info', 'details'],
            'list': ['show', 'display', 'enumerate', 'get', 'fetch'],
            'search': ['find', 'look', 'query', 'locate', 'discover'],
            'count': ['number', 'quantity', 'total', 'amount', 'sum'],
        }

        keywords = []
        name_lower = tool_name.lower()

        for keyword, synonyms in category_keywords.items():
            if keyword in name_lower:
                keywords.extend(synonyms[:3])  # Add top 3 synonyms

        return keywords

    def _save_embeddings_cache(self):
        """Save embeddings to cache file."""
        try:
            os.makedirs(os.path.dirname(self.cache_file), exist_ok=True)

            # Convert numpy arrays to lists for JSON serialization
            cache_data = {
                'embeddings': {
                    tool_name: embedding.tolist()
                    for tool_name, embedding in self.tool_embeddings.items()
                },
                'tools': self.tool_metadata,
                'model': self.model_name
            }

            with open(self.cache_file, 'w') as f:
                json.dump(cache_data, f)

            print(f"[semantic] Saved {len(self.tool_embeddings)} embeddings to cache")
        except Exception as e:
            print(f"[semantic] Failed to save cache: {e}")

    def find_matching_tools(
        self,
        query: str,
        top_k: int = 5,
        threshold: float = 0.3,
        intent: str = "unknown"
    ) -> List[Tuple[str, float, str]]:
        """
        Find tools that best match the query semantically.

        Args:
            query: User's query text
            top_k: Number of top matches to return
            threshold: Minimum similarity score (0-1)
            intent: Intent tag for XAI tracing (optional)

        Returns:
            List of (tool_name, similarity_score, description) tuples, sorted by score
        """
        if not self.model or not self.tool_embeddings:
            return []

        try:
            # Embed the query
            query_embedding = self.model.encode(query, normalize_embeddings=True)

            # Calculate cosine similarity with all tools (for XAI candidates)
            all_candidates = []
            similarities = []

            for tool_name, tool_embedding in self.tool_embeddings.items():
                similarity = np.dot(query_embedding, tool_embedding)

                # Check visibility (masking)
                tool_obj = self.tool_registry.tools.get(tool_name)
                visible = True
                mask_matched = True
                preconditions_met = True

                if tool_obj and hasattr(tool_obj, 'manifest'):
                    from .registry import visible_to
                    visible = visible_to(query, {}, tool_obj.manifest)
                    mask_matched = visible

                    # Check preconditions if they exist
                    if hasattr(tool_obj.manifest, 'preconditions'):
                        preconditions = tool_obj.manifest.get('preconditions', [])
                    else:
                        preconditions = []

                # Add to all_candidates for XAI (even if not visible)
                all_candidates.append({
                    "tool": tool_name,
                    "score": float(similarity),
                    "visible": visible,
                    "mask_matched": mask_matched,
                    "preconditions": preconditions if 'preconditions' in locals() else [],
                    "preconditions_met": preconditions_met
                })

                # Add to results only if visible and above threshold
                if similarity >= threshold and visible:
                    description = self.tool_metadata.get(tool_name, {}).get('short_desc', tool_name)
                    similarities.append((tool_name, float(similarity), description))

            # Sort by similarity score (descending)
            similarities.sort(key=lambda x: x[1], reverse=True)
            top_matches = similarities[:top_k]

            # XAI Integration: Log routing trace
            if XAI_AVAILABLE and all_candidates:
                # Build decision steps
                selected_tool = top_matches[0][0] if top_matches else None
                decisions = build_routing_decisions(
                    all_candidates,
                    masking_rule=f"visible_to(query, context, manifest) → intent tags",
                    selected_tool=selected_tool
                )

                # Create scorer for attribution
                def scorer(text: str) -> float:
                    """Score the selected tool for this text."""
                    if not selected_tool or not self.model:
                        return 0.0
                    try:
                        text_embedding = self.model.encode(text, normalize_embeddings=True)
                        tool_embedding = self.tool_embeddings.get(selected_tool)
                        if tool_embedding is not None:
                            return float(np.dot(text_embedding, tool_embedding))
                    except Exception:
                        pass
                    return 0.0

                # Log routing trace
                log_routing_trace(intent, all_candidates, query, scorer, decisions)

            return top_matches

        except Exception as e:
            print(f"[semantic] Error finding matches: {e}")
            return []

    def suggest_better_tool(
        self,
        query: str,
        proposed_tool: str,
        threshold: float = 0.1
    ) -> Optional[Tuple[str, float]]:
        """
        Check if there's a better tool for the query than the proposed one.

        Args:
            query: User's query text
            proposed_tool: Tool name that was initially selected
            threshold: Minimum improvement margin to suggest alternative

        Returns:
            (better_tool_name, confidence_delta) if found, None otherwise
        """
        matches = self.find_matching_tools(query, top_k=3, threshold=0.2)

        if not matches:
            return None

        # Check if proposed tool is in matches
        proposed_score = None
        for tool_name, score, _ in matches:
            if tool_name == proposed_tool:
                proposed_score = score
                break

        # If proposed tool is not even in top matches, definitely suggest better one
        if proposed_score is None:
            best_tool, best_score, _ = matches[0]
            return (best_tool, best_score)

        # Check if top match is significantly better
        best_tool, best_score, _ = matches[0]
        if best_tool != proposed_tool and (best_score - proposed_score) > threshold:
            return (best_tool, best_score - proposed_score)

        return None

    def get_tool_similarity(self, tool1: str, tool2: str) -> float:
        """
        Get semantic similarity between two tools.

        Args:
            tool1: First tool name
            tool2: Second tool name

        Returns:
            Similarity score (0-1)
        """
        if tool1 not in self.tool_embeddings or tool2 not in self.tool_embeddings:
            return 0.0

        embedding1 = self.tool_embeddings[tool1]
        embedding2 = self.tool_embeddings[tool2]

        return float(np.dot(embedding1, embedding2))

    def refresh_embeddings(self):
        """Refresh embeddings for all tools (call after registry changes)."""
        print("[semantic] Refreshing tool embeddings...")
        self._create_tool_embeddings()
        self._save_embeddings_cache()

    def get_stats(self) -> Dict:
        """Get statistics about the semantic matcher."""
        return {
            'model': self.model_name,
            'model_loaded': self.model is not None,
            'tools_embedded': len(self.tool_embeddings),
            'cache_file': self.cache_file,
            'cache_exists': os.path.exists(self.cache_file)
        }
