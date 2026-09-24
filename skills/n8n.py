"""Skill de n8n: controla workflows + busca/importa templates de n8n.io."""
import json
import re
from pathlib import Path

import requests

from skills.base import Skill
from core import confirmation

ROOT = Path(__file__).resolve().parent.parent
ENV_FILE = ROOT / ".env.n8n.tmp"
TIMEOUT = 20
N8N_IO_API = "https://api.n8n.io/api"


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