#!/usr/bin/env python3
"""
Script de délégation et d'appel de compétence pour l'agent OpenClaw.
Usage:
  python3 scripts/mesh_call.py <skill> '<payload_json>' [peer_name_or_url]
"""

import asyncio
import json
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from openclaw_mesh.client import MeshClient


async def run(skill: str, payload_str: str, peer: str = "") -> None:
    try:
        payload = json.loads(payload_str) if payload_str else {}
    except Exception as e:
        print(json.dumps({"ok": False, "error": f"JSON payload invalide: {e}"}))
        sys.exit(1)

    client = MeshClient(name="openclaw-task-runner")
    if not peer:
        await client.start()
        await asyncio.sleep(1.5)
        resp = await client.delegate(skill, payload)
    else:
        resp = await client.call(peer, skill, payload)

    await client.stop()
    print(resp.to_json())


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 scripts/mesh_call.py <skill> '<payload_json>' [peer]")
        sys.exit(1)

    skill_name = sys.argv[1]
    payload_raw = sys.argv[2] if len(sys.argv) > 2 else "{}"
    peer_name = sys.argv[3] if len(sys.argv) > 3 else ""

    asyncio.run(run(skill_name, payload_raw, peer_name))
