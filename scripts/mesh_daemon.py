#!/usr/bin/env python3
"""
Démon de Nœud P2P OpenClawMesh d'arrière-plan.
Permet à OpenClaw de rester joignable sur le maillage et d'exposer ses outils.
Usage:
  python3 scripts/mesh_daemon.py [--name openclaw-mac] [--port 8770]
"""
import argparse
import asyncio
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from openclaw_mesh.node import OpenClawMeshNode
from openclaw_mesh.bridge import SkillRegistry, skill
from openclaw_mesh.crypto import NodeIdentity, TrustStore


def create_default_node(name: str, port: int, keyfile: str = "", trustfile: str = "") -> OpenClawMeshNode:
    registry = SkillRegistry(name=name)

    # Exemple de compétence additionnelle
    @skill(name="claw_status", description="Retourne l'état opérationnel et l'agent OpenClaw actif.")
    def claw_status(payload: dict) -> dict:
        return {
            "status": "ready",
            "agent": name,
            "skills_loaded": registry.list_names(),
        }

    registry.register(claw_status)

    identity = NodeIdentity.load(keyfile) if keyfile else None
    trust_store = TrustStore.load(trustfile) if trustfile else None

    return OpenClawMeshNode(
        name=name,
        port=port,
        registry=registry,
        identity=identity,
        trust_store=trust_store,
    )


async def main_async() -> None:
    parser = argparse.ArgumentParser(description="Démon de nœud OpenClawMesh")
    parser.add_argument("--name", default="openclaw-mac", help="Nom du nœud sur le réseau")
    parser.add_argument("--port", type=int, default=8770, help="Port d'écoute (défaut: 8770)")
    parser.add_argument("--keyfile", help="Clé privée Ed25519")
    parser.add_argument("--trustfile", help="TrustStore")
    args = parser.parse_args()

    node = create_default_node(args.name, args.port, args.keyfile, args.trustfile)
    await node.start()
    print(f"🚀 Démon OpenClawMesh '{args.name}' actif sur le port {args.port}")

    try:
        while True:
            await asyncio.sleep(3600)
    except (asyncio.CancelledError, KeyboardInterrupt):
        pass
    finally:
        await node.stop()


if __name__ == "__main__":
    asyncio.run(main_async())
