"""
Exemple 2 : Délégation d'inférence LLM locale avec streaming token-par-token.
"""
import asyncio
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from openclaw_mesh import MeshClient


async def main():
    client = MeshClient(name="openclaw-llm-caller")
    await client.start()
    print("⌛ Recherche d'un nœud d'inférence LLM sur le maillage...")
    await asyncio.sleep(1.5)

    prompt = "Explique en 2 phrases simples le principe du maillage P2P d'agents IA."
    print(f"\n💬 Prompt envoyé : \"{prompt}\"\n")
    print("🤖 Réponse en streaming direct :")

    def on_token(chunk):
        token = chunk.get("text", "") if isinstance(chunk, dict) else str(chunk)
        sys.stdout.write(token)
        sys.stdout.flush()

    resp = await client.delegate(
        skill="llm_stream",
        payload={"prompt": prompt, "temperature": 0.3},
        on_chunk=on_token,
    )

    print("\n")
    if resp.ok:
        print(f"✅ Traité par le nœud : {resp.handled_by}")
    else:
        print(f"❌ Erreur : {resp.error}")

    await client.stop()


if __name__ == "__main__":
    asyncio.run(main())
