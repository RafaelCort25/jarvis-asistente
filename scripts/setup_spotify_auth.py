"""
Script de un solo uso para autorizar Nitro con Spotify.
Abre el navegador, escucha el callback en 127.0.0.1:8888, y guarda el
refresh_token en .env para que la skill lo use despues.

Uso:
    python scripts/setup_spotify_auth.py
"""
import base64
import http.server
import os
import socketserver
import time
import urllib.parse
import webbrowser
from pathlib import Path

import requests
from dotenv import load_dotenv, set_key

ROOT = Path(__file__).resolve().parent.parent
ENV_FILE = ROOT / ".env"

load_dotenv(ENV_FILE)

CLIENT_ID = os.getenv("SPOTIFY_CLIENT_ID")
CLIENT_SECRET = os.getenv("SPOTIFY_CLIENT_SECRET")
REDIRECT_URI = os.getenv("SPOTIFY_REDIRECT_URI", "http://127.0.0.1:8888/callback")

SCOPES = (
    "user-read-playback-state "
    "user-modify-playback-state "
    "user-read-currently-playing"
)

if not CLIENT_ID or not CLIENT_SECRET:
    raise SystemExit("Falta SPOTIFY_CLIENT_ID o SPOTIFY_CLIENT_SECRET en .env")

auth_code = None


class CallbackHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        global auth_code
        query = urllib.parse.urlparse(self.path).query
        params = urllib.parse.parse_qs(query)

        if "code" in params:
            auth_code = params["code"][0]
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(
                b"<h2>Autorizado correctamente. Puedes cerrar esta pestana y volver a la consola.</h2>"
            )
        else:
            error = params.get("error", ["desconocido"])[0]
            self.send_response(400)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(f"<h2>Error: {error}</h2>".encode())

    def log_message(self, format, *args):
        pass  # silenciar logs HTTP


def wait_for_code(timeout=120):
    port = int(urllib.parse.urlparse(REDIRECT_URI).port or 8888)
    with socketserver.TCPServer(("127.0.0.1", port), CallbackHandler) as httpd:
        httpd.timeout = 1
        start = time.time()
        while auth_code is None and (time.time() - start) < timeout:
            httpd.handle_request()
    return auth_code


def main():
    # 1. URL de autorizacion
    auth_url = (
        "https://accounts.spotify.com/authorize?"
        + urllib.parse.urlencode({
            "client_id": CLIENT_ID,
            "response_type": "code",
            "redirect_uri": REDIRECT_URI,
            "scope": SCOPES,
        })
    )

    print("[SPOTIFY] Abriendo navegador para autorizar...")
    print(f"Si no se abre, visita manualmente:\n{auth_url}\n")
    webbrowser.open(auth_url)

    print("[SPOTIFY] Esperando callback en 127.0.0.1...")
    code = wait_for_code(timeout=120)

    if not code:
        raise SystemExit("[SPOTIFY] Timeout: no se recibio el codigo.")

    print("[SPOTIFY] Codigo recibido. Intercambiando por tokens...")

    # 2. Intercambio code -> tokens
    auth_header = base64.b64encode(
        f"{CLIENT_ID}:{CLIENT_SECRET}".encode()
    ).decode()

    resp = requests.post(
        "https://accounts.spotify.com/api/token",
        headers={
            "Authorization": f"Basic {auth_header}",
            "Content-Type": "application/x-www-form-urlencoded",
        },
        data={
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": REDIRECT_URI,
        },
        timeout=15,
    )

    if resp.status_code != 200:
        raise SystemExit(f"[SPOTIFY] Error: {resp.status_code} - {resp.text}")

    tokens = resp.json()
    refresh = tokens.get("refresh_token")
    if not refresh:
        raise SystemExit("[SPOTIFY] No se recibio refresh_token.")

    # 3. Guardar refresh_token en .env
    if not ENV_FILE.exists():
        ENV_FILE.write_text("", encoding="utf-8")
    set_key(str(ENV_FILE), "SPOTIFY_REFRESH_TOKEN", refresh)

    print("[SPOTIFY] Listo. refresh_token guardado en .env.")
    print("[SPOTIFY] Ya puedes usar la skill de Spotify.")


if __name__ == "__main__":
    main()