# OpenClawMesh v1.1.0 — Documentation Technique

> **Périmètre et sécurité :** la passerelle FastAPI/Bitcoin est un composant optionnel, séparé de la connectivité mesh. Elle manipule des métadonnées de paiement et des identifiants API ; ne la déployez pas si vous avez uniquement besoin du réseau P2P, et conservez son écoute sur localhost sauf configuration WAN explicitement sécurisée.

> **Protocole P2P & Skill Décentralisé pour Agents IA**  
> Compatible JarvisMesh 1.0 · Python 3.10+ · WebSocket · Kademlia DHT · E2EE ChaCha20-Poly1305

---

## Table des Matières

1. [Vue d'ensemble du Système](#1-vue-densemble-du-système)
2. [Architecture Modulaire](#2-architecture-modulaire)
3. [Protocole Wire (Format des Messages)](#3-protocole-wire-format-des-messages)
4. [Modèle de Sécurité](#4-modèle-de-sécurité)
5. [Découverte Réseau (mDNS & DHT Kademlia)](#5-découverte-réseau-mdns--dht-kademlia)
6. [Moteurs d'Inférence IA](#6-moteurs-dinférence-ia)
7. [Passerelle de Monétisation](#7-passerelle-de-monétisation)
8. [Installation & Configuration](#8-installation--configuration)
9. [Guide de Déploiement](#9-guide-de-déploiement)
10. [Référence API Publique](#10-référence-api-publique)
11. [Guide de Contribution](#11-guide-de-contribution)
12. [Changelog & Décisions Architecturales](#12-changelog--décisions-architecturales)

---

## 1. Vue d'ensemble du Système

OpenClawMesh est une bibliothèque Python permettant à des agents IA autonomes de **se découvrir mutuellement**, de **déléguer des tâches** et de **partager des compétences** (skills) sur un réseau pair-à-pair (P2P), aussi bien sur réseau local (LAN via mDNS) que sur Internet (WAN via DHT Kademlia et relais WebSocket).

### Philosophie de Conception

| Principe | Implémentation |
|----------|---------------|
| **Zéro infrastructure centralisée** | mDNS LAN + DHT Kademlia WAN, sans serveur de découverte central |
| **Sécurité de bout en bout** | Authentification HMAC-SHA256 ou Ed25519, chiffrement E2EE X25519+ChaCha20 |
| **Interopérabilité** | Protocole wire 100% compatible avec JarvisMesh 1.0 |
| **Agnosticisme matériel** | Détection et adaptation automatique NVIDIA/AMD/Intel/Apple Silicon/CPU |
| **Streaming natif** | Support des générateurs async pour l'inférence token-par-token |

### Flux de Communication Simplifié

```
Client A (MeshClient)                    Node B (OpenClawMeshNode)
    │                                            │
    │── mDNS discover ──────────────────────────►│ (PeerInfo: skills, address)
    │                                            │
    │── WS connect ────────────────────────────►│
    │── TaskRequest{skill, payload, sig} ───────►│
    │                                            │── Vérif HMAC/Ed25519
    │                                            │── handler(payload)
    │◄── TaskChunk{index=0, chunk=...} ──────────│  (streaming)
    │◄── TaskChunk{index=1, chunk=...} ──────────│
    │◄── TaskResponse{ok, result} ───────────────│
```

---

## 2. Architecture Modulaire

### Couches du Système

```
┌─────────────────────────────────────────────────────────────────┐
│  INTERFACE                                                       │
│  cli.py (argparse, 11 commandes)    __init__.py (API publique)  │
├─────────────────────────────────────────────────────────────────┤
│  TRANSPORT                                                       │
│  node.py (WS Server)   client.py (WS Client+Pool)              │
│  network/relay.py (WAN Relay Server/Client)                     │
├─────────────────────────────────────────────────────────────────┤
│  PROTOCOLE                                                       │
│  protocol.py (Wire Format JSON)    bridge.py (SkillRegistry)   │
├─────────────────────────────────────────────────────────────────┤
│  DÉCOUVERTE                                                      │
│  discovery.py (mDNS/Zeroconf)   network/dht.py (Kademlia UDP)  │
│  network/nat_traversal.py (STUN RFC5389)                        │
├─────────────────────────────────────────────────────────────────┤
│  SÉCURITÉ                                                        │
│  crypto.py (Ed25519 NodeIdentity)                               │
│  crypto_e2ee.py (X25519 + ChaCha20-Poly1305 AEAD)              │
├─────────────────────────────────────────────────────────────────┤
│  INFÉRENCE IA                                                    │
│  engines/hardware.py          engines/inference.py              │
│  engines/model_manager.py     engines/distributed_moe.py        │
│  engines/multimodal.py                                          │
├─────────────────────────────────────────────────────────────────┤
│  MONÉTISATION                                                    │
│  gateway/server.py (FastAPI)   gateway/db.py (SQLite)          │
│  gateway/portal.py (Web UI)                                     │
├─────────────────────────────────────────────────────────────────┤
│  CONFIGURATION                                                   │
│  config.py (Pydantic Settings, singleton, env-driven)           │
└─────────────────────────────────────────────────────────────────┘
```

### Description des Modules

#### `openclaw_mesh/protocol.py`
**Responsabilité** : Définition du format wire JSON. Garantit la compatibilité bidirectionnelle avec JarvisMesh.

**Types de messages** :

| Classe | `type` JSON | Description |
|--------|-------------|-------------|
| `TaskRequest` | `"task_request"` | Requête d'exécution d'une compétence |
| `TaskChunk` | `"task_chunk"` | Fragment de réponse en streaming |
| `TaskResponse` | `"task_response"` | Réponse finale (succès ou erreur) |

**Base canonique de signature HMAC-SHA256** (compatible JarvisMesh) :
```
base = f"{request_id}|{origin}|{skill}|{repr(ts)}|{json.dumps(payload, sort_keys=True, separators=(',', ':'))}"
sig  = hmac.HMAC(psk.encode('utf-8'), base.encode('utf-8'), digestmod=sha256).hexdigest()
```

**Base canonique Ed25519** (extension OpenClawMesh) :
```
base = f"{request_id}|{origin}|{pubkey_hex}|{skill}|{repr(ts)}|{json.dumps(payload, sort_keys=True, separators=(',', ':'))}"
sig  = private_key.sign(base.encode('utf-8')).hex()
```

---

#### `openclaw_mesh/node.py` — `OpenClawMeshNode`
**Responsabilité** : Serveur WebSocket exposant les compétences d'un nœud.

**Pipeline de traitement d'une requête** :
```
Connexion WebSocket entrante
    └─► parse_message(raw)
        └─► [msg_type != "task_request"] → ignoré
        └─► TaskRequest.from_dict(data)
            ├─► [PSK configuré] → verify_hmac() → ERR si échec
            ├─► [TrustStore configuré] → verify_ed25519() + drift check → ERR si échec
            ├─► [skill == "_describe_skills"] → SkillRegistry.describe()
            ├─► [skill == "_health"] → health_data + health_extra()
            └─► SkillRegistry.get(skill)
                ├─► [async generator] → TaskChunk × N → TaskResponse(streamed=True)
                ├─► [generator] → TaskChunk × N → TaskResponse(streamed=True)
                ├─► [coroutine] → await handler(payload) → TaskResponse
                └─► [sync function] → asyncio.to_thread(handler, payload) → TaskResponse
```

**Compétences réservées** :

| Nom | Description |
|-----|-------------|
| `_describe_skills` | Retourne le catalogue complet (noms, descriptions, schémas JSON) |
| `_health` | Retourne l'état du nœud : uptime, tâches actives, nombre de skills |

---

#### `openclaw_mesh/client.py` — `MeshClient`
**Responsabilité** : Client P2P asynchrone avec pool de connexions WebSocket multiplexées.

**Architecture du Pool** :
```
_pool         : {endpoint_key → WebSocket}           (1 connexion par pair)
_pending      : {endpoint_key → {request_id → Future[TaskResponse]}}
_stream_cbs   : {endpoint_key → {request_id → Callable}}
_reader_tasks : {endpoint_key → asyncio.Task}         (1 lecteur par connexion)
```

Chaque endpoint utilise **une seule connexion WebSocket** avec **une seule tâche de lecture** (`_reader_loop`). Le multiplexage est assuré par le `request_id` UUID hex 8 chars.

**Algorithme `find_best_peer_for_skill`** :
1. Collecte tous les pairs connaissant la compétence (cache mDNS + statiques)
2. Si données de santé disponibles (`check_health`), tri par `(active_tasks, rtt_ms)` croissant
3. Sinon, score neutre `(10, 999.0)` → premier de la liste

---

#### `openclaw_mesh/bridge.py` — `SkillRegistry`
**Responsabilité** : Registre central des compétences. Supporte sync, async, générateurs et async générateurs.

```python
registry = SkillRegistry(name="mon-nœud")


# Décorateur direct
@registry.register
async def llm(payload: dict) -> dict: ...


# Décorateur nommé via skill()
@skill(name="vision", description="Analyse d'image")
async def analyze(payload: dict) -> dict: ...


registry.register(analyze)

# Enregistrement batch
registry.register_dict({"echo": echo_fn, "ping": ping_fn})
```

**Compétences intégrées** (auto-enregistrées au `__init__`) :
- `echo` — renvoie le payload reçu
- `openclaw_info` — version (dynamique via `importlib.metadata`), OS, Python
- `system_info` — platform, CPU, cores

---

#### `openclaw_mesh/config.py` — `Settings`
**Responsabilité** : Configuration centralisée via `pydantic-settings`. Singleton thread-safe.

```python
settings = get_settings()  # retourne toujours la même instance
settings = reload_settings()  # recharge depuis l'environnement
reset_settings()  # remet à None (utile en tests)
```

---

## 3. Protocole Wire (Format des Messages)

### TaskRequest

```json
{
  "type": "task_request",
  "skill": "llm",
  "payload": {"prompt": "Hello", "max_tokens": 512},
  "request_id": "a1b2c3d4",
  "origin": "mac-m3-agent",
  "ts": 1724695234.567,
  "sig": "9f4a...",
  "pubkey": "4c8e..."
}
```

| Champ | Type | Requis | Description |
|-------|------|--------|-------------|
| `type` | string | ✓ | Toujours `"task_request"` |
| `skill` | string | ✓ | Nom de la compétence à exécuter |
| `payload` | object | ✓ | Arguments de la compétence |
| `request_id` | string | ✓ | UUID court hex 8 chars (multiplexage) |
| `origin` | string | ✓ | Nom du nœud émetteur |
| `ts` | float | ✓ | Timestamp POSIX (anti-rejeu) |
| `sig` | string | ○ | Signature HMAC-SHA256 ou Ed25519 hex |
| `pubkey` | string | ○ | Clé publique Ed25519 hex 64 chars |

### TaskChunk (Streaming token-par-token)

```json
{
  "type": "task_chunk",
  "request_id": "a1b2c3d4",
  "index": 0,
  "chunk": "Bonjour, "
}
```

### TaskResponse

```json
{
  "type": "task_response",
  "request_id": "a1b2c3d4",
  "ok": true,
  "result": {"text": "...", "model": "qwen2.5-coder-7b", "duration_ms": 234.5},
  "error": null,
  "handled_by": "mac-m3-node",
  "streamed": false
}
```

---

## 4. Modèle de Sécurité

### Couches de Sécurité (Hiérarchiques et Indépendantes)

```
┌────────────────────────────────────────────────────────────────┐
│  Couche 3 — E2EE (optionnel, recommandé sur WAN)              │
│  X25519 ECDH + HKDF-SHA256 + ChaCha20-Poly1305 (AEAD)        │
│  Protège le payload même via un relais WAN compromis           │
├────────────────────────────────────────────────────────────────┤
│  Couche 2 — Auth Asymétrique (optionnel)                      │
│  Ed25519 + TrustStore liste blanche + anti-rejeu ±300s         │
├────────────────────────────────────────────────────────────────┤
│  Couche 1 — Auth Symétrique (optionnel, compat JarvisMesh)    │
│  HMAC-SHA256 sur base canonique (compare_digest temps constant)│
├────────────────────────────────────────────────────────────────┤
│  Couche 0 — Transport TLS (optionnel)                         │
│  WSS via ssl.SSLContext injecté dans Node et Client            │
└────────────────────────────────────────────────────────────────┘
```

> **Note** : Les couches sont **indépendantes et cumulables**. Exemple : PSK (Couche 1) + Ed25519 (Couche 2) + WSS (Couche 0) pour une sécurité maximale.

### 4.1 Authentification HMAC-SHA256

Compatible JarvisMesh. La clé pré-partagée (PSK) est configurée via `OPENCLAW_PSK`.

```
base = f"{request_id}|{origin}|{skill}|{repr(ts)}|{json_payload_sorted}"
sig  = hmac.HMAC(psk_bytes, base_bytes, digestmod=sha256).hexdigest()
```

La comparaison utilise `hmac.compare_digest()` — résistant aux timing attacks.

**Vérification** : Si `psk` configuré ET `req.sig` absent ou invalide → `TaskResponse(ok=False)`.

### 4.2 Authentification Ed25519

Extension OpenClawMesh (champs `pubkey`/`sig` optionnels dans le format wire).

**Flux** :
```
Génération (une fois)  : identity = NodeIdentity.generate()
                         identity.save("~/.openclaw/identity.key")  # chmod 0600

Enregistrement pair    : trust_store.trust(identity.public_key_hex)

Signature (client)     : req.sign_ed25519(identity)

Vérification (serveur) :
  1. trust_store.is_trusted(req.pubkey)?      → 403 si non
  2. |now - req.ts| <= drift_limit (300s)?    → 403 si non
  3. public_key.verify(sig_bytes, base_bytes)? → 403 si non
```

**Anti-rejeu** : Tolérance configurable via `OPENCLAW_SIGNATURE_MAX_DRIFT_SECONDS` (défaut 300s).

### 4.3 Chiffrement E2EE (End-to-End Encryption)

**Algorithmes** : X25519 (ECDH key exchange) + HKDF-SHA256 (key derivation) + ChaCha20-Poly1305 (AEAD encryption).

**Format du paquet chiffré** :
```json
{
  "version": "1.0",
  "algorithm": "ChaCha20-Poly1305",
  "ephemeral_pubkey": "a1b2c3... (32 octets hex)",
  "nonce": "f7e3a1...             (12 octets hex, unique par session)",
  "ciphertext": "9f4a...          (payload + tag AEAD 16 octets)",
  "data_type": "json|text|bytes",
  "timestamp": 1724695234.567
}
```

**Double protection anti-rejeu** :
1. **Horodatage** : `|now - ts| > drift_limit` → `ReplayError`
2. **Cache de nonces** (`ReplayCache`, FIFO borné à 4096 entrées) : nonce déjà vu → `ReplayError`

```python
# Session persistante (échanges multiples)
session_a = E2EESession()
session_b = E2EESession()
session_b.establish_with_peer(session_a.public_key_bytes)
session_a.establish_with_peer(session_b.public_key_bytes)

packet = session_a.encrypt({"secret": "data"})
data = session_b.decrypt(packet)

# One-shot (sans état)
packet = encrypt_message_for_peer(peer_pubkey_hex, {"msg": "hello"})
data = decrypt_message_with_key(my_private_bytes, packet)
```

---

## 5. Découverte Réseau (mDNS & DHT Kademlia)

### 5.1 Découverte LAN — mDNS/Zeroconf

Publication simultanée sur **deux types mDNS** pour la rétrocompatibilité :
- `_jarvismesh._tcp.local.` (JarvisMesh v1)
- `_openclawmesh._tcp.local.` (OpenClawMesh v1.1+)

**Propriétés TXT publiées** :
```
skills = "llm,memory_search,echo,vision"
proto  = "1.0"
client = "openclaw"
```

| `ServiceStateChange` | Action |
|---------------------|--------|
| `Added` | `_resolve_peer()` — récupère IP, port, skills via `AsyncServiceInfo` |
| `Updated` | Même traitement (mise à jour du `PeerInfo`) |
| `Removed` | Retire le pair de `MeshDiscovery.peers` |

### 5.2 Découverte WAN — DHT Kademlia 160-bit

**Paramètres Kademlia** :

| Paramètre | Valeur | Description |
|-----------|--------|-------------|
| `ID_BITS` | 160 | Espace d'adressage (SHA-1 hex 40 chars) |
| `K` | 20 | Taille des k-buckets (contacts par bucket) |
| `α (alpha)` | 3 | Requêtes parallèles en lookup itératif |
| `RPC_TIMEOUT` | 3.0s | Timeout UDP par RPC |
| `DEFAULT_TTL` | 3600s | TTL des entrées distribuées |

**RPCs implémentés** :

| RPC | Description |
|-----|-------------|
| `PING` | Vérifier qu'un pair est joignable |
| `FIND_NODE` | Trouver les k contacts les plus proches d'un ID |
| `FIND_VALUE` | Trouver une valeur ou les k contacts les plus proches |
| `STORE` | Déposer une valeur sur un pair |

```python
dht = KademliaDHT(host="127.0.0.1", port=8780)
await dht.start_network()
await dht.bootstrap([Contact(node_id="...", host="seed.example.com", port=8780)])

# Publication d'une compétence dans le DHT
await dht.advertise_skill_distributed(
    "llm", {"host": "203.0.113.42", "port": 8770, "node": "mac-m3"}
)

# Recherche distribuée
endpoint = await dht.lookup_skill_distributed("llm")
```

### 5.3 Traversée NAT (STUN RFC 5389)

```python
nat = await discover_nat_and_public_ip(local_port=8770)
print(nat.public_ip, nat.public_port, nat.nat_type)
print(nat.is_direct_connectable)  # True si Cone NAT
```

Serveurs STUN utilisés (dans l'ordre) :
1. `stun.l.google.com:19302`
2. `stun.cloudflare.com:3478`
3. `stun1.l.google.com:19302`

### 5.4 Relais WAN WebSocket (Opaque)

Quand la traversée NAT directe échoue (NAT Symétrique), le relais route les trames **sans pouvoir les déchiffrer** (E2EE obligatoire).

```
Pair A ──WS──► Relais WAN ──WS──► Pair B
               (opaque routing)
```

**Messages gérés par le relais** :
- `register` : Enregistre le pair avec son `node_id`
- `forward` : Route vers `target_node_id` (paquet `relayed_message`)
- `list_peers` : Retourne la liste des pairs connectés

---

## 6. Moteurs d'Inférence IA

### 6.1 Détection Matériel (`detect_hardware`)

**Ordre de détection** :
```
1. NVIDIA CUDA (torch.cuda.is_available()) → rec: "cuda"
2. Apple Silicon Metal (macOS + ARM) → rec: "mlx"
3. AMD DirectML (importlib.util.find_spec) → rec: "directml"
4. AMD ROCm (/opt/rocm présent) → rec: "rocm"
5. Intel OpenVINO (openvino importable) → rec: "openvino_npu" / "openvino_gpu" / "openvino"
6. CPU Universel (fallback) → rec: "cpu"
```

### 6.2 Sélection Automatique de Modèle (`AutoModelManager`)

| VRAM disponible | Modèle recommandé | Quantization | Context |
|-----------------|-------------------|-------------|---------|
| < 6 Go | Qwen2.5-Coder-1.5B-Instruct | 4bit | 8K tokens |
| 6–16 Go | Qwen2.5-Coder-7B-Instruct | 4bit | 32K tokens |
| 16–32 Go | Qwen2.5-Coder-14B-Instruct | 8bit / fp16 | 64K tokens |
| > 32 Go | Qwen2.5-Coder-32B-Instruct | 4bit / fp16 | 128K tokens |

**Format par backend** :

| Backend | Format de modèle |
|---------|-----------------|
| `mlx` | MLX 4-bit/8-bit (`.mlx`) |
| `cuda` | SafeTensors FP16 |
| `openvino*` | OpenVINO IR |
| `cpu` / autres | GGUF (Q4_K_M, Q8_0) |

### 6.3 `UniversalInferenceEngine`

```python
engine = UniversalInferenceEngine()

# Génération complète
result = await engine.generate(
    prompt="def fibonacci(n):",
    max_tokens=256,
    temperature=0.1,
    system_prompt="Tu es un expert Python.",
)
# → {"text": "...", "model": "...", "backend": "apple_metal_mlx", "duration_ms": 234.5}

# Streaming token-par-token
async for token in engine.generate_stream(prompt="Explique les closures Python"):
    print(token["text"], end="", flush=True)
```

**Backends tentés dans l'ordre** :
1. MLX (Apple Silicon) : `mlx_lm.generate` / `mlx_lm.stream_generate`
2. CUDA PyTorch : `transformers.pipeline`
3. Intel OpenVINO : `openvino_genai.LLMPipeline`
4. Fallback universel (simulation / Ollama local)

### 6.4 Distributed MoE (Mixture of Experts)

Fragmente un grand modèle en `N` étapes pipeline réparties sur différents nœuds.

```python
orchestrator = DistributedMoEOrchestrator(num_stages=4)
orchestrator.add_stage(PipelineStage(stage_id=0, node_name="mac-m3", skill_name="moe_stage_0"))
orchestrator.add_stage(PipelineStage(stage_id=1, node_name="linux-rtx", skill_name="moe_stage_1"))
result = await orchestrator.run_pipeline({"input": "..."}, client=mesh_client)
```

### 6.5 MultiModalEngine

```python
engine = MultiModalEngine()

# Vision (analyse d'image base64 ou fichier)
result = engine.analyze_image(image_path="photo.jpg", prompt="Décris cette image")

# STT (Speech-to-Text)
transcription = engine.transcribe_audio(audio_path="audio.wav")

# TTS (Text-to-Speech)
audio_path = engine.synthesize_speech(text="Bonjour le monde")
```

---

## 7. Passerelle de Monétisation

### 7.1 Architecture de la Passerelle

```
Client Web/App
      │
      ▼
FastAPI (gateway/server.py) — uvicorn/gunicorn
      │
      ├── GET  /                        → Portail HTML (portal.py)
    ├── GET  /api/v1/payment/info     → Cours BTC/EUR et montant en satoshis
    ├── POST /api/v1/payment/submit   → Soumission TXID + jeton privé de statut
    ├── GET  /api/v1/payment/status   → Statut protégé par X-Payment-Token
    ├── POST /api/v1/admin/payments/confirm → Secours admin authentifié
      ├── POST /api/v1/auth/verify      → Valider une clé API
      ├── POST /api/v1/execute          → Exécuter compétence (auth requise)
      ├── POST /api/v1/checkout/demo-key → Clé démo (3 req, 7j)
      ├── GET  /api/v1/admin/keys       → Liste clés (token admin)
      └── POST /api/v1/admin/keys/create → Création manuelle (admin)
            │
            ▼
      SQLite (KeyDatabase — gateway/db.py)
      ├── api_keys       (clés, quotas, expiration, abonnement)
    ├── payment_events (TXID, idempotence, statut blockchain)
      └── usage_logs     (métriques par clé et compétence)
```

### 7.2 Plans d'Accès

| Plan | Durée | Quota | Prix |
|------|-------|-------|------|
| `demo_free` | 7 jours | 3 requêtes | Gratuit |
| `pro_monthly` | 30 jours renouvelable | Illimité | 10€/mois |
| `lifetime` | Illimité (pas d'expiration) | Illimité | 200€ paiement unique |

### 7.3 Cycle de Vie d'une Clé

```
payment.submit ───────────────► pending_verification + status_token
                                      │
BTC confirmations suffisantes ───────► KeyRecord(active=True)
Bitcoin reorg détectée ──────────────► active = False
quota_used >= quota_limit ───────────► is_valid() returns False
expires_at < now ────────────────────► is_valid() returns False
admin revoke ────────────────────────► active = False
```

### 7.4 Déploiement de la Passerelle

```bash
# Variables requises
export GATEWAY_ADMIN_TOKEN="mon_token_admin_secret_long"
export GATEWAY_DB_PATH="/data/openclaw_keys.db"
export BTC_WALLET_ADDRESS="bc1q..."
export BTC_AUTO_VERIFY=true
export BTC_REQUIRED_CONFIRMATIONS=2

# Développement
uvicorn openclaw_mesh.gateway.server:app --host 127.0.0.1 --port 8000

# Production (avec gunicorn)
gunicorn openclaw_mesh.gateway.server:app \
  -w 4 -k uvicorn.workers.UvicornWorker \
    --bind 127.0.0.1:8000 \
  --access-logfile /var/log/openclaw/access.log
```

La confirmation Bitcoin est manuelle par défaut. La vérification automatique n’est activée qu’avec `BTC_AUTO_VERIFY=true`; l’endpoint d’administration reste protégé par un secret fort.

---

## 8. Installation & Configuration

### Prérequis

- Python ≥ 3.10 (3.11 recommandé pour les meilleures performances asyncio)
- Dépendances système : aucune (pure Python)

### Installation

```bash
# Minimal (découverte mDNS + WebSocket seulement)
pip install openclaw-mesh

# Avec cryptographie Ed25519 (recommandé en production)
pip install "openclaw-mesh[crypto]"

# Avec CLI riche (affichage Rich)
pip install "openclaw-mesh[rich]"

# Tout inclus
pip install "openclaw-mesh[all]"

# Développement
git clone https://github.com/your-org/OpenClawMesh
cd OpenClawMesh
pip install -e ".[dev]"
pre-commit install
```

### Variables d'Environnement Principales

| Variable | Défaut | Description |
|----------|--------|-------------|
| `OPENCLAW_NODE_NAME` | `"openclaw-node"` | Nom du nœud publié en mDNS |
| `OPENCLAW_DEFAULT_PORT` | `8770` | Port WebSocket du nœud |
| `OPENCLAW_PSK` | `None` | Clé pré-partagée HMAC-SHA256 |
| `OPENCLAW_MDNS_ENABLED` | `True` | Activer la découverte mDNS |
| `OPENCLAW_DHT_PORT` | `8780` | Port UDP DHT Kademlia |
| `OPENCLAW_RELAY_PORT` | `8790` | Port WebSocket du relais WAN |
| `OPENCLAW_GATEWAY_PORT` | `8000` | Port HTTP configuré |
| `GATEWAY_DB_PATH` | `openclaw_keys.db` | Base SQLite des clés |
| `OPENCLAW_E2EE_ENABLED` | `True` | Chiffrement E2EE activé |
| `OPENCLAW_SIGNATURE_MAX_DRIFT_SECONDS` | `300.0` | Tolérance anti-rejeu (s) |
| `OPENCLAW_LOG_LEVEL` | `"INFO"` | Niveau de logging |
| `OPENCLAW_DEBUG` | `False` | Mode debug verbeux |

### Fichier `.env` Exemple Production

```env
OPENCLAW_NODE_NAME=prod-node-paris-1
OPENCLAW_DEFAULT_PORT=8770
OPENCLAW_PSK=changeme_at_least_32_chars_long_secret

OPENCLAW_SIGNATURE_MAX_DRIFT_SECONDS=300
OPENCLAW_E2EE_ENABLED=true

OPENCLAW_DHT_ENABLED=true
OPENCLAW_DHT_PORT=8780

GATEWAY_DB_PATH=/data/openclaw/keys.db
GATEWAY_CORS_ORIGINS=https://app.example.com
GATEWAY_ADMIN_TOKEN=replace-with-a-long-random-secret
BTC_WALLET_ADDRESS=bc1q...
BTC_AUTO_VERIFY=true
BTC_REQUIRED_CONFIRMATIONS=2
# Optionnel : active une requête sortante vers un oracle de prix configuré.
# BTC_PRICE_URLS=https://provider.example/api/price

OPENCLAW_LOG_LEVEL=INFO
OPENCLAW_LOG_FILE=/var/log/openclaw/node.log
OPENCLAW_LOG_ROTATION=true
```

---

## 9. Guide de Déploiement

### Scénario 1 — Nœud Simple (LAN uniquement)

```python
import asyncio
from openclaw_mesh import OpenClawMeshNode, SkillRegistry

registry = SkillRegistry(name="mon-nœud")


@registry.register
async def llm(payload: dict) -> dict:
    return {"text": f"Réponse : {payload.get('prompt')}"}


async def main():
    node = OpenClawMeshNode(
        name="mon-agent",
        port=8770,
        psk="mon_psk_secret",
        registry=registry,
    )
    await node.start(enable_zeroconf=False)  # Publication LAN à activer explicitement.
    print(f"Nœud démarré sur {node.advertise_ip}:{node.port}")
    await asyncio.Event().wait()  # tourne indéfiniment


asyncio.run(main())
```

### Scénario 2 — Client Multi-Agent avec Routage Intelligent

```python
from openclaw_mesh import MeshClient


async def main():
    client = MeshClient(name="orchestrateur", psk="mon_psk_secret")
    await client.start()
    await asyncio.sleep(3)  # découverte mDNS

    # Appel direct
    resp = await client.call("mon-agent", "llm", {"prompt": "Dis bonjour"})
    print(resp.result)

    # Délégation automatique (sélection du meilleur pair)
    resp = await client.delegate("llm", {"prompt": "Code un tri rapide en Python"})
    print(resp.result)

    # Streaming token-par-token
    await client.call_stream(
        "mon-agent",
        "llm",
        {"prompt": "Explique les closures"},
        on_chunk=lambda c: print(c, end="", flush=True),
    )
    await client.stop()
```

### Scénario 3 — Production avec Sécurité Maximale

```bash
# 1. Générer l'identité cryptographique du nœud
openclaw-mesh keygen --output ~/.openclaw/identity.key --show-pubkey
# → Pubkey: 4c8eabcd...

# 2. Créer le TrustStore sur le nœud serveur
cat > trust_store.json << EOF
{"allow_all": false, "allowed_keys": ["4c8eabcd..."]}
EOF

# 3. Démarrer le nœud avec TLS + Ed25519
openclaw-mesh serve \
  --name prod-node-1 \
  --port 8770 \
  --identity ~/.openclaw/identity.key \
  --trust-store /etc/openclaw/trust_store.json

# 4. Appel authentifié
openclaw-mesh call prod-node-1 llm \
  --payload '{"prompt": "hello"}' \
  --identity ~/.openclaw/identity.key
```

### Scénario 4 — Réseau WAN Décentralisé

```python
async def start_wan_node():
    # 1. Découvrir le NAT
    nat = await discover_nat_and_public_ip(local_port=8770)

    # 2. Nœud WebSocket local
    node = OpenClawMeshNode(name="wan-node-1", port=8770, advertise_ip=nat.public_ip)
    await node.start()

    # 3. DHT Kademlia
    dht = KademliaDHT(host="127.0.0.1", port=8780)
    await dht.start_network()
    await dht.bootstrap([Contact(node_id="aabbcc...", host="seed.openclaw.io", port=8780)])

    # 4. Publier les skills dans le DHT global
    for skill_name in node.registry.list_names():
        await dht.advertise_skill_distributed(
            skill_name, {"host": nat.public_ip, "port": 8770, "node": "wan-node-1"}
        )
```

---

## 10. Référence API Publique

### `OpenClawMeshNode`

```python
class OpenClawMeshNode:
    """Serveur P2P WebSocket exposant les compétences d'un nœud."""

    def __init__(
        self,
        name: str | None = None,
        port: int | None = None,
        host: str | None = None,
        advertise_ip: str | None = None,
        registry: SkillRegistry | None = None,
        psk: str | None = None,
        identity: NodeIdentity | None = None,
        trust_store: TrustStore | None = None,
        ssl_context: ssl.SSLContext | None = None,
        health_extra: Callable[[], dict] | None = None,
    ): ...

    async def start(self, enable_zeroconf: bool = True) -> None:
        """Démarre le serveur WebSocket et la publication Zeroconf."""

    async def stop(self) -> None:
        """Arrête le serveur et la découverte réseau proprement."""
```

### `MeshClient`

```python
class MeshClient:
    """Client P2P asynchrone avec pool de connexions multiplexées."""

    def __init__(
        self,
        name: str | None = None,
        psk: str | None = None,
        identity: NodeIdentity | None = None,
        ssl_context: ssl.SSLContext | None = None,
        discovery: MeshDiscovery | None = None,
        enable_discovery: bool | None = None,
    ): ...

    async def start(self) -> None: ...
    async def stop(self) -> None: ...

    def add_peer(
        self, name: str, address: str, port: int, skills: list[str] | None = None
    ) -> PeerInfo: ...
    def list_peers(self) -> dict[str, PeerInfo]: ...

    async def call(
        self, target: str, skill: str, payload: dict | None = None, timeout: float = 60.0
    ) -> TaskResponse: ...

    async def call_stream(
        self,
        target: str,
        skill: str,
        payload: dict | None = None,
        on_chunk: Callable[[Any], None] | None = None,
        timeout: float = 120.0,
    ) -> TaskResponse: ...

    async def delegate(
        self,
        skill: str,
        payload: dict | None = None,
        on_chunk: Callable[[Any], None] | None = None,
        timeout: float = 60.0,
    ) -> TaskResponse:
        """Routage intelligent : sélectionne automatiquement le meilleur pair."""

    async def discover_skills(self, peer_target: str, timeout: float = 4.0) -> dict: ...
    async def check_health(self, peer_target: str, timeout: float = 3.0) -> dict: ...
    def find_best_peer_for_skill(self, skill: str) -> str | None: ...
```

### `SkillRegistry`

```python
class SkillRegistry:
    """Registre central des compétences d'un nœud."""

    def register(
        self,
        fn: Callable,
        name: str | None = None,
        description: str | None = None,
        schema: Any | None = None,
    ) -> Callable: ...

    def register_dict(self, skills: dict[str, Callable]) -> None: ...
    def get(self, name: str) -> Callable | None: ...
    def list_names(self) -> list[str]: ...
    def describe(self) -> dict[str, Any]: ...
```

### `NodeIdentity`

```python
class NodeIdentity:
    """Identité cryptographique Ed25519 d'un nœud."""
    node_id: str           # 16 premiers chars du pubkey hex
    public_key_hex: str    # 64 chars hex

    @classmethod def generate(cls) -> NodeIdentity: ...
    @classmethod def from_private_hex(cls, hex_str: str) -> NodeIdentity: ...
    @classmethod def from_private_bytes(cls, raw_bytes: bytes) -> NodeIdentity: ...
    @classmethod def load(cls, path: str | Path) -> NodeIdentity: ...
    def save(self, path: str | Path) -> None: ...  # chmod 0600 automatique
```

### `E2EESession`

```python
class E2EESession:
    """Session de chiffrement de bout en bout X25519 + ChaCha20-Poly1305."""

    public_key_bytes: bytes  # 32 octets X25519
    public_key_hex: str  # 64 chars hex
    is_established: bool

    def establish_with_peer(
        self, peer_public_key_bytes: bytes, salt: bytes = b"openclaw_e2ee_salt_v1"
    ) -> None: ...

    def encrypt(
        self, data: str | bytes | dict | list, associated_data: bytes | None = None
    ) -> dict: ...

    def decrypt(
        self,
        encrypted_package: dict,
        associated_data: bytes | None = None,
        max_drift_seconds: float | None = None,
    ) -> Any: ...
```

### `KademliaDHT`

```python
class KademliaDHT:
    """Nœud DHT Kademlia 160-bit avec transport UDP réel."""

    async def start_network(
        self, host: str | None = None, port: int | None = None
    ) -> tuple[str, int]: ...
    async def stop_network(self) -> None: ...
    async def bootstrap(self, contacts: list[Contact], timeout: float = 3.0) -> int: ...

    def store_local(self, key: str, value: Any, ttl_seconds: float = 3600.0) -> None: ...
    def get_local(self, key: str) -> Any | None: ...

    async def store_distributed(self, key: str, value: Any, ttl: float = 3600.0) -> bool: ...
    async def find_value_distributed(self, key: str) -> Any: ...
    async def find_node_distributed(self, target_id: str) -> list[Contact]: ...

    async def advertise_skill_distributed(self, skill_name: str, endpoint_info: dict) -> bool: ...
    async def lookup_skill_distributed(self, skill_name: str) -> Any | None: ...
```

---

## 11. Guide de Contribution

### Prérequis

```bash
git clone https://github.com/your-org/OpenClawMesh
cd OpenClawMesh
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pre-commit install
```

### Commandes

```bash
# Tests
pytest tests/ -v                     # Suite complète
pytest tests/test_crypto.py -v       # Module spécifique
pytest -x --pdb                      # Stop au premier échec

# Qualité de code
ruff check openclaw_mesh/            # Linting (0 erreur tolérée)
ruff check --fix openclaw_mesh/      # Auto-fix
black openclaw_mesh/ tests/          # Formatage
mypy openclaw_mesh/                  # Type checking strict
pre-commit run --all-files           # Toutes les vérifications
```

### Conventions

| Règle | Standard |
|-------|----------|
| Type hints | Obligatoires sur toutes les signatures publiques et protégées |
| Docstrings | Google style, toutes les classes et méthodes publiques |
| Gestion d'erreurs | `raise X from e` dans les blocs except, jamais `raise X` nu |
| Logging | `logger = logging.getLogger("openclaw_mesh.<module>")` — jamais `print()` |
| Asyncio | `asyncio.create_task()` (pas `ensure_future()`), `asyncio.get_running_loop()` (pas `get_event_loop()`) |
| Chemins | `pathlib.Path` — jamais `os.path.join()` |
| Ports tests | Aléatoires dans la plage 19000-19999 pour éviter les conflits |

### Écriture de Tests

```python
import pytest


@pytest.mark.asyncio
async def test_my_feature():
    from openclaw_mesh import OpenClawMeshNode, MeshClient

    port = 19000 + abs(hash("my_feature")) % 1000
    node = OpenClawMeshNode(name="test-node", port=port, host="127.0.0.1")
    await node.start(enable_zeroconf=False)

    try:
        client = MeshClient(name="test-client", enable_discovery=False)
        client.add_peer("test-node", "127.0.0.1", port)
        resp = await client.call("test-node", "echo", {"hello": "world"})
        assert resp.ok
        assert resp.result == {"hello": "world"}
    finally:
        await node.stop()
```

---

## 12. Changelog & Décisions Architecturales

### v1.1.0 (2026-08) — Corrections & Documentation

**Bugs corrigés** :
| Fichier | Bug | Correction |
|---------|-----|-----------|
| `protocol.py` | `hmac.new()` (API incorrecte) | → `hmac.HMAC()` (API publique correcte) |
| `config.py` | Caractère CJK parasite `某些` | Commentaire corrigé en français |
| `network/dht.py` | Logger `"opencl_mesh.dht"` (faute de frappe) | → `"openclaw_mesh.dht"` |
| `bridge.py` | Version `"1.0.0"` hardcodée | → `importlib.metadata.version()` dynamique |
| `node.py` | `asyncio.ensure_future()` déprécié | → `asyncio.create_task()` |
| `client.py` | `asyncio.ensure_future()` déprécié | → `asyncio.create_task()` |
| `client.py` | `asyncio.get_event_loop()` déprécié (×2) | → `asyncio.get_running_loop()` |
| `network/dht.py` | `asyncio.get_event_loop()` déprécié (×2) | → `asyncio.get_running_loop()` |
| `network/relay.py` | `WebSocketServerProtocol` import déprécié (ws v14+) | → `websockets.ServerConnection` |
| `network/nat_traversal.py` | `zip()` sans `strict=` | → `strict=True` |
| `cli.py` | Imports `JSON`, `Panel` inutilisés | Supprimés |
| `cli.py` | Variable `p_e2ee` non utilisée | Argument `--action` ajouté |
| `engines/hardware.py` | `import torch_directml` inutilisé | → `importlib.util.find_spec()` |
| `gateway/server.py` | `import secrets` manquant en tête | Ajouté en tête de fichier |
| `gateway/server.py` | `secrets_id()` défini après usage | Déplacé avant son premier appel |
| `gateway/server.py` | `raise X` sans `from e` (×4) | → `raise X from e` |
| `gateway/portal.py` | Trailing whitespace (×4 lignes) | Supprimé |
| `pyproject.toml` | `[tool.ruff]` config dépréciée | → `[tool.ruff.lint]` |
| `pyproject.toml` | `ruff>=0.1.0` trop ancien | → `ruff>=0.4.0` |

**Améliorations** :
- Documentation technique complète niveau ingénieur senior (`ARCHITECTURE.md`)

### v1.0.0 (2026-07) — Version Initiale

- Protocole wire JSON compatible JarvisMesh 1.0
- Découverte mDNS dual-type (Zeroconf)
- DHT Kademlia 160-bit avec transport UDP réel asynchrone
- Authentification HMAC-SHA256 + Ed25519 + TrustStore
- E2EE X25519 + ChaCha20-Poly1305 + anti-rejeu double (timestamp + cache nonces)
- Détection matériel universelle (NVIDIA/AMD/Intel/Apple Silicon)
- Inférence MLX, CUDA, OpenVINO avec streaming async
- Pipeline Distributed MoE
- Moteur multimodal (Vision/STT/TTS)
- Relais WAN WebSocket opaque (sans accès au contenu E2EE)
- Passerelle de monétisation FastAPI + SQLite + portail web
- CLI argparse avec 11 commandes

---

### ADR-001 — WebSocket pour le Transport Principal

**Contexte** : Choisir entre WebSocket, gRPC, QUIC ou HTTP/2.

**Décision** : WebSocket bidirectionnel sur TCP.

**Raisons** :
- Compatible tous navigateurs et proxies HTTP (ports 80/443)
- Traverse naturellement les pare-feux d'entreprise
- Streaming natif token-par-token sans polling
- `websockets` Python : bibliothèque mature, asynchrone, maintenue activement

**Compromis accepté** : TCP (non QUIC) → head-of-line blocking sur pertes de paquets. Acceptable pour le cas d'usage actuel (LAN faible perte).

---

### ADR-002 — Pool de Connexions Persistantes Multiplexées

**Contexte** : Une connexion WebSocket par requête vs. pool persistant multiplexé.

**Décision** : Pool persistant (une connexion par endpoint), multiplexage par `request_id`.

**Raisons** :
- Évite les handshakes TCP+TLS répétés (latence ÷10)
- Milliers de requêtes simultanées sur une seule connexion sans saturation de ports
- Architecture naturelle pour le streaming interleaved de plusieurs sessions

**Implémentation** : `_reader_loop` unique par endpoint, `_pending` dict correlant les futures par `request_id`.

---

### ADR-003 — Double Protection Anti-Rejeu E2EE

**Contexte** : Protéger contre les attaques par rejeu sur les paquets chiffrés.

**Décision** : Combinaison **horodatage + cache de nonces** (sliding window borné).

**Analyse des alternatives** :
| Approche | Avantage | Inconvénient |
|----------|---------|-------------|
| Timestamp seul | Mémoire O(0) | Rejouable dans la fenêtre ±300s |
| Nonce seul | Protection totale | Cache non borné → DoS mémoire |
| Combinaison | Mémoire bornée (4096 entrées) | Légèrement plus complexe |

**Conclusion** : La combinaison offre le meilleur compromis — le cache est borné par `e2ee_nonce_cache_size` et les nonces expirent avec la fenêtre temporelle.

---

*Documentation OpenClawMesh v1.1.0 — Niveau Ingénieur Senior*  
*Généré le 2026-08-26*
