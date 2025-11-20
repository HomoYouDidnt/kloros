#!/usr/bin/env python3
"""
Acceptance tests for adaptive model routing.

Tests that queries are routed to the correct model based on intent.
"""

import pytest
import sys
sys.path.insert(0, '/home/kloros')

from src.config.routing import get_intent_router


class TestRoutingAcceptance:
    """Acceptance tests for routing decisions."""

    def setup_method(self):
        """Setup for each test."""
        self.router = get_intent_router()

    def test_code_refactor_hits_coder(self):
        """Test: 'Refactor function X across files' → hits coder."""
        transcript = "Refactor the divide function across all files to add zero checking"
        mode, model, url = self.router.route(transcript)

        assert mode == "code", f"Expected 'code' mode, got '{mode}'"
        assert "coder" in model.lower(), f"Expected coder model, got '{model}'"

    def test_file_operation_hits_coder(self):
        """Test: File operation requests → hits coder."""
        transcript = "Edit file math_utils.py and change the divide function"
        mode, model, url = self.router.route(transcript)

        assert mode == "code", f"Expected 'code' mode, got '{mode}'"

    def test_comparison_analysis_hits_reasoner(self):
        """Test: 'Compare two strategies with tradeoffs' → hits reasoner."""
        transcript = "Compare SQLite vs PostgreSQL with tradeoffs for our use case"
        mode, model, url = self.router.route(transcript)

        assert mode == "think", f"Expected 'think' mode, got '{mode}'"
        assert "deepseek" in model.lower() or "r1" in model.lower(), f"Expected reasoning model, got '{model}'"

    def test_why_question_hits_reasoner(self):
        """Test: 'Why' questions → hits reasoner."""
        transcript = "Why does the system use three separate Ollama instances?"
        mode, model, url = self.router.route(transcript)

        assert mode == "think", f"Expected 'think' mode, got '{mode}'"

    def test_short_query_hits_generalist(self):
        """Test: 'Summarize this note' → generalist."""
        transcript = "Summarize"
        mode, model, url = self.router.route(transcript)

        assert mode == "live", f"Expected 'live' mode, got '{mode}'"

    def test_manual_override_code_tag(self):
        """Test: @code tag forces coder model."""
        transcript = "@code What is 2 + 2?"
        mode, model, url = self.router.route(transcript)

        assert mode == "code", f"Expected 'code' mode, got '{mode}'"

    def test_manual_override_reason_tag(self):
        """Test: @reason tag forces reasoning model."""
        transcript = "@reason What is the capital of France?"
        mode, model, url = self.router.route(transcript)

        assert mode == "think", f"Expected 'think' mode, got '{mode}'"

    def test_explicit_mode_parameter(self):
        """Test: explicit_mode parameter takes precedence."""
        transcript = "This should normally go to code"
        mode, model, url = self.router.route(transcript, explicit_mode="deep")

        assert mode == "deep", f"Expected 'deep' mode from explicit param, got '{mode}'"

    def test_route_logging(self):
        """Test: Routing decisions are logged."""
        initial_count = len(self.router.route_history)

        self.router.route("Test query 1")
        self.router.route("Test query 2")
        self.router.route("Test query 3")

        assert len(self.router.route_history) == initial_count + 3, "Routes should be logged"

    def test_route_stats(self):
        """Test: Route statistics are available."""
        # Generate some routes
        self.router.route("Implement function X")  # code
        self.router.route("Why does this happen?")  # think
        self.router.route("Hello")  # live

        stats = self.router.get_route_stats()

        assert "total_routes" in stats
        assert "mode_distribution" in stats
        assert "reason_distribution" in stats
        assert stats["total_routes"] >= 3


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
