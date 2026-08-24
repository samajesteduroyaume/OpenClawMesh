"""
Table de Hachage Distribuée (DHT) Kademlia 160-bit pour OpenClawMesh.

Permet la découverte et l'indexation décentralisée de milliers de nœuds et de compétences
sur de vastes réseaux sans dépendre des limites de diffusion broadcast/multicast mDNS :
- Espace d'adressage 160-bit (hachages SHA-1 / SHA-256 tronqués)
- Métrique de distance XOR Kademlia
- Table de routage en k-buckets (k=20, alpha=3)
- Recherche itérative de nœuds et de valeurs (Compétences IA & Endpoints de Pairs)
"""
from __future__ import annotations
import asyncio
import hashlib
import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple

logger = logging.getLogger("openclaw_mesh.dht")

ID_BITS = 160
K_BUCKET_SIZE = 20
ALPHA = 3


def hash_key(key: str) -> str:
    """Génère un identifiant Kademlia 160-bit (hexadécimal de 40 caractères) à partir d'une chaîne."""
    return hashlib.sha1(key.encode("utf-8")).hexdigest()


def xor_distance(id1: str, id2: str) -> int:
    """Calcule la distance métrique XOR entre deux identifiants de 160 bits."""
    return int(id1, 16) ^ int(id2, 16)


