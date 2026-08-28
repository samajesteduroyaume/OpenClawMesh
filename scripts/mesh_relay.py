#!/usr/bin/env python3
"""
Point d'Entrée Direct pour Lancer un Relais WAN WebSocket E2EE OpenClawMesh.

Exemple :
  python3 scripts/mesh_relay.py --port 8790 --name wan-relay-paris
"""

import argparse
import asyncio
import sys
from pathlib import Path

# Ajouter le répertoire racine au PYTHONPATH
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from openclaw_mesh.network.relay import WANRelayServer


async def main():
    parser = argparse.ArgumentParser(description="Serveur de Relais WAN OpenClawMesh")
    parser.add_argument("--host", default="127.0.0.1", help="Hôte d'écoute (défaut: localhost)")
    parser.add_argument("--port", type=int, default=8790, help="Port d'écoute (défaut: 8790)")
    parser.add_argument("--name", default="openclaw-wan-relay", help="Nom du relais")
    args = parser.parse_args()

    server = WANRelayServer(host=args.host, port=args.port, name=args.name)
    await server.start()
    print(f"🌐 Relais WAN OpenClawMesh '{args.name}' actif sur ws://{args.host}:{args.port}")
    print("Prêt à router les paquets chiffrés E2EE entre pairs. Appuyez sur Ctrl+C pour arrêter...")

    try:
        while True:
            await asyncio.sleep(3600)
    except (asyncio.CancelledError, KeyboardInterrupt):
        pass
    finally:
        await server.stop()


if __name__ == "__main__":
    asyncio.run(main())
