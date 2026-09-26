"""Skill de n8n: controla workflows + busca/importa templates de n8n.io."""
import json
import re
import uuid
from pathlib import Path

import ollama
import requests

from skills.base import Skill
from core import confirmation

ROOT = Path(__file__).resolve().parent.parent
ENV_FILE = ROOT / ".env.n8n.tmp"
TIMEOUT = 20
N8N_IO_API = "https://api.n8n.io/api"
# Tipos de nodo que el LLM puede usar (whitelist)
# Fuente: https://docs.n8n.io/integrations/
NODE_WHITELIST = {
    # Triggers
    "n8n-nodes-base.scheduleTrigger",
    "n8n-nodes-base.webhook",
    "n8n-nodes-base.manualTrigger",
    "n8n-nodes-base.emailReadImap",
    "n8n-nodes-base.telegramTrigger",
    "n8n-nodes-base.slackTrigger",
    "n8n-nodes-base.whatsAppTrigger",
    # Utils
    "n8n-nodes-base.httpRequest",
    "n8n-nodes-base.code",
    "n8n-nodes-base.set",
    "n8n-nodes-base.if",
    "n8n-nodes-base.switch",
    "n8n-nodes-base.merge",
    "n8n-nodes-base.noOp",
    "n8n-nodes-base.wait",
    "n8n-nodes-base.splitInBatches",
    "n8n-nodes-base.removeDuplicates",
    # Comunicación
    "n8n-nodes-base.telegram",
    "n8n-nodes-base.slack",
    "n8n-nodes-base.discord",
    "n8n-nodes-base.emailSend",
    "n8n-nodes-base.gmail",
    "n8n-nodes-base.whatsApp",
    # Datos
    "n8n-nodes-base.googleSheets",
    "n8n-nodes-base.postgres",
    "n8n-nodes-base.mysql",
    "n8n-nodes-base.supabase",
    "n8n-nodes-base.redis",
    "n8n-nodes-base.mongodb",
    # IA
    "@n8n/n8n-nodes-langchain.agent",
    "@n8n/n8n-nodes-langchain.chainLlm",
    "@n8n/n8n-nodes-langchain.lmChatOpenAi",
    "@n8n/n8n-nodes-langchain.lmChatOllama",
    "@n8n/n8n-nodes-langchain.memoryBufferWindow",
}


def _load_env():
    """Carga N8N_API_KEY y N8N_URL del archivo .env.n8n.tmp."""
    if not ENV_FILE.exists():
        return None, None
    api_key = None
    base_url = None
    try:
        for line in ENV_FILE.read_text(encoding="utf-8-sig").splitlines():
            line = line.strip()
            if line.startswith("N8N_API_KEY="):
                api_key = line.split("=", 1)[1].strip()
            elif line.startswith("N8N_URL="):
                base_url = line.split("=", 1)[1].strip()
    except Exception as e:
        print(f"[N8N] Error leyendo env: {e}")
        return None, None
    return api_key, base_url


