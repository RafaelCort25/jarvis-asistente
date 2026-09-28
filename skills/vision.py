"""Skill de vision: analisis de pantalla e imagenes con Ollama (vision-language models).

Acciones:
- describe_screen       -> describir la pantalla actual
- explain_screen_code   -> explicar el codigo visible en pantalla
- ocr                   -> extraer texto de la pantalla (OCR)
- describe_ui           -> describir elementos de UI (botones, menus)
- detect_objects        -> detectar objetos en pantalla
- read_error            -> leer y explicar errores visibles
- read_table            -> extraer tabla a Markdown
- translate_screen      -> traducir texto en pantalla
- find_text             -> buscar texto en pantalla
- capture               -> guardar screenshot a disco
- describe_image        -> describir una imagen de disco
- ocr_image             -> OCR de una imagen de disco
- compare_images        -> comparar dos imagenes
- set_model             -> cambiar modelo de vision
- list_models           -> listar modelos de vision
"""

import base64
import io
import re
import time
from pathlib import Path

import ollama
import pyautogui
from skills.base import Skill
from core.config_loader import CONFIG

ROOT = Path(__file__).resolve().parent.parent
VISION_DIR = ROOT / "sandbox" / "vision"
VISION_DIR.mkdir(parents=True, exist_ok=True)

# Aliases de modelo (auto no implementado aun)
VISION_MODELS = {
    "calidad": "qwen2.5vl:7b",
    "rapido": "llava-phi3",
    "lite": "moondream",
}

DEFAULT_MODEL = "llava-phi3"

# Prompts especializados
PROMPTS = {
    "general": (
        "Describe esta captura de pantalla en espanol. "
        "Se breve y concreto. Menciona: nombre exacto de la aplicacion si lo puedes leer, "
        "que tipo de contenido se ve, y 2-3 elementos especificos que observes. "
        "Si no puedes leer un texto, di 'no legible' en vez de adivinar. "
        "NO inventes elementos que no esten claramente visibles. Maximo 80 palabras."
    ),
    "code": (
        "En esta captura hay codigo en un editor. Responde en espanol: "
        "1) Nombre del archivo si es legible, o 'no legible'. "
        "2) Lenguaje de programacion. "
        "3) Que hace el codigo segun lo que ves. "
        "4) Errores o warnings visibles. Si no ves ninguno, di 'ninguno visible'. "
        "Se estricto: si no puedes leer algo con claridad, di 'no legible'. "
        "NO inventes nombres, funciones ni errores. Maximo 120 palabras."
    ),
    "ocr": (
        "Extrae TODO el texto visible en esta imagen. "
        "Devuelvelo tal cual, linea por linea, sin comentarios ni explicaciones. "
        "Si hay tablas, manten la estructura. "
        "Si no puedes leer algo, escribe '[ilegible]' en su lugar."
    ),
    "ui": (
        "Analiza esta interfaz de usuario. Lista en espanol: "
        "1) Nombre de la aplicacion (si es visible). "
        "2) Elementos interactivos visibles (botones, menus, campos de texto, pestanas). "
        "3) Estado actual (que ventana o dialogo esta abierto). "
        "Se conciso. Maximo 100 palabras."
    ),
    "objects": (
        "Lista los objetos reconocibles en esta imagen. "
        "Devuelve una lista con guiones, uno por linea. "
        "Se especifico (ej: 'un gato naranja', no solo 'animal'). "
        "Maximo 15 objetos."
    ),
    "error": (
        "En esta captura hay un mensaje de error o advertencia. Responde en espanol: "
        "1) Texto exacto del error (o 'no legible'). "
        "2) Aplicacion donde ocurre. "
        "3) Posible causa segun el mensaje. "
        "4) Sugerencia para solucionarlo. "
        "Si no hay error visible, di 'no veo errores'."
    ),
    "table": (
        "En esta imagen hay una tabla. Extrae su contenido en formato Markdown. "
        "Manten las columnas y filas correctamente. "
        "Si no puedes leer algo, escribe '[ilegible]'. "
        "Si no hay tabla visible, di 'no veo tabla'."
    ),
    "translate": (
        "Traduce al espanol todo el texto visible en esta imagen. "
        "Devuelve la traduccion linea por linea, manteniendo la estructura original. "
        "Si algo no es texto (iconos, imagenes), ignoralo."
    ),
}


