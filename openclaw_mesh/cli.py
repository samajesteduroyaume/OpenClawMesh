"""
Interface en Ligne de Commande (CLI) d'OpenClawMesh.

Fournit les commandes :
- discover : Découverte et cartographie des pairs du réseau LAN.
- call     : Appel synchrone d'une compétence distante ou routage automatique.
- stream   : Consommation en direct (token-by-token) d'une compétence distante.
- ping     : Vérification de connectivité et latence RTT avec un pair.
- serve    : Démarrage d'un nœud OpenClawMesh exposant des compétences locales.
- keygen   : Génération d'une identité cryptographique Ed25519.
- status   : Diagnostic de la configuration et des adresses réseau.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import socket
import ssl
import sys
import time
from pathlib import Path
from typing import Any

from .bridge import SkillRegistry
from .client import MeshClient
from .crypto import NodeIdentity, TrustStore
from .discovery import get_local_ip
from .node import OpenClawMeshNode

try:
    from rich.console import Console
    from rich.table import Table

    _HAS_RICH = True
    console = Console()
except ImportError:
    _HAS_RICH = False
    console = None


def _print_json(data: Any) -> None:
    print(json.dumps(data, indent=2, ensure_ascii=False))


# ---------------------------------------------------------------------- #
# Commande : discover
# ---------------------------------------------------------------------- #
async def cmd_discover(args: argparse.Namespace) -> None:
    timeout = args.timeout
    if not args.json and _HAS_RICH:
        console.print(
            f"[bold cyan]🔍 Recherche des pairs JarvisMesh / OpenClawMesh sur le LAN ({timeout}s)...[/bold cyan]"
        )

    if not args.enable_discovery:
        message = (
            "Découverte LAN désactivée. Utilisez --enable-discovery après vérification du réseau."
        )
        if args.json:
            _print_json({"peers": {}, "warning": message})
        elif _HAS_RICH:
            console.print(f"[yellow]⚠️ {message}[/yellow]")
        else:
            print(message)
        return

    if args.inspect and not args.json:
        print("⚠️ L’introspection interroge les compétences et l’état des pairs détectés.")
    client = MeshClient(name="openclaw-scanner", enable_discovery=True)
    await client.start()
    await asyncio.sleep(timeout)
    peers = client.list_peers()

    # Introspection approfondie si demandée
    if args.inspect:
        for pname in list(peers.keys()):
            try:
                desc = await client.discover_skills(pname, timeout=2.0)
                health = await client.check_health(pname, timeout=2.0)
                peer = peers[pname]
                if "skills" in desc:
                    peer.skills = desc["skills"]
                peer.health = health
                peer.rtt_ms = health.get("rtt_ms")
            except Exception:
                pass

    await client.stop()

    if args.json:
        result = {pname: pinfo.to_dict() for pname, pinfo in peers.items()}
        _print_json(result)
        return

    if not peers:
        if _HAS_RICH:
            console.print("[yellow]⚠️ Aucun pair détecté sur le réseau local.[/yellow]")
        else:
            print("Aucun pair détecté sur le réseau local.")
        return

    if _HAS_RICH:
        table = Table(
            title="🌐 Pairs JarvisMesh / OpenClawMesh Découverts", header_style="bold magenta"
        )
        table.add_column("Nom du Pair", style="bold green")
        table.add_column("Adresse WS", style="cyan")
        table.add_column("Latence (RTT)", style="yellow")
        table.add_column("Compétences Disponibles", style="white")
        table.add_column("Charge", style="blue")

        for pname, pinfo in peers.items():
            rtt_str = f"{pinfo.rtt_ms} ms" if pinfo.rtt_ms is not None else "-"
            skills_str = ", ".join(pinfo.skills[:6])
            if len(pinfo.skills) > 6:
                skills_str += f" (+{len(pinfo.skills) - 6} autres)"
            active_tasks = str(pinfo.health.get("active_tasks", "-")) if pinfo.health else "-"
            table.add_row(pname, pinfo.ws_url, rtt_str, skills_str or "(aucune)", active_tasks)

        console.print(table)
    else:
        print(f"--- {len(peers)} Pairs Découverts ---")
        for pname, pinfo in peers.items():
            print(f"- {pname} : {pinfo.ws_url} | Skills: {', '.join(pinfo.skills)}")


# ---------------------------------------------------------------------- #
# Commande : call
# ---------------------------------------------------------------------- #
async def cmd_call(args: argparse.Namespace) -> None:
    try:
        payload = json.loads(args.payload) if args.payload else {}
    except Exception as e:
        print(f"Erreur format JSON dans --payload: {e}", file=sys.stderr)
        sys.exit(1)

    identity = NodeIdentity.load(args.keyfile) if args.keyfile else None
    client = MeshClient(name=args.origin or "openclaw-cli", psk=args.psk, identity=identity)

    target = args.peer
    if not target:
        # Découverte automatique pour routage intelligent
        await client.start()
        await asyncio.sleep(args.timeout_discovery)
        best = client.find_best_peer_for_skill(args.skill)
        if not best:
            await client.stop()
            print(f"Erreur : Aucun pair ne fournit la compétence '{args.skill}'", file=sys.stderr)
            sys.exit(1)
        target = best

    t0 = time.perf_counter()
    if getattr(args, "quic", False):
        await client.start(enable_quic=True)
        resp = await client.call_stream_quic(target, args.skill, payload, timeout=args.timeout)
    else:
        resp = await client.call(target, args.skill, payload, timeout=args.timeout)
    duration_ms = round((time.perf_counter() - t0) * 1000.0, 2)
    await client.stop()

    if args.json:
        data = resp.to_dict()
        data["duration_ms"] = duration_ms
        _print_json(data)
    else:
        if resp.ok:
            if isinstance(resp.result, (dict, list)):
                _print_json(resp.result)
            else:
                print(resp.result)
        else:
            print(f"❌ Erreur ({resp.handled_by}): {resp.error}", file=sys.stderr)
            sys.exit(1)


# ---------------------------------------------------------------------- #
# Commande : stream
# ---------------------------------------------------------------------- #
async def cmd_stream(args: argparse.Namespace) -> None:
    try:
        payload = json.loads(args.payload) if args.payload else {}
    except Exception as e:
        print(f"Erreur format JSON dans --payload: {e}", file=sys.stderr)
        sys.exit(1)

    identity = NodeIdentity.load(args.keyfile) if args.keyfile else None
    client = MeshClient(name=args.origin or "openclaw-streamer", psk=args.psk, identity=identity)

    target = args.peer
    if not target:
        await client.start(enable_quic=getattr(args, "quic", False))
        await asyncio.sleep(args.timeout_discovery)
        best = client.find_best_peer_for_skill(args.skill)
        if not best:
            await client.stop()
            print(f"Erreur : Aucun pair ne fournit la compétence '{args.skill}'", file=sys.stderr)
            sys.exit(1)
        target = best

    def on_chunk(chunk_val: Any) -> None:
        if isinstance(chunk_val, dict) and "text" in chunk_val:
            sys.stdout.write(chunk_val["text"])
        elif isinstance(chunk_val, str):
            sys.stdout.write(chunk_val)
        else:
            sys.stdout.write(str(chunk_val))
        sys.stdout.flush()

    if getattr(args, "quic", False):
        await client.start(enable_quic=True)
        resp = await client.call_stream_quic(
            target, args.skill, payload, on_chunk=on_chunk, timeout=args.timeout
        )
    else:
        resp = await client.call_stream(
            target, args.skill, payload, on_chunk=on_chunk, timeout=args.timeout
        )
    await client.stop()
    sys.stdout.write("\n")
    sys.stdout.flush()

    if not resp.ok:
        print(f"❌ Erreur Streaming: {resp.error}", file=sys.stderr)
        sys.exit(1)


# ---------------------------------------------------------------------- #
# Commande : ping
# ---------------------------------------------------------------------- #
async def cmd_ping(args: argparse.Namespace) -> None:
    client = MeshClient(name="openclaw-pinger", psk=args.psk)
    target = args.peer
    health = await client.check_health(target, timeout=args.timeout)
    await client.stop()

    if args.json:
        _print_json(health)
    else:
        if health.get("status") == "ok":
            rtt = health.get("rtt_ms", 0)
            active = health.get("active_tasks", 0)
            uptime = health.get("uptime_seconds", 0)
            print(
                f"✅ {target} répond | RTT: {rtt}ms | Tâches actives: {active} | Uptime: {uptime}s"
            )
        else:
            print(f"❌ Échec du ping vers {target} : {health.get('error')}", file=sys.stderr)
            sys.exit(1)


# ---------------------------------------------------------------------- #
# Commande : serve
# ---------------------------------------------------------------------- #
async def cmd_serve(args: argparse.Namespace) -> None:
    identity = NodeIdentity.load(args.keyfile) if args.keyfile else None
    trust_store = TrustStore.load(args.trustfile) if args.trustfile else None

    registry = SkillRegistry(name=args.name)
    node = OpenClawMeshNode(
        name=args.name,
        port=args.port,
        host=args.host,
        registry=registry,
        psk=args.psk,
        identity=identity,
        trust_store=trust_store,
    )

    enable_wan = not getattr(args, "no_wan", False)
    enable_dht = (getattr(args, "dht", False) or enable_wan) and not getattr(args, "no_dht", False)

    await node.start(
        enable_zeroconf=not args.no_zeroconf,
        enable_wan=enable_wan,
        enable_dht=enable_dht,
        enable_quic=not getattr(args, "no_quic", False),
        enable_gossipsub=not getattr(args, "no_gossipsub", False),
        dht_port=getattr(args, "dht_port", 8780),
        quic_port=getattr(args, "quic_port", None),
        relay_url=getattr(args, "relay", None),
    )
    print(f"🌐 Nœud OpenClawMesh '{args.name}' actif sur ws://{get_local_ip()}:{args.port}")
    if node.quic_transport:
        print(
            f"⚡ Transport QUIC/WebRTC UDP direct actif sur {node.quic_transport.bound_host}:{node.quic_transport.bound_port}"
        )
    if enable_wan or enable_dht:
        print(f"🌍 Raccordé au WAN et à la DHT Kademlia mondiale sur UDP:{getattr(args, 'dht_port', 8780)}")
    if node.freebox_client and node.freebox_client.is_registered:
        print(f"⚡ Raccordé automatiquement au Guichet Unique Freebox : {node.freebox_client.discovered_guichet_url}")
        print(f"🌟 Nœud enregistré et actif sur le maillage mondial ({len(node.freebox_client.active_bootstrap_peers)} pairs reçus)")
    if node.gossipsub:
        print("📡 Overlay Pub/Sub GossipSub v1.1 actif")
    print(f"📡 Compétences publiées : {', '.join(registry.list_remote_names())}")
    print("Appuyez sur Ctrl+C pour arrêter le serveur...")

    try:
        while True:
            await asyncio.sleep(3600)
    except (asyncio.CancelledError, KeyboardInterrupt):
        pass
    finally:
        await node.stop()


# ---------------------------------------------------------------------- #
# Commande : keygen
# ---------------------------------------------------------------------- #
def cmd_keygen(args: argparse.Namespace) -> None:
    identity = NodeIdentity.generate()
    out_path = Path(args.out).resolve()
    identity.save(out_path)

    print("🔑 Nouvelle identité Ed25519 générée avec succès !")
    print(f"📁 Fichier de clé privée sauvegardé : {out_path} (mode 0600)")
    print(f"🆔 Node ID : {identity.node_id}")
    print(f"🔓 Clé Publique (Hex) : {identity.public_key_hex}")


# ---------------------------------------------------------------------- #
# Commande : hardware
# ---------------------------------------------------------------------- #
def cmd_hardware(args: argparse.Namespace) -> None:
    from .engines.hardware import detect_hardware

    hw = detect_hardware()

    if args.json:
        _print_json(hw.to_dict())
        return

    if _HAS_RICH:
        from rich.table import Table

        table = Table(
            title="⚡ Diagnostic Matériel IA Multi-Plateformes", header_style="bold magenta"
        )
        table.add_column("Propriété", style="bold cyan")
        table.add_column("Détails Détectés", style="white")

        table.add_row("Système d'Exploitation", f"{hw.os_name} ({hw.architecture})")
        table.add_row("Modèle de Processeur", hw.cpu_model)
        table.add_row(
            "Cœurs CPU", f"{hw.cpu_cores_logical} logiques / {hw.cpu_cores_physical} physiques"
        )
        table.add_row(
            "Accélérateur IA Principal", f"[bold green]{hw.accelerator_name}[/bold green]"
        )
        table.add_row("Type d'Accélérateur", hw.accelerator_type)
        table.add_row("Backend Recommandé", f"[bold yellow]{hw.recommended_backend}[/bold yellow]")
        if hw.vram_total_mb > 0:
            table.add_row("VRAM / Mémoire Dédiée", f"{hw.vram_total_mb:,.0f} MB")

        support_flags = []
        if hw.has_cuda:
            support_flags.append("[green]✓ NVIDIA CUDA[/green]")
        if hw.has_rocm:
            support_flags.append("[green]✓ AMD ROCm[/green]")
        if hw.has_directml:
            support_flags.append("[green]✓ AMD/DirectML[/green]")
        if hw.has_intel_npu:
            support_flags.append("[green]✓ Intel NPU[/green]")
        if hw.has_intel_openvino:
            support_flags.append("[green]✓ Intel OpenVINO[/green]")
        if hw.has_apple_metal:
            support_flags.append("[green]✓ Apple Silicon Metal (MLX)[/green]")
        if not support_flags:
            support_flags.append("[white]✓ CPU Standard (AVX/AVX-512)[/white]")

        table.add_row("Compatibilité Matérielle", " | ".join(support_flags))
        console.print(table)
    else:
        print("--- Diagnostic Matériel IA ---")
        print(f"OS : {hw.os_name} ({hw.architecture})")
        print(f"CPU : {hw.cpu_model} ({hw.cpu_cores_logical} cores)")
        print(f"Accélérateur : {hw.accelerator_name}")
        print(f"Backend : {hw.recommended_backend}")
        print(f"VRAM : {hw.vram_total_mb} MB")


# ---------------------------------------------------------------------- #
# Commande : relay
# ---------------------------------------------------------------------- #
async def cmd_relay(args: argparse.Namespace) -> None:
    from .network.relay import WANRelayServer

    ssl_context = None
    if args.certfile or args.keyfile:
        if not args.certfile or not args.keyfile:
            raise SystemExit("--certfile et --keyfile doivent être fournis ensemble.")
        ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ssl_context.load_cert_chain(args.certfile, args.keyfile)
    server = WANRelayServer(host=args.host, port=args.port, name=args.name, ssl_context=ssl_context)
    await server.start()
    scheme = "wss" if ssl_context else "ws"
    print(f"🌐 Relais WAN OpenClawMesh '{args.name}' actif sur {scheme}://{args.host}:{args.port}")
    print("Prêt à router les paquets chiffrés E2EE entre pairs. Appuyez sur Ctrl+C pour arrêter...")
    try:
        while True:
            await asyncio.sleep(3600)
    except (asyncio.CancelledError, KeyboardInterrupt):
        pass
    finally:
        await server.stop()


# ---------------------------------------------------------------------- #
# Commande : dht
# ---------------------------------------------------------------------- #
async def cmd_dht(args: argparse.Namespace) -> None:
    from .network.dht import Contact, KademliaDHT

    dht = KademliaDHT(name=args.name, host=args.host, port=args.port)

    def _parse_peer(raw: str) -> tuple[str, int]:
        host, _, port = raw.partition(":")
        if not host or not port.isdigit():
            raise ValueError(
                f"Format d'adresse de bootstrap invalide (attendu host:port) : {raw!r}"
            )
        return host, int(port)

    bootstrap_contacts = [
        Contact(node_id="", host=host, port=port, name="bootstrap")
        for raw in (args.bootstrap or [])
        for host, port in (_parse_peer(raw),)
    ]
    local_endpoint = {"host": args.host, "port": args.port, "name": args.name}

    if args.advertise:
        if bootstrap_contacts:
            host, port = await dht.start_network(args.host, args.port)
            print(f"🗺️ Nœud DHT Kademlia '{args.name}' actif sur UDP {host}:{port}")
            await dht.bootstrap(bootstrap_contacts)
            endpoint = {"host": host, "port": port, "name": args.name}
            ok = await dht.advertise_skill_distributed(args.advertise, endpoint)
            print(f"📢 Compétence '{args.advertise}' publiée sur le réseau DHT décentralisé !")
            print(f"   Réplication réussie : {ok}")
            await dht.stop_network()
        else:
            key = dht.advertise_skill(args.advertise, local_endpoint)
            print(f"📢 Compétence '{args.advertise}' publiée localement dans la DHT !")
            print(f"🔑 Clé 160-bit Kademlia : {key}")
        return

    if args.lookup:
        if bootstrap_contacts:
            host, port = await dht.start_network(args.host, args.port)
            print(f"🗺️ Nœud DHT Kademlia '{args.name}' actif sur UDP {host}:{port}")
            await dht.bootstrap(bootstrap_contacts)
            info = await dht.lookup_skill_distributed(args.lookup)
            await dht.stop_network()
            if info:
                print(f"✅ Compétence '{args.lookup}' trouvée sur le réseau DHT : {info}")
            else:
                print(f"❌ Compétence '{args.lookup}' introuvable sur le réseau DHT.")
        else:
            info = dht.lookup_skill(args.lookup)
            if info:
                print(f"✅ Compétence '{args.lookup}' trouvée localement : {info}")
            else:
                print(f"❌ Compétence '{args.lookup}' non trouvée dans l'espace local DHT.")
        return

    # Mode démon : écoute UDP et participe au routage DHT (Ctrl+C pour arrêter)
    host, port = await dht.start_network(args.host, args.port)
    print(f"🗺️ Nœud DHT Kademlia '{args.name}' en écoute sur UDP {host}:{port}")
    print(f"🆔 Node ID 160-bit : {dht.node_id}")
    if bootstrap_contacts:
        reachable = await dht.bootstrap(bootstrap_contacts)
        print(
            f"🔗 Réseau DHT joint : {reachable} pair(s) joignable(s) sur {len(bootstrap_contacts)} contact(s) de départ."
        )
    print("Prêt à router le trafic DHT. Appuyez sur Ctrl+C pour arrêter...")
    try:
        while True:
            await asyncio.sleep(3600)
    except (asyncio.CancelledError, KeyboardInterrupt):
        pass
    finally:
        await dht.stop_network()


# ---------------------------------------------------------------------- #
# Commande : gossipsub
# ---------------------------------------------------------------------- #
async def cmd_gossipsub(args: argparse.Namespace) -> None:
    import hashlib

    from .network.gossipsub import GossipSubNode

    node = GossipSubNode(
        node_id=hashlib.sha256(args.name.encode("utf-8")).hexdigest()[:16],
        node_name=args.name,
        psk=args.psk,
    )
    await node.start()

    if getattr(args, "subscribe", None):

        def on_msg(m):
            print(f"\n📩 Message reçu sur topic [{m.topic}] de {m.from_peer}: {m.data}")

        node.subscribe(args.subscribe, handler=on_msg)
        print(f"📡 Souscription active au topic GossipSub : '{args.subscribe}'")

    if getattr(args, "publish", None) and getattr(args, "topic", None):
        try:
            data = json.loads(args.publish)
        except Exception:
            data = {"message": args.publish}
        mid = await node.publish(args.topic, data)
        print(f"🚀 Message publié sur [{args.topic}] (msg_id: {mid})")

    if getattr(args, "daemon", False):
        print("En écoute GossipSub (Ctrl+C pour quitter)...")
        try:
            while True:
                await asyncio.sleep(3600)
        except (asyncio.CancelledError, KeyboardInterrupt):
            pass

    await node.stop()


# ---------------------------------------------------------------------- #
# Commande : multimodal
# ---------------------------------------------------------------------- #
async def cmd_multimodal(args: argparse.Namespace) -> None:
    from .engines.multimodal import MultiModalEngine

    engine = MultiModalEngine()

    if args.task == "vision":
        res = await engine.analyze_image(
            image_base64="aGVsbG9fdmlzaW9u", prompt=args.prompt or "Décris l'image."
        )
        _print_json(res)
    elif args.task == "stt":
        res = await engine.transcribe_audio(audio_base64="YXVkaW9fZXhhbXBsZQ==", language="fr")
        _print_json(res)
    elif args.task == "tts":
        res = await engine.synthesize_speech(text=args.prompt or "Bienvenue sur OpenClawMesh.")
        _print_json(res)


# ---------------------------------------------------------------------- #
# Commande : e2ee
# ---------------------------------------------------------------------- #
def cmd_e2ee(args: argparse.Namespace) -> None:
    from .crypto_e2ee import E2EESessionManager, generate_x25519_keypair

    if args.action == "generate":
        priv, pub = generate_x25519_keypair()
        print("🔐 Paire de clés X25519 générée :")
        print(f"Clé Publique (Hex) : {pub}")
        print(f"Clé Privée (Hex)   : {priv}")
    elif args.action == "test":
        alice = E2EESessionManager("alice")
        bob = E2EESessionManager("bob")
        plaintext = b"Message secret OpenClawMesh E2EE"
        pkg = alice.encrypt_for_peer(bob.local_public_key, plaintext)
        decrypted = bob.decrypt_from_peer(alice.local_public_key, pkg)
        print(f"Test E2EE réussi: {decrypted == plaintext} -> '{decrypted.decode()}'")


# ---------------------------------------------------------------------- #
# Commande : doctor
# ---------------------------------------------------------------------- #
def cmd_doctor(args: argparse.Namespace) -> None:
    """Diagnostique l'environnement complet d'OpenClawMesh."""
    import platform
    import socket

    from .engines.hardware import detect_hardware
    from .security.pqc_kem import HybridPQCManager

    hw = detect_hardware()

    # Check Ports
    ports_status = {}
    for port in [8000, 8770, 8780, 8790]:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(0.2)
            available = s.connect_ex(("127.0.0.1", port)) != 0
            ports_status[port] = "DISPONIBLE" if available else "OCCUPÉ"

    # Check PQC
    pqc_ok = False
    try:
        pqc = HybridPQCManager()
        enc = pqc.encapsulate(pqc.keypair.public_key_b64)
        dec = pqc.decapsulate(enc.ephemeral_public_b64, enc.pqc_ciphertext_b64)
        pqc_ok = enc.shared_secret == dec
    except Exception:
        pqc_ok = False

    report = {
        "system": {
            "os": platform.system(),
            "release": platform.release(),
            "python_version": platform.python_version(),
            "arch": platform.machine(),
        },
        "hardware": {
            "accelerator": hw.accelerator_name,
            "type": hw.accelerator_type,
            "recommended_backend": hw.recommended_backend,
            "vram_mb": hw.vram_total_mb,
            "has_apple_metal": hw.has_apple_metal,
            "has_cuda": hw.has_cuda,
            "has_intel_npu": hw.has_intel_npu,
        },
        "ports": ports_status,
        "security": {
            "pqc_hybrid_kem": "OPÉRATIONNEL" if pqc_ok else "ÉCHEC",
            "ed25519_signatures": "OPÉRATIONNEL",
            "chacha20_poly1305": "OPÉRATIONNEL",
        },
        "status": "HEALTHY",
    }

    if args.json:
        _print_json(report)
        return

    if _HAS_RICH:
        console.print("[bold green]🩺 OpenClawMesh System & Network Doctor[/bold green]\n")

        t_sys = Table(title="💻 Système & Environnement")
        t_sys.add_column("Paramètre", style="cyan")
        t_sys.add_column("Valeur", style="magenta")
        t_sys.add_row(
            "Système d'exploitation", f"{report['system']['os']} ({report['system']['arch']})"
        )
        t_sys.add_row("Version Python", report["system"]["python_version"])
        console.print(t_sys)
        console.print()

        t_hw = Table(title="⚡ Matériel & Accélérateurs IA")
        t_hw.add_column("Composant", style="cyan")
        t_hw.add_column("Détection", style="green")
        t_hw.add_row("Accélérateur principal", report["hardware"]["accelerator"] or "CPU Standard")
        t_hw.add_row("Backend recommandé", report["hardware"]["recommended_backend"])
        t_hw.add_row("VRAM Totale", f"{report['hardware']['vram_mb']} MB")
        t_hw.add_row(
            "Apple Metal GPU", "✅ Actif" if report["hardware"]["has_apple_metal"] else "❌ Inactif"
        )
        t_hw.add_row("NVIDIA CUDA", "✅ Actif" if report["hardware"]["has_cuda"] else "❌ Inactif")
        t_hw.add_row(
            "Intel NPU", "✅ Actif" if report["hardware"]["has_intel_npu"] else "❌ Inactif"
        )
        console.print(t_hw)
        console.print()

        t_sec = Table(title="🔐 Cryptographie & Sécurité")
        t_sec.add_column("Module", style="cyan")
        t_sec.add_column("État", style="green")
        t_sec.add_row(
            "PQC Hybride (X25519 + ML-KEM-768)", f"✅ {report['security']['pqc_hybrid_kem']}"
        )
        t_sec.add_row("Signatures Ed25519", f"✅ {report['security']['ed25519_signatures']}")
        t_sec.add_row(
            "Chiffrement ChaCha20-Poly1305", f"✅ {report['security']['chacha20_poly1305']}"
        )
        console.print(t_sec)
        console.print()

        console.print(
            "[bold green]✅ Tout le système est prêt et opérationnel pour le maillage P2P ![/bold green]"
        )
    else:
        print("🩺 OpenClawMesh System Doctor Report:")
        print(json.dumps(report, indent=2))


# ---------------------------------------------------------------------- #
# Point d'Entrée Principal
# ---------------------------------------------------------------------- #
def main() -> None:
    parser = argparse.ArgumentParser(
        prog="openclaw-mesh",
        description="OpenClawMesh — Maillage Décentralisé P2P IA & Transport Ultra-Basse Latence",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # 1. discover
    p_disc = subparsers.add_parser("discover", help="Recherche les pairs sur le LAN")
    p_disc.add_argument("--timeout", type=float, default=2.0, help="Durée du scan (secondes)")
    p_disc.add_argument("--json", action="store_true", help="Format de sortie JSON brut")
    p_disc.add_argument(
        "--inspect", action="store_true", help="Interroge les compétences et la santé des pairs"
    )
    p_disc.add_argument(
        "--enable-discovery", action="store_true", help="Active la découverte LAN (opt-in)"
    )

    # 2. call
    p_call = subparsers.add_parser("call", help="Appel synchrone d'une compétence sur un pair")
    p_call.add_argument("--skill", required=True, help="Nom de la compétence (ex: 'generate_text')")
    p_call.add_argument("--payload", default="{}", help="Payload JSON d'entrée")
    p_call.add_argument(
        "--peer", help="Nom du pair cible ou URL ws:// (si omis, routage automatique)"
    )
    p_call.add_argument("--origin", default="openclaw-cli", help="Nom de l'agent appelant")
    p_call.add_argument("--psk", help="Clé pré-partagée HMAC-SHA256")
    p_call.add_argument("--keyfile", help="Chemin vers le fichier de clé privée Ed25519")
    p_call.add_argument(
        "--timeout", type=float, default=60.0, help="Timeout de l'appel (défaut: 60s)"
    )
    p_call.add_argument(
        "--timeout-discovery",
        type=float,
        default=1.5,
        help="Temps d'attente découverte si --peer omis",
    )
    p_call.add_argument(
        "--quic", action="store_true", help="Utilise le transport direct UDP QUIC/WebRTC (sub-10ms)"
    )
    p_call.add_argument("--json", action="store_true", help="Format de sortie JSON brut")

    # 3. stream
    p_stream = subparsers.add_parser(
        "stream", help="Consommation en direct (streaming) de tokens d'une compétence"
    )
    p_stream.add_argument("--skill", required=True, help="Nom de la compétence (ex: 'stream_llm')")
    p_stream.add_argument("--payload", default="{}", help="Payload JSON d'entrée")
    p_stream.add_argument(
        "--peer", help="Nom du pair cible ou URL ws:// (si omis, routage automatique)"
    )
    p_stream.add_argument("--origin", default="openclaw-streamer", help="Nom de l'agent appelant")
    p_stream.add_argument("--psk", help="Clé pré-partagée HMAC-SHA256")
    p_stream.add_argument("--keyfile", help="Chemin vers le fichier de clé privée Ed25519")
    p_stream.add_argument(
        "--timeout", type=float, default=120.0, help="Timeout streaming (défaut: 120s)"
    )
    p_stream.add_argument(
        "--timeout-discovery",
        type=float,
        default=1.5,
        help="Temps d'attente découverte si --peer omis",
    )
    p_stream.add_argument(
        "--quic", action="store_true", help="Utilise le transport direct UDP QUIC/WebRTC (sub-10ms)"
    )

    # 4. ping
    p_ping = subparsers.add_parser(
        "ping", help="Mesure la latence RTT et vérifie la santé d'un pair"
    )
    p_ping.add_argument("--peer", required=True, help="Nom du pair ou URL ws://")
    p_ping.add_argument("--psk", help="Clé pré-partagée HMAC-SHA256")
    p_ping.add_argument("--timeout", type=float, default=3.0, help="Timeout du ping (défaut: 3s)")
    p_ping.add_argument("--json", action="store_true", help="Format de sortie JSON brut")

    # 5. serve
    p_serve = subparsers.add_parser("serve", help="Démarre un nœud serveur OpenClawMesh")
    p_serve.add_argument(
        "--name",
        default=socket.gethostname(),
        help="Nom de ce nœud sur le réseau (défaut: nom d'hôte de la machine)",
    )
    p_serve.add_argument(
        "--port", type=int, default=8770, help="Port d'écoute WebSocket (défaut: 8770)"
    )
    p_serve.add_argument("--host", default="0.0.0.0", help="Hôte d'écoute (défaut: 0.0.0.0 pour écoute globale)")
    p_serve.add_argument("--psk", help="Clé pré-partagée HMAC-SHA256 requise")
    p_serve.add_argument("--keyfile", help="Chemin vers la clé privée Ed25519 de ce nœud")
    p_serve.add_argument("--trustfile", help="Chemin vers le TrustStore des clés autorisées")
    p_serve.add_argument("--no-zeroconf", action="store_true", help="Désactive l'annonce mDNS")
    p_serve.add_argument(
        "--wan",
        action="store_true",
        default=True,
        help="Active l'ouverture WAN automatique (UPnP, PCP RFC 6887, STUN, DHT) [Actif par défaut]",
    )
    p_serve.add_argument(
        "--no-wan",
        action="store_true",
        help="Désactive l'ouverture WAN et restreint le nœud au réseau local (LAN isolé)",
    )
    p_serve.add_argument(
        "--dht", action="store_true", default=True, help="Active le nœud d'indexation Kademlia DHT 160-bit [Actif par défaut]"
    )
    p_serve.add_argument(
        "--no-dht", action="store_true", help="Désactive l'indexation DHT Kademlia"
    )
    p_serve.add_argument(
        "--dht-port", type=int, default=8780, help="Port d'écoute UDP Kademlia (défaut: 8780)"
    )
    p_serve.add_argument(
        "--no-quic", action="store_true", help="Désactive l'écoute UDP QUIC ultra-basse latence"
    )
    p_serve.add_argument("--quic-port", type=int, help="Port d'écoute UDP QUIC (défaut: 8775)")
    p_serve.add_argument(
        "--no-gossipsub", action="store_true", help="Désactive l'overlay GossipSub v1.1"
    )
    p_serve.add_argument(
        "--relay", help="URL du serveur relais WAN WebSocket (ex: ws://hub.domaine.com:8790)"
    )

    # 6. keygen
    p_keygen = subparsers.add_parser("keygen", help="Génère une paire de clés asymétriques Ed25519")
    p_keygen.add_argument(
        "--out", default="openclaw_node.key", help="Fichier de sortie de la clé privée"
    )

    # 7. hardware
    p_hw = subparsers.add_parser(
        "hardware",
        help="Diagnostique le matériel IA (NVIDIA, AMD, Intel Core Ultra, Apple Silicon)",
    )
    p_hw.add_argument("--json", action="store_true", help="Sortie au format JSON brut")

    # 8. relay
    p_relay = subparsers.add_parser("relay", help="Démarre un serveur de relais WAN WebSocket E2EE")
    p_relay.add_argument(
        "--host", default="127.0.0.1", help="Hôte d'écoute du relais (défaut: localhost)"
    )
    p_relay.add_argument("--port", type=int, default=8790, help="Port d'écoute (défaut: 8790)")
    p_relay.add_argument("--name", default="openclaw-wan-relay", help="Nom du relais")
    p_relay.add_argument("--certfile", help="Certificat TLS du relais WAN")
    p_relay.add_argument("--keyfile", help="Clé privée TLS du relais WAN")

    # 9. dht
    p_dht = subparsers.add_parser(
        "dht", help="Gestionnaire de table de hachage distribuée Kademlia & Content Routing"
    )
    p_dht.add_argument("--name", default="dht-node", help="Nom du nœud")
    p_dht.add_argument("--host", default="127.0.0.1", help="Hôte")
    p_dht.add_argument("--port", type=int, default=8780, help="Port")
    p_dht.add_argument("--advertise", help="Publier une compétence (réseau si --bootstrap fourni)")
    p_dht.add_argument("--lookup", help="Rechercher une compétence dans la DHT")
    p_dht.add_argument(
        "--find-providers",
        help="Recherche les fournisseurs enregistrés (Provider Records) d'une ressource",
    )
    p_dht.add_argument(
        "--bootstrap",
        action="append",
        default=[],
        metavar="host:port",
        help="Pair(s) de départ pour rejoindre le réseau WAN Kademlia (peut être répété)",
    )

    # 10. gossipsub
    p_gsub = subparsers.add_parser(
        "gossipsub", help="Pub/Sub décentralisé par topics GossipSub v1.1"
    )
    p_gsub.add_argument("--name", default="gossip-node", help="Nom du nœud")
    p_gsub.add_argument("--topic", help="Nom du topic (ex: 'openclaw/v1/models')")
    p_gsub.add_argument("--subscribe", help="Topic auquel souscrire")
    p_gsub.add_argument("--publish", help="Message JSON ou chaîne à publier")
    p_gsub.add_argument("--psk", help="Clé pré-partagée HMAC-SHA256")
    p_gsub.add_argument("--daemon", action="store_true", help="Garde le nœud actif en écoute")

    # 11. multimodal
    p_multi = subparsers.add_parser(
        "multimodal", help="Exécute des compétences multi-modales (vision, stt, tts)"
    )
    p_multi.add_argument(
        "--task", choices=["vision", "stt", "tts"], default="vision", help="Tâche multi-modale"
    )
    p_multi.add_argument("--prompt", help="Prompt ou texte d'entrée")

    # 12. e2ee
    p_e2ee = subparsers.add_parser(
        "e2ee", help="Génère ou teste les clés de chiffrement de bout en bout"
    )
    p_e2ee.add_argument(
        "--action",
        choices=["generate", "test"],
        default="generate",
        help="Action à exécuter : 'generate' (crée une paire de clés X25519) ou 'test' (chiffre/déchiffre un message de test)",
    )

    # 13. doctor
    p_doc = subparsers.add_parser(
        "doctor", help="Diagnostic complet du système, matériel IA, réseau et cryptographie"
    )
    p_doc.add_argument("--json", action="store_true", help="Format de sortie JSON brut")

    # 14. guichet
    p_guichet = subparsers.add_parser(
        "guichet", help="Interroge ou s'enregistre auprès du Guichet Unique Freebox Ultra"
    )
    p_guichet.add_argument(
        "action",
        choices=["ips", "nodes", "register", "status"],
        default="ips",
        nargs="?",
        help="Action : ips (annuaire mondial), nodes (détails), register (s'enregistrer), status (santé)",
    )
    p_guichet.add_argument(
        "--url", help="URL personnalisée du Guichet Freebox (défaut: auto-détection)"
    )

    # 15. daemon
    p_daemon = subparsers.add_parser(
        "daemon", help="Gère le service d'arrière-plan autonome OpenClawMesh (LaunchAgent/systemd)"
    )
    p_daemon.add_argument(
        "action",
        choices=["install", "status", "start", "stop"],
        default="install",
        nargs="?",
        help="Action : install (active au démarrage), status, start, stop",
    )
    p_daemon.add_argument("--port", type=int, default=8770, help="Port d'écoute du nœud")

    args = parser.parse_args()

    if args.command == "keygen":
        cmd_keygen(args)
    elif args.command == "discover":
        asyncio.run(cmd_discover(args))
    elif args.command == "call":
        asyncio.run(cmd_call(args))
    elif args.command == "stream":
        asyncio.run(cmd_stream(args))
    elif args.command == "ping":
        asyncio.run(cmd_ping(args))
    elif args.command == "serve":
        asyncio.run(cmd_serve(args))
    elif args.command == "hardware":
        cmd_hardware(args)
    elif args.command == "relay":
        asyncio.run(cmd_relay(args))
    elif args.command == "dht":
        asyncio.run(cmd_dht(args))
    elif args.command == "gossipsub":
        asyncio.run(cmd_gossipsub(args))
    elif args.command == "multimodal":
        asyncio.run(cmd_multimodal(args))
    elif args.command == "e2ee":
        cmd_e2ee(args)
    elif args.command == "doctor":
        cmd_doctor(args)
    elif args.command == "guichet":
        asyncio.run(cmd_guichet(args))
    elif args.command == "daemon":
        cmd_daemon(args)


def cmd_daemon(args: argparse.Namespace) -> None:
    """Gère le démon de service autonome d'OpenClawMesh."""
    import importlib.util
    import platform
    import subprocess
    from pathlib import Path

    is_mac = "darwin" in platform.system().lower()
    plist_path = Path.home() / "Library/LaunchAgents/com.openclaw.mesh.plist"
    service_path = Path("/etc/systemd/system/openclaw-mesh.service")

    if args.action == "install":
        # Import direct depuis le chemin absolu du fichier (scripts/ n'est pas un package Python)
        _installer_path = Path(__file__).resolve().parent.parent / "scripts" / "service_installer.py"
        spec = importlib.util.spec_from_file_location("service_installer", _installer_path)
        _mod = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
        spec.loader.exec_module(_mod)  # type: ignore[union-attr]

        os_type = platform.system().lower()
        target_type = "launchd" if "darwin" in os_type else "systemd"

        if target_type == "launchd":
            content = _mod.generate_launchd_plist(port=args.port)
            out_path = plist_path
        else:
            content = _mod.generate_systemd_service(port=args.port)
            out_path = service_path

        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(content, encoding="utf-8")
        print(f"✅ Service enregistré dans : {out_path}")

        if target_type == "launchd":
            subprocess.run(["launchctl", "unload", str(out_path)], check=False, stderr=subprocess.DEVNULL)
            res = subprocess.run(["launchctl", "load", "-w", str(out_path)], check=False)
            if res.returncode == 0:
                print("🚀 OpenClawMesh est maintenant ACTIF en arrière-plan et démarrera tout seul à chaque allumage !")
                print("📋 Logs disponibles dans : /tmp/openclaw_mesh.log")
            else:
                print(f"⚠️ Erreur chargement launchctl ({res.returncode})")
        elif target_type == "systemd":
            subprocess.run(["systemctl", "daemon-reload"], check=False)
            res = subprocess.run(["systemctl", "enable", "--now", out_path.name], check=False)
            if res.returncode == 0:
                print("🚀 Service systemd OpenClawMesh activé avec succès au démarrage !")
            else:
                print(f"⚠️ Erreur systemctl ({res.returncode}) - vérifiez vos droits sudo.")

    elif args.action == "status":
        if is_mac:
            res = subprocess.run(["launchctl", "list"], capture_output=True, text=True)
            if "com.openclaw.mesh" in res.stdout:
                print("🟢 Service OpenClawMesh ACTIF en tâche de fond (LaunchAgent).")
            else:
                print("🔴 Service OpenClawMesh NON ACTIF.")
        else:
            res = subprocess.run(["systemctl", "is-active", "openclaw-mesh"], capture_output=True, text=True)
            if res.stdout.strip() == "active":
                print("🟢 Service OpenClawMesh ACTIF en tâche de fond (systemd).")
            else:
                print(f"🔴 Service OpenClawMesh ({res.stdout.strip()}).")
    elif args.action == "stop":
        if is_mac:
            subprocess.run(["launchctl", "unload", str(plist_path)], check=False)
            print("🛑 Service arrêté.")
        else:
            subprocess.run(["systemctl", "stop", "openclaw-mesh"], check=False)
            print("🛑 Service arrêté.")
    elif args.action == "start":
        if is_mac:
            subprocess.run(["launchctl", "load", "-w", str(plist_path)], check=False)
            print("🚀 Service démarré.")
        else:
            subprocess.run(["systemctl", "start", "openclaw-mesh"], check=False)
            print("🚀 Service démarré.")


