"""Routes du Portail Web Communautaire OpenClawMesh."""

from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import HTMLResponse

from ..portal import render_portal_html

router = APIRouter(tags=["Portal"])


@router.get("/", response_class=HTMLResponse)
@router.get("/portal", response_class=HTMLResponse)
async def get_portal():
    """Affiche le portail web client 100% Free & Open-Access."""
    return render_portal_html()
