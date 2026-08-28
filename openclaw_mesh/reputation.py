"""
Système de Réputation Décentralisé des Nœuds OpenClawMesh.

Évalue en continu la fiabilité, l'intégrité et les performances de chaque pair du maillage :
- Score de fiabilité probabiliste (0.0 à 1.0)
- Pénalisation exponentielle en cas d'erreur de calcul, de timeout ou d'échec de vérification
- Récompense progressive en cas d'inférence réussie à faible latence
- Éviction automatique des nœuds défaillants ou malveillants
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger("openclaw_mesh.reputation")

_DEFAULT_MIN_ELIGIBLE_SCORE = 0.4
_PENALTY_FAILURE = 0.15
_PENALTY_DISPUTE = 0.50
_REWARD_SUCCESS = 0.02


@dataclass
class NodeReputationRecord:
    """Historique et score de réputation d'un pair du réseau."""

    node_id: str
    node_name: str
    score: float = 1.0  # Entre 0.0 et 1.0
    successful_calls: int = 0
    failed_calls: int = 0
    dispute_count: int = 0
    avg_latency_ms: float = 0.0
    last_updated: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> NodeReputationRecord:
        return cls(
            node_id=str(data.get("node_id", "")),
            node_name=str(data.get("node_name", "unknown")),
            score=float(data.get("score", 1.0)),
            successful_calls=int(data.get("successful_calls", 0)),
            failed_calls=int(data.get("failed_calls", 0)),
            dispute_count=int(data.get("dispute_count", 0)),
            avg_latency_ms=float(data.get("avg_latency_ms", 0.0)),
            last_updated=float(data.get("last_updated", time.time())),
        )


class ReputationManager:
    """Gestionnaire de calcul de réputation pour les pairs du maillage."""

    def __init__(self, min_eligible_score: float = _DEFAULT_MIN_ELIGIBLE_SCORE):
        self.min_eligible_score = min_eligible_score
        self._records: dict[str, NodeReputationRecord] = {}

    def get_record(self, node_id: str, node_name: str = "unknown") -> NodeReputationRecord:
        """Récupère ou initialise le profil de réputation d'un nœud."""
        if node_id not in self._records:
            self._records[node_id] = NodeReputationRecord(node_id=node_id, node_name=node_name)
        return self._records[node_id]

    def record_success(self, node_id: str, latency_ms: float = 50.0, node_name: str = "unknown") -> float:
        """Enregistre un appel réussi et met à jour positivement le score."""
        rec = self.get_record(node_id, node_name)
        rec.successful_calls += 1
        # Moyenne glissante de latence
        if rec.avg_latency_ms == 0.0:
            rec.avg_latency_ms = latency_ms
        else:
            rec.avg_latency_ms = (rec.avg_latency_ms * 0.8) + (latency_ms * 0.2)

        # Bonus de score (asymptote vers 1.0)
        rec.score = min(1.0, rec.score + _REWARD_SUCCESS)
        rec.last_updated = time.time()
        return rec.score

    def record_failure(self, node_id: str, reason: str = "timeout", node_name: str = "unknown") -> float:
        """Pénalise un nœud suite à un échec d'exécution ou timeout."""
        rec = self.get_record(node_id, node_name)
        rec.failed_calls += 1
        rec.score = max(0.0, rec.score - _PENALTY_FAILURE)
        rec.last_updated = time.time()
        logger.warning(f"Pénalité réputation pour '{rec.node_name}' ({node_id[:8]}) : {rec.score:.2f} [{reason}]")
        return rec.score

    def record_dispute(self, node_id: str, reason: str = "signature_mismatch", node_name: str = "unknown") -> float:
        """Pénalise lourdement un nœud en cas de tricherie ou falsification cryptographique."""
        rec = self.get_record(node_id, node_name)
        rec.dispute_count += 1
        rec.score = max(0.0, rec.score - _PENALTY_DISPUTE)
        rec.last_updated = time.time()
        logger.error(f"DISPUTE enregistrée pour '{rec.node_name}' ({node_id[:8]}) : nouveau score={rec.score:.2f} [{reason}]")
        return rec.score

    def is_eligible(self, node_id: str) -> bool:
        """Indique si un nœud a une réputation suffisante pour recevoir du trafic."""
        rec = self._records.get(node_id)
        if rec is None:
            return True  # Nœud neuf accepté par défaut (score initial 1.0)
        return rec.score >= self.min_eligible_score

    def get_all_records(self) -> dict[str, dict[str, Any]]:
        """Retourne l'état complet de la table de réputation."""
        return {nid: rec.to_dict() for nid, rec in self._records.items()}

    def save_state(self, filepath: str | Path) -> None:
        """Sauvegarde les réputations sur disque."""
        path = Path(filepath).resolve()
        path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "saved_at": time.time(),
            "records": [r.to_dict() for r in self._records.values()],
        }
        path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

    def load_state(self, filepath: str | Path) -> int:
        """Restaure les réputations depuis le disque."""
        path = Path(filepath).resolve()
        if not path.is_file():
            return 0
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            recs = data.get("records", [])
            restored = 0
            for r in recs:
                try:
                    obj = NodeReputationRecord.from_dict(r)
                    self._records[obj.node_id] = obj
                    restored += 1
                except Exception:
                    continue
            return restored
        except Exception as exc:
            logger.warning(f"Impossible de charger la réputation depuis {path}: {exc}")
            return 0
