"""OpenClawMesh Background Service & Daemon Installer.

Generates and installs background daemon scripts for:
- Linux: systemd unit service (/etc/systemd/system/openclaw-mesh.service)
- macOS: launchd property list (~/Library/LaunchAgents/com.openclaw.mesh.plist)
- Docker Compose: Multi-node cluster orchestration
"""

from __future__ import annotations

import argparse
import platform
import subprocess
import sys
from pathlib import Path


def get_default_exec_args(port: int = 8770) -> list[str]:
    root_dir = Path(__file__).resolve().parent.parent
    cli_path = root_dir / "scripts" / "mesh_cli.py"
    py_exec = sys.executable
    return [py_exec, str(cli_path), "serve", "--port", str(port), "--host", "0.0.0.0", "--wan"]


def generate_systemd_service(
    user: str = "root", port: int = 8770, exec_cmd: str | None = None
) -> str:
    if not exec_cmd:
        args = get_default_exec_args(port)
        exec_cmd = " ".join(f'"{a}"' if " " in a else a for a in args)
    return f"""[Unit]
Description=OpenClawMesh Autonomous P2P Agent Mesh & Gateway Daemon
After=network.target network-online.target
Wants=network-online.target

[Service]
Type=simple
User={user}
ExecStart={exec_cmd}
Restart=always
RestartSec=5s
LimitNOFILE=65535
Environment="PYTHONUNBUFFERED=1"
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
"""


def generate_launchd_plist(port: int = 8770, exec_args: list[str] | None = None) -> str:
    if not exec_args:
        exec_args = get_default_exec_args(port)
    args_xml = "\n        ".join(f"<string>{arg}</string>" for arg in exec_args)
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.openclaw.mesh</string>
    <key>ProgramArguments</key>
    <array>
        {args_xml}
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>StandardOutPath</key>
    <string>/tmp/openclaw_mesh.log</string>
    <key>StandardErrorPath</key>
    <string>/tmp/openclaw_mesh.err</string>
</dict>
</plist>
"""


def generate_docker_compose() -> str:
    return """version: '3.8'

services:
  openclaw-mesh-node:
    image: python:3.11-slim
    container_name: openclaw_node
    working_dir: /app
    volumes:
      - .:/app
    command: bash -c "pip install -e . && python scripts/mesh_cli.py serve --port 8770 --host 0.0.0.0 --wan"
    ports:
      - "8770:8770"
      - "8780:8780/udp"
      - "8775:8775/udp"
    restart: unless-stopped
"""


def main() -> None:
    parser = argparse.ArgumentParser(description="OpenClawMesh Service & Daemon Installer")
    parser.add_argument("--type", choices=["systemd", "launchd", "docker", "auto"], default="auto")
    parser.add_argument("--out", help="Chemin du fichier de sortie")
    parser.add_argument("--port", type=int, default=8770, help="Port d'écoute (défaut: 8770)")
    parser.add_argument("--install", action="store_true", help="Installe et active immédiatement le service au démarrage")
    args = parser.parse_args()

    os_type = platform.system().lower()
    target_type = args.type
    if target_type == "auto":
        target_type = "launchd" if "darwin" in os_type else "systemd"

    if target_type == "systemd":
        content = generate_systemd_service(port=args.port)
        out_path = Path(args.out or "/etc/systemd/system/openclaw-mesh.service")
    elif target_type == "launchd":
        content = generate_launchd_plist(port=args.port)
        out_path = Path(args.out or (Path.home() / "Library/LaunchAgents/com.openclaw.mesh.plist"))
    else:
        content = generate_docker_compose()
        out_path = Path(args.out or "docker-compose.mesh.yml")

    if args.install:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(content, encoding="utf-8")
        print(f"✅ Service enregistré dans : {out_path}")

        if target_type == "launchd":
            subprocess.run(["launchctl", "unload", str(out_path)], check=False, stderr=subprocess.DEVNULL)
            res = subprocess.run(["launchctl", "load", "-w", str(out_path)], check=False)
            if res.returncode == 0:
                print("🚀 OpenClawMesh est maintenant ACTIF en arrière-plan et démarrera tout seul à chaque allumage de la machine !")
                print("📋 Logs disponibles dans : /tmp/openclaw_mesh.log")
            else:
                print(f"⚠️ Erreur chargement launchctl ({res.returncode})")
        elif target_type == "systemd":
            subprocess.run(["systemctl", "daemon-reload"], check=False)
            res = subprocess.run(["systemctl", "enable", "--now", out_path.name], check=False)
            if res.returncode == 0:
                print("🚀 Service systemd OpenClawMesh activé avec succès au démarrage !")
            else:
                print(f"⚠️ Erreur systemctl ({res.returncode}) - vérifiez vos droits sudo.")
        return

    print(f"Generated {target_type} configuration for OpenClawMesh:")
    print("-" * 50)
    print(content)
    print("-" * 50)
    if args.out:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(content, encoding="utf-8")
        print(f"✅ Configuration écrite dans : {out_path}")


if __name__ == "__main__":
    main()
