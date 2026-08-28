"""
Table de Hachage Distribuée (DHT) Kademlia 160-bit pour OpenClawMesh.

Permet la découverte et l'indexation décentralisée de milliers de nœuds et de compétences
sur de vastes réseaux sans dépendre des limites de diffusion broadcast/multicast mDNS :
- Espace d'adressage 160-bit (hachages SHA-1 / SHA-256 tronqués)
- Métrique de distance XOR Kademlia
- Table de routage en k-buckets (k=20, alpha=3)
- Recherche itérative de nœuds et de valeurs (Compétences IA & Endpoints de Pairs)
- Transport réseau réel UDP asynchrone (protocole JSON-RPC Kademlia)
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import logging
import secrets
import time
from collections.abc import Callable, Coroutine
from dataclasses import dataclass, field
from typing import Any

from ..config import get_settings

logger = logging.getLogger("openclaw_mesh.dht")
_settings = get_settings()

ID_BITS = _settings.dht_id_bits
K_BUCKET_SIZE = _settings.dht_k_bucket_size
ALPHA = _settings.dht_alpha
RPC_TIMEOUT = _settings.dht_transport_timeout
DEFAULT_TTL = _settings.dht_default_ttl_seconds
MAX_DHT_TTL = 7 * 24 * 3600
MAX_DHT_VALUE_BYTES = 256 * 1024
_DHT_SIGNATURE_FIELD = "signature"

# Limites de recherche itérative
MAX_DHT_HOPS = 20


def hash_key(key: str) -> str:
    """Génère un identifiant Kademlia 160-bit (hexadécimal de 40 caractères) à partir d'une chaîne."""
    return hashlib.sha1(key.encode("utf-8")).hexdigest()


def _is_hex_id(candidate: str) -> bool:
    """Vrai si la chaîne est un identifiant Kademlia existant (40 hexadécimaux)."""
    if len(candidate) != 40:
        return False
    try:
        int(candidate, 16)
        return True
    except ValueError:
        return False


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

    def __post_init__(self) -> None:
        if not isinstance(self.node_id, str) or not _is_hex_id(self.node_id.lower()):
            raise ValueError("node_id DHT invalide")
        self.node_id = self.node_id.lower()
        if not isinstance(self.host, str) or not self.host or len(self.host) > 255:
            raise ValueError("hôte DHT invalide")
        if not isinstance(self.port, int) or not 1 <= self.port <= 65535:
            raise ValueError("port DHT invalide")
        if not isinstance(self.name, str) or len(self.name) > 128:
            raise ValueError("nom DHT invalide")

    @property
    def address(self) -> tuple[str, int]:
        """Adresse réseau UDP (host, port) du pair."""
        return (self.host, self.port)

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

        all_contacts.sort(key=lambda c: xor_distance(c.node_id, target_id))
        return all_contacts[:count]

    def count_contacts(self) -> int:
        return sum(len(b.get_contacts()) for b in self.buckets)


# ---------------------------------------------------------------------- #
# Transport UDP Réseau Réel (Kademlia JSON-RPC)
# ---------------------------------------------------------------------- #
class _DatagramProtocol(asyncio.DatagramProtocol):
    """Protocol UDP low-level qui délègue la réception au nœud DHT."""

    def __init__(self, node: KademliaDHT):
        self.node = node
        self.transport: asyncio.Transport | None = None

    def connection_made(self, transport: asyncio.BaseTransport) -> None:
        self.transport = transport  # type: ignore[assignment]
        sockname = transport.get_extra_info("sockname")
        if sockname:
            host, port = sockname[0], sockname[1]
            self.node._bound_host = host
            self.node._bound_port = port
        self.node._set_bound()

    def connection_lost(self, exc: Exception | None) -> None:
        self.transport = None

    def datagram_received(self, data: bytes, addr: tuple[str, int]) -> None:
        self.node._handle_datagram(data, addr)

    def error_received(self, exc: Exception) -> None:
        logger.debug(f"Erreur transport UDP DHT: {exc}")


