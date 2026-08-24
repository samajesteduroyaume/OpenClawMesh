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
