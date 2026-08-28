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
        await client.start()
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

    await node.start(enable_zeroconf=not args.no_zeroconf)
    print(f"🌐 Nœud OpenClawMesh '{args.name}' actif sur ws://{get_local_ip()}:{args.port}")
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
    from .crypto_e2ee import E2EESession

    session = E2EESession()
    print("🔐 Session E2EE Initialisée (X25519 & ChaCha20-Poly1305)")
    print(f"🔓 Clé Publique X25519 (Hex) : {session.public_key_hex}")


# ---------------------------------------------------------------------- #
# Parser CLI Principal
# ---------------------------------------------------------------------- #
def main() -> None:
    parser = argparse.ArgumentParser(
        prog="openclaw-mesh",
        description="OpenClawMesh — Protocole P2P & Skill Décentralisé pour Agents IA OpenClaw",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # 1. discover
    p_disc = subparsers.add_parser("discover", help="Scanne et liste les pairs du maillage LAN")
    p_disc.add_argument(
        "--timeout", type=float, default=2.0, help="Durée du scan en secondes (défaut: 2.0)"
    )
    p_disc.add_argument(
        "--inspect",
        action="store_true",
        help="Interroge chaque pair pour son catalogue complet et sa santé",
    )
    p_disc.add_argument(
        "--enable-discovery",
        action="store_true",
        help="Autorise explicitement le scan mDNS du réseau local",
    )
    p_disc.add_argument("--json", action="store_true", help="Format de sortie JSON brut")

    # 2. call
    p_call = subparsers.add_parser("call", help="Délègue et exécute une compétence sur le maillage")
    p_call.add_argument(
        "--skill", required=True, help="Nom de la compétence à exécuter (ex: llm, memory_search)"
    )
    p_call.add_argument(
        "--payload", default="{}", help='Payload JSON d\'entrée (ex: \'{"prompt": "Hello"}\')'
    )
    p_call.add_argument(
        "--peer", help="Nom du pair cible ou URL ws:// (si omis, routage automatique)"
    )
    p_call.add_argument("--origin", default="openclaw-agent", help="Nom de l'agent appelant")
    p_call.add_argument("--psk", help="Clé pré-partagée HMAC-SHA256")
    p_call.add_argument("--keyfile", help="Chemin vers le fichier de clé privée Ed25519")
    p_call.add_argument(
        "--timeout", type=float, default=60.0, help="Timeout d'exécution (défaut: 60s)"
    )
    p_call.add_argument(
        "--timeout-discovery",
        type=float,
        default=1.5,
        help="Temps d'attente découverte si --peer omis",
    )
    p_call.add_argument("--json", action="store_true", help="Format de sortie JSON complet")

    # 3. stream
    p_stream = subparsers.add_parser(
        "stream", help="Consomme une compétence en streaming continu (ex: LLM)"
    )
    p_stream.add_argument(
        "--skill", required=True, help="Nom de la compétence de streaming (ex: llm_stream, llm)"
    )
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
    p_serve.add_argument("--name", default="openclaw-node", help="Nom de ce nœud sur le réseau")
    p_serve.add_argument(
        "--port", type=int, default=8770, help="Port d'écoute WebSocket (défaut: 8770)"
    )
    p_serve.add_argument("--host", default="127.0.0.1", help="Hôte d'écoute (défaut: localhost)")
    p_serve.add_argument("--psk", help="Clé pré-partagée HMAC-SHA256 requise")
    p_serve.add_argument("--keyfile", help="Chemin vers la clé privée Ed25519 de ce nœud")
    p_serve.add_argument("--trustfile", help="Chemin vers le TrustStore des clés autorisées")
    p_serve.add_argument("--no-zeroconf", action="store_true", help="Désactive l'annonce mDNS")

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
        "dht", help="Gestionnaire de table de hachage distribuée Kademlia"
    )
    p_dht.add_argument("--name", default="dht-node", help="Nom du nœud")
    p_dht.add_argument("--host", default="127.0.0.1", help="Hôte")
    p_dht.add_argument("--port", type=int, default=8780, help="Port")
    p_dht.add_argument("--advertise", help="Publier une compétence (réseau si --bootstrap fourni)")
    p_dht.add_argument("--lookup", help="Rechercher une compétence dans la DHT")
    p_dht.add_argument(
        "--bootstrap",
        action="append",
        default=[],
        metavar="host:port",
        help="Pair(s) de départ pour rejoindre le réseau WAN Kademlia (peut être répété)",
    )

    # 10. multimodal
    p_multi = subparsers.add_parser(
        "multimodal", help="Exécute des compétences multi-modales (vision, stt, tts)"
    )
    p_multi.add_argument(
        "--task", choices=["vision", "stt", "tts"], default="vision", help="Tâche multi-modale"
    )
    p_multi.add_argument("--prompt", help="Prompt ou texte d'entrée")

    # 11. e2ee
    p_e2ee = subparsers.add_parser(
        "e2ee", help="Génère ou teste les clés de chiffrement de bout en bout"
    )
    p_e2ee.add_argument(
        "--action",
        choices=["generate", "test"],
        default="generate",
        help="Action à exécuter : 'generate' (crée une paire de clés X25519) ou 'test' (chiffre/déchiffre un message de test)",
    )

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
    elif args.command == "multimodal":
        asyncio.run(cmd_multimodal(args))
    elif args.command == "e2ee":
        cmd_e2ee(args)


if __name__ == "__main__":
    main()