class KademliaDHT:
    """Nœud DHT Kademlia complet avec transport UDP réseau et stockage clé-valeur distribué."""

    def __init__(
        self,
        node_id: str | None = None,
        name: str = "openclaw-dht",
        host: str = "127.0.0.1",
        port: int = 8780,
        psk: str | None = None,
    ):
        self.node_id = node_id or hash_key(f"{name}_{host}_{port}_{time.time()}")
        self.name = name
        self.host = host
        self.port = port
        self.psk = psk or _settings.psk
        self.routing_table = RoutingTable(self.node_id)
        self.storage: dict[str, tuple[Any, float]] = {}  # key -> (value, expiration)

        # --- Transport réseau UDP ---
        self._transport: asyncio.DatagramTransport | None = None
        self._protocol: _DatagramProtocol | None = None
        self._pending: dict[str, asyncio.Future[dict[str, Any] | None]] = {}  # txid -> Future
        self._bound = False
        self._bound_host: str | None = None
        self._bound_port: int | None = None
        self._bound_event: asyncio.Event | None = None
        self._loop: asyncio.AbstractEventLoop | None = None

    def self_contact(self) -> Contact:
        return Contact(
            node_id=self.node_id,
            host=self._bound_host or self.host,
            port=self._bound_port or self.port,
            name=self.name,
        )

    @property
    def is_listening(self) -> bool:
        """Vrai si le transport UDP est actif et écoute sur le réseau."""
        return self._transport is not None

    def _set_bound(self) -> None:
        if self._bound_event is not None and not self._bound_event.is_set():
            self._bound = True
            self._bound_event.set()

    # ------------------------------------------------------------------ #
    # Opérations Locales DHT
    # ------------------------------------------------------------------ #
    def store_local(self, key: str, value: Any, ttl_seconds: float = DEFAULT_TTL) -> None:
        """Enregistre localement une entrée clé-valeur."""
        if not isinstance(key, str) or not key or ttl_seconds <= 0 or ttl_seconds > MAX_DHT_TTL:
            raise ValueError("Clé ou TTL DHT invalide")
        if (
            len(json.dumps(value, separators=(",", ":"), default=str).encode("utf-8"))
            > MAX_DHT_VALUE_BYTES
        ):
            raise ValueError("Valeur DHT trop volumineuse")
        h_key = hash_key(key) if not _is_hex_id(key) else key
        self.storage[h_key] = (value, time.time() + ttl_seconds)

    def get_local(self, key: str) -> Any | None:
        """Récupère une valeur locale si non expirée."""
        h_key = hash_key(key) if not _is_hex_id(key) else key
        if h_key in self.storage:
            val, exp = self.storage[h_key]
            if time.time() < exp:
                return val
            else:
                del self.storage[h_key]
        return None

    # ------------------------------------------------------------------ #
    # Transport UDP Réseau Réel
    # ------------------------------------------------------------------ #
    async def start_network(
        self, host: str | None = None, port: int | None = None
    ) -> tuple[str, int]:
        """Démarre l'écoute UDP Kademlia. Retourne (host, port) réellement liés."""
        if self._transport is not None:
            return (self._bound_host or self.host, self._bound_port or self.port)

        self._loop = asyncio.get_running_loop()
        self._bound_event = asyncio.Event()
        self.host = host or self.host
        self.port = port or self.port

        self._transport, self._protocol = await self._loop.create_datagram_endpoint(
            lambda: _DatagramProtocol(self),
            local_addr=(self.host, self.port),
        )
        # On UDP, connection_made fires immediately during endpoint creation
        if not self._bound_event.is_set():
            try:
                await asyncio.wait_for(self._bound_event.wait(), timeout=1.0)
            except asyncio.TimeoutError:
                self._set_bound()
        return (self._bound_host or self.host, self._bound_port or self.port)

    async def stop_network(self) -> None:
        """Arrête l'écoute UDP."""
        if self._transport is not None:
            self._transport.close()
            self._transport = None
        self._protocol = None
        self._bound = False
        self._bound_host = None
        self._bound_port = None
        for fut in list(self._pending.values()):
            if not fut.done():
                fut.set_result(None)
        self._pending.clear()

    def _send_raw(self, addr: tuple[str, int], message: dict[str, Any]) -> None:
        """Envoie un message JSON au pair (sans attendre de réponse)."""
        if self._transport is None:
            raise RuntimeError("Transport UDP non démarré : appelez start_network() d'abord.")
        if not self.psk and addr[0] not in {"127.0.0.1", "::1", "localhost"}:
            logger.warning("RPC DHT non authentifiée rejetée depuis %s", addr)
            return
        if self.psk:
            unsigned = {key: value for key, value in message.items() if key != _DHT_SIGNATURE_FIELD}
            canonical = json.dumps(unsigned, sort_keys=True, separators=(",", ":"))
            message = {
                **unsigned,
                _DHT_SIGNATURE_FIELD: hmac.new(
                    self.psk.encode("utf-8"), canonical.encode("utf-8"), hashlib.sha256
                ).hexdigest(),
            }
        self._transport.sendto(json.dumps(message).encode("utf-8"), addr)

    def _reply(self, addr: tuple[str, int], txid: str | None, payload: dict[str, Any]) -> None:
        """Envoie une réponse en conservant l'identifiant de transaction."""
        if txid:
            payload = {"txid": txid, **payload}
        self._send_raw(addr, payload)

    def _handle_datagram(self, data: bytes, addr: tuple[str, int]) -> None:
        """Point d'entrée de tout datagramme UDP reçu : répartit entre réponses et requêtes."""
        if len(data) > MAX_DHT_VALUE_BYTES:
            logger.warning("Paquet UDP DHT trop volumineux de %s", addr)
            return
        try:
            msg = json.loads(data.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            logger.debug(f"Paquet UDP DHT JSON invalide de {addr}")
            return
        if not isinstance(msg, dict):
            return
        if self.psk:
            signature = msg.get(_DHT_SIGNATURE_FIELD)
            unsigned = {key: value for key, value in msg.items() if key != _DHT_SIGNATURE_FIELD}
            canonical = json.dumps(unsigned, sort_keys=True, separators=(",", ":"))
            expected = hmac.new(
                self.psk.encode("utf-8"), canonical.encode("utf-8"), hashlib.sha256
            ).hexdigest()
            if not isinstance(signature, str) or not hmac.compare_digest(expected, signature):
                logger.warning("RPC DHT non authentifiée rejetée depuis %s", addr)
                return

        txid = msg.get("txid")
        msg_type = msg.get("type")
        node_id = msg.get("node_id", "")
        try:
            sender = Contact(node_id=node_id, host=addr[0], port=addr[1], name=msg.get("name", ""))
        except (TypeError, ValueError):
            logger.warning("Contact DHT invalide reçu de %s", addr)
            return
        if node_id and node_id != self.node_id:
            self.routing_table.add_contact(sender)

        # 1. Réponse à une requête émise localement → résolution de la future
        if msg_type in ("pong", "find_node_response", "find_value_response", "store_response"):
            fut = self._pending.pop(txid or "", None)
            if fut is not None and not fut.done():
                fut.set_result(msg)
            return

        # 2. Requête entrante → dispatch vers le handler RPC local
        if msg_type == "ping":
            self._reply(addr, txid, self.rpc_ping(sender))
        elif msg_type == "find_node":
            contacts = self.rpc_find_node(sender, msg.get("target", ""))
            self._reply(
                addr,
                txid,
                {
                    "type": "find_node_response",
                    "node_id": self.node_id,
                    "name": self.name,
                    "contacts": contacts,
                },
            )
        elif msg_type == "find_value":
            result = self.rpc_find_value(sender, msg.get("target_key", ""))
            self._reply(
                addr,
                txid,
                {
                    "type": "find_value_response",
                    "node_id": self.node_id,
                    "name": self.name,
                    **result,
                },
            )
        elif msg_type == "store":
            try:
                resp = self.rpc_store(
                    sender, msg.get("key", ""), msg.get("value"), ttl=msg.get("ttl", DEFAULT_TTL)
                )
            except (TypeError, ValueError, OverflowError) as exc:
                resp = {"status": "error", "stored": False, "error": str(exc)}
            self._reply(
                addr,
                txid,
                {"type": "store_response", "node_id": self.node_id, "name": self.name, **resp},
            )

    async def send_rpc(
        self, contact: Contact, message: dict[str, Any], timeout: float = RPC_TIMEOUT
    ) -> dict[str, Any] | None:
        """Envoie une requête RPC à un pair et attend la réponse (corrélée par txid)."""
        txid = secrets.token_hex(4)
        msg = {"txid": txid, "node_id": self.node_id, "name": self.name, **message}
        loop = self._loop or asyncio.get_running_loop()
        fut: asyncio.Future[dict[str, Any] | None] = loop.create_future()
        self._pending[txid] = fut
        try:
            self._send_raw(contact.address, msg)
            return await asyncio.wait_for(fut, timeout=timeout)
        except asyncio.TimeoutError:
            logger.debug(f"Timeout RPC {message.get('type')} vers {contact.node_id[:8]}")
            return None
        except Exception as e:
            logger.debug(f"Erreur RPC {message.get('type')} vers {contact.node_id[:8]}: {e}")
            return None
        finally:
            self._pending.pop(txid, None)

    # ------------------------------------------------------------------ #
    # RPC Réseau (client)
    # ------------------------------------------------------------------ #
    async def ping(self, contact: Contact, timeout: float = RPC_TIMEOUT) -> bool:
        """Ping réseau d'un pair. Retourne True si le pair répond."""
        resp = await self.send_rpc(contact, {"type": "ping"}, timeout=timeout)
        return bool(resp and resp.get("type") == "pong")

    async def find_node(
        self, contact: Contact, target_id: str, timeout: float = RPC_TIMEOUT
    ) -> list[Contact]:
        """Recherche les k contacts les plus proches de target_id chez un pair."""
        resp = await self.send_rpc(
            contact, {"type": "find_node", "target": target_id}, timeout=timeout
        )
        if not resp:
            return []
        return [Contact.from_dict(c) for c in resp.get("contacts", [])]

    async def find_value(
        self, contact: Contact, key: str, timeout: float = RPC_TIMEOUT
    ) -> tuple[Any, list[Contact]]:
        """
        Recherche une valeur chez un pair.
        Retourne (valeur, []) si trouvée, (None, contacts_proches) sinon.
        """
        target_key = key if _is_hex_id(key) else hash_key(key)
        resp = await self.send_rpc(
            contact, {"type": "find_value", "target_key": target_key}, timeout=timeout
        )
        if not resp:
            return None, []
        if resp.get("found"):
            return resp.get("value"), []
        return None, [Contact.from_dict(c) for c in resp.get("closest_nodes", [])]

    async def store(
        self,
        contact: Contact,
        key: str,
        value: Any,
        ttl: float = DEFAULT_TTL,
        timeout: float = RPC_TIMEOUT,
    ) -> bool:
        """Dépose une entrée clé-valeur sur un pair."""
        target_key = key if _is_hex_id(key) else hash_key(key)
        resp = await self.send_rpc(
            contact,
            {"type": "store", "key": target_key, "value": value, "ttl": ttl},
            timeout=timeout,
        )
        return bool(resp and resp.get("status") == "ok")

    async def bootstrap(self, contacts: list[Contact], timeout: float = RPC_TIMEOUT) -> int:
        """
        Rejoint le réseau en pinggant les contacts de départ et en les inscrivant
        dans la table de routage. Retourne le nombre de pairs joignables.
        """
        reachable = 0
        for c in contacts:
            if await self.ping(c, timeout=timeout):
                reachable += 1
        return reachable

    # ------------------------------------------------------------------ #
    # Recherches Itératives Distribuées (Kademlia)
    # ------------------------------------------------------------------ #
    async def _iterative_lookup(
        self,
        target_id: str,
        fetch: Callable[[Contact, float], Coroutine[Any, Any, tuple[Any, list[Contact]]]],
        timeout: float = RPC_TIMEOUT,
        max_steps: int = MAX_DHT_HOPS,
    ) -> tuple[Any, list[Contact]]:
        """
        Parcours itératif Kademlia vers `target_id` en interrogeant alpha noeuds en parallèle.

        `fetch(contact)` doit retourner (found_value | None, returned_contacts: list[Contact]).
        S'arrête quand la valeur est trouvée ou qu'aucun nœud plus proche n'est disponible.
        """
        alpha = ALPHA
        candidates = self.routing_table.find_closest_contacts(target_id, K_BUCKET_SIZE * 2)
        candidates = [c for c in candidates if c.node_id != self.node_id]
        candidates.sort(key=lambda c: xor_distance(c.node_id, target_id))

        visited: set[str] = set()
        result_value: Any = None
        closest: list[Contact] = candidates[:K_BUCKET_SIZE]

        for _ in range(max_steps):
            to_query = [c for c in candidates if c.node_id not in visited][:alpha]
            if not to_query:
                break

            async def _query(c: Contact) -> tuple[Any, list[Contact]]:
                visited.add(c.node_id)
                try:
                    return await fetch(c, timeout)
                except Exception as e:
                    logger.debug(f"Erreur lookup depuis {c.node_id[:8]}: {e}")
                    return None, []

            outcomes = await asyncio.gather(*[_query(c) for c in to_query])

            new_contacts: list[Contact] = []
            found_value: Any = None
            for value, cts in outcomes:
                if value is not None:
                    found_value = value
                new_contacts.extend(cts)

            # Intégration des nouveaux contacts
            existing = {c.node_id for c in candidates}
            for c in new_contacts:
                if (
                    c.node_id != self.node_id
                    and c.node_id not in existing
                    and c.node_id not in visited
                ):
                    candidates.append(c)
                    existing.add(c.node_id)

            candidates.sort(key=lambda c: xor_distance(c.node_id, target_id))
            closest = candidates[:K_BUCKET_SIZE]

            if found_value is not None:
                result_value = found_value
                break

        return result_value, closest

    async def find_value_distributed(
        self, key: str, timeout: float = RPC_TIMEOUT, max_steps: int = MAX_DHT_HOPS
    ) -> Any:
        """Recherche une valeur dans le réseau DHT de manière itérative (Kademlia FIND_VALUE)."""
        local = self.get_local(key)
        if local is not None:
            return local
        if self._transport is None:
            return None

        target_id = key if _is_hex_id(key) else hash_key(key)

        async def _fetch(contact: Contact, t: float) -> tuple[Any, list[Contact]]:
            return await self.find_value(contact, key, timeout=t)

        value, _closest = await self._iterative_lookup(
            target_id, _fetch, timeout=timeout, max_steps=max_steps
        )
        return value

    async def find_node_distributed(
        self, target_id: str, timeout: float = RPC_TIMEOUT, max_steps: int = MAX_DHT_HOPS
    ) -> list[Contact]:
        """Recherche itérative des k contacts les plus proches d'un identifiant cible."""
        if self._transport is None:
            return self.routing_table.find_closest_contacts(target_id, K_BUCKET_SIZE)

        async def _fetch(contact: Contact, t: float) -> tuple[Any, list[Contact]]:
            contacts = await self.find_node(contact, target_id, timeout=t)
            return None, contacts

        _, closest = await self._iterative_lookup(
            target_id, _fetch, timeout=timeout, max_steps=max_steps
        )
        return closest

    async def store_distributed(
        self, key: str, value: Any, ttl: float = DEFAULT_TTL, timeout: float = RPC_TIMEOUT
    ) -> bool:
        """
        Dépose une entrée sur les k nœuds les plus proches de la clé (Kademlia STORE).
        Le nœud local stocke toujours localement en premier.
        """
        self.store_local(key, value, ttl_seconds=ttl)
        if self._transport is None:
            return True

        target_id = key if _is_hex_id(key) else hash_key(key)
        closest = await self.find_node_distributed(target_id, timeout=timeout)
        if not closest:
            return True

        successes = 0
        for c in closest[:K_BUCKET_SIZE]:
            if await self.store(c, target_id, value, ttl=ttl, timeout=timeout):
                successes += 1
        return successes > 0

    # ------------------------------------------------------------------ #
    # Protocol RPC Handlers (Locaux — invoqués par le transport réseau)
    # ------------------------------------------------------------------ #
    def rpc_ping(self, sender: Contact) -> dict[str, Any]:
        """Répond à un ping et enregistre le pair émetteur."""
        self.routing_table.add_contact(sender)
        return {"type": "pong", "node_id": self.node_id, "name": self.name}

    def rpc_store(
        self, sender: Contact, key: str, value: Any, ttl: float = DEFAULT_TTL
    ) -> dict[str, Any]:
        """Traite une requête de stockage distribuée."""
        if ttl <= 0 or ttl > MAX_DHT_TTL:
            raise ValueError("TTL DHT hors limites")
        if not isinstance(key, str) or not key or len(key) > 512:
            raise ValueError("Clé DHT invalide")
        if (
            len(json.dumps(value, separators=(",", ":"), default=str).encode("utf-8"))
            > MAX_DHT_VALUE_BYTES
        ):
            raise ValueError("Valeur DHT trop volumineuse")
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
        target_id = key if _is_hex_id(key) else hash_key(key)
        closest = self.routing_table.find_closest_contacts(target_id, count=K_BUCKET_SIZE)
        return {"found": False, "closest_nodes": [c.to_dict() for c in closest]}

    # ------------------------------------------------------------------ #
    # Publication & Recherche Décentralisée de Compétences
    # ------------------------------------------------------------------ #
    def advertise_skill(self, skill_name: str, endpoint_info: dict[str, Any]) -> str:
        """Publie une compétence IA et son adresse dans l'espace DHT localement."""
        k = f"skill:{skill_name}"
        self.store_local(k, endpoint_info)
        return hash_key(k)

    def lookup_skill(self, skill_name: str) -> dict[str, Any] | None:
        """Recherche locale du fournisseur d'une compétence (utilise la DHT réseau via lookup_skill_distributed)."""
        k = f"skill:{skill_name}"
        return self.get_local(k)

    async def lookup_skill_distributed(
        self, skill_name: str, timeout: float = RPC_TIMEOUT
    ) -> Any | None:
        """Recherche décentralisée du fournisseur d'une compétence sur le réseau DHT."""
        k = f"skill:{skill_name}"
        local = self.get_local(k)
        if local is not None:
            return local
        if self._transport is None:
            return None
        return await self.find_value_distributed(k, timeout=timeout)

    async def advertise_skill_distributed(
        self, skill_name: str, endpoint_info: dict[str, Any]
    ) -> bool:
        """Publie une compétence dans le réseau DHT décentralisé (k nœuds les plus proches)."""
        k = f"skill:{skill_name}"
        return await self.store_distributed(k, endpoint_info)
