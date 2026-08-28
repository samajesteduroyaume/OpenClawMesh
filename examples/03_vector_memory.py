"""
Exemple 3 : Interaction avec la mémoire vectorielle persistante (SQLite Vector Store).
"""

import asyncio
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from openclaw_mesh import MeshClient


async def main():
    client = MeshClient(name="openclaw-memory-caller")
    await client.start()
    print("⌛ Recherche d'un nœud de mémoire vectorielle sur le réseau...")
    await asyncio.sleep(1.5)

    # 1. Stocker des documents
    doc = {
        "content": "OpenClaw utilise le protocole P2P JarvisMesh pour communiquer en direct entre agents.",
        "doc_id": "openclaw_spec_001",
        "metadata": {"category": "architecture", "author": "openclaw"},
    }
    print(f"\n💾 Stockage du document : '{doc['doc_id']}'...")
    store_resp = await client.delegate("memory_store", doc)
    print("Résultat stockage :", store_resp.to_dict())

    # 2. Recherche sémantique
    query = {"query": "protocole p2p décentralisé", "top_k": 2}
    print(f"\n🔍 Recherche sémantique : '{query['query']}'...")
    search_resp = await client.delegate("memory_search", query)
    print("Résultat recherche :", search_resp.to_dict())

    await client.stop()


if __name__ == "__main__":
    asyncio.run(main())
