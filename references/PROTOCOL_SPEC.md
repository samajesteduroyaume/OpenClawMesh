# 📜 OpenClawMesh — Spécification Wire Protocol 1.0

Ce document spécifie le protocole de communication pair-à-pair utilisé par **OpenClawMesh**, strictement identique et interopérable avec **JarvisMesh 1.0**.

---

## 1. Découverte Réseau (mDNS / Zeroconf)

- **Types de service annoncés & écoutés** :
  - `_jarvismesh._tcp.local.`
  - `_openclawmesh._tcp.local.`
- **Enregistrements TXT (Properties)** :
  - `skills`: liste des compétences exposées séparées par des virgules (ex: `llm,memory_search,echo`)
  - `proto`: version du protocole (ex: `1.0`)
  - `client`: identifiant client (ex: `openclaw`)

---

## 2. Format des Messages JSON (WebSockets)

Chaque connexion WebSocket transporte des messages JSON encodés en UTF-8.

### 2.1. `TaskRequest`
Envoyé par un client pour requérir l'exécution d'une compétence par un pair :
```json
{
  "type": "task_request",
  "skill": "llm",
  "payload": {
    "prompt": "Bonjour",
    "temperature": 0.2
  },
  "request_id": "a1b2c3d4",
  "origin": "openclaw-agent",
  "ts": 1740432000.123,
  "sig": "abcdef...",
  "pubkey": "123456..."
}
```

### 2.2. `TaskChunk` (Streaming)
Envoyé par le serveur vers le client au fur et à mesure de la génération :
```json
{
  "type": "task_chunk",
  "request_id": "a1b2c3d4",
  "index": 0,
  "chunk": {
    "text": "Salut"
  }
}
```

### 2.3. `TaskResponse` (Réponse Finale)
Envoyé à la fin de l'exécution ou en cas d'erreur :
```json
{
  "type": "task_response",
  "request_id": "a1b2c3d4",
  "ok": true,
  "result": {
    "text": "Salut ! Comment puis-je t'aider ?"
  },
  "error": null,
  "handled_by": "mac-m3",
  "streamed": true
}
```

---

## 3. Compétences Réservées (Système)

Deux compétences réservées sont toujours exposées par tous les nœuds :
1. **`_describe_skills`** :
   - Payload : `{}`
   - Réponse : `{ "skills": ["llm", "memory_store", ...], "descriptions": {...}, "schemas": {...} }`
2. **`_health`** :
   - Payload : `{}`
   - Réponse : `{ "status": "ok", "active_tasks": 0, "uptime_seconds": 120.4, ... }`

---

## 4. Découverte Décentralisée — DHT Kademlia UDP (WAN)

Au-delà de la découverte mDNS locale, le réseau DHT Kademlia fournit l'indexation décentralisée à grande échelle. Le transport est un **socket UDP asynchrone** transportant des messages JSON-RPC corrélés par un identifiant de transaction `txid`.

### 4.1. Format des messages

Chaque message est `{"txid": "<8 hex>", "type": <type>, "node_id": "<40 hex>", "name": <str>, ...}`. Lorsque `OPENCLAW_PSK` est configuré, il contient également `signature`, un HMAC-SHA256 du message canonique sans ce champ.

| `type` (requête) | Champs additionnels | Réponse |
| :--- | :--- | :--- |
| `ping` | — | `pong` |
| `find_node` | `target` (`<node_id>`) | `find_node_response` → `{ contacts: [...] }` |
| `find_value` | `target_key` (`<hash ou clé>`) | `find_value_response` → `{ found: true, value }` ou `{ found: false, closest_nodes: [...] }` |
| `store` | `key`, `value`, `ttl` | `store_response` → `{ status: "ok" }` |
| `add_provider` | `target_key`, `provider_info`, `ttl` | `add_provider_response` → `{ status: "ok" }` |
| `get_providers` | `target_key` | `get_providers_response` → `{ providers: [...], closest_nodes: [...] }` |

### 4.2. Routage de Contenu & Provider Records (BitTorrent / Libp2p style)

Les compétences et modèles IA peuvent être annoncés par de multiples fournisseurs simultanés via `provide_distributed` et découverts via `find_providers_distributed` :

```python
# Annoncer la fourniture d'une compétence
await dht.provide_distributed("skill:llm_streaming", {
    "node_id": dht.node_id,
    "host": "198.51.100.42",
    "port": 8770,
    "quic_port": 8775,
    "gpu": "RTX 4090"
})

# Résoudre tous les fournisseurs enregistrés sur la DHT
providers = await dht.find_providers_distributed("skill:llm_streaming")
```

### 4.3. Démarrage du transport réseau

