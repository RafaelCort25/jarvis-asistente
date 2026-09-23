"""
API de Jarvis: expone el brain/router + sirve la interfaz web (orbe).
"""
import os
import re
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, File, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from core.brain import Brain
from core.router import Router
from core.voice_cleaner import clean_voice

ROOT = Path(__file__).resolve().parent

app = FastAPI(title="Jarvis API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

brain = Brain()
router = Router()
# Configurar confirmacion para el contexto GUI
# En modo GUI (Electron), las acciones se auto-aprueban porque:
# 1. El usuario esta viendo la accion en pantalla.
# 2. La GUI todavia no soporta dialogo interactivo.
# 3. En modo voz (main.py) SI se pide confirmacion por voz.
from core import confirmation

def _gui_confirmation(skill, action, summary, level, timeout=30):
    print(f"[GUI/CONFIRM] Auto-aprobado ({level}): {skill}.{action} - {summary[:80]}")
    return True

confirmation.set_handler(_gui_confirmation)
print("[API] Handler de confirmacion GUI instalado (auto-aprobar).")

# Servir archivos generados (imágenes, documentos) por HTTP
SANDBOX_DIR = ROOT / "sandbox"
SANDBOX_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/sandbox", StaticFiles(directory=str(SANDBOX_DIR)), name="sandbox")


class Message(BaseModel):
    text: str


# ─── Deteccion de artefactos en las respuestas ─────────────────────────

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp"}
DOC_EXTS = {".docx", ".xlsx", ".pptx", ".pdf", ".txt", ".md", ".csv"}
CODE_EXTS = {".py", ".js", ".java", ".html", ".css", ".json", ".yml", ".yaml", ".sh", ".ps1"}


def _to_url(path_str):
    """Convierte una ruta absoluta dentro de ROOT a URL relativa /sandbox/..."""
    try:
        p = Path(path_str).resolve()
        rel = p.relative_to(ROOT.resolve())
        return "/" + str(rel).replace("\\", "/")
    except (ValueError, OSError):
        return None


def _extract_artifacts(text):
    """Busca rutas de archivo en el texto y las clasifica."""
    if not text:
        return []

    found = []
    seen = set()

    patterns = [
        r'[A-Za-z]:\\[^\s\n\r"\'<>|]+',   # Windows: C:\...
        r'/[^\s\n\r"\'<>|]+',              # Unix: /home/...
    ]

    for pattern in patterns:
        for m in re.finditer(pattern, text):
            raw = m.group(0).rstrip(".,;:!?)]}\"'")
            raw = raw.replace("`", "")
            p = Path(raw)
            ext = p.suffix.lower()

            if ext not in (IMAGE_EXTS | DOC_EXTS | CODE_EXTS):
                continue

            key = str(p).lower()
            if key in seen:
                continue
            seen.add(key)

            item = {
                "path": str(p),
                "name": p.name,
                "ext": ext.lstrip("."),
                "exists": p.exists(),
            }

            if ext in IMAGE_EXTS:
                item["type"] = "image"
                item["url"] = _to_url(str(p))
            elif ext in DOC_EXTS:
                item["type"] = "document"
            else:
                item["type"] = "code"

            found.append(item)

    return found


# ─── Endpoints ─────────────────────────────────────────────────────────

@app.post("/chat")
def chat(msg: Message):
    result, is_chat = router.route(msg.text)

    if result:
        display = result.get("display", "")
        voice = result.get("voice", "")
        thought = result.get("thought", "")
        artifacts = _extract_artifacts(display or voice)
        # Limpiar la voz para el TTS del navegador
        voice_clean = clean_voice(voice or display) or "Listo."
        return {
            "type": "command",
            "text": display or voice or "Listo.",
            "voice": voice_clean,
            "thought": thought,
            "artifacts": artifacts,
        }

    if is_chat:
        reply = brain.chat(msg.text)
        return {
            "type": "chat",
            "text": reply,
            "voice": clean_voice(reply),
            "artifacts": [],
        }

    return {
        "type": "unknown",
        "text": "No entendi el comando.",
        "voice": "",
        "artifacts": [],
    }
@app.post("/copy_image")
def copy_image(path: str = Query(...)):
    """Copia una imagen al portapapeles de Windows."""
    try:
        p = Path(path).resolve()
        p.relative_to(ROOT.resolve())
    except (ValueError, OSError):
        return {"ok": False, "error": "Ruta fuera del proyecto o invalida"}

    if not p.exists():
        return {"ok": False, "error": "El archivo no existe"}

    if p.suffix.lower() not in IMAGE_EXTS:
        return {"ok": False, "error": f"No es una imagen: {p.suffix}"}

    try:
        from io import BytesIO
        from PIL import Image
        import win32clipboard

        image = Image.open(str(p))
        # Convertir a RGB (por si es PNG con alpha)
        if image.mode != "RGB":
            image = image.convert("RGB")

        output = BytesIO()
        image.save(output, "BMP")
        # Quitar la cabecera BMP (los primeros 14 bytes)
        data = output.getvalue()[14:]
        output.close()

        win32clipboard.OpenClipboard()
        win32clipboard.EmptyClipboard()
        win32clipboard.SetClipboardData(win32clipboard.CF_DIB, data)
        win32clipboard.CloseClipboard()

        print(f"[API] Imagen copiada al portapapeles: {p.name}")
        return {"ok": True}
    except Exception as e:
        print(f"[API/COPY ERROR] {e}")
        return {"ok": False, "error": str(e)}

@app.post("/open_file")
def open_file(path: str = Query(...)):
    """Abre un archivo con la aplicacion por defecto de Windows."""
    try:
        p = Path(path).resolve()
        p.relative_to(ROOT.resolve())
    except (ValueError, OSError):
        return {"ok": False, "error": "Ruta fuera del proyecto o invalida"}

    if not p.exists():
        return {"ok": False, "error": "El archivo no existe"}

    try:
        os.startfile(str(p))
        return {"ok": True}
    except Exception as e:
        return {"ok": False, "error": str(e)}
    


@app.post("/reset")
def reset():
    brain.reset()
    return {"ok": True}


@app.get("/health")
def health():
    return {"status": "ok"}
@app.get("/resolve_url")
def resolve_url(url: str = Query(...)):
    """Convierte una URL relativa (/sandbox/...) a un path absoluto."""
    try:
        # Quitar el slash inicial y normalizar
        clean = url.lstrip("/").replace("/", "\\")
        full = (ROOT / clean).resolve()
        full.relative_to(ROOT.resolve())
        if not full.exists():
            return {"ok": False, "error": "No existe"}
        return {"ok": True, "path": str(full)}
    except Exception as e:
        return {"ok": False, "error": str(e)}


# ─── Transcripcion de audio (STT) ──────────────────────────────────────

_stt_instance = None


def _get_stt():
    global _stt_instance
    if _stt_instance is None:
        from voice.stt import STT
        _stt_instance = STT()
    return _stt_instance


@app.post("/transcribe")
async def transcribe(audio: UploadFile = File(...)):
    """Recibe audio (webm/ogg/wav) y devuelve texto transcrito."""
    import tempfile
    try:
        stt = _get_stt()
        contents = await audio.read()

        with tempfile.NamedTemporaryFile(suffix=".webm", delete=False) as f:
            f.write(contents)
            path = f.name

        try:
            segments, _ = stt.model.transcribe(
                path,
                language=stt.language,
                initial_prompt=stt.initial_prompt,
                vad_filter=True,
                vad_parameters=dict(min_silence_duration_ms=200),
                beam_size=1,
                temperature=0.0,
                condition_on_previous_text=False,
            )
            text = " ".join(seg.text for seg in segments).strip()
            cleaned = stt.clean(text)
            print(f"[API/T] raw={text!r} limpio={cleaned!r}")
            return {"text": cleaned}
        finally:
            if os.path.exists(path):
                os.remove(path)
    except Exception as e:
        print(f"[API/T ERROR] {e}")
        return {"text": "", "error": str(e)}


# ─── Interfaz web ──────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
def index():
    """Sirve la interfaz del orbe."""
    for name in [
        "jarvis-orb.html",
        "jarvis_orb.html",
        "jarvis-orb-connected.html",
    ]:
        html_path = ROOT / name
        if html_path.exists():
            print(f"[API] Sirviendo {name}")
            return HTMLResponse(html_path.read_text(encoding="utf-8"))
    return HTMLResponse(
        "<h1>Falta el archivo HTML</h1>"
        "<p>Coloca jarvis-orb.html en la raiz del proyecto.</p>",
        status_code=404,
    )