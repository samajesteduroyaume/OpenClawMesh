<div align="center">

<img src="assets/banner.jpg" alt="OpenClawMesh Hero Banner" width="100%" style="border-radius: 12px; margin-bottom: 20px; box-shadow: 0 10px 30px rgba(0,0,0,0.5);">

<br/>

<img src="https://img.shields.io/badge/OpenClawMesh-v1.2.0-brightgreen?style=for-the-badge&logo=open-source-initiative&logoColor=white" alt="version">
<img src="https://img.shields.io/badge/ClawHub-Verified%20Skill-00E5FF?style=for-the-badge&logo=dependabot&logoColor=white" alt="clawhub">
<img src="https://img.shields.io/badge/Network-Decentralized%20Mesh-7928CA?style=for-the-badge&logo=libp2p&logoColor=white" alt="mesh">

# ⚡ OpenClawMesh

### Decentralized AI Agent Protocol · Universal Multi-Hardware Inference · 100% Free & Sovereign

[🇫🇷 Lire en Français](README.fr.md) · [📜 Whitepaper (Livre Blanc)](WHITEPAPER.md) · [📘 User Manual (Notice)](docs/MANUAL.md) · [📐 Architecture](ARCHITECTURE.md) · [🌐 Gateway Portal](http://localhost:8000)

---

[![License: MIT](https://img.shields.io/badge/License-MIT-brightgreen.svg?style=flat-square)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-blue.svg?style=flat-square&logo=python)](https://www.python.org/)
[![Access: 100% Free](https://img.shields.io/badge/Access-100%25%20Free-00ff88.svg?style=flat-square)](LICENSE)
[![JarvisMesh](https://img.shields.io/badge/JarvisMesh-100%25%20Compatible-cyan.svg?style=flat-square)](#-jarvismesh-compatibility)
[![Tests](https://img.shields.io/badge/Tests-134%20passing-brightgreen.svg?style=flat-square)](file:///Users/selim/Desktop/OpenClawMesh/tests)
[![PQC](https://img.shields.io/badge/Security-PQC%20ML--KEM--768-purple.svg?style=flat-square)](WHITEPAPER.md)

[![Hardware](https://img.shields.io/badge/Hardware-NVIDIA%20%7C%20AMD%20%7C%20Intel%20%7C%20Apple-8a2be2.svg?style=flat-square)](#-universal-hardware-acceleration)


</div>

---

**OpenClawMesh** is a sovereign peer-to-peer framework and modular Skill for **OpenClaw** AI agents. WAN connectivity and NAT port opening (UPnP IGD, PCP RFC 6887, STUN, DHT) are automated upon installation, while LAN-isolated private modes remain accessible via `--no-wan`.

Agents discover each other on the local network and across the Internet, delegate compute, leverage local GPU/NPU hardware, route end-to-end encrypted payloads, stream tokens over sub-10ms UDP tunnels, and share episodic memory — **100% Free, Open-Source & Sovereign**.

> [!IMPORTANT]
> **Security, WAN Access & Operator Privacy:**
> - **Automated WAN Port Opening**: Auto-configures router port mappings via UPnP IGD, PCP (RFC 6887), NAT-PMP & STUN discovery.
> - **Private LAN Isolation Mode**: Run with `--no-wan` or `OPENCLAW_WAN_ENABLED=false` to restrict traffic strictly to localhost / private LAN.
> - **Secured WAN Exposure**: External access uses end-to-end encryption (TLS, ChaCha20-Poly1305, ML-KEM-768 PQC) and Ed25519 authentication.

---

## ✨ Features

<table>
<tr>
<td width="50%">

**🌐 Global Discovery & P2P Routing**
- Zero-config LAN discovery via **mDNS Zeroconf** (JarvisMesh & OpenClawMesh)
- Global WAN routing via **Kademlia DHT 160-bit** with **Content Routing & Provider Records**
- Automated **STUN RFC 5389** NAT traversal & **E2EE Relay**
- Automated **UPnP IGD** and **PCP RFC 6887 / NAT-PMP** port opening upon installation

**⚡ Ultra-Low Latency UDP Transport (QUIC / WebRTC)**
- Direct UDP tunnels with sub-10ms token-by-token streaming
- Lightweight binary protocol framing (`OCQ1` header)
- Asynchronous stream multiplexing and 0-RTT/1-RTT handshakes
- NAT puncture and direct peer connectivity without port forwarding

**📡 GossipSub v1.1 Pub/Sub Overlay**
- Scalable decentralized topic broadcast and auto-stabilizing mesh
- Mesh maintenance (`GRAFT` / `PRUNE` with exponential backoff)
- Eager push combined with lazy gossip (`IHAVE` / `IWANT`)
- Deduplication cache (`mcache`) and peer scoring against spam

</td>
<td width="50%">

**⚡ Multi-Hardware Universal Inference Engine**
- 🟢 **NVIDIA** — CUDA / TensorRT / PyTorch
- 🔴 **AMD** — ROCm / DirectML / HIP
- 🔵 **Intel Core Ultra** — NPU / OpenVINO / AVX-512
- 🟣 **Apple Silicon M1–M4** — Metal GPU via MLX-LM
- ⚪ **CPU Fallback** — Ollama / llama.cpp / vLLM

**🔐 Zero-Trust Security & Anti-Replay**
- **ChaCha20-Poly1305 AEAD** + **X25519 ECDH** — E2EE (relays see only ciphertext)
- **Ed25519** node identities + `TrustStore` access control
- Comprehensive anti-replay: timestamp freshness window + bounded request/nonce cache

**🔀 Distributed Pipeline & MoE**
- Distributed MoE with real quantized tensor buffers
- Native **streaming** (SSE, token-by-token)

**🎯 VRAM Quantization & Semantic Cache**
- Dynamic quantization format selection (4-bit, 8-bit, FP16)
- **Semantic KV-Cache** with LRU memory eviction
</td>
</tr>
</table>

---

## 🏛️ Architecture

```mermaid
graph TD
    subgraph "Your Machine — OpenClaw Agent"
        OC["🤖 OpenClaw Agent"]
        SKILL["📦 Skill OpenClawMesh"]
        Client["📡 MeshClient · WebSocket Pool"]
        E2EE["🔐 E2EE · X25519 + ChaCha20-Poly1305"]
        OC --> SKILL --> Client --> E2EE
    end

    subgraph "Decentralized Mesh — LAN / WAN"
        N1["🟢 NVIDIA CUDA Node"]
        N2["🟣 Apple Silicon MLX Node"]
        N3["🔵 Intel NPU Node"]
        N4["💾 SQLite Vector Memory Node"]
        R["⚡ WAN WebSocket Relay (opaque)"]
    end

    subgraph "Gateway & Command Center"
        GW["🌐 FastAPI Free Gateway"]
        UI["🖥️ Web Portal & Playground"]
        GW --- UI
    end

    Client -.-> N1
    Client -.-> N2
    Client -.-> N3
    Client -.-> N4
    Client -.-> R
    GW -.-> Client
```

---

## 🚀 Quick Start

### 1. Installation

```bash
# Minimal install
pip install openclaw-mesh

# With full cryptography & hardware acceleration
pip install "openclaw-mesh[all]"
```

### 2. Launch the Free Gateway & Web Portal

```bash
# Start gateway on port 8000
uvicorn openclaw_mesh.gateway.server:app --host 127.0.0.1 --port 8000
```
Open **`http://localhost:8000`** in your browser to access the Web Portal & Command Center.

### 3. Generate a Free API Key & Execute Skills

```bash
# Instant free API key generation
curl -X POST http://localhost:8000/api/v1/checkout/free-key \
  -H "Content-Type: application/json" \
  -d '{"email":"community@openclaw.mesh"}'

# Execute inference with your key
export OPENCLAW_API_KEY="sk_claw_..."
curl -X POST http://localhost:8000/api/v1/execute \
  -H "X-API-Key: $OPENCLAW_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"skill":"llm","payload":{"prompt":"Hello decentralized AI!"}}'
```

---

## 🧪 Tests

```bash
# Run full test suite
pytest tests/ -v

# With coverage
pytest tests/ -v --cov=openclaw_mesh

# Specific module
pytest tests/test_gateway.py -v
```

> **70 tests passing** — covering P2P networking, QUIC/WebRTC UDP ultra-low latency streaming, GossipSub v1.1 pub/sub overlay, Kademlia DHT bootstrap, auto-refresh & provider records, UPnP port mapping & STUN traversal, E2EE anti-replay and identity authentication, WAN relay routing, VRAM quantization, multi-modal engines, and the Free Gateway.

---

## 🔁 JarvisMesh Compatibility

OpenClawMesh is **wire-compatible with JarvisMesh 1.0**:
- Same JSON message format (`type`, `skill`, `payload`, `request_id`, `origin`, `ts`, `sig`)
- Same HMAC-SHA256 signing base (canonical sorted JSON)
- Dual mDNS service registration (`_jarvismesh._tcp.local.` + `_openclawmesh._tcp.local.`)

JarvisMesh nodes can call OpenClawMesh nodes and vice versa without any modification.

---

## ⚙️ Configuration

All settings are driven by environment variables (prefix `OPENCLAW_`):

```bash
OPENCLAW_NODE_NAME=my-prod-node      # Node name (mDNS)
OPENCLAW_DEFAULT_PORT=8770           # WebSocket port
OPENCLAW_QUIC_ENABLED=true           # Ultra-low latency UDP QUIC transport
OPENCLAW_QUIC_PORT=8775              # UDP QUIC port
OPENCLAW_GOSSIPSUB_ENABLED=true      # GossipSub v1.1 pub/sub overlay
OPENCLAW_PSK=your_psk_secret         # HMAC pre-shared key
OPENCLAW_E2EE_ENABLED=true           # End-to-end encryption
OPENCLAW_DHT_ENABLED=true            # Kademlia DHT WAN discovery
OPENCLAW_LOG_LEVEL=INFO              # DEBUG / INFO / WARNING
GATEWAY_ADMIN_TOKEN=your_admin_token # Gateway: admin API token
GATEWAY_DB_PATH=/data/keys.db        # Gateway: SQLite path
```

Full reference: [`config.py`](openclaw_mesh/config.py) · [`ARCHITECTURE.md`](ARCHITECTURE.md)

---

## 📁 Project Structure

```
OpenClawMesh/
├── openclaw_mesh/
│   ├── node.py            # Node server (WebSocket + QUIC UDP + GossipSub dispatch)
│   ├── client.py          # MeshClient (WebSocket pool, QUIC stream multiplexing, DHT fallback)
│   ├── protocol.py        # Wire format JSON (TaskRequest/Chunk/Response)
│   ├── bridge.py          # SkillRegistry (sync/async/generator support)
│   ├── crypto.py          # Ed25519 NodeIdentity & TrustStore
│   ├── crypto_e2ee.py     # X25519 + ChaCha20-Poly1305 E2EE sessions
│   ├── discovery.py       # mDNS/Zeroconf LAN discovery
│   ├── config.py          # Pydantic Settings (env-driven singleton)
│   ├── cli.py             # argparse CLI (12 commands: discover, call, stream, ping, serve, dht, gossipsub...)
│   ├── engines/
│   │   ├── hardware.py    # Universal hardware detection
│   │   ├── inference.py   # MLX / CUDA / OpenVINO / CPU inference engine
│   │   ├── model_manager.py   # Auto VRAM quantization & model selection
│   │   ├── distributed_moe.py # Pipeline parallelism across nodes
│   │   └── multimodal.py  # Vision / STT / TTS
│   ├── network/
│   │   ├── quic_webrtc.py # Ultra-low latency UDP QUIC transport & token streaming
│   │   ├── gossipsub.py   # Decentralized Pub/Sub overlay v1.1 (GRAFT/PRUNE, IHAVE/IWANT)
│   │   ├── dht.py         # Kademlia 160-bit DHT & Content Routing / Provider Records
│   │   ├── relay.py       # WAN WebSocket relay (opaque routing)
│   │   └── nat_traversal.py   # STUN RFC 5389 & UPnP auto port mapping NAT discovery
│   └── gateway/
│       ├── server.py      # FastAPI gateway (Free keys, execution, WAN control)
│       ├── db.py          # SQLite KeyDatabase (keys, quotas, audit logs)
│       └── portal.py      # Web UI (Free key generator, command center, playground)
├── tests/                 # 70 unit & integration tests
├── ARCHITECTURE.md        # Full technical documentation (senior engineer level)
├── SKILL.md               # OpenClaw skill descriptor
├── LICENSE                # MIT License (100% Free & Open Source)
└── pyproject.toml
```

---

## 📄 License

OpenClawMesh is distributed under the **[MIT License](LICENSE)** — 100% Free and Open Source.

---

<div align="center">

**OpenClawMesh © 2026 — Decentralized AI · Sovereign Compute · 100% Free**

*Built with ⚡ for AI agents that don't ask permission*

</div>
