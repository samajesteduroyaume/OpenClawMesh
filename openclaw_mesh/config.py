"""
Configuration centralisée pour OpenClawMesh.

Utilise Pydantic Settings pour gérer toutes les configurations via variables d'environnement
et fichiers de configuration. Préfixe OPENCLAW_ pour toutes les variables d'environnement.
"""

from __future__ import annotations

from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Configuration centralisée OpenClawMesh."""

    model_config = SettingsConfigDict(
        env_prefix="OPENCLAW_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ------------------------------------------------------------------ #
    # Configuration Générale
    # ------------------------------------------------------------------ #
    app_name: str = Field(default="openclaw-mesh", description="Nom de l'application")
    app_version: str = Field(default="1.0.0", description="Version de l'application")
    debug: bool = Field(default=False, description="Mode debug")

    # ------------------------------------------------------------------ #
    # Configuration Réseau
    # ------------------------------------------------------------------ #
    default_host: str = Field(default="127.0.0.1", description="Hôte par défaut")
    default_port: int = Field(default=8770, description="Port par défaut")

    # Timeouts réseau (en secondes)
    websocket_timeout: float = Field(default=60.0, description="Timeout WebSocket par défaut")
    discovery_timeout: float = Field(default=2.0, description="Timeout découverte mDNS")
    connection_timeout: float = Field(default=10.0, description="Timeout connexion")
    ping_timeout: float = Field(default=3.0, description="Timeout ping")

    # Configuration mDNS
    mdns_enabled: bool = Field(default=False, description="Activer découverte mDNS (opt-in)")
    mdns_service_types: list[str] = Field(
        default=["_jarvismesh._tcp.local.", "_openclawmesh._tcp.local."],
        description="Types de services mDNS",
    )

    # ------------------------------------------------------------------ #
    # Configuration Client
    # ------------------------------------------------------------------ #
    client_name: str = Field(default="openclaw-agent", description="Nom du client par défaut")
    max_connections_per_endpoint: int = Field(default=5, description="Max connexions par endpoint")
    connection_pool_size: int = Field(default=10, description="Taille du pool de connexions")
    connection_idle_timeout: float = Field(
        default=300.0, description="Timeout d'inactivité des connexions (secondes)"
    )
    enable_connection_pooling: bool = Field(
        default=True, description="Activer le pool de connexions"
    )

    # ------------------------------------------------------------------ #
    # Configuration Serveur Nœud
    # ------------------------------------------------------------------ #
    node_name: str = Field(default="openclaw-node", description="Nom du nœud par défaut")
    max_active_tasks: int = Field(default=100, description="Nombre maximum de tâches actives")
    max_queued_tasks: int = Field(default=200, description="Nombre maximum de tâches en attente")
    task_timeout: float = Field(default=120.0, description="Timeout par défaut des tâches")
    max_output_bytes: int = Field(
        default=2 * 1024 * 1024, description="Taille maximale d'une sortie distante"
    )

    # ------------------------------------------------------------------ #
    # Configuration Sécurité
    # ------------------------------------------------------------------ #
    # PSK (Pre-Shared Key)
    psk: str | None = Field(default=None, description="Clé pré-partagée HMAC-SHA256")

    # Ed25519
    identity_key_path: Path | None = Field(
        default=None, description="Chemin vers le fichier de clé privée Ed25519"
    )
    trust_store_path: Path | None = Field(
        default=None, description="Chemin vers le fichier TrustStore"
    )

    # E2EE
    e2ee_enabled: bool = Field(default=True, description="Activer chiffrement E2EE")
    e2ee_require_identity_binding: bool = Field(
        default=False,
        description="Exiger une liaison Ed25519/X25519 authentifiée (recommandé hors localhost)",
    )
    e2ee_algorithm: str = Field(
        default="ChaCha20-Poly1305", description="Algorithme de chiffrement E2EE"
    )

    # Anti-rejeu
    signature_max_drift_seconds: float = Field(
        default=300.0, description="Dérive maximale autorisée pour les signatures (secondes)"
    )
    e2ee_max_drift_seconds: float = Field(
        default=300.0,
        description="Fenêtre d'horodatage anti-rejeu pour les paquets E2EE (secondes)",
    )
    e2ee_nonce_cache_size: int = Field(
        default=4096, description="Taille max du cache de non-rejeu E2EE (entrées)"
    )

    # ------------------------------------------------------------------ #
    # Configuration DHT Kademlia
    # ------------------------------------------------------------------ #
    dht_enabled: bool = Field(default=False, description="Activer DHT Kademlia (opt-in)")
    dht_id_bits: int = Field(default=160, description="Nombre de bits pour les IDs DHT")
    dht_k_bucket_size: int = Field(default=20, description="Taille des k-buckets Kademlia")
    dht_alpha: int = Field(default=3, description="Paramètre alpha Kademlia (lookups parallèles)")
    dht_port: int = Field(default=8780, description="Port DHT par défaut")
    dht_persistence_enabled: bool = Field(
        default=False, description="Activer persistance DHT sur disque"
    )
    dht_persistence_path: Path | None = Field(
        default=None, description="Chemin vers le fichier de persistance DHT"
    )
    dht_transport_timeout: float = Field(
        default=3.0, description="Timeout réseau UDP pour les RPCs Kademlia (secondes)"
    )
    dht_default_ttl_seconds: float = Field(
        default=3600.0, description="TTL par défaut des entrées DHT distribuées"
    )

    # ------------------------------------------------------------------ #
    # Configuration Relais WAN
    # ------------------------------------------------------------------ #
    relay_enabled: bool = Field(default=False, description="Activer relais WAN")
    relay_host: str = Field(
        default="127.0.0.1", description="Hôte du relais (WAN explicitement configuré)"
    )
    relay_port: int = Field(default=8790, description="Port du relais")
    relay_name: str = Field(default="openclaw-wan-relay", description="Nom du relais")
    relay_max_clients: int = Field(
        default=100, description="Nombre maximum de pairs connectés au relais"
    )
    relay_max_message_bytes: int = Field(
        default=2 * 1024 * 1024, description="Taille maximale d'une trame relais"
    )

    # ------------------------------------------------------------------ #
    # Configuration Moteurs IA
    # ------------------------------------------------------------------ #
    # Auto-quantification
    auto_quantization_enabled: bool = Field(
        default=True, description="Activer auto-quantification VRAM"
    )
    default_model_backend: str = Field(
        default="auto", description="Backend par défaut (auto, cuda, mlx, openvino, cpu)"
    )

    # Modèles par défaut
    default_llm_model: str = Field(default="auto", description="Modèle LLM par défaut")
    default_vision_model: str = Field(default="auto", description="Modèle Vision par défaut")
    default_stt_model: str = Field(default="auto", description="Modèle STT par défaut")
    allowed_models: list[str] = Field(
        default=[
            "test",
            "openclaw-universal-v1",
            "mlx-community/Qwen2.5-Coder-7B-Instruct-4bit",
            "Qwen/Qwen2.5-Coder-7B-Instruct",
            "openvino_model",
        ],
        description="Liste blanche des modèles autorisés",
    )

    # Limites
    max_tokens_default: int = Field(default=512, description="Max tokens par défaut")
    temperature_default: float = Field(default=0.3, description="Température par défaut")

    # ------------------------------------------------------------------ #
    # Configuration Cache
    # ------------------------------------------------------------------ #
    cache_enabled: bool = Field(default=False, description="Activer cache distribué")
    cache_backend: str = Field(default="memory", description="Backend cache (memory, redis)")
    cache_ttl_seconds: float = Field(default=3600.0, description="TTL par défaut cache (secondes)")
    cache_max_size: int = Field(default=1000, description="Taille max cache (entrées)")
    redis_url: str | None = Field(default=None, description="URL Redis pour cache distribué")

    # ------------------------------------------------------------------ #
    # Configuration Passerelle / Monétisation
    # ------------------------------------------------------------------ #
    gateway_enabled: bool = Field(default=False, description="Activer passerelle monétisation")
    gateway_db_path: Path = Field(
        default=Path("openclaw_keys.db"), description="Chemin base de données clés"
    )
    gateway_host: str = Field(default="127.0.0.1", description="Hôte passerelle")
    gateway_port: int = Field(default=8000, description="Port passerelle")

    # Rate limiting
    rate_limit_enabled: bool = Field(default=True, description="Activer rate limiting")
    rate_limit_requests_per_minute: int = Field(
        default=60, description="Limite de requêtes par minute par IP"
    )
    rate_limit_burst: int = Field(default=10, description="Burst rate limiting")

    # ------------------------------------------------------------------ #
    # Configuration Logging
    # ------------------------------------------------------------------ #
    log_level: str = Field(default="INFO", description="Niveau de logging")
    log_format: str = Field(
        default="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        description="Format des logs",
    )
    log_file: Path | None = Field(default=None, description="Fichier de log (optionnel)")
    log_rotation: bool = Field(default=False, description="Activer rotation des logs")
    log_max_bytes: int = Field(default=10485760, description="Taille max fichier log (10MB)")
    log_backup_count: int = Field(default=5, description="Nombre de backups log")

    # ------------------------------------------------------------------ #
    # Configuration Compression
    # ------------------------------------------------------------------ #
    compression_enabled: bool = Field(default=True, description="Activer compression messages")
    compression_threshold_bytes: int = Field(default=1024, description="Seuil compression (bytes)")
    compression_algorithm: str = Field(default="gzip", description="Algorithme compression")

    # ------------------------------------------------------------------ #
    # Configuration Monitoring
    # ------------------------------------------------------------------ #
    monitoring_enabled: bool = Field(default=False, description="Activer monitoring")
    metrics_port: int = Field(default=9090, description="Port métriques Prometheus")
    tracing_enabled: bool = Field(default=False, description="Activer tracing distribué")

    # ------------------------------------------------------------------ #
    # Configuration Tests
    # ------------------------------------------------------------------ #
    test_mode: bool = Field(
        default=False, description="Mode test (override de certaines configurations)"
    )
    test_host: str = Field(default="127.0.0.1", description="Hôte pour tests")
    test_port_base: int = Field(default=8900, description="Base port pour tests")

    @field_validator("log_level")
    @classmethod
    def validate_log_level(cls, v: str) -> str:
        """Valide le niveau de logging."""
        valid_levels = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
        if v.upper() not in valid_levels:
            raise ValueError(f"log_level doit être dans {valid_levels}")
        return v.upper()

    @field_validator("mdns_service_types")
    @classmethod
    def validate_mdns_service_types(cls, v: list[str]) -> list[str]:
        """Valide les types de services mDNS."""
        for service_type in v:
            if not service_type.endswith("._tcp.local.") and not service_type.endswith(
                "._udp.local."
            ):
                raise ValueError(f"Type de service mDNS invalide: {service_type}")
        return v

    @field_validator("cache_backend")
    @classmethod
    def validate_cache_backend(cls, v: str) -> str:
        """Valide le backend de cache."""
        valid_backends = ["memory", "redis"]
        if v not in valid_backends:
            raise ValueError(f"cache_backend doit être dans {valid_backends}")
        return v

    @field_validator("compression_algorithm")
    @classmethod
    def validate_compression_algorithm(cls, v: str) -> str:
        """Valide l'algorithme de compression."""
        valid_algos = ["gzip", "zstd", "none"]
        if v not in valid_algos:
            raise ValueError(f"compression_algorithm doit être dans {valid_algos}")
        return v


# Instance globale des settings
_settings: Settings | None = None


def get_settings() -> Settings:
    """Retourne l'instance singleton des settings."""
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings


def reload_settings() -> Settings:
    """Recharge les settings depuis les variables d'environnement."""
    global _settings
    _settings = Settings()
    return _settings


def reset_settings() -> None:
    """Réinitialise les settings (utile pour les tests)."""
    global _settings
    _settings = None
