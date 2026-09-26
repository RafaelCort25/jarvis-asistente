"""Supervisor que orquesta los agentes."""
import json
import ollama
from typing import Dict

from core.model_config import get_model
from core.agents.memory import SharedMemory
from core.agents.trace import Trace


SUPERVISOR_PROMPT = """Eres el SUPERVISOR de un sistema multiagente.

Tu UNICO trabajo: leer la tarea del usuario y decidir que agente debe ejecutarla.

AGENTES DISPONIBLES:
- dev:      programacion, scripts, codigo, refactor, bugs, funciones
- research: investigacion, busquedas, resumen, explicaciones, definiciones
- execute:  comandos de sistema, automatizacion, control de la PC.
           Incluye: hora, fecha, captura de pantalla, volumen (subir/bajar/silenciar),
           abrir apps (notepad, chrome, calculadora), listar archivos, espacio en disco,
           limpiar temporales, papelera, wifi, brillo, apagar, reiniciar, etc.
- chat:     conversacion casual, saludos, preguntas simples

REGLA MAS IMPORTANTE:
- POR DEFECTO, usa **1 SOLO PASO**. Un agente, una tarea.
- SOLO usa 2-3 pasos si el usuario pide explicitamente VARIAS cosas separadas
  con palabras como "y luego", "tambien", "despues", "primero... luego".

EJEMPLOS CORRECTOS (1 paso):
- "hazme un script" -> [{"agente":"dev","tarea":"hazme un script"}]
- "que es X" -> [{"agente":"research","tarea":"que es X"}]
- "hola" -> [{"agente":"chat","tarea":"hola"}]
- "abre notepad" -> [{"agente":"execute","tarea":"abre notepad"}]
- "que hora es" -> [{"agente":"execute","tarea":"que hora es"}]
- "sube el volumen" -> [{"agente":"execute","tarea":"sube el volumen"}]

EJEMPLO CORRECTO (multi-paso):
- "busca en google X y luego hazme un script de Y" ->
  [{"agente":"research","tarea":"busca X"},
   {"agente":"dev","tarea":"hazme un script de Y"}]

REGLAS ADICIONALES:
- NUNCA inventes sub-pasos: "abrir editor", "escribir codigo", "ejecutar script"
  NO son tareas validas. La tarea del usuario se pasa TAL CUAL al agente.
- Maximo 3 pasos.

FORMATO DE RESPUESTA (JSON estricto):
{
  "plan": [{"agente": "chat", "tarea": "texto literal del usuario"}],
  "razon": "por que elegiste este agente"
}

Responde SOLO con el JSON, sin texto adicional."""


class Supervisor:
    def __init__(self, model: str = None, memory: SharedMemory = None, trace: Trace = None):
        self.model = model or get_model("classifier")
        self.memory = memory
        self.trace = trace

    def planificar(self, tarea: str) -> Dict:
        try:
            messages = [
                {"role": "system", "content": SUPERVISOR_PROMPT},
                {"role": "user", "content": tarea},
            ]
            response = ollama.chat(
                model=self.model,
                messages=messages,
                stream=False,
                options={"temperature": 0.1},
                format="json",
            )
            raw = response["message"]["content"].strip()
            plan = json.loads(raw)
            if "plan" not in plan or not isinstance(plan["plan"], list):
                raise ValueError("Formato invalido")
            plan["plan"] = plan["plan"][:3]
            # Fix: si la razon es literal, vaciarla
            razon = (plan.get("razon") or "").strip()
            if razon.lower() in ("por que elegiste este agente", "por que elegiste este plan", ""):
                plan["razon"] = f"{len(plan['plan'])} paso(s)"
            for p in plan["plan"]:
                if "agente" not in p or "tarea" not in p:
                    raise ValueError("Falta agente o tarea")
                if p["agente"] not in ("dev", "research", "execute", "chat"):
                    p["agente"] = "chat"
            return plan
        except Exception as e:
            if self.trace:
                self.trace.log_evento("supervisor_error", {"error": str(e)})
            return self._fallback(tarea)

    def _fallback(self, tarea: str) -> Dict:
        t = tarea.lower()
        # EXECUTE: control del sistema
        ejecutar = [
            "abre", "abrir", "ejecuta", "ejecutar", "comando", "terminal",
            "captura", "screenshot", "pantalla",
            "volumen", "sube", "baja", "subir", "bajar", "silencia", "mute",
            "hora", "fecha", "dia", "es",
            "bloquea", "bloquear", "lock", "apaga", "apagar", "reinicia",
            "reiniciar", "suspende", "suspender", "duerme", "dormir",
            "disco", "espacio", "limpia", "limpiar", "temporales",
            "papelera", "reiniciar", "shutdown", "restart", "sleep",
            "listar", "archivos grandes", "startup", "inicio",
        ]
        # DEV: programacion
        dev = [
            "script", "codigo", "programa", "funcion", "bug",
            "refactor", "clase", "test", "python", "javascript", "java",
            "funcion ", "algoritmo", "compile", "debug",
        ]
        # RESEARCH: investigacion
        research = [
            "busca", "buscar", "investiga", "investigar", "explica",
            "explicar", "resume", "resumir", "que es", "como funciona",
            "por que", "porque", "cuando", "donde", "quien",
        ]
        # PRIORIDAD: identidad -> chat siempre
        identidad = [
            "como te llamas", "quien eres", "quien te creo", "quien te hizo",
            "tu nombre", "presentate", "preséntate",
        ]
        if any(w in t for w in identidad):
            agente = "chat"
        elif any(w in t for w in ejecutar):
            agente = "execute"
        elif any(w in t for w in dev):
            agente = "dev"
        elif any(w in t for w in research):
            agente = "research"
        else:
            agente = "chat"
        return {
            "plan": [{"agente": agente, "tarea": tarea}],
            "razon": f"heuristic: {agente}",
        }
