#!/usr/bin/env python3
"""
Gestionnaire et Nœud de Table de Hachage Distribuée (DHT) Kademlia OpenClawMesh.

Exemples :
  python3 scripts/mesh_dht.py --advertise llm
  python3 scripts/mesh_dht.py --lookup llm
"""
import argparse
import sys
from pathlib import Path

# Ajouter le répertoire racine au PYTHONPATH
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from openclaw_mesh.network.dht import KademliaDHT


def main():
    parser = argparse.ArgumentParser(description="Nœud DHT Kademlia OpenClawMesh")
    parser.add_argument("--name", default="dht-node", help="Nom du nœud")
    parser.add_argument("--host", default="127.0.0.1", help="Hôte d'écoute")
    parser.add_argument("--port", type=int, default=8780, help="Port d'écoute")
    parser.add_argument("--advertise", help="Publier une compétence dans la DHT (ex: --advertise llm)")
    parser.add_argument("--lookup", help="Rechercher une compétence dans la DHT (ex: --lookup llm)")
    args = parser.parse_args()

    dht = KademliaDHT(name=args.name, host=args.host, port=args.port)

    if args.advertise:
        key = dht.advertise_skill(args.advertise, {"host": args.host, "port": args.port, "name": args.name})
        print(f"📢 Compétence '{args.advertise}' publiée dans la DHT !")
        print(f"🔑 Clé 160-bit Kademlia : {key}")
    elif args.lookup:
        info = dht.lookup_skill(args.lookup)
        if info:
            print(f"✅ Compétence '{args.lookup}' trouvée : {info}")
        else:
            print(f"❌ Compétence '{args.lookup}' non trouvée dans l'espace local DHT.")
    else:
        print(f"🗺️ Nœud DHT Kademlia '{args.name}' actif.")
        print(f"🆔 Node ID 160-bit : {dht.node_id}")
        print(f"📍 Coordonnées : {args.host}:{args.port}")


if __name__ == "__main__":
    main()
