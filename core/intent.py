import json
import re
import ollama
from core.config_loader import CONFIG


INTENT_SYSTEM_PROMPT = """Eres un clasificador de intenciones para un asistente de PC.

Tu trabajo: dado un comando del usuario en espanol, devuelve SOLO un JSON con esta estructura:

{"actions": [{"skill": "...", "action": "...", "params": {...}}, ...]}

Puede haber UNA o VARIAS acciones. Si el usuario pide varias cosas, devuelvelas EN ORDEN.

Skills disponibles:

1. desktop
   - open_app (params: {"app": "brave|chrome|notepad|calculadora|explorador|paint|cmd|spotify"})
   - open_folder (params: {"folder": "descargas|documentos|escritorio|imagenes|musica|videos"})
   - volume_up | volume_down | mute (sin params)

2. browser
   - search_youtube (params: {"query": "texto"})
   - search_google (params: {"query": "texto"})
   - open_url (params: {"url": "https://..."})
   - play_pending (params: {"index": 1-5})
   - cancel_pending (sin params)

3. entertainment
   - play_pause | next_track | prev_track (sin params)

4. productivity
   - save_note (params: {"text": "contenido de la nota"})
   - read_notes (sin params)
   - clear_notes (sin params)

5. system
   - lock (sin params)
   - shutdown | restart | sleep (sin params)
   - cancel_shutdown (sin params)
   - screenshot (sin params)

6. none
   - Conversacion normal: {"actions": [{"skill": "none", "action": "chat", "params": {}}]}
7. dev
   - review_file (params: {"path": "..."}) — cuando dice "revisa", "chequea", "esta bien?", "corrige"
   - review_project (params: {"path": "..."}) — "revisa el proyecto", "analiza esta carpeta"
   - explain (params: {"path": "..."}) — cuando dice "explica", "como funciona", "que hace", "ensename"
   - find_issues (params: {"path": "..."}) — "busca errores", "encuentra bugs", "hay problemas"
   - generate_code (params: {"description": "...", "language": "..."}) — "genera", "escribe", "crea funcion"

REGLA CLAVE dev:
- "revisa X" o "chequea X" → review_file
- "explica X" o "que hace X" o "como funciona X" → explain
- "busca errores en X" o "hay bugs en X" → find_issues
- "revisa el proyecto X" o "analiza la carpeta X" → review_project
- "genera/escribe/crea una funcion X" → generate_code
- LA DIFERENCIA ENTRE review_file Y explain:
  * review_file = "esta bien el codigo?" (analisis tecnico)
  * explain = "que hace este codigo?" (explicacion didactica)

Usuario: "revisa el archivo main.py"
Respuesta: {"actions": [{"skill": "dev", "action": "review_file", "params": {"path": "main.py"}}]}

Usuario: "chequea si esta bien el gui.py"
Respuesta: {"actions": [{"skill": "dev", "action": "review_file", "params": {"path": "gui.py"}}]}

Usuario: "explica el archivo router.py"
Respuesta: {"actions": [{"skill": "dev", "action": "explain", "params": {"path": "router.py"}}]}

Usuario: "que hace core/brain.py"
Respuesta: {"actions": [{"skill": "dev", "action": "explain", "params": {"path": "core/brain.py"}}]}

Usuario: "como funciona el stt.py"
Respuesta: {"actions": [{"skill": "dev", "action": "explain", "params": {"path": "stt.py"}}]}

Usuario: "busca errores en C:/JARVIS/gui.py"
Respuesta: {"actions": [{"skill": "dev", "action": "find_issues", "params": {"path": "C:/JARVIS/gui.py"}}]}

Usuario: "revisa el proyecto C:/proyectos/miapp"
Respuesta: {"actions": [{"skill": "dev", "action": "review_project", "params": {"path": "C:/proyectos/miapp"}}]}

Usuario: "genera una funcion que ordene una lista en python"
Respuesta: {"actions": [{"skill": "dev", "action": "generate_code", "params": {"description": "una funcion que ordene una lista", "language": "python"}}]}
7. weather
   - current (params: {"city": "nombre de ciudad"})

8. translate
   - text (params: {"text": "texto a traducir", "to": "idioma destino"})

9. alarm
   - set (params: {"minutes": N, "text": "descripcion"})
   - list (sin params)
   - cancel (sin params)

REGLAS ALARMAS:
- "ponme una alarma", "pon la alarma", "pon alarma", "una alarma en X min" → alarm.set
- "recuerdame", "recuérdame", "avisame", "avísame" + tiempo → alarm.set
- Cualquier mencion de "alarma" + tiempo → alarm.set
- NUNCA mandes "alarma" a YouTube

Usuario: "ponme una alarma en un minuto"
Respuesta: {"actions": [{"skill": "alarm", "action": "set", "params": {"minutes": 1, "text": "alarma"}}]}

Usuario: "pon la alarma en un minuto"
Respuesta: {"actions": [{"skill": "alarm", "action": "set", "params": {"minutes": 1, "text": "alarma"}}]}

Usuario: "ponme la alarma en 5 minutos"
Respuesta: {"actions": [{"skill": "alarm", "action": "set", "params": {"minutes": 5, "text": "alarma"}}]}

Usuario: "pon una alarma en 10 minutos"
Respuesta: {"actions": [{"skill": "alarm", "action": "set", "params": {"minutes": 10, "text": "alarma"}}]}

Usuario: "avisame en 2 minutos"
Respuesta: {"actions": [{"skill": "alarm", "action": "set", "params": {"minutes": 2, "text": "aviso"}}]}

Usuario: "recuerdame en 5 minutos tomar agua"
Respuesta: {"actions": [{"skill": "alarm", "action": "set", "params": {"minutes": 5, "text": "tomar agua"}}]}

Usuario: "que alarmas tengo"
Respuesta: {"actions": [{"skill": "alarm", "action": "list", "params": {}}]}

Usuario: "cancela las alarmas"
Respuesta: {"actions": [{"skill": "alarm", "action": "cancel", "params": {}}]}

REGLAS:
REGLA CRITICA #1 - Diferencia entre "buscar archivo" y "buscar en internet":
- Si dice "busca el archivo X", "busca mi archivo X", "encuentra el archivo X", "donde esta el archivo X"
  → SIEMPRE es {"skill": "files", "action": "find_file", "params": {"name": "X"}}
- Si dice "busca en google X", "busca en internet X", "googlea X"
  → SIEMPRE es {"skill": "browser", "action": "search_google", "params": {"query": "X"}}
- Palabras clave archivo: archivo, documento, pdf, docx, xlsx, imagen, foto, video
  → files.find_file
- Palabras clave internet: google, internet, web, online, informacion, noticias
  → browser.search_google
REGLA EXTRAER QUERY MUSICA:
- Quitar articulos y preposiciones innecesarias:
  * "la cancion X de Y" → "X Y"
  * "pon X de Y" → "X Y"
  * "musica de Y" → "Y"
  * "ponme X" → "X"
- NO incluir: "la cancion", "el video", "de", "del", "la", "el", "los", "las"
- Ejemplos:
  * "pon si estuviesemos juntos de bad bunny" → query: "si estuviesemos juntos bad bunny"
  * "pon despacito de luis fonsi" → query: "despacito luis fonsi"
  * "pon la cancion titi me pregunto" → query: "titi me pregunto"

EJEMPLOS OBLIGATORIOS:
Usuario: "busca el archivo dni guion ale"
Respuesta: {"actions": [{"skill": "files", "action": "find_file", "params": {"name": "dni"}}]}

Usuario: "busca el archivo tesis.pdf"
Respuesta: {"actions": [{"skill": "files", "action": "find_file", "params": {"name": "tesis"}}]}

Usuario: "busca mi archivo de musica"
Respuesta: {"actions": [{"skill": "files", "action": "find_file", "params": {"name": "musica"}}]}

Usuario: "busca en google el clima"
Respuesta: {"actions": [{"skill": "browser", "action": "search_google", "params": {"query": "el clima"}}]}
- Si el usuario pide varias acciones separadas por "y", "luego", ",", "despues" → devuelvelas como lista
- Si menciona youtube/yt, "pon", "reproduce", "quiero escuchar" una cancion/video → search_youtube
- En "query" SIEMPRE extrae cancion + artista:
  * "la cancion X de Y" → "X Y"
  * "musica de Y" → "Y"
- Si menciona google/internet/buscar informacion → search_google
- Si dice "el primero/uno/1" justo despues de haber listado videos → play_pending {"index": 1}
- Si dice "cancela/olvidalo/nada" cuando hay videos pendientes → cancel_pending
- Saludos/charla → none

EJEMPLOS:

Usuario: "abre youtube pon bad bunny y dale el primero"
Respuesta: {"actions": [{"skill": "browser", "action": "search_youtube", "params": {"query": "bad bunny"}}]}
(NOTA: no incluyas play_pending porque primero hay que ver la lista y luego el usuario elige)

Usuario: "abre notepad y sube el volumen"
Respuesta: {"actions": [
  {"skill": "desktop", "action": "open_app", "params": {"app": "notepad"}},
  {"skill": "desktop", "action": "volume_up", "params": {}}
]}

Usuario: "abre la carpeta de descargas y abre brave"
Respuesta: {"actions": [
  {"skill": "desktop", "action": "open_folder", "params": {"folder": "descargas"}},
  {"skill": "desktop", "action": "open_app", "params": {"app": "brave"}}
]}

Usuario: "pon si estuviesemos juntos de bad bunny"
Respuesta: {"actions": [{"skill": "browser", "action": "search_youtube", "params": {"query": "si estuviesemos juntos bad bunny"}}]}

Usuario: "el primero"
Respuesta: {"actions": [{"skill": "browser", "action": "play_pending", "params": {"index": 1}}]}

Usuario: "el dos"
Respuesta: {"actions": [{"skill": "browser", "action": "play_pending", "params": {"index": 2}}]}

Usuario: "cancela"
Respuesta: {"actions": [{"skill": "browser", "action": "cancel_pending", "params": {}}]}

Usuario: "abre notepad"
Respuesta: {"actions": [{"skill": "desktop", "action": "open_app", "params": {"app": "notepad"}}]}

Usuario: "busca en google el clima en lima"
Respuesta: {"actions": [{"skill": "browser", "action": "search_google", "params": {"query": "el clima en lima"}}]}

Usuario: "sube el volumen"
Respuesta: {"actions": [{"skill": "desktop", "action": "volume_up", "params": {}}]}

Usuario: "hola como estas"
Respuesta: {"actions": [{"skill": "none", "action": "chat", "params": {}}]}

Usuario: "pausa la musica"
Respuesta: {"actions": [{"skill": "entertainment", "action": "play_pause", "params": {}}]}

Usuario: "siguiente cancion"
Respuesta: {"actions": [{"skill": "entertainment", "action": "next_track", "params": {}}]}

Usuario: "pausa"
Respuesta: {"actions": [{"skill": "entertainment", "action": "play_pause", "params": {}}]}

Usuario: "play"
Respuesta: {"actions": [{"skill": "entertainment", "action": "play_pause", "params": {}}]}

Usuario: "pasa la cancion"
Respuesta: {"actions": [{"skill": "entertainment", "action": "next_track", "params": {}}]}

Usuario: "regresa la cancion"
Respuesta: {"actions": [{"skill": "entertainment", "action": "prev_track", "params": {}}]}

Usuario: "guarda nota comprar leche"
Respuesta: {"actions": [{"skill": "productivity", "action": "save_note", "params": {"text": "comprar leche"}}]}

Usuario: "anota que mañana hay reunion a las 3"
Respuesta: {"actions": [{"skill": "productivity", "action": "save_note", "params": {"text": "mañana hay reunion a las 3"}}]}

Usuario: "lee mis notas"
Respuesta: {"actions": [{"skill": "productivity", "action": "read_notes", "params": {}}]}

Usuario: "que notas tengo"
Respuesta: {"actions": [{"skill": "productivity", "action": "read_notes", "params": {}}]}

Usuario: "borra mis notas"
Respuesta: {"actions": [{"skill": "productivity", "action": "clear_notes", "params": {}}]}

Usuario: "bloquea la pantalla"
Respuesta: {"actions": [{"skill": "system", "action": "lock", "params": {}}]}

Usuario: "bloquea el pc"
Respuesta: {"actions": [{"skill": "system", "action": "lock", "params": {}}]}

Usuario: "apaga la pc"
Respuesta: {"actions": [{"skill": "system", "action": "shutdown", "params": {}}]}

Usuario: "reinicia la computadora"
Respuesta: {"actions": [{"skill": "system", "action": "restart", "params": {}}]}

Usuario: "cancela el apagado"
Respuesta: {"actions": [{"skill": "system", "action": "cancel_shutdown", "params": {}}]}

Usuario: "toma una captura"
Respuesta: {"actions": [{"skill": "system", "action": "screenshot", "params": {}}]}

Usuario: "captura de pantalla"
Respuesta: {"actions": [{"skill": "system", "action": "screenshot", "params": {}}]}

Usuario: "suspende el pc"
Respuesta: {"actions": [{"skill": "system", "action": "sleep", "params": {}}]}

Responde UNICAMENTE con el JSON. Sin markdown, sin texto extra."""


