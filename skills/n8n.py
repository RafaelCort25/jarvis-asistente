"""Skill de n8n: controla workflows via la API oficial de n8n."""
import json
import os
import re
from pathlib import Path

import requests

from skills.base import Skill
from core import confirmation

ROOT = Path(__file__).resolve().parent.parent
ENV_FILE = ROOT / ".env.n8n.tmp"
TIMEOUT = 15


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
    description = "Controla workflows de n8n (listar, activar, ejecutar, borrar)"

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
        return f"Accion desconocida en n8n: {action}"

    # ─── HELPERS ─────────────────────────────────────────────────────────

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
            return None, "No puedo conectar con n8n. ¿Esta corriendo en http://localhost:5678?"
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
                return None, f"n8n respondio {r.status_code}: {r.text[:200]}"
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
        """Busca un workflow por ID exacto o por nombre (parcial, case-insensitive)."""
        id_or_name = (id_or_name or "").strip()
        if not id_or_name:
            return None, "Falta el nombre o ID del workflow."

        # Si parece un ID corto (ej: "abc123"), intentar directo
        data, err = self._api_get("/api/v1/workflows")
        if err:
            return None, err

        workflows = data.get("data", [])

        # 1. ID exacto
        for w in workflows:
            if w.get("id") == id_or_name:
                return w, None

        # 2. Nombre exacto (case-insensitive)
        target = id_or_name.lower()
        for w in workflows:
            if (w.get("name") or "").lower() == target:
                return w, None

        # 3. Nombre parcial
        candidatos = [w for w in workflows if target in (w.get("name") or "").lower()]
        if len(candidatos) == 1:
            return candidatos[0], None
        if len(candidatos) > 1:
            nombres = [w.get("name") for w in candidatos[:5]]
            return None, f"Hay varios workflows que coinciden: {nombres}. Se mas especifico."

        return None, f"No encontre workflow con '{id_or_name}'."

    # ─── ACCIONES ────────────────────────────────────────────────────────

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
        n_nodes = len(nodes)

        detalle = [
            f"Workflow: {nombre}",
            f"  ID: {w.get('id')}",
            f"  Estado: {activo}",
            f"  Nodos: {n_nodes}",
        ]
        if nodes:
            detalle.append("  Pasos:")
            for n in nodes[:8]:
                detalle.append(f"    - {n.get('name', '?')} ({n.get('type', '?').split('.')[-1]})")

        return {
            "thought": f"Workflow {nombre}",
            "display": "\n".join(detalle),
            "voice": f"El workflow {nombre} esta {activo} con {n_nodes} pasos.",
        }

    def _set_active(self, id_or_name, activate):
        w, err = self._find_workflow(id_or_name)
        if err:
            return {"thought": "No encontrado", "display": err, "voice": "No lo encontre."}

        wid = w.get("id")
        nombre = w.get("name")

        accion = "activar" if activate else "desactivar"
        if not confirmation.require("n8n", "activate" if activate else "deactivate",
                                    f"{accion.capitalize()} workflow '{nombre}'"):
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