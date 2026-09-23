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
  - SPOTIFY (revisar ANTES que browser):
  - "pon X en spotify", "reproduce X en spotify" → spotify.play (query = X)
  - "pausa la musica", "pausa spotify" → spotify.pause
  - "siguiente cancion", "salta esta" → spotify.next
  - "cancion anterior", "vuelve a la anterior" → spotify.previous
  - "que esta sonando", "que cancion es" → spotify.current
  - "volumen de spotify al N" → spotify.volume (percent = N)
  - NUNCA envies "pon X en spotify" a browser.search_youtube
  - DEV WRITE/RUN (importante, revisar ANTES que dev.generate_code):
  - "crea un archivo X en Y.py", "escribe un programa que haga X en Y.py" → dev.create_and_test (description = X, language = lenguaje segun extension, path = Y.py)
  - "escribe esto en el archivo X" → dev.write_file (path = X, content = el texto previo)
  - "corre el archivo X", "ejecuta X.py" → dev.run_file (path = X)
  - NUNCA uses dev.create_and_test sin un path explicito. Si no hay path, usa dev.generate_code.
  - OFFICE WORD:
  - "hazme un documento/informe/reporte/ensayo sobre X" -> office.create_doc (description = X, path = "", title = "")
  - "lee el documento X.docx", "abre el word X.docx" -> office.read_doc (path = X.docx)
  - NUNCA envies "hazme un documento sobre X" a dev.create_and_test
  - OFFICE EXCEL:
  - "hazme un excel/hoja de calculo sobre X" -> office.create_xlsx (description = X, path = "")
  - "lee el excel X.xlsx" -> office.read_xlsx (path = X.xlsx)
  - OFFICE POWERPOINT:
  - "hazme una presentacion/powerpoint sobre X" -> office.create_ppt (description = X, path = "")
  - "lee la presentacion X.pptx" -> office.read_ppt (path = X.pptx)
- IMAGENES (generacion):
  - "genera/crea/hazme/dibuja una imagen de X" -> image.generate (prompt = X, width = 1024, height = 1024)
  - "que imagenes tengo", "lista mis imagenes" -> image.list
  - NUNCA envies "genera una imagen" a dev.create_and_test
- "que hora es", "dime la hora" -> system.time
- "que dia es hoy", "que fecha es" -> system.date
- IMAGENES -> WORD (combo):
  - "genera un logo y hazme un word con el" -> image.to_word (prompt = "logo", count = 1)
  - "genera 3 logos y hazme un word con los 3" -> image.to_word (prompt = "logos", count = 3)
  - "hazme un word con las ultimas imagenes" -> image.to_word (prompt = "", count = 1)
  - NUNCA uses image.generate + office.create_doc para estos casos
- PDF (conversion):
  - "convierte el word/ese word a pdf" -> pdf.from_docx (path = "", output = "")
  - "convierte X.docx a pdf" -> pdf.from_docx (path = X.docx, output = "")
  - "que pdfs tengo" -> pdf.list
  - NUNCA envies "convierte a pdf" a office.create_doc ni a dev.*
  - EDIT (modificar archivos):
  - "modifica X.docx cambiando 'Juan' por 'Pedro'" -> edit.modify (path = X.docx, instruction = "cambia Juan por Pedro")
  - "modifica el ultimo archivo de uploads cambiando 'X' por 'Y'" -> edit.modify (path = "", instruction = "cambia X por Y")
  - "en el archivo X cambia Y por Z" -> edit.modify (path = X, instruction = "cambia Y por Z")
  - "que archivos tengo en uploads" -> edit.list_uploads
  - NUNCA envies "modifica X" a office.create_doc ni a dev.*
 - DEV COMBOS (revisar CODIGO -> documento):
  - Solo si mencionan "codigo", "archivo.py", "script" o un path .py/.js/etc.
  - "revisa el archivo/codigo y hazme un excel con los bugs" -> dev.review_to_excel (path = "", output = "")
  - "revisa X.py y hazme un excel con los bugs" -> dev.review_to_excel (path = X.py, output = "")
  - "revisa X.py y hazme un word con el analisis" -> dev.review_to_word (path = X.py, output = "")
  - NO uses estos combos si la frase es "hazme un word sobre X tema" (eso es office.create_doc)
  - NUNCA uses dev.create_and_test ni dev.generate_code para estos casos
 - TELEGRAM (enviar archivos):
  - "envíame el pdf por telegram" -> telegram.send_last (tipo = "pdf")
  - "envíame el word/excel/imagen por telegram" -> telegram.send_last (tipo = "word" | "excel" | "imagen")
  - "envíame el último archivo por telegram" -> telegram.send_last (tipo = "")
  - "envía X.pdf por telegram" -> telegram.send_file (path = X.pdf)
  - NUNCA envies "envía ... por telegram" a dev.* ni a office.*
  
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