"""
Gestionnaire de Base de Données SQLite pour Clés d'API & Accès OpenClawMesh (100% Free & Open-Access).

Gère les clés d'API (création, validation, décompte de quotas, expirations, profils communautaires)
et les journaux d'audit d'utilisation.
"""

from __future__ import annotations

import hashlib
import json
import secrets
import sqlite3
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from ..config import get_settings

_settings = get_settings()


def _key_audit_id(key_str: str) -> str:
    """Identifiant non réversible utilisé dans les journaux d'utilisation."""
    return hashlib.sha256(key_str.encode("utf-8")).hexdigest()[:16]


def _key_hash(key_str: str) -> str:
    """Empreinte stable utilisée pour valider une clé sans la stocker en clair."""
    return hashlib.sha256(key_str.encode("utf-8")).hexdigest()


@dataclass
class KeyRecord:
    key: str
    email: str
    plan: str
    active: bool = True
    created_at: float = field(default_factory=time.time)
    expires_at: float | None = None
    quota_limit: int = -1  # -1 = illimité
    quota_used: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)
    customer_id: str | None = None
    subscription_id: str | None = None

    def is_valid(self) -> tuple[bool, str]:
        if not self.active:
            return False, "Clé désactivée ou révoquée."
        if self.expires_at is not None and time.time() > self.expires_at:
            return False, "Clé d'API expirée."
        if self.quota_limit != -1 and self.quota_used >= self.quota_limit:
            return False, f"Quota de requêtes épuisé ({self.quota_used}/{self.quota_limit})."
        return True, "ok"

    def to_dict(self, include_key: bool = True) -> dict[str, Any]:
        data = asdict(self)
        if not include_key:
            data.pop("key", None)
        return data


