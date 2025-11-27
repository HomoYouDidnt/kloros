#!/usr/bin/env python3
"""
Semantic Evidence - Tracks learned context about modules from investigations.

Purpose:
    Store and retrieve semantic understanding of modules discovered through
    curiosity-driven investigations. This is the LEARNED context, not static
    filesystem metadata.

Evidence Types:
    - purpose: What the module does
    - integrates_with: Which modules it connects to
    - provides_capability: What capabilities it offers
    - used_by: Which modules depend on it
    - key_abstractions: Important classes/concepts

This enables recursive learning: investigating A updates evidence for B,
which triggers re-investigation of B with enriched context.
"""

import json
import logging
import hashlib
from pathlib import Path
from typing import Dict, Any, List, Optional, Set
from datetime import datetime

logger = logging.getLogger(__name__)

SEMANTIC_EVIDENCE_PATH = Path("/home/kloros/.kloros/semantic_evidence.json")


class SemanticEvidenceStore:
    """Stores and manages semantic evidence learned from investigations."""

    def __init__(self, evidence_path: Path = SEMANTIC_EVIDENCE_PATH):
        """Initialize semantic evidence store."""
        self.evidence_path = evidence_path
        self.evidence: Dict[str, Dict[str, Any]] = self._load_evidence()
        self._embedder = None  # Lazy-loaded for semantic deduplication
        self._similarity_threshold = 0.85  # Cosine similarity threshold for deduplication
        self._auto_suppress_threshold = 5  # Auto-suppress after N failures

    def _load_evidence(self) -> Dict[str, Dict[str, Any]]:
        """Load semantic evidence from disk."""
        if not self.evidence_path.exists():
            logger.info("[semantic] No existing semantic evidence, starting fresh")
            return {}

        try:
            with open(self.evidence_path, 'r') as f:
                data = json.load(f)
            logger.info(f"[semantic] Loaded evidence for {len(data)} modules")
            return data
        except Exception as e:
            logger.error(f"[semantic] Failed to load evidence: {e}, starting fresh")
            return {}

    def _save_evidence(self):
        """Persist semantic evidence to disk."""
        try:
            self.evidence_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.evidence_path, 'w') as f:
                json.dump(self.evidence, f, indent=2)
            logger.info(f"[semantic] Saved evidence for {len(self.evidence)} modules")
        except Exception as e:
            logger.error(f"[semantic] Failed to save evidence: {e}")

    def _get_embedder(self):
        """Lazy-load embedding model for semantic deduplication."""
        if self._embedder is None:
            try:
                from sentence_transformers import SentenceTransformer
                import sys
                sys.path.insert(0, '/home/kloros/src')
                from config.models_config import get_embedder_model, get_embedder_trust_remote_code

                model_name = get_embedder_model()
                trust_remote_code = get_embedder_trust_remote_code()

                logger.info(f"[semantic] Loading embedder for deduplication: {model_name}")
                self._embedder = SentenceTransformer(model_name, device='cuda', trust_remote_code=trust_remote_code)
            except Exception as e:
                logger.warning(f"[semantic] Failed to load embedder, deduplication disabled: {e}")
                self._embedder = False  # Disable future attempts

        return self._embedder if self._embedder is not False else None

    def _is_semantically_similar(self, new_text: str, existing_texts: List[str]) -> bool:
        """
        Check if new_text is semantically similar to any existing text.

        Returns:
            True if similar to any existing text (should skip), False if unique
        """
        if not existing_texts:
            return False

        embedder = self._get_embedder()
        if embedder is None:
            # Deduplication disabled, fall back to exact string match
            return new_text in existing_texts

        try:
            import numpy as np

            # Compute embeddings
            all_texts = [new_text] + existing_texts
            embeddings = embedder.encode(all_texts, convert_to_numpy=True, show_progress_bar=False)

            # Normalize for cosine similarity
            norms = np.linalg.norm(embeddings, axis=1, keepdims=True)
            normalized = embeddings / norms

            # Compare new text (index 0) with all existing texts (index 1+)
            new_embedding = normalized[0:1]
            existing_embeddings = normalized[1:]

            similarities = new_embedding @ existing_embeddings.T
            max_similarity = similarities.max()

            if max_similarity >= self._similarity_threshold:
                logger.debug(f"[semantic] Skipping similar capability (similarity: {max_similarity:.2f}): {new_text[:60]}...")
                return True

            return False

        except Exception as e:
            logger.warning(f"[semantic] Similarity check failed, falling back to exact match: {e}")
            return new_text in existing_texts

    def update_from_investigation(self, investigation: Dict[str, Any]) -> Set[str]:
        """
        Update semantic evidence from investigation results.

        Args:
            investigation: Investigation result dict with integration_points,
                          capabilities, key_abstractions

        Returns:
            Set of module names whose evidence was updated (for triggering re-investigation)
        """
        module_name = investigation.get("module_name")
        if not module_name:
            logger.debug("[semantic] Investigation has no module_name (non-module question), skipping semantic evidence update")
            return set()

        updated_modules = set()

        # Initialize evidence for this module if needed
        if module_name not in self.evidence:
            self.evidence[module_name] = {
                "discovered_at": datetime.now().isoformat(),
                "integrates_with": [],
                "provides_capabilities": [],
                "used_by": [],
                "key_abstractions": [],
                "purpose": None
            }

        module_evidence = self.evidence[module_name]

        # Extract semantic data from investigation
        integration_points = investigation.get("integration_points", [])
        capabilities = investigation.get("capabilities", [])
        abstractions = investigation.get("key_abstractions", [])
        llm_analysis = investigation.get("llm_analysis", "")

        # Update integration points
        for point in integration_points:
            # Extract module names from integration point descriptions
            # e.g., "Depends on registry for tracking" -> extract "registry"
            related_modules = self._extract_module_names(point)
            for related in related_modules:
                if related not in module_evidence["integrates_with"]:
                    module_evidence["integrates_with"].append(related)
                    updated_modules.add(module_name)

                    # RECIPROCAL UPDATE: Add this module to related module's "used_by"
                    if related not in self.evidence:
                        self.evidence[related] = {
                            "discovered_at": datetime.now().isoformat(),
                            "integrates_with": [],
                            "provides_capabilities": [],
                            "used_by": [],
                            "key_abstractions": [],
                            "purpose": None
                        }
                    if module_name not in self.evidence[related]["used_by"]:
                        self.evidence[related]["used_by"].append(module_name)
                        updated_modules.add(related)  # Trigger re-investigation of related module
                        logger.info(f"[semantic] {related} now known to be used by {module_name}")

        # Update capabilities (with semantic deduplication)
        for cap in capabilities:
            # Check both exact match and semantic similarity
            if not self._is_semantically_similar(cap, module_evidence["provides_capabilities"]):
                module_evidence["provides_capabilities"].append(cap)
                updated_modules.add(module_name)
                logger.debug(f"[semantic] Added new capability to {module_name}: {cap[:60]}...")

        # Update abstractions (with semantic deduplication)
        for ab in abstractions:
            # Check both exact match and semantic similarity
            if not self._is_semantically_similar(ab, module_evidence["key_abstractions"]):
                module_evidence["key_abstractions"].append(ab)
                updated_modules.add(module_name)
                logger.debug(f"[semantic] Added new abstraction to {module_name}: {ab[:60]}...")

        # Extract purpose from LLM analysis (first sentence usually)
        if llm_analysis and not module_evidence["purpose"]:
            # Handle both string and dict formats
            if isinstance(llm_analysis, dict):
                llm_text = " ".join(str(v) for v in llm_analysis.values())
            else:
                llm_text = str(llm_analysis)

            # Take first meaningful sentence as purpose
            sentences = llm_text.split('. ')
            if sentences:
                module_evidence["purpose"] = sentences[0].strip()[:100]  # Truncate
                updated_modules.add(module_name)

        # Update last_updated timestamp
        module_evidence["last_updated"] = datetime.now().isoformat()

        # Persist changes
        if updated_modules:
            self._save_evidence()
            logger.debug(f"[semantic] Updated evidence for modules: {', '.join(updated_modules)}")

        return updated_modules

    def _extract_module_names(self, text) -> List[str]:
        """
        Extract module names from integration point descriptions.

        Examples:
            "Depends on registry for tracking" -> ["registry"]
            "Uses policy configuration files" -> ["policy"]
            "Interfaces with tool execution" -> ["tool"]
        """
        # Handle non-string inputs gracefully
        if not isinstance(text, str):
            if isinstance(text, dict):
                # Try to extract from dict values
                text = " ".join(str(v) for v in text.values())
            else:
                text = str(text)

        # Common module names in KLoROS
        known_modules = [
            "registry", "kloros", "orchestration", "phase", "dream", "spica",
            "policy", "governance", "memory", "reasoning", "integration",
            "consciousness", "introspection", "curiosity", "capability",
            "dream_evolution", "gpu_workers"
        ]

        found = []
        text_lower = text.lower()
        for module in known_modules:
            if module in text_lower:
                found.append(module)

        return found

    def get_evidence(self, module_name: str) -> Dict[str, Any]:
        """Get semantic evidence for a module."""
        return self.evidence.get(module_name, {
            "integrates_with": [],
            "provides_capabilities": [],
            "used_by": [],
            "key_abstractions": [],
            "purpose": None
        })

    def to_evidence_list(self, module_name: str) -> List[str]:
        """
        Convert semantic evidence to evidence list format for hashing.

        Returns:
            List of evidence strings like:
            ["purpose:Shadow testing system", "integrates_with:registry",
             "used_by:orchestration", "capability:promotion_logic"]
        """
        evidence_dict = self.get_evidence(module_name)
        evidence_list = []

        if evidence_dict.get("purpose"):
            evidence_list.append(f"purpose:{evidence_dict['purpose'][:50]}")  # Truncate

        for integration in sorted(evidence_dict.get("integrates_with", [])):
            evidence_list.append(f"integrates_with:{integration}")

        for user in sorted(evidence_dict.get("used_by", [])):
            evidence_list.append(f"used_by:{user}")

        for cap in sorted(evidence_dict.get("provides_capabilities", []))[:3]:  # Top 3
            evidence_list.append(f"capability:{cap[:40]}")  # Truncate

        return evidence_list

    def _initialize_suppression(self, capability_key: str) -> Dict[str, Any]:
        """Initialize suppression metadata for a capability."""
        now = datetime.now().isoformat()
        return {
            "suppressed": False,
            "reason": "",
            "first_attempt": now,
            "last_attempt": now,
            "failure_count": 0,
            "suppress_until": None,
            "user_can_override": True
        }

    def _ensure_suppression_exists(self, capability_key: str) -> None:
        """Ensure capability has suppression metadata."""
        if capability_key not in self.evidence:
            self.evidence[capability_key] = {
                "discovered_at": datetime.now().isoformat(),
                "integrates_with": [],
                "provides_capabilities": [],
                "used_by": [],
                "key_abstractions": [],
                "purpose": None
            }

        if "suppression" not in self.evidence[capability_key]:
            self.evidence[capability_key]["suppression"] = self._initialize_suppression(capability_key)

    def record_failure(self, capability_key: str, reason: str = "") -> None:
        """
        Record a failure for a capability.

        Auto-suppresses at configured threshold (default: 5 failures).

        Args:
            capability_key: The capability identifier
            reason: Description of the failure
        """
        self._ensure_suppression_exists(capability_key)
        suppression = self.evidence[capability_key]["suppression"]

        suppression["failure_count"] += 1
        suppression["last_attempt"] = datetime.now().isoformat()
        suppression["reason"] = reason

        if suppression["failure_count"] >= self._auto_suppress_threshold and not suppression["suppressed"]:
            suppression["suppressed"] = True
            suppression["reason"] = f"Repeated investigation failures ({suppression['failure_count']} attempts)"
            logger.warning(f"[semantic] Auto-suppressed {capability_key} after {suppression['failure_count']} failures")

        self._save_evidence()

    def is_suppressed(self, capability_key: str) -> bool:
        """
        Check if a capability is suppressed.

        Conservative: returns False if capability not found.

        Args:
            capability_key: The capability identifier

        Returns:
            True if suppressed, False otherwise
        """
        if capability_key not in self.evidence:
            return False

        suppression = self.evidence[capability_key].get("suppression", {})
        return suppression.get("suppressed", False)

    def suppress(self, capability_key: str, reason: str) -> None:
        """
        Manually suppress a capability.

        Args:
            capability_key: The capability identifier
            reason: Why the capability is being suppressed
        """
        self._ensure_suppression_exists(capability_key)
        suppression = self.evidence[capability_key]["suppression"]

        suppression["suppressed"] = True
        suppression["reason"] = reason

        logger.info(f"[semantic] Suppressed {capability_key}: {reason}")
        self._save_evidence()

    def unsuppress(self, capability_key: str) -> None:
        """
        Clear suppression for a capability.

        Preserves failure history for audit trail.

        Args:
            capability_key: The capability identifier
        """
        if capability_key not in self.evidence:
            return

        if "suppression" in self.evidence[capability_key]:
            self.evidence[capability_key]["suppression"]["suppressed"] = False
            logger.info(f"[semantic] Unsuppressed {capability_key}")
            self._save_evidence()

    def get_suppression_info(self, capability_key: str) -> Dict[str, Any]:
        """
        Get suppression metadata for a capability.

        Args:
            capability_key: The capability identifier

        Returns:
            Dictionary with suppression metadata, empty dict if not found
        """
        if capability_key not in self.evidence:
            return {}

        return self.evidence[capability_key].get("suppression", {})


if __name__ == "__main__":
    # Self-test
    logging.basicConfig(level=logging.INFO)

    print("=== Semantic Evidence Store Self-Test ===\n")

    store = SemanticEvidenceStore()
    print(f"Loaded evidence for {len(store.evidence)} modules\n")

    # Show sample evidence
    for module_name in list(store.evidence.keys())[:3]:
        print(f"Module: {module_name}")
        evidence = store.get_evidence(module_name)
        print(f"  Purpose: {evidence.get('purpose', 'Unknown')}")
        print(f"  Integrates with: {', '.join(evidence.get('integrates_with', []))}")
        print(f"  Used by: {', '.join(evidence.get('used_by', []))}")
        print(f"  Evidence list: {store.to_evidence_list(module_name)}")
        print()
