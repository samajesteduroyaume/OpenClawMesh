# 📘 MANUEL D'UTILISATION COMPLET & NOTICE TECHNIQUE — OpenClawMesh v1.2.0

Guide pratique d'installation, configuration, commandes CLI, intégration d'agents et exploitation en production d'**OpenClawMesh**.

---

## 📑 Table des Matières

1. [Installation & Prérequis](#1-installation--prérequis)
2. [Démarrage Rapide en 1 Minute](#2-démarrage-rapide-en-1-minute)
3. [Référence Complète des Commandes CLI](#3-référence-complète-des-commandes-cli)
4. [Intégration API Universelle (OpenAI, Anthropic, Ollama, MCP)](#4-intégration-api-universelle)
5. [Connecteurs Frameworks Multi-Agents (CrewAI, AutoGen, LangGraph)](#5-connecteurs-frameworks-multi-agents)
6. [Parallélisme de Pipeline & Sharding Multi-Machines (70B+)](#6-parallélisme-de-pipeline--sharding-multi-machines)
7. [Voice-to-Voice (<150ms) & Vision Vidéo Temps Réel](#7-voice-to-voice--vision-vidéo-temps-réel)
8. [Sécurité, Cryptographie PQC & Gestion des Clés](#8-sécurité-cryptographie-pqc--gestion-des-clés)
9. [Déploiement en Démon Système (systemd, launchd, Docker)](#9-déploiement-en-démon-système)
10. [Application Desktop MenuBar 1-Clic](#10-application-desktop-menubar-1-clic)
11. [Diagnostic & Résolution des Problèmes (FAQ)](#11-diagnostic--résolution-des-problèmes)

---

## 1. Installation & Prérequis

### Prérequis Système
* **Python** : Version 3.10, 3.11 ou 3.12 recommandée.
* **Systèmes d'exploitation** : macOS (Apple Silicon M1–M4 ou Intel), Linux (Ubuntu, Debian, Arch, RHEL), Windows 10/11 (WSL2 ou natif).
* **Accélérateurs matériels supportés** :
  * 🍏 **Apple Silicon** : Metal GPU via MLX & MPS.
  * 🟢 **NVIDIA** : CUDA 11.8+ / 12.x avec vLLM ou PyTorch.
  * 🔴 **AMD** : ROCm / HIP.
  * 🔵 **Intel** : Core Ultra NPU via OpenVINO & oneAPI.
  * 💻 **CPU Universel** : Exécution optimisée AVX-512 / ARM NEON.

### Installation depuis les sources

```bash
# Cloner le dépôt
git clone https://github.com/samajesteduroyaume/OpenClawMesh.git
cd OpenClawMesh

# Créer et activer l'environnement virtuel
python3 -m venv .venv
source .venv/bin/activate  # Sur Windows: .venv\Scripts\activate

# Installer le package en mode éditable avec toutes les dépendances
pip install -e .
```

---

## 2. Démarrage Rapide en 1 Minute

### 1. Diagnostiquer votre matériel et réseau
```bash
openclaw-mesh doctor
```

### 2. Démarrer la passerelle et le nœud local
```bash
openclaw-mesh serve --port 8000
```
* Le tableau de bord Web s'ouvre sur : **`http://localhost:8000`**
* Le serveur mDNS diffuse automatiquement votre présence aux autres machines du réseau local.

### 3. Exécuter une inférence distribuée depuis un autre terminal
```bash
openclaw-mesh call --prompt "Explique la théorie de la relativité en 2 phrases."
```

---

## 3. Référence Complète des Commandes CLI

L'exécutable `openclaw-mesh` offre un ensemble complet de commandes :

### 🔍 `openclaw-mesh doctor`
Effectue un diagnostic instantané du matériel, des ports réseau, de la cryptographie post-quantique et de l'intégrité du système.
* **Options** :
  * `--json` : Sortie au format JSON pour intégration dans des scripts de monitoring.

### 📡 `openclaw-mesh discover`
Scanne le réseau local (mDNS) et la table DHT pour lister tous les nœuds pairs disponibles et leurs capacités de calcul.
* **Options** :
  * `--timeout <secondes>` : Durée de recherche (défaut : `3.0`).
  * `--json` : Affichage structuré en JSON.

### ⚡ `openclaw-mesh call`
Envoie une invite d'inférence à un nœud pair ou au maillage avec sélection automatique du meilleur pair.
* **Options** :
  * `--prompt <texte>` : (Requis) Le texte de l'invite.
  * `--node <id>` : Cibler un nœud spécifique par son identifiant.
  * `--model <nom>` : Spécifier le modèle souhaité (ex: `qwen2.5-coder-7b`, `llama-3.1-8b`).
  * `--max-tokens <n>` : Nombre maximal de tokens à générer (défaut : `512`).
  * `--temperature <float>` : Température d'échantillonnage (défaut : `0.7`).

### 🌊 `openclaw-mesh stream`
Reçoit la réponse en flux continu (token par token) en temps réel dans le terminal.
* **Options** :
  * `--prompt <texte>` : (Requis) L'invite utilisateur.
  * `--model <nom>` : Modèle cible.

### 🚀 `openclaw-mesh serve`
Démarre le démon de nœud et la passerelle HTTP/WebSocket d'OpenClawMesh.
* **Options** :
  * `--port <port>` : Port HTTP de la passerelle (défaut : `8000`).
  * `--host <ip>` : Adresse IP d'écoute (défaut : `0.0.0.0`).
  * `--wan` : Active l'enregistrement sur la table DHT WAN et les relais NAT.
  * `--e2ee` : Force le chiffrement de bout en bout strict.
  * `--pqc` : Active l'encapsulation post-quantique ML-KEM-768.

### 🔑 `openclaw-mesh keygen`
Génère une nouvelle paire de clés d'identité cryptographique Ed25519 et une paire post-quantique ML-KEM-768.
* **Options** :
  * `--out <chemin>` : Fichier de sauvegarde de la clé privée (défaut : `~/.openclaw/identity.json`).

### 💻 `openclaw-mesh hardware`
Affiche le profil matériel détecté (GPU, VRAM totale et libre, NPU, CPU, backend recommandé).

### 🏓 `openclaw-mesh ping`
Mesure la latence réseau aller-retour (RTT) avec un nœud pair.
* **Options** :
  * `--node <id>` : Identifiant du nœud cible.
  * `--count <n>` : Nombre de pings (défaut : `4`).

---

## 4. Intégration API Universelle

OpenClawMesh expose des interfaces standardisées compatibles avec tout l'écosystème IA :

### 1. Utilisation avec le SDK Python `openai`

```python
from openai import OpenAI

client = OpenAI(
    base_url="http://localhost:8000/v1",
    api_key="sk-openclaw-free-local-key",  # Clé libre de développement
)

# Chat Completions avec streaming
response = client.chat.completions.create(
    model="qwen2.5-coder-7b",
    messages=[{"role": "user", "content": "Écris une fonction Python de tri rapide."}],
    stream=True,
)

for chunk in response:
    if chunk.choices[0].delta.content:
        print(chunk.choices[0].delta.content, end="", flush=True)
print()

# Génération d'embeddings vectoriels
emb = client.embeddings.create(
    model="text-embedding-3-small",
    input="Recherche sémantique décentralisée",
)
print(f"Dimension vecteur : {len(emb.data[0].embedding)}")
```

### 2. Utilisation avec le SDK Python `anthropic`

```python
import anthropic

client = anthropic.Anthropic(
    base_url="http://localhost:8000",
    api_key="sk-ant-openclaw-key",
)

message = client.messages.create(
    model="claude-3-5-sonnet-20241022",
    max_tokens=1024,
    messages=[{"role": "user", "content": "Analyse les avantages d'un réseau P2P."}],
)
print(message.content[0].text)
```

### 3. Utilisation avec le CLI `ollama`

```bash
# Pointer Ollama vers votre passerelle OpenClawMesh
export OLLAMA_HOST="http://localhost:8000"

# Lancer une inférence directe
ollama run qwen2.5-coder-7b "Génère une classe TypeScript pour gérer un panier d'achats."
```

### 4. Configuration Claude Desktop / Cursor (MCP Protocol)

Ajoutez cette configuration dans votre fichier `claude_desktop_config.json` :

```json
{
  "mcpServers": {
    "openclaw-mesh": {
      "command": "python",
      "args": ["-m", "openclaw_mesh.mcp_server", "--stdio"]
    }
  }
}
```

Ou via le transport SSE distant :
* **URL SSE** : `http://localhost:8000/mcp/sse`
* **URL Messages** : `http://localhost:8000/mcp/messages`

---

## 5. Connecteurs Frameworks Multi-Agents

### 🤖 CrewAI
```python
from crewai import Agent, Task, Crew
from openclaw_mesh.connectors.crewai import OpenClawCrewAILLM

# Instancier le LLM souverain OpenClawMesh
mesh_llm = OpenClawCrewAILLM(model="qwen2.5-coder-7b")

dev_agent = Agent(
    role="Architecte Logiciel Senior",
    goal="Concevoir des architectures distribuées résilientes",
    backstory="Expert en protocoles P2P et chiffrement post-quantique.",
    llm=mesh_llm,
)

task = Task(
    description="Proposer un protocole de synchronisation d'état pour 100 nœuds.",
    expected_output="Un document technique structuré en markdown.",
    agent=dev_agent,
)

crew = Crew(agents=[dev_agent], tasks=[task])
result = crew.kickoff()
print(result)
```

### 🤖 Microsoft AutoGen
```python
import asyncio
from openclaw_mesh.connectors.autogen import OpenClawAutoGenClient

async def run_autogen():
    client = OpenClawAutoGenClient(model="qwen2.5-coder-7b")
    response = await client.create({
        "messages": [{"role": "user", "content": "Rédige une suite de tests unitaires pour une file d'attente async."}]
    })
    print(client.message_retrieval(response)[0])

asyncio.run(run_autogen())
```

### 🤖 LangGraph
```python
from langgraph.graph import StateGraph, START, END
from openclaw_mesh.connectors.langgraph import OpenClawGraphNode

# Créer un nœud de calcul relié au maillage P2P
mesh_node = OpenClawGraphNode(skill="llm", state_key="messages", output_key="messages")

workflow = StateGraph(dict)
workflow.add_node("agent", mesh_node)
workflow.add_edge(START, "agent")
workflow.add_edge("agent", END)

app = workflow.compile()
state = app.invoke({"messages": [{"role": "user", "content": "Explique les CRDTs en une phrase."}]})
print(state["messages"][-1]["content"])
```

---

## 6. Parallélisme de Pipeline & Sharding Multi-Machines

Pour découper un modèle de 70B à 671B sur plusieurs machines de votre réseau :

```python
import asyncio
from openclaw_mesh.engines.distributed_cluster import MultiMachineClusterOrchestrator

async def run_cluster():
    orchestrator = MultiMachineClusterOrchestrator(cluster_name="lab-cluster")

    # Déclaration des nœuds pairs disponibles
    peers = [
        {"node_id": "node-mac", "node_name": "Mac Studio M2 Ultra", "hardware_type": "apple_metal", "vram_mb": 128000},
        {"node_id": "node-pc", "node_name": "Rig RTX 4090", "hardware_type": "nvidia_cuda", "vram_mb": 24000},
        {"node_id": "node-srv", "node_name": "Serveur Xeon NPU", "hardware_type": "intel_npu", "vram_mb": 32000},
    ]

    # Planification automatique de l'allocation des couches
    topology = orchestrator.plan_distribution(
        model_name="deepseek-v3-671b",
        total_layers=60,
        hidden_dim=4096,
        available_peers=peers,
    )

    # Exécution du passage avant distribué
    result = await orchestrator.execute_forward_pass(
        model_name="deepseek-v3-671b",
        prompt="Synthétise les principes de la mécanique quantique.",
    )
    print(result["generated_text"])
    print(f"Latence totale : {result['total_latency_ms']} ms")

asyncio.run(run_cluster())
```

---

## 7. Voice-to-Voice & Vision Vidéo Temps Réel

### Streaming Vocal (<150ms)
```python
import asyncio
from openclaw_mesh.engines.voice_pipeline import RealTimeVoicePipeline, VoiceStreamConfig

async def demo_voice():
    pipeline = RealTimeVoicePipeline(VoiceStreamConfig(language="fr"))

    async def mic_stream():
        # Simulation d'un flux audio micro
        for _ in range(5):
            yield b"\x00\x7f" * 320

    async for event in pipeline.process_voice_turn(mic_stream()):
        if event["type"] == "transcription":
            print(f"🗣️ Transcription : {event['text']}")
        elif event["type"] == "audio_response":
            print(f"🔊 Réponse parlée ({event['latency_ms']}ms) : {event['text']}")

asyncio.run(demo_voice())
```

---

## 8. Sécurité, Cryptographie PQC & Gestion des Clés

### Structure des Identités
Chaque nœud dispose d'un trousseau cryptographique stocké dans `~/.openclaw/identity.json` :
1. **Clé Ed25519** : Signature numérique et authentification P2P.
2. **Clé ML-KEM-768** : Encapsulation post-quantique pour les sessions E2EE.
3. **Clé X25519** : Diffie-Hellman pour le protocole Double Ratchet (PFS).

### Autorisation de Nœuds (TrustStore)
Pour restreindre l'accès à votre maillage aux seules machines approuvées :
```bash
# Ajouter une clé publique autorisée
openclaw-mesh trust add --node-id <public_key_hex> --name "MacBook-Sophie"
```

---

## 9. Déploiement en Démon Système

Utilisez le script automatique [service_installer.py](file:///Users/selim/Desktop/OpenClawMesh/scripts/service_installer.py) :

### Linux (systemd)
```bash
python scripts/service_installer.py --type systemd --port 8000 --out /etc/systemd/system/openclaw-mesh.service
sudo systemctl daemon-reload
sudo systemctl enable --now openclaw-mesh
sudo systemctl status openclaw-mesh
```

### macOS (launchd)
```bash
python scripts/service_installer.py --type launchd --port 8000 --out ~/Library/LaunchAgents/com.openclaw.mesh.plist
launchctl load ~/Library/LaunchAgents/com.openclaw.mesh.plist
```

### Docker Compose
```bash
python scripts/service_installer.py --type docker --out docker-compose.yml
docker compose up -d
```

---

## 10. Application Desktop MenuBar 1-Clic

Lancez l'application de barre des menus intégrée :
```bash
python scripts/desktop_tray.py --port 8000 --vram 8192
```
* **Fonctionnalités** :
  * Découverte automatique des collègues sur le Wi-Fi local.
  * Curseur de réglage de la VRAM partagée avec le réseau.
  * Bouton pause instantané pour libérer vos ressources lors de sessions de jeu ou de montage vidéo.

---

## 11. Diagnostic & Résolution des Problèmes (FAQ)

### Q1 : La commande `openclaw-mesh doctor` signale un port occupé (8000 ou 8770).
**Solution** : Spécifiez un port alternatif lors du lancement :
```bash
openclaw-mesh serve --port 8080
```

### Q2 : Deux machines sur le même Wi-Fi ne se découvrent pas.
* Vérifiez que le pare-feu n'isole pas les paquets multicast UDP (port `5353` pour mDNS).
* Forcez la connexion directe par adresse IP :
```bash
openclaw-mesh ping --node 192.168.1.45:8770
```

### Q3 : Comment vérifier que l'accélération GPU Metal ou CUDA est bien active ?
Lancez la commande :
```bash
openclaw-mesh hardware
```
Elle affichera le nom du GPU, la mémoire VRAM détectée et le moteur sélectionné (`mlx`, `cuda`, ou `openvino`).

---

**OpenClawMesh est 100% open-source sous licence MIT.**  
Pour toute question ou contribution : rejoignez le dépôt GitHub et lancez `openclaw-mesh doctor` !