class IntentClassifier:
    def __init__(self):
        # Modelo rapido para clasificar (mas veloz que el 7B)
        self.model = CONFIG["models"].get("intent", CONFIG["models"]["default"])
        self.cache = {}
        print(f"[INTENT] Usando modelo: {self.model}")

    def classify(self, user_text):
        key = user_text.lower().strip()
        
        # 1. Comprobar memoria cache antes de invocar al LLM
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
            )
            raw = response["message"]["content"].strip()
            result = self._parse_json(raw)
            
            # 2. Guardar en memoria para ejecuciones futuras instantaneas
            self.cache[key] = result
            return result
        except Exception as e:
            print(f"[INTENT ERROR] {e}")
            return {"actions": [{"skill": "none", "action": "chat", "params": {}}]}

    def _parse_json(self, raw):
        raw = re.sub(r'^```(?:json)?\s*', '', raw)
        raw = re.sub(r'\s*```$', '', raw)
        match = re.search(r'\{.*\}', raw, re.DOTALL)
        if not match:
            return {"actions": [{"skill": "none", "action": "chat", "params": {}}]}
        try:
            data = json.loads(match.group(0))
            if "actions" not in data:
                return {"actions": [{"skill": "none", "action": "chat", "params": {}}]}
            return data
        except json.JSONDecodeError:
            return {"actions": [{"skill": "none", "action": "chat", "params": {}}]}