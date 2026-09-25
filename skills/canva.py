"""Skill de Canva: crear, leer y exportar diseños via Connect API."""
import base64
import hashlib
import http.server
import json
import re
import secrets
import socketserver
import threading
import time
import urllib.parse
import webbrowser
from pathlib import Path
from queue import Queue

import requests

from skills.base import Skill
from core import confirmation

ROOT = Path(__file__).resolve().parent.parent
ENV_FILE = ROOT / ".env.canva.tmp"
TOKEN_FILE = ROOT / "sandbox" / "canva_tokens.json"
TIMEOUT = 20

CANVA_AUTH_URL = "https://www.canva.com/api/oauth/authorize"
CANVA_TOKEN_URL = "https://api.canva.com/rest/v1/oauth/token"
CANVA_API_BASE = "https://api.canva.com/rest/v1"

# Scopes en el formato correcto de Canva (algunos usan :read/:write por separado)
SCOPES = [
    "asset:read",
    "asset:write",
    "design:content:read",
    "design:content:write",
    "design:meta:read",
    "folder:read",
    "profile:read",
]


# ─── CONFIG / TOKENS ──────────────────────────────────────────────────────

def _load_env():
    """Carga credenciales del .env.canva.tmp."""
    if not ENV_FILE.exists():
        return None, None, None
    client_id = client_secret = redirect_uri = None
    try:
        for line in ENV_FILE.read_text(encoding="utf-8-sig").splitlines():
            line = line.strip()
            if line.startswith("CANVA_CLIENT_ID="):
                client_id = line.split("=", 1)[1].strip()
            elif line.startswith("CANVA_CLIENT_SECRET="):
                client_secret = line.split("=", 1)[1].strip()
            elif line.startswith("CANVA_REDIRECT_URI="):
                redirect_uri = line.split("=", 1)[1].strip()
    except Exception as e:
        print(f"[CANVA] Error leyendo env: {e}")
    return client_id, client_secret, redirect_uri


def _save_tokens(tokens):
    TOKEN_FILE.parent.mkdir(parents=True, exist_ok=True)
    TOKEN_FILE.write_text(json.dumps(tokens, indent=2), encoding="utf-8")


def _load_tokens():
    if not TOKEN_FILE.exists():
        return None
    try:
        return json.loads(TOKEN_FILE.read_text(encoding="utf-8"))
    except Exception:
        return None


# ─── PKCE ──────────────────────────────────────────────────────────────────

def _generate_pkce():
    verifier = secrets.token_urlsafe(64)
    challenge = base64.urlsafe_b64encode(
        hashlib.sha256(verifier.encode()).digest()
    ).decode().rstrip("=")
    return verifier, challenge


# ─── SERVIDOR LOCAL PARA CAPTURAR CALLBACK ─────────────────────────────────

class _CallbackHandler(http.server.BaseHTTPRequestHandler):
    code_queue = None

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        params = urllib.parse.parse_qs(parsed.query)
        code = params.get("code", [None])[0]
        error = params.get("error", [None])[0]

        if code:
            self.code_queue.put(("code", code))
            body = b"<html><body><h2>Nitro conectado a Canva</h2><p>Ya puedes cerrar esta ventana.</p></body></html>"
        elif error:
            self.code_queue.put(("error", error))
            body = f"<html><body><h2>Error: {error}</h2></body></html>".encode()
        else:
            self.code_queue.put(("error", "no_code"))
            body = b"<html><body><h2>No se recibio codigo.</h2></body></html>"

        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass  # silenciar logs del servidor


def _run_callback_server(port, code_queue, timeout=180):
    """Levanta servidor temporal y devuelve el code o error."""

    class _Server(socketserver.TCPServer):
        allow_reuse_address = True

    _CallbackHandler.code_queue = code_queue
    try:
        with _Server(("127.0.0.1", port), _CallbackHandler) as httpd:
            httpd.timeout = timeout
            started = time.time()
            while time.time() - started < timeout:
                httpd.handle_request()
                if not code_queue.empty():
                    break
    except Exception as e:
        code_queue.put(("error", f"server: {e}"))


# ─── AUTORIZACION ──────────────────────────────────────────────────────────

