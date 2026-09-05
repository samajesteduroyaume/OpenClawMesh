#!/usr/bin/env bash
# OpenClawMesh — Démarrage et Enregistrement Automatique au démarrage du système
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
bash "$SCRIPT_DIR/scripts/install_auto_daemon.sh"
