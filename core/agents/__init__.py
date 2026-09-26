"""Sistema multiagente profesional de JARVIS.

Arquitectura:
- Supervisor: planifica y orquesta
- Agentes especializados: DEV, RESEARCH, EXECUTE, CHAT
- Memoria compartida, trace, registry de skills
"""
from .base import AgentBase, AgentResult
from .multiagent import MultiAgent

__all__ = ["AgentBase", "AgentResult", "MultiAgent"]
