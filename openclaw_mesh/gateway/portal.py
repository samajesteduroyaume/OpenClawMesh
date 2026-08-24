"""
Portail Web Client & Playground Interactif pour OpenClawMesh Gateway.

Interface moderne, dark mode, responsive avec :
- Présentation des offres & plans tarifaires
- Achat direct ou simulation de paiement
- Affichage de clé avec copie 1-clic
- Playground de test de compétences en temps réel
"""


def render_portal_html(portal_title: str = "OpenClawMesh — API Store & Gateway") -> str:
    return f"""<!DOCTYPE html>
<html lang="fr">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{portal_title}</title>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;600;700;800&family=JetBrains+Mono:wght@400;600&display=swap" rel="stylesheet">
    <style>
        :root {{
            --bg: #0b0f19;
            --card-bg: rgba(22, 30, 49, 0.7);
            --card-border: rgba(255, 255, 255, 0.08);
            --primary: #6366f1;
            --primary-gradient: linear-gradient(135deg, #6366f1 0%, #a855f7 100%);
            --accent: #10b981;
            --text: #f3f4f6;
            --text-muted: #9ca3af;
            --code-bg: #030712;
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
                radial-gradient(at 0% 0%, rgba(99, 102, 241, 0.15) 0px, transparent 50%),
                radial-gradient(at 100% 100%, rgba(168, 85, 247, 0.12) 0px, transparent 50%);
            background-attachment: fixed;
        }}

        header {{
            padding: 1.5rem 2rem;
            display: flex;
            justify-content: space-between;
            align-items: center;
            border-bottom: 1px solid var(--card-border);
            backdrop-filter: blur(12px);
            position: sticky;
            top: 0;
            z-index: 50;
        }}

        .logo {{
            font-size: 1.4rem;
            font-weight: 800;
            background: var(--primary-gradient);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            display: flex;
            align-items: center;
            gap: 0.5rem;
        }}

        .badge {{
            background: rgba(99, 102, 241, 0.2);
            color: #818cf8;
            font-size: 0.75rem;
            padding: 0.2rem 0.6rem;
            border-radius: 9999px;
            border: 1px solid rgba(99, 102, 241, 0.3);
            font-weight: 600;
        }}

        main {{
            max-width: 1100px;
            margin: 0 auto;
            padding: 3rem 1.5rem;
            flex: 1;
            width: 100%;
        }}

        .hero {{
            text-align: center;
            margin-bottom: 3.5rem;
        }}

        .hero h1 {{
            font-size: 3rem;
            font-weight: 800;
            line-height: 1.15;
            margin-bottom: 1rem;
            background: linear-gradient(180deg, #ffffff 0%, #cbd5e1 100%);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
        }}

        .hero p {{
            color: var(--text-muted);
            font-size: 1.2rem;
            max-width: 650px;
            margin: 0 auto;
        }}

        .pricing-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
            gap: 2rem;
            margin-bottom: 4rem;
        }}

        .card {{
            background: var(--card-bg);
            border: 1px solid var(--card-border);
            border-radius: 1.25rem;
            padding: 2.5rem 2rem;
            display: flex;
            flex-direction: column;
            position: relative;
            backdrop-filter: blur(16px);
            transition: transform 0.2s ease, border-color 0.2s ease;
        }}

        .card:hover {{
            transform: translateY(-4px);
            border-color: rgba(99, 102, 241, 0.4);
        }}

        .card.featured {{
            border-color: var(--primary);
            box-shadow: 0 0 40px rgba(99, 102, 241, 0.2);
        }}

        .card-header {{
            margin-bottom: 1.5rem;
        }}

        .card-title {{
            font-size: 1.3rem;
            font-weight: 700;
            margin-bottom: 0.5rem;
        }}

        .card-price {{
            font-size: 2.5rem;
            font-weight: 800;
            color: #fff;
            display: flex;
            align-items: baseline;
            gap: 0.3rem;
        }}

        .card-price span {{
            font-size: 1rem;
            color: var(--text-muted);
            font-weight: 400;
        }}

        .features-list {{
            list-style: none;
            margin-bottom: 2rem;
            flex: 1;
        }}

        .features-list li {{
            display: flex;
            align-items: center;
            gap: 0.6rem;
            margin-bottom: 0.8rem;
            color: #e2e8f0;
            font-size: 0.95rem;
        }}

        .features-list li::before {{
            content: "✓";
            color: var(--accent);
            font-weight: 800;
        }}

        .btn {{
            background: var(--primary-gradient);
            color: white;
            border: none;
            padding: 0.9rem 1.5rem;
            border-radius: 0.75rem;
            font-size: 1rem;
            font-weight: 600;
            cursor: pointer;
            width: 100%;
            transition: opacity 0.2s, transform 0.1s;
            text-align: center;
            text-decoration: none;
            display: inline-block;
        }}

        .btn:hover {{
            opacity: 0.92;
            transform: scale(0.99);
        }}

        .btn-outline {{
            background: transparent;
            border: 1px solid var(--card-border);
            color: var(--text);
        }}

        .btn-outline:hover {{
            background: rgba(255, 255, 255, 0.05);
            border-color: rgba(255, 255, 255, 0.2);
        }}

        .modal {{
            display: none;
            position: fixed;
            inset: 0;
            background: rgba(0, 0, 0, 0.75);
            backdrop-filter: blur(8px);
            z-index: 100;
            align-items: center;
            justify-content: center;
            padding: 1.5rem;
        }}

        .modal-content {{
            background: #111827;
            border: 1px solid var(--card-border);
            border-radius: 1.5rem;
            max-width: 550px;
            width: 100%;
            padding: 2.5rem;
            position: relative;
        }}

        .key-box {{
            background: var(--code-bg);
            border: 1px solid rgba(99, 102, 241, 0.3);
            border-radius: 0.75rem;
            padding: 1rem;
            display: flex;
            justify-content: space-between;
            align-items: center;
            font-family: 'JetBrains Mono', monospace;
            color: #38bdf8;
            font-size: 0.95rem;
            margin: 1.5rem 0;
            word-break: break-all;
        }}

        .btn-copy {{
            background: rgba(99, 102, 241, 0.2);
            color: #818cf8;
            border: 1px solid rgba(99, 102, 241, 0.4);
            border-radius: 0.5rem;
            padding: 0.4rem 0.8rem;
            cursor: pointer;
            font-size: 0.85rem;
            font-weight: 600;
            white-space: nowrap;
            margin-left: 0.8rem;
        }}

        .playground {{
            background: var(--card-bg);
            border: 1px solid var(--card-border);
            border-radius: 1.25rem;
            padding: 2.5rem;
            backdrop-filter: blur(16px);
        }}

        .form-group {{
            margin-bottom: 1.25rem;
        }}

        label {{
            display: block;
            margin-bottom: 0.5rem;
            font-size: 0.9rem;
            font-weight: 600;
            color: var(--text-muted);
        }}

        input, textarea, select {{
            width: 100%;
            background: var(--code-bg);
            border: 1px solid var(--card-border);
            color: #fff;
            padding: 0.8rem 1rem;
            border-radius: 0.6rem;
            font-family: inherit;
            font-size: 0.95rem;
        }}

        input:focus, textarea:focus {{
            outline: none;
            border-color: var(--primary);
        }}

        pre {{
            background: var(--code-bg);
            border: 1px solid var(--card-border);
            border-radius: 0.75rem;
            padding: 1rem;
            font-family: 'JetBrains Mono', monospace;
            font-size: 0.9rem;
            color: #a7f3d0;
            overflow-x: auto;
            min-height: 80px;
        }}

        footer {{
            text-align: center;
            padding: 2rem;
            border-top: 1px solid var(--card-border);
            color: var(--text-muted);
            font-size: 0.9rem;
        }}
    </style>
</head>
<body>

    <header>
        <div class="logo">
            ⚡ OpenClawMesh <span class="badge">API Access</span>
        </div>
        <div>
            <span style="font-size: 0.9rem; color: var(--text-muted);">🔒 Paiement Sécurisé CB & Apple Pay</span>
        </div>
    </header>

    <main>
        <section class="hero">
            <h1>Débloquez la Puissance d'OpenClawMesh</h1>
            <p>Accédez instantanément à l'inférence IA multi-matériels haute performance et au réseau décentralisé d'agents autonomes.</p>
        </section>

        <!-- Pricing Cards -->
        <section class="pricing-grid">
            
            <!-- Plan Découverte -->
            <div class="card">
                <div class="card-header">
                    <div class="card-title">Découverte</div>
                    <div class="card-price">0€ <span>/ gratuit</span></div>
                </div>
                <ul class="features-list">
                    <li>3 requêtes de test par jour</li>
                    <li>Modèles IA standards</li>
                    <li>Support communautaire</li>
                </ul>
                <button class="btn btn-outline" onclick="generateDemoKey()">Obtenir une clé démo</button>
            </div>

            <!-- Plan Pro Mensuel -->
            <div class="card featured">
                <div class="card-header">
                    <span class="badge" style="margin-bottom: 0.5rem; display: inline-block;">Recommandé</span>
                    <div class="card-title">Pro Mensuel</div>
                    <div class="card-price">10€ <span>/ mois</span></div>
                </div>
                <ul class="features-list">
                    <li>Requêtes IA illimitées</li>
                    <li>Inférence GPU (NVIDIA, AMD, Intel, Apple Silicon)</li>
                    <li>Recherche Vectorielle SQLite RAG</li>
                    <li>Support prioritaire & Webhook direct</li>
                </ul>
                <button class="btn" onclick="buyPlan('pro_monthly', 10)">S'abonner (10€/mois)</button>
            </div>

            <!-- Plan Licence à Vie -->
            <div class="card" style="border-color: rgba(234, 179, 8, 0.4); background: radial-gradient(at top right, rgba(234, 179, 8, 0.08), transparent 70%), var(--card-bg);">
                <div class="card-header">
                    <span class="badge" style="background: rgba(234, 179, 8, 0.2); color: #facc15; border-color: rgba(234, 179, 8, 0.4); margin-bottom: 0.5rem; display: inline-block;">Paiement Unique</span>
                    <div class="card-title">Licence à Vie</div>
                    <div class="card-price">200€ <span>/ à vie</span></div>
                </div>
                <ul class="features-list">
                    <li>Accès illimité à vie sans abonnement</li>
                    <li>Tous moteurs GPU & CPU accélérés</li>
                    <li>Toutes les futures mises à jour incluses</li>
                    <li>Clé privée Ed25519 & Support VIP</li>
                </ul>
                <button class="btn" style="background: linear-gradient(135deg, #eab308 0%, #ca8a04 100%); color: #000; font-weight: 700;" onclick="buyPlan('lifetime', 200)">Acheter à Vie (200€)</button>
            </div>

        </section>

        <!-- Live API Playground -->
        <section class="playground">
            <h2 style="font-size: 1.5rem; font-weight: 700; margin-bottom: 1.5rem;">🧪 Tester votre Clé en Direct (Playground)</h2>
            
            <div class="form-group">
                <label>Clé d'API OpenClaw (Header X-API-Key) :</label>
                <input type="text" id="playKey" placeholder="sk_claw_..." value="">
            </div>

            <div class="form-group">
                <label>Compétence à exécuter :</label>
                <select id="playSkill">
                    <option value="llm">llm (Inférence MLX Apple Silicon)</option>
                    <option value="memory_search">memory_search (RAG Sémantique SQLite)</option>
                    <option value="echo">echo (Ping / Test)</option>
                </select>
            </div>

            <div class="form-group">
                <label>Prompt ou Payload (JSON) :</label>
                <textarea id="playPayload" rows="3">{{"prompt": "Explique en 2 phrases le protocole P2P OpenClawMesh."}}</textarea>
            </div>

            <button class="btn" style="width: auto; padding: 0.8rem 2rem;" onclick="runPlayground()">Exécuter la requête</button>

            <div style="margin-top: 1.5rem;">
                <label>Réponse de la passerelle :</label>
                <pre id="playOutput">// Le résultat s'affichera ici...</pre>
            </div>
        </section>
    </main>

    <!-- Modal Affichage Clé -->
    <div class="modal" id="keyModal">
        <div class="modal-content">
            <h2 style="font-size: 1.6rem; font-weight: 800; color: #fff;">🎉 Paiement Validé !</h2>
            <p style="color: var(--text-muted); margin-top: 0.5rem;">Voici votre clé d'API personnelle. Conservez-la précieusement :</p>
            
            <div class="key-box">
                <span id="modalApiKey">sk_claw_...</span>
                <button class="btn-copy" onclick="copyKey()">Copier</button>
            </div>

            <div style="background: rgba(255,255,255,0.03); padding: 1rem; border-radius: 0.75rem; font-size: 0.85rem; color: var(--text-muted);">
                <strong>Comment l'utiliser dans OpenClaw :</strong>
                <pre style="margin-top: 0.5rem; color: #93c5fd;">export OPENCLAW_API_KEY="<span id="modalKeyPlaceholder">...</span>"</pre>
            </div>

            <button class="btn" style="margin-top: 1.5rem;" onclick="closeModal()">Fermer et Tester</button>
        </div>
    </div>

    <footer>
        OpenClawMesh &copy; 2026 — Inférence IA Décentralisée & Multi-Matériels. Tous droits réservés.
    </footer>

    <script>
        async function buyPlan(planName, price) {{
            const email = prompt("Veuillez saisir votre adresse email pour recevoir votre clé :", "client@exemple.com");
            if (!email) return;

            // Appel de l'API de création de session checkout ou simulation
            try {{
                const res = await fetch('/api/v1/checkout/simulate', {{
                    method: 'POST',
                    headers: {{ 'Content-Type': 'application/json' }},
                    body: JSON.stringify({{ email: email, plan: planName, amount: price * 100 }})
                }});
                const data = await res.json();
                if (data.ok) {{
                    showKeyModal(data.api_key);
                }} else {{
                    alert("Erreur: " + data.error);
                }}
            }} catch (err) {{
                alert("Erreur lors de la commande: " + err);
            }}
        }}

        async function generateDemoKey() {{
            const email = "demo_" + Math.random().toString(36).substring(7) + "@openclaw.mesh";
            try {{
                const res = await fetch('/api/v1/checkout/demo-key', {{
                    method: 'POST',
                    headers: {{ 'Content-Type': 'application/json' }},
                    body: JSON.stringify({{ email: email }})
                }});
                const data = await res.json();
                if (data.ok) {{
                    showKeyModal(data.api_key);
                }}
            }} catch (err) {{
                alert("Erreur démo: " + err);
            }}
        }}

        function showKeyModal(key) {{
            document.getElementById('modalApiKey').innerText = key;
            document.getElementById('modalKeyPlaceholder').innerText = key;
            document.getElementById('playKey').value = key;
            document.getElementById('keyModal').style.display = 'flex';
        }}

        function closeModal() {{
            document.getElementById('keyModal').style.display = 'none';
        }}

        function copyKey() {{
            const keyText = document.getElementById('modalApiKey').innerText;
            navigator.clipboard.writeText(keyText);
            alert("Clé copiée dans le presse-papier !");
        }}

        async function runPlayground() {{
            const key = document.getElementById('playKey').value.trim();
            const skill = document.getElementById('playSkill').value;
            const payloadRaw = document.getElementById('playPayload').value;
            const outEl = document.getElementById('playOutput');

            if (!key) {{
                alert("Veuillez générer ou saisir une clé d'API d'abord.");
                return;
            }}

            let payload;
            try {{
                payload = JSON.parse(payloadRaw);
            }} catch (e) {{
                outEl.innerText = "Erreur: Payload JSON invalide.";
                return;
            }}

            outEl.innerText = "⌛ Exécution de la compétence sur la passerelle...";

            try {{
                const res = await fetch('/api/v1/execute', {{
                    method: 'POST',
                    headers: {{
                        'Content-Type': 'application/json',
                        'X-API-Key': key
                    }},
                    body: JSON.stringify({{ skill: skill, payload: payload }})
                }});

                const result = await res.json();
                outEl.innerText = JSON.stringify(result, null, 2);
            }} catch (err) {{
                outEl.innerText = "Erreur d'appel: " + err;
            }}
        }}
    </script>
</body>
</html>
"""
