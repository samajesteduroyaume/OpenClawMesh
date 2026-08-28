#!/usr/bin/env python3
"""
CLI autonome OpenClawMesh — exécutable directement par un agent OpenClaw.
"""

import sys
from pathlib import Path

# Ajouter le répertoire racine au PYTHONPATH
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from openclaw_mesh.cli import main

if __name__ == "__main__":
    main()