class KeyDatabase:
    """Base de données SQLite autonome pour les clés d'accès et d'inférence."""

    def __init__(self, db_path: str | Path | None = None):
        self.db_path = Path(db_path or _settings.gateway_db_path).resolve()
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        """Crée les tables SQLite nécessaires."""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._get_connection() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS api_keys (
                    key TEXT PRIMARY KEY,
                    key_hash TEXT,
                    email TEXT NOT NULL,
                    plan TEXT NOT NULL,
                    active INTEGER NOT NULL DEFAULT 1,
                    created_at REAL NOT NULL,
                    expires_at REAL,
                    quota_limit INTEGER NOT NULL DEFAULT -1,
                    quota_used INTEGER NOT NULL DEFAULT 0,
                    metadata_json TEXT DEFAULT '{}',
                    customer_id TEXT,
                    subscription_id TEXT
                )
            """)
            columns = {row["name"] for row in conn.execute("PRAGMA table_info(api_keys)")}
            if "key_hash" not in columns:
                conn.execute("ALTER TABLE api_keys ADD COLUMN key_hash TEXT")
            conn.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS idx_api_keys_key_hash ON api_keys(key_hash)"
            )
            conn.execute("""
                CREATE TABLE IF NOT EXISTS usage_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    key TEXT NOT NULL,
                    skill TEXT NOT NULL,
                    ts REAL NOT NULL,
                    duration_ms REAL,
                    status TEXT NOT NULL
                )
            """)

    # ------------------------------------------------------------------ #
    # Gestion des Clés
    # ------------------------------------------------------------------ #
    def create_key(
        self,
        email: str,
        plan: str = "free_community",
        days_valid: int | None = None,
        quota_limit: int = -1,
        customer_id: str | None = None,
        subscription_id: str | None = None,
        custom_prefix: str = "sk_claw_",
        metadata: dict | None = None,
    ) -> KeyRecord:
        """Génère une nouvelle clé d'API et la persiste en base."""
        key = f"{custom_prefix}{secrets.token_hex(20)}"
        now = time.time()
        expires_at = (now + (days_valid * 86400)) if days_valid and days_valid > 0 else None

        safe_metadata = dict(metadata or {})
        safe_metadata.setdefault("key_id", _key_audit_id(key))
        meta_json = json.dumps(safe_metadata)

        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO api_keys (
                    key, key_hash, email, plan, active, created_at, expires_at,
                    quota_limit, quota_used, metadata_json, customer_id, subscription_id
                ) VALUES (NULL, ?, ?, ?, 1, ?, ?, ?, 0, ?, ?, ?)
                """,
                (
                    _key_hash(key),
                    email,
                    plan,
                    now,
                    expires_at,
                    quota_limit,
                    meta_json,
                    customer_id,
                    subscription_id,
                ),
            )

        return KeyRecord(
            key=key,
            email=email,
            plan=plan,
            active=True,
            created_at=now,
            expires_at=expires_at,
            quota_limit=quota_limit,
            quota_used=0,
            metadata=safe_metadata,
            customer_id=customer_id,
            subscription_id=subscription_id,
        )

    def get_key(self, key_str: str) -> KeyRecord | None:
        """Récupère une clé par sa valeur hachée."""
        with self._get_connection() as conn:
            row = conn.execute(
                "SELECT * FROM api_keys WHERE key_hash = ?", (_key_hash(key_str),)
            ).fetchone()
            if not row:
                row = conn.execute("SELECT * FROM api_keys WHERE key = ?", (key_str,)).fetchone()
            if not row:
                return None
            record = self._key_from_row(row)
            record.key = key_str
            return record

    def list_all_keys(self, limit: int | None = None) -> list[KeyRecord]:
        """Retourne toutes les clés enregistrées (avec limite optionnelle)."""
        with self._get_connection() as conn:
            query = "SELECT * FROM api_keys ORDER BY created_at DESC"
            params: tuple[Any, ...] = ()
            if limit is not None and limit > 0:
                query += " LIMIT ?"
                params = (limit,)
            rows = conn.execute(query, params).fetchall()
            return [self._key_from_row(r) for r in rows]

    def revoke_key(self, key_str: str) -> bool:
        """Désactive définitivement une clé."""
        with self._get_connection() as conn:
            cur = conn.execute(
                "UPDATE api_keys SET active = 0 WHERE key_hash = ? OR key = ?",
                (_key_hash(key_str), key_str),
            )
            return cur.rowcount > 0

    def revoke_key_hash(self, key_hash: str) -> bool:
        """Désactive définitivement une clé par son empreinte SHA-256."""
        with self._get_connection() as conn:
            cur = conn.execute("UPDATE api_keys SET active = 0 WHERE key_hash = ?", (key_hash,))
            return cur.rowcount > 0

    def increment_usage(
        self,
        key_str: str,
        skill_name: str = "unknown",
        duration_ms: float = 0.0,
        status_code: str = "ok",
    ) -> None:
        """Incrémente le compteur de requêtes et consigne l'audit."""
        now = time.time()
        audit_id = _key_audit_id(key_str)
        with self._get_connection() as conn:
            conn.execute(
                "UPDATE api_keys SET quota_used = quota_used + 1 WHERE key_hash = ? OR key = ?",
                (_key_hash(key_str), key_str),
            )
            conn.execute(
                "INSERT INTO usage_logs (key, skill, ts, duration_ms, status) VALUES (?, ?, ?, ?, ?)",
                (audit_id, skill_name, now, duration_ms, status_code),
            )

    def reserve_usage(self, key_str: str, skill_name: str = "unknown") -> bool:
        """Réservation atomique du quota pour éviter les courses concurrentes."""
        now = time.time()
        audit_id = _key_audit_id(key_str)
        with self._get_connection() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                "SELECT * FROM api_keys WHERE (key_hash = ? OR key = ?) AND active = 1",
                (_key_hash(key_str), key_str),
            ).fetchone()
            if not row:
                return False
            rec = self._key_from_row(row)
            rec.key = key_str
            valid, _ = rec.is_valid()
            if not valid:
                return False
            conn.execute(
                "UPDATE api_keys SET quota_used = quota_used + 1 WHERE (key_hash = ? OR key = ?) AND active = 1",
                (_key_hash(key_str), key_str),
            )
            conn.execute(
                "INSERT INTO usage_logs (key, skill, ts, duration_ms, status) VALUES (?, ?, ?, ?, ?)",
                (audit_id, skill_name, now, 0.0, "reserved"),
            )
            return True

    @staticmethod
    def _key_from_row(row: sqlite3.Row) -> KeyRecord:
        return KeyRecord(
            key="",
            email=row["email"],
            plan=row["plan"],
            active=bool(row["active"]),
            created_at=row["created_at"],
            expires_at=row["expires_at"],
            quota_limit=row["quota_limit"],
            quota_used=row["quota_used"],
            metadata=json.loads(row["metadata_json"] or "{}"),
            customer_id=row["customer_id"],
            subscription_id=row["subscription_id"],
        )
