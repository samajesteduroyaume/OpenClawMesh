"""Gestionnaire de Cache de Modèles d'Inférence LRU pour OpenClawMesh.

Empêche le rechargement disque/VRAM à chaque requête d'inférence,
stabilise le temps de génération (TTFT) et gère l'éviction propre de la mémoire.
"""

from __future__ import annotations

import asyncio
import gc
import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger("openclaw_mesh.engines.model_cache")


@dataclass
class CachedModelEntry:
    """Entrée de cache pour un modèle chargé en mémoire/VRAM."""

    model_name: str
    backend: str
    model_obj: Any
    tokenizer: Any | None = None
    loaded_at: float = field(default_factory=time.time)
    last_accessed: float = field(default_factory=time.time)
    access_count: int = 0

    def touch(self) -> None:
        """Met à jour l'horodatage d'accès."""
        self.last_accessed = time.time()
        self.access_count += 1


class ModelCache:
    """
    Cache LRU thread-safe pour modèles d'inférence (MLX, PyTorch CUDA, OpenVINO).

    Limite le nombre de modèles simultanément résidents en mémoire et décharge
    proprement les modèles inactifs les plus anciens.
    """

    def __init__(self, max_models: int = 2, max_loaded_models: int | None = None) -> None:
        # Compatibility: accept both max_models and max_loaded_models
        if max_loaded_models is not None:
            self.max_models = max(1, max_loaded_models)
        else:
            self.max_models = max(1, max_models)
        self._cache: dict[str, CachedModelEntry] = {}
        self._lock = threading.Lock()
        self._eviction_count = 0
        self._hits = 0
        self._misses = 0
        self._loading_locks: dict[str, asyncio.Lock] = {}

    def _cache_key(self, model_name: str, backend: str | None = None) -> str:
        b = backend or "default"
        return f"{b}::{model_name}"

    def get(self, model_name: str, backend: str | None = None) -> Any | None:
        """Récupère un modèle en cache si présent et actualise son statut LRU."""
        key = self._cache_key(model_name, backend)
        with self._lock:
            entry = self._cache.get(key)
            if entry is not None:
                entry.touch()
                self._hits += 1
                return entry.model_obj
            self._misses += 1
            return None

    def put(
        self,
        model_name: str,
        model_obj: Any,
        backend: str = "default",
        tokenizer: Any | None = None,
    ) -> CachedModelEntry:
        """Insère ou met à jour un modèle dans le cache en appliquant l'éviction LRU."""
        key = self._cache_key(model_name, backend)
        with self._lock:
            # Si le modèle existe déjà
            if key in self._cache:
                entry = self._cache[key]
                entry.model_obj = model_obj
                entry.tokenizer = tokenizer
                entry.touch()
                return entry

            # Éviction LRU si capacité maximale atteinte
            while len(self._cache) >= self.max_models:
                self._evict_oldest_locked()

            entry = CachedModelEntry(
                model_name=model_name,
                backend=backend,
                model_obj=model_obj,
                tokenizer=tokenizer,
            )
            entry.touch()
            self._cache[key] = entry
            logger.info(f"Modèle '{model_name}' ({backend}) mis en cache. Modèles actifs: {len(self._cache)}/{self.max_models}")
            return entry

    def _evict_oldest_locked(self) -> str | None:
        """Évince le modèle le moins récemment utilisé (doit être appelé sous lock)."""
        if not self._cache:
            return None

        oldest_key = min(self._cache.keys(), key=lambda k: self._cache[k].last_accessed)
        evicted = self._cache.pop(oldest_key)
        self._eviction_count += 1
        logger.info(f"Éviction LRU du modèle '{evicted.model_name}' ({evicted.backend}) du cache.")

        # Libération de mémoire / GPU
        del evicted.model_obj
        if evicted.tokenizer is not None:
            del evicted.tokenizer
        gc.collect()

        # Libération CUDA si applicable
        try:
            import torch
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
        except Exception:
            pass

        return oldest_key

    def clear(self) -> None:
        """Vide l'intégralité du cache."""
        with self._lock:
            keys = list(self._cache.keys())
            for k in keys:
                entry = self._cache.pop(k, None)
                if entry:
                    del entry.model_obj
                    del entry.tokenizer
            gc.collect()
            try:
                import torch
                if torch.cuda.is_available():
                    torch.cuda.empty_cache()
            except Exception:
                pass
            logger.info("Cache de modèles entièrement purgé.")

    def get_status(self) -> dict[str, Any]:
        """Retourne les métriques actuelles du cache."""
        with self._lock:
            models_info = [
                {
                    "model_name": e.model_name,
                    "backend": e.backend,
                    "loaded_at": e.loaded_at,
                    "last_accessed": e.last_accessed,
                    "access_count": e.access_count,
                }
                for e in self._cache.values()
            ]
            return {
                "active_models_count": len(self._cache),
                "max_models": self.max_models,
                "hits": self._hits,
                "misses": self._misses,
                "models": models_info,
            }

    def stats(self) -> dict[str, Any]:
        """Retourne les statistiques du cache (compatibilité avec tests)."""
        with self._lock:
            total_requests = self._hits + self._misses
            hit_ratio = self._hits / total_requests if total_requests > 0 else 0.0
            return {
                "loaded_models": len(self._cache),
                "max_models": self.max_models,
                "hits": self._hits,
                "misses": self._misses,
                "evictions": self._eviction_count,
                "hit_ratio": hit_ratio,
            }

    def invalidate(self, model_name: str, backend: str = "default") -> bool:
        """Supprime un modèle du cache."""
        key = self._cache_key(model_name, backend)
        with self._lock:
            entry = self._cache.pop(key, None)
            if entry:
                del entry.model_obj
                if entry.tokenizer is not None:
                    del entry.tokenizer
                gc.collect()
                return True
            return False

    def list_loaded(self) -> list[str]:
        """Retourne la liste des noms de modèles chargés."""
        with self._lock:
            return [entry.model_name for entry in self._cache.values()]

    async def load_or_get(self, model_name: str, loader: callable, backend: str = "default") -> Any:
        """Charge un modèle si pas en cache, sinon retourne le modèle existant."""
        key = self._cache_key(model_name, backend)
        
        # Check cache first
        with self._lock:
            entry = self._cache.get(key)
            if entry is not None:
                entry.touch()
                self._hits += 1
                return entry.model_obj
            self._misses += 1

        # Get or create lock for this specific model
        with self._lock:
            if key not in self._loading_locks:
                self._loading_locks[key] = asyncio.Lock()
        model_lock = self._loading_locks[key]

        # Try to acquire lock to load the model
        async with model_lock:
            # Double-check after acquiring lock
            with self._lock:
                entry = self._cache.get(key)
                if entry is not None:
                    entry.touch()
                    self._hits += 1
                    return entry.model_obj

            # Load the model
            model_obj = await loader(model_name)
            self.put(model_name, model_obj, backend)
            return model_obj
