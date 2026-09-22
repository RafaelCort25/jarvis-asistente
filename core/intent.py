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

REGLAS DOCS (importante, revisar antes de dev):
- Preguntas sobre MI información personal o mis documentos (curriculum, cv, apuntes, pdfs, notas) → docs.ask
- Palabras clave: "que dice mi", "segun mi", "de que trata mi", "mi curriculum", "mi cv", "mis apuntes", "mis pdfs", "que habilidades tengo", "que experiencia tengo"
- docs.ask SIEMPRE usa la frase completa como query.
- NUNCA envies frases con "curriculum", "cv", "mis apuntes", "mis pdfs", "mi" + pregunta → a dev.* ni a files.*
- "indexa X", "aprende X", "guarda X en conocimiento", "procesa el archivo X", "lee el pdf X" → docs.index_file
- "indexa la carpeta X", "procesa la carpeta X", "aprende todo lo de X" → docs.index_folder
- "que documentos tienes", "lista mis documentos", "que has indexado" → docs.list
- "olvida el documento X", "borra X de documentos" → docs.delete
- "que tengo copiado", "lee el portapapeles", "que hay en el portapapeles" → clipboard.read
- "copia esto", "copia al portapapeles", "guarda en el portapapeles" → clipboard.write (usa el texto completo como text)
- "recuérdame X en N minutos/horas" → scheduler.add_once (seconds = N*60 o N*3600, message = X)
- "recuérdame X en N segundos" → scheduler.add_once (seconds = N, message = X)
- "todos los días a las HHHH envíame/recuérdame X" → scheduler.add_daily (time = "HH:MM", message = X)
- "cada N minutos haz/recuérdame X" → scheduler.add_interval (every_minutes = N, message = X)
- "qué tareas tengo", "lista mis recordatorios", "mis alarmas" → scheduler.list
- "cancela el recordatorio N", "elimina la tarea N" → scheduler.cancel (identifier = N)
- "ejecuta X", "corre X", "lanza X" (comando de shell) → terminal.run (command = X)
- "haz git status", "muestrame git status", "corre git status" → terminal.run (command = "git status")
- "instala las dependencias", "corre los tests", "haz un commit" → terminal.suggest (goal = frase completa)  ← el usuario tendra que confirmar despues

- GIT (importante):
  - "que cambios tengo", "git status", "estado del repo" → git.status
  - "muestrame los cambios", "git diff" → git.diff
  - "ultimos commits", "git log", "historial" → git.log
  - "añade todo al staging", "git add", "prepara los cambios" → git.add (paths = ".")
  - "haz un commit con mensaje: X" → git.commit (message = X literal)
  - "sube los cambios", "git push" → git.push
  - "baja los cambios", "git pull" → git.pull
  - NUNCA envies "añade todo al staging", "commit", "git add" a docs.* ni a files.*
  - SPOTIFY (importante: revisar ANTES que browser):
  - "pon X en spotify", "reproduce X en spotify" → spotify.play (query = X)
  - "pausa la musica", "pausa spotify", "pausa" → spotify.pause
  - "siguiente cancion", "salta esta", "pasa a la siguiente" → spotify.next
  - "cancion anterior", "vuelve a la anterior" → spotify.previous
  - "que esta sonando", "que cancion es" → spotify.current
  - "volumen de spotify al N" → spotify.volume (percent = N)
  - NUNCA envies "pon X en spotify" a browser.search_youtube

- "busca el archivo X", "encuentra X", "dónde está X" → files.find_file
- "busca en google X", "googlea X" → browser.search_google
- "busca en youtube X", "pon X", "reproduce X" → browser.search_youtube

- Si el usuario pide varias cosas separadas por "y", "luego", "después" → devuelvelas en orden.
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