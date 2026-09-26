"""Sistema multiagente profesional."""
from typing import List, Dict

from core.agents.memory import SharedMemory
from core.agents.trace import Trace
from core.agents.supervisor import Supervisor
from core.agents.dev import DevAgent
from core.agents.research import ResearchAgent
from core.agents.execute import ExecuteAgent
from core.agents.chat import ChatAgent
from core.agents.base import AgentResult


# Skills cuyo quick_match es DETERMINISTICO y seguro ejecutar directo.
# El resto pasa por el supervisor LLM.
SKILLS_PRECACHE = {
    "system",
    "desktop",
    "clipboard",
    "entertainment",
    "productivity",
    "alarm",
    "spotify",
}


class MultiAgent:
    def __init__(self):
        self.memory = SharedMemory()
        self.trace = Trace()
        self.supervisor = Supervisor(memory=self.memory, trace=self.trace)
        self.agents = {
            "dev": DevAgent(memory=self.memory, trace=self.trace),
            "research": ResearchAgent(memory=self.memory, trace=self.trace),
            "execute": ExecuteAgent(memory=self.memory, trace=self.trace),
            "chat": ChatAgent(memory=self.memory, trace=self.trace),
        }
        self.max_pasos = 3

    def run(self, tarea: str, skills=None, router=None) -> Dict:
        self.memory.add_message("user", tarea)
        
        # PRE-CHECK: si la tarea matchea quick_match, ejecutar directo sin LLM.
        # Esto evita que el supervisor reescriba la tarea (bug: "bloquea la pc" -> "apaga la pc")
        # y es mucho mas rapido (no llama al supervisor LLM).
        if router is not None:
            try:
                quick = router._quick_match(tarea)
                if quick and not isinstance(quick, str):
                    acciones = quick if isinstance(quick, list) else [quick]
                    # Ejecutar la primera accion directa
                    resultados_quick = []
                    for accion in acciones:
                        skill_name = accion.get("skill", "")
                        action = accion.get("action", "")
                        params = accion.get("params", {})
                        if not skill_name or skill_name == "none":
                            continue
                        skill = router.skills.get(skill_name)
                        if not skill:
                            continue
                        r = router._safe_run(skill, action, params)
                        if r:
                            resultados_quick.append(r)
                    # Filtrar: solo ejecutar si TODAS las acciones son de skills deterministicas
                    acciones_validas = [
                        a for a in acciones
                        if a.get("skill", "") in SKILLS_PRECACHE
                    ]
                    if not acciones_validas:
                        # Ninguna accion es deterministica: dejar que el supervisor decida
                        resultados_quick = []
                    
                    if resultados_quick:
                        # Normalizar
                        norm = []
                        for r in resultados_quick:
                            if isinstance(r, dict):
                                norm.append(r)
                            elif isinstance(r, str):
                                norm.append({"display": r, "voice": r, "thought": ""})
                            else:
                                norm.append({"display": str(r), "voice": str(r), "thought": ""})
                        displays = [n.get("display", "") for n in norm if n.get("display")]
                        voices = [n.get("voice", "") for n in norm if n.get("voice")]
                        respuesta = "\n".join(displays) or "\n".join(voices)
                        self.memory.add_message("assistant", respuesta[:200])
                        if self.trace:
                            self.trace.log_evento("quick_match_hit", {
                                "tarea": tarea,
                                "acciones": acciones,
                            })
                            self.trace.guardar()
                        return {
                            "respuesta": respuesta,
                            "agentes_usados": ["quick_match"],
                            "plan": [{"agente": "quick_match", "tarea": tarea}],
                            "razon_plan": "quick_match directo (sin LLM)",
                            "exito": True,
                            "tiempo_total": 0.0,
                            "trace_id": self.trace.sesion_id,
                        }
            except Exception as e:
                if self.trace:
                    self.trace.log_evento("quick_match_error", {"error": str(e)})
        
        plan_obj = self.supervisor.planificar(tarea)
        plan = plan_obj.get("plan", [])
        # Safety: si el supervisor devolvio plan vacio, usar fallback
        if not plan:
            plan_obj = self.supervisor._fallback(tarea)
            plan = plan_obj["plan"]
        plan = plan[:self.max_pasos]
        if not plan:
            plan = [{"agente": "chat", "tarea": tarea}]
        # FIX: si el plan tiene 1 solo paso, forzar la tarea ORIGINAL del usuario.
        # El supervisor a veces reescribe la tarea (ej: "bloquea la pc" -> "apaga la pc")
        # y eso dispara acciones incorrectas.
        if len(plan) == 1:
            plan[0]["tarea"] = tarea

        if self.trace:
            self.trace.log_evento("plan", {
                "tarea": tarea[:200],
                "plan": plan,
                "razon": plan_obj.get("razon", ""),
            })

        resultados: List[AgentResult] = []
        contexto_acumulado = ""
        for i, paso in enumerate(plan):
            agente_name = paso["agente"]
            tarea_paso = paso["tarea"]
            agente = self.agents.get(agente_name)
            if not agente:
                continue

            if self.trace:
                self.trace.log_evento("ejecutar", {
                    "paso": i + 1,
                    "agente": agente_name,
                    "tarea": tarea_paso[:200],
                })

            result = agente.run(tarea=tarea_paso, contexto=contexto_acumulado, skills=skills, router=router)
            resultados.append(result)

            if result.exito:
                contexto_acumulado += f"\n[{agente_name}]: {result.respuesta[:500]}"
                self.memory.add_message("assistant", f"[{agente_name}] {result.respuesta[:200]}")

        if not resultados:
            respuesta = "No pude procesar esa tarea."
            exito = False
        elif len(resultados) == 1:
            respuesta = resultados[0].respuesta
            exito = resultados[0].exito
        else:
            respuesta = self._sintetizar(tarea, resultados)
            exito = any(r.exito for r in resultados)

        self.trace.guardar()

        return {
            "respuesta": respuesta,
            "agentes_usados": [r.agente for r in resultados],
            "plan": plan,
            "razon_plan": plan_obj.get("razon", ""),
            "exito": exito,
            "tiempo_total": sum(r.tiempo_seg for r in resultados),
            "trace_id": self.trace.sesion_id,
        }

    def _sintetizar(self, tarea: str, resultados: List[AgentResult]) -> str:
        partes = [f"**{r.agente.upper()}**\n{r.respuesta}" for r in resultados if r.exito]
        if not partes:
            return "Los agentes fallaron al procesar la tarea."
        if len(partes) == 1:
            return partes[0]
        return "\n\n---\n\n".join(partes)

    def reset(self):
        self.memory.clear()
        self.trace = Trace()
