"""
High-level query interface for memory graph.

Provides natural language-style queries like:
- "What happened after X?"
- "What caused Y?"
- "Show me everything related to Z"
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Set

from .graph import MemoryGraph, EdgeType
from .models import Event
from .storage import MemoryStore

logger = logging.getLogger(__name__)


class GraphQueryEngine:
    """
    High-level query interface for the memory graph.

    Features:
    - Natural language-style queries
    - Temporal reasoning ("what came after X?")
    - Causal reasoning ("what caused Y?")
    - Relationship discovery
    """

    def __init__(self, graph: Optional[MemoryGraph] = None, store: Optional[MemoryStore] = None):
        """
        Initialize the query engine.

        Args:
            graph: Memory graph instance
            store: Memory storage instance
        """
        self.store = store or MemoryStore()
        self.graph = graph or MemoryGraph(store=self.store)

    def what_happened_after(
        self,
        event_id: int,
        max_events: int = 5
    ) -> List[Event]:
        """
        Get events that happened after a specific event.

        Args:
            event_id: Starting event ID
            max_events: Maximum events to return

        Returns:
            List of subsequent events in chronological order
        """
        # Get temporal sequence
        sequence_ids = self.graph.get_temporal_sequence(
            event_id=event_id,
            direction="forward",
            max_length=max_events
        )

        # Fetch full events
        events = []
        for eid in sequence_ids:
            event = self.store.get_event(eid)
            if event:
                events.append(event)

        return events

    def what_happened_before(
        self,
        event_id: int,
        max_events: int = 5
    ) -> List[Event]:
        """
        Get events that happened before a specific event.

        Args:
            event_id: Starting event ID
            max_events: Maximum events to return

        Returns:
            List of preceding events in reverse chronological order
        """
        sequence_ids = self.graph.get_temporal_sequence(
            event_id=event_id,
            direction="backward",
            max_length=max_events
        )

        events = []
        for eid in sequence_ids:
            event = self.store.get_event(eid)
            if event:
                events.append(event)

        return events

    def get_related_memories(
        self,
        event_id: int,
        max_depth: int = 2,
        max_memories: int = 20,
        relationship_types: Optional[List[str]] = None
    ) -> List[Event]:
        """
        Get all memories related to a specific event.

        Args:
            event_id: Starting event ID
            max_depth: Maximum relationship depth (1 = direct, 2 = indirect)
            max_memories: Maximum memories to return
            relationship_types: Filter by relationship types

        Returns:
            List of related events
        """
        # Convert relationship types to EdgeType
        edge_types = None
        if relationship_types:
            edge_types = [EdgeType(rt) for rt in relationship_types]

        # Expand context via graph
        related_ids = self.graph.expand_context(
            event_id=event_id,
            max_depth=max_depth,
            max_nodes=max_memories,
            edge_types=edge_types
        )

        # Fetch full events
        events = []
        for eid in related_ids:
            event = self.store.get_event(eid)
            if event:
                events.append(event)

        # Sort by timestamp (most recent first)
        events.sort(key=lambda e: e.timestamp, reverse=True)

        return events[:max_memories]

    def find_connection(
        self,
        event1_id: int,
        event2_id: int,
        max_hops: int = 5
    ) -> Optional[Dict[str, Any]]:
        """
        Find how two events are connected.

        Args:
            event1_id: First event ID
            event2_id: Second event ID
            max_hops: Maximum path length

        Returns:
            Dictionary with path info, or None if not connected
        """
        path = self.graph.find_path(
            source_id=event1_id,
            target_id=event2_id,
            max_length=max_hops
        )

        if not path:
            return None

        # Fetch events along path
        events = []
        for node_id, node_type in path:
            if node_type == "event":
                event = self.store.get_event(node_id)
                if event:
                    events.append(event)

        # Get edge types along path
        edge_types = []
        for i in range(len(path) - 1):
            source_id, source_type = path[i]
            target_id, target_type = path[i + 1]

            neighbors = self.graph.get_neighbors(
                node_id=source_id,
                node_type=source_type,
                direction="outgoing"
            )

            for neighbor_id, neighbor_type, edge_data in neighbors:
                if neighbor_id == target_id and neighbor_type == target_type:
                    edge_types.append(edge_data['edge_type'])
                    break

        return {
            "path_length": len(path) - 1,
            "events": events,
            "edge_types": edge_types,
            "connected": True
        }

    def get_conversation_timeline(self, conversation_id: str) -> List[Event]:
        """
        Get chronological timeline of a conversation.

        Args:
            conversation_id: Conversation ID

        Returns:
            List of events in chronological order
        """
        # Get all events in conversation from storage
        events = self.store.get_events(
            conversation_id=conversation_id,
            limit=1000
        )

        # Sort by timestamp
        events.sort(key=lambda e: e.timestamp)

        return events

    def find_cause_chain(
        self,
        event_id: int,
        max_depth: int = 3
    ) -> List[Event]:
        """
        Find causal chain leading to an event.

        Args:
            event_id: Event to trace causes for
            max_depth: Maximum depth to trace

        Returns:
            List of events in causal chain
        """
        # Get predecessors via causal edges
        chain_ids = []
        current_id = event_id
        visited = set()

        for _ in range(max_depth):
            if current_id in visited:
                break

            visited.add(current_id)

            # Find causal predecessors
            neighbors = self.graph.get_neighbors(
                node_id=current_id,
                edge_types=[EdgeType.CAUSAL],
                direction="incoming"
            )

            if not neighbors:
                break

            # Take highest weight causal edge
            neighbors.sort(key=lambda x: x[2]['weight'], reverse=True)
            prev_id, _, _ = neighbors[0]

            chain_ids.append(prev_id)
            current_id = prev_id

        # Reverse to get cause → effect order
        chain_ids.reverse()

        # Fetch full events
        events = []
        for eid in chain_ids:
            event = self.store.get_event(eid)
            if event:
                events.append(event)

        return events

    def get_procedural_sequence(
        self,
        starting_event_id: int,
        max_steps: int = 10
    ) -> List[Event]:
        """
        Get procedural sequence starting from an event.

        Args:
            starting_event_id: Starting event ID
            max_steps: Maximum steps to retrieve

        Returns:
            List of events in procedural order
        """
        # Get sequence via procedural edges
        sequence_ids = []
        current_id = starting_event_id
        visited = set()

        while len(sequence_ids) < max_steps:
            if current_id in visited:
                break

            visited.add(current_id)

            # Find next procedural step
            neighbors = self.graph.get_neighbors(
                node_id=current_id,
                edge_types=[EdgeType.PROCEDURAL],
                direction="outgoing"
            )

            if not neighbors:
                break

            # Take first procedural edge (assuming single sequence)
            next_id, _, _ = neighbors[0]
            sequence_ids.append(next_id)
            current_id = next_id

        # Fetch full events
        events = []
        for eid in sequence_ids:
            event = self.store.get_event(eid)
            if event:
                events.append(event)

        return events
