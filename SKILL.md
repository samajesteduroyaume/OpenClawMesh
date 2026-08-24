---
name: openclaw-mesh
description: Connect OpenClaw to local and LAN P2P AI agent meshes (JarvisMesh & OpenClawMesh). Discover active peer nodes, delegate heavy tasks across all hardware architectures (NVIDIA CUDA, AMD ROCm, Intel Core Ultra NPU/OpenVINO, Apple Silicon Metal, and CPU), run Whisper audio STT, Vision models, SQLite vector memory RAG, stream real-time tokens, and expose local tools to the decentralized network.
version: 1.0.0
metadata:
  openclaw:
    requires:
      bins:
        - python3
---

# 🌐 OpenClawMesh — Decentralized P2P AI Mesh Skill

`openclaw-mesh` enables your OpenClaw agent to seamlessly discover, collaborate with, and delegate tasks to other AI agent nodes on your local network (LAN) and peer-to-peer clusters across all hardware architectures, fully utilizing the **JarvisMesh 1.0 P2P Protocol**.

---

## 🎯 When to Use This Skill (Triggers)

Activate this skill when:
1. **Multi-Hardware AI Inference & Task Delegation**: The user wants to run inference across any hardware accelerator:
   - 🟢 **NVIDIA GPUs** (GeForce RTX, A100, H100 via CUDA / TensorRT / PyTorch)
   - 🔴 **AMD GPUs** (Radeon RX, Instinct via ROCm / DirectML / HIP)
   - 🔵 **Intel Core Ultra & Arc** (Intel NPU, OpenVINO, oneAPI, AVX-512)
   - 🟣 **Apple Silicon** (M1/M2/M3/M4 Metal GPU via MLX)
   - ⚪ **Universal CPU** (Ollama, llama.cpp, vLLM, CPU fallback)
2. **Streaming AI Responses**: Real-time token streaming is required for interactive dialogue or large code generation (`llm_stream`).
3. **Local Vector Memory & RAG**: Querying or updating persistent episodic memory stored on SQLite vector store nodes (`memory_search`, `memory_store`, `memory_recall`, `rag_query`).
4. **Multimodal Vision & Audio STT**: Transcribing audio via Whisper (`transcribe_audio`) or analyzing images with Vision models (`vlm_analyze`).
5. **Cluster Peer Discovery**: Checking what AI nodes, machines, and tools are available across your machines on the local Wi-Fi/LAN (`discover`).
6. **Hardware Acceleration Diagnostic**: Inspecting local AI hardware accelerators (`hardware`).
7. **Exposing OpenClaw Tools**: Publishing OpenClaw tools so other JarvisMesh / OpenClaw agents can call them remotely.

---

## 🚀 Quick Execution Guide

All commands can be executed via the unified Python CLI or standalone helper scripts located in `scripts/`.

### 1. Diagnose AI Hardware
Identify available GPU / NPU accelerators on the local machine:
```bash
python3 scripts/mesh_cli.py hardware
```

### 2. Discover Active Mesh Peers
Find all online JarvisMesh & OpenClaw nodes, their addresses, latencies, and advertised skills:
```bash
python3 scripts/mesh_cli.py discover --inspect
```
Or structured JSON output:
```bash
python3 scripts/mesh_discover.py
```

### 3. Delegate a Task (Auto-Routed or Targeted)
Send a task request to the network. If `--peer` is omitted, OpenClawMesh automatically picks the best and least-loaded node:
```bash
# Auto-routed LLM prompt to the best available GPU/NPU node
python3 scripts/mesh_cli.py call --skill llm --payload '{"prompt": "Write a Python FastAPI health check endpoint."}'

# Target a specific peer node (e.g. NVIDIA GPU server or Intel Ultra laptop)
python3 scripts/mesh_cli.py call --peer gpu-server --skill memory_search --payload '{"query": "P2P protocol memory", "top_k": 3}'
```

### 4. Stream LLM Generation Token-by-Token
Stream responses directly to stdout in real time:
```bash
python3 scripts/mesh_cli.py stream --skill llm_stream --payload '{"prompt": "Explain quantum computing in 3 bullet points."}'
```
Or via script:
```bash
python3 scripts/mesh_stream.py llm_stream '{"prompt": "Summarize today tasks."}'
```

### 5. Check Health & Latency
Probe a specific peer node:
```bash
python3 scripts/mesh_cli.py ping --peer mac-m3
```

### 6. Run OpenClaw as a Mesh Node
Expose local OpenClaw capabilities as a discoverable P2P service:
```bash
python3 scripts/mesh_cli.py serve --name openclaw-worker --port 8770
```

---

## 🛠️ Available Mesh Skills Reference

When interacting with a standard JarvisMesh / OpenClawMesh cluster, the following skills are commonly available:

| Skill Name | Parameters (Payload) | Description |
| :--- | :--- | :--- |
| `llm` | `{"prompt": str, "model": str, "temperature": float, "max_tokens": int}` | Universal AI inference (NVIDIA CUDA, AMD ROCm, Intel NPU, Apple Silicon Metal, CPU) |
| `llm_stream` | `{"prompt": str, "model": str, "temperature": float}` | Real-time streaming LLM token generation |
| `memory_store` | `{"content": str, "metadata": dict, "doc_id": str}` | Stores a text chunk into persistent SQLite vector DB |
| `memory_search` | `{"query": str, "top_k": int}` | Semantic cosine similarity search |
| `memory_recall` | `{"query": str, "top_k": int}` | Recalls past conversational context |
| `transcribe_audio`| `{"audio_base64": str, "model_size": str}` | Whisper Speech-to-Text audio transcription |
| `vlm_analyze` | `{"image_base64": str, "prompt": str}` | Vision multimodal image reasoning |
| `rag_query` | `{"query": str, "k": int}` | Hybrid BM25 / TF-IDF document retrieval |
| `_describe_skills`| `{}` | Introspects full skill catalog and schemas |
| `_health` | `{}` | Returns node status, active tasks, hardware & uptime |

---

## 🔐 Security & Zero-Trust Mesh

OpenClawMesh supports two authentication modes:

### A. Pre-Shared Key (HMAC-SHA256)
Set `--psk <shared_secret>` on both server and client:
```bash
python3 scripts/mesh_cli.py call --skill llm --payload '{"prompt": "Hello"}' --psk "my_secret_token"
```

### B. Asymmetric Ed25519 Signatures
1. Generate an identity keypair:
   ```bash
   python3 scripts/mesh_cli.py keygen --out ~/.openclaw/identity.key
   ```
2. Call nodes using the private key:
   ```bash
   python3 scripts/mesh_cli.py call --skill llm --payload '{"prompt": "Hello"}' --keyfile ~/.openclaw/identity.key
   ```

---

## 📋 Python API (for custom OpenClaw Plugins / Tools)

```python
import asyncio
from openclaw_mesh import MeshClient

async def main():
    # Initialize client
    client = MeshClient(name="openclaw-agent")
    await client.start()
    
    # Discover peers
    await asyncio.sleep(1.5)
    print("Peers detected on LAN:", client.list_peers())

    # Call remote GPU / NPU inference node
    response = await client.delegate(
        skill="llm",
        payload={"prompt": "Explain quantum computing in one sentence."}
    )
    print("Result:", response.result)

    await client.stop()

if __name__ == "__main__":
    asyncio.run(main())
```
