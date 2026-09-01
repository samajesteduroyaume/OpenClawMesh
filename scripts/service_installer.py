"""OpenClawMesh Background Service & Daemon Installer.

Generates and installs background daemon scripts for:
- Linux: systemd unit service (/etc/systemd/system/openclaw-mesh.service)
- macOS: launchd property list (~/Library/LaunchAgents/com.openclaw.mesh.plist)
- Docker Compose: Multi-node cluster orchestration
"""

from __future__ import annotations

import argparse
import platform
from pathlib import Path


def generate_systemd_service(
    user: str = "root", port: int = 8000, bin_path: str = "/usr/local/bin/openclaw-mesh"
) -> str:
    return f"""[Unit]
Description=OpenClawMesh Autonomous P2P Agent Mesh & Gateway Daemon
After=network.target network-online.target
Wants=network-online.target

[Service]
Type=simple
User={user}
ExecStart={bin_path} serve --port {port} --host 0.0.0.0 --wan
Restart=always
RestartSec=5s
LimitNOFILE=65535
Environment="PYTHONUNBUFFERED=1"
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
"""


def generate_launchd_plist(bin_path: str = "/usr/local/bin/openclaw-mesh", port: int = 8000) -> str:
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.openclaw.mesh</string>
    <key>ProgramArguments</key>
    <array>
        <string>{bin_path}</string>
        <string>serve</string>
        <string>--port</string>
        <string>{port}</string>
        <string>--host</string>
        <string>0.0.0.0</string>
        <string>--wan</string>
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
  openclaw-gateway:
    image: python:3.11-slim
    container_name: openclaw_gateway
    working_dir: /app
    volumes:
      - .:/app
    command: bash -c "pip install -e . && uvicorn openclaw_mesh.gateway.server:app --host 0.0.0.0 --port 8000"
    ports:
      - "8000:8000"
    restart: unless-stopped

  openclaw-mesh-node-1:
    image: python:3.11-slim
    container_name: openclaw_node_1
    working_dir: /app
    volumes:
      - .:/app
    command: bash -c "pip install -e . && openclaw-mesh serve --port 8770 --host 0.0.0.0 --wan"
    ports:
      - "8770:8770"
    restart: unless-stopped
"""


def main() -> None:
    parser = argparse.ArgumentParser(description="OpenClawMesh Service & Daemon Installer")
    parser.add_argument("--type", choices=["systemd", "launchd", "docker", "auto"], default="auto")
    parser.add_argument("--out", help="Chemin du fichier de sortie")
    parser.add_argument("--port", type=int, default=8000, help="Port d'écoute")
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
