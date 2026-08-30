"""OpenClawMesh Federation Bridge & Inter-Domain Cluster Routing.

Enables secure inter-cluster collaboration between independent autonomous meshes
with policy-based skill ACLs, domain trust boundaries, and cross-mesh task routing.
"""

from __future__ import annotations

import logging
import time
from dataclasses import asdict, dataclass, field
from typing import Any

logger = logging.getLogger("openclaw_mesh.network.federation")


@dataclass
class MeshDomain:
    domain_id: str
    name: str
    gateway_endpoint: str
    allowed_skills: list[str]
    trust_score: float = 1.0
    public_key_hex: str = ""
    is_active: bool = True
    joined_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class FederationBridge:
    """Manages cross-mesh domain peering and ACL-governed skill invocation."""

    def __init__(self, local_domain_id: str = "domain_local") -> None:
        self.local_domain_id = local_domain_id
        self.federated_domains: dict[str, MeshDomain] = {}
        self.cross_domain_routes: dict[str, str] = {}  # skill_name -> domain_id

    def register_domain(
        self,
        domain_id: str,
        name: str,
        gateway_endpoint: str,
        allowed_skills: list[str],
        public_key_hex: str = "",
    ) -> MeshDomain:
        """Register a federated external mesh cluster."""
        domain = MeshDomain(
            domain_id=domain_id,
            name=name,
            gateway_endpoint=gateway_endpoint,
            allowed_skills=allowed_skills,
            public_key_hex=public_key_hex,
        )
        self.federated_domains[domain_id] = domain
        for skill in allowed_skills:
            self.cross_domain_routes[skill] = domain_id
        logger.info(
            f"Registered Federated Mesh Domain '{name}' ({domain_id}) with skills: {allowed_skills}"
        )
        return domain

    def check_access(self, source_domain_id: str, skill_name: str) -> bool:
        """Verify if a domain is authorized to invoke a specific skill."""
        if source_domain_id == self.local_domain_id:
            return True

        domain = self.federated_domains.get(source_domain_id)
        if not domain or not domain.is_active:
            return False

        return skill_name in domain.allowed_skills or "*" in domain.allowed_skills

    def route_federated_skill(self, skill_name: str) -> MeshDomain | None:
        """Find the best federated domain hosting the requested skill."""
        domain_id = self.cross_domain_routes.get(skill_name)
        if domain_id:
            domain = self.federated_domains.get(domain_id)
            if domain and domain.is_active:
                return domain
        return None
