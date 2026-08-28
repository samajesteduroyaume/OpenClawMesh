#!/usr/bin/env python3
"""
Script de découverte rapide pour l'agent OpenClaw.
Affiche les pairs actifs sous format JSON structuré.
"""

import asyncio
import json
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from openclaw_mesh.client import MeshClient


async def run(timeout: float = 2.0, inspect: bool = True) -> None:
    client = MeshClient(name="openclaw-discover-agent")
    await client.start()
    await asyncio.sleep(timeout)
    peers = client.list_peers()

    results = {}
    for pname, pinfo in peers.items():
        data = pinfo.to_dict()
        if inspect:
            try:
                desc = await client.discover_skills(pname, timeout=1.5)
                health = await client.check_health(pname, timeout=1.5)
                if "skills" in desc:
                    data["skills"] = desc["skills"]
                data["health"] = health
                data["rtt_ms"] = health.get("rtt_ms")
            except Exception:
                pass
        results[pname] = data

    await client.stop()
    print(json.dumps(results, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    t = float(sys.argv[1]) if len(sys.argv) > 1 else 2.0
    asyncio.run(run(timeout=t))