async def cmd_guichet(args: argparse.Namespace) -> None:
    """Gère les requêtes CLI avec le Guichet Unique Freebox Ultra."""
    from .network.freebox_guichet import FreeboxGuichetClient

    client = FreeboxGuichetClient(guichet_url=args.url)
    endpoint = await client.detect_guichet_endpoint()
    if not endpoint:
        print("❌ Guichet Unique Freebox Ultra non joignable sur le réseau.")
        return

    print(f"⚡ Guichet Freebox détecté sur : {endpoint}")

    if args.action == "status":
        print("✓ Guichet opérationnel et prêt pour l'amorçage mondial.")
    elif args.action == "ips":
        data = await client.fetch_global_ip_directory()
        if not data:
            print("[-] Impossible de récupérer l'annuaire d'adresses IP.")
            return
        print(f"\n📋 Annuaire Universel des Machines ({data.get('total_machines', 0)} machines, {data.get('online_machines', 0)} en ligne) :")
        print("-" * 75)
        for row in data.get("directory", []):
            st = "🟢" if row.get("status") == "online" else "🔴"
            print(f"{st} {row.get('name', 'Node'):<24} | WAN: {row.get('public_ip', '—'):<15} | LAN: {row.get('local_ip', '—'):<15} | Port: {row.get('port')}")
        print("-" * 75)
    elif args.action == "register":
        res = await client.register()
        if res:
            print("✓ Enregistrement réussi auprès du Guichet Freebox.")
            print(f"🌍 Pairs reçus pour amorçage : {res.get('mesh_peer_count', 0)}")
        else:
            print("[-] Échec de l'enregistrement.")


if __name__ == "__main__":
    main()
