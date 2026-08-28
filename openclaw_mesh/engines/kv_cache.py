"""
Cache Sémantique & Prefix Caching Distribué (Semantic KV-Cache) pour OpenClawMesh.

Permet de mettre en cache les états clés-valeurs (KV-Cache) et les préfixes de prompts récurrents
au sein du cluster de nœuds d'IA pour accélérer drastiquement le Time-To-First-Token (TTFT)
et économiser la mémoire VRAM/GPU.
"""

from __future__ import annotations

import hashlib
import logging
import threading
import time
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger("openclaw_mesh.kv_cache")

_DEFAULT_MAX_ENTRIES = 1000
_DEFAULT_MAX_BYTES = 512 * 1024 * 1024  # 512 Mo max par défaut
_DEFAULT_TTL_SECONDS = 3600.0           # 1 heure de validité


@dataclass
class KVCacheEntry:
    """Entrée de cache pour un préfixe de contexte ou tenseur d'activation."""

    prefix_hash: str
    prefix_text: str
    token_count: int
    data: bytes | list[float] | Any
    data_bytes_size: int
    created_at: float = field(default_factory=time.time)
    last_accessed: float = field(default_factory=time.time)
    hits: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)

    def is_expired(self, ttl: float = _DEFAULT_TTL_SECONDS) -> bool:
        return (time.time() - self.last_accessed) > ttl

    def to_dict(self) -> dict[str, Any]:
        return {
            "prefix_hash": self.prefix_hash,
            "prefix_text": self.prefix_text[:100] + ("..." if len(self.prefix_text) > 100 else ""),
            "token_count": self.token_count,
            "data_bytes_size": self.data_bytes_size,
            "created_at": self.created_at,
            "last_accessed": self.last_accessed,
            "hits": self.hits,
            "metadata": self.metadata,
        }


class SemanticKVCache:
    """Gestionnaire de cache sémantique LRU en mémoire vive."""

    def __init__(
        self,
        max_entries: int = _DEFAULT_MAX_ENTRIES,
        max_memory_bytes: int = _DEFAULT_MAX_BYTES,
        default_ttl: float = _DEFAULT_TTL_SECONDS,
    ):
        self.max_entries = max_entries
        self.max_memory_bytes = max_memory_bytes
        self.default_ttl = default_ttl

        self._cache: OrderedDict[str, KVCacheEntry] = OrderedDict()
        self._current_memory_bytes = 0
        self._lock = threading.Lock()

        # Statistiques d'observabilité
        self.total_queries = 0
        self.total_hits = 0
        self.total_misses = 0

    @staticmethod
    def hash_prefix(text: str) -> str:
        """Génère un identifiant déterministe SHA-256 pour un préfixe de prompt."""
        normalized = text.strip().lower()
        return hashlib.sha256(normalized.encode("utf-8")).hexdigest()

    def get(self, prompt: str) -> KVCacheEntry | None:
        """Recherche une entrée exacte ou préfixée dans le cache."""
        prefix_h = self.hash_prefix(prompt)
        with self._lock:
            self.total_queries += 1
            if prefix_h in self._cache:
                entry = self._cache[prefix_h]
                if entry.is_expired(self.default_ttl):
                    self._remove_entry(prefix_h)
                    self.total_misses += 1
                    return None

                # Mettre à jour LRU et compteur
                entry.last_accessed = time.time()
                entry.hits += 1
                self._cache.move_to_end(prefix_h)
                self.total_hits += 1
                return entry

            self.total_misses += 1
            return None

    def put(
        self,
        prompt: str,
        data: bytes | list[float] | Any,
        token_count: int = 0,
        metadata: dict[str, Any] | None = None,
    ) -> KVCacheEntry:
        """Insère ou met à jour une entrée dans le cache LRU."""
        prefix_h = self.hash_prefix(prompt)
        data_size = len(data) if isinstance(data, (bytes, bytearray)) else 1024

        with self._lock:
            # Éviction si déjà existant
            if prefix_h in self._cache:
                self._remove_entry(prefix_h)

            # Éviction préventive selon capacité
            self._ensure_capacity(data_size)

            entry = KVCacheEntry(
                prefix_hash=prefix_h,
                prefix_text=prompt,
                token_count=token_count,
                data=data,
                data_bytes_size=data_size,
                metadata=metadata or {},
            )

            self._cache[prefix_h] = entry
            self._current_memory_bytes += data_size
            return entry

    def clear(self) -> None:
        """Vide l'ensemble du cache."""
        with self._lock:
            self._cache.clear()
            self._current_memory_bytes = 0

    def stats(self) -> dict[str, Any]:
        """Retourne les métriques d'efficacité du cache."""
        with self._lock:
            hit_ratio = (self.total_hits / self.total_queries) if self.total_queries > 0 else 0.0
            return {
                "entries_count": len(self._cache),
                "max_entries": self.max_entries,
                "memory_used_mb": round(self._current_memory_bytes / (1024 * 1024), 2),
                "max_memory_mb": round(self.max_memory_bytes / (1024 * 1024), 2),
                "total_queries": self.total_queries,
                "total_hits": self.total_hits,
                "total_misses": self.total_misses,
                "hit_ratio": round(hit_ratio, 4),
            }

    def _remove_entry(self, prefix_hash: str) -> None:
        """Supprime une entrée et décrémente la taille mémoire occupée."""
        entry = self._cache.pop(prefix_hash, None)
        if entry:
            self._current_memory_bytes = max(0, self._current_memory_bytes - entry.data_bytes_size)

    def _ensure_capacity(self, new_data_size: int) -> None:
        """Évince les entrées les plus anciennes (FIFO/LRU) pour libérer de l'espace."""
        # 1. Évincer les éléments expirés
        expired_keys = [
            k for k, v in self._cache.items() if v.is_expired(self.default_ttl)
        ]
        for k in expired_keys:
            self._remove_entry(k)

        # 2. Éviction LRU si limite atteinte
        while len(self._cache) >= self.max_entries or (
            (self._current_memory_bytes + new_data_size) > self.max_memory_bytes and self._cache
        ):
            # Le premier élément est le plus ancien accédé
            oldest_key, _ = next(iter(self._cache.items()))
            self._remove_entry(oldest_key)
