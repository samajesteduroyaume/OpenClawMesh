"""
Exemple 4 : Création d'un nœud OpenClaw exposant un outil personnalisé au maillage.
"""

import asyncio
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from openclaw_mesh import OpenClawMeshNode, SkillRegistry, skill


# Définition de compétences personnalisées avec le décorateur @skill
@skill(
    name="calculator",
    description="Effectue des calculs mathématiques simples (add, sub, mul, div).",
)
def calculator(payload: dict) -> dict:
    op = payload.get("op", "add")
    a = float(payload.get("a", 0))
    b = float(payload.get("b", 0))

    if op == "add":
        res = a + b
    elif op == "sub":
        res = a - b
    elif op == "mul":
        res = a * b
    elif op == "div":
        if b == 0:
            raise ValueError("Division par zéro")
        res = a / b
    else:
        raise ValueError(f"Opération non supportée: {op}")

    return {"op": op, "a": a, "b": b, "result": res}


@skill(
    name="countdown_stream",
    description="Générateur streaming qui décompte de N à 0.",
)
async def countdown_stream(payload: dict):
    start = int(payload.get("start", 5))
    for i in range(start, -1, -1):
        yield {"count": i, "text": f"{i}... "}
        await asyncio.sleep(0.5)


async def main():
    registry = SkillRegistry(name="openclaw-calculator-node")
    registry.register(calculator)
    registry.register(countdown_stream)

    node = OpenClawMeshNode(
        name="openclaw-calc",
        port=8780,
        registry=registry,
    )

    print(
        "🚀 Démarrage du nœud OpenClaw avec les compétences 'calculator' et 'countdown_stream'..."
    )
    await node.start()
    print("🌐 Nœud publié sur mDNS. Appuyez sur Ctrl+C pour arrêter.")

    try:
        while True:
            await asyncio.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        await node.stop()


if __name__ == "__main__":
    asyncio.run(main())
