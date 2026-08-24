"""
Gestionnaire de Base de Données SQLite pour Clés d'API & Monétisation OpenClawMesh.

Gère les clés d'API (création, validation, décompte de quotas, expirations, abonnements),
les transactions de paiement et les logs d'utilisation.
"""
from __future__ import annotations
import os
import secrets
import sqlite3
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Optional


@dataclass
class KeyRecord:
    key: str
    email: str
    plan: str
    active: bool = True
    created_at: float = field(default_factory=time.time)
    expires_at: Optional[float] = None
    quota_limit: int = -1  # -1 = illimité
    quota_used: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)
    customer_id: Optional[str] = None
    subscription_id: Optional[str] = None

    def is_valid(self) -> tuple[bool, str]:
        if not self.active:
            return False, "Clé désactivée ou révoquée."
        if self.expires_at is not None and time.time() > self.expires_at:
            return False, "Clé d'API expirée."
        if self.quota_limit != -1 and self.quota_used >= self.quota_limit:
            return False, f"Quota de requêtes épuisé ({self.quota_used}/{self.quota_limit})."
        return True, "ok"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class KeyDatabase:
    """Base de données SQLite autonome pour les clés de monétisation."""

    def __init__(self, db_path: str | Path = "openclaw_keys.db"):
        self.db_path = Path(db_path).resolve()
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
            conn.execute("""
                CREATE TABLE IF NOT EXISTS payment_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_id TEXT UNIQUE,
                    provider TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    customer_email TEXT,
                    amount_cents INTEGER,
                    currency TEXT,
                    created_at REAL NOT NULL,
                    raw_payload_json TEXT
                )
            """)
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
        plan: str = "pro_monthly",
        days_valid: Optional[int] = 30,
        quota_limit: int = -1,
        customer_id: Optional[str] = None,
        subscription_id: Optional[str] = None,
        custom_prefix: str = "sk_claw_",
        metadata: Optional[dict] = None,
    ) -> KeyRecord:
        """Génère une nouvelle clé d'API et la persiste en base."""
        key = f"{custom_prefix}{secrets.token_hex(20)}"
        now = time.time()
        expires_at = (now + (days_valid * 86400)) if days_valid and days_valid > 0 else None

        import json
        meta_json = json.dumps(metadata or {})

        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO api_keys (
                    key, email, plan, active, created_at, expires_at,
                    quota_limit, quota_used, metadata_json, customer_id, subscription_id
                ) VALUES (?, ?, ?, 1, ?, ?, ?, 0, ?, ?, ?)
                """,
                (key, email, plan, now, expires_at, quota_limit, meta_json, customer_id, subscription_id),
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
            metadata=metadata or {},
            customer_id=customer_id,
            subscription_id=subscription_id,
        )

    def get_key(self, key_str: str) -> Optional[KeyRecord]:
        """Récupère une clé par sa valeur."""
        import json
        with self._get_connection() as conn:
            row = conn.execute("SELECT * FROM api_keys WHERE key = ?", (key_str.strip(),)).fetchone()
            if not row:
                return None

            return KeyRecord(
                key=row["key"],
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

    def find_by_email(self, email: str) -> list[KeyRecord]:
        """Trouve toutes les clés associées à une adresse email."""
        import json
        with self._get_connection() as conn:
            rows = conn.execute("SELECT * FROM api_keys WHERE email = ? ORDER BY created_at DESC", (email.strip().lower(),)).fetchall()
            keys = []
            for r in rows:
                keys.append(KeyRecord(
                    key=r["key"],
                    email=r["email"],
                    plan=r["plan"],
                    active=bool(r["active"]),
                    created_at=r["created_at"],
                    expires_at=r["expires_at"],
                    quota_limit=r["quota_limit"],
                    quota_used=r["quota_used"],
                    metadata=json.loads(r["metadata_json"] or "{}"),
                    customer_id=r["customer_id"],
                    subscription_id=r["subscription_id"],
                ))
            return keys

    def increment_usage(self, key_str: str, skill_name: str = "", duration_ms: float = 0.0, status: str = "ok") -> bool:
        """Incrémente le compteur d'utilisation et enregistre un log."""
        now = time.time()
        with self._get_connection() as conn:
            conn.execute("UPDATE api_keys SET quota_used = quota_used + 1 WHERE key = ?", (key_str,))
            conn.execute(
                "INSERT INTO usage_logs (key, skill, ts, duration_ms, status) VALUES (?, ?, ?, ?, ?)",
                (key_str, skill_name, now, duration_ms, status),
            )
        return True

    def revoke_key(self, key_str: str) -> bool:
        """Désactive une clé."""
        with self._get_connection() as conn:
            res = conn.execute("UPDATE api_keys SET active = 0 WHERE key = ?", (key_str,))
            return res.rowcount > 0

    def renew_subscription(self, subscription_id: str, days_extension: int = 30) -> bool:
        """Prolonge la validité d'une clé liée à un abonnement."""
        now = time.time()
        with self._get_connection() as conn:
            row = conn.execute("SELECT expires_at FROM api_keys WHERE subscription_id = ?", (subscription_id,)).fetchone()
            if not row:
                return False
            current_expiry = row["expires_at"] or now
            new_expiry = max(now, current_expiry) + (days_extension * 86400)
            conn.execute("UPDATE api_keys SET expires_at = ?, active = 1 WHERE subscription_id = ?", (new_expiry, subscription_id))
            return True

    def list_all_keys(self, limit: int = 100) -> list[KeyRecord]:
        """Liste toutes les clés existantes pour le dashboard admin."""
        import json
        with self._get_connection() as conn:
            rows = conn.execute("SELECT * FROM api_keys ORDER BY created_at DESC LIMIT ?", (limit,)).fetchall()
            return [
                KeyRecord(
                    key=r["key"],
                    email=r["email"],
                    plan=r["plan"],
                    active=bool(r["active"]),
                    created_at=r["created_at"],
                    expires_at=r["expires_at"],
                    quota_limit=r["quota_limit"],
                    quota_used=r["quota_used"],
                    metadata=json.loads(r["metadata_json"] or "{}"),
                    customer_id=r["customer_id"],
                    subscription_id=r["subscription_id"],
                )
                for r in rows
            ]

    # ------------------------------------------------------------------ #
    # Logs d'Événements de Paiement
    # ------------------------------------------------------------------ #
    def log_payment_event(
        self,
        event_id: str,
        provider: str,
        event_type: str,
        customer_email: Optional[str] = None,
        amount_cents: int = 0,
        currency: str = "eur",
        raw_payload: Optional[dict] = None,
    ) -> bool:
        import json
        with self._get_connection() as conn:
            try:
                conn.execute(
                    """
                    INSERT INTO payment_events (
                        event_id, provider, event_type, customer_email,
                        amount_cents, currency, created_at, raw_payload_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        event_id, provider, event_type, customer_email,
                        amount_cents, currency, time.time(), json.dumps(raw_payload or {})
                    )
                )
                return True
            except sqlite3.IntegrityError:
                # Événement déjà traité (idempotence)
                return False