class N8nSkill(Skill):
    name = "n8n"
    description = "Controla n8n: lista workflows, busca/importa templates de n8n.io"

    def _headers(self):
        api_key, _ = _load_env()
        if not api_key:
            return None
        return {
            "X-N8N-API-KEY": api_key,
            "Content-Type": "application/json",
        }

    def _url(self, path):
        _, base = _load_env()
        if not base:
            return None
        return f"{base.rstrip('/')}{path}"

    # ─── DISPATCHER ──────────────────────────────────────────────────────

    def run(self, action, params):
        # Locales (tu n8n)
        if action == "list_workflows":
            return self._list_workflows()
        if action == "get_workflow":
            return self._get_workflow(params.get("id_or_name", ""))
        if action == "activate":
            return self._set_active(params.get("id_or_name", ""), True)
        if action == "deactivate":
            return self._set_active(params.get("id_or_name", ""), False)
        if action == "delete_workflow":
            return self._delete_workflow(params.get("id_or_name", ""))
        if action == "list_executions":
            return self._list_executions()

        # Templates de n8n.io
        if action == "search_templates":
            return self._search_templates(
                params.get("query", ""),
                int(params.get("limit", 5) or 5),
            )
        if action == "get_template":
            return self._get_template_action(params.get("id", ""))
        if action == "import_template":
            return self._import_template(
                params.get("id", ""),
                params.get("name", ""),
            )
        if action == "import_template":
            return self._import_template(
                params.get("id", ""),
                params.get("name", ""),
            )
        if action == "create_workflow":
            return self._create_workflow(
                params.get("description", ""),
                params.get("name", ""),
            )

        return f"Accion desconocida en n8n: {action}"

    # ─── HELPERS LOCALES ─────────────────────────────────────────────────

    def _api_get(self, path):
        headers = self._headers()
        url = self._url(path)
        if not headers or not url:
            return None, "No hay configuracion de n8n (.env.n8n.tmp)."
        try:
            r = requests.get(url, headers=headers, timeout=TIMEOUT)
            if r.status_code != 200:
                return None, f"n8n respondio {r.status_code}: {r.text[:200]}"
            return r.json(), None
        except requests.exceptions.ConnectionError:
            return None, "No puedo conectar con n8n. Verifica que corre en http://localhost:5678"
        except Exception as e:
            return None, f"Error consultando n8n: {e}"

    def _api_post(self, path, data=None):
        headers = self._headers()
        url = self._url(path)
        if not headers or not url:
            return None, "No hay configuracion de n8n."
        try:
            r = requests.post(url, headers=headers, json=data or {}, timeout=TIMEOUT)
            if r.status_code not in (200, 201):
                return None, f"n8n respondio {r.status_code}: {r.text[:300]}"
            return r.json() if r.text else {}, None
        except Exception as e:
            return None, f"Error: {e}"

    def _api_delete(self, path):
        headers = self._headers()
        url = self._url(path)
        if not headers or not url:
            return None, "No hay configuracion de n8n."
        try:
            r = requests.delete(url, headers=headers, timeout=TIMEOUT)
            if r.status_code not in (200, 204):
                return None, f"n8n respondio {r.status_code}: {r.text[:200]}"
            return {}, None
        except Exception as e:
            return None, f"Error: {e}"

    def _find_workflow(self, id_or_name):
        id_or_name = (id_or_name or "").strip()
        if not id_or_name:
            return None, "Falta el nombre o ID del workflow."

        data, err = self._api_get("/api/v1/workflows")
        if err:
            return None, err

        workflows = data.get("data", [])
        for w in workflows:
            if w.get("id") == id_or_name:
                return w, None

        target = id_or_name.lower()
        for w in workflows:
            if (w.get("name") or "").lower() == target:
                return w, None

        candidatos = [w for w in workflows if target in (w.get("name") or "").lower()]
        if len(candidatos) == 1:
            return candidatos[0], None
        if len(candidatos) > 1:
            nombres = [w.get("name") for w in candidatos[:5]]
            return None, f"Hay varios workflows que coinciden: {nombres}. Se mas especifico."

        return None, f"No encontre workflow con '{id_or_name}'."

    # ─── ACCIONES LOCALES ────────────────────────────────────────────────

    def _list_workflows(self):
        data, err = self._api_get("/api/v1/workflows")
        if err:
            return {"thought": "Error n8n", "display": err, "voice": "No pude consultar n8n."}

        workflows = data.get("data", [])
        if not workflows:
            return {
                "thought": "",
                "display": "No hay workflows en n8n todavia.",
                "voice": "No tienes workflows en n8n.",
            }

        lineas = [f"Workflows en n8n ({len(workflows)}):"]
        for w in workflows[:20]:
            nombre = w.get("name", "(sin nombre)")
            activo = "ON " if w.get("active") else "off"
            wid = w.get("id", "?")[:8]
            lineas.append(f"  [{activo}] {nombre}  (id: {wid}...)")

        return {
            "thought": f"{len(workflows)} workflows",
            "display": "\n".join(lineas),
            "voice": f"Tienes {len(workflows)} workflows en n8n.",
        }

    def _get_workflow(self, id_or_name):
        w, err = self._find_workflow(id_or_name)
        if err:
            return {"thought": "No encontrado", "display": err, "voice": "No lo encontre."}

        nombre = w.get("name", "?")
        activo = "activado" if w.get("active") else "desactivado"
        nodes = w.get("nodes", [])

        detalle = [
            f"Workflow: {nombre}",
            f"  ID: {w.get('id')}",
            f"  Estado: {activo}",
            f"  Nodos: {len(nodes)}",
        ]
        if nodes:
            detalle.append("  Pasos:")
            for n in nodes[:8]:
                detalle.append(f"    - {n.get('name', '?')} ({n.get('type', '?').split('.')[-1]})")

        return {
            "thought": f"Workflow {nombre}",
            "display": "\n".join(detalle),
            "voice": f"El workflow {nombre} esta {activo} con {len(nodes)} pasos.",
        }

    def _set_active(self, id_or_name, activate):
        w, err = self._find_workflow(id_or_name)
        if err:
            return {"thought": "No encontrado", "display": err, "voice": "No lo encontre."}

        wid = w.get("id")
        nombre = w.get("name")
        accion = "activar" if activate else "desactivar"

        if not confirmation.require(
            "n8n", "activate" if activate else "deactivate",
            f"{accion.capitalize()} workflow '{nombre}'"
        ):
            return {"thought": "", "display": "Cancelado.", "voice": "Cancelado."}

        endpoint = "activate" if activate else "deactivate"
        result, err = self._api_post(f"/api/v1/workflows/{wid}/{endpoint}")
        if err:
            return {"thought": "Error n8n", "display": err, "voice": "No pude cambiar el estado."}

        estado = "activado" if activate else "desactivado"
        return {
            "thought": f"Workflow {nombre} {estado}",
            "display": f"Workflow '{nombre}' {estado}.",
            "voice": f"Workflow {nombre} {estado}.",
        }

    def _delete_workflow(self, id_or_name):
        w, err = self._find_workflow(id_or_name)
        if err:
            return {"thought": "No encontrado", "display": err, "voice": "No lo encontre."}

        wid = w.get("id")
        nombre = w.get("name")

        if not confirmation.require("n8n", "delete_workflow", f"Borrar workflow '{nombre}' permanentemente"):
            return {"thought": "", "display": "Cancelado.", "voice": "Cancelado."}

        _, err = self._api_delete(f"/api/v1/workflows/{wid}")
        if err:
            return {"thought": "Error n8n", "display": err, "voice": "No pude borrarlo."}

        return {
            "thought": f"Workflow {nombre} borrado",
            "display": f"Workflow '{nombre}' eliminado permanentemente.",
            "voice": f"Workflow {nombre} eliminado.",
        }

    def _list_executions(self):
        data, err = self._api_get("/api/v1/executions?limit=10")
        if err:
            return {"thought": "Error n8n", "display": err, "voice": "No pude consultar ejecuciones."}

        ejecuciones = data.get("data", [])
        if not ejecuciones:
            return {
                "thought": "",
                "display": "No hay ejecuciones registradas.",
                "voice": "No hay ejecuciones.",
            }

        lineas = [f"Ultimas ejecuciones ({len(ejecuciones)}):"]
        for e in ejecuciones[:10]:
            wid = e.get("workflowId", "?")[:8]
            status = e.get("status", "?")
            started = (e.get("startedAt") or "")[:19].replace("T", " ")
            lineas.append(f"  [{status}] wf:{wid}... {started}")

        return {
            "thought": f"{len(ejecuciones)} ejecuciones",
            "display": "\n".join(lineas),
            "voice": f"Tienes {len(ejecuciones)} ejecuciones recientes.",
        }

    # ─── TEMPLATES (n8n.io) ──────────────────────────────────────────────

    def _search_templates(self, query, limit=5):
        query = (query or "").strip()
        if not query:
            return {"thought": "", "display": "Dime que buscar en templates.", "voice": "Dime que buscar."}

        try:
            r = requests.get(
                f"{N8N_IO_API}/templates/search",
                params={"query": query, "rows": limit},
                timeout=TIMEOUT,
            )
            if r.status_code != 200:
                return {
                    "thought": "Error n8n.io",
                    "display": f"n8n.io respondio {r.status_code}",
                    "voice": "No pude consultar templates.",
                }
            data = r.json()
        except Exception as e:
            return {
                "thought": "Error n8n.io",
                "display": f"Error buscando templates: {e}",
                "voice": "No pude consultar templates.",
            }

        workflows = data.get("workflows", [])
        total = data.get("totalWorkflows", 0)

        if not workflows:
            return {
                "thought": "",
                "display": f"No encontre templates para '{query}'.",
                "voice": f"No encontre templates para {query}.",
            }

        lineas = [f"Templates de n8n.io para '{query}' (mostrando {len(workflows)} de {total}):"]
        for i, w in enumerate(workflows, 1):
            nombre = w.get("name", "?")
            views = w.get("totalViews", 0)
            wid = w.get("id", "?")
            lineas.append(f"  {i}. {nombre}")
            lineas.append(f"     id: {wid} | {views} vistas")

        # Guardar para poder referenciar despues por numero
        self._last_search_results = workflows

        return {
            "thought": f"{len(workflows)} templates encontrados",
            "display": "\n".join(lineas),
            "voice": f"Encontre {len(workflows)} templates para {query}.",
        }

    def _get_template_action(self, template_id):
        template_id = str(template_id or "").strip()
        if not template_id.isdigit() and not hasattr(self, "_last_search_results"):
            return {"thought": "", "display": "Necesito un ID de template.", "voice": "Dime el ID."}

        # Si es un numero 1-5, es un indice del ultimo search
        if template_id.isdigit() and 1 <= int(template_id) <= 5 and hasattr(self, "_last_search_results"):
            idx = int(template_id) - 1
            results = self._last_search_results
            if idx < len(results):
                template_id = results[idx].get("id")

        data, err = self._fetch_template_json(template_id)
        if err:
            return {"thought": "Error", "display": err, "voice": "No pude obtener el template."}

        # La respuesta puede tener formato {"workflow": {...}} o similar
        wf = data.get("workflow") or (data.get("data") or {}).get("workflow") or data

        nombre = wf.get("name", f"Template {template_id}")
        nodes = wf.get("nodes", [])

        lineas = [
            f"Template: {nombre}",
            f"  ID: {template_id}",
            f"  Nodos: {len(nodes)}",
        ]
        if nodes:
            lineas.append("  Pasos:")
            for n in nodes[:10]:
                lineas.append(f"    - {n.get('name', '?')} ({n.get('type', '?').split('.')[-1]})")

        return {
            "thought": f"Template {nombre}",
            "display": "\n".join(lineas),
            "voice": f"El template {nombre} tiene {len(nodes)} pasos.",
        }

    def _fetch_template_json(self, template_id):
        try:
            r = requests.get(
                f"{N8N_IO_API}/templates/workflows/{template_id}",
                timeout=TIMEOUT,
            )
            if r.status_code != 200:
                return None, f"n8n.io respondio {r.status_code}"
            return r.json(), None
        except Exception as e:
            return None, f"Error: {e}"
            # ─── CREAR WORKFLOW DESDE CERO CON LLM ───────────────────────────────

    def _create_workflow(self, description, name=""):
        description = (description or "").strip()
        if not description:
            return {"thought": "", "display": "Dime que workflow quieres crear.", "voice": "Dime que workflow."}

        # 1. Generar JSON con LLM
        from core.model_config import get_model
        _model = get_model("agent")
        print(f"[N8N] Generando workflow con {_model}...")
        wf_json, err = self._generate_workflow_with_llm(description)
        if err:
            return {
                "thought": "LLM fallo",
                "display": f"No pude generar el workflow: {err}",
                "voice": "No pude generar el workflow.",
            }

        # 2. Validar
        ok, msg = self._validate_workflow(wf_json)
        if not ok:
            return {
                "thought": "Workflow invalido",
                "display": f"El workflow generado no es valido: {msg}",
                "voice": "El workflow no es valido.",
            }

        # 3. Auto-fix (ids, positions)
        wf_json = self._autofix_workflow(wf_json)

        # 4. Nombre final
        final_name = name or wf_json.get("name") or "Workflow generado por Nitro"
        wf_json["name"] = final_name

        # 5. Preview + confirmacion
        nodes = wf_json.get("nodes", [])
        n_nodes = len(nodes)
        resumen_nodos = []
        for n in nodes:
            tipo_corto = n.get("type", "?").split(".")[-1]
            resumen_nodos.append(f"  - {n.get('name', '?')} ({tipo_corto})")

        preview = (
            f"Workflow: {final_name}\n"
            f"  Nodos: {n_nodes}\n"
            + "\n".join(resumen_nodos)
        )

        if not confirmation.require("n8n", "create_workflow", preview):
            return {"thought": "Cancelado", "display": "Cancelado.", "voice": "Cancelado."}

        # 6. Subir a n8n
        payload = {
            "name": final_name,
            "nodes": wf_json.get("nodes", []),
            "connections": wf_json.get("connections", {}),
            "settings": wf_json.get("settings", {}) or {},
        }

        result, err = self._api_post("/api/v1/workflows", payload)
        if err:
            return {
                "thought": "Error subiendo",
                "display": f"Error subiendo el workflow a n8n: {err}",
                "voice": "No pude subir el workflow.",
            }

        nuevo_id = result.get("id", "?")

        return {
            "thought": f"Workflow {final_name} creado ({n_nodes} nodos)",
            "display": (
                f"Workflow creado en n8n.\n"
                f"  Nombre: {final_name}\n"
                f"  ID: {nuevo_id}\n"
                f"  Nodos: {n_nodes}\n\n"
                f"Ábrelo en: http://localhost:5678/workflow/{nuevo_id}\n\n"
                f"Esta inactivo por defecto. Dime 'activa el workflow {final_name}' para activarlo."
            ),
            "voice": f"Workflow {final_name} creado con {n_nodes} nodos.",
        }

    def _generate_workflow_with_llm(self, description):
        """Llama al LLM para generar el JSON del workflow."""
        prompt = f"""Eres un experto en n8n. Genera un workflow en JSON valido para esta tarea:

{description}

FORMATO DE RESPUESTA (JSON puro, sin markdown):

{{
  "name": "Nombre descriptivo del workflow",
  "nodes": [
    {{
      "parameters": {{}},
      "id": "uuid-aqui",
      "name": "Nombre del nodo",
      "type": "n8n-nodes-base.xxx",
      "typeVersion": 1,
      "position": [250, 300]
    }}
  ],
  "connections": {{
    "Nodo A": {{
      "main": [[{{"node": "Nodo B", "type": "main", "index": 0}}]]
    }}
  }},
  "settings": {{}}
}}

NODOS PERMITIDOS (usa SOLO estos, no inventes):
- n8n-nodes-base.scheduleTrigger (cron, "cada dia a las 9")
- n8n-nodes-base.webhook (recibir HTTP)
- n8n-nodes-base.manualTrigger (ejecucion manual)
- n8n-nodes-base.httpRequest (hacer peticiones HTTP)
- n8n-nodes-base.code (codigo JS/Python)
- n8n-nodes-base.set (editar campos)
- n8n-nodes-base.if (condicion)
- n8n-nodes-base.switch (switch multiple)
- n8n-nodes-base.merge (unir ramas)
- n8n-nodes-base.telegram (enviar mensaje Telegram)
- n8n-nodes-base.slack (enviar a Slack)
- n8n-nodes-base.discord (enviar a Discord)
- n8n-nodes-base.emailSend (enviar email)
- n8n-nodes-base.gmail (Gmail)
- n8n-nodes-base.whatsApp (WhatsApp Business)
- n8n-nodes-base.googleSheets (Google Sheets)
- n8n-nodes-base.postgres (PostgreSQL)
- n8n-nodes-base.mysql (MySQL)
- @n8n/n8n-nodes-langchain.agent (AI Agent)
- @n8n/n8n-nodes-langchain.lmChatOpenAi (modelo OpenAI)

REGLAS ESTRICTAS:
1. Responde SOLO con JSON puro. Sin ```json, sin texto antes ni despues.
2. Empieza con {{ y termina con }}.
3. Cada nodo DEBE tener: parameters, id, name, type, typeVersion, position.
4. El campo "id" de cada nodo debe ser un string unico (usa formato UUID).
5. El campo "position" es un array [x, y]. Empieza en [250, 300] y suma 200 al x para cada nodo siguiente.
6. Las "connections" usan el NOMBRE del nodo (no el id) como clave.
7. SIEMPRE incluye un trigger como primer nodo.
8. typeVersion mas comun: 1, 1.1, 2. Si dudas, usa 1.
9. NO uses nodos fuera de la lista permitida.
10. Si el usuario pide algo que necesita credenciales (Telegram chat ID, API key, etc.), deja esos parametros con un placeholder como "REEMPLAZAR_AQUI".

EJEMPLO para "cada dia a las 9 mandar buenos dias por Telegram":

{{
  "name": "Buenos dias por Telegram",
  "nodes": [
    {{
      "parameters": {{"rule": {{"interval": [{{"field": "days", "triggerAtHour": 9}}]}}}},
      "id": "a1b2c3d4-1111-2222-3333-444455556666",
      "name": "Schedule Trigger",
      "type": "n8n-nodes-base.scheduleTrigger",
      "typeVersion": 1.2,
      "position": [250, 300]
    }},
    {{
      "parameters": {{"chatId": "REEMPLAZAR_AQUI", "text": "Buenos dias", "additionalFields": {{}}}},
      "id": "b2c3d4e5-2222-3333-4444-555566667777",
      "name": "Telegram",
      "type": "n8n-nodes-base.telegram",
      "typeVersion": 1.2,
      "position": [450, 300]
    }}
  ],
  "connections": {{
    "Schedule Trigger": {{"main": [[{{"node": "Telegram", "type": "main", "index": 0}}]]}}
  }},
  "settings": {{}}
}}

Ahora genera el workflow para: {description}
"""

        try:
            from core.config_loader import CONFIG
            from core.model_config import get_model
            model = get_model("agent")
            response = ollama.chat(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                options={"temperature": 0.1, "num_predict": 6000},
            )
            raw = response["message"]["content"].strip()
        except Exception as e:
            return None, f"Error llamando al LLM: {e}"

        # Parser robusto (limpiar fences, buscar JSON balanceado)
        raw = re.sub(r'^```(?:json)?\s*', '', raw)
        raw = re.sub(r'\s*```$', '', raw)

        try:
            wf = json.loads(raw)
            return wf, None
        except json.JSONDecodeError:
            pass

        # Buscar el primer JSON balanceado
                # Buscar el primer JSON balanceado
        start = raw.find("{")
        if start == -1:
            return None, f"El LLM no devolvio JSON. Respuesta: {raw[:300]}"

        depth = 0
        for i in range(start, len(raw)):
            if raw[i] == "{":
                depth += 1
            elif raw[i] == "}":
                depth -= 1
                if depth == 0:
                    candidate = raw[start:i + 1]
                    try:
                        return json.loads(candidate), None
                    except json.JSONDecodeError as e:
                        return None, f"JSON invalido: {e}. Respuesta: {candidate[:300]}"

        # FALLBACK: JSON incompleto -> intentar repararlo cerrando llaves/corchetes
        repaired = self._repair_incomplete_json(raw[start:])
        if repaired:
            print("[N8N] JSON incompleto reparado automaticamente")
            return repaired, None

        return None, "JSON incompleto (no se cerraron las llaves)."

    def _repair_incomplete_json(self, candidate):
        """Intenta cerrar un JSON que quedo incompleto (LLM corto la salida)."""
        candidate = candidate.rstrip()

        # ─── PASO 1: rastrear con pila el orden de apertura ───
        stack = []
        in_string = False
        escape = False

        for c in candidate:
            if escape:
                escape = False
                continue
            if c == "\\":
                escape = True
                continue
            if c == '"':
                in_string = not in_string
                continue
            if in_string:
                continue
            if c == "{":
                stack.append("}")
            elif c == "[":
                stack.append("]")
            elif c == "}":
                if stack and stack[-1] == "}":
                    stack.pop()
            elif c == "]":
                if stack and stack[-1] == "]":
                    stack.pop()

        # ─── PASO 2: reparar el corte ───
        out = candidate

        # Si un string quedo abierto, cerrarlo
        if in_string:
            out += '"'

        # Si el ultimo caracter es ':' (falta valor), anadir null
        if out.rstrip().endswith(":"):
            out += " null"

        # Si el ultimo caracter es ',' (falta elemento), quitarlo
        if out.rstrip().endswith(","):
            out = out.rstrip()[:-1]

        # ─── PASO 3: cerrar en orden inverso al de apertura ───
        for closer in reversed(stack):
            out += closer

        try:
            return json.loads(out)
        except json.JSONDecodeError as e:
            print(f"[N8N] No pude reparar el JSON: {e}")
            print(f"[N8N] JSON intentado: {out[-300:]}")
            return None

    def _validate_workflow(self, wf):
        """Valida estructura + nodos contra whitelist."""
        if not isinstance(wf, dict):
            return False, "No es un objeto JSON."

        if "nodes" not in wf or not isinstance(wf["nodes"], list):
            return False, "Falta 'nodes' o no es lista."

        if not wf["nodes"]:
            return False, "'nodes' esta vacio."

        if "connections" not in wf or not isinstance(wf["connections"], dict):
            return False, "Falta 'connections' o no es dict."

        # Verificar que cada nodo tenga type permitido
        for i, node in enumerate(wf["nodes"]):
            if not isinstance(node, dict):
                return False, f"Nodo {i} no es dict."
            node_type = node.get("type")
            if not node_type:
                return False, f"Nodo {i} no tiene 'type'."
            if node_type not in NODE_WHITELIST:
                return False, f"Nodo '{node.get('name', i)}' usa tipo no permitido: {node_type}"

        return True, "OK"

    def _autofix_workflow(self, wf):
        """Rellena campos faltantes y repara problemas que n8n rechazaria."""
        # Asegurar name
        if not wf.get("name"):
            wf["name"] = "Workflow generado por Nitro"

        # Asegurar settings
        if "settings" not in wf or not isinstance(wf["settings"], dict):
            wf["settings"] = {}

        # ─── PASO 1: normalizar nodos (id, name, parameters, typeVersion, position) ───
        x_pos = 250
        for node in wf.get("nodes", []):
            if not node.get("id"):
                node["id"] = str(uuid.uuid4())
            if not node.get("name"):
                tipo = node.get("type", "node").split(".")[-1]
                node["name"] = tipo
            if "parameters" not in node or not isinstance(node["parameters"], dict):
                node["parameters"] = {}
            if "typeVersion" not in node:
                node["typeVersion"] = 1
            if "position" not in node or not isinstance(node["position"], list) or len(node["position"]) != 2:
                node["position"] = [x_pos, 300]
            x_pos += 200

        # ─── PASO 2: renombrar duplicados ───
        # n8n rechaza workflows con nombres de nodo duplicados.
        # El LLM a veces repite "WhatsApp" o "Postgres" varias veces.
        seen_names = {}
        rename_map = {}  # (indice_original) -> nombre_final
        for i, node in enumerate(wf.get("nodes", [])):
            original = node.get("name", "")
            if original not in seen_names:
                seen_names[original] = 1
                rename_map[i] = original
            else:
                seen_names[original] += 1
                nuevo = f"{original}_{seen_names[original]}"
                node["name"] = nuevo
                rename_map[i] = nuevo
                print(f"[N8N] Nodo duplicado renombrado: '{original}' -> '{nuevo}'")

        # ─── PASO 3: limpiar connections rotas ───
        # n8n rechaza workflows con conexiones que apuntan a nodos inexistentes.
        # El LLM a veces confunde case labels con nodos reales.
        nombres_reales = set(rename_map.values())
        connections = wf.get("connections", {})
        connections_limpias = {}

        for src, outputs in connections.items():
            # Si el source no existe, eliminar toda la entrada
            if src not in nombres_reales:
                print(f"[N8N] Connection source inexistente eliminado: '{src}'")
                continue

            nuevos_outputs = {}
            for output_type, lista_ramas in outputs.items():
                nuevas_ramas = []
                for rama in lista_ramas:
                    rama_limpia = []
                    for target in rama:
                        target_name = target.get("node", "")
                        if target_name in nombres_reales:
                            rama_limpia.append(target)
                        else:
                            print(f"[N8N] Connection target inexistente eliminado: '{src}' -> '{target_name}'")
                    if rama_limpia:
                        nuevas_ramas.append(rama_limpia)
                if nuevas_ramas:
                    nuevos_outputs[output_type] = nuevas_ramas
            if nuevos_outputs:
                connections_limpias[src] = nuevos_outputs

        wf["connections"] = connections_limpias

        return wf

    def _import_template(self, template_id, custom_name=""):
        template_id = str(template_id or "").strip()

        # Si es un numero 1-5, resolver del ultimo search
        if template_id.isdigit() and 1 <= int(template_id) <= 5 and hasattr(self, "_last_search_results"):
            idx = int(template_id) - 1
            results = self._last_search_results
            if idx < len(results):
                template_id = str(results[idx].get("id"))

        if not template_id:
            return {"thought": "", "display": "Necesito un ID de template.", "voice": "Dime el ID."}

        # Descargar template
        data, err = self._fetch_template_json(template_id)
        if err:
            return {"thought": "Error", "display": err, "voice": "No pude descargar el template."}

        wf_wrapper = data.get("workflow") or (data.get("data") or {}).get("workflow") or data
        wf_inner = wf_wrapper.get("workflow") or wf_wrapper

        # Nombre del nuevo workflow en tu n8n
        nombre = custom_name or wf_wrapper.get("name") or wf_inner.get("name") or f"Template {template_id}"

        # Confirmar
        if not confirmation.require("n8n", "import_template", f"Importar template '{nombre}' ({template_id})"):
            return {"thought": "", "display": "Cancelado.", "voice": "Cancelado."}

        # Construir payload para la API de n8n
        payload = {
            "name": nombre,
            "nodes": wf_inner.get("nodes", []),
            "connections": wf_inner.get("connections", {}),
            "settings": wf_inner.get("settings", {}) or {},
        }

        # Subir a n8n
        result, err = self._api_post("/api/v1/workflows", payload)
        if err:
            return {
                "thought": "Error importando",
                "display": f"Error importando el template: {err}",
                "voice": "No pude importar el template.",
            }

        nuevo_id = result.get("id", "?")

        return {
            "thought": f"Template {nombre} importado como {nuevo_id}",
            "display": (
                f"Template importado a n8n.\n"
                f"  Nombre: {nombre}\n"
                f"  ID: {nuevo_id}\n"
                f"  Nodos: {len(payload['nodes'])}\n\n"
                f"Abre n8n para configurarlo: http://localhost:5678"
            ),
            "voice": f"Template {nombre} importado. Configuralo en n8n.",
        }