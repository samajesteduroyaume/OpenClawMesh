"""
Portail Web Client & Playground Interactif pour OpenClawMesh Gateway.

Interface dark mode, responsive, avec paiement Bitcoin natif :
- Présentation des offres & plans tarifaires
- Adresse BTC + QR code + formulaire de soumission de paiement
- Suivi du statut de paiement par payment_id
- Playground de test de compétences en temps réel
"""

from __future__ import annotations

import base64
from io import BytesIO

import qrcode
from qrcode.image.svg import SvgPathImage


def _bitcoin_qr_data_uri(address: str) -> str:
    """Génère le QR Bitcoin localement afin de ne transmettre aucune donnée à un tiers."""
    qr = qrcode.QRCode(version=None, box_size=4, border=2)
    qr.add_data(f"bitcoin:{address}")
    qr.make(fit=True)
    image = qr.make_image(image_factory=SvgPathImage)
    buffer = BytesIO()
    image.save(buffer)
    encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
    return f"data:image/svg+xml;base64,{encoded}"


def render_portal_html(
    portal_title: str = "OpenClawMesh — API Store & Gateway",
    btc_address: str = "bc1qwq8sll9vrl83lclyhha2gyncpd5275cdr2wul5",
) -> str:
    btc_qr_data_uri = _bitcoin_qr_data_uri(btc_address)
    return f"""<!DOCTYPE html>
<html lang="fr">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <meta http-equiv="Content-Security-Policy" content="default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; script-src 'self' 'unsafe-inline'; connect-src 'self';">
    <title>{portal_title}</title>
    <meta name="description" content="Accédez à l'inférence IA décentralisée OpenClawMesh par paiement Bitcoin — pas de compte, pas de tracking.">
    <style>
        :root {{
            --bg: #080c14;
            --card-bg: rgba(18, 24, 40, 0.75);
            --card-border: rgba(255, 255, 255, 0.07);
            --primary: #f7931a;
            --primary-gradient: linear-gradient(135deg, #f7931a 0%, #fbbf24 100%);
            --accent: #10b981;
            --text: #f3f4f6;
            --text-muted: #9ca3af;
            --code-bg: #030712;
            --btc: #f7931a;
            --btc-dim: rgba(247, 147, 26, 0.12);
            --btc-border: rgba(247, 147, 26, 0.35);
        }}

        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
            font-family: 'Outfit', -apple-system, sans-serif;
        }}

        body {{
            background-color: var(--bg);
            color: var(--text);
            min-height: 100vh;
            display: flex;
            flex-direction: column;
            background-image:
                radial-gradient(at 15% 0%, rgba(247, 147, 26, 0.10) 0px, transparent 55%),
                radial-gradient(at 85% 100%, rgba(251, 191, 36, 0.07) 0px, transparent 55%);
            background-attachment: fixed;
        }}

        header {{
            padding: 1.25rem 2rem;
            display: flex;
            justify-content: space-between;
            align-items: center;
            border-bottom: 1px solid var(--card-border);
            backdrop-filter: blur(16px);
            position: sticky;
            top: 0;
            z-index: 50;
            background: rgba(8, 12, 20, 0.85);
        }}

        .logo {{
            font-size: 1.35rem;
            font-weight: 800;
            background: var(--primary-gradient);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            display: flex;
            align-items: center;
            gap: 0.5rem;
        }}

        .badge {{
            background: var(--btc-dim);
            color: var(--btc);
            font-size: 0.72rem;
            font-weight: 700;
            padding: 0.25rem 0.65rem;
            border-radius: 999px;
            border: 1px solid var(--btc-border);
            text-transform: uppercase;
            letter-spacing: 0.05em;
        }}

        main {{
            max-width: 1100px;
            margin: 0 auto;
            padding: 2rem 1.5rem 4rem;
            width: 100%;
            flex: 1;
        }}

        .hero {{
            text-align: center;
            padding: 3rem 1rem 2rem;
        }}

        .hero h1 {{
            font-size: clamp(1.8rem, 4vw, 2.8rem);
            font-weight: 800;
            line-height: 1.2;
            background: var(--primary-gradient);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            margin-bottom: 1rem;
        }}

        .hero p {{
            color: var(--text-muted);
            font-size: 1.1rem;
            max-width: 600px;
            margin: 0 auto;
            line-height: 1.7;
        }}

        .hero .btc-pill {{
            display: inline-flex;
            align-items: center;
            gap: 0.5rem;
            margin-top: 1.25rem;
            background: var(--btc-dim);
            border: 1px solid var(--btc-border);
            color: var(--btc);
            padding: 0.5rem 1.2rem;
            border-radius: 999px;
            font-size: 0.9rem;
            font-weight: 600;
        }}

        .pricing-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
            gap: 1.5rem;
            margin: 2.5rem 0;
        }}

        .card {{
            background: var(--card-bg);
            border: 1px solid var(--card-border);
            border-radius: 1.25rem;
            padding: 1.75rem;
            display: flex;
            flex-direction: column;
            gap: 1.25rem;
            backdrop-filter: blur(12px);
            transition: transform 0.2s ease, box-shadow 0.2s ease;
        }}

        .card:hover {{
            transform: translateY(-3px);
            box-shadow: 0 8px 32px rgba(0, 0, 0, 0.4);
        }}

        .card.featured {{
            border-color: var(--btc-border);
            background: radial-gradient(at top left, rgba(247, 147, 26, 0.10), transparent 70%), var(--card-bg);
            box-shadow: 0 0 0 1px var(--btc-border), 0 4px 24px rgba(247, 147, 26, 0.15);
        }}

        .card-title {{
            font-size: 1.2rem;
            font-weight: 700;
        }}

        .card-price {{
            font-size: 2.2rem;
            font-weight: 800;
            color: var(--btc);
        }}

        .card-price span {{
            font-size: 1rem;
            font-weight: 400;
            color: var(--text-muted);
        }}

        .features-list {{
            list-style: none;
            display: flex;
            flex-direction: column;
            gap: 0.6rem;
            flex: 1;
        }}

        .features-list li {{
            color: var(--text-muted);
            font-size: 0.95rem;
            display: flex;
            align-items: flex-start;
            gap: 0.5rem;
        }}

        .features-list li::before {{
            content: "✓";
            color: var(--accent);
            font-weight: 700;
            flex-shrink: 0;
            margin-top: 1px;
        }}

        .btn {{
            background: var(--primary-gradient);
            color: #0a0a0a;
            font-weight: 700;
            font-size: 0.95rem;
            border: none;
            padding: 0.85rem 1.5rem;
            border-radius: 0.75rem;
            cursor: pointer;
            width: 100%;
            transition: opacity 0.2s ease, transform 0.15s ease;
            letter-spacing: 0.02em;
        }}

        .btn:hover {{
            opacity: 0.92;
            transform: translateY(-1px);
        }}

        .btn:active {{
            transform: scale(0.98);
        }}

        .btn-outline {{
            background: transparent;
            color: var(--btc);
            border: 1px solid var(--btc-border);
            font-weight: 600;
            padding: 0.8rem 1.5rem;
            border-radius: 0.75rem;
            cursor: pointer;
            width: 100%;
            font-size: 0.95rem;
            transition: background 0.2s;
        }}

        .btn-outline:hover {{
            background: var(--btc-dim);
        }}

        /* ── BTC Payment Section ── */
        .btc-section {{
            background: var(--card-bg);
            border: 1px solid var(--btc-border);
            border-radius: 1.25rem;
            padding: 2rem;
            margin: 1rem 0 2.5rem;
            backdrop-filter: blur(12px);
        }}

        .btc-section h2 {{
            font-size: 1.4rem;
            font-weight: 800;
            margin-bottom: 1.5rem;
            display: flex;
            align-items: center;
            gap: 0.6rem;
        }}

        .btc-steps {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
            gap: 1.25rem;
            margin-bottom: 2rem;
        }}

        .step {{
            background: rgba(255, 255, 255, 0.03);
            border: 1px solid var(--card-border);
            border-radius: 1rem;
            padding: 1.25rem;
        }}

        .step-num {{
            width: 2rem;
            height: 2rem;
            background: var(--primary-gradient);
            color: #000;
            font-weight: 800;
            font-size: 0.9rem;
            border-radius: 50%;
            display: flex;
            align-items: center;
            justify-content: center;
            margin-bottom: 0.75rem;
        }}

        .step h3 {{
            font-size: 0.95rem;
            font-weight: 700;
            margin-bottom: 0.35rem;
        }}

        .step p {{
            font-size: 0.85rem;
            color: var(--text-muted);
            line-height: 1.5;
        }}

        .address-box {{
            display: flex;
            align-items: center;
            gap: 0.75rem;
            background: rgba(247, 147, 26, 0.07);
            border: 1px solid var(--btc-border);
            border-radius: 0.75rem;
            padding: 1rem 1.25rem;
            margin-bottom: 1.5rem;
            word-break: break-all;
        }}

        .address-box code {{
            font-family: 'JetBrains Mono', monospace;
            font-size: 0.9rem;
            color: var(--btc);
            flex: 1;
            letter-spacing: 0.02em;
        }}

        .btn-copy-addr {{
            background: var(--btc-dim);
            color: var(--btc);
            border: 1px solid var(--btc-border);
            padding: 0.45rem 0.9rem;
            border-radius: 0.5rem;
            font-size: 0.8rem;
            font-weight: 600;
            cursor: pointer;
            white-space: nowrap;
            transition: background 0.2s;
            flex-shrink: 0;
        }}

        .btn-copy-addr:hover {{
            background: rgba(247, 147, 26, 0.2);
        }}

        /* ── Formulaires ── */
        .form-section {{
            background: var(--card-bg);
            border: 1px solid var(--card-border);
            border-radius: 1.25rem;
            padding: 2rem;
            margin-bottom: 2rem;
            backdrop-filter: blur(12px);
        }}

        .form-section h2 {{
            font-size: 1.3rem;
            font-weight: 800;
            margin-bottom: 1.5rem;
        }}

        .form-group {{
            margin-bottom: 1.1rem;
        }}

        label {{
            display: block;
            font-size: 0.85rem;
            font-weight: 600;
            color: var(--text-muted);
            margin-bottom: 0.4rem;
            text-transform: uppercase;
            letter-spacing: 0.05em;
        }}

        input, select, textarea {{
            width: 100%;
            background: rgba(255, 255, 255, 0.04);
            border: 1px solid var(--card-border);
            color: var(--text);
            padding: 0.8rem 1rem;
            border-radius: 0.6rem;
            font-family: inherit;
            font-size: 0.95rem;
        }}

        input:focus, textarea:focus, select:focus {{
            outline: none;
            border-color: var(--btc);
        }}

        .tab-group {{
            display: flex;
            gap: 0.5rem;
            margin-bottom: 1.5rem;
        }}

        .tab {{
            flex: 1;
            padding: 0.65rem;
            border-radius: 0.65rem;
            font-size: 0.9rem;
            font-weight: 600;
            cursor: pointer;
            border: 1px solid var(--card-border);
            background: transparent;
            color: var(--text-muted);
            text-align: center;
            transition: all 0.2s;
        }}

        .tab.active {{
            background: var(--btc-dim);
            border-color: var(--btc-border);
            color: var(--btc);
        }}

        pre {{
            background: var(--code-bg);
            border: 1px solid var(--card-border);
            border-radius: 0.75rem;
            padding: 1rem;
            font-family: 'JetBrains Mono', monospace;
            font-size: 0.88rem;
            color: #a7f3d0;
            overflow-x: auto;
            min-height: 80px;
            white-space: pre-wrap;
        }}

        .alert {{
            padding: 0.9rem 1.1rem;
            border-radius: 0.75rem;
            font-size: 0.9rem;
            margin-top: 1rem;
            display: none;
        }}

        .alert.success {{
            background: rgba(16, 185, 129, 0.1);
            border: 1px solid rgba(16, 185, 129, 0.3);
            color: #6ee7b7;
            display: block;
        }}

        .alert.error {{
            background: rgba(239, 68, 68, 0.1);
            border: 1px solid rgba(239, 68, 68, 0.3);
            color: #fca5a5;
            display: block;
        }}

        .key-display {{
            background: rgba(247, 147, 26, 0.07);
            border: 1px solid var(--btc-border);
            border-radius: 0.75rem;
            padding: 1rem 1.25rem;
            display: flex;
            align-items: center;
            gap: 0.75rem;
            margin-top: 1rem;
        }}

        .key-display code {{
            font-family: 'JetBrains Mono', monospace;
            font-size: 0.88rem;
            color: var(--btc);
            flex: 1;
            word-break: break-all;
        }}

        /* ── Modal ── */
        .modal {{
            display: none;
            position: fixed;
            inset: 0;
            background: rgba(0,0,0,0.75);
            z-index: 100;
            align-items: center;
            justify-content: center;
            padding: 1rem;
            backdrop-filter: blur(4px);
        }}

        .modal-content {{
            background: #111827;
            border: 1px solid var(--btc-border);
            border-radius: 1.5rem;
            padding: 2.5rem;
            max-width: 520px;
            width: 100%;
            box-shadow: 0 25px 60px rgba(0,0,0,0.6), 0 0 0 1px rgba(247,147,26,0.2);
        }}

        footer {{
            text-align: center;
            padding: 2rem;
            border-top: 1px solid var(--card-border);
            color: var(--text-muted);
            font-size: 0.85rem;
            line-height: 1.6;
        }}
    </style>
</head>
<body>

    <header>
        <div class="logo">
            ⚡ OpenClawMesh <span class="badge">BTC Payments</span>
        </div>
        <div>
            <span style="font-size: 0.85rem; color: var(--text-muted);">₿ Paiement Bitcoin uniquement — Sans compte, sans KYC</span>
        </div>
    </header>

    <main>
        <section class="hero">
            <h1>Inférence IA Décentralisée<br>Payée en Bitcoin</h1>
            <p>Accédez à l'inférence multi-matériels haute performance et au réseau P2P d'agents IA autonomes — sans intermédiaire bancaire.</p>
            <div class="btc-pill">
                ₿ Paiement direct · Confidentialité totale · Pas de compte requis
            </div>
        </section>

        <!-- Plans tarifaires -->
        <section class="pricing-grid">
            <!-- Démo gratuite -->
            <div class="card">
                <div>
                    <div class="card-title">Découverte</div>
                    <div class="card-price">0€ <span>/ gratuit</span></div>
                </div>
                <ul class="features-list">
                    <li>3 requêtes de test</li>
                    <li>Validité 7 jours</li>
                    <li>Modèles IA standards</li>
                    <li>Support communautaire</li>
                </ul>
                <button class="btn-outline" onclick="generateDemoKey()">Obtenir une clé démo</button>
            </div>

            <!-- Pro Mensuel -->
            <div class="card featured">
                <div>
                    <span class="badge" style="display:inline-block; margin-bottom:0.5rem;">Recommandé</span>
                    <div class="card-title">Pro Mensuel</div>
                    <div class="card-price">10€ <span>/ mois en BTC</span></div>
                </div>
                <ul class="features-list">
                    <li>Sans quota numérique (débit et capacité applicables)</li>
                    <li>Inférence GPU NVIDIA / AMD / Apple Silicon</li>
                    <li>Recherche Vectorielle RAG</li>
                    <li>Renouvellement simple en BTC</li>
                </ul>
                <button class="btn" onclick="selectPlan('pro_monthly')">Payer en Bitcoin (10€)</button>
            </div>

            <!-- Lifetime -->
            <div class="card" style="border-color:rgba(251,191,36,0.4); background: radial-gradient(at top right, rgba(251,191,36,0.08), transparent 70%), var(--card-bg);">
                <div>
                    <span class="badge" style="background:rgba(251,191,36,0.15); color:#fbbf24; border-color:rgba(251,191,36,0.4); display:inline-block; margin-bottom:0.5rem;">Paiement Unique</span>
                    <div class="card-title">Licence à Vie</div>
                    <div class="card-price" style="color:#fbbf24;">200€ <span>/ à vie en BTC</span></div>
                </div>
                <ul class="features-list">
                    <li>Accès illimité à vie sans abonnement</li>
                    <li>Tous moteurs GPU & CPU accélérés</li>
                    <li>Toutes les futures mises à jour incluses</li>
                    <li>Clé Ed25519 & Support VIP</li>
                </ul>
                <button class="btn" style="background:linear-gradient(135deg,#fbbf24 0%,#f59e0b 100%);" onclick="selectPlan('lifetime')">Acheter à Vie (200€ en BTC)</button>
            </div>
        </section>

        <!-- Section Paiement BTC -->
        <section class="btc-section" id="btcSection">
            <h2>₿ Comment Payer en Bitcoin</h2>

            <div class="btc-steps">
                <div class="step">
                    <div class="step-num">1</div>
                    <h3>Choisissez votre plan</h3>
                    <p>Cliquez sur « Payer en Bitcoin » ci-dessus pour sélectionner votre plan.</p>
                </div>
                <div class="step">
                    <div class="step-num">2</div>
                    <h3>Envoyez le montant BTC</h3>
                    <p>Scannez l'adresse ou copiez-la dans votre wallet. Envoyez l'équivalent exact du plan.</p>
                </div>
                <div class="step">
                    <div class="step-num">3</div>
                    <h3>Soumettez votre txid</h3>
                    <p>Renseignez votre email, le txid de la transaction et votre plan dans le formulaire.</p>
                </div>
                <div class="step">
                    <div class="step-num">4</div>
                    <h3>Clé activée instantanément après confirmation</h3>
                    <p>Après vérification sur la blockchain, votre clé d'API sera activée et retournée.</p>
                </div>
            </div>

            <label>Adresse Bitcoin de paiement :</label>
            <div class="address-box">
                <code id="btcAddressDisplay">{btc_address}</code>
                <button class="btn-copy-addr" onclick="copyAddress()">Copier</button>
            </div>

            <div style="display:flex; align-items:center; gap:1rem; flex-wrap:wrap;">
                <div style="background:white; padding:0.75rem; border-radius:0.75rem;">
                    <img src="{btc_qr_data_uri}" alt="QR Code Bitcoin généré localement" width="150" height="150" style="display:block; border-radius:0.35rem;">
                </div>
                <div style="flex:1; min-width:200px;">
                    <p style="color:var(--text-muted); font-size:0.9rem; line-height:1.7;">
                        ₿ Scannez le QR code avec votre wallet (Electrum, BlueWallet, Phoenix, Muun…)<br>
                        ou copiez l'adresse manuellement.<br><br>
                        <strong style="color:var(--text);">Taux de change :</strong>
                        consultez votre portefeuille ou exchange habituel dans un autre onglet.
                    </p>
                </div>
            </div>
        </section>

        <!-- Tabs : Soumettre paiement / Vérifier statut -->
        <div class="form-section">
            <h2>Gestion de Paiement</h2>

            <div class="tab-group">
                <button class="tab active" id="tab-submit" onclick="switchTab('submit')">📤 Soumettre un paiement</button>
                <button class="tab" id="tab-status" onclick="switchTab('status')">🔍 Vérifier le statut</button>
            </div>

            <!-- Formulaire soumission -->
            <div id="panel-submit">
                <div class="form-group">
                    <label>Plan sélectionné</label>
                    <select id="submitPlan" onchange="updatePriceHint()">
                        <option value="pro_monthly">Pro Mensuel — 10€/mois</option>
                        <option value="lifetime">Licence à Vie — 200€ paiement unique</option>
                    </select>
                </div>
                <div class="form-group">
                    <label>Votre adresse email</label>
                    <input type="email" id="submitEmail" placeholder="vous@exemple.com">
                </div>
                <div class="form-group">
                    <label>Transaction ID (txid Bitcoin)</label>
                    <input type="text" id="submitTxid" placeholder="a1b2c3d4e5f6... (64 caractères hex)" style="font-family:'JetBrains Mono',monospace; font-size:0.85rem;">
                </div>
                <div class="form-group">
                    <label>Note (optionnel)</label>
                    <input type="text" id="submitNote" placeholder="Ex: depuis Bisq, wallet Electrum...">
                </div>
                <p style="color:var(--text-muted); font-size:0.85rem;">Vos email, txid et note sont transmis à cette passerelle et conservés avec le statut du paiement pour la vérification. N’envoyez pas de données personnelles inutiles.</p>
                <button class="btn" style="width:auto; padding:0.85rem 2.5rem;" onclick="submitPayment()">₿ Soumettre mon paiement</button>
                <div id="submitAlert"></div>
            </div>

            <!-- Vérification statut -->
            <div id="panel-status" style="display:none;">
                <div class="form-group">
                    <label>Payment ID (reçu lors de votre soumission)</label>
                    <input type="text" id="statusPaymentId" placeholder="ex: 3a7f9c1e2b4d...">
                </div>
                <button class="btn" style="width:auto; padding:0.85rem 2.5rem;" onclick="checkStatus()">🔍 Vérifier le statut</button>
                <div id="statusResult" style="margin-top:1rem;"></div>
            </div>
        </div>

        <!-- Nœud WAN 100% Confiance -->
        <div class="form-section">
            <div style="display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:0.5rem; margin-bottom:1rem;">
                <h2 style="margin:0;">🌐 Passerelle & Nœud WAN</h2>
                <span id="wanBadge" class="badge badge-info">100% Confiance</span>
            </div>
            <p style="color:var(--text-muted); margin-bottom:1.2rem;">
                Basculez votre nœud OpenClaw d’une écoute locale (<code style="color:var(--accent);">127.0.0.1</code>) à une exposition réseau mondiale (<code style="color:var(--accent);">0.0.0.0</code>) en 1 clic. Le chiffrement TLS et l'authentification PSK sont configurés automatiquement.
            </p>
            <div class="form-group">
                <label>Jeton Administrateur (Optionnel si exécuté localement)</label>
                <input type="password" id="wanAdminToken" placeholder="X-Admin-Token (automatiquement mémorisé)">
            </div>
            <label style="display:flex; align-items:center; gap:0.6rem; color:var(--text-muted); margin-bottom:1.2rem; cursor:pointer;">
                <input type="checkbox" id="wanRemoteAccess" checked>
                <strong>Exposer sur toutes les interfaces réseau (0.0.0.0 / WAN)</strong>
            </label>
            <button id="wanToggleBtn" class="btn" style="width:100%; font-size:1rem; padding:0.85rem;" onclick="toggleWanNode()">
                🌐 Activer le Nœud WAN (100% Confiance & Auto-Sécurisé)
            </button>

            <!-- Dashboard de connexion active (affiché après activation) -->
            <div id="wanActiveCard" style="display:none; margin-top:1.5rem; background:rgba(0,255,136,0.05); border:1px solid rgba(0,255,136,0.3); border-radius:12px; padding:1.2rem;">
                <div style="display:flex; align-items:center; gap:0.5rem; margin-bottom:0.8rem;">
                    <span style="color:#00ff88; font-size:1.2rem;">●</span>
                    <strong style="color:#00ff88;">Nœud WAN Actif & Opérationnel</strong>
                </div>
                <div style="display:grid; grid-template-columns:1fr; gap:0.8rem; font-size:0.9rem;">
                    <div>
                        <span style="color:var(--text-muted);">URL Endpoint :</span>
                        <code id="wanEndpointVal" style="display:block; padding:0.4rem 0.6rem; background:rgba(0,0,0,0.4); border-radius:6px; margin-top:0.2rem; color:var(--accent); word-break:break-all;"></code>
                    </div>
                    <div>
                        <span style="color:var(--text-muted);">Clé PSK Générée :</span>
                        <code id="wanPskVal" style="display:block; padding:0.4rem 0.6rem; background:rgba(0,0,0,0.4); border-radius:6px; margin-top:0.2rem; color:#f7931a; word-break:break-all;"></code>
                    </div>
                    <div>
                        <span style="color:var(--text-muted);">Commande d'appel pour Agents OpenClaw :</span>
                        <div style="display:flex; gap:0.5rem; margin-top:0.2rem;">
                            <code id="wanCliVal" style="flex:1; padding:0.4rem 0.6rem; background:rgba(0,0,0,0.4); border-radius:6px; color:#fff; word-break:break-all;"></code>
                            <button class="btn-outline" style="padding:0.4rem 0.8rem; font-size:0.8rem;" onclick="copyWanCli()">Copier</button>
                        </div>
                    </div>
                </div>
            </div>

            <div id="wanAlert" style="margin-top:1rem;"></div>
        </div>

        <!-- Playground -->
        <div class="form-section">
            <h2>🧪 Tester votre Clé en Direct</h2>

            <div class="form-group">
                <label>Clé d'API OpenClaw (Header X-API-Key)</label>
                <input type="text" id="playKey" placeholder="sk_claw_...">
            </div>

            <div class="form-group">
                <label>Compétence à exécuter</label>
                <select id="playSkill">
                    <option value="llm">llm — Inférence LLM (MLX / CUDA / CPU)</option>
                    <option value="memory_search">memory_search — RAG Sémantique SQLite</option>
                    <option value="echo">echo — Ping / Test de connectivité</option>
                </select>
            </div>

            <div class="form-group">
                <label>Payload JSON</label>
                <textarea id="playPayload" rows="3">{{"prompt": "Explique en 2 phrases le protocole P2P OpenClawMesh."}}</textarea>
            </div>

            <button class="btn" style="width:auto; padding:0.8rem 2rem;" onclick="runPlayground()">Exécuter la requête</button>

            <div style="margin-top:1.5rem;">
                <label>Réponse de la passerelle :</label>
                <pre id="playOutput">// Le résultat s'affichera ici...</pre>
            </div>
        </div>
    </main>

    <!-- Modal clé démo -->
    <div class="modal" id="keyModal">
        <div class="modal-content">
            <h2 style="font-size:1.5rem; font-weight:800; color:#fff;">🎉 Clé Démo Générée !</h2>
            <p style="color:var(--text-muted); margin-top:0.5rem; font-size:0.95rem;">Voici votre clé gratuite (3 requêtes, 7 jours). Conservez-la :</p>

            <div class="key-display">
                <code id="modalApiKey">sk_claw_...</code>
                <button class="btn-copy-addr" onclick="copyKey()">Copier</button>
            </div>

            <div style="background:rgba(255,255,255,0.03); padding:1rem; border-radius:0.75rem; font-size:0.85rem; color:var(--text-muted); margin-top:1rem;">
                <strong>Utilisation dans OpenClaw :</strong>
                <pre style="margin-top:0.5rem; color:#93c5fd; font-size:0.82rem;">export OPENCLAW_API_KEY="<span id="modalKeyPlaceholder">...</span>"</pre>
            </div>

            <button class="btn" style="margin-top:1.25rem;" onclick="closeModal()">Fermer et Tester</button>
        </div>
    </div>

    <footer>
        OpenClawMesh &copy; 2026 — Inférence IA Décentralisée & Multi-Matériels.<br>
        Paiements Bitcoin uniquement — Confidentialité & Souveraineté financière.
    </footer>

    <script>
        // ── Utils ──────────────────────────────────────────────────────
        function showAlert(containerId, message, type) {{
            const el = document.getElementById(containerId);
            el.className = 'alert ' + type;
            el.innerHTML = message;
        }}

        function copyAddress() {{
            navigator.clipboard.writeText('{btc_address}');
            const btn = document.querySelector('.btn-copy-addr');
            const prev = btn.textContent;
            btn.textContent = '✓ Copié !';
            setTimeout(() => btn.textContent = prev, 2000);
        }}

        function copyKey() {{
            const key = document.getElementById('modalApiKey').innerText;
            navigator.clipboard.writeText(key);
            alert('Clé copiée !');
        }}

        function closeModal() {{
            document.getElementById('keyModal').style.display = 'none';
        }}

        function showKeyModal(key) {{
            document.getElementById('modalApiKey').innerText = key;
            document.getElementById('modalKeyPlaceholder').innerText = key;
            document.getElementById('playKey').value = key;
            document.getElementById('keyModal').style.display = 'flex';
        }}

        // ── Tabs ───────────────────────────────────────────────────────
        function switchTab(tab) {{
            document.getElementById('panel-submit').style.display = tab === 'submit' ? 'block' : 'none';
            document.getElementById('panel-status').style.display = tab === 'status' ? 'block' : 'none';
            document.getElementById('tab-submit').className = 'tab' + (tab === 'submit' ? ' active' : '');
            document.getElementById('tab-status').className = 'tab' + (tab === 'status' ? ' active' : '');
        }}

        // ── Sélection plan via bouton carte ────────────────────────────
        function selectPlan(plan) {{
            document.getElementById('submitPlan').value = plan;
            document.getElementById('btcSection').scrollIntoView({{ behavior: 'smooth' }});
            document.getElementById('submitEmail').focus();
        }}

        function updatePriceHint() {{
            // Peut afficher un texte indicatif si besoin
        }}

        let paymentStatusToken = '';

        document.addEventListener('DOMContentLoaded', () => {{
            const savedToken = localStorage.getItem('openclaw_admin_token');
            if (savedToken) {{
                const input = document.getElementById('wanAdminToken');
                if (input) input.value = savedToken;
            }}
        }});

        async function toggleWanNode() {{
            const tokenInput = document.getElementById('wanAdminToken');
            const token = tokenInput ? tokenInput.value.trim() : '';
            if (token) localStorage.setItem('openclaw_admin_token', token);
            const remoteAccess = document.getElementById('wanRemoteAccess').checked;

            const btn = document.getElementById('wanToggleBtn');
            const card = document.getElementById('wanActiveCard');
            const badge = document.getElementById('wanBadge');

            showAlert('wanAlert', '⌛ Bascule de l’état du nœud...', 'success');
            try {{
                const headers = {{ 'Content-Type': 'application/json', ...(token ? {{ 'X-Admin-Token': token }} : {{}}) }};
                const res = await fetch('/api/v1/admin/wan/toggle', {{
                    method: 'POST', headers, body: JSON.stringify({{ remote_access: remoteAccess }})
                }});
                const data = await res.json();
                if (res.ok && data.ok) {{
                    showAlert('wanAlert', (data.active ? '🟢 ' : '⚪ ') + (data.message || 'Succès.'), 'success');
                    if (data.active) {{
                        btn.innerHTML = '🔴 Désactiver le Nœud WAN (Mode Local 127.0.0.1)';
                        btn.style.background = '#e74c3c';
                        badge.className = 'badge badge-confirmed';
                        badge.textContent = 'En Ligne (0.0.0.0:' + data.port + ')';
                        document.getElementById('wanEndpointVal').textContent = data.connect_url || '';
                        document.getElementById('wanPskVal').textContent = data.psk || '';
                        document.getElementById('wanCliVal').textContent = data.cli_command || '';
                        card.style.display = 'block';
                    }} else {{
                        btn.innerHTML = '🌐 Activer le Nœud WAN (100% Confiance & Auto-Sécurisé)';
                        btn.style.background = '';
                        badge.className = 'badge badge-info';
                        badge.textContent = '100% Confiance';
                        card.style.display = 'none';
                    }}
                }} else {{
                    showAlert('wanAlert', '❌ ' + (data.detail || data.message || 'Erreur lors de la bascule.'), 'error');
                }}
            }} catch (err) {{ showAlert('wanAlert', '❌ Erreur réseau : ' + err, 'error'); }}
        }}

        function copyWanCli() {{
            const val = document.getElementById('wanCliVal').textContent;
            if (val) {{
                navigator.clipboard.writeText(val);
                showAlert('wanAlert', '📋 Commande d’appel pour agents OpenClaw copiée dans le presse-papiers !', 'success');
            }}
        }}

        // ── Soumettre paiement BTC ─────────────────────────────────────
        async function submitPayment() {{
            const email = document.getElementById('submitEmail').value.trim();
            const plan  = document.getElementById('submitPlan').value;
            const txid  = document.getElementById('submitTxid').value.trim();
            const note  = document.getElementById('submitNote').value.trim();

            if (!email || !txid) {{
                showAlert('submitAlert', '⚠️ Email et txid sont obligatoires.', 'error');
                return;
            }}
            if (!/^[0-9a-fA-F]{{64}}$/.test(txid)) {{
                showAlert('submitAlert', '⚠️ Le txid Bitcoin doit contenir 64 caractères hexadécimaux.', 'error');
                return;
            }}

            document.getElementById('submitAlert').className = '';
            document.getElementById('submitAlert').innerHTML = '⌛ Envoi en cours...';

            try {{
                const res = await fetch('/api/v1/payment/submit', {{
                    method: 'POST',
                    headers: {{ 'Content-Type': 'application/json' }},
                    body: JSON.stringify({{ email, plan, txid, note }})
                }});
                const data = await res.json();

                if (res.ok && data.ok) {{
                    showAlert('submitAlert',
                        `✅ <strong>Paiement enregistré !</strong><br>
                        Payment ID : <code style="font-family:monospace; color:#f7931a;">${{data.payment_id}}</code><br>
                        Conservez ce code pour suivre votre paiement. Votre clé sera activée dès la confirmation du txid par l’administrateur.`,
                        'success'
                    );
                    // Pré-remplir l'onglet de vérification
                    document.getElementById('statusPaymentId').value = data.payment_id;
                    paymentStatusToken = data.status_token;
                }} else {{
                    showAlert('submitAlert', '❌ ' + (data.detail || data.error || 'Erreur inconnue.'), 'error');
                }}
            }} catch (err) {{
                showAlert('submitAlert', '❌ Erreur réseau : ' + err, 'error');
            }}
        }}

        // ── Vérifier statut ────────────────────────────────────────────
        async function checkStatus() {{
            const paymentId = document.getElementById('statusPaymentId').value.trim();
            if (!paymentId) {{
                document.getElementById('statusResult').innerHTML =
                    '<div class="alert error">⚠️ Veuillez saisir un Payment ID.</div>';
                return;
            }}

            document.getElementById('statusResult').innerHTML = '<p style="color:var(--text-muted);">⌛ Vérification...</p>';

            try {{
                const res = await fetch('/api/v1/payment/status/' + encodeURIComponent(paymentId), {{
                    headers: {{ 'X-Payment-Token': paymentStatusToken }}
                }});
                const data = await res.json();

                if (!res.ok) {{
                    document.getElementById('statusResult').innerHTML =
                        `<div class="alert error">❌ ${{data.detail || 'Introuvable.'}}</div>`;
                    return;
                }}

                const statusLabels = {{
                    'pending_verification': '⌛ En attente de vérification admin',
                    'confirmed': '✅ Confirmé — Clé active',
                    'rejected': '❌ Rejeté',
                }};

                let html = `<div class="alert success" style="display:block;">
                    <strong>${{statusLabels[data.status] || data.status}}</strong><br>
                    Plan : <strong>${{data.plan}}</strong> · Email : ${{data.email}}`;

                if (data.status === 'confirmed' && data.api_key) {{
                    html += `<br><br><strong>Votre clé d'API :</strong>`;
                    document.getElementById('statusResult').innerHTML = html + '</div>';
                    const keyDiv = document.createElement('div');
                    keyDiv.className = 'key-display';
                    keyDiv.innerHTML = `<code>${{data.api_key}}</code>
                        <button class="btn-copy-addr" onclick="navigator.clipboard.writeText('${{data.api_key}}')">Copier</button>`;
                    document.getElementById('statusResult').querySelector('.alert').appendChild(keyDiv);
                    document.getElementById('playKey').value = data.api_key;
                    return;
                }} else if (data.status === 'rejected') {{
                    html += `<br>Raison : ${{data.rejection_reason || 'Non précisée.'}}`;
                }}

                html += '</div>';
                document.getElementById('statusResult').innerHTML = html;

            }} catch (err) {{
                document.getElementById('statusResult').innerHTML =
                    `<div class="alert error">❌ Erreur réseau : ${{err}}</div>`;
            }}
        }}

        // ── Clé Démo ──────────────────────────────────────────────────
        async function generateDemoKey() {{
            const email = 'demo_' + Math.random().toString(36).substring(7) + '@openclaw.mesh';
            try {{
                const res = await fetch('/api/v1/checkout/demo-key', {{
                    method: 'POST',
                    headers: {{ 'Content-Type': 'application/json' }},
                    body: JSON.stringify({{ email }})
                }});
                const data = await res.json();
                if (data.ok) showKeyModal(data.api_key);
                else alert('Erreur : ' + (data.detail || 'Inconnue'));
            }} catch (err) {{
                alert('Erreur démo : ' + err);
            }}
        }}

        // ── Playground ─────────────────────────────────────────────────
        async function runPlayground() {{
            const key = document.getElementById('playKey').value.trim();
            const skill = document.getElementById('playSkill').value;
            const payloadRaw = document.getElementById('playPayload').value;
            const outEl = document.getElementById('playOutput');

            if (!key) {{ alert('Veuillez saisir ou générer une clé d\'API d\'abord.'); return; }}

            let payload;
            try {{
                payload = JSON.parse(payloadRaw);
            }} catch (e) {{
                outEl.innerText = 'Erreur : Payload JSON invalide.';
                return;
            }}

            outEl.innerText = '⌛ Exécution de la compétence sur la passerelle...';

            try {{
                const res = await fetch('/api/v1/execute', {{
                    method: 'POST',
                    headers: {{ 'Content-Type': 'application/json', 'X-API-Key': key }},
                    body: JSON.stringify({{ skill, payload }})
                }});
                const result = await res.json();
                outEl.innerText = JSON.stringify(result, null, 2);
            }} catch (err) {{
                outEl.innerText = 'Erreur d\'appel : ' + err;
            }}
        }}
    </script>
</body>
</html>
"""
