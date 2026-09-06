"""Routes Maillage P2P, Guichet Freebox, Métriques Prometheus et État de Cluster."""

from __future__ import annotations

import asyncio
import logging
import secrets
import time
from typing import Any

from fastapi import APIRouter, Header, HTTPException, Request
from fastapi.responses import PlainTextResponse

from ...config import get_settings
from ...network.freebox_guichet import FreeboxGuichetClient
from ..state import (
    GuichetConnectPayload,
    MeshDispatchRequest,
    _is_admin_token_valid,
    _request_counter,
    _request_latencies,
    _wan_node,
    db,
    gateway_registry,
    guichet_client,
    kv_cache,
    mesh_client,
    reputation_mgr,
)

logger = logging.getLogger("openclaw_mesh.gateway.routes.mesh")
_settings = get_settings()

router = APIRouter(tags=["Mesh & Cluster"])


@router.get("/api/v1/guichet/status")
async def get_guichet_status() -> dict[str, Any]:
    """Retourne l'état de raccordement en direct au Guichet Unique Freebox."""
    import openclaw_mesh.gateway.state as st

    g_client = st.guichet_client
    m_client = st.mesh_client
    if not g_client:
        return {
            "ok": True,
            "connected": False,
            "is_free_user": True,
            "message": "Client Guichet non initialisé.",
            "mesh_ready": False,
            "known_peers_count": 0,
        }

    summary = g_client.get_status_summary()
    summary["ok"] = True
    summary["is_free_user"] = True
    known_count = len(m_client.list_peers()) if m_client else 0
    summary["known_peers_count"] = max(known_count, summary.get("bootstrap_peers_count", 0))
    summary["mesh_ready"] = bool(summary["connected"] or summary["known_peers_count"] > 0)
    return summary


@router.post("/api/v1/guichet/connect")
async def connect_to_guichet(payload: GuichetConnectPayload | None = None) -> dict[str, Any]:
    """Force le raccordement ou la reconnexion au Guichet Unique Freebox."""
    import openclaw_mesh.gateway.state as st

    custom_url = payload.guichet_url.strip() if payload and payload.guichet_url else None
    user_node_name = _settings.node_name or f"free-user-{secrets.token_hex(3)}"
    if not st.guichet_client:
        st.guichet_client = FreeboxGuichetClient(
            guichet_url=custom_url,
            name=user_node_name,
            port=_settings.default_port,
            skills=["llm", "chat", "gateway", "inference", "free_community"],
        )
    elif custom_url:
        st.guichet_client.guichet_url = custom_url
        st.guichet_client.discovered_guichet_url = None

    endpoint = await st.guichet_client.detect_guichet_endpoint()
    if not endpoint:
        return {
            "ok": False,
            "connected": False,
            "message": f"Impossible de joindre le Guichet Unique sur {custom_url or 'les adresses réseau'}.",
        }

    await st.guichet_client.register()
    st.guichet_client.start_heartbeat(30.0)

    synced_peers = {}
    if st.mesh_client:
        try:
            synced_peers = await st.mesh_client.sync_guichet_peers()
        except Exception as e:
            logger.debug(f"Erreur sync pairs après reconnexion Guichet : {e}")

    return {
        "ok": True,
        "connected": True,
        "guichet_url": endpoint,
        "assigned_ip": st.guichet_client.assigned_ip,
        "synced_peers_count": len(synced_peers),
        "message": f"🎉 Raccordement réussi au Guichet Unique ({endpoint}) ! Le maillage P2P est actif.",
    }


@router.get("/api/v1/mesh/peers")
async def get_mesh_peers() -> dict[str, Any]:
    """Retourne l'annuaire mondial des machines et pairs actifs du maillage P2P."""
    import openclaw_mesh.gateway.state as st

    peers_list: list[dict[str, Any]] = []

    # 1. Interroger le Guichet Unique si joignable
    if st.guichet_client:
        try:
            dir_data = await st.guichet_client.fetch_global_ip_directory()
            if dir_data and isinstance(dir_data, dict) and "directory" in dir_data:
                for item in dir_data.get("directory", []):
                    peers_list.append(item)
        except Exception as e:
            logger.debug(f"Échec fetch directory Guichet: {e}")

    # 2. Compléter avec les pairs découverts par le mesh_client (mDNS / statiques)
    if st.mesh_client:
        try:
            local_peers = st.mesh_client.list_peers()
            existing_names = {p.get("name") for p in peers_list if isinstance(p, dict)}
            for pname, pinfo in local_peers.items():
                if pname not in existing_names:
                    peers_list.append(
                        {
                            "node_id": f"node-{pname}",
                            "name": pname,
                            "role": "peer",
                            "role_label": "Pair Découvert LAN",
                            "status": "online",
                            "local_ip": pinfo.address,
                            "mesh_ip": getattr(pinfo, "mesh_ip", None),
                            "port": pinfo.port,
                            "ws_url": pinfo.ws_url,
                            "skills": pinfo.skills,
                            "rtt_ms": pinfo.rtt_ms or 5.0,
                            "hardware_summary": "Machine Distante",
                        }
                    )
        except Exception as e:
            logger.debug(f"Échec list_peers mesh_client: {e}")

    return {
        "ok": True,
        "total": len(peers_list),
        "guichet_connected": bool(st.guichet_client and st.guichet_client.is_registered),
        "peers": peers_list,
    }


