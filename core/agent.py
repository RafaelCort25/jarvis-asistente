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

Si necesitas pedir informacion al usuario (no la tienes y no puedes deducirla), usa:
{"thought": "razonamiento", "ask": "pregunta al usuario"}

SKILLS DISPONIBLES:

=== ARCHIVOS Y SISTEMA ===
1. files.list_folder(folder, sort, filter_ext, limit)
   - folder: "descargas"|"documentos"|"escritorio"|"imagenes"|"musica"|"videos"
2. files.pick(folder, criteria, filter_ext) - criteria: "mas_reciente"|"mas_grande"|"primero"
3. files.open_path(path)
4. files.find_file(name)
5. files.info(path)
6. desktop.open_app(app) - app: "brave"|"chrome"|"notepad"|"calculadora"|"explorador"|"paint"|"cmd"|"spotify"
7. desktop.volume_up() | desktop.volume_down() | desktop.mute()
8. system.time() | system.date() | system.screenshot()
9. system.disk_info() | system.list_big_files(folder, min_mb) | system.list_startup()
10. clipboard.read() | clipboard.write(text)

=== WEB Y COMUNICACION ===
11. browser.search_youtube(query) | browser.search_google(query) | browser.open_url(url)
12. telegram.send_last(tipo) | telegram.send_file(path)

=== PRODUCTIVIDAD ===
13. productivity.save_note(text) | productivity.read_notes()
14. weather.current(city)
15. translate.text(text, to)
16. alarm.set(minutes, text) | alarm.list() | alarm.cancel()
17. scheduler.add_once(seconds, message) | scheduler.add_daily(time, message) | scheduler.list()

=== DESARROLLO ===
18. dev.generate_code(description, language)
    - language: "python"|"javascript"|"java"|"c"|"cpp"|"csharp"|"go"|"rust"|"ruby"|"php"
19. dev.review_file(path) | dev.review_project(path) | dev.explain(path) | dev.find_issues(path)
20. dev.review_to_excel(path, output) | dev.review_to_word(path, output)
21. git.status() | git.diff() | git.log(n)

=== DOCUMENTOS Y OFICINA ===
22. docs.ask(query) - pregunta sobre los documentos del usuario
23. docs.ask_to_word(query, title)
24. docs.index_file(path) | docs.index_folder(path) | docs.list()
25. office.create_doc(description, path, title) | office.create_xlsx(description, path) | office.create_ppt(description, path)
26. office.read_doc(path) | office.read_xlsx(path) | office.read_ppt(path)
27. pdf.from_docx(path, output)
28. edit.modify(path, instruction, output)

=== IMAGENES Y EDUCACION ===
29. image.generate(prompt, width, height) | image.to_word(prompt, count, title)
30. education.pseint(description) | education.diagram(description, kind) | education.convert(code, to_language)

=== OTROS ===
31. vision.describe_screen() | vision.explain_screen_code()
32. spotify.play(query) | spotify.pause() | spotify.next() | spotify.current()

REGLAS:
- Responde SOLO JSON, sin markdown, sin texto extra.
- Usa UN solo paso por respuesta. Espera el resultado antes del siguiente.
- Si el objetivo es simple (abrir X, buscar Y), un solo paso basta.
- Para tareas multi-paso, encadena acciones usando resultados anteriores.
- Cuando tengas la respuesta final, usa "final_answer".
- Si te falta informacion que SOLO el usuario puede dar, usa "ask".
- Maximo usa los 12 pasos disponibles.
- Si una skill falla, ANALIZA el error y prueba OTRA ruta. NO repitas la misma accion.
- NUNCA inventes paths. Si no sabes un path, usa files.find_file primero.

VERIFICACION OBLIGATORIA ANTES DE "final_answer":
Antes de terminar, comprueba:
1. ¿Cumpli TODOS los objetivos de la frase del usuario?
2. Si el usuario pidio 2+ cosas (unidas por "y", "tambien", "ademas"), ¿hice TODAS?
3. Si el usuario pidio informacion de 2 fuentes distintas, ¿consulte AMBAS?

