# 💳 Guide Complet de Monétisation OpenClawMesh (Stripe / Revolut)

Ce guide vous explique pas à pas comment monétiser vos compétences IA OpenClaw/JarvisMesh en recevant les paiements par carte bancaire directement sur votre compte **Revolut**.

---

## 🏛️ Vue d'Ensemble du Flux de Paiement

```mermaid
graph TD
    Client["👤 Client OpenClaw"]
    Stripe["💳 Stripe Checkout (CB / Apple Pay)"]
    Revolut["🏦 Votre Compte Revolut (IBAN)"]
    Gateway["🛡️ OpenClawMesh Gateway Server (`/gateway`)"]
    DB["💾 Base SQLite (`openclaw_keys.db`)"]
    Skill["🤖 Skill OpenClaw (`SKILL.md`)"]

    Client -->|1. Achète un abonnement (ex: 10€/mois)| Stripe
    Stripe -->|2. Virement automatique des gains| Revolut
    Stripe -->|3. Webhook instantané| Gateway
    Gateway -->|4. Émet la clé `sk_claw_...`| DB
    Gateway -->|5. Affiche la clé au client| Client
    Client -->|6. Configure `export OPENCLAW_API_KEY`| Skill
    Skill -->|7. Requête premium authentifiée| Gateway
```

---

## 📋 Étape 1 : Configurer votre compte Revolut dans Stripe

1. Créez ou connectez-vous à votre compte **Stripe** ([stripe.com](https://stripe.com)).
2. Allez dans **Paramètres (Settings)** ➔ **Comptes bancaires et planification des virements (Bank accounts and scheduling)**.
3. Renseignez l'**IBAN de votre compte Revolut** (Format `FR...` ou `LT...` disponible dans l'application Revolut sous *Détails du compte*).
4. Choisissez la fréquence des virements (quotidienne ou hebdomadaire). L'argent de vos ventes arrivera automatiquement sur votre solde Revolut.

---

## ⚙️ Étape 2 : Configurer le Webhook Stripe

Dans votre dashboard Stripe :
1. Allez dans **Développeurs (Developers)** ➔ **Webhooks**.
2. Cliquez sur **Ajouter un endpoint (Add destination)**.
3. **URL de l'endpoint** : `https://votre-domaine.com/api/webhooks/stripe` (ou votre URL ngrok/tunnel en local).
4. **Événements à écouter** :
   - `checkout.session.completed` (création de clé immédiate après paiement).
   - `invoice.payment_succeeded` (renouvellement mensuel automatique).
   - `customer.subscription.deleted` (résiliation d'abonnement).
5. Copiez la clé secrète de signature du webhook (`whsec_...`) et définissez la variable d'environnement :
   ```bash
   export STRIPE_WEBHOOK_SECRET="whsec_..."
   ```

---

## 🚀 Étape 3 : Démarrer la Passerelle de Monétisation

Sur votre serveur ou machine hôte :
```bash
cd /Users/selim/Desktop/OpenClawMesh
python3 scripts/gateway_server.py --port 8000
```

Vous disposez immédiatement de :
- 🌐 **Portail Client & Dashboard d'Achat** : `http://localhost:8000/portal`
- 🧪 **Playground Interactif de Test** : test en direct des requêtes avec clé.
- ⚡ **Endpoint Webhook Stripe** : `http://localhost:8000/api/webhooks/stripe`
- 🛡️ **Endpoint Sécurisé Exécution Skill** : `http://localhost:8000/api/v1/execute`

---

## 🛠️ Étape 4 : Gestion des Clés d'API en Ligne de Commande (CLI)

Vous pouvez à tout moment inspecter, créer ou révoquer des clés manuellement via le script admin :

```bash
# 1. Lister toutes les clés existantes et leur consommation
python3 scripts/manage_keys.py list

# 2. Créer une clé personnalisée (ex: pour un partenaire ou testeur)
python3 scripts/manage_keys.py create --email client@vip.com --plan pro_monthly --days 60

# 3. Révoquer une clé en cas d'abus ou impayé
python3 scripts/manage_keys.py revoke --key sk_claw_abc123...

# 4. Afficher les détails et quotas d'une clé
python3 scripts/manage_keys.py info --key sk_claw_abc123...
```

---

## 🧪 Étape 5 : Simuler un Paiement sans Carte Bancaire Réelle

Pendant le développement ou pour valider votre installation, vous pouvez simuler un paiement Stripe instantané :

```bash
# 1. Simuler l'abonnement Pro Mensuel (10€)
python3 scripts/simulate_payment.py --email selim@test.com --plan pro_monthly --amount 1000

# 2. Simuler l'achat de la Licence à Vie (200€)
python3 scripts/simulate_payment.py --email vip@test.com --plan lifetime --amount 20000
```
Le serveur émettra instantanément une nouvelle clé `sk_claw_...` active, sans date d'expiration pour la licence à vie.

---

## 📦 Étape 6 : Distribution du `SKILL.md`

Dans le `SKILL.md` que vous distribuez à la communauté OpenClaw, indiquez simplement :

```markdown
---
name: my-premium-skill
description: Compétence IA avec données et modèles en temps réel.
version: 1.0.0
metadata:
  openclaw:
    requires:
      env:
        - OPENCLAW_API_KEY
      bins:
        - python3
---

# My Premium Skill

Pour utiliser cette compétence :
1. Obtenez votre clé d'accès sur **https://votre-domaine.com/portal**
2. Configurez votre variable d'environnement :
   ```bash
   export OPENCLAW_API_KEY="sk_claw_..."
   ```
```
