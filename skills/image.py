"""Skill de generación de imágenes con Pollinations AI (con API key personal)."""
import os
import re
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import quote

import ollama
import requests
from dotenv import load_dotenv
from docx import Document
from docx.shared import Inches, Pt
from docx.enum.text import WD_ALIGN_PARAGRAPH

from skills.base import Skill
from core import confirmation
from core.config_loader import CONFIG

ROOT = Path(__file__).resolve().parent.parent
IMAGES_DIR = ROOT / "sandbox" / "images"

load_dotenv(ROOT / ".env")
POLLINATIONS_API_KEY = os.getenv("POLLINATIONS_API_KEY")

# Tamaño por defecto (cuadrado, tipo Instagram post)
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
        if action == "to_word":
            return self._to_word(
                params.get("prompt", ""),
                params.get("count", 1),
                params.get("title", ""),
            )
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

        # Limitar tamaños razonables
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

    # ─── COMBO: IMAGEN → WORD ────────────────────────────────────────────

    def _to_word(self, prompt, count, title):
        """
        Combo: genera 1+ imagenes y crea un Word con ellas incrustadas.
        Si no hay prompt, usa las ultimas imagenes de sandbox/images/.
        """
        try:
            count = int(count)
        except (ValueError, TypeError):
            count = 1
        count = max(1, min(count, 5))  # maximo 5 imagenes

        imagenes = []

        # Si hay prompt, generar las imagenes primero
        if prompt:
            print(f"[IMAGE] Generando {count} imagen(es) para '{prompt[:60]}'...")
            for i in range(count):
                # Variar el prompt un poco para cada variante
                variante = prompt if count == 1 else f"{prompt} (variante {i+1})"
                result = self._generate(variante, DEFAULT_WIDTH, DEFAULT_HEIGHT)
                # El _generate devuelve dict o string de error
                if isinstance(result, dict):
                    # Extraer el path del display
                    display = result.get("display", "")
                    m = re.search(r'([A-Za-z]:\\[^\s]+\.jpg)', display)
                    if m:
                        imagenes.append({
                            "path": Path(m.group(1)),
                            "prompt": variante,
                        })
                else:
                    return f"Error generando imagen {i+1}: {result}"

            if not imagenes:
                return "No pude generar las imagenes."
        else:
            # Usar las ultimas imagenes generadas
            if not IMAGES_DIR.exists():
                return "No hay imagenes generadas todavia."

            files = sorted(
                IMAGES_DIR.glob("*.jpg"),
                key=lambda p: p.stat().st_mtime,
                reverse=True,
            )[:count]

            if not files:
                return "No hay imagenes generadas todavia."

            for f in files:
                imagenes.append({"path": f, "prompt": ""})

        # Pedir descripcion al LLM (1 por imagen, si hay prompt)
        descripciones = []
        for img in imagenes:
            if img["prompt"]:
                desc = self._describe_image(img["prompt"])
            else:
                desc = ""
            descripciones.append(desc)

        # Resolver titulo del Word
        titulo = title or (f"Imagenes: {prompt[:60]}" if prompt else "Imagenes generadas")

        # Path de salida
        office_dir = ROOT / "sandbox" / "office"
        office_dir.mkdir(parents=True, exist_ok=True)
        slug = self._slug(prompt or "imagenes")
        ts = int(datetime.now().timestamp())
        out = office_dir / f"imagenes_{slug}_{ts}.docx"

        summary = f"Crear Word con {len(imagenes)} imagen(es) incrustadas"
        if not confirmation.require("image", "to_word", summary):
            return "Cancelado."

        # Crear el Word
        try:
            doc = Document()
            style = doc.styles["Normal"]
            style.font.name = "Calibri"
            style.font.size = Pt(11)

            # Portada
            h = doc.add_heading(titulo, level=0)
            h.alignment = WD_ALIGN_PARAGRAPH.CENTER

            # Por cada imagen
            for i, img in enumerate(imagenes):
                path = img["path"]
                if not path.exists():
                    continue

                # Subtitulo (si hay varias)
                if len(imagenes) > 1:
                    doc.add_heading(f"Imagen {i+1}", level=1)

                # Imagen centrada
                try:
                    doc.add_picture(str(path), width=Inches(5.0))
                    last_para = doc.paragraphs[-1]
                    last_para.alignment = WD_ALIGN_PARAGRAPH.CENTER
                except Exception as e:
                    doc.add_paragraph(f"[No se pudo insertar la imagen: {e}]")
                    continue

                # Descripcion (si la hay)
                desc = descripciones[i] if i < len(descripciones) else ""
                if desc:
                    doc.add_paragraph(desc)

                # Prompt original en cursiva
                if img["prompt"]:
                    p = doc.add_paragraph()
                    run = p.add_run(f"Prompt: {img['prompt']}")
                    run.italic = True
                    run.font.size = Pt(9)

                # Espacio entre imagenes
                if i < len(imagenes) - 1:
                    doc.add_paragraph("")

            out.parent.mkdir(parents=True, exist_ok=True)
            doc.save(str(out))
        except Exception as e:
            return f"Error creando Word: {e}"

        size_kb = out.stat().st_size // 1024
        print(f"[IMAGE] Word guardado: {out} ({len(imagenes)} imagenes)")

        return {
            "thought": f"Word con {len(imagenes)} imagenes incrustadas",
            "display": (
                f"Word con imagenes: {out}\n"
                f"({len(imagenes)} imagen(es) incrustada(s), {size_kb} KB)"
            ),
            "voice": f"Listo. Cree un Word con {len(imagenes)} imagenes.",
        }

    def _describe_image(self, prompt):
        """Pide al LLM una descripcion breve para usar en el Word."""
        prompt_llm = f"""Describe en 1-2 frases cortas (maximo 40 palabras) una imagen que tenga este prompt: "{prompt}"
Habla como si describieras la imagen resultante. Se concreto y visual.
NO digas "esta imagen muestra" ni "la imagen es". Empieza directamente.
Responde solo la descripcion."""
        try:
            resp = ollama.chat(
                model=CONFIG["models"].get("default", "dolphin-directo"),
                messages=[{"role": "user", "content": prompt_llm}],
                options={"temperature": 0.5},
            )
            return resp["message"]["content"].strip()
        except Exception as e:
            print(f"[IMAGE] No pude generar descripcion: {e}")
            return ""
