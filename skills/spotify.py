"""Skill de control de Spotify via Web API (requiere Premium)."""
import os
import time
from pathlib import Path

import requests
from dotenv import load_dotenv

from skills.base import Skill

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

CLIENT_ID = os.getenv("SPOTIFY_CLIENT_ID")
CLIENT_SECRET = os.getenv("SPOTIFY_CLIENT_SECRET")
REFRESH_TOKEN = os.getenv("SPOTIFY_REFRESH_TOKEN")

API = "https://api.spotify.com/v1"
TOKEN_URL = "https://accounts.spotify.com/api/token"


class SpotifySkill(Skill):
    name = "spotify"
    description = "Controla Spotify: play, pausa, siguiente, anterior, que suena, volumen"

    def __init__(self):
        self._access_token = None
        self._expires_at = 0

    # ── Autenticacion ──────────────────────────────────────────
    def _get_token(self):
        if not all([CLIENT_ID, CLIENT_SECRET, REFRESH_TOKEN]):
            raise RuntimeError(
                "Faltan credenciales. Ejecuta scripts/setup_spotify_auth.py una vez."
            )
        if self._access_token and time.time() < self._expires_at - 30:
            return self._access_token

        resp = requests.post(
            TOKEN_URL,
            data={
                "grant_type": "refresh_token",
                "refresh_token": REFRESH_TOKEN,
                "client_id": CLIENT_ID,
                "client_secret": CLIENT_SECRET,
            },
            timeout=10,
        )
        if resp.status_code != 200:
            raise RuntimeError(f"Error renovando token: {resp.status_code} {resp.text}")

        data = resp.json()
        self._access_token = data["access_token"]
        self._expires_at = time.time() + int(data.get("expires_in", 3600))
        return self._access_token

    def _headers(self):
        return {"Authorization": f"Bearer {self._get_token()}"}

    def _active_device(self):
        try:
            r = requests.get(f"{API}/me/player/devices", headers=self._headers(), timeout=10)
            if r.status_code != 200:
                return None
            devices = r.json().get("devices", [])
            for d in devices:
                if d.get("is_active"):
                    return d["id"]
            return devices[0]["id"] if devices else None
        except Exception:
            return None

    # ── Dispatcher ─────────────────────────────────────────────
    def run(self, action, params):
        try:
            if action == "play":
                return self._play(params.get("query", ""))
            if action == "pause":
                return self._pause()
            if action == "next":
                return self._next()
            if action == "previous":
                return self._previous()
            if action == "current":
                return self._current()
            if action == "volume":
                return self._set_volume(int(params.get("percent", 50)))
        except Exception as e:
            return f"Error Spotify: {e}"
        return f"Accion desconocida en spotify: {action}"

    # ── Acciones ───────────────────────────────────────────────
    def _play(self, query):
        query = (query or "").strip()
        if not query:
            return "Dime que quieres reproducir."

        r = requests.get(
            f"{API}/search",
            headers=self._headers(),
            params={"q": query, "type": "track", "limit": 1},
            timeout=10,
        )
        if r.status_code != 200:
            return f"Error buscando: {r.status_code}"

        items = r.json().get("tracks", {}).get("items", [])
        if not items:
            return f"No encontre '{query}' en Spotify."

        track = items[0]
        uri = track["uri"]
        name = track["name"]
        artist = track["artists"][0]["name"]

        device = self._active_device()
        body = {"uris": [uri]}
        url = f"{API}/me/player/play"
        if device:
            url += f"?device_id={device}"

        r = requests.put(url, headers=self._headers(), json=body, timeout=10)
        if r.status_code == 404:
            return "Abre Spotify primero en algun dispositivo."
        if r.status_code not in (200, 204):
            return f"Error reproduciendo: {r.status_code} {r.text[:200]}"

        return f"Reproduciendo: {name} - {artist}"

    def _pause(self):
        device = self._active_device()
        url = f"{API}/me/player/pause"
        if device:
            url += f"?device_id={device}"
        r = requests.put(url, headers=self._headers(), timeout=10)
        if r.status_code in (200, 204):
            return "Pausado."
        return f"No pude pausar: {r.status_code} {r.text[:150]}"

    def _next(self):
        device = self._active_device()
        url = f"{API}/me/player/next"
        if device:
            url += f"?device_id={device}"
        r = requests.post(url, headers=self._headers(), timeout=10)
        if r.status_code in (200, 204):
            return "Siguiente."
        return f"No pude avanzar: {r.status_code} {r.text[:150]}"

    def _previous(self):
        device = self._active_device()
        url = f"{API}/me/player/previous"
        if device:
            url += f"?device_id={device}"
        r = requests.post(url, headers=self._headers(), timeout=10)
        if r.status_code in (200, 204):
            return "Anterior."
        return f"No pude retroceder: {r.status_code} {r.text[:150]}"

    def _current(self):
        r = requests.get(
            f"{API}/me/player/currently-playing",
            headers=self._headers(),
            timeout=10,
        )
        if r.status_code == 204:
            return "No hay nada reproduciendose."
        if r.status_code != 200:
            return f"Error: {r.status_code}"
        data = r.json()
        item = data.get("item")
        if not item:
            return "No hay nada reproduciendose."
        name = item["name"]
        artist = item["artists"][0]["name"]
        return f"Suena: {name} - {artist}"

    def _set_volume(self, percent):
        percent = max(0, min(100, percent))
        device = self._active_device()
        params = {"volume_percent": percent}
        if device:
            params["device_id"] = device
        r = requests.put(
            f"{API}/me/player/volume",
            headers=self._headers(),
            params=params,
            timeout=10,
        )
        if r.status_code in (200, 204):
            return f"Volumen Spotify a {percent}%."
        return f"No pude cambiar volumen: {r.status_code} {r.text[:150]}"