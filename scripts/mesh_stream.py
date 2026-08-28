#!/usr/bin/env python3
"""
Script de consommation streaming (token-par-token) pour l'agent OpenClaw.
Usage:
  python3 scripts/mesh_stream.py <skill> '<payload_json>' [peer_name_or_url]
"""

import asyncio
import json
import sys
from pathlib import Path
from typing import Any

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from openclaw_mesh.client import MeshClient


async def run(skill: str, payload_str: str, peer: str = "") -> None:
    try:
        payload = json.loads(payload_str) if payload_str else {}
    except Exception as e:
        sys.stderr.write(f"JSON payload invalide: {e}\n")
        sys.exit(1)

    client = MeshClient(name="openclaw-stream-runner")

    def on_chunk(chunk_val: Any) -> None:
        if isinstance(chunk_val, dict) and "text" in chunk_val:
            sys.stdout.write(chunk_val["text"])
        elif isinstance(chunk_val, str):
            sys.stdout.write(chunk_val)
        else:
            sys.stdout.write(str(chunk_val))
        sys.stdout.flush()

    if not peer:
        await client.start()
        await asyncio.sleep(1.5)
        resp = await client.delegate(skill, payload, on_chunk=on_chunk)
    else:
        resp = await client.call_stream(peer, skill, payload, on_chunk=on_chunk)

    await client.stop()
    sys.stdout.write("\n")
    sys.stdout.flush()

    if not resp.ok:
        sys.stderr.write(f"Erreur streaming: {resp.error}\n")
        sys.exit(1)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 scripts/mesh_stream.py <skill> '<payload_json>' [peer]")
        sys.exit(1)

    skill_name = sys.argv[1]
    payload_raw = sys.argv[2] if len(sys.argv) > 2 else "{}"
    peer_name = sys.argv[3] if len(sys.argv) > 3 else ""

    asyncio.run(run(skill_name, payload_raw, peer_name))
