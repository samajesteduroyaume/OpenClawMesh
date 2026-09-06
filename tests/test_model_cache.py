"""Tests de validation du ModelCache (LRU, verrous concurrents, éviction VRAM)."""

from __future__ import annotations

import asyncio
import time

import pytest

from openclaw_mesh.engines.model_cache import ModelCache


# ------------------------------------------------------------------ #
# Fixtures
# ------------------------------------------------------------------ #


@pytest.fixture
def cache() -> ModelCache:
    """Cache de capacité 3 pour les tests."""
    return ModelCache(max_loaded_models=3)


# ------------------------------------------------------------------ #
# Tests de base
# ------------------------------------------------------------------ #


def test_store_and_retrieve(cache: ModelCache) -> None:
    """Un modèle stocké est retrouvé immédiatement."""
    model = object()
    cache.put("model-a", model, "default")
    assert cache.get("model-a") is model


def test_miss_returns_none(cache: ModelCache) -> None:
    """Un modèle absent retourne None."""
    assert cache.get("nonexistent") is None


def test_hit_and_miss_counts(cache: ModelCache) -> None:
    """Les compteurs hits/misses sont mis à jour correctement."""
    cache.put("m", object(), "default")
    cache.get("m")          # hit
    cache.get("missing")    # miss
    stats = cache.stats()
    assert stats["hits"] >= 1
    assert stats["misses"] >= 1


# ------------------------------------------------------------------ #
# LRU Eviction
# ------------------------------------------------------------------ #


def test_lru_eviction_removes_oldest(cache: ModelCache) -> None:
    """Quand la capacité est dépassée, le modèle LRU est évincé."""
    cache.put("a", object(), "default")
    cache.put("b", object(), "default")
    cache.put("c", object(), "default")
    cache.get("b")
    cache.get("c")
    cache.put("d", object(), "default")
    assert cache.get("a") is None, "Le modèle LRU 'a' aurait dû être évincé"
    assert cache.get("d") is not None


def test_lru_access_updates_order(cache: ModelCache) -> None:
    """Accéder à un modèle le déplace en tête de la liste LRU."""
    cache.put("a", object(), "default")
    cache.put("b", object(), "default")
    cache.put("c", object(), "default")
    cache.get("a")
    cache.put("d", object(), "default")
    assert cache.get("b") is None, "Le modèle LRU 'b' aurait dû être évincé"
    assert cache.get("a") is not None


def test_eviction_count_in_stats(cache: ModelCache) -> None:
    """Le compteur d'évictions est incrémenté à chaque éviction."""
    for i in range(5):
        cache.put(f"model-{i}", object(), "default")
    stats = cache.stats()
    assert stats["evictions"] >= 2


# ------------------------------------------------------------------ #
# Chargement concurrent
# ------------------------------------------------------------------ #


@pytest.mark.asyncio
async def test_concurrent_load_calls_loader_once() -> None:
    """load_or_get ne charge le modèle qu'une seule fois sous forte concurrence."""
    call_count = 0

    async def slow_loader(name: str):
        nonlocal call_count
        await asyncio.sleep(0.05)
        call_count += 1
        return f"model-{name}"

    c = ModelCache(max_loaded_models=10)
    results = await asyncio.gather(*[c.load_or_get("shared", slow_loader) for _ in range(8)])

    assert call_count == 1, f"Le loader a été appelé {call_count} fois au lieu de 1"
    assert all(r == "model-shared" for r in results)


@pytest.mark.asyncio
async def test_different_models_load_in_parallel() -> None:
    """Des modèles différents peuvent être chargés en parallèle."""
    async def timed_loader(name: str):
        await asyncio.sleep(0.05)
        return f"loaded-{name}"

    c = ModelCache(max_loaded_models=10)
    t_start = time.perf_counter()
    await asyncio.gather(
        c.load_or_get("alpha", timed_loader),
        c.load_or_get("beta", timed_loader),
        c.load_or_get("gamma", timed_loader),
    )
    total = time.perf_counter() - t_start
    assert total < 0.12, f"Les modèles n'ont pas été chargés en parallèle ({total:.3f}s)"


# ------------------------------------------------------------------ #
# Invalidation et liste
# ------------------------------------------------------------------ #


def test_invalidate_removes_model(cache: ModelCache) -> None:
    """invalidate() supprime le modèle du cache."""
    cache.put("x", object(), "default")
    cache.invalidate("x")
    assert cache.get("x") is None


def test_clear_empties_cache(cache: ModelCache) -> None:
    """clear() vide entièrement le cache."""
    for i in range(3):
        cache.put(f"m{i}", object(), "default")
    cache.clear()
    assert cache.stats()["loaded_models"] == 0


def test_list_loaded_models(cache: ModelCache) -> None:
    """list_loaded() retourne les noms des modèles en cache."""
    cache.put("lion", object(), "default")
    cache.put("tiger", object(), "default")
    names = cache.list_loaded()
    assert "lion" in names
    assert "tiger" in names


# ------------------------------------------------------------------ #
# Métriques
# ------------------------------------------------------------------ #


def test_stats_structure(cache: ModelCache) -> None:
    """stats() retourne un dict avec les clés attendues."""
    stats = cache.stats()
    required = {"loaded_models", "max_models", "hits", "misses", "evictions", "hit_ratio"}
    assert required.issubset(stats.keys())


def test_hit_ratio_calculation(cache: ModelCache) -> None:
    """Le hit_ratio est calculé correctement."""
    cache.put("m", object(), "default")
    cache.get("m")
    cache.get("m")
    cache.get("z")
    stats = cache.stats()
    assert abs(stats["hit_ratio"] - 2 / 3) < 0.01