```python
from openclaw_mesh.network.dht import KademliaDHT, Contact

dht = KademliaDHT(name="my-node", host="127.0.0.1", port=8780, psk="shared-secret")
await dht.start_network()  # écoute UDP réelle

# Rejoindre le réseau via un pair connu, puis publier/rechercher
await dht.bootstrap([Contact(node_id="...", host="192.0.2.5", port=8780)])
await dht.advertise_skill_distributed("llm", {"host": "10.0.0.5", "port": 8770})
result = await dht.lookup_skill_distributed("llm")  # FIND_VALUE itératif
```

### 4.4. Recherche itérative (alpha-parallèle)

- `ALPHA = 3` requêtes parallèles par itération, jusqu'à `MAX_DHT_HOPS = 20` itérations.
- La table de routage (`k`-buckets, `k=20`) est mise à jour à chaque contact reçu.
- La recherche s'arrête quand la valeur est trouvée ou qu'aucun nœud plus proche n'est disponible.

---

## 5. Chiffrement E2EE des Relais WAN

Les paquets UDP/TCP traversant un relais WAN WebSocket sont des paquets E2EE opaques
(`ChaCha20-Poly1305` selon §3 de `SECURITY_MODEL.md`). Le relais ne fait que acheminer
le blob sans jamais le déchiffrer.

### Format du paquet E2EE

```json
{
  "version": "1.0",
  "algorithm": "ChaCha20-Poly1305",
  "ephemeral_pubkey": "<hex X25519 publique de l'émetteur>",
  "nonce": "<hex 96 bits>",
  "ciphertext": "<hex ciphertext + tag Poly1305>",
  "data_type": "json",
  "timestamp": 1740432000.123
}
```

---

## 6. Transport Ultra-Basse Latence QUIC / WebRTC UDP

OpenClawMesh implémente un transport direct UDP multiplexé avec cadrage binaire compact (`OCQ1`) pour le streaming de tokens sub-10ms et la traversée NAT automatique.

### 6.1. Cadrage Binaire (`OCQ1`)

Chaque datagramme UDP transporte un en-tête fixe de 24 octets (format struct `!4s B B H Q I`) suivi de la charge utile :

```text
 0                   1                   2                   3
 0 1 2 3 4 5 6 7 8 9 0 1 2 3 4 5 6 7 8 9 0 1 2 3 4 5 6 7 8 9 0 1
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|                       Magic: 'OCQ1' (4B)                      |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|  Type (1B)    |  Flags (1B)   |        Stream ID (2B)         |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|                        Sequence Number (8B)                   |
|                                                               |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|                         Payload Length (4B)                   |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|                        Payload Data (...)                     |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
```

### 6.2. Types de Paquets

| Type (Hex) | Nom | Description |
| :--- | :--- | :--- |
| `0x01` | `SYN` | Demande d'ouverture de session 0-RTT/1-RTT avec handshake sécurisé |
| `0x02` | `ACK` | Confirmation de session ou d'acquittement de flux |
| `0x03` | `PING` | Mesure de latence RTT haute précision via `perf_counter_ns()` |
| `0x04` | `PONG` | Réponse au Ping avec écho d'horodatage |
| `0x05` | `STREAM_OPEN` | Ouverture d'un flux multiplexé transportant un `TaskRequest` |
| `0x06` | `STREAM_DATA` | Datagramme de token / chunk en continu (`TaskChunk` / `TaskResponse`) |
| `0x07` | `STREAM_FIN` | Clôture ordonnée du flux |
| `0x08` | `STREAM_RESET`| Annulation immédiate en cas d'erreur |

---

## 7. Spécification GossipSub v1.1 Pub/Sub Overlay

Pour la diffusion thématique décentralisée en temps réel (découverte de modèles, métriques de cluster, état des nœuds), OpenClawMesh utilise GossipSub v1.1.

### 7.1. Format Wire JSON

```json
{
  "type": "gossipsub_v1",
  "sender_id": "<node_id>",
  "sender_name": "worker-gpu-1",
  "ts": 1740432000.123,
  "messages": [
    {
      "topic": "openclaw/v1/discovery",
      "data": { "skills": ["llm", "vlm"], "vram_free": 18200 },
      "from_peer": "<node_id>",
      "seq": 42,
      "ts": 1740432000.100,
      "msg_id": "a9f8b7c6..."
    }
  ],
  "control": {
    "graft": ["openclaw/v1/discovery"],
    "prune": [],
    "ihave": [
      { "topic": "openclaw/v1/models", "msg_ids": ["msg_1", "msg_2"] }
    ],
    "iwant": ["msg_1"]
  },
  "sig": "<HMAC-SHA256 ou Ed25519>"
}
```

### 7.2. Paramètres de Maillage

- **Degré cible ($D$)** : 6 pairs par topic.
- **Borne basse ($D_{\text{low}}$)** : 4 pairs (déclenche des requêtes `GRAFT`).
- **Borne haute ($D_{\text{high}}$)** : 12 pairs (déclenche des `PRUNE` sur les pairs les moins bien notés).
- **Degré paresseux ($D_{\text{lazy}}$)** : 6 pairs aléatoires hors maillage reçoivent les annonces `IHAVE` périodiques.