def _authorize():
    """Levanta servidor local, abre navegador, espera el code."""
    client_id, _, redirect_uri = _load_env()
    if not client_id or not redirect_uri:
        return None, "Falta CANVA_CLIENT_ID o CANVA_REDIRECT_URI en .env.canva.tmp"

    # Extraer puerto del redirect_uri
    parsed = urllib.parse.urlparse(redirect_uri)
    port = parsed.port or 8080

    verifier, challenge = _generate_pkce()
    state = secrets.token_urlsafe(16)

    params = {
        "client_id": client_id,
        "response_type": "code",
        "redirect_uri": redirect_uri,
        "scope": " ".join(SCOPES),
        "code_challenge": challenge,
        "code_challenge_method": "S256",
        "state": state,
    }
    url = f"{CANVA_AUTH_URL}?{urllib.parse.urlencode(params)}"

    code_queue = Queue()
    server_thread = threading.Thread(
        target=_run_callback_server,
        args=(port, code_queue, 180),
        daemon=True,
    )
    server_thread.start()

    print(f"[CANVA] Abriendo navegador para autorizar...")
    print(f"[CANVA] Si no se abre, ve manualmente a:\n{url}\n")
    webbrowser.open(url)

    print(f"[CANVA] Esperando callback en {redirect_uri} (max 3 min)...")
    try:
        kind, value = code_queue.get(timeout=185)
    except Exception:
        return None, "Timeout esperando callback."

    if kind == "error":
        return None, f"Error en callback: {value}"

    return (value, verifier), None


def _exchange_code_for_tokens(code, verifier):
    client_id, client_secret, redirect_uri = _load_env()
    if not all([client_id, client_secret, redirect_uri]):
        return None, "Faltan credenciales en .env.canva.tmp"

    data = {
        "grant_type": "authorization_code",
        "code": code,
        "code_verifier": verifier,
        "redirect_uri": redirect_uri,
    }
    auth = base64.b64encode(f"{client_id}:{client_secret}".encode()).decode()
    headers = {
        "Authorization": f"Basic {auth}",
        "Content-Type": "application/x-www-form-urlencoded",
    }

    try:
        r = requests.post(CANVA_TOKEN_URL, data=data, headers=headers, timeout=TIMEOUT)
    except Exception as e:
        return None, f"Error de red: {e}"

    if r.status_code != 200:
        return None, f"Canva respondio {r.status_code}: {r.text[:300]}"

    tokens = r.json()
    tokens["expires_at"] = time.time() + tokens.get("expires_in", 14400)
    _save_tokens(tokens)
    return tokens, None


def _refresh_token():
    tokens = _load_tokens()
    if not tokens or "refresh_token" not in tokens:
        return None, "No hay refresh_token. Autoriza de nuevo."

    client_id, client_secret, _ = _load_env()
    data = {
        "grant_type": "refresh_token",
        "refresh_token": tokens["refresh_token"],
    }
    auth = base64.b64encode(f"{client_id}:{client_secret}".encode()).decode()
    headers = {
        "Authorization": f"Basic {auth}",
        "Content-Type": "application/x-www-form-urlencoded",
    }
    try:
        r = requests.post(CANVA_TOKEN_URL, data=data, headers=headers, timeout=TIMEOUT)
    except Exception as e:
        return None, f"Error de red: {e}"

    if r.status_code != 200:
        return None, f"Error refrescando: {r.text[:300]}"

    new_tokens = r.json()
    new_tokens["expires_at"] = time.time() + new_tokens.get("expires_in", 14400)
    _save_tokens(new_tokens)
    return new_tokens, None


def _get_access_token():
    tokens = _load_tokens()
    if not tokens:
        return None, "No autorizado. Corre 'canva.authorize' primero."
    if tokens.get("expires_at", 0) < time.time() + 120:
        tokens, err = _refresh_token()
        if err:
            return None, err
    return tokens["access_token"], None


# ─── SKILL ─────────────────────────────────────────────────────────────────

