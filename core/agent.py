import json
import re
import ollama
from core.config_loader import CONFIG


AGENT_SYSTEM_PROMPT = """Eres un agente autonomo que resuelve tareas del usuario usando herramientas (skills).

Tu trabajo: dado un objetivo, decides paso a paso que skill usar hasta completarlo.

FORMATO DE RESPUESTA (obligatorio, siempre JSON valido):

Piensa y actua:
{"thought": "razonamiento breve", "action": "skill.metodo", "params": {...}}

O termina:
{"thought": "razonamiento", "final_answer": "respuesta final al usuario"}

SKILLS DISPONIBLES:

1. files.list_folder(folder, sort, filter_ext, limit)
   - folder: "descargas"|"documentos"|"escritorio"|"imagenes"|"musica"|"videos"
   - sort: "date_desc"|"date_asc"|"size_desc"|"size_asc"|"name"
   - filter_ext: extension sin punto, ej "mp4", "pdf"
   - limit: numero maximo de resultados
   - Devuelve lista de archivos con nombre, tamaño, fecha

2. files.pick(folder, criteria, filter_ext)
   - criteria: "mas_reciente"|"mas_antiguo"|"mas_grande"|"mas_pequeno"|"primero"|"ultimo"
   - Devuelve el PATH completo de UN archivo

3. files.open_path(path)
   - Abre un archivo o carpeta con el programa por defecto

4. files.find_file(name)
   - Busca archivos por nombre en carpetas comunes

5. files.info(path)
   - Informacion detallada de un archivo (tamaño, fecha, tipo)

6. browser.search_youtube(query)
7. browser.search_google(query)
8. browser.open_url(url)

9. desktop.open_app(app)
   - app: "brave"|"chrome"|"notepad"|"calculadora"|"explorador"|"paint"|"cmd"|"spotify"

10. desktop.volume_up() | desktop.volume_down() | desktop.mute()

11. system.screenshot() | system.lock()

12. productivity.save_note(text) | productivity.read_notes()

13. weather.current(city)

14. translate.text(text, to)

15. alarm.set(minutes, text) | alarm.list() | alarm.cancel()

REGLAS:
- Responde SOLO JSON, sin markdown, sin texto extra
- Usa UN solo paso por respuesta. Espera el resultado antes del siguiente.
- Si el usuario pidio algo simple (abrir X, buscar Y), un solo paso basta.
- Si necesitas informacion (listar archivos, buscar), hazlo paso a paso.
- Cuando tengas la respuesta final, usa "final_answer".
- Maximo usa los 5 pasos disponibles.
- Los parametros van en "params" como objeto.
- Si una skill falla, intenta otra ruta o da un final_answer explicando.

EJEMPLOS:

Objetivo: "abre el ultimo archivo de la carpeta descargas"
Paso 1: {"thought": "Necesito el archivo mas reciente en descargas", "action": "files.pick", "params": {"folder": "descargas", "criteria": "mas_reciente"}}
Resultado: {"path": "C:/Users/alein/Downloads/video.mp4", "name": "video.mp4"}
Paso 2: {"thought": "Ya tengo la ruta, ahora lo abro", "action": "files.open_path", "params": {"path": "C:/Users/alein/Downloads/video.mp4"}}
Resultado: "Abriendo video.mp4."
Paso 3: {"thought": "Listo", "final_answer": "Listo, abri video.mp4"}

Objetivo: "cuantos archivos pdf tengo en descargas"
Paso 1: {"thought": "Necesito listar los pdf de descargas", "action": "files.list_folder", "params": {"folder": "descargas", "filter_ext": "pdf"}}
Resultado: [lista de 8 pdfs]
Paso 2: {"thought": "Hay 8", "final_answer": "Tienes 8 archivos PDF en descargas"}

Objetivo: "abre notepad"
Paso 1: {"thought": "Es directo", "action": "desktop.open_app", "params": {"app": "notepad"}}
Resultado: "Abriendo notepad."
Paso 2: {"thought": "Listo", "final_answer": "Listo, abri Notepad"}

Objetivo: "que clima hace en lima y pon musica de bad bunny"
Paso 1: {"thought": "Primero el clima", "action": "weather.current", "params": {"city": "lima"}}
Resultado: "Lima: 20 grados, mayormente despejado"
Paso 2: {"thought": "Ahora la musica", "action": "browser.search_youtube", "params": {"query": "bad bunny"}}
Resultado: "5 canciones encontradas"
Paso 3: {"thought": "Ambas hechas", "final_answer": "En Lima esta mayormente despejado, 20 grados. Y ya busque Bad Bunny en YouTube."}

Objetivo: "cual es el archivo mas grande en documentos"
Paso 1: {"thought": "Buscar el mas grande en documentos", "action": "files.pick", "params": {"folder": "documentos", "criteria": "mas_grande"}}
Resultado: {"path": "C:/Users/alein/Documents/pelicula.mp4", "name": "pelicula.mp4", "size_kb": 500000}
Paso 2: {"thought": "El mas grande es pelicula.mp4", "final_answer": "El archivo mas grande en documentos es pelicula.mp4 (500 MB)"}

Objetivo: "hay algun archivo mp4 en descargas"
Paso 1: {"thought": "Buscar mp4 en descargas", "action": "files.list_folder", "params": {"folder": "descargas", "filter_ext": "mp4"}}
Resultado: {"thought": "Listar descargas", "data": [{"name": "video.mp4", "size_kb": 5000}]}
Paso 2: {"thought": "Si hay mp4", "final_answer": "Si, hay archivos mp4 en descargas"}
"""

