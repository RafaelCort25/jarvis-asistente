"""Clase base para todos los agentes."""
import time
from dataclasses import dataclass, field
from typing import Optional, List

import ollama

from core.model_config import get_model


ANTI_HALLUC = """
REGLAS CRITICAS DE IDENTIDAD:
- Tu nombre es Senna. Eres una asistente personal.
- Si te preguntan quien te creo, responde exactamente: "Fui creado por Rafael como asistente personal."
- NUNCA inventes historia sobre JARVIS, Iron Man, Marvel ni Douglas Engelbart.
- NUNCA inventes URLs, fuentes, citas bibliograficas ni estadisticas.
- Si no sabes algo, di "No lo se".
"""


@dataclass
class AgentResult:
    agente: str
    tarea: str
    respuesta: str
    exito: bool = True
    error: str = ""
    skills_usadas: list = field(default_factory=list)
    tiempo_seg: float = 0.0
    metadata: dict = field(default_factory=dict)


class AgentBase:
    """Clase base para agentes especializados."""

    name = "base"
    system_prompt = "Eres un asistente."
    default_model_key = "chat"
    max_iter = 5
    can_execute = False   # Si True, intenta ejecutar skills reales

    def __init__(self, model: Optional[str] = None, memory=None, trace=None):
        if model:
            self.model = model
        else:
            # Leer config/agents.json primero, sino usar model_config
            try:
                import json
                from pathlib import Path as _P
                cfg_path = _P(__file__).resolve().parent.parent.parent / "config" / "agents.json"
                if cfg_path.exists():
                    cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
                    entry = cfg.get(self.name, {})
                    if isinstance(entry, dict) and entry.get("model"):
                        self.model = entry["model"]
                    else:
                        self.model = get_model(self.default_model_key)
                else:
                    self.model = get_model(self.default_model_key)
            except Exception:
                self.model = get_model(self.default_model_key)
        self.memory = memory
        self.trace = trace

    def _build_messages(self, tarea: str, contexto: str = ""):
        messages = [{"role": "system", "content": self.system_prompt + "\n" + ANTI_HALLUC}]
        if contexto:
            messages.append({"role": "system", "content": f"Contexto previo:\n{contexto}"})
        if self.memory:
            hist = self.memory.get_conversation_context()
            if hist:
                messages.append({"role": "system", "content": f"Historial reciente:\n{hist}"})
            facts = self.memory.get_facts_context()
            if facts:
                messages.append({"role": "system", "content": facts})
        messages.append({"role": "user", "content": tarea})
        return messages

    def _try_execute_skill(self, tarea: str, router):
        """Si la tarea matchea quick_match y la skill esta permitida, la ejecuta.
        
        Devuelve un AgentResult o None si no hay match.
        """
        if not router:
            return None
        try:
            from core.agents.registry import puede_usar
            quick = router._quick_match(tarea)
            if not quick or isinstance(quick, str):
                return None
            # quick es una lista de acciones
            acciones = quick if isinstance(quick, list) else [quick]
            resultados = []
            for accion in acciones:
                skill_name = accion.get("skill", "")
                action = accion.get("action", "")
                params = accion.get("params", {})
                if not skill_name or skill_name == "none":
                    continue
                if not puede_usar(self.name, skill_name):
                    continue
                skill = router.skills.get(skill_name)
                if not skill:
                    continue
                r = router._safe_run(skill, action, params)
                if r:
                    resultados.append(r)
            
            if not resultados:
                return None
            
            # Normalizar resultados (por si _safe_run devolvio un str)
            normalizados = []
            for r in resultados:
                if isinstance(r, dict):
                    normalizados.append(r)
                elif isinstance(r, str):
                    normalizados.append({"display": r, "voice": r, "thought": ""})
                elif isinstance(r, tuple):
                    # Algun _safe_run devuelve (dict, bool)
                    for item in r:
                        if isinstance(item, dict):
                            normalizados.append(item)
                            break
                else:
                    normalizados.append({"display": str(r), "voice": str(r), "thought": ""})
            
            # Combinar resultados
            displays = [r.get("display", "") for r in normalizados if r.get("display")]
            voices = [r.get("voice", "") for r in normalizados if r.get("voice")]
            thoughts = [r.get("thought", "") for r in normalizados if r.get("thought")]
            
            result = AgentResult(
                agente=self.name,
                tarea=tarea,
                respuesta="\n".join(displays) or "\n".join(voices),
                exito=True,
                skills_usadas=[a.get("skill", "") for a in acciones if a.get("skill")],
                metadata={"voice": " ".join(voices), "thought": " | ".join(thoughts)},
            )
            if self.trace:
                self.trace.log(result)
            return result
        except Exception as e:
            print(f"[{self.name}] Error ejecutando skill: {e}")
            return None

    def run(self, tarea: str, contexto: str = "", skills=None, router=None, **kwargs) -> AgentResult:
        t0 = time.time()
        
        # 1. Si el agente puede ejecutar, intentar skill directa
        if self.can_execute and router:
            exec_result = self._try_execute_skill(tarea, router)
            if exec_result:
                exec_result.tiempo_seg = time.time() - t0
                return exec_result
        
        # 2. Fallback: generar respuesta con LLM
        result = AgentResult(agente=self.name, tarea=tarea, respuesta="")
        try:
            messages = self._build_messages(tarea, contexto)
            response = ollama.chat(
                model=self.model,
                messages=messages,
                stream=False,
                options={"temperature": 0.4},
            )
            result.respuesta = response["message"]["content"].strip()
            result.exito = True
        except Exception as e:
            result.exito = False
            result.error = str(e)
            result.respuesta = f"[Error {self.name}] {e}"

        result.tiempo_seg = time.time() - t0
        if self.trace:
            self.trace.log(result)
        return result
