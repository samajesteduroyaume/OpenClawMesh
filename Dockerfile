# syntax=docker/dockerfile:1.4
# Multi-arch production Dockerfile for OpenClawMesh (linux/amd64, linux/arm64)

# ── Stage 1: Build & Dependencies ──
FROM python:3.11-slim AS builder

WORKDIR /build

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    git \
    libffi-dev \
    libssl-dev \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml requirements.txt ./
COPY openclaw_mesh ./openclaw_mesh

RUN pip install --no-cache-dir --upgrade pip wheel setuptools && \
    pip install --no-cache-dir -e ".[all,gateway]"

# ── Stage 2: Minimal Distroless / Slim Runtime ──
FROM python:3.11-slim AS runtime

LABEL maintainer="OpenClawMesh Contributors"
LABEL description="OpenClawMesh Decentralized AI Agent Protocol & Gateway"

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user
RUN useradd -m -u 10001 openclaw && \
    mkdir -p /app/data /app/.config && \
    chown -R openclaw:openclaw /app

COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin
COPY --from=builder /build/openclaw_mesh /app/openclaw_mesh
COPY assets /app/assets

USER openclaw:openclaw

ENV PYTHONUNBUFFERED=1
ENV GATEWAY_DB_PATH=/app/data/openclaw_keys.db
ENV OPENCLAW_PORT=8000
ENV OPENCLAW_HOST=0.0.0.0

EXPOSE 8000 8765 8766/udp

HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/api/v1/health || exit 1

ENTRYPOINT ["uvicorn", "openclaw_mesh.gateway.server:app", "--host", "0.0.0.0", "--port", "8000"]
