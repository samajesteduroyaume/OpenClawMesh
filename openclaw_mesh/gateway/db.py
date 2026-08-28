"""
Gestionnaire de Base de Données SQLite pour Clés d'API & Monétisation OpenClawMesh.

Gère les clés d'API (création, validation, décompte de quotas, expirations, abonnements),
les transactions de paiement et les logs d'utilisation.
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
    """Base de données SQLite autonome pour les clés de monétisation."""

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
            # Migration des anciennes installations : l'empreinte est conservée,
            # la valeur secrète n'est plus persistée.
            conn.execute(
                "UPDATE api_keys SET key_hash = ? WHERE (key_hash IS NULL OR key_hash = '') AND key IS NOT NULL AND key != ''",
                (_key_hash(""),),
            )
            legacy_rows = conn.execute(
                "SELECT rowid, key FROM api_keys WHERE key IS NOT NULL AND key != '' AND (key_hash IS NULL OR key_hash = ?)",
                (_key_hash(""),),
            ).fetchall()
            for legacy_row in legacy_rows:
                conn.execute(
                    "UPDATE api_keys SET key_hash = ?, key = NULL WHERE rowid = ?",
                    (_key_hash(legacy_row["key"]), legacy_row["rowid"]),
                )
            conn.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS idx_api_keys_key_hash ON api_keys(key_hash)"
            )
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
                    raw_payload_json TEXT,
                    txid TEXT
                )
            """)
            columns = {row["name"] for row in conn.execute("PRAGMA table_info(payment_events)")}
            if "txid" not in columns:
                conn.execute("ALTER TABLE payment_events ADD COLUMN txid TEXT")
            conn.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS idx_payment_events_bitcoin_txid "
                "ON payment_events(provider, txid) WHERE provider = 'bitcoin' AND txid IS NOT NULL"
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
            payment_rows = conn.execute(
                "SELECT event_id, raw_payload_json FROM payment_events"
            ).fetchall()
            for payment_row in payment_rows:
                try:
                    payment_data = json.loads(payment_row["raw_payload_json"] or "{}")
                except (TypeError, ValueError):
                    continue
                legacy_key = payment_data.pop("confirmed_key", None)
                if legacy_key and "confirmed_key_hash" not in payment_data:
                    payment_data["confirmed_key_hash"] = _key_hash(legacy_key)
                    conn.execute(
                        "UPDATE payment_events SET raw_payload_json = ? WHERE event_id = ?",
                        (json.dumps(payment_data), payment_row["event_id"]),
                    )

    # ------------------------------------------------------------------ #
    # Gestion des Clés
    # ------------------------------------------------------------------ #
    def create_key(
        self,
        email: str,
        plan: str = "pro_monthly",
        days_valid: int | None = 30,
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

        import json

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
        """Récupère une clé par sa valeur."""
        import json

        with self._get_connection() as conn:
            normalized_key = key_str.strip()
            row = conn.execute(
                "SELECT * FROM api_keys WHERE key_hash = ?", (_key_hash(normalized_key),)
            ).fetchone()
            if not row:
                return None

            return KeyRecord(
                key=normalized_key,
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
            rows = conn.execute(
                "SELECT * FROM api_keys WHERE email = ? ORDER BY created_at DESC",
                (email.strip().lower(),),
            ).fetchall()
            keys = []
            for r in rows:
                keys.append(
                    KeyRecord(
                        key="",
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
                )
            return keys

    def increment_usage(
        self, key_str: str, skill_name: str = "", duration_ms: float = 0.0, status: str = "ok"
    ) -> bool:
        """Incrémente le compteur d'utilisation et enregistre un log."""
        now = time.time()
        with self._get_connection() as conn:
            conn.execute(
                "UPDATE api_keys SET quota_used = quota_used + 1 WHERE key_hash = ?",
                (_key_hash(key_str),),
            )
            conn.execute(
                "INSERT INTO usage_logs (key, skill, ts, duration_ms, status) VALUES (?, ?, ?, ?, ?)",
                (_key_audit_id(key_str), skill_name, now, duration_ms, status),
            )
        return True

    def reserve_usage(self, key_str: str, skill_name: str = "") -> bool:
        """Réserve atomiquement une unité de quota avant exécution."""
        now = time.time()
        with self._get_connection() as conn:
            result = conn.execute(
                "UPDATE api_keys SET quota_used = quota_used + 1 WHERE key_hash = ? "
                "AND active = 1 AND (quota_limit = -1 OR quota_used < quota_limit)",
                (_key_hash(key_str),),
            )
            if result.rowcount != 1:
                return False
            conn.execute(
                "INSERT INTO usage_logs (key, skill, ts, duration_ms, status) VALUES (?, ?, ?, ?, ?)",
                (_key_audit_id(key_str), skill_name, now, 0.0, "reserved"),
            )
            return True

    def revoke_key(self, key_str: str) -> bool:
        """Désactive une clé."""
        with self._get_connection() as conn:
            res = conn.execute(
                "UPDATE api_keys SET active = 0 WHERE key_hash = ?", (_key_hash(key_str),)
            )
            return res.rowcount > 0

    def revoke_key_hash(self, key_hash: str) -> bool:
        """Désactive une clé à partir de son empreinte persistée."""
        with self._get_connection() as conn:
            res = conn.execute("UPDATE api_keys SET active = 0 WHERE key_hash = ?", (key_hash,))
            return res.rowcount > 0

    def renew_subscription(self, subscription_id: str, days_extension: int = 30) -> bool:
        """Prolonge la validité d'une clé liée à un abonnement."""
        now = time.time()
        with self._get_connection() as conn:
            row = conn.execute(
                "SELECT expires_at FROM api_keys WHERE subscription_id = ?", (subscription_id,)
            ).fetchone()
            if not row:
                return False
            current_expiry = row["expires_at"] or now
            new_expiry = max(now, current_expiry) + (days_extension * 86400)
            conn.execute(
                "UPDATE api_keys SET expires_at = ?, active = 1 WHERE subscription_id = ?",
                (new_expiry, subscription_id),
            )
            return True

    def list_all_keys(self, limit: int = 100) -> list[KeyRecord]:
        """Liste toutes les clés existantes pour le dashboard admin."""
        import json

        with self._get_connection() as conn:
            rows = conn.execute(
                "SELECT * FROM api_keys ORDER BY created_at DESC LIMIT ?", (limit,)
            ).fetchall()
            return [
                KeyRecord(
                    key="",
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
        customer_email: str | None = None,
        amount_cents: int = 0,
        currency: str = "eur",
        raw_payload: dict | None = None,
        txid: str | None = None,
    ) -> bool:
        import json

        with self._get_connection() as conn:
            try:
                conn.execute(
                    """
                    INSERT INTO payment_events (
                        event_id, provider, event_type, customer_email,
                        amount_cents, currency, created_at, raw_payload_json, txid
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        event_id,
                        provider,
                        event_type,
                        customer_email,
                        amount_cents,
                        currency,
                        time.time(),
                        json.dumps(raw_payload or {}),
                        txid,
                    ),
                )
                return True
            except sqlite3.IntegrityError:
                # Événement déjà traité (idempotence)
                return False

    def confirm_payment(
        self,
        event_id: str,
        *,
        quota_limit: int = -1,
        days_valid: int | None = None,
        confirmed_by: str = "admin",
        confirmation_metadata: dict[str, Any] | None = None,
    ) -> KeyRecord | None:
        """Confirme un paiement et crée sa clé dans une transaction atomique."""
        import json

        now = time.time()
        with self._get_connection() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                "SELECT * FROM payment_events WHERE event_id = ?", (event_id,)
            ).fetchone()
            if not row:
                return None

            raw_data = json.loads(row["raw_payload_json"] or "{}")
            existing_key_hash = raw_data.get("confirmed_key_hash")
            if row["event_type"] == "confirmed" and existing_key_hash:
                key_row = conn.execute(
                    "SELECT * FROM api_keys WHERE key_hash = ?", (existing_key_hash,)
                ).fetchone()
                if key_row:
                    return self._key_from_row(key_row)
            if row["event_type"] != "pending_verification":
                return None

            plan = raw_data.get("plan", "pro_monthly")
            email = row["customer_email"]
            key = f"sk_claw_{secrets.token_hex(20)}"
            expires_at = now + days_valid * 86400 if days_valid and days_valid > 0 else None
            metadata = {
                "provider": "bitcoin",
                "txid": row["txid"] or raw_data.get("txid"),
                "payment_id": raw_data.get("payment_id"),
                "confirmed_by": confirmed_by,
                "confirmed_at": now,
                "key_id": _key_audit_id(key),
            }
            conn.execute(
                "INSERT INTO api_keys (key, key_hash, email, plan, active, created_at, expires_at, "
                "quota_limit, quota_used, metadata_json) VALUES (?, ?, ?, ?, 1, ?, ?, ?, 0, ?)",
                (
                    None,
                    _key_hash(key),
                    email,
                    plan,
                    now,
                    expires_at,
                    quota_limit,
                    json.dumps(metadata),
                ),
            )
            raw_data.update({"confirmed_at": now, "confirmed_key_hash": _key_hash(key)})
            if confirmation_metadata:
                raw_data.update(confirmation_metadata)
            conn.execute(
                "UPDATE payment_events SET event_type = 'confirmed', raw_payload_json = ? "
                "WHERE event_id = ? AND event_type = 'pending_verification'",
                (json.dumps(raw_data), event_id),
            )
            return KeyRecord(
                key=key,
                email=email,
                plan=plan,
                created_at=now,
                expires_at=expires_at,
                quota_limit=quota_limit,
                metadata=metadata,
            )

    @staticmethod
    def _key_from_row(row: sqlite3.Row) -> KeyRecord:
        import json

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
