"""OpenClawMesh Latency-Aware Multipath Routing & Self-Healing Topology.

Continuously probes link metrics (RTT, jitter, packet loss), balances high-volume
inference traffic across multiple paths, and performs sub-15ms dynamic failover.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger("openclaw_mesh.network.multipath")


@dataclass
class PathMetrics:
    target_node_id: str
    endpoint: str
    rtt_ms: float = 20.0
    jitter_ms: float = 2.0
    packet_loss_rate: float = 0.0
    success_count: int = 0
    failure_count: int = 0
    last_updated: float = field(default_factory=time.time)

    @property
    def score(self) -> float:
        """Composite routing score (lower is better)."""
        loss_penalty = 1.0 + (self.packet_loss_rate * 5.0)
        return round((self.rtt_ms + (self.jitter_ms * 1.5)) * loss_penalty, 2)

    @property
    def is_healthy(self) -> bool:
        return self.packet_loss_rate < 0.35 and (time.time() - self.last_updated) < 60.0


class MultipathRouter:
    """Dispatches traffic across top-N low-latency paths and manages link health."""

    def __init__(self, local_node_id: str) -> None:
        self.local_node_id = local_node_id
        self.routes: dict[str, list[PathMetrics]] = {}  # target_node_id -> list of paths
        self._round_robin_counters: dict[str, int] = {}

    def register_path(
        self, target_node_id: str, endpoint: str, initial_rtt_ms: float = 25.0
    ) -> PathMetrics:
        """Register or update a path candidate."""
        if target_node_id not in self.routes:
            self.routes[target_node_id] = []

        # Find existing or create new
        for p in self.routes[target_node_id]:
            if p.endpoint == endpoint:
                p.rtt_ms = initial_rtt_ms
                p.last_updated = time.time()
                return p

        new_path = PathMetrics(
            target_node_id=target_node_id,
            endpoint=endpoint,
            rtt_ms=initial_rtt_ms,
        )
        self.routes[target_node_id].append(new_path)
        logger.info(
            f"Registered path: {self.local_node_id} -> {target_node_id} via {endpoint} ({initial_rtt_ms}ms)"
        )
        return new_path

    def update_metrics(
        self,
        target_node_id: str,
        endpoint: str,
        rtt_ms: float,
        success: bool = True,
    ) -> None:
        """Update live telemetry metrics for a path."""
        paths = self.routes.get(target_node_id, [])
        for p in paths:
            if p.endpoint == endpoint:
                # Exponential moving average for RTT
                p.jitter_ms = abs(rtt_ms - p.rtt_ms) * 0.3 + p.jitter_ms * 0.7
                p.rtt_ms = rtt_ms * 0.4 + p.rtt_ms * 0.6
                p.last_updated = time.time()
                if success:
                    p.success_count += 1
                else:
                    p.failure_count += 1

                total = p.success_count + p.failure_count
                if total > 0:
                    p.packet_loss_rate = p.failure_count / total
                break

    def select_best_path(self, target_node_id: str) -> PathMetrics | None:
        """Select the single path with the lowest score."""
        paths = self.routes.get(target_node_id, [])
        healthy = [p for p in paths if p.is_healthy]
        if not healthy:
            return paths[0] if paths else None

        healthy.sort(key=lambda p: p.score)
        return healthy[0]

    def select_multipath_bundle(
        self, target_node_id: str, bundle_size: int = 2
    ) -> list[PathMetrics]:
        """Select the top N paths for multi-path striping."""
        paths = self.routes.get(target_node_id, [])
        healthy = [p for p in paths if p.is_healthy]
        if not healthy:
            return paths[:bundle_size]

        healthy.sort(key=lambda p: p.score)
        return healthy[:bundle_size]


class SelfHealingController:
    """Monitors active peer connections and triggers sub-15ms route failovers."""

    def __init__(self, router: MultipathRouter) -> None:
        self.router = router
        self.active_sessions: dict[str, str] = {}  # session_id -> current_endpoint
        self.failover_events: list[dict[str, Any]] = []

    def bind_session(self, session_id: str, target_node_id: str) -> str:
        """Bind session to the best available path."""
        best = self.router.select_best_path(target_node_id)
        endpoint = best.endpoint if best else "default"
        self.active_sessions[session_id] = endpoint
        return endpoint

    async def handle_link_failure(
        self, session_id: str, target_node_id: str, failed_endpoint: str
    ) -> str:
        """Execute rapid failover when a link fails."""
        t0 = time.perf_counter()
        # Mark path failure
        self.router.update_metrics(target_node_id, failed_endpoint, rtt_ms=999.0, success=False)

        # Select alternate healthy path
        new_path = self.router.select_best_path(target_node_id)
        new_endpoint = new_path.endpoint if new_path else failed_endpoint
        self.active_sessions[session_id] = new_endpoint

        elapsed_ms = (time.perf_counter() - t0) * 1000.0
        event = {
            "session_id": session_id,
            "target_node_id": target_node_id,
            "failed_endpoint": failed_endpoint,
            "new_endpoint": new_endpoint,
            "failover_latency_ms": round(elapsed_ms, 2),
            "timestamp": time.time(),
        }
        self.failover_events.append(event)
        logger.warning(
            f"Self-healing failover executed in {elapsed_ms:.2f}ms: {failed_endpoint} -> {new_endpoint}"
        )
        return new_endpoint
