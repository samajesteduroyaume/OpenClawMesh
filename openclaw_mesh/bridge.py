"""
Registre et pont de compétences (Skills Bridge) pour OpenClawMesh.

Permet d'enregistrer des fonctions synchrones, asynchrones, générateurs
(streaming) et outils OpenClaw pour les exposer aux autres agents du maillage.
"""

from __future__ import annotations

import inspect
import os
import platform
from collections.abc import Callable
from typing import Any

try:
    from importlib.metadata import version as _pkg_version

    _OPENCLAW_VERSION = _pkg_version("openclaw-mesh")
except Exception:
    _OPENCLAW_VERSION = "1.1.0"  # fallback si package non installé en mode éditable

try:
    from pydantic import BaseModel

    _HAS_PYDANTIC = True
except ImportError:
    BaseModel = Any  # type: ignore[assignment, misc]
    _HAS_PYDANTIC = False


def skill(
    name: str | None = None,
    description: str | None = None,
    schema: Any | None = None,
) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Décorateur pour enregistrer une fonction en tant que compétence OpenClawMesh."""

    def decorator(fn: Callable[..., Any]) -> Callable[..., Any]:
        setattr(fn, "__is_openclaw_skill__", True)  # noqa: B010
        setattr(fn, "__is_jarvismesh_skill__", True)  # noqa: B010
        setattr(fn, "__skill_name__", name or getattr(fn, "__name__", "skill"))  # noqa: B010
        setattr(fn, "__skill_desc__", description or (inspect.getdoc(fn) or "").strip())  # noqa: B010
        setattr(fn, "__skill_schema__", schema)  # noqa: B010
        return fn

    return decorator


class SkillRegistry:
    """Registre central des compétences d'un nœud OpenClawMesh."""

    def __init__(self, name: str = "default") -> None:
        self.name = name
        self._skills: dict[str, Callable] = {}
        self._schemas: dict[str, Any] = {}
        self._descriptions: dict[str, str] = {}
        self._remote_exposed: set[str] = set()
        self._register_builtins()

    def _register_builtins(self) -> None:
        """Enregistre les compétences utilitaires intégrées par défaut."""
        self.register(
            self._echo,
            name="echo",
            description="Renvoie le payload reçu tel quel.",
            expose_remote=True,
        )
        self.register(
            self._openclaw_info,
            name="openclaw_info",
            description="Retourne les informations du nœud OpenClaw.",
            expose_remote=False,
        )
        self.register(
            self._system_info,
            name="system_info",
            description="Retourne les métriques système (OS, CPU, Python).",
            expose_remote=False,
        )

    def register(
        self,
        fn: Callable[..., Any],
        name: str | None = None,
        description: str | None = None,
        schema: Any | None = None,
        expose_remote: bool = False,
    ) -> Callable[..., Any]:
        """Enregistre une fonction Python comme compétence du nœud."""
        skill_name = str(name or getattr(fn, "__skill_name__", getattr(fn, "__name__", "skill")))
        desc = str(description or getattr(fn, "__skill_desc__", inspect.getdoc(fn) or "")).strip()
        sch = schema or getattr(fn, "__skill_schema__", None)

        self._skills[skill_name] = fn
        if desc:
            self._descriptions[skill_name] = desc
        if sch:
            self._schemas[skill_name] = sch
        if expose_remote:
            self._remote_exposed.add(skill_name)
        else:
            self._remote_exposed.discard(skill_name)

        return fn

    def register_dict(self, skills: dict[str, Callable[..., Any]]) -> None:
        for name, fn in skills.items():
            self.register(fn, name=name)

    def get(self, name: str) -> Callable[..., Any] | None:
        return self._skills.get(name)

    def is_remote_exposed(self, name: str) -> bool:
        """Indique si une compétence peut être invoquée par un pair distant."""
        return name in self._remote_exposed

    def list_names(self) -> list[str]:
        return list(self._skills.keys())

    def list_remote_names(self) -> list[str]:
        """Retourne uniquement les compétences explicitement autorisées à distance."""
        return [name for name in self._skills if name in self._remote_exposed]

    def describe(self) -> dict[str, Any]:
        """Génère la documentation complète des compétences du nœud."""
        schemas_doc: dict[str, Any] = {}
        for s_name, s_model in self._schemas.items():
            if s_name not in self._remote_exposed:
                continue
            if _HAS_PYDANTIC and isinstance(s_model, type) and issubclass(s_model, BaseModel):
                schemas_doc[s_name] = s_model.model_json_schema()
            elif hasattr(s_model, "__dict__"):
                schemas_doc[s_name] = {"type": "object", "description": str(s_model)}

        return {
            "skills": self.list_remote_names(),
            "descriptions": {
                name: desc
                for name, desc in self._descriptions.items()
                if name in self._remote_exposed
            },
            "schemas": schemas_doc,
        }

    # ------------------------------------------------------------------ #
    # Compétences Intégrées
    # ------------------------------------------------------------------ #
    @staticmethod
    def _echo(payload: dict[str, Any]) -> dict[str, Any]:
        return payload

    @staticmethod
    def _openclaw_info(payload: dict[str, Any]) -> dict[str, Any]:
        return {
            "agent": "OpenClaw",
            "version": _OPENCLAW_VERSION,
            "protocol": "1.0",
            "os": platform.system(),
            "python": platform.python_version(),
        }

    @staticmethod
    def _system_info(payload: dict[str, Any]) -> dict[str, Any]:
        return {
            "platform": platform.platform(),
            "machine": platform.machine(),
            "processor": platform.processor(),
            "cpu_count": os.cpu_count(),
            "python_version": platform.python_version(),
        }