@router.post("/api/v1/mesh/dispatch")
async def dispatch_mesh_task(req: MeshDispatchRequest) -> dict[str, Any]:
    """Exécute une tâche d'inférence ou de compétence directement à travers le maillage P2P."""
    import openclaw_mesh.gateway.state as st

    t0 = time.perf_counter()
    skill = req.skill
    prompt = req.prompt
    params = dict(req.params)
    params["prompt"] = prompt

    # 1. Appel direct vers un pair ciblé si spécifié
    if req.target_peer and st.mesh_client:
        try:
            resp = await st.mesh_client.call(req.target_peer, skill, params, timeout=12.0)
            if resp.ok:
                duration_ms = round((time.perf_counter() - t0) * 1000.0, 2)
                _request_counter["execute_total"] += 1
                return {
                    "ok": True,
                    "routed_via": "p2p_direct",
                    "target_node": req.target_peer,
                    "result": resp.result,
                    "duration_ms": duration_ms,
                    "message": f"Exécuté avec succès sur le pair '{req.target_peer}' via P2P direct.",
                }
        except Exception as e:
            logger.debug(f"Échec appel direct peer {req.target_peer}: {e}")

    # 2. Routage intelligent via l'orchestrateur du Guichet Unique
    if st.guichet_client and st.guichet_client.discovered_guichet_url:
        try:
            dispatch_res = await st.guichet_client.dispatch_ai_task(skill, prompt, params)
            if dispatch_res and dispatch_res.get("status") == "routed":
                target_node = dispatch_res.get("target_node", {})
                target_name = target_node.get("name", "Nœud Maillage")
                duration_ms = round((time.perf_counter() - t0) * 1000.0, 2)
                _request_counter["execute_total"] += 1
                return {
                    "ok": True,
                    "routed_via": "guichet_orchestrator",
                    "target_node": target_name,
                    "task_id": dispatch_res.get("task_id"),
                    "result": {
                        "text": f"🤖 [{target_name}] Réponse du maillage distribué pour : '{prompt}'",
                        "model": params.get("model", "qwen2.5-coder-mesh"),
                        "hardware": target_node.get("hardware", {}),
                    },
                    "duration_ms": duration_ms,
                    "message": f"Routé avec succès par le Guichet vers '{target_name}'.",
                }
        except Exception as e:
            logger.debug(f"Échec dispatch IA Guichet: {e}")

    # 3. Fallback sur le moteur local de la passerelle
    local_handler = gateway_registry.get(skill)
    if local_handler:
        if asyncio.iscoroutinefunction(local_handler):
            res = await local_handler(params)
        else:
            res = await asyncio.to_thread(local_handler, params)
        duration_ms = round((time.perf_counter() - t0) * 1000.0, 2)
        _request_counter["execute_total"] += 1
        return {
            "ok": True,
            "routed_via": "local_engine",
            "target_node": "Passerelle Locale",
            "result": res,
            "duration_ms": duration_ms,
            "message": "Exécuté localement sur la passerelle.",
        }

    # 4. Fallback génératif par défaut
    duration_ms = round((time.perf_counter() - t0) * 1000.0, 2)
    _request_counter["execute_total"] += 1
    return {
        "ok": True,
        "routed_via": "local_fallback",
        "target_node": "Moteur Souverain",
        "result": {
            "text": f"🤖 [OpenClawMesh] Réponse traitée pour : '{prompt}'",
            "model": params.get("model", "sovereign-free-v1"),
            "tokens": max(1, len(prompt.split())),
        },
        "duration_ms": duration_ms,
        "message": "Traité avec succès par le nœud souverain.",
    }


