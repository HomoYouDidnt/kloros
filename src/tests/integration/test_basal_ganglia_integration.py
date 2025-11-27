import numpy as np
import pytest
from src.cognition.basal_ganglia.striatum import Striatum
from src.cognition.basal_ganglia.globus_pallidus import GlobusPallidus
from src.cognition.basal_ganglia.substantia_nigra import SubstantiaNigra
from src.cognition.basal_ganglia.pathways.direct import DirectPathway
from src.cognition.basal_ganglia.pathways.indirect import IndirectPathway
from src.cognition.basal_ganglia.channels.tool_channel import ToolChannel
from src.cognition.basal_ganglia.types import Context, Outcome


class TestBasalGangliaIntegration:
    def test_full_selection_and_learning_loop(self):
        channel = ToolChannel(
            tool_registry=["search", "calculate", "read"],
            tool_descriptions={
                "search": "find information on the web",
                "calculate": "perform math",
                "read": "read a file",
            }
        )

        striatum = Striatum(channels=[channel])
        direct = DirectPathway(learning_rate=0.1)
        indirect = IndirectPathway(learning_rate=0.1)
        gp = GlobusPallidus()
        sn = SubstantiaNigra()

        context = Context(query="search for python documentation")
        candidates = striatum.process(context)

        context_emb = striatum.get_context_embedding(context)
        for c in candidates:
            c.direct_activation = direct.compute_activation(context_emb, c)
            c.indirect_activation = indirect.compute_activation(context_emb, c)

        selection = gp.select(candidates)

        assert selection.selected is not None
        assert selection.selection_method in ["competition", "deliberation"]

        outcome = Outcome(success=True, latency_ms=200)
        dopamine = sn.compute_signal(selection.selected, outcome)

        direct.update(selection.selected, dopamine)
        indirect.update(selection.selected, dopamine)

        assert dopamine.delta != 0

    def test_learning_improves_selection(self):
        channel = ToolChannel(
            tool_registry=["good_tool", "bad_tool"],
            tool_descriptions={
                "good_tool": "always works",
                "bad_tool": "never works",
            }
        )

        striatum = Striatum(channels=[channel])
        direct = DirectPathway(learning_rate=0.2)
        indirect = IndirectPathway(learning_rate=0.2)
        gp = GlobusPallidus()
        sn = SubstantiaNigra()

        for _ in range(10):
            context = Context(query="do the task")
            candidates = striatum.process(context)
            context_emb = striatum.get_context_embedding(context)

            for c in candidates:
                c.direct_activation = direct.compute_activation(context_emb, c)
                c.indirect_activation = indirect.compute_activation(context_emb, c)

            selection = gp.select(candidates)

            success = selection.selected.action_id == "good_tool"
            outcome = Outcome(success=success, latency_ms=100)
            dopamine = sn.compute_signal(selection.selected, outcome)

            direct.update(selection.selected, dopamine)
            indirect.update(selection.selected, dopamine)

        final_context = Context(query="do the task")
        final_candidates = striatum.process(final_context)
        final_emb = striatum.get_context_embedding(final_context)

        for c in final_candidates:
            c.direct_activation = direct.compute_activation(final_emb, c)
            c.indirect_activation = indirect.compute_activation(final_emb, c)

        good = next(c for c in final_candidates if c.action_id == "good_tool")
        bad = next(c for c in final_candidates if c.action_id == "bad_tool")

        assert good.competition_degree > bad.competition_degree
