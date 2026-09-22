"""Skill de generacion de imagenes con Pollinations AI (con API key personal)."""
import os
import re
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import quote

import requests
from dotenv import load_dotenv

from skills.base import Skill
from core import confirmation

ROOT = Path(__file__).resolve().parent.parent
IMAGES_DIR = ROOT / "sandbox" / "images"

load_dotenv(ROOT / ".env")
POLLINATIONS_API_KEY = os.getenv("POLLINATIONS_API_KEY")

# Tamano por defecto (cuadrado, tipo Instagram post)
DEFAULT_WIDTH = 1024
DEFAULT_HEIGHT = 1024

# Timeout generoso (Pollinations a veces tarda)
TIMEOUT = 60


class ImageSkill(Skill):
    name = "image"
    description = "Genera imagenes desde texto con Pollinations AI"

    def run(self, action, params):
        if action == "generate":
            return self._generate(
                params.get("prompt", ""),
                params.get("width", DEFAULT_WIDTH),
                params.get("height", DEFAULT_HEIGHT),
            )
        if action == "list":
            return self._list()
        return f"Accion desconocida en image: {action}"

    # ─── HELPERS ─────────────────────────────────────────────────────────

    def _slug(self, text, maxlen=50):
        """Convierte un texto en un nombre de archivo seguro."""
        s = text.lower()
        replacements = {
            "á": "a", "é": "e", "í": "i", "ó": "o", "ú": "u",
            "ñ": "n", "ü": "u",
        }
        for k, v in replacements.items():
            s = s.replace(k, v)
        s = re.sub(r'[^a-z0-9]+', '_', s)[:maxlen].strip("_")
        return s or "imagen"

    def _build_url(self, prompt, width, height, seed=None):
        """Construye la URL del endpoint nuevo gen.pollinations.ai."""
        encoded = quote(prompt, safe="")
        url = f"https://gen.pollinations.ai/image/{encoded}"
        params = {
            "width": int(width),
            "height": int(height),
            "model": "flux",
        }
        if seed is not None:
            params["seed"] = seed
        query = "&".join(f"{k}={v}" for k, v in params.items())
        return f"{url}?{query}"

    # ─── GENERATE ────────────────────────────────────────────────────────

    def _generate(self, prompt, width, height):
        prompt = (prompt or "").strip()
        if not prompt:
            return "Dime que imagen quieres que genere."

        try:
            width = int(width)
            height = int(height)
        except (ValueError, TypeError):
            width, height = DEFAULT_WIDTH, DEFAULT_HEIGHT

        # Limitar tamanos razonables
        width = max(256, min(width, 2048))
        height = max(256, min(height, 2048))

        summary = f"Generar imagen: {prompt[:100]} ({width}x{height})"
        if not confirmation.require("image", "generate", summary):
            return "Cancelado."

        url = self._build_url(prompt, width, height)
        print(f"[IMAGE] Generando con Pollinations: {prompt[:60]}...")

        # API key va en header Authorization (no en query param)
        headers = {}
        if POLLINATIONS_API_KEY:
            headers["Authorization"] = f"Bearer {POLLINATIONS_API_KEY}"

        try:
            t0 = time.time()
            r = requests.get(url, headers=headers, timeout=TIMEOUT)
            elapsed = time.time() - t0
        except requests.Timeout:
            return f"Timeout: Pollinations tardo mas de {TIMEOUT}s."
        except Exception as e:
            return f"Error conectando con Pollinations: {e}"

        if r.status_code != 200:
            return f"Error de Pollinations: {r.status_code} - {r.text[:200]}"

        # Guardar
        IMAGES_DIR.mkdir(parents=True, exist_ok=True)
        slug = self._slug(prompt)
        ts = int(datetime.now().timestamp())
        filename = f"{slug}_{ts}.jpg"
        path = IMAGES_DIR / filename

        try:
            path.write_bytes(r.content)
        except Exception as e:
            return f"Error guardando imagen: {e}"

        size_kb = len(r.content) // 1024
        print(f"[IMAGE] Guardada: {path} ({size_kb} KB en {elapsed:.1f}s)")

        return {
            "thought": f"Imagen generada en {elapsed:.1f}s",
            "display": (
                f"Imagen generada:\n"
                f"  {path}\n"
                f"  {width}x{height}, {size_kb} KB, {elapsed:.1f}s\n\n"
                f"Prompt: {prompt}"
            ),
            "voice": f"Listo. Imagen guardada en {filename}.",
        }

    # ─── LIST ────────────────────────────────────────────────────────────

    def _list(self):
        if not IMAGES_DIR.exists():
            return "No hay imagenes generadas todavia."

        files = sorted(
            IMAGES_DIR.glob("*.jpg"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )[:10]

        if not files:
            return "No hay imagenes generadas todavia."

        lines = [f"Ultimas {len(files)} imagenes:"]
        for f in files:
            size_kb = f.stat().st_size // 1024
            lines.append(f"  - {f.name} ({size_kb} KB)")

        return {
            "thought": "",
            "display": "\n".join(lines),
            "voice": f"Tienes {len(files)} imagenes generadas.",
        }