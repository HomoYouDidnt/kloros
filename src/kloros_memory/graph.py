"""
Memory graph system for KLoROS using NetworkX.

Creates a network of relationships between memories for:
- Multi-hop reasoning (A → B → C)
- Context expansion ("what came after this?")
- Related memory discovery
- Causal relationship tracking
"""

from __future__ import annotations

import logging
import time
from enum import Enum
from typing import Any, Dict, List, Optional, Set, Tuple

try:
    import networkx as nx
    HAS_NETWORKX = True
except ImportError:
    nx = None
    HAS_NETWORKX = False

from .models import Event, EpisodeSummary
from .storage import MemoryStore

logger = logging.getLogger(__name__)


class EdgeType(str, Enum):
    """Types of edges in the memory graph."""

    TEMPORAL = "temporal"  # Event A happened before B
    CAUSAL = "causal"  # Event A caused B
    SEMANTIC = "semantic"  # A and B are semantically related
    CONVERSATIONAL = "conversational"  # A and B in same conversation
    REFERENCE = "reference"  # A references B explicitly
    PROCEDURAL = "procedural"  # A and B are steps in same procedure


class MemoryGraph:
    """
    Graph-based memory network using NetworkX.

    Features:
    - Multiple edge types for different relationships
    - Weighted edges with decay
    - Bidirectional traversal
    - Efficient path finding
    - Persistent storage in SQLite
    """

    def __init__(self, store: Optional[MemoryStore] = None):
        """
        Initialize the memory graph.

        Args:
            store: Memory storage instance
        """
        if not HAS_NETWORKX:
            raise ImportError(
                "networkx is not installed. "
                "Install it with: pip install networkx"
            )

        self.store = store or MemoryStore()
        self.graph = nx.MultiDiGraph()  # Directed multigraph (multiple edges between nodes)

        # Load existing edges from database
        self._load_from_storage()

    def _load_from_storage(self):
        """Load existing edges from SQLite into NetworkX graph."""
        conn = self.store._get_connection()
        cursor = conn.execute(
            "SELECT source_id, target_id, source_type, target_type, edge_type, weight, created_at, metadata FROM memory_edges"
        )

        edge_count = 0
        for row in cursor.fetchall():
            self.graph.add_edge(
                f"{row['source_type']}_{row['source_id']}",
                f"{row['target_type']}_{row['target_id']}",
                edge_type=row['edge_type'],
                weight=row['weight'],
                created_at=row['created_at'],
                metadata=row['metadata']
            )
            edge_count += 1

        logger.info(f"[graph] Loaded {edge_count} edges from storage")

    def add_edge(
        self,
        source_id: int,
        target_id: int,
        edge_type: EdgeType,
        weight: float = 1.0,
        source_type: str = "event",
        target_type: str = "event",
        metadata: Optional[Dict[str, Any]] = None
    ) -> None:
        """
        Add an edge between two memory nodes.

        Args:
            source_id: ID of source node
            target_id: ID of target node
            edge_type: Type of relationship
            weight: Edge weight (0.0-1.0)
            source_type: Type of source node (event, summary, etc.)
            target_type: Type of target node
            metadata: Additional edge metadata
        """
        import json

        # Create node identifiers
        source_node = f"{source_type}_{source_id}"
        target_node = f"{target_type}_{target_id}"

        # Add to NetworkX graph
        self.graph.add_edge(
            source_node,
            target_node,
            edge_type=edge_type.value if isinstance(edge_type, EdgeType) else edge_type,
            weight=weight,
            created_at=time.time(),
            metadata=metadata or {}
        )

        # Persist to database
        with self.store._transaction() as conn:
            conn.execute("""
                INSERT INTO memory_edges (
                    source_id, target_id, source_type, target_type,
                    edge_type, weight, decay_rate, created_at, metadata
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                source_id,
                target_id,
                source_type,
                target_type,
                edge_type.value if isinstance(edge_type, EdgeType) else edge_type,
                weight,
                0.1,  # Default decay rate
                time.time(),
                json.dumps(metadata or {})
            ))

    def add_temporal_edge(self, event1_id: int, event2_id: int, weight: float = 0.8):
        """Add temporal edge (event1 happened before event2)."""
        self.add_edge(
            source_id=event1_id,
            target_id=event2_id,
            edge_type=EdgeType.TEMPORAL,
            weight=weight,
            metadata={"relation": "preceded_by"}
        )

    def add_conversational_edges(self, event_ids: List[int], conversation_id: str):
        """
        Add conversational edges for all events in a conversation.

        Args:
            event_ids: List of event IDs in chronological order
            conversation_id: Conversation ID
        """
        # Connect consecutive events temporally
        for i in range(len(event_ids) - 1):
            self.add_temporal_edge(event_ids[i], event_ids[i + 1])

        # Connect all events in conversation (weaker edges)
        for i in range(len(event_ids)):
            for j in range(i + 1, len(event_ids)):
                self.add_edge(
                    source_id=event_ids[i],
                    target_id=event_ids[j],
                    edge_type=EdgeType.CONVERSATIONAL,
                    weight=0.5,
                    metadata={"conversation_id": conversation_id}
                )

    def add_semantic_edge(self, event1_id: int, event2_id: int, similarity: float):
        """
        Add semantic edge based on content similarity.

        Args:
            event1_id: First event ID
            event2_id: Second event ID
            similarity: Semantic similarity score (0.0-1.0)
        """
        if similarity > 0.6:  # Only add if significantly similar
            self.add_edge(
                source_id=event1_id,
                target_id=event2_id,
                edge_type=EdgeType.SEMANTIC,
                weight=similarity,
                metadata={"similarity": similarity}
            )

    def get_neighbors(
        self,
        node_id: int,
        node_type: str = "event",
        edge_types: Optional[List[EdgeType]] = None,
        direction: str = "outgoing"
    ) -> List[Tuple[int, str, Dict[str, Any]]]:
        """
        Get neighboring nodes.

        Args:
            node_id: ID of the node
            node_type: Type of node (event, summary, etc.)
            edge_types: Filter by edge types (None = all types)
            direction: "outgoing", "incoming", or "both"

        Returns:
            List of (neighbor_id, neighbor_type, edge_data) tuples
        """
        node = f"{node_type}_{node_id}"

        if node not in self.graph:
            return []

        neighbors = []

        # Get outgoing edges
        if direction in ["outgoing", "both"]:
            for target in self.graph.successors(node):
                for edge_data in self.graph[node][target].values():
                    if edge_types is None or edge_data['edge_type'] in [et.value for et in edge_types]:
                        target_type, target_id = target.split("_", 1)
                        neighbors.append((int(target_id), target_type, edge_data))

        # Get incoming edges
        if direction in ["incoming", "both"]:
            for source in self.graph.predecessors(node):
                for edge_data in self.graph[source][node].values():
                    if edge_types is None or edge_data['edge_type'] in [et.value for et in edge_types]:
                        source_type, source_id = source.split("_", 1)
                        neighbors.append((int(source_id), source_type, edge_data))

        return neighbors

    def find_path(
        self,
        source_id: int,
        target_id: int,
        source_type: str = "event",
        target_type: str = "event",
        max_length: int = 5
    ) -> Optional[List[Tuple[int, str]]]:
        """
        Find shortest path between two nodes.

        Args:
            source_id: Source node ID
            target_id: Target node ID
            source_type: Source node type
            target_type: Target node type
            max_length: Maximum path length

        Returns:
            Path as list of (node_id, node_type) tuples, or None if no path
        """
        source_node = f"{source_type}_{source_id}"
        target_node = f"{target_type}_{target_id}"

        if source_node not in self.graph or target_node not in self.graph:
            return None

        try:
            path = nx.shortest_path(
                self.graph,
                source=source_node,
                target=target_node,
                weight='weight'
            )

            if len(path) > max_length + 1:
                return None

            # Convert node names back to (id, type) tuples
            result = []
            for node in path:
                node_type, node_id = node.split("_", 1)
                result.append((int(node_id), node_type))

            return result

        except nx.NetworkXNoPath:
            return None
        except nx.NodeNotFound:
            return None

    def expand_context(
        self,
        event_id: int,
        max_depth: int = 2,
        max_nodes: int = 20,
        edge_types: Optional[List[EdgeType]] = None
    ) -> Set[int]:
        """
        Expand context around an event using graph traversal.

        Args:
            event_id: Starting event ID
            max_depth: Maximum traversal depth
            max_nodes: Maximum number of nodes to return
            edge_types: Filter by edge types

        Returns:
            Set of related event IDs
        """
        node = f"event_{event_id}"

        if node not in self.graph:
            return set()

        related = set()
        visited = set()
        queue = [(node, 0)]  # (node, depth)

        while queue and len(related) < max_nodes:
            current, depth = queue.pop(0)

            if current in visited or depth > max_depth:
                continue

            visited.add(current)

            # Add current node to results (skip starting node)
            if current != node:
                node_type, node_id = current.split("_", 1)
                if node_type == "event":
                    related.add(int(node_id))

            # Add neighbors to queue
            if depth < max_depth:
                # Outgoing edges
                for target in self.graph.successors(current):
                    for edge_data in self.graph[current][target].values():
                        if edge_types is None or edge_data['edge_type'] in [et.value for et in edge_types]:
                            queue.append((target, depth + 1))

                # Incoming edges
                for source in self.graph.predecessors(current):
                    for edge_data in self.graph[source][current].values():
                        if edge_types is None or edge_data['edge_type'] in [et.value for et in edge_types]:
                            queue.append((source, depth + 1))

        return related

    def get_temporal_sequence(
        self,
        event_id: int,
        direction: str = "forward",
        max_length: int = 10
    ) -> List[int]:
        """
        Get temporal sequence of events.

        Args:
            event_id: Starting event ID
            direction: "forward" (what came after) or "backward" (what came before)
            max_length: Maximum sequence length

        Returns:
            List of event IDs in temporal order
        """
        sequence = []
        current_id = event_id
        visited = set()

        while len(sequence) < max_length:
            if current_id in visited:
                break

            visited.add(current_id)

            # Find next/prev temporal edge
            neighbors = self.get_neighbors(
                node_id=current_id,
                edge_types=[EdgeType.TEMPORAL],
                direction="outgoing" if direction == "forward" else "incoming"
            )

            if not neighbors:
                break

            # Take highest weight edge
            neighbors.sort(key=lambda x: x[2]['weight'], reverse=True)
            next_id, _, _ = neighbors[0]

            sequence.append(next_id)
            current_id = next_id

        return sequence

    def get_graph_statistics(self) -> Dict[str, Any]:
        """
        Get statistics about the memory graph.

        Returns:
            Dictionary with graph statistics
        """
        stats = {
            "total_nodes": self.graph.number_of_nodes(),
            "total_edges": self.graph.number_of_edges(),
            "edge_types": {}
        }

        # Count edges by type
        for _, _, data in self.graph.edges(data=True):
            edge_type = data['edge_type']
            stats['edge_types'][edge_type] = stats['edge_types'].get(edge_type, 0) + 1

        # Graph density (how connected it is)
        if self.graph.number_of_nodes() > 1:
            stats['density'] = nx.density(self.graph)
        else:
            stats['density'] = 0.0

        # Most connected nodes
        if self.graph.number_of_nodes() > 0:
            degrees = dict(self.graph.degree())
            sorted_degrees = sorted(degrees.items(), key=lambda x: x[1], reverse=True)[:5]
            stats['most_connected'] = [
                (node.split("_")[1], degree) for node, degree in sorted_degrees
            ]

        return stats
