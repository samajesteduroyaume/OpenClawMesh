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

### 4.2. Démarrage du transport réseau

```python
from openclaw_mesh.network.dht import KademliaDHT, Contact

dht = KademliaDHT(name="my-node", host="127.0.0.1", port=8780, psk="shared-secret")
await dht.start_network()  # écoute UDP réelle

# Rejoindre le réseau via un pair connu, puis publier/rechercher
await dht.bootstrap([Contact(node_id="...", host="192.0.2.5", port=8780)])
await dht.advertise_skill_distributed("llm", {"host": "10.0.0.5", "port": 8770})
result = await dht.lookup_skill_distributed("llm")  # FIND_VALUE itératif
```

### 4.3. Recherche itérative (alpha-parallèle)

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

- La clé symétrique est dérivée par `HKDF-SHA256` à partir du secret partagé ECDH-X25519.
- Le nonce est **unique par session** ; le récepteur rejette les rejets via un cache glissant de nonces et un contrôle de fraîcheur d'horodatage (voir §5 de `SECURITY_MODEL.md`).
