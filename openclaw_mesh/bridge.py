"""
Registre et pont de compétences (Skills Bridge) pour OpenClawMesh.

Permet d'enregistrer des fonctions synchrones, asynchrones, générateurs
(streaming) et outils OpenClaw pour les exposer aux autres agents du maillage.
"""
from __future__ import annotations
import asyncio
import functools
import inspect
import os
import platform
import sys
import time
from typing import Any, AsyncGenerator, Callable, Generator, Optional, Union

try:
    from pydantic import BaseModel
    _HAS_PYDANTIC = True
except ImportError:
    BaseModel = None
    _HAS_PYDANTIC = False


def skill(
    name: Optional[str] = None,
    description: Optional[str] = None,
    schema: Optional[Any] = None,
):
    """Décorateur pour enregistrer une fonction en tant que compétence OpenClawMesh."""
    def decorator(fn: Callable):
        setattr(fn, "__is_openclaw_skill__", True)
        setattr(fn, "__is_jarvismesh_skill__", True)
        setattr(fn, "__skill_name__", name or fn.__name__)
        setattr(fn, "__skill_desc__", description or (inspect.getdoc(fn) or "").strip())
        setattr(fn, "__skill_schema__", schema)
        return fn
    return decorator


class SkillRegistry:
    """Registre central des compétences d'un nœud OpenClawMesh."""

    def __init__(self, name: str = "default"):
        self.name = name
        self._skills: dict[str, Callable] = {}
        self._schemas: dict[str, Any] = {}
        self._descriptions: dict[str, str] = {}
        self._register_builtins()

    def _register_builtins(self) -> None:
        """Enregistre les compétences utilitaires intégrées par défaut."""
        self.register(self._echo, name="echo", description="Renvoie le payload reçu tel quel.")
        self.register(self._openclaw_info, name="openclaw_info", description="Retourne les informations du nœud OpenClaw.")
        self.register(self._system_info, name="system_info", description="Retourne les métriques système (OS, CPU, Python).")

    def register(
        self,
        fn: Callable,
        name: Optional[str] = None,
        description: Optional[str] = None,
        schema: Optional[Any] = None,
    ) -> Callable:
        """Enregistre une fonction Python comme compétence du nœud."""
        skill_name = name or getattr(fn, "__skill_name__", fn.__name__)
        desc = description or getattr(fn, "__skill_desc__", inspect.getdoc(fn) or "").strip()
        sch = schema or getattr(fn, "__skill_schema__", None)

        self._skills[skill_name] = fn
        if desc:
            self._descriptions[skill_name] = desc
        if sch:
            self._schemas[skill_name] = sch

        return fn

    def register_dict(self, skills: dict[str, Callable]) -> None:
        for name, fn in skills.items():
            self.register(fn, name=name)

    def get(self, name: str) -> Optional[Callable]:
        return self._skills.get(name)

    def list_names(self) -> list[str]:
        return list(self._skills.keys())

    def describe(self) -> dict[str, Any]:
        """Génère la documentation complète des compétences du nœud."""
        schemas_doc = {}
        for s_name, s_model in self._schemas.items():
            if _HAS_PYDANTIC and issubclass(s_model, BaseModel):
                schemas_doc[s_name] = s_model.model_json_schema()
            elif hasattr(s_model, "__dict__"):
                schemas_doc[s_name] = str(s_model)

        return {
            "skills": self.list_names(),
            "descriptions": self._descriptions,
            "schemas": schemas_doc,
        }

    # ------------------------------------------------------------------ #
    # Compétences Intégrées
    # ------------------------------------------------------------------ #
    @staticmethod
    def _echo(payload: dict) -> dict:
        return payload

    @staticmethod
    def _openclaw_info(payload: dict) -> dict:
        return {
            "agent": "OpenClaw",
            "version": "1.0.0",
            "protocol": "1.0",
            "os": platform.system(),
            "python": platform.python_version(),
        }

    @staticmethod
    def _system_info(payload: dict) -> dict:
        return {
            "platform": platform.platform(),
            "machine": platform.machine(),
            "processor": platform.processor(),
            "cpu_count": os.cpu_count(),
            "python_version": platform.python_version(),
        }
