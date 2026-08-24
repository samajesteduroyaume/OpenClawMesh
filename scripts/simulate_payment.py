#!/usr/bin/env python3
"""
Simulateur de Webhook Stripe / Lemon Squeezy.
Permet de tester le déclenchement de l'émission de clés sans carte bancaire réelle.
Usage:
  python3 scripts/simulate_payment.py --email user@example.com --plan pro_monthly
"""
import argparse
import json
import sys
import urllib.request


def main():
    parser = argparse.ArgumentParser(description="Simulateur de Webhook de Paiement")
    parser.add_argument("--url", default="http://localhost:8000/api/webhooks/stripe", help="URL du Webhook")
    parser.add_argument("--email", default="selim@example.com", help="Email du client")
    parser.add_argument("--plan", default="pro_monthly", help="Nom du plan")
    parser.add_argument("--amount", type=int, default=1000, help="Montant en centimes (ex: 1000 = 10.00€)")
    args = parser.parse_args()

    # Payload simulant un événement Stripe checkout.session.completed
    mock_event = {
        "id": f"evt_sim_{int(urllib.request.time.time())}",
        "type": "checkout.session.completed",
        "data": {
            "object": {
                "customer_details": {
                    "email": args.email,
                    "name": "Selim Test",
                },
                "amount_total": args.amount,
                "currency": "eur",
                "payment_status": "paid",
                "subscription": f"sub_sim_{int(urllib.request.time.time())}",
                "customer": f"cus_sim_{int(urllib.request.time.time())}",
            }
        }
    }

    req_data = json.dumps(mock_event).encode("utf-8")
    req = urllib.request.Request(
        args.url,
        data=req_data,
        headers={"Content-Type": "application/json"},
    )

    print(f"📤 Envoi du webhook de test vers {args.url} pour {args.email} ({args.amount / 100}€)...")
    try:
        with urllib.request.urlopen(req) as resp:
            body = resp.read().decode("utf-8")
            print(f"📥 Réponse reçue ({resp.status}) :\n{body}")
    except Exception as e:
        print(f"❌ Erreur lors de l'envoi : {e}")


if __name__ == "__main__":
    main()
