# core/intent.py — versión modificada (solo las partes relevantes)

import json
import re
import ollama
from core.config_loader import CONFIG
from core.schemas import build_json_schema, SKILLS_VALIDAS

# Prompt reducido: el schema ya restringe la estructura,
# así que aquí solo damos guía semántica para desambiguar.
INTENT_SYSTEM_PROMPT = """Eres un clasificador de intenciones para un asistente de PC.
Dado un comando en español, devuelve un JSON con una lista de acciones.

Cada acción tiene:
- skill: el módulo que ejecuta
- action: la operación concreta
- params: los datos que necesita esa operación

REGLAS DE DESAMBIGUACIÓN:
- "revisa X", "chequea X", "está bien X" → dev.review_file
- "explica X", "qué hace X", "cómo funciona X" → dev.explain
- "busca errores en X", "hay bugs en X" → dev.find_issues
- "revisa el proyecto X", "analiza la carpeta X" → dev.review_project
- "genera/escribe/crea una función X" → dev.generate_code
- "qué ves en mi pantalla", "describe mi pantalla", "mira mi pantalla", "qué hay en mi pantalla" → vision.describe_screen
- "qué ves en mi pantalla y explica el código", "mira el código en pantalla", "analiza el código que se ve", "revisa el código de la pantalla" → vision.explain_screen_code
- IMPORTANTE: si la frase menciona "pantalla" + "código", SIEMPRE es vision.explain_screen_code, NUNCA dev.*

- "busca el archivo X", "encuentra X", "dónde está X" → files.find_file
- "busca en google X", "googlea X" → browser.search_google
- "busca en youtube X", "pon X", "reproduce X" → browser.search_youtube

- Si el usuario pide varias cosas separadas por "y", "luego", "después" → devuélvelas en orden.
- Si es charla normal, saludo, o no encaja en ninguna skill → none.chat

No inventes parámetros que no estén en el schema.
No devuelvas texto fuera del JSON.
"""

class IntentClassifier:
    def __init__(self):
        self.model = CONFIG["models"].get("intent", CONFIG["models"]["default"])
        self.cache = {}
        self.schema = build_json_schema()
        print(f"[INTENT] Usando modelo: {self.model}")

    def classify(self, user_text):
        key = user_text.lower().strip()
        if key in self.cache:
            return self.cache[key]

        try:
            response = ollama.chat(
                model=self.model,
                messages=[
                    {"role": "system", "content": INTENT_SYSTEM_PROMPT},
                    {"role": "user", "content": user_text},
                ],
                options={"temperature": 0.1},
                format=self.schema,  # ← clave: fuerza la estructura
            )
            raw = response["message"]["content"].strip()
            result = self._parse_json(raw)
            result = self._validate_actions(result)  # ← validación extra
            self.cache[key] = result
            return result
        except Exception as e:
            print(f"[INTENT ERROR] {e}")
            return {"actions": [{"skill": "none", "action": "chat", "params": {}}]}

    def _parse_json(self, raw):
        # Con format=schema, Ollama garantiza JSON válido.
        # Igual dejamos el parseo defensivo por si acaso.
        try:
            data = json.loads(raw)
            if "actions" not in data:
                return {"actions": [{"skill": "none", "action": "chat", "params": {}}]}
            return data
        except json.JSONDecodeError:
            return {"actions": [{"skill": "none", "action": "chat", "params": {}}]}

    def _validate_actions(self, data):
        """
        Segunda barrera: aunque el schema fuerza la estructura,
        verificamos que skill/action existan y que params no tenga campos extra.
        Si algo no cuadra, lo reemplazamos por none.chat.
        """
        acciones_limpias = []
        for accion in data.get("actions", []):
            skill = accion.get("skill")
            action = accion.get("action")
            params = accion.get("params", {})

            if skill not in SKILLS_VALIDAS:
                continue
            if action not in SKILLS_VALIDAS[skill]:
                continue

            # Filtrar params que no estén definidos para esta acción
            params_permitidos = SKILLS_VALIDAS[skill][action]
            params_filtrados = {k: v for k, v in params.items() if k in params_permitidos}

            acciones_limpias.append({
                "skill": skill,
                "action": action,
                "params": params_filtrados,
            })

        if not acciones_limpias:
            return {"actions": [{"skill": "none", "action": "chat", "params": {}}]}
        return {"actions": acciones_limpias}