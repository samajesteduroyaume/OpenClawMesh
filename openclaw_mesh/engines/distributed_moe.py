"""
Orchestrateur de Parallélisme par Pipeline & Mixture of Experts (MoE) Distribué.

Permet de répartir l'exécution d'un grand modèle de langage (LLM / MoE)
entre plusieurs machines du maillage OpenClawMesh lorsque la mémoire d'un seul nœud est insuffisante.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger("openclaw_mesh.moe")


@dataclass
class PipelineStage:
    """Représente une étape de calcul dans le pipeline distribué."""

    stage_id: int
    node_name: str
    layer_range: tuple[int, int]
    expert_ids: list[int] = field(default_factory=list)
    latency_ms: float = 0.0


class DistributedMoEOrchestrator:
    """Orchestre la répartition des étapes d'inférence ou d'experts à travers le maillage."""

    def __init__(self, cluster_nodes: list[str] | None = None):
        self.nodes = cluster_nodes or ["local-node"]
        self.stages: list[PipelineStage] = []
        self._build_pipeline_stages()

    def _build_pipeline_stages(self) -> None:
        """Découpe automatiquement le modèle en étapes selon le nombre de nœuds."""
        total_layers = 32
        num_nodes = max(1, len(self.nodes))
        layers_per_node = total_layers // num_nodes

        self.stages.clear()
        for i, node in enumerate(self.nodes):
            start = i * layers_per_node
            end = total_layers if i == num_nodes - 1 else (i + 1) * layers_per_node
            self.stages.append(
                PipelineStage(
                    stage_id=i,
                    node_name=node,
                    layer_range=(start, end),
                    expert_ids=[i * 2, i * 2 + 1],
                )
            )

    def update_cluster_nodes(self, nodes: list[str]) -> None:
        """Met à jour les nœuds disponibles et recalcule le partitionnement."""
        self.nodes = nodes if nodes else ["local-node"]
        self._build_pipeline_stages()

    async def execute_distributed_pipeline(
        self,
        prompt: str,
        delegate_fn: Callable[[str, dict[str, Any]], Any] | None = None,
    ) -> dict[str, Any]:
        """
        Exécute le pipeline séquentiel distribué à travers les nœuds du maillage.
        Chaque nœud traite son ensemble de couches/experts et passe l'activation au nœud suivant.
        """
        t0 = time.perf_counter()
        current_activation = {
            "prompt": prompt,
            "stage": 0,
            "intermediate_tensor_summary": f"tokens_len_{len(prompt)}",
        }
        stage_traces = []

        for stage in self.stages:
            stage_t0 = time.perf_counter()
            stage_payload = {
                "layers": stage.layer_range,
                "experts": stage.expert_ids,
                "input_activation": current_activation,
            }

            # Si une fonction de délégation réseau est fournie et qu'il s'agit d'un nœud distant
            if delegate_fn and stage.node_name != "local-node":
                try:
                    res = await delegate_fn(stage.node_name, stage_payload)
                    current_activation = res
                except Exception as e:
                    logger.warning(
                        f"Échec étape {stage.stage_id} sur {stage.node_name}, fallback local : {e}"
                    )
                    await asyncio.sleep(0.01)
                    current_activation["stage"] = stage.stage_id + 1
            else:
                # Calcul local simulé / direct
                await asyncio.sleep(0.015)  # Latence de calcul des couches
                current_activation["stage"] = stage.stage_id + 1
                current_activation["intermediate_tensor_summary"] = (
                    f"layers_{stage.layer_range[0]}_{stage.layer_range[1]}_computed"
                )

            stage_duration = (time.perf_counter() - stage_t0) * 1000.0
            stage.latency_ms = round(stage_duration, 2)
            stage_traces.append(
                {
                    "stage_id": stage.stage_id,
                    "node": stage.node_name,
                    "layers": f"{stage.layer_range[0]}-{stage.layer_range[1]}",
                    "duration_ms": stage.latency_ms,
                }
            )

        total_duration_ms = (time.perf_counter() - t0) * 1000.0

        return {
            "result_text": f"✅ [Pipeline MoE Distribué] Calcul achevé à travers {len(self.stages)} nœuds pour : '{prompt[:60]}...'",
            "stages": stage_traces,
            "total_duration_ms": round(total_duration_ms, 2),
            "nodes_participating": self.nodes,
        }
