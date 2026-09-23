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
   - sort: "date_desc"|"date_asc"|"size_desc"|"size_asc"|"name"
   - filter_ext: extension sin punto (ej "pdf")
2. files.pick(folder, criteria, filter_ext) — criteria: "mas_reciente"|"mas_grande"|"primero"
3. files.open_path(path)
4. files.find_file(name)
5. files.info(path)
6. desktop.open_app(app) — app: "brave"|"chrome"|"notepad"|"calculadora"|"explorador"|"paint"|"cmd"|"spotify"
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
20. dev.review_to_excel(path, output) — genera Excel con analisis
21. dev.review_to_word(path, output) — genera Word con analisis
22. git.status() | git.diff() | git.log(n)

=== DOCUMENTOS Y OFICINA ===
23. docs.ask(query) — pregunta sobre los documentos del usuario (CV, apuntes, PDFs)
24. docs.ask_to_word(query, title) — RAG + Word
25. docs.index_file(path) | docs.index_folder(path) | docs.list()
26. office.create_doc(description, path, title) — Word
27. office.create_xlsx(description, path) — Excel
28. office.create_ppt(description, path)
29. office.read_doc(path) | office.read_xlsx(path) | office.read_ppt(path)
30. pdf.from_docx(path, output)
31. edit.modify(path, instruction, output) — edita archivo segun instrucciones

=== IMAGENES Y EDUCACION ===
32. image.generate(prompt, width, height) — genera imagen con IA
33. image.to_word(prompt, count, title) — N imagenes + Word
34. education.pseint(description) — pseudocodigo PSeInt
35. education.diagram(description, kind) — kind: "flowchart"|"sequence"|"class"|"state"|"er"
36. education.convert(code, to_language) — convierte codigo entre lenguajes

=== OTROS ===
37. vision.describe_screen() | vision.explain_screen_code()
38. spotify.play(query) | spotify.pause() | spotify.next() | spotify.current()

REGLAS:
- Responde SOLO JSON, sin markdown, sin texto extra.
- Usa UN solo paso por respuesta. Espera el resultado antes del siguiente.
- Si el objetivo es simple (abrir X, buscar Y), un solo paso basta.
- Para tareas multi-paso, encadena acciones usando resultados anteriores.
- Cuando tengas la respuesta final, usa "final_answer".
- Si te falta informacion que SOLO el usuario puede dar (nombre de empresa, tono, preferencias), usa "ask".
- Maximo usa los 12 pasos disponibles.
- Si una skill falla, intenta otra ruta o usa "final_answer" explicando.
- NUNCA inventes paths. Si no sabes un path, usa files.find_file primero.

EJEMPLOS:

Objetivo: "abre el ultimo archivo de descargas"
Paso 1: {"thought": "Necesito el archivo mas reciente", "action": "files.pick", "params": {"folder": "descargas", "criteria": "mas_reciente"}}
Resultado: {"path": "C:/Users/alein/Downloads/video.mp4"}
Paso 2: {"thought": "Ya tengo la ruta", "action": "files.open_path", "params": {"path": "C:/Users/alein/Downloads/video.mp4"}}
Paso 3: {"thought": "Listo", "final_answer": "Listo, abri video.mp4"}

Objetivo: "revisa mi CV y dime mis 5 fortalezas, guarda en Word"
Paso 1: {"thought": "Consulto el RAG", "action": "docs.ask", "params": {"query": "cuales son mis 5 fortalezas profesionales"}}
Resultado: {"answer": "...", "sources": [...]}
Paso 2: {"thought": "Guardo en Word", "action": "docs.ask_to_word", "params": {"query": "cuales son mis 5 fortalezas profesionales", "title": "Mis 5 Fortalezas"}}
Paso 3: {"thought": "Listo", "final_answer": "Word creado con tus 5 fortalezas"}

Objetivo: "crea un chatbot de whatsapp para una clinica dental"
Paso 1: {"thought": "Necesito saber el tono", "ask": "¿Que tono quieres para el chatbot? (formal / cercano / profesional)"}
(User responde: "profesional")
Paso 2: {"thought": "Genero un workflow base", "action": "dev.generate_code", "params": {"description": "workflow n8n de chatbot whatsapp para clinica dental, tono profesional", "language": "python"}}
"""


class Agent:
    def __init__(self):
        self.model = CONFIG["models"].get("reasoning", CONFIG["models"]["default"])
        self.max_steps = 12

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

        steps_log = []
        display_lines = []
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
            parsed = self._parse_json(raw)

            # Si falla el parse, retry con instruccion mas estricta
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

            # Log
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

            # Anadir al historial de mensajes
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

        # Respetar confirmacion para acciones riesgosas
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