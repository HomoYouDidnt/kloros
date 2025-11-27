"""Provenance tracking for results and artifacts."""
from typing import Dict, Any, List, Optional
import time
import hashlib


class ProvenanceTracker:
    """Tracks provenance of results, decisions, and artifacts."""

    def __init__(self):
        """Initialize provenance tracker."""
        self.records: Dict[str, Dict[str, Any]] = {}

    def attach(
        self,
        artifacts: Dict[str, Any],
        decision: Optional[Dict[str, Any]] = None,
        sources: Optional[List[Dict[str, Any]]] = None
    ) -> Dict[str, Any]:
        """Attach provenance to artifacts.

        Args:
            artifacts: Artifacts dict to attach provenance to
            decision: Decision that produced these artifacts
            sources: Source documents/data used

        Returns:
            Artifacts with provenance attached
        """
        # Get existing provenance or create new
        provenance = artifacts.get("provenance", [])

        # Add sources
        if sources:
            for source in sources:
                prov_entry = {
                    "type": "source",
                    "source_id": source.get("id"),
                    "source_type": source.get("type", "document"),
                    "timestamp": time.time()
                }

                # Add content hash if available
                if "text" in source:
                    prov_entry["content_hash"] = self._hash_content(source["text"])

                provenance.append(prov_entry)

        # Add decision provenance
        if decision:
            prov_entry = {
                "type": "decision",
                "tool": decision.get("tool"),
                "confidence": decision.get("confidence"),
                "timestamp": time.time()
            }
            provenance.append(prov_entry)

        artifacts["provenance"] = provenance
        return artifacts

    def record(
        self,
        artifact_id: str,
        artifact_type: str,
        sources: List[str],
        metadata: Optional[Dict[str, Any]] = None
    ):
        """Record provenance information.

        Args:
            artifact_id: Unique identifier for artifact
            artifact_type: Type of artifact
            sources: List of source IDs
            metadata: Optional metadata
        """
        self.records[artifact_id] = {
            "id": artifact_id,
            "type": artifact_type,
            "sources": sources,
            "metadata": metadata or {},
            "timestamp": time.time()
        }

    def get_provenance(self, artifact_id: str) -> Optional[Dict[str, Any]]:
        """Get provenance for an artifact.

        Args:
            artifact_id: Artifact ID

        Returns:
            Provenance dict or None
        """
        return self.records.get(artifact_id)

    def trace_lineage(self, artifact_id: str, max_depth: int = 10) -> List[Dict[str, Any]]:
        """Trace lineage of an artifact.

        Args:
            artifact_id: Starting artifact ID
            max_depth: Maximum depth to trace

        Returns:
            List of provenance records in lineage
        """
        lineage = []
        visited = set()
        queue = [(artifact_id, 0)]

        while queue and len(lineage) < max_depth:
            current_id, depth = queue.pop(0)

            if current_id in visited or depth >= max_depth:
                continue

            visited.add(current_id)

            prov = self.get_provenance(current_id)
            if prov:
                lineage.append({**prov, "depth": depth})

                # Add sources to queue
                for source_id in prov.get("sources", []):
                    if source_id not in visited:
                        queue.append((source_id, depth + 1))

        return lineage

    def _hash_content(self, content: str) -> str:
        """Hash content for provenance.

        Args:
            content: Content to hash

        Returns:
            Hash string
        """
        return hashlib.sha256(content.encode("utf-8")).hexdigest()[:16]


def attach_provenance(
    artifacts: Dict[str, Any],
    decision: Optional[Dict[str, Any]] = None,
    sources: Optional[List[Dict[str, Any]]] = None
) -> Dict[str, Any]:
    """Convenience function to attach provenance.

    Args:
        artifacts: Artifacts dict
        decision: Decision dict
        sources: Source list

    Returns:
        Artifacts with provenance
    """
    tracker = ProvenanceTracker()
    return tracker.attach(artifacts, decision, sources)


class ProvenanceChain:
    """Chain of provenance for complex workflows."""

    def __init__(self):
        """Initialize provenance chain."""
        self.chain: List[Dict[str, Any]] = []

    def add_step(
        self,
        step_type: str,
        inputs: List[str],
        outputs: List[str],
        metadata: Optional[Dict[str, Any]] = None
    ):
        """Add step to provenance chain.

        Args:
            step_type: Type of step (e.g., 'retrieval', 'execution', 'synthesis')
            inputs: Input artifact IDs
            outputs: Output artifact IDs
            metadata: Optional metadata
        """
        self.chain.append({
            "step": len(self.chain) + 1,
            "type": step_type,
            "inputs": inputs,
            "outputs": outputs,
            "metadata": metadata or {},
            "timestamp": time.time()
        })

    def get_chain(self) -> List[Dict[str, Any]]:
        """Get full provenance chain.

        Returns:
            List of chain steps
        """
        return self.chain

    def get_summary(self) -> Dict[str, Any]:
        """Get summary of provenance chain.

        Returns:
            Summary dict
        """
        if not self.chain:
            return {"steps": 0}

        step_types = {}
        for step in self.chain:
            step_type = step["type"]
            step_types[step_type] = step_types.get(step_type, 0) + 1

        return {
            "steps": len(self.chain),
            "step_types": step_types,
            "start_time": self.chain[0]["timestamp"],
            "end_time": self.chain[-1]["timestamp"],
            "duration": self.chain[-1]["timestamp"] - self.chain[0]["timestamp"]
        }

    def to_graph(self) -> Dict[str, Any]:
        """Convert chain to graph representation.

        Returns:
            Graph dict with nodes and edges
        """
        nodes = set()
        edges = []

        for step in self.chain:
            # Add input/output nodes
            for inp in step["inputs"]:
                nodes.add(inp)
            for out in step["outputs"]:
                nodes.add(out)

            # Add edges from inputs to outputs
            for inp in step["inputs"]:
                for out in step["outputs"]:
                    edges.append({
                        "from": inp,
                        "to": out,
                        "step": step["step"],
                        "type": step["type"]
                    })

        return {
            "nodes": list(nodes),
            "edges": edges
        }
