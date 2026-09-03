#!/usr/bin/env bash
# ⚡ Installation 1-clic pour démarrer OpenClawMesh automatiquement en tâche de fond sur n'importe quelle machine
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(dirname "$SCRIPT_DIR")"
cd "$ROOT_DIR"

echo "======================================================================"
echo "⚡ Installation Automatique du Service OpenClawMesh (Zero-Touch Daemon)"
echo "======================================================================"

# Détecter l'interpréteur Python (.venv ou système)
if [ -f "$ROOT_DIR/.venv/bin/python3" ]; then
    PYTHON_EXEC="$ROOT_DIR/.venv/bin/python3"
elif [ -f "$ROOT_DIR/.venv/bin/python" ]; then
    PYTHON_EXEC="$ROOT_DIR/.venv/bin/python"
else
    PYTHON_EXEC="$(command -v python3 || command -v python)"
fi

echo "🐍 Interpréteur Python : $PYTHON_EXEC"
echo "🌐 Connexion automatique vers Freebox Guichet : http://82.67.166.90:8790"

"$PYTHON_EXEC" "$SCRIPT_DIR/service_installer.py" --install

echo "======================================================================"
echo "✓ Terminé ! La machine est maintenant autonome et connectée au maillage."
echo "======================================================================"