Si la respuesta es NO, NO uses "final_answer". Ejecuta el siguiente paso.

EJEMPLOS:

Objetivo: "abre el ultimo archivo de descargas"
Paso 1: {"thought": "Necesito el archivo mas reciente", "action": "files.pick", "params": {"folder": "descargas", "criteria": "mas_reciente"}}
Resultado: {"path": "C:/Users/alein/Downloads/video.mp4"}
Paso 2: {"thought": "Ya tengo la ruta", "action": "files.open_path", "params": {"path": "C:/Users/alein/Downloads/video.mp4"}}
Paso 3: {"thought": "Listo", "final_answer": "Listo, abri video.mp4"}

Objetivo: "cuanto espacio tengo y que programas arrancan con windows"
Paso 1: {"thought": "Primero el disco", "action": "system.disk_info", "params": {}}
Resultado: "C: 511 GB total, 132 GB libres"
Paso 2: {"thought": "Ahora los programas de inicio", "action": "system.list_startup", "params": {}}
Resultado: "12 programas: OneDrive, Steam..."
Paso 3: {"thought": "Ya tengo ambas cosas", "final_answer": "Tienes 511 GB en C: con 132 GB libres. Y 12 programas arrancan con Windows."}

Objetivo: "crea un chatbot de whatsapp para una clinica dental"
Paso 1: {"thought": "Necesito saber el tono", "ask": "¿Que tono quieres para el chatbot? (formal / cercano / profesional)"}
(User responde: "profesional")
Paso 2: {"thought": "Genero un workflow base", "action": "dev.generate_code", "params": {"description": "workflow n8n de chatbot whatsapp para clinica dental, tono profesional", "language": "python"}}
Paso 3: {"thought": "Listo", "final_answer": "Workflow generado. Guardado en sandbox."}