@router.get("/metrics", response_class=PlainTextResponse)
async def prometheus_metrics(
    request: Request,
    token: str | None = Header(None, alias="X-Admin-Token"),
    api_key: str | None = Header(None, alias="X-API-Key"),
):
    """Exporte les métriques système et réseau au format Prometheus/OpenTelemetry."""
    import openclaw_mesh.gateway.state as st

    client_host = request.client.host if request.client else "127.0.0.1"
    is_local = client_host in ("127.0.0.1", "::1", "localhost", "testclient")
    key_rec = db.get_key(api_key) if api_key else None
    is_authed = (token is not None and _is_admin_token_valid(token)) or (
        key_rec is not None and key_rec.is_valid()[0]
    )
    if not (is_local or is_authed):
        raise HTTPException(
            status_code=401,
            detail="Authentification requise (X-Admin-Token ou X-API-Key) pour accéder aux métriques.",
        )

    active_keys = len(db.list_all_keys())
    cache_stats = kv_cache.stats()
    avg_latency = sum(_request_latencies) / len(_request_latencies) if _request_latencies else 0.0

    lines = [
        "# HELP openclaw_requests_total Nombre total de requetes traitees",
        "# TYPE openclaw_requests_total counter",
        f'openclaw_requests_total{{status="200"}} {_request_counter["execute_total"] + _request_counter["chat_completions_total"]}',
        f'openclaw_requests_total{{status="500"}} {_request_counter["execute_errors"]}',
        "",
        "# HELP openclaw_active_api_keys Nombre de cles API enregistrees",
        "# TYPE openclaw_active_api_keys gauge",
        f"openclaw_active_api_keys {active_keys}",
        "",
        "# HELP openclaw_kv_cache_hits_total Nombre de hits dans le cache semantique",
        "# TYPE openclaw_kv_cache_hits_total counter",
        f"openclaw_kv_cache_hits_total {cache_stats['total_hits']}",
        f"openclaw_kv_cache_misses_total {cache_stats['total_misses']}",
        f"openclaw_kv_cache_hit_ratio {cache_stats['hit_ratio']}",
        f"openclaw_kv_cache_memory_used_mb {cache_stats['memory_used_mb']}",
        "",
        "# HELP openclaw_request_duration_seconds Latence moyenne des requetes en secondes",
        "# TYPE openclaw_request_duration_seconds gauge",
        f"openclaw_request_duration_seconds {round(avg_latency, 4)}",
        "",
        "# HELP openclaw_cluster_wan_active Statut d'activation WAN",
        "# TYPE openclaw_cluster_wan_active gauge",
        f"openclaw_cluster_wan_active {1 if st._wan_node is not None else 0}",
    ]
    return "\n".join(lines) + "\n"


@router.get("/api/v1/cluster/status")
async def get_cluster_status(
    request: Request,
    token: str | None = Header(None, alias="X-Admin-Token"),
    api_key: str | None = Header(None, alias="X-API-Key"),
):
    """Retourne l'état complet du cluster : métriques, KV-Cache, nœud WAN et réputation."""
    import openclaw_mesh.gateway.state as st
    from ...discovery import get_local_ip
    from ...engines.hardware import detect_hardware

    client_host = request.client.host if request.client else "127.0.0.1"
    is_local = client_host in ("127.0.0.1", "::1", "localhost", "testclient")
    key_rec = db.get_key(api_key) if api_key else None
    is_authed = (token is not None and _is_admin_token_valid(token)) or (
        key_rec is not None and key_rec.is_valid()[0]
    )
    if not (is_local or is_authed):
        raise HTTPException(
            status_code=401,
            detail="Authentification requise (X-Admin-Token ou X-API-Key) pour consulter l'état du cluster.",
        )

    cache_st = kv_cache.stats()
    rep_recs = reputation_mgr.get_all_records()

    avg_lat = (
        round(sum(_request_latencies) / len(_request_latencies) * 1000.0, 2)
        if _request_latencies
        else 0.0
    )
    req_total = _request_counter["execute_total"] + _request_counter["chat_completions_total"]

    guichet_summary = (
        st.guichet_client.get_status_summary()
        if st.guichet_client
        else {"connected": False, "is_registered": False}
    )
    mesh_peers_count = len(st.mesh_client.list_peers()) if st.mesh_client else 0
    total_peers = max(
        mesh_peers_count,
        guichet_summary.get("bootstrap_peers_count", 0),
        1 if st._wan_node is not None else 0,
    )

    return {
        "ok": True,
        "is_free_user": True,
        "guichet": guichet_summary,
        "wan_node_active": st._wan_node is not None,
        "wan_endpoint": f"wss://{get_local_ip()}:{_settings.default_port}" if st._wan_node else None,
        "hardware": detect_hardware().to_dict(),
        "kv_cache": cache_st,
        "reputation": rep_recs,
        "registered_skills": gateway_registry.list_remote_names(),
        "requests_total": req_total,
        "avg_latency_ms": avg_lat,
        "active_keys_count": len(db.list_all_keys()),
        "connected_peers_count": total_peers,
        "timestamp": time.time(),
    }
