import numpy as np
import pytest
from src.cognition.basal_ganglia.striatum import Striatum
from src.cognition.basal_ganglia.channels.tool_channel import ToolChannel
from src.cognition.basal_ganglia.types import Context


class TestStriatum:
    def test_processes_context_into_candidates(self):
        channel = ToolChannel(tool_registry=["search", "calculate"])
        striatum = Striatum(channels=[channel])

        context = Context(query="find information")
        candidates = striatum.process(context)

        assert len(candidates) == 2
        assert all(c.channel == "tool" for c in candidates)

    def test_candidates_have_d1_d2_scores(self):
        channel = ToolChannel(tool_registry=["search"])
        striatum = Striatum(channels=[channel])

        context = Context(query="test")
        candidates = striatum.process(context)

        assert candidates[0].direct_activation > 0
        assert candidates[0].indirect_activation > 0

    def test_detects_novel_context(self):
        channel = ToolChannel(tool_registry=["search"])
        striatum = Striatum(channels=[channel], novelty_threshold=0.5)

        context1 = Context(query="first query about apples")
        striatum.process(context1)

        context2 = Context(query="completely different topic about quantum physics")
        candidates = striatum.process(context2)

        assert candidates[0].is_novel_context is True

    def test_familiar_context_not_novel(self):
        channel = ToolChannel(tool_registry=["search"])
        striatum = Striatum(channels=[channel])

        for _ in range(5):
            context = Context(query="search for python docs")
            striatum.process(context)

        context = Context(query="search for python documentation")
        candidates = striatum.process(context)

        assert candidates[0].is_novel_context is False
