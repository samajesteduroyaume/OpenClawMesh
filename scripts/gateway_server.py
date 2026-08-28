#!/usr/bin/env python3
"""
Lanceur du Serveur Passerelle de Monétisation OpenClawMesh.
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
    parser = argparse.ArgumentParser(description="Serveur de Monétisation OpenClawMesh")
    parser.add_argument("--host", default="127.0.0.1", help="Hôte d'écoute (défaut: localhost)")
    parser.add_argument("--port", type=int, default=8000, help="Port d'écoute HTTP (défaut: 8000)")
    parser.add_argument("--reload", action="store_true", help="Rechargement à chaud automatique")
    args = parser.parse_args()

    print(f"\n🚀 Démarrage de la Passerelle OpenClawMesh sur http://{args.host}:{args.port}")
    print(f"🌐 Portail Client : http://localhost:{args.port}/portal")
    print(f"💳 Webhook Stripe : http://localhost:{args.port}/api/webhooks/stripe")
    print(f"🍋 Webhook Lemon Squeezy : http://localhost:{args.port}/api/webhooks/lemonsqueezy")
    print(f"🛡️  Endpoint Exécution : http://localhost:{args.port}/api/v1/execute\n")

    uvicorn.run(
        "openclaw_mesh.gateway.server:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
    )


if __name__ == "__main__":
    main()
