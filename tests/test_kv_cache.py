
from openclaw_mesh.engines.kv_cache import SemanticKVCache


def test_semantic_kv_cache_put_get_and_hits():
    cache = SemanticKVCache(max_entries=3, default_ttl=10.0)

    # 1. Miss initial
    assert cache.get("Quel est le protocole OpenClaw ?") is None

    # 2. Put entry
    cache.put("Quel est le protocole OpenClaw ?", "OpenClaw est un maillage P2P souverain.", token_count=12)

    # 3. Hit
    entry = cache.get("Quel est le protocole OpenClaw ?")
    assert entry is not None
    assert "maillage P2P" in str(entry.data)
    assert entry.hits == 1

    stats = cache.stats()
    assert stats["total_queries"] == 2
    assert stats["total_hits"] == 1
    assert stats["total_misses"] == 1
    assert stats["hit_ratio"] == 0.5


def test_semantic_kv_cache_lru_eviction():
    cache = SemanticKVCache(max_entries=2, default_ttl=3600.0)

    cache.put("prompt_1", "res_1")
    cache.put("prompt_2", "res_2")
    assert cache.get("prompt_1") is not None  # accède à prompt_1, rendant prompt_2 le plus ancien

    # Insérer le 3ème élément -> doit évincer prompt_2
    cache.put("prompt_3", "res_3")

    assert cache.get("prompt_1") is not None
    assert cache.get("prompt_3") is not None
    assert cache.get("prompt_2") is None