EJEMPLO DE ERROR RECUPERADO:
Paso 1: {"thought": "Busco el archivo", "action": "files.open_path", "params": {"path": "C:/ruta/inventada.pdf"}}
Resultado: "Error en files.open_path: archivo no encontrado"
Paso 2: {"thought": "La ruta no existia, mejor busco el archivo primero", "action": "files.find_file", "params": {"name": "factura"}}
Resultado: [lista de archivos]
Paso 3: {"thought": "Ya tengo la ruta correcta", "action": "files.open_path", "params": {"path": "..."}}
"""


class Agent:
    def __init__(self):
        self.model = CONFIG["models"].get("reasoning", CONFIG["models"]["default"])
        self.max_steps = 12
        # Estado pendiente cuando el agente pregunta algo y espera respuesta
        self._pending_state = None

    def has_pending_question(self):
        """True si el agente hizo una pregunta y espera respuesta del usuario."""
        return self._pending_state is not None

    def clear_pending(self):
        """Limpia cualquier estado pendiente."""
        self._pending_state = None

    def run(self, user_input, skills, on_step=None):
        """Ejecuta el bucle ReAct desde cero."""
        messages = [
            {"role": "system", "content": AGENT_SYSTEM_PROMPT},
            {"role": "user", "content": f"Objetivo: {user_input}"},
        ]
        return self._run_loop(messages, [], 1, skills, on_step)

    def resume(self, user_response, skills, on_step=None):
        """Continua la ejecucion desde donde el agente pregunto."""
        if not self._pending_state:
            return None

        state = self._pending_state
        self._pending_state = None

        messages = state["messages"]
        steps_log = state["steps_log"]
        next_step = state["step_num"]

        # Inyectar la respuesta del usuario
        messages.append({
            "role": "user",
            "content": f"Respuesta del usuario a tu pregunta: {user_response}",
        })

        return self._run_loop(messages, steps_log, next_step, skills, on_step)

    def _run_loop(self, messages, steps_log, start_step, skills, on_step):
        """Bucle ReAct principal (reutilizable por run y resume)."""
        display_lines = []
        voice_parts = []

        for step_num in range(start_step, self.max_steps + 1):
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
            parsed = self._parse_json(raw)

            # Retry si falla el parse
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

            # Caso 0: el agente pide informacion al usuario
            if "ask" in parsed:
                question = parsed["ask"]
                steps_log.append({"step": step_num, "type": "ask", "text": question})

                # Guardar estado para poder reanudar
                self._pending_state = {
                    "messages": messages,
                    "steps_log": steps_log,
                    "step_num": step_num + 1,
                }

                print(f"[AGENT] Pregunta pendiente: {question}")
                return {
                    "voice": question,
                    "display": question,
                    "thought": f"Pregunta al usuario: {question}",
                    "steps": steps_log,
                    "needs_answer": True,
                }

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

            # AUTO-VERIFICACION: detectar si el paso fallo
            if self._looks_like_error(result_str):
                print(f"[AGENT] Paso {step_num} fallo: {result_str[:120]}")
                steps_log.append({
                    "step": step_num,
                    "type": "error",
                    "text": thought,
                    "action": action,
                    "params": params,
                    "result": result_str[:200],
                })
                display_lines.append(f"  {step_num}. {action} -> FALLO")
                voice_parts.append(thought)

                messages.append({"role": "assistant", "content": raw})
                messages.append({
                    "role": "user",
                    "content": (
                        f"El paso {step_num} FALLO con: {result_str}\n\n"
                        "Analiza por que fallo y prueba OTRA ruta. "
                        "NO repitas la misma accion con los mismos parametros. "
                        "Si no hay otra ruta posible, usa final_answer explicando el problema."
                    ),
                })
                continue

            # Paso exitoso: loggear
            step_info = {
                "step": step_num,
                "type": "action",
                "text": thought,
                "action": action,
                "params": params,
                "result": result_str[:200],
            }
            steps_log.append(step_info)

            display_lines.append(f"  {step_num}. {action} -> {result_str[:100]}")
            voice_parts.append(thought)

            messages.append({"role": "assistant", "content": raw})
            messages.append({
                "role": "user",
                "content": f"Resultado del paso {step_num}: {result_str}",
            })

        # Se acabaron los pasos sin final_answer
        return {
            "voice": "No pude completar la tarea en el limite de pasos.",
            "display": f"Se alcanzo el maximo de {self.max_steps} pasos:\n" + "\n".join(display_lines),
            "thought": " | ".join(voice_parts),
            "steps": steps_log,
        }

    def _looks_like_error(self, result_str):
        """Detecta si el resultado de un paso parece un error."""
        if result_str is None:
            return True
        s = str(result_str).strip()
        if not s:
            return True
        low = s.lower()
        markers = [
            "error en ",
            "error al ",
            "skill desconocida",
            "accion invalida",
            "action invalida",
            "sin resultado",
            "[error",
            "[error llm]",
            "no se pudo",
            "no pude ",
            "timeout",
            "tardo demasiado",
            "no encontre el macro",
            "no encontre la carpeta",
        ]
        return any(m in low for m in markers)

    def _parse_json(self, raw):
        """Parser robusto: intenta extraer JSON aunque venga con texto extra."""
        raw = re.sub(r'^```(?:json)?\s*', '', raw.strip())
        raw = re.sub(r'\s*```$', '', raw)

        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            pass

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
            from core import confirmation
            summary = f"Agente quiere ejecutar: {action}"
            if not confirmation.require(skill_name, method_name, summary):
                return "El usuario rechazo esta accion. Busca otra forma o usa final_answer."
        except Exception as e:
            print(f"[AGENT] Confirmacion fallo: {e}")

        try:
            result = skill.run(method_name, params)
            if result is None:
                return "Sin resultado."
            if isinstance(result, dict):
                return json.dumps(result, ensure_ascii=False)
            return str(result)
        except Exception as e:
            return f"Error en {action}: {e}"