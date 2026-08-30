import pytest

from openclaw_mesh.engines.speculative import (
    DistributedSpeculativeEngine,
    DraftCandidate,
)


@pytest.mark.asyncio
async def test_speculative_verification():
    engine = DistributedSpeculativeEngine(
        draft_node_id="npu-draft", target_node_id="cuda-target", gamma=4
    )

    draft = DraftCandidate(tokens=["The", "quick", "brown", "cat"])
    target_tokens = ["The", "quick", "brown", "fox", "jumps"]

    result = engine.verify_tokens(draft, target_tokens)
    assert result.num_accepted == 3
    assert result.accepted_tokens == ["The", "quick", "brown"]
    assert result.correction_token == "fox"
    assert engine.stats.total_accepted == 3
    assert engine.stats.total_corrections == 1


@pytest.mark.asyncio
async def test_speculative_stream_execution():
    engine = DistributedSpeculativeEngine(
        draft_node_id="npu-draft", target_node_id="cuda-target", gamma=3
    )

    emitted = [item async for item in engine.execute_speculative_stream("Hello", max_tokens=6)]

    assert len(emitted) == 6
    assert all("token" in it for it in emitted)
