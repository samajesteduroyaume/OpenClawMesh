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
Chaque requête inclut un timestamp flottant `ts`. Un nœud récepteur rejette toute requête dont la dérive temporelle dépasse 300 secondes (`signature_max_drift_seconds = 300.0`).

---

## 3. Chiffrement de Bout en Bout (E2EE) & Anti-Rejet

### 3.1. Échange de clé & chiffrement (X25519 / ChaCha20-Poly1305 AEAD)

Les charges utiles échangées entre pairs — y compris celles transitant par des relais WAN — sont protégées par **ChaCha20-Poly1305 (AEAD)** avec une clé dérivée via **ECDH X25519 + HKDF-SHA256** :

- Chaque session génère une paire de clés X25519 pour sa durée de vie.
- La clé symétrique est dérivée par `HKDF-SHA256` (sel `openclaw_e2ee_salt_v1`, info `openclaw_mesh_e2ee_session_key`).
- Le nonce est aléatoire de 96 bits, **unique par session** (suivi en mémoire pour éviter toute collision).

### 3.2. Format du paquet chiffré

```json
{
  "version": "1.0",
  "algorithm": "ChaCha20-Poly1305",
  "ephemeral_pubkey": "<hex clé publique X25519 de l'émetteur>",
  "nonce": "<hex nonce 96 bits>",
  "ciphertext": "<hex ciphertext+tag>",
  "data_type": "json | text | bytes",
  "timestamp": 1740432000.123
}
```

En production, une session doit être liée aux identités Ed25519 de confiance afin
de prévenir une attaque man-in-the-middle. Dans ce mode, l'émetteur signe les
métadonnées critiques du paquet et le destinataire vérifie
`peer_identity_public_key` avant le déchiffrement :

```python
alice = E2EESession(
    identity=alice_identity,
    peer_identity_public_key=bob_identity.public_key_hex,
)
bob = E2EESession(
    identity=bob_identity,
    peer_identity_public_key=alice_identity.public_key_hex,
)
```

### 3.3. Anti-rejet (replay)

Le déchiffrement d'un paquet applique **deux couches de protection** :

1. **Fraîcheur d'horodatage** : si `abs(now - timestamp)` dépasse `e2ee_max_drift_seconds` (300 s par défaut), le paquet est rejeté (`ReplayError`). Protège contre un paquet capturé et réinjecté ultérieurement.
2. **Cache de nonces** : un cache glissant (sliding-window) mémorise chaque nonce vu. Un paquet dont le nonce a déjà été consommé (rejeu immédit) est rejeté (`ReplayError`), même si son horodatage est toujours valide. Le cache est borné (`e2ee_nonce_cache_size`) et évite les entrées expirées.

```python
session = E2EESession()
session.establish_with_peer(bob_public_key_bytes)
pkg = session.encrypt({"cmd": "run_task"})
# Un deuxième appel avec le même paquet est rejeté :
session.decrypt(pkg)  # OK
session.decrypt(pkg)  # -> ReplayError (nonce déjà vu)
```

Les RPC DHT peuvent être authentifiés en configurant le même `OPENCLAW_PSK` sur
les nœuds participants. Sans PSK, la DHT doit être considérée comme un mécanisme
de découverte non fiable.
