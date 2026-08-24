# 🔐 OpenClawMesh — Modèle de Sécurité & Authentification

OpenClawMesh implémente deux niveaux de sécurité cryptographique compatibles avec JarvisMesh.

---

## 1. Mode Pre-Shared Key (HMAC-SHA256)

Dans ce mode, tous les nœuds de confiance partagent une clé secrète commune (`psk`).

### Base de calcul du HMAC :
1. Sérialisation canonique du payload : `payload_json = json.dumps(payload, sort_keys=True, separators=(",", ":"))`
2. Chaîne canonique :
   ```text
   {request_id}|{origin}|{skill}|{ts!r}|{payload_json}
   ```
3. Signature : `HMAC-SHA256(psk, base)` au format hexadécimal.

---

## 2. Mode Asymétrique Ed25519 (Zero-Trust)

Chaque agent dispose de sa propre paire de clés Ed25519 :
- Clé privée : conservée localement avec permissions `0600`.
- Clé publique : diffusée et enregistrée dans les `TrustStore` des pairs autorisés.

### Base de signature Ed25519 :
```text
{request_id}|{origin}|{pubkey_hex}|{skill}|{ts!r}|{payload_json}
```

### Protection anti-rejeu :
Chaque requête inclut un timestamp flottant `ts`. Un nœud récepteur rejette toute requête dont la dérive temporelle dépasse 300 secondes (`max_drift_seconds = 300.0`).