class Agent:
    def __init__(self):
        self.model = CONFIG["models"].get("reasoning", CONFIG["models"]["default"])
        self.max_steps = 5

    def run(self, user_input, skills, on_step=None):
        """
        Ejecuta el bucle ReAct.
        
        Args:
            user_input: el objetivo del usuario
            skills: dict {nombre: instancia_skill}
            on_step: callback(step_dict) para notificar cada paso (opcional)
        
        Returns:
            dict con {voice, display, thought, steps}
        """
        messages = [
            {"role": "system", "content": AGENT_SYSTEM_PROMPT},
            {"role": "user", "content": f"Objetivo: {user_input}"},
        ]

        steps_log = []  # historial visible
        display_lines = []  # lineas para la consola/gui
        voice_parts = []

        for step_num in range(1, self.max_steps + 1):
            # Llamar al LLM
            try:
                response = ollama.chat(
                    model=self.model,
                    messages=messages,
                    options={"temperature": 0.1},
                )
                raw = response["message"]["content"].strip()
            except Exception as e:
                return {
                    "voice": "Hubo un error pensando.",
                    "display": f"Error del LLM: {e}",
                    "thought": "Error",
                    "steps": steps_log,
                }

            # Parsear JSON
                        # Parsear JSON
            parsed = self._parse_json(raw)

            # Si falla el parse, retry con instrucción más estricta
            if not parsed:
                print(f"[AGENT] Parse fallo, reintentando. Raw: {raw[:200]}")
                messages.append({"role": "assistant", "content": raw})
                messages.append({
                    "role": "user",
                    "content": (
                        "Tu respuesta anterior NO fue JSON valido. "
                        "Responde SOLO con JSON puro. Sin markdown, sin texto antes ni despues. "
                        "Empieza con { y termina con }. Ejemplo: "
                        "{\"thought\": \"...\", \"action\": \"skill.metodo\", \"params\": {...}}"
                    ),
                })
                try:
                    retry = ollama.chat(
                        model=self.model,
                        messages=messages,
                        options={"temperature": 0.0},
                    )
                    parsed = self._parse_json(retry["message"]["content"].strip())
                except Exception:
                    parsed = None

                if not parsed:
                    return {
                        "voice": "No pude procesar la tarea.",
                        "display": f"El agente no dio JSON valido. Ultimo intento: {raw[:200]}",
                        "thought": "Parse error tras retry",
                        "steps": steps_log,
                    }

            thought = parsed.get("thought", "")

            # Caso 1: respuesta final
            if "final_answer" in parsed:
                final = parsed["final_answer"]
                steps_log.append({"step": step_num, "type": "final", "text": thought})
                return {
                    "voice": final,
                    "display": final,
                    "thought": " | ".join(s.get("text", "") for s in steps_log if s.get("text")),
                    "steps": steps_log,
                }

            # Caso 2: ejecutar accion
            action = parsed.get("action", "")
            params = parsed.get("params", {}) or {}

            if not action:
                return {
                    "voice": "No se que hacer.",
                    "display": "El agente no especifico accion ni respuesta.",
                    "thought": thought,
                    "steps": steps_log,
                }

            # Notificar al UI
            if on_step:
                on_step({"step": step_num, "thought": thought, "action": action, "params": params})

            # Ejecutar skill
            result_str = self._execute_action(action, params, skills)

            # Log
            step_info = {
                "step": step_num,
                "type": "action",
                "text": thought,
                "action": action,
                "params": params,
                "result": result_str[:200],  # truncar
            }
            steps_log.append(step_info)

            display_lines.append(f"  {step_num}. {action} → {result_str[:100]}")
            voice_parts.append(thought)

            # Añadir al historial de mensajes
            messages.append({"role": "assistant", "content": raw})
            messages.append({
                "role": "user",
                "content": f"Resultado del paso {step_num}: {result_str}",
            })

        # Se acabaron los pasos sin final_answer
        return {
            "voice": "No pude completar la tarea en el limite de pasos.",
            "display": "Se alcanzo el maximo de 5 pasos:\n" + "\n".join(display_lines),
            "thought": " | ".join(voice_parts),
            "steps": steps_log,
        }

    def _parse_json(self, raw):
        """Parser robusto: intenta extraer JSON aunque venga con texto extra."""
        # 1. Limpiar fences markdown
        raw = re.sub(r'^```(?:json)?\s*', '', raw.strip())
        raw = re.sub(r'\s*```$', '', raw)

        # 2. Intentar parsear directo
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            pass

        # 3. Buscar el primer JSON balanceado
        start = raw.find("{")
        if start == -1:
            return None

        depth = 0
        for i in range(start, len(raw)):
            if raw[i] == "{":
                depth += 1
            elif raw[i] == "}":
                depth -= 1
                if depth == 0:
                    candidate = raw[start:i + 1]
                    try:
                        return json.loads(candidate)
                    except json.JSONDecodeError:
                        # Intentar reparar comillas simples
                        candidate = candidate.replace("'", '"')
                        try:
                            return json.loads(candidate)
                        except json.JSONDecodeError:
                            break

        return None

    def _execute_action(self, action, params, skills):
        """Ejecuta skill.metodo(params). Devuelve string con el resultado."""
        if "." not in action:
            return f"Accion invalida: {action}"

        skill_name, method_name = action.split(".", 1)
        skill = skills.get(skill_name)
        if not skill:
            return f"Skill desconocida: {skill_name}"

        try:
            # Llamar al metodo. Las skills viejas usan run(action, params),
            # pero las nuevas del agente exponen los metodos directos.
            result = skill.run(method_name, params)
            if result is None:
                return "Sin resultado."
            if isinstance(result, dict):
                # Convertir dict a string legible para el LLM
                return json.dumps(result, ensure_ascii=False)
            return str(result)
        except Exception as e:
            return f"Error en {action}: {e}"