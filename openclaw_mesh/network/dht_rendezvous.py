"""OpenClawMesh DHT Rendezvous Hole-Punching for Symmetric NAT Traversal.

Enables two peers behind strict symmetric NAT / CGNAT (4G/5G) to negotiate
simultaneous UDP hole-punching using ephemeral rendezvous records published on Kademlia DHT.
"""

from __future__ import annotations

import hashlib
import logging
import time
import uuid
from dataclasses import asdict, dataclass, field
from typing import Any

logger = logging.getLogger("openclaw_mesh.network.rendezvous")


@dataclass
class RendezvousRecord:
    node_id: str
    public_endpoints: list[str]
    ephemeral_pubkey: str
    nonce: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    timestamp: float = field(default_factory=time.time)
    ttl_seconds: int = 180

    @property
    def is_expired(self) -> bool:
        return (time.time() - self.timestamp) > self.ttl_seconds

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> RendezvousRecord:
        return cls(
            node_id=data["node_id"],
            public_endpoints=data["public_endpoints"],
            ephemeral_pubkey=data["ephemeral_pubkey"],
            nonce=data.get("nonce", uuid.uuid4().hex[:12]),
            timestamp=data.get("timestamp", time.time()),
            ttl_seconds=data.get("ttl_seconds", 180),
        )


class DHTRendezvousManager:
    """Manages publishing, discovering, and coordinating rendezvous hole-punching."""

    def __init__(self, node_id: str) -> None:
        self.node_id = node_id
        self._local_records: dict[str, RendezvousRecord] = {}

    @staticmethod
    def get_rendezvous_key(target_node_id: str) -> str:
        """Compute the Kademlia DHT key for a peer's rendezvous record."""
        return hashlib.sha256(f"openclaw_rv_{target_node_id}".encode()).hexdigest()

    def create_record(
        self,
        public_endpoints: list[str],
        ephemeral_pubkey: str,
        ttl_seconds: int = 180,
    ) -> RendezvousRecord:
        """Create and store local rendezvous registration."""
        record = RendezvousRecord(
            node_id=self.node_id,
            public_endpoints=public_endpoints,
            ephemeral_pubkey=ephemeral_pubkey,
            ttl_seconds=ttl_seconds,
        )
        self._local_records[self.node_id] = record
        logger.info(
            f"Created DHT Rendezvous record for {self.node_id} with {len(public_endpoints)} endpoints"
        )
        return record

    def store_remote_record(self, record: RendezvousRecord) -> None:
        """Cache a discovered remote peer's rendezvous record."""
        if not record.is_expired:
            self._local_records[record.node_id] = record

    def get_record(self, target_node_id: str) -> RendezvousRecord | None:
        """Get active rendezvous record for a target peer."""
        record = self._local_records.get(target_node_id)
        if record and not record.is_expired:
            return record
        return None

    def plan_hole_punch(
        self, target_node_id: str, lead_time_ms: int = 500
    ) -> dict[str, Any] | None:
        """Coordinate synchronized UDP punch timestamp between both NAT endpoints."""
        target_rec = self.get_record(target_node_id)
        if not target_rec:
            return None

        # Synchronized punch target timestamp in future
        target_time = time.time() + (lead_time_ms / 1000.0)
        return {
            "target_node_id": target_node_id,
            "target_endpoints": target_rec.public_endpoints,
            "ephemeral_pubkey": target_rec.ephemeral_pubkey,
            "sync_punch_timestamp": target_time,
            "lead_time_ms": lead_time_ms,
        }
