"""
Exemple 1 : Découverte automatique des pairs JarvisMesh & OpenClawMesh sur le LAN.
"""

import asyncio
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from openclaw_mesh import MeshClient


async def main():
    print("⚠️ Ce script sonde le LAN et interroge les pairs détectés.")
    answer = input("Continuer ? [y/N] ").strip().lower()
    if answer not in {"y", "yes", "o", "oui"}:
        print("Scan annulé.")
        return
    print("🔍 Démarrage du client et écoute mDNS (2 secondes)...")
    client = MeshClient(name="openclaw-discoverer", enable_discovery=True)
    await client.start()
    await asyncio.sleep(2.0)

    peers = client.list_peers()
    print(f"\n🌐 {len(peers)} pair(s) détecté(s) sur le réseau local :")

    for name, peer in peers.items():
        print(f"\n🔹 Nœud : {name}")
        print(f"   ├─ Adresse : {peer.ws_url}")
        print(f"   ├─ Type : {peer.service_type}")

        # Introspection
        desc = await client.discover_skills(name, timeout=1.5)
        health = await client.check_health(name, timeout=1.5)

        skills = desc.get("skills", peer.skills)
        print(f"   ├─ Compétences ({len(skills)}) : {', '.join(skills)}")
        print(
            f"   └─ RTT : {health.get('rtt_ms', '-')} ms | Tâches actives : {health.get('active_tasks', 0)}"
        )

    await client.stop()


if __name__ == "__main__":
    asyncio.run(main())
