#!/usr/bin/env python3
"""
Lanceur de la Passerelle Universelle & Portail OpenClawMesh (100% Free & Open-Access).
Usage:
    python3 scripts/gateway_server.py [--port 8000] [--host 127.0.0.1]
"""

import argparse
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import uvicorn


def main():
    parser = argparse.ArgumentParser(
        description="Passerelle Universelle & Portail OpenClawMesh (100% Free & Open-Access)"
    )
    parser.add_argument("--host", default="127.0.0.1", help="Hôte d'écoute (défaut: localhost)")
    parser.add_argument("--port", type=int, default=8000, help="Port d'écoute HTTP (défaut: 8000)")
    parser.add_argument("--reload", action="store_true", help="Rechargement à chaud automatique")
    args = parser.parse_args()

    print(f"\n🚀 Démarrage de la Passerelle OpenClawMesh sur http://{args.host}:{args.port}")
    print(f"🌐 Portail & Command Center : http://{args.host}:{args.port}/portal")
    print(f"🔑 Génération Clé Locale : http://{args.host}:{args.port}/api/v1/checkout/free-key")
    print(f"⚡ Endpoints OpenAI : http://{args.host}:{args.port}/v1/chat/completions")
    print(f"🛡️  Endpoint Exécution : http://{args.host}:{args.port}/api/v1/execute")
    print("🔒 [Avis de Sécurité] Écoute locale par défaut (127.0.0.1). L'accès aux outils, mémoire et calcul")
    print("   exige le consentement explicite de l'opérateur. L'exposition WAN requiert TLS et authentification.\n")

    uvicorn.run(
        "openclaw_mesh.gateway.server:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
    )


if __name__ == "__main__":
    main()