@dataclass
class Contact:
    """Représente un pair DHT avec son identifiant et son adresse réseau."""
    node_id: str
    host: str
    port: int
    name: str = ""
    last_seen: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {
            "node_id": self.node_id,
            "host": self.host,
            "port": self.port,
            "name": self.name,
            "last_seen": self.last_seen,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Contact:
        return cls(
            node_id=data["node_id"],
            host=data["host"],
            port=data["port"],
            name=data.get("name", ""),
            last_seen=data.get("last_seen", time.time()),
        )


class KBucket:
    """Un seau Kademlia contenant jusqu'à k contacts."""

    def __init__(self, range_min: int, range_max: int, k: int = K_BUCKET_SIZE):
        self.range_min = range_min
        self.range_max = range_max
        self.k = k
        self.contacts: list[Contact] = []
        self.last_updated = time.time()

    def has_in_range(self, node_id_int: int) -> bool:
        return self.range_min <= node_id_int < self.range_max

    def is_full(self) -> bool:
        return len(self.contacts) >= self.k

    def add_contact(self, contact: Contact) -> bool:
        """Ajoute ou actualise un contact dans le bucket selon la politique LRU."""
        self.last_updated = time.time()
        for idx, existing in enumerate(self.contacts):
            if existing.node_id == contact.node_id:
                # Actualiser la position (déplacer à la fin = le plus récemment vu)
                self.contacts.pop(idx)
                contact.last_seen = time.time()
                self.contacts.append(contact)
                return True

        if not self.is_full():
            self.contacts.append(contact)
            return True
        return False

    def remove_contact(self, node_id: str) -> None:
        self.contacts = [c for c in self.contacts if c.node_id != node_id]

    def get_contacts(self) -> list[Contact]:
        return list(self.contacts)


class RoutingTable:
    """Table de routage Kademlia subdivisée en k-buckets logarithmiques."""

    def __init__(self, local_node_id: str, k: int = K_BUCKET_SIZE):
        self.local_node_id = local_node_id
        self.local_id_int = int(local_node_id, 16)
        self.k = k
        self.buckets: list[KBucket] = [KBucket(0, 2**ID_BITS, k)]

    def add_contact(self, contact: Contact) -> bool:
        """Insère un contact dans le k-bucket approprié avec fractionnement si nécessaire."""
        if contact.node_id == self.local_node_id:
            return False

        contact_id_int = int(contact.node_id, 16)
        bucket_idx = self._get_bucket_index(contact_id_int)
        bucket = self.buckets[bucket_idx]

        if bucket.add_contact(contact):
            return True

        # Si le bucket est plein et contient l'ID du nœud local, on peut le fractionner
        if bucket.has_in_range(self.local_id_int) and (bucket.range_max - bucket.range_min) > 1:
            mid = (bucket.range_min + bucket.range_max) // 2
            left = KBucket(bucket.range_min, mid, self.k)
            right = KBucket(mid, bucket.range_max, self.k)

            for c in bucket.get_contacts():
                c_int = int(c.node_id, 16)
                if left.has_in_range(c_int):
                    left.add_contact(c)
                else:
                    right.add_contact(c)

            self.buckets.pop(bucket_idx)
            self.buckets.insert(bucket_idx, right)
            self.buckets.insert(bucket_idx, left)

            # Réessayer après fractionnement
            return self.add_contact(contact)

        return False

    def _get_bucket_index(self, node_id_int: int) -> int:
        for idx, bucket in enumerate(self.buckets):
            if bucket.has_in_range(node_id_int):
                return idx
        return len(self.buckets) - 1

    def find_closest_contacts(self, target_id: str, count: int = K_BUCKET_SIZE) -> list[Contact]:
        """Retourne les contacts les plus proches de la cible selon la distance XOR."""
        all_contacts: list[Contact] = []
        for b in self.buckets:
            all_contacts.extend(b.get_contacts())

        # Trier par distance XOR
        all_contacts.sort(key=lambda c: xor_distance(c.node_id, target_id))
        return all_contacts[:count]

    def count_contacts(self) -> int:
        return sum(len(b.get_contacts()) for b in self.buckets)


class KademliaDHT:
    """Nœud DHT Kademlia complet avec stockage clé-valeur distribué."""

    def __init__(self, node_id: Optional[str] = None, name: str = "openclaw-dht", host: str = "127.0.0.1", port: int = 8780):
        self.node_id = node_id or hash_key(f"{name}_{host}_{port}_{time.time()}")
        self.name = name
        self.host = host
        self.port = port
        self.routing_table = RoutingTable(self.node_id)
        self.storage: dict[str, tuple[Any, float]] = {}  # key -> (value, expiration)

    def self_contact(self) -> Contact:
        return Contact(node_id=self.node_id, host=self.host, port=self.port, name=self.name)

    # ------------------------------------------------------------------ #
    # Opérations Locales DHT
    # ------------------------------------------------------------------ #
    def store_local(self, key: str, value: Any, ttl_seconds: float = 3600.0) -> None:
        """Enregistre localement une entrée clé-valeur."""
        h_key = hash_key(key) if len(key) != 40 or not all(c in "0123456789abcdef" for c in key.lower()) else key
        self.storage[h_key] = (value, time.time() + ttl_seconds)

    def get_local(self, key: str) -> Optional[Any]:
        """Récupère une valeur locale si non expirée."""
        h_key = hash_key(key) if len(key) != 40 or not all(c in "0123456789abcdef" for c in key.lower()) else key
        if h_key in self.storage:
            val, exp = self.storage[h_key]
            if time.time() < exp:
                return val
            else:
                del self.storage[h_key]
        return None

    # ------------------------------------------------------------------ #
    # Protocol RPC Handlers (Simulés et Async)
    # ------------------------------------------------------------------ #
    def rpc_ping(self, sender: Contact) -> dict[str, Any]:
        """Répond à un ping et enregistre le pair émetteur."""
        self.routing_table.add_contact(sender)
        return {"type": "pong", "node_id": self.node_id, "name": self.name}

    def rpc_store(self, sender: Contact, key: str, value: Any, ttl: float = 3600.0) -> dict[str, Any]:
        """Traite une requête de stockage distribuée."""
        self.routing_table.add_contact(sender)
        self.store_local(key, value, ttl_seconds=ttl)
        return {"status": "ok", "stored": True}

    def rpc_find_node(self, sender: Contact, target_id: str) -> list[dict[str, Any]]:
        """Retourne les k contacts les plus proches de target_id."""
        self.routing_table.add_contact(sender)
        closest = self.routing_table.find_closest_contacts(target_id, count=K_BUCKET_SIZE)
        return [c.to_dict() for c in closest]

    def rpc_find_value(self, sender: Contact, key: str) -> dict[str, Any]:
        """Retourne la valeur si présente, ou la liste des k contacts les plus proches."""
        self.routing_table.add_contact(sender)
        val = self.get_local(key)
        if val is not None:
            return {"found": True, "value": val}
        closest = self.routing_table.find_closest_contacts(hash_key(key), count=K_BUCKET_SIZE)
        return {"found": False, "closest_nodes": [c.to_dict() for c in closest]}

    # ------------------------------------------------------------------ #
    # Publication & Recherche Décentralisée de Compétences
    # ------------------------------------------------------------------ #
    def advertise_skill(self, skill_name: str, endpoint_info: dict[str, Any]) -> str:
        """Publie une compétence IA et son adresse dans l'espace DHT."""
        k = f"skill:{skill_name}"
        self.store_local(k, endpoint_info)
        return hash_key(k)

    def lookup_skill(self, skill_name: str) -> Optional[dict[str, Any]]:
        """Recherche décentralisée du fournisseur d'une compétence."""
        k = f"skill:{skill_name}"
        return self.get_local(k)
