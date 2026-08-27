#!/usr/bin/env python3
"""
Gestionnaire et Nœud de Table de Hachage Distribuée (DHT) Kademlia OpenClawMesh.

Fonctionne en mode local (stockage/lookup en mémoire) ou en mode réseau réel
(transport UDP, bootstrap Kademlia, recherche itérative distribuée).

Exemples :
  # Nœud en écoute UDP (démon réseau réel, jusqu'à Ctrl+C)
    python3 scripts/mesh_dht.py --host 127.0.0.1 --port 8780

  # Publier/lire localement (mémoire)
  python3 scripts/mesh_dht.py --advertise llm
  python3 scripts/mesh_dht.py --lookup llm

  # Publier/lire sur le réseau décentralisé (bootstrape sur un pair connu)
  python3 scripts/mesh_dht.py --advertise llm --bootstrap 192.0.2.5:8780
  python3 scripts/mesh_dht.py --lookup llm --bootstrap 192.0.2.5:8780
"""

import argparse
import asyncio
import sys
from pathlib import Path

# Ajouter le répertoire racine au PYTHONPATH
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from openclaw_mesh.network.dht import Contact, KademliaDHT


def _parse_bootstrap(raw: str) -> tuple[str, int]:
    host, _, port = raw.partition(":")
    if not host or not port.isdigit():
        raise ValueError(f"Format d'adresse de bootstrap invalide (attendu host:port) : {raw!r}")
    return host, int(port)


def _bootstrap_contacts(raw_list: list[str]) -> list[Contact]:
    contacts: list[Contact] = []
    for raw in raw_list:
        host, port = _parse_bootstrap(raw)
        # L'ID du pair est inconnu au préalable : le pong renvoie le vrai node_id.
        contacts.append(Contact(node_id="", host=host, port=port, name="bootstrap"))
    return contacts


async def _run(args: argparse.Namespace) -> None:
    dht = KademliaDHT(name=args.name, host=args.host, port=args.port)
    bootstrap_contacts = _bootstrap_contacts(args.bootstrap or [])
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


def main():
    parser = argparse.ArgumentParser(description="Nœud DHT Kademlia OpenClawMesh (LAN/WAN)")
    parser.add_argument("--name", default="dht-node", help="Nom du nœud")
    parser.add_argument("--host", default="127.0.0.1", help="Hôte d'écoute UDP (défaut: localhost)")
    parser.add_argument("--port", type=int, default=8780, help="Port d'écoute UDP")
    parser.add_argument("--advertise", help="Publier une compétence (réseau si --bootstrap)")
    parser.add_argument("--lookup", help="Rechercher une compétence dans la DHT")
    parser.add_argument(
        "--bootstrap",
        action="append",
        default=[],
        metavar="host:port",
        help="Pair(s) de départ pour rejoindre le réseau WAN Kademlia (peut être répété)",
    )
    args = parser.parse_args()
    asyncio.run(_run(args))


if __name__ == "__main__":
    main()
