import pytest

from openclaw_mesh.network.ice import ICECandidate, ICENegotiator


@pytest.mark.asyncio
async def test_ice_candidate_gathering_and_pairing():
    neg_a = ICENegotiator(local_name="peer-a", local_port=8771, relay_url="wss://relay.openclaw.mesh")
    neg_b = ICENegotiator(local_name="peer-b", local_port=8772, relay_url="wss://relay.openclaw.mesh")

    cands_a = await neg_a.gather_candidates()
    cands_b = await neg_b.gather_candidates()

    assert len(cands_a) >= 1
    assert len(cands_b) >= 1

    offer_a = neg_a.create_offer()
    assert "candidates" in offer_a
    assert len(offer_a["candidates"]) >= 1

    pair = neg_b.select_best_candidate_pair(offer_a)
    assert pair is not None
    local_c, remote_c = pair
    assert isinstance(local_c, ICECandidate)
    assert isinstance(remote_c, ICECandidate)