def _slugify(text, maxlen=30):
    s = text.lower()
    for k, v in {"a":"a","e":"e","i":"i","o":"o","u":"u","n":"n"}.items():
        s = s.replace(k, v)
    s = re.sub(r"[^a-z0-9]+", "_", s)[:maxlen].strip("_")
    return s or "img"


class VisionSkill(Skill):
    name = "vision"
    description = "Analiza pantalla e imagenes con modelos de vision locales"

    def __init__(self):
        self.model = CONFIG["models"].get("vision", DEFAULT_MODEL)

    def run(self, action, params):
        try:
            if action == "describe_screen":
                return self._describe_screen(params.get("mode", "general"), params.get("region"))
            if action == "explain_screen_code":
                return self._describe_screen("code", params.get("region"))
            if action == "ocr":
                return self._describe_screen("ocr", params.get("region"))
            if action == "describe_ui":
                return self._describe_screen("ui", params.get("region"))
            if action == "detect_objects":
                return self._describe_screen("objects", params.get("region"))
            if action == "read_error":
                return self._describe_screen("error", params.get("region"))
            if action == "read_table":
                return self._describe_screen("table", params.get("region"))
            if action == "translate_screen":
                return self._describe_screen("translate", params.get("region"))
            if action == "describe_image":
                return self._describe_image(params.get("path", ""), params.get("mode", "general"))
            if action == "ocr_image":
                return self._describe_image(params.get("path", ""), "ocr")
            if action == "compare_images":
                return self._compare(params.get("path1", ""), params.get("path2", ""), params.get("question", ""))
            if action == "find_text":
                return self._find_text(params.get("text", ""), params.get("region"))
            if action == "capture":
                return self._capture_only(params.get("region"), params.get("filename", ""))
            if action == "set_model":
                return self._set_model(params.get("model", ""))
            if action == "list_models":
                return self._list_models()
            return f"Accion desconocida en vision: {action}"
        except Exception as e:
            return {"thought": "Error vision", "display": f"Error: {e}", "voice": "Error en vision."}

    def _capture(self, region=None, save=False, filename=""):
        if region:
            try:
                x = int(region.get("x", 0))
                y = int(region.get("y", 0))
                w = int(region.get("w", 0))
                h = int(region.get("h", 0))
                img = pyautogui.screenshot(region=(x, y, w, h))
            except Exception:
                img = pyautogui.screenshot()
        else:
            img = pyautogui.screenshot()
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        b64 = base64.b64encode(buf.getvalue()).decode("utf-8")
        path = None
        if save:
            ts = int(time.time())
            name = filename or f"captura_{ts}.png"
            path = VISION_DIR / name
            img.save(str(path))
        return b64, path

    def _ollama_vision(self, b64_list, prompt, model=None):
        use_model = model or self.model
        try:
            response = ollama.chat(
                model=use_model,
                messages=[
                    {
                        "role": "user",
                        "content": prompt,
                        "images": b64_list,
                    }
                ],
                options={"temperature": 0.2},
                stream=False,
            )
            return response["message"]["content"].strip()
        except Exception as e:
            return f"[ERROR] {e}"

    def _describe_screen(self, mode, region=None):
        try:
            b64, _ = self._capture(region=region)
        except Exception as e:
            return {"thought": "Error captura", "display": f"No pude capturar la pantalla: {e}", "voice": "Error capturando pantalla."}
        prompt = PROMPTS.get(mode, PROMPTS["general"])
        texto = self._ollama_vision([b64], prompt)
        if texto.startswith("[ERROR]"):
            return {"thought": "Error vision", "display": texto, "voice": "Error en vision."}
        if not texto:
            return {"thought": "", "display": "No pude interpretar la pantalla.", "voice": "No pude interpretar."}
        return {
            "thought": f"Vision ({mode}) con {self.model}",
            "display": f"**Vision ({mode}):**\n\n{texto}",
            "voice": texto[:200],
        }

    def _describe_image(self, path_str, mode):
        if not path_str:
            return {"thought": "", "display": "Necesito la ruta de la imagen.", "voice": "Falta ruta."}
        raw = path_str.strip().strip('"').strip("'")
        p = Path(raw)
        if not p.is_absolute():
            p = ROOT / p
        if not p.exists():
            return {"thought": "", "display": f"No encontre: {p}", "voice": "No encontre imagen."}
        try:
            b64 = base64.b64encode(p.read_bytes()).decode("utf-8")
        except Exception as e:
            return {"thought": "", "display": f"Error leyendo: {e}", "voice": "Error leyendo."}
        prompt = PROMPTS.get(mode, PROMPTS["general"])
        texto = self._ollama_vision([b64], prompt)
        if texto.startswith("[ERROR]"):
            return {"thought": "Error vision", "display": texto, "voice": "Error."}
        return {
            "thought": f"Analisis de {p.name}",
            "display": f"**{p.name}:**\n\n{texto}",
            "voice": texto[:200],
        }

    def _compare(self, path1_str, path2_str, question):
        if not path1_str or not path2_str:
            return {"thought": "", "display": "Necesito 2 imagenes.", "voice": "Faltan rutas."}
        paths = []
        for ps in (path1_str, path2_str):
            p = Path(ps.strip().strip('"').strip("'"))
            if not p.is_absolute():
                p = ROOT / p
            if not p.exists():
                return {"thought": "", "display": f"No encontre: {p}", "voice": "No encontre imagen."}
            paths.append(p)
        try:
            b64_list = [base64.b64encode(p.read_bytes()).decode("utf-8") for p in paths]
        except Exception as e:
            return {"thought": "", "display": f"Error leyendo: {e}", "voice": "Error."}
        q = question or "Que diferencias hay entre estas dos imagenes? Se conciso."
        prompt = f"Tienes dos imagenes. {q} Responde en espanol."
        texto = self._ollama_vision(b64_list, prompt)
        return {
            "thought": "Comparacion de 2 imagenes",
            "display": f"**Comparacion:**\n\n{texto}",
            "voice": texto[:200],
        }

    def _find_text(self, text, region=None):
        if not text:
            return {"thought": "", "display": "Que texto busco?", "voice": "Falta texto."}
        try:
            b64, _ = self._capture(region=region)
        except Exception as e:
            return {"thought": "", "display": f"Error captura: {e}", "voice": "Error."}
        prompt = (
            f"En esta captura, busca el texto '{text}'. "
            f"Si lo ves, describe aproximadamente donde esta (arriba-izquierda, centro, etc.) "
            f"y que hay a su alrededor. Si no lo ves, di 'no visible'. "
            f"Responde en espanol, maximo 60 palabras."
        )
        texto = self._ollama_vision([b64], prompt)
        return {
            "thought": f"Buscando '{text}'",
            "display": f"**Buscando '{text}':**\n\n{texto}",
            "voice": texto[:200],
        }

    def _capture_only(self, region=None, filename=""):
        try:
            _, path = self._capture(region=region, save=True, filename=filename)
        except Exception as e:
            return {"thought": "", "display": f"Error: {e}", "voice": "Error."}
        return {
            "thought": "Captura guardada",
            "display": f"Screenshot guardado:\n{path}",
            "voice": "Captura guardada.",
        }

    def _set_model(self, model_alias):
        if not model_alias:
            return {"thought": "", "display": f"Modelo actual: {self.model}", "voice": "Modelo actual."}
        real = VISION_MODELS.get(model_alias.lower(), model_alias)
        self.model = real
        return {
            "thought": f"Modelo cambiado a {real}",
            "display": f"Modelo de vision: {real}",
            "voice": "Modelo cambiado.",
        }

    def _list_models(self):
        try:
            r = ollama.list()
            modelos = [m.get("name", "?") for m in r.get("models", [])]
            # Palabras clave de modelos de vision conocidos
            kws = ["vl", "llava", "moondream", "vision", "phi", "bunny", "minicpm", "cogvlm", "florence"]
            vision_candidates = [m for m in modelos if any(k in m.lower() for k in kws)]
            if not vision_candidates:
                # Fallback: mostrar todos
                vision_candidates = modelos
            lineas = [
                f"**Modelo actual:** {self.model}",
                "",
                "**Modelos de vision disponibles:**",
            ]
            for m in vision_candidates:
                marca = " <- actual" if m.startswith(self.model) else ""
                lineas.append(f" - {m}{marca}")
            return {
                "thought": f"{len(vision_candidates)} modelos",
                "display": "\n".join(lineas),
                "voice": f"Tienes {len(vision_candidates)} modelos de vision.",
            }
        except Exception as e:
            return {"thought": "", "display": f"Error: {e}", "voice": "Error."}
