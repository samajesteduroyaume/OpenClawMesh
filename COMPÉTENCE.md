# OpenClawMesh pour Claw Hub

Cette compétence connecte OpenClaw à un maillage pair-à-pair d'agents IA. Elle permet de découvrir des pairs, déléguer des tâches, partager des compétences et interroger des nœuds de mémoire ou d'inférence.

Le manifeste technique compatible Claw Hub se trouve dans [SKILL.md](SKILL.md). Ce document en présente l'utilisation en français.

## Activation

Utiliser cette compétence lorsque l'utilisateur demande :

- de découvrir des agents ou des accélérateurs disponibles sur le LAN ou le WAN ;
- de déléguer une inférence, une recherche mémoire, une transcription ou une analyse d'image ;
- d'exécuter une compétence distante ou d'exposer un outil OpenClaw ;
- de publier ou rechercher une compétence dans la DHT ;
- de diagnostiquer le matériel local ou l'état du maillage.

## Installation

```bash
pip install openclaw-mesh
```

Pour les dépendances optionnelles (matériel, cryptographie et transports avancés) :

```bash
pip install "openclaw-mesh[all]"
```

## Commandes principales

Découvrir les pairs du réseau local :

```bash
python3 scripts/mesh_cli.py discover --inspect
```

Déléguer une tâche au meilleur pair disponible :

```bash
python3 scripts/mesh_cli.py call \
  --skill llm \
  --payload '{"prompt":"Résume ce texte en trois points."}'
```

Démarrer un nœud OpenClawMesh :

```bash
python3 scripts/mesh_cli.py serve --name openclaw-worker --port 8770
```

## Compétences courantes

| Nom | Usage |
| --- | --- |
| `llm` | Inférence de texte à distance |
| `llm_stream` | Génération de texte en streaming |
| `memory_store` | Stockage dans la mémoire vectorielle |
| `memory_search` | Recherche sémantique |
| `transcribe_audio` | Transcription audio avec Whisper |
| `vlm_analyze` | Analyse d'image par modèle vision |
| `rag_query` | Recherche documentaire hybride |
| `_describe_skills` | Description du catalogue de compétences |
| `_health` | État et santé du nœud |

## Permissions et sécurité

- Les accès réseau sortants (mDNS, WebSocket/WSS, DHT UDP et STUN) nécessitent le consentement de l'utilisateur.
- Les requêtes, fichiers, médias, souvenirs et résultats d'outils envoyés à un pair peuvent quitter la machine locale.
- L'accès aux clés d'identité, à la PSK et au `TrustStore` est limité aux chemins configurés.
- Le réseau entrant est désactivé par défaut ; l'exposition WAN doit utiliser TLS avec une PSK ou un `TrustStore`.
- Vérifier l'identité et les permissions d'un pair avant d'envoyer des données sensibles.

## Documentation

- [Guide de la compétence](SKILL.md)
- [Manuel](docs/MANUAL.md)
- [Architecture](ARCHITECTURE.md)
- [Modèle de sécurité](references/SECURITY_MODEL.md)