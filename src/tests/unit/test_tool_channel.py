import numpy as np
import pytest
from src.cognition.basal_ganglia.channels.tool_channel import ToolChannel
from src.cognition.basal_ganglia.types import Context


class TestToolChannel:
    def test_channel_name(self):
        channel = ToolChannel()
        assert channel.name == "tool"

    def test_get_candidates_returns_available_tools(self):
        channel = ToolChannel(tool_registry=["search", "calculate", "read_file"])
        context = Context(query="search for information")
        candidates = channel.get_candidates(context)
        assert len(candidates) == 3
        assert all(c.channel == "tool" for c in candidates)
        assert {c.action_id for c in candidates} == {"search", "calculate", "read_file"}

    def test_candidates_have_embeddings(self):
        channel = ToolChannel(tool_registry=["search"])
        context = Context(query="test")
        candidates = channel.get_candidates(context)
        assert candidates[0].context_embedding.shape == (384,)

    def test_d1_higher_for_relevant_tool(self):
        channel = ToolChannel(
            tool_registry=["search", "calculate"],
            tool_descriptions={
                "search": "find information on the web",
                "calculate": "perform mathematical calculations",
            }
        )
        context = Context(query="search for python documentation")
        candidates = channel.get_candidates(context)

        search_candidate = next(c for c in candidates if c.action_id == "search")
        calc_candidate = next(c for c in candidates if c.action_id == "calculate")

        context_emb = channel._embed(context.query)
        d1_search = channel.compute_d1(context_emb, search_candidate)
        d1_calc = channel.compute_d1(context_emb, calc_candidate)

        assert d1_search > d1_calc