class CanvaSkill(Skill):
    name = "canva"
    description = "Crea, lee y exporta disenos de Canva"

    def run(self, action, params):
        if action == "authorize":
            return self._authorize_action()
        if action == "whoami":
            return self._whoami()
        if action == "list_designs":
            return self._list_designs(int(params.get("limit", 10) or 10))
        if action == "get_design":
            return self._get_design(params.get("id", ""))
        if action == "create_design":
            return self._create_design(
                params.get("design_type", ""),
                params.get("title", ""),
            )
        if action == "export_design":
            return self._export_design(
                params.get("id", ""),
                params.get("format", "png"),
            )
        if action == "list_assets":
            return self._list_assets()
        if action == "upload_asset_from_url":
            return self._upload_asset_from_url(
                params.get("url", ""),
                params.get("name", ""),
            )
        return f"Accion desconocida en canva: {action}"

    # ─── AUTH ───────────────────────────────────────────────────────────

    def _authorize_action(self):
        result, err = _authorize()
        if err:
            return {"thought": "Error", "display": err, "voice": "No pude autorizar."}
        code, verifier = result
        tokens, err = _exchange_code_for_tokens(code, verifier)
        if err:
            return {"thought": "Error", "display": err, "voice": "No pude obtener tokens."}
        return {
            "thought": "Autorizado",
            "display": "Canva autorizado correctamente. Ya puedes usar la skill.",
            "voice": "Canva conectado.",
        }

    # ─── HELPERS HTTP ───────────────────────────────────────────────────

    def _api_get(self, path):
        token, err = _get_access_token()
        if err:
            return None, err
        try:
            r = requests.get(
                f"{CANVA_API_BASE}{path}",
                headers={"Authorization": f"Bearer {token}"},
                timeout=TIMEOUT,
            )
            if r.status_code != 200:
                return None, f"Canva respondio {r.status_code}: {r.text[:200]}"
            return r.json(), None
        except Exception as e:
            return None, f"Error: {e}"

    def _api_post(self, path, body):
        token, err = _get_access_token()
        if err:
            return None, err
        try:
            r = requests.post(
                f"{CANVA_API_BASE}{path}",
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json",
                },
                json=body,
                timeout=TIMEOUT,
            )
            if r.status_code not in (200, 201, 202):
                return None, f"Canva respondio {r.status_code}: {r.text[:300]}"
            return r.json(), None
        except Exception as e:
            return None, f"Error: {e}"

    # ─── ACCIONES ───────────────────────────────────────────────────────

    def _whoami(self):
        data, err = self._api_get("/users/me")
        if err:
            return {"thought": "Error", "display": err, "voice": "Error conectando."}
        profile = data.get("team_user", {}) or data
        uid = profile.get("user_id", "?")
        team = profile.get("team_id", "?")
        return {
            "thought": "Perfil obtenido",
            "display": f"Canva conectado.\n  user_id: {uid}\n  team_id: {team}",
            "voice": "Canva conectado correctamente.",
        }

    def _list_designs(self, limit=10):
        data, err = self._api_get(f"/designs?limit={limit}")
        if err:
            return {"thought": "Error", "display": err, "voice": "Error listando disenos."}
        items = data.get("items", [])
        if not items:
            return {"thought": "", "display": "No tienes disenos en Canva.", "voice": "No tienes disenos."}
        lineas = [f"Disenos en Canva ({len(items)}):"]
        for d in items:
            did = d.get("id", "?")
            titulo = d.get("title", "(sin titulo)")
            urls = d.get("urls", {})
            edit_url = urls.get("edit_url", "")
            lineas.append(f"  - {titulo}")
            lineas.append(f"    id: {did}")
            if edit_url:
                lineas.append(f"    editar: {edit_url}")
        return {
            "thought": f"{len(items)} disenos",
            "display": "\n".join(lineas),
            "voice": f"Tienes {len(items)} disenos en Canva.",
        }

    def _get_design(self, design_id):
        if not design_id:
            return {"thought": "", "display": "Falta el ID del diseno.", "voice": "Falta el ID."}
        data, err = self._api_get(f"/designs/{design_id}")
        if err:
            return {"thought": "Error", "display": err, "voice": "No lo encontre."}
        d = data.get("design", {}) or data
        titulo = d.get("title", "?")
        urls = d.get("urls", {})
        return {
            "thought": f"Diseno {titulo}",
            "display": (
                f"Diseno: {titulo}\n"
                f"  id: {d.get('id', '?')}\n"
                f"  editar: {urls.get('edit_url', '')}\n"
                f"  ver: {urls.get('view_url', '')}"
            ),
            "voice": f"Diseno {titulo}.",
        }

    def _create_design(self, design_type, title):
        design_type = (design_type or "").strip()
        title = (title or "").strip() or "Diseno de Nitro"

        # Canva SOLO permite crear estos 4 tipos en blanco via API
        # (el resto requiere Enterprise + Brand Templates)
        presets_validos = {
            "doc": "doc",
            "documento": "doc",
            "document": "doc",
            "email": "email",
            "correo": "email",
            "presentation": "presentation",
            "presentacion": "presentation",
            "whiteboard": "whiteboard",
            "pizarra": "whiteboard",
        }

        # Mapear "instagram", "facebook", etc. -> "doc" (lo más cercano)
        # y avisar al usuario que no se puede crear como ese tipo
        tipos_no_soportados = {
            "instagram": "post de Instagram",
            "post": "post generico",
            "facebook": "post de Facebook",
            "twitter": "post de Twitter",
            "youtube": "thumbnail de YouTube",
            "thumbnail": "thumbnail",
            "poster": "poster",
            "flyer": "flyer",
        }

        key = design_type.lower().replace(" ", "")
        preset = presets_validos.get(key)

        aviso = ""
        if not preset and key in tipos_no_soportados:
            preset = "doc"
            aviso = (
                f"\n\nNOTA: Canva no permite crear '{tipos_no_soportados[key]}' "
                f"en blanco via API (requiere Enterprise + Brand Templates). "
                f"Se ha creado como documento en su lugar. "
                f"Puedes cambiar el tipo dentro de Canva manualmente."
            )
        elif not preset:
            preset = "doc"
            aviso = "\n\nNOTA: tipo no soportado, se creo como documento."

        if not confirmation.require("canva", "create_design", f"Crear diseno '{title}' ({preset}){aviso}"):
            return {"thought": "Cancelado", "display": "Cancelado.", "voice": "Cancelado."}

        body = {
            "design_type": {"type": "preset", "name": preset},
            "title": title,
        }
        data, err = self._api_post("/designs", body)
        if err:
            return {"thought": "Error", "display": err, "voice": "No pude crear el diseno."}

        d = data.get("design", {}) or data
        did = d.get("id", "?")
        urls = d.get("urls", {})
        return {
            "thought": f"Diseno creado {did}",
            "display": (
                f"Diseno creado.\n"
                f"  Titulo: {title}\n"
                f"  Tipo: {preset}\n"
                f"  id: {did}\n"
                f"  editar: {urls.get('edit_url', '')}"
                f"{aviso}"
            ),
            "voice": f"Diseno {title} creado.",
        }

        if not confirmation.require("canva", "create_design", f"Crear diseno '{title}' ({preset})"):
            return {"thought": "Cancelado", "display": "Cancelado.", "voice": "Cancelado."}

        body = {
            "design_type": {"type": "preset", "name": preset},
            "title": title,
        }
        data, err = self._api_post("/designs", body)
        if err:
            return {"thought": "Error", "display": err, "voice": "No pude crear el diseno."}

        d = data.get("design", {}) or data
        did = d.get("id", "?")
        urls = d.get("urls", {})
        return {
            "thought": f"Diseno creado {did}",
            "display": (
                f"Diseno creado.\n"
                f"  Titulo: {title}\n"
                f"  Tipo: {preset}\n"
                f"  id: {did}\n"
                f"  editar: {urls.get('edit_url', '')}"
            ),
            "voice": f"Diseno {title} creado.",
        }

    def _export_design(self, design_id, fmt="png"):
        if not design_id:
            return {"thought": "", "display": "Falta el ID del diseno.", "voice": "Falta el ID."}
        fmt = (fmt or "png").lower()
        if fmt not in ("png", "jpg", "pdf", "pptx", "gif", "mp4"):
            fmt = "png"

        body = {
            "design_id": design_id,
            "format": {"type": fmt},
        }
        data, err = self._api_post("/exports", body)
        if err:
            return {"thought": "Error", "display": err, "voice": "No pude exportar."}

        job = data.get("job", {}) or data
        job_id = job.get("id", "?")
        return {
            "thought": f"Export iniciado {job_id}",
            "display": (
                f"Export iniciado.\n"
                f"  job_id: {job_id}\n"
                f"  formato: {fmt}\n"
                f"  estado: {job.get('status', '?')}\n"
                f"El proceso puede tardar unos segundos. Consulta el estado con la API."
            ),
            "voice": "Export iniciado.",
        }

    def _list_assets(self):
        data, err = self._api_get("/assets?limit=20")
        if err:
            return {"thought": "Error", "display": err, "voice": "Error listando assets."}
        items = data.get("items", [])
        if not items:
            return {"thought": "", "display": "No tienes assets en Canva.", "voice": "No hay assets."}
        lineas = [f"Assets en Canva ({len(items)}):"]
        for a in items[:10]:
            lineas.append(f"  - {a.get('name', '(sin nombre)')} ({a.get('type', '?')})")
        return {
            "thought": f"{len(items)} assets",
            "display": "\n".join(lineas),
            "voice": f"Tienes {len(items)} assets.",
        }

    def _upload_asset_from_url(self, url, name):
        url = (url or "").strip()
        if not url:
            return {"thought": "", "display": "Falta la URL del asset.", "voice": "Falta la URL."}
        name = (name or "").strip() or "asset-nitro"

        if not confirmation.require("canva", "upload_asset", f"Subir asset '{name}' desde URL"):
            return {"thought": "Cancelado", "display": "Cancelado.", "voice": "Cancelado."}

        body = {"name": name, "url": url}
        data, err = self._api_post("/url-assets", body)
        if err:
            return {"thought": "Error", "display": err, "voice": "No pude subir el asset."}
        asset = data.get("asset", {}) or data
        return {
            "thought": f"Asset subido {asset.get('id', '?')}",
            "display": (
                f"Asset subido.\n"
                f"  nombre: {name}\n"
                f"  id: {asset.get('id', '?')}"
            ),
            "voice": "Asset subido a Canva.",
        }