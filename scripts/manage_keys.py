#!/usr/bin/env python3
"""
Outil CLI d'Administration des Clés d'API OpenClawMesh.
Usage:
  python3 scripts/manage_keys.py list
  python3 scripts/manage_keys.py create --email user@example.com --plan pro_monthly --days 30
  python3 scripts/manage_keys.py revoke --key sk_claw_...
  python3 scripts/manage_keys.py info --key sk_claw_...
"""
import argparse
import json
import sys
import time
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from openclaw_mesh.gateway.db import KeyDatabase

try:
    from rich.console import Console
    from rich.table import Table
    _HAS_RICH = True
    console = Console()
except ImportError:
    _HAS_RICH = False
    console = None


def main():
    parser = argparse.ArgumentParser(description="Gestionnaire de Clés OpenClawMesh")
    subparsers = parser.add_subparsers(dest="action", required=True)

    # 1. list
    p_list = subparsers.add_parser("list", help="Lister les clés existantes")
    p_list.add_argument("--limit", type=int, default=50)
    p_list.add_argument("--json", action="store_true")

    # 2. create
    p_create = subparsers.add_parser("create", help="Créer manuellement une nouvelle clé")
    p_create.add_argument("--email", required=True, help="Email de l'utilisateur")
    p_create.add_argument("--plan", default="pro_monthly", help="Nom du plan (ex: pro_monthly, developer_yearly, lifetime)")
    p_create.add_argument("--days", type=int, default=30, help="Durée de validité en jours (0 = illimité)")
    p_create.add_argument("--quota", type=int, default=-1, help="Quota max de requêtes (-1 = illimité)")

    # 3. revoke
    p_revoke = subparsers.add_parser("revoke", help="Révoquer une clé")
    p_revoke.add_argument("--key", required=True, help="Clé sk_claw_...")

    # 4. info
    p_info = subparsers.add_parser("info", help="Afficher les détails d'une clé")
    p_info.add_argument("--key", required=True, help="Clé sk_claw_...")

    args = parser.parse_args()
    db = KeyDatabase()

    if args.action == "list":
        keys = db.list_all_keys(limit=args.limit)
        if args.json or not _HAS_RICH:
            print(json.dumps([k.to_dict() for k in keys], indent=2))
        else:
            table = Table(title="🔑 Clés d'API Enregistrées", header_style="bold cyan")
            table.add_column("Clé d'API", style="green")
            table.add_column("Email", style="white")
            table.add_column("Plan", style="yellow")
            table.add_column("Statut", style="bold")
            table.add_column("Quota Utilisé", style="magenta")
            table.add_column("Expire dans", style="cyan")

            for k in keys:
                valid, _ = k.is_valid()
                status_str = "[green]Active[/green]" if valid else "[red]Inactive[/red]"
                quota_str = f"{k.quota_used} / {k.quota_limit if k.quota_limit != -1 else '∞'}"
                expires_str = f"{round((k.expires_at - time.time())/86400, 1)}j" if k.expires_at else "Jamais"
                table.add_row(k.key, k.email, k.plan, status_str, quota_str, expires_str)

            console.print(table)

    elif args.action == "create":
        key_rec = db.create_key(
            email=args.email,
            plan=args.plan,
            days_valid=args.days,
            quota_limit=args.quota,
        )
        print(f"\n✅ Clé créée avec succès !")
        print(f"🔑 Clé : {key_rec.key}")
        print(f"📧 Email : {key_rec.email}")
        print(f"📦 Plan : {key_rec.plan}")
        print(f"📅 Expiration : {time.ctime(key_rec.expires_at) if key_rec.expires_at else 'Illimitée'}\n")

    elif args.action == "revoke":
        ok = db.revoke_key(args.key)
        if ok:
            print(f"🚫 Clé '{args.key}' révoquée avec succès.")
        else:
            print(f"❌ Clé non trouvée.")

    elif args.action == "info":
        key_rec = db.get_key(args.key)
        if not key_rec:
            print(f"❌ Clé non trouvée.")
            sys.exit(1)
        valid, reason = key_rec.is_valid()
        print(json.dumps(key_rec.to_dict(), indent=2))
        print(f"\nStatut actuel : {'VALIDE' if valid else 'INVALIDE (' + reason + ')'}")


if __name__ == "__main__":
    main()
