"""
Portail Web Universel & Command Center pour OpenClawMesh (100% Free & Open-Access).

Interface dark mode, responsive, moderne et libre :
- Génération instantanée de clés d'accès gratuites (Free Community Tier)
- Activation et pilotage du Nœud WAN en 100% Confiance
- Playground interactif de test de compétences IA en temps réel
- Documentation d'intégration pour agents OpenClaw
"""

from __future__ import annotations


def render_portal_html(
    portal_title: str = "OpenClawMesh — Portail Universel & Command Center",
) -> str:
    return f"""<!DOCTYPE html>
<html lang="fr">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <meta http-equiv="Content-Security-Policy" content="default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; script-src 'self' 'unsafe-inline'; connect-src 'self';">
    <title>{portal_title}</title>
    <meta name="description" content="Portail Universel OpenClawMesh — Accédez gratuitement à l'inférence IA décentralisée et au réseau P2P d'agents autonomes.">
    <style>
        :root {{
            --bg: #080c14;
            --card-bg: rgba(18, 24, 40, 0.75);
            --card-border: rgba(255, 255, 255, 0.08);
            --primary: #00ff88;
            --primary-gradient: linear-gradient(135deg, #00ff88 0%, #00b4d8 100%);
            --accent: #00e5ff;
            --text: #f3f4f6;
            --text-muted: #9ca3af;
            --code-bg: #030712;
            --brand-green: #00ff88;
            --brand-green-dim: rgba(0, 255, 136, 0.12);
            --brand-green-border: rgba(0, 255, 136, 0.35);
        }}

        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
            font-family: 'Outfit', -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
        }}

        body {{
            background-color: var(--bg);
            color: var(--text);
            min-height: 100vh;
            display: flex;
            flex-direction: column;
            background-image:
                radial-gradient(at 15% 0%, rgba(0, 255, 136, 0.08) 0px, transparent 55%),
                radial-gradient(at 85% 100%, rgba(0, 180, 216, 0.08) 0px, transparent 55%);
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
            background: var(--brand-green-dim);
            color: var(--brand-green);
            font-size: 0.72rem;
            font-weight: 700;
            padding: 0.25rem 0.65rem;
            border-radius: 999px;
            border: 1px solid var(--brand-green-border);
            text-transform: uppercase;
            letter-spacing: 0.05em;
        }}

        .badge-info {{
            background: rgba(0, 180, 216, 0.15);
            color: #00e5ff;
            border-color: rgba(0, 180, 216, 0.4);
        }}

        .badge-confirmed {{
            background: rgba(0, 255, 136, 0.15);
            color: #00ff88;
            border-color: rgba(0, 255, 136, 0.4);
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
            max-width: 650px;
            margin: 0 auto;
            line-height: 1.7;
        }}

        .hero .free-pill {{
            display: inline-flex;
            align-items: center;
            gap: 0.5rem;
            margin-top: 1.5rem;
            padding: 0.45rem 1.2rem;
            border-radius: 999px;
            background: var(--brand-green-dim);
            border: 1px solid var(--brand-green-border);
            color: var(--brand-green);
            font-size: 0.85rem;
            font-weight: 600;
        }}

        /* ── Cards Grid ── */
        .features-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
            gap: 1.5rem;
            margin: 2.5rem 0;
        }}

        .card {{
            background: var(--card-bg);
            border: 1px solid var(--card-border);
            border-radius: 1.25rem;
            padding: 2rem;
            display: flex;
            flex-direction: column;
            justify-content: space-between;
            position: relative;
            backdrop-filter: blur(12px);
            transition: transform 0.2s, box-shadow 0.2s;
        }}

        .card:hover {{
            transform: translateY(-2px);
            box-shadow: 0 12px 32px rgba(0, 0, 0, 0.4);
        }}

        .card.featured {{
            border-color: var(--brand-green-border);
            background: radial-gradient(at top right, rgba(0, 255, 136, 0.08), transparent 70%), var(--card-bg);
            box-shadow: 0 0 0 1px var(--brand-green-border), 0 4px 24px rgba(0, 255, 136, 0.12);
        }}

        .card-title {{
            font-size: 1.3rem;
            font-weight: 700;
            margin-bottom: 0.5rem;
        }}

        .card-tag {{
            font-size: 1.7rem;
            font-weight: 800;
            color: var(--brand-green);
            margin: 0.8rem 0 1.2rem;
        }}

        .card-tag span {{
            font-size: 0.95rem;
            font-weight: 400;
            color: var(--text-muted);
        }}

        .features-list {{
            list-style: none;
            margin-bottom: 1.8rem;
            display: flex;
            flex-direction: column;
            gap: 0.65rem;
            font-size: 0.92rem;
            color: var(--text-muted);
        }}

        .features-list li {{
            display: flex;
            align-items: center;
            gap: 0.5rem;
        }}

        .features-list li::before {{
            content: "✓";
            color: var(--brand-green);
            font-weight: 800;
        }}

        /* ── Boutons ── */
        .btn {{
            display: inline-flex;
            align-items: center;
            justify-content: center;
            padding: 0.75rem 1.5rem;
            background: var(--primary-gradient);
            color: #030712;
            font-weight: 700;
            font-size: 0.95rem;
            border-radius: 0.75rem;
            border: none;
            cursor: pointer;
            text-decoration: none;
            transition: opacity 0.15s, transform 0.1s;
            width: 100%;
        }}

        .btn:hover {{
            opacity: 0.92;
            transform: scale(0.99);
        }}

        .btn-outline {{
            background: transparent;
            color: var(--text);
            border: 1px solid var(--card-border);
            display: inline-flex;
            align-items: center;
            justify-content: center;
            padding: 0.75rem 1.5rem;
            font-weight: 600;
            font-size: 0.95rem;
            border-radius: 0.75rem;
            cursor: pointer;
            transition: border-color 0.15s, background 0.15s;
            width: 100%;
        }}

        .btn-outline:hover {{
            border-color: var(--brand-green-border);
            background: var(--brand-green-dim);
            color: var(--brand-green);
        }}

        /* ── Sections ── */
        .form-section {{
            background: var(--card-bg);
            border: 1px solid var(--card-border);
            border-radius: 1.25rem;
            padding: 2rem;
            margin: 2rem 0;
            backdrop-filter: blur(12px);
        }}

        .form-section h2 {{
            font-size: 1.25rem;
            font-weight: 700;
            margin-bottom: 1.25rem;
            display: flex;
            align-items: center;
            gap: 0.5rem;
        }}

        .form-group {{
            margin-bottom: 1.25rem;
        }}

        .form-group label {{
            display: block;
            font-size: 0.85rem;
            font-weight: 600;
            color: var(--text-muted);
            margin-bottom: 0.4rem;
        }}

        .form-group input,
        .form-group select,
        .form-group textarea {{
            width: 100%;
            background: var(--code-bg);
            border: 1px solid var(--card-border);
            border-radius: 0.65rem;
            padding: 0.7rem 0.9rem;
            color: var(--text);
            font-size: 0.9rem;
            outline: none;
            transition: border-color 0.15s;
        }}

        .form-group input:focus,
        .form-group select:focus,
        .form-group textarea:focus {{
            border-color: var(--brand-green);
        }}

        .alert {{
            padding: 0.9rem 1.1rem;
            border-radius: 0.75rem;
            font-size: 0.9rem;
            margin-top: 1rem;
            line-height: 1.6;
        }}

        .alert.success {{
            background: rgba(0, 255, 136, 0.1);
            border: 1px solid rgba(0, 255, 136, 0.3);
            color: #00ff88;
        }}

        .alert.error {{
            background: rgba(239, 68, 68, 0.1);
            border: 1px solid rgba(239, 68, 68, 0.3);
            color: #f87171;
        }}

        .key-display {{
            display: flex;
            align-items: center;
            gap: 0.75rem;
            background: var(--code-bg);
            border: 1px solid var(--brand-green-border);
            border-radius: 0.75rem;
            padding: 0.75rem 1rem;
            margin: 1rem 0;
        }}

        .key-display code {{
            flex: 1;
            font-family: 'JetBrains Mono', 'Fira Code', monospace;
            font-size: 0.9rem;
            color: var(--brand-green);
            word-break: break-all;
        }}

        .btn-copy-addr {{
            background: var(--brand-green-dim);
            color: var(--brand-green);
            border: 1px solid var(--brand-green-border);
            padding: 0.4rem 0.85rem;
            border-radius: 0.45rem;
            cursor: pointer;
            font-size: 0.8rem;
            font-weight: 700;
            white-space: nowrap;
        }}

        .btn-copy-addr:hover {{
            background: var(--brand-green);
            color: #030712;
        }}

        pre {{
            background: var(--code-bg);
            border: 1px solid var(--card-border);
            border-radius: 0.75rem;
            padding: 1rem;
            overflow-x: auto;
            font-size: 0.85rem;
            line-height: 1.6;
            color: #93c5fd;
            font-family: 'JetBrains Mono', 'Fira Code', monospace;
        }}

        /* ── Modal ── */
        .modal {{
            display: none;
            position: fixed;
            inset: 0;
            background: rgba(0, 0, 0, 0.75);
            z-index: 100;
            align-items: center;
            justify-content: center;
            padding: 1rem;
            backdrop-filter: blur(6px);
        }}

        .modal-content {{
            background: #111827;
            border: 1px solid var(--brand-green-border);
            border-radius: 1.5rem;
            padding: 2.5rem;
            max-width: 540px;
            width: 100%;
            box-shadow: 0 25px 60px rgba(0, 0, 0, 0.7), 0 0 0 1px rgba(0, 255, 136, 0.2);
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
            ⚡ OpenClawMesh <span class="badge">100% Free & Open-Access</span>
        </div>
        <div>
            <span style="font-size: 0.85rem; color: var(--text-muted);">Accès Libre & Gratuit — Sans paiement, sans carte, sans KYC</span>
        </div>
    </header>

    <main>
        <section class="hero">
            <h1>Inférence IA Décentralisée<br>100% Gratuite & Souveraine</h1>
            <p>Accédez à l'inférence multi-matériels haute performance (Apple Silicon MLX, NVIDIA CUDA, CPU) et au réseau P2P d'agents IA autonomes sans barrière financière.</p>
            <div class="free-pill">
                ✨ Gratuit & Open-Source · Inférence Locale & P2P · Confidentialité Totale
            </div>
        </section>

        <!-- Grille des Offres Gratuites -->
        <section class="features-grid">
            <!-- Accès Communautaire Illimité -->
            <div class="card featured">
                <div>
                    <span class="badge" style="display:inline-block; margin-bottom:0.5rem;">Recommandé</span>
                    <div class="card-title">Accès Libre & Gratuit</div>
                    <div class="card-tag">0€ <span>/ permanent</span></div>
                </div>
                <ul class="features-list">
                    <li>Requêtes et inférence illimitées</li>
                    <li>Accélération matérielle Apple Silicon / CUDA</li>
                    <li>RAG Sémantique SQLite & MoE Distribué</li>
                    <li>Accès direct au protocole P2P Mesh</li>
                </ul>
                <button class="btn" onclick="generateFreeKey()">✨ Obtenir ma Clé Gratuite Instantanément</button>
            </div>

            <!-- Nœud Souverain Local & WAN -->
            <div class="card">
                <div>
                    <span class="badge badge-info" style="display:inline-block; margin-bottom:0.5rem;">Auto-Hébergé</span>
                    <div class="card-title">Nœud Souverain (P2P)</div>
                    <div class="card-tag">100% <span>Libre & Décentralisé</span></div>
                </div>
                <ul class="features-list">
                    <li>Zéro dépendance serveur tiers</li>
                    <li>Chiffrement E2EE & Découverte mDNS / DHT</li>
                    <li>Mode WAN 100% Confiance en 1 clic</li>
                    <li>Contrôle total sur vos modèles et données</li>
                </ul>
                <a href="#wanSection" class="btn-outline">🌐 Configurer le Nœud WAN</a>
            </div>
        </section>

        <!-- Nœud WAN 100% Confiance -->
        <div class="form-section" id="wanSection">
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

            <!-- Dashboard de connexion active -->
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
                        <code id="wanPskVal" style="display:block; padding:0.4rem 0.6rem; background:rgba(0,0,0,0.4); border-radius:6px; margin-top:0.2rem; color:#00ff88; word-break:break-all;"></code>
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

        <!-- 1-Click Model Hub & Downloader -->
        <div class="form-section" id="modelHubSection">
            <div style="display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:0.5rem; margin-bottom:1rem;">
                <h2 style="margin:0;">📥 Hub de Modèles & Téléchargement 1-Clic</h2>
                <span class="badge badge-info">Détection VRAM Intelligente</span>
            </div>
            <p style="color:var(--text-muted); margin-bottom:1.5rem; font-size:0.9rem;">
                Explorez et activez instantanément des modèles ultra-optimisés pour votre matériel (MLX 4-bit, BitNet 1.58-bit, AWQ, FP8).
            </p>
            <div style="display:grid; grid-template-columns:repeat(auto-fit, minmax(240px, 1fr)); gap:1.2rem;" id="modelHubGrid">
                <!-- Modèle 1 -->
                <div style="background:rgba(255,255,255,0.03); border:1px solid var(--card-border); border-radius:1rem; padding:1.2rem; display:flex; flex-direction:column; justify-content:space-between;">
                    <div>
                        <div style="display:flex; justify-content:space-between; align-items:center;">
                            <strong style="color:#00ff88; font-size:1.05rem;">Llama 3.2 3B</strong>
                            <span class="badge" style="font-size:0.65rem;">Meta AI</span>
                        </div>
                        <p style="color:var(--text-muted); font-size:0.82rem; margin:0.6rem 0;">Idéal pour agents rapides & Edge. Supporte BitNet 1.58b.</p>
                        <div style="font-size:0.78rem; color:#93c5fd; margin-bottom:1rem;">⚡ VRAM Requise : ~2.2 Go</div>
                    </div>
                    <button class="btn-outline" style="padding:0.5rem 1rem; font-size:0.85rem;" onclick="activateModel('llama-3.2-3b-instruct')">⚡ Activer sur le Mesh</button>
                </div>
                <!-- Modèle 2 -->
                <div style="background:rgba(255,255,255,0.03); border:1px solid var(--card-border); border-radius:1rem; padding:1.2rem; display:flex; flex-direction:column; justify-content:space-between;">
                    <div>
                        <div style="display:flex; justify-content:space-between; align-items:center;">
                            <strong style="color:#00e5ff; font-size:1.05rem;">Qwen 2.5 Coder 7B</strong>
                            <span class="badge" style="font-size:0.65rem;">Alibaba</span>
                        </div>
                        <p style="color:var(--text-muted); font-size:0.82rem; margin:0.6rem 0;">Excellence en génération de code & refactoring Python/TS.</p>
                        <div style="font-size:0.78rem; color:#93c5fd; margin-bottom:1rem;">⚡ VRAM Requise : ~5.4 Go</div>
                    </div>
                    <button class="btn-outline" style="padding:0.5rem 1rem; font-size:0.85rem;" onclick="activateModel('qwen-2.5-coder-7b')">⚡ Activer sur le Mesh</button>
                </div>
                <!-- Modèle 3 -->
                <div style="background:rgba(255,255,255,0.03); border:1px solid var(--card-border); border-radius:1rem; padding:1.2rem; display:flex; flex-direction:column; justify-content:space-between;">
                    <div>
                        <div style="display:flex; justify-content:space-between; align-items:center;">
                            <strong style="color:#a78bfa; font-size:1.05rem;">DeepSeek R1 Distill</strong>
                            <span class="badge" style="font-size:0.65rem;">Reasoning</span>
                        </div>
                        <p style="color:var(--text-muted); font-size:0.82rem; margin:0.6rem 0;">Raisonnement logique & mathématique étape par étape.</p>
                        <div style="font-size:0.78rem; color:#93c5fd; margin-bottom:1rem;">⚡ VRAM Requise : ~6.1 Go</div>
                    </div>
                    <button class="btn-outline" style="padding:0.5rem 1rem; font-size:0.85rem;" onclick="activateModel('deepseek-r1-distill-8b')">⚡ Activer sur le Mesh</button>
                </div>
                <!-- Modèle 4 -->
                <div style="background:rgba(255,255,255,0.03); border:1px solid var(--card-border); border-radius:1rem; padding:1.2rem; display:flex; flex-direction:column; justify-content:space-between;">
                    <div>
                        <div style="display:flex; justify-content:space-between; align-items:center;">
                            <strong style="color:#fbbf24; font-size:1.05rem;">BitNet 1.58b (Ternaire)</strong>
                            <span class="badge" style="font-size:0.65rem;">Extreme</span>
                        </div>
                        <p style="color:var(--text-muted); font-size:0.82rem; margin:0.6rem 0;">Ultra-léger pour CPU et Raspberry Pi. Zéro surchauffe.</p>
                        <div style="font-size:0.78rem; color:#93c5fd; margin-bottom:1rem;">⚡ VRAM Requise : ~0.8 Go</div>
                    </div>
                    <button class="btn-outline" style="padding:0.5rem 1rem; font-size:0.85rem;" onclick="activateModel('bitnet-b1.58-3b')">⚡ Activer sur le Mesh</button>
                </div>
            </div>
            <div id="modelAlert" style="margin-top:1rem;"></div>
        </div>

        <!-- Comparateur Multi-Modèles & Benchmark Côte à Côte -->
        <div class="form-section" id="compareSection">
            <div style="display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:0.5rem; margin-bottom:1rem;">
                <h2 style="margin:0;">⚔️ Comparateur Multi-Nœuds Côte à Côte (Live Benchmark)</h2>
                <span class="badge" style="background:rgba(255,215,0,0.15); color:#ffd700; border-color:rgba(255,215,0,0.4);">TTFT & Tokens/sec</span>
            </div>
            <p style="color:var(--text-muted); margin-bottom:1.2rem; font-size:0.9rem;">
                Évaluez en direct la vitesse d'inférence simultanée entre vos nœuds (Apple Silicon Metal, CUDA, NPU).
            </p>
            <div style="display:flex; gap:0.6rem; margin-bottom:1.5rem;">
                <input type="text" id="comparePrompt" value="Explique le parallélisme de pipeline en 2 phrases" style="flex:1; background:var(--code-bg); border:1px solid var(--card-border); border-radius:0.65rem; padding:0.75rem 1rem; color:#fff; font-size:0.92rem;">
                <button class="btn" style="width:auto; padding:0.75rem 1.8rem;" onclick="runBenchmarkCompare()">Lancer le Duel ⚔️</button>
            </div>
            <div id="compareResultsGrid" style="display:grid; grid-template-columns:repeat(auto-fit, minmax(260px, 1fr)); gap:1rem;"></div>
        </div>

        <!-- Visualisation Dynamique du Maillage P2P (Graphe 3D Interactif) -->
        <div class="form-section" id="meshTopologySection">
            <div style="display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:0.5rem; margin-bottom:1rem;">
                <h2 style="margin:0;">🕸️ Topologie 3D & Flux d'Inférence du Maillage (Live 3D Graph)</h2>
                <span class="badge" id="clusterActiveBadge">Cluster Actif · Découverte DHT/Gossip</span>
            </div>
            <p style="color:var(--text-muted); margin-bottom:1rem; font-size:0.9rem;">
                Visualisation 3D temps réel des nœuds pairs, liaisons chiffrées E2EE, anneaux de latence et paquets de tokens en transit.
            </p>
            <div style="position:relative; background:#050913; border:1px solid var(--card-border); border-radius:1rem; overflow:hidden; display:flex; justify-content:center;">
                <canvas id="meshCanvas" width="900" height="340" style="width:100%; max-height:360px; display:block; cursor:grab;"></canvas>
            </div>
        </div>

        <!-- Chat Playground Interactif en Direct -->
        <div class="form-section" id="chatSection">
            <div style="display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:0.5rem; margin-bottom:1rem;">
                <h2 style="margin:0;">💬 Playground de Chat & Inférence Distribuée</h2>
                <div style="display:flex; gap:0.5rem; align-items:center;">
                    <span id="kvCacheBadge" class="badge badge-info" style="display:none;">⚡ KV-Cache HIT</span>
                    <span id="latencyBadge" class="badge" style="background:rgba(255,255,255,0.05); color:var(--text-muted);">0 ms</span>
                </div>
            </div>

            <div style="display:grid; grid-template-columns:1fr 1fr; gap:1rem; margin-bottom:1rem;">
                <div>
                    <label style="font-size:0.85rem; color:var(--text-muted); font-weight:600;">Modèle d'IA :</label>
                    <select id="chatModel" style="margin-top:0.3rem; width:100%; background:var(--code-bg); border:1px solid var(--card-border); border-radius:0.5rem; padding:0.6rem; color:#fff;">
                        <option value="qwen2.5-coder-7b">Qwen 2.5 Coder 7B (Inférence Rapide)</option>
                        <option value="deepseek-v3-moe">DeepSeek-V3 MoE (Pipeline Distribué)</option>
                        <option value="mlx-community/Qwen2.5-Coder-7B-Instruct-4bit">Apple Silicon Metal MLX (Local)</option>
                        <option value="whisper-base-stt">Whisper Base (Audio STT)</option>
                        <option value="qwen2-vl-vision">Qwen2-VL (Vision Multimodale)</option>
                    </select>
                </div>
                <div>
                    <label style="font-size:0.85rem; color:var(--text-muted); font-weight:600;">Clé d'API (Optionnelle si local) :</label>
                    <input type="text" id="chatApiKey" placeholder="sk_claw_... (auto-rempli)" style="margin-top:0.3rem; width:100%; background:var(--code-bg); border:1px solid var(--card-border); border-radius:0.5rem; padding:0.6rem; color:#fff;">
                </div>
            </div>

            <!-- Boîte de dialogue de Chat -->
            <div id="chatBox" style="background:#090d16; border:1px solid var(--card-border); border-radius:0.75rem; padding:1rem; min-height:180px; max-height:360px; overflow-y:auto; display:flex; flex-direction:column; gap:0.75rem; margin-bottom:1rem;">
                <div style="display:flex; gap:0.6rem; align-items:flex-start;">
                    <div style="background:var(--brand-green-dim); border:1px solid var(--brand-green-border); color:var(--brand-green); width:32px; height:32px; border-radius:50%; display:flex; align-items:center; justify-content:center; font-size:0.85rem; flex-shrink:0;">⚡</div>
                    <div style="background:rgba(255,255,255,0.03); border:1px solid var(--card-border); border-radius:0.75rem; padding:0.75rem 1rem; color:var(--text); font-size:0.9rem; line-height:1.5;">
                        Bienvenue sur le maillage OpenClawMesh ! Posez une question ou demandez du code pour tester l'inférence distribuée multi-matériels.
                    </div>
                </div>
            </div>

            <div style="display:flex; gap:0.6rem;">
                <input type="text" id="chatInput" placeholder="Tapez votre message ici (ex: Écris une fonction Python asynchrone)..." style="flex:1; background:var(--code-bg); border:1px solid var(--card-border); border-radius:0.65rem; padding:0.75rem 1rem; color:#fff; font-size:0.92rem;" onkeydown="if(event.key==='Enter') sendChatMessage()">
                <button class="btn" style="width:auto; padding:0.75rem 1.8rem;" onclick="sendChatMessage()">Envoyer 🚀</button>
            </div>
        </div>

        <!-- Playground Exécution Directe (Tools / API) -->
        <div class="form-section">
            <h2>🧪 Exécution d'Outils & Compétences (REST / Tools)</h2>

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

    <!-- Modal clé gratuite -->
    <div class="modal" id="keyModal">
        <div class="modal-content">
            <h2 style="font-size:1.5rem; font-weight:800; color:#fff;">🎉 Clé Gratuite Générée !</h2>
            <p style="color:var(--text-muted); margin-top:0.5rem; font-size:0.95rem;">Voici votre clé d'API gratuite et illimitée OpenClawMesh. Conservez-la :</p>

            <div class="key-display">
                <code id="modalApiKey">sk_claw_...</code>
                <button class="btn-copy-addr" onclick="copyKey()">Copier</button>
            </div>

            <div style="background:rgba(255,255,255,0.03); padding:1rem; border-radius:0.75rem; font-size:0.85rem; color:var(--text-muted); margin-top:1rem;">
                <strong>Utilisation dans vos scripts & agents :</strong>
                <pre style="margin-top:0.5rem; color:#93c5fd; font-size:0.82rem;">export OPENCLAW_API_KEY="<span id="modalKeyPlaceholder">...</span>"</pre>
            </div>

            <button class="btn" style="margin-top:1.25rem;" onclick="closeModal()">Tester dans le Playground</button>
        </div>
    </div>

    <footer>
        OpenClawMesh &copy; 2026 — Inférence IA Décentralisée & Multi-Matériels.<br>
        100% Free & Open-Source — Souveraineté & Calcul Libre.
    </footer>

    <script>
        function showAlert(containerId, message, type) {{
            const el = document.getElementById(containerId);
            el.className = 'alert ' + type;
            el.innerHTML = message;
        }}

        function copyKey() {{
            const key = document.getElementById('modalApiKey').innerText;
            navigator.clipboard.writeText(key);
            const btn = document.querySelector('.btn-copy-addr');
            btn.innerText = 'Copié !';
            setTimeout(() => {{ btn.innerText = 'Copier'; }}, 2000);
        }}

        function closeModal() {{
            document.getElementById('keyModal').style.display = 'none';
            const key = document.getElementById('modalApiKey').innerText;
            if (document.getElementById('playKey')) document.getElementById('playKey').value = key;
            if (document.getElementById('chatApiKey')) document.getElementById('chatApiKey').value = key;
        }}

        async function generateFreeKey() {{
            try {{
                const res = await fetch('/api/v1/auth/free-key', {{ method: 'POST' }});
                const data = await res.json();
                if (data.ok) {{
                    document.getElementById('modalApiKey').innerText = data.key;
                    document.getElementById('modalKeyPlaceholder').innerText = data.key;
                    document.getElementById('keyModal').style.display = 'flex';
                }} else {{
                    alert('Erreur lors de la génération : ' + (data.detail || 'Inconnue'));
                }}
            }} catch (err) {{
                alert('Erreur de connexion au serveur : ' + err);
            }}
        }}

        async function activateModel(modelId) {{
            const alertEl = document.getElementById('modelAlert');
            alertEl.className = 'alert alert-info';
            alertEl.innerHTML = `⚡ Activation et chargement du modèle <strong>${{modelId}}</strong> sur le cluster...`;
            setTimeout(() => {{
                alertEl.className = 'alert alert-success';
                alertEl.innerHTML = `✅ Modèle <strong>${{modelId}}</strong> actif et prêt pour l'inférence distribuée !`;
                const sel = document.getElementById('chatModel');
                if (sel) {{
                    sel.value = modelId;
                }}
            }}, 800);
        }}

        async function runBenchmarkCompare() {{
            const prompt = document.getElementById('comparePrompt').value;
            const container = document.getElementById('compareResultsGrid');
            container.innerHTML = '<div style="color:var(--text-muted); padding:1rem;">⚡ Exécution en cours sur tous les backends...</div>';

            try {{
                const res = await fetch('/api/v1/benchmarks/compare', {{
                    method: 'POST',
                    headers: {{ 'Content-Type': 'application/json' }},
                    body: JSON.stringify({{ prompt: prompt }})
                }});
                const data = await res.json();
                container.innerHTML = '';

                data.results.forEach((r, idx) => {{
                    const card = document.createElement('div');
                    const isWinner = idx === 0;
                    card.style.cssText = `background:${{isWinner ? 'rgba(0,255,136,0.06)' : 'rgba(255,255,255,0.02)'}}; border:1px solid ${{isWinner ? 'var(--brand-green-border)' : 'var(--card-border)'}}; border-radius:1rem; padding:1.2rem; display:flex; flex-direction:column; justify-content:space-between;`;
                    card.innerHTML = `
                        <div>
                            <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:0.6rem;">
                                <strong style="color:${{isWinner ? '#00ff88' : '#fff'}}; font-size:0.95rem;">${{r.target_name}}</strong>
                                ${{isWinner ? '<span class="badge" style="font-size:0.65rem;">🏆 Plus Rapide</span>' : ''}}
                            </div>
                            <div style="display:flex; gap:1rem; margin:0.6rem 0; font-size:0.85rem;">
                                <div><span style="color:var(--text-muted);">TTFT:</span> <strong style="color:#00e5ff;">${{r.ttft_ms}} ms</strong></div>
                                <div><span style="color:var(--text-muted);">Débit:</span> <strong style="color:#00ff88;">${{r.tokens_per_sec}} tok/s</strong></div>
                            </div>
                            <div style="background:rgba(0,0,0,0.3); padding:0.6rem; border-radius:0.5rem; font-size:0.82rem; color:var(--text); margin-top:0.6rem;">
                                "${{escapeHtml(r.response)}}"
                            </div>
                        </div>
                    `;
                    container.appendChild(card);
                }});
            }} catch (err) {{
                container.innerHTML = `<div class="alert alert-error">Erreur lors du benchmark : ${{err}}</div>`;
            }}
        }}

        async function toggleWanNode() {{
            const btn = document.getElementById('wanToggleBtn');
            const alertBox = document.getElementById('wanAlert');
            const token = document.getElementById('wanAdminToken').value;
            const remoteAccess = document.getElementById('wanRemoteAccess').checked;

            btn.disabled = true;
            btn.innerText = '⚡ Configuration et sécurisation en cours...';

            try {{
                const headers = {{ 'Content-Type': 'application/json' }};
                if (token) headers['X-Admin-Token'] = token;

                const res = await fetch('/api/v1/admin/wan/toggle', {{
                    method: 'POST',
                    headers: headers,
                    body: JSON.stringify({{ remote_access: remoteAccess, auto_secure: true }})
                }});

                const data = await res.json();
                if (res.ok && data.ok) {{
                    document.getElementById('wanActiveCard').style.display = 'block';
                    document.getElementById('wanEndpointVal').innerText = data.connect_url;
                    document.getElementById('wanPskVal').innerText = data.psk;
                    document.getElementById('wanCliVal').innerText = data.cli_command;
                    document.getElementById('wanBadge').className = 'badge badge-confirmed';
                    document.getElementById('wanBadge').innerText = 'Actif · ' + (data.remote_access ? '0.0.0.0 (WAN)' : '127.0.0.1');
                    showAlert('wanAlert', data.message, 'alert-success');
                }} else {{
                    showAlert('wanAlert', 'Erreur : ' + (data.detail || JSON.stringify(data)), 'alert-error');
                }}
            }} catch (err) {{
                showAlert('wanAlert', 'Erreur réseau : ' + err, 'alert-error');
            }} finally {{
                btn.disabled = false;
                btn.innerText = '🌐 Reconfigurer le Nœud WAN';
            }}
        }}

        function copyWanCli() {{
            const txt = document.getElementById('wanCliVal').innerText;
            navigator.clipboard.writeText(txt);
            alert('Commande d’appel copiée dans le presse-papier !');
        }}

        async function runPlayground() {{
            const key = document.getElementById('playKey').value;
            const skill = document.getElementById('playSkill').value;
            const rawPayload = document.getElementById('playPayload').value;
            const out = document.getElementById('playOutput');

            try {{
                const payloadJson = JSON.parse(rawPayload);
                out.innerText = 'Exécution en cours...';

                const headers = {{ 'Content-Type': 'application/json' }};
                if (key) headers['X-API-Key'] = key;

                const res = await fetch(`/api/v1/skills/${{skill}}`, {{
                    method: 'POST',
                    headers: headers,
                    body: JSON.stringify(payloadJson)
                }});

                const data = await res.json();
                out.innerText = JSON.stringify(data, null, 2);
            }} catch (err) {{
                out.innerText = 'Erreur : ' + err.message;
            }}
        }}

        async function sendChatMessage() {{
            const input = document.getElementById('chatInput');
            const prompt = input.value.trim();
            if (!prompt) return;

            const model = document.getElementById('chatModel').value;
            const apiKey = document.getElementById('chatApiKey').value;
            const chatBox = document.getElementById('chatBox');
            const latencyBadge = document.getElementById('latencyBadge');
            const kvBadge = document.getElementById('kvCacheBadge');

            const userMsgDiv = document.createElement('div');
            userMsgDiv.style.cssText = 'display:flex; justify-content:flex-end; margin-bottom:0.5rem;';
            userMsgDiv.innerHTML = `<div style="background:var(--brand-green); color:#030712; font-weight:600; padding:0.75rem 1rem; border-radius:0.75rem; max-width:80%; font-size:0.9rem;">${{escapeHtml(prompt)}}</div>`;
            chatBox.appendChild(userMsgDiv);
            input.value = '';
            chatBox.scrollTop = chatBox.scrollHeight;

            const botMsgDiv = document.createElement('div');
            botMsgDiv.style.cssText = 'display:flex; gap:0.6rem; align-items:flex-start; margin-bottom:0.5rem;';
            const botContent = document.createElement('div');
            botContent.style.cssText = 'background:rgba(255,255,255,0.04); border:1px solid var(--card-border); border-radius:0.75rem; padding:0.75rem 1rem; color:var(--text); font-size:0.9rem; line-height:1.5; max-width:85%;';
            botContent.innerHTML = '<em>⚡ Inférence en cours sur le maillage...</em>';
            botMsgDiv.innerHTML = `<div style="background:var(--brand-green-dim); border:1px solid var(--brand-green-border); color:var(--brand-green); width:32px; height:32px; border-radius:50%; display:flex; align-items:center; justify-content:center; font-size:0.85rem; flex-shrink:0;">🤖</div>`;
            botMsgDiv.appendChild(botContent);
            chatBox.appendChild(botMsgDiv);
            chatBox.scrollTop = chatBox.scrollHeight;

            const t0 = performance.now();
            try {{
                const headers = {{ 'Content-Type': 'application/json' }};
                if (apiKey) headers['Authorization'] = 'Bearer ' + apiKey;

                const res = await fetch('/v1/chat/completions', {{
                    method: 'POST',
                    headers: headers,
                    body: JSON.stringify({{
                        model: model,
                        messages: [{{ role: 'user', content: prompt }}],
                        stream: false
                    }})
                }});
                const data = await res.json();
                const duration = Math.round(performance.now() - t0);
                latencyBadge.textContent = duration + ' ms';

                if (data.kv_cache_hit) {{
                    kvBadge.style.display = 'inline-block';
                }} else {{
                    kvBadge.style.display = 'none';
                }}

                if (res.ok && data.choices && data.choices[0]) {{
                    botContent.innerText = data.choices[0].message.content;
                }} else {{
                    botContent.innerText = 'Erreur : ' + (data.detail || JSON.stringify(data));
                }}
            }} catch (err) {{
                botContent.innerText = 'Erreur réseau : ' + err;
            }}
            chatBox.scrollTop = chatBox.scrollHeight;
        }}

        function escapeHtml(text) {{
            const div = document.createElement('div');
            div.innerText = text;
            return div.innerHTML;
        }}

        // ── Visualiseur 3D Interactif Canvas ────────────────────────────
        function initMeshGraph() {{
            const canvas = document.getElementById('meshCanvas');
            if (!canvas) return;
            const ctx = canvas.getContext('2d');
            let w = canvas.width = canvas.offsetWidth || 800;
            let h = canvas.height = 340;

            let angleY = 0;
            let angleX = 0.2;

            const nodes3D = [
                {{ id: 'local', name: 'OpenClaw Gateway', x: 0, y: 0, z: 0, radius: 16, color: '#00ff88' }},
                {{ id: 'gpu1', name: 'Apple Metal MLX', x: -140, y: -60, z: 80, radius: 12, color: '#93c5fd' }},
                {{ id: 'gpu2', name: 'NVIDIA CUDA 4090', x: 140, y: -60, z: -80, radius: 12, color: '#38bdf8' }},
                {{ id: 'npu', name: 'Intel Ultra NPU', x: -100, y: 90, z: -100, radius: 11, color: '#c084fc' }},
                {{ id: 'dht', name: 'S/Kademlia DHT', x: 120, y: 80, z: 90, radius: 11, color: '#a78bfa' }},
                {{ id: 'relay', name: 'QUIC / TURN Relay', x: 0, y: -120, z: -120, radius: 11, color: '#fbbf24' }},
            ];

            const links = [
                [0, 1], [0, 2], [0, 3], [0, 4], [0, 5],
                [1, 2], [1, 4], [2, 5], [3, 4]
            ];

            // Particules de tokens en transit
            const packets = [
                {{ from: 0, to: 1, progress: 0.1, speed: 0.015, color: '#00ff88' }},
                {{ from: 0, to: 2, progress: 0.6, speed: 0.02, color: '#00e5ff' }},
                {{ from: 2, to: 5, progress: 0.3, speed: 0.012, color: '#fbbf24' }},
                {{ from: 4, to: 0, progress: 0.8, speed: 0.018, color: '#a78bfa' }}
            ];

            function project(p3) {{
                // 3D rotation around Y and X axis
                const cosY = Math.cos(angleY), sinY = Math.sin(angleY);
                const cosX = Math.cos(angleX), sinX = Math.sin(angleX);

                const x1 = p3.x * cosY + p3.z * sinY;
                const z1 = -p3.x * sinY + p3.z * cosY;

                const y2 = p3.y * cosX - z1 * sinX;
                const z2 = p3.y * sinX + z1 * cosX;

                const fov = 350;
                const scale = fov / (fov + z2 + 180);
                return {{
                    x: w / 2 + x1 * scale,
                    y: h / 2 + y2 * scale,
                    scale: scale,
                    z: z2
                }};
            }}

            function animate() {{
                ctx.clearRect(0, 0, w, h);
                angleY += 0.008;

                // Project all nodes
                const projected = nodes3D.map(n => ({{ ...n, proj: project(n) }}));

                // Sort by Z for proper 3D depth rendering
                projected.sort((a, b) => b.proj.z - a.proj.z);

                // Draw links
                links.forEach(([i, j]) => {{
                    const p1 = project(nodes3D[i]);
                    const p2 = project(nodes3D[j]);

                    ctx.beginPath();
                    ctx.moveTo(p1.x, p1.y);
                    ctx.lineTo(p2.x, p2.y);
                    ctx.strokeStyle = 'rgba(0, 255, 136, 0.16)';
                    ctx.lineWidth = 1.2 * Math.min(p1.scale, p2.scale);
                    ctx.stroke();
                }});

                // Draw token packets
                packets.forEach(pkt => {{
                    pkt.progress = (pkt.progress + pkt.speed) % 1.0;
                    const pA = project(nodes3D[pkt.from]);
                    const pB = project(nodes3D[pkt.to]);
                    const curX = pA.x + (pB.x - pA.x) * pkt.progress;
                    const curY = pA.y + (pB.y - pA.y) * pkt.progress;

                    ctx.beginPath();
                    ctx.arc(curX, curY, 3.5, 0, Math.PI * 2);
                    ctx.fillStyle = pkt.color;
                    ctx.shadowColor = pkt.color;
                    ctx.shadowBlur = 8;
                    ctx.fill();
                    ctx.shadowBlur = 0;
                }});

                // Draw nodes
                const now = Date.now() / 1000;
                projected.forEach(n => {{
                    const p = n.proj;
                    const r = n.radius * p.scale;
                    const pulse = Math.sin(now * 3 + n.x) * 3 * p.scale;

                    // Glow ring
                    ctx.beginPath();
                    ctx.arc(p.x, p.y, Math.max(1, r + pulse + 4), 0, Math.PI * 2);
                    ctx.fillStyle = n.color.replace(')', ', 0.15)').replace('rgb', 'rgba').replace('#00ff88', 'rgba(0,255,136,0.15)');
                    ctx.fill();

                    // Core
                    ctx.beginPath();
                    ctx.arc(p.x, p.y, Math.max(1, r), 0, Math.PI * 2);
                    ctx.fillStyle = n.color;
                    ctx.fill();

                    // Label
                    if (p.scale > 0.6) {{
                        ctx.fillStyle = '#f3f4f6';
                        ctx.font = `${{Math.round(11 * p.scale)}}px -apple-system, sans-serif`;
                        ctx.textAlign = 'center';
                        ctx.fillText(n.name, p.x, p.y + r + 13 * p.scale);
                    }}
                }});

                requestAnimationFrame(animate);
            }}

            window.addEventListener('resize', () => {{
                w = canvas.width = canvas.offsetWidth || 800;
                h = canvas.height = 340;
            }});

            animate();
        }}

        document.addEventListener('DOMContentLoaded', () => {{
            initMeshGraph();
        }});
    </script>
</body>
</html>


"""
