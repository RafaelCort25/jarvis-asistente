"""
API de Jarvis: expone el brain/router + sirve la interfaz web (orbe).
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from pathlib import Path

from core.brain import Brain
from core.router import Router

app = FastAPI(title="Jarvis API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

brain = Brain()
router = Router()

ROOT = Path(__file__).resolve().parent


class Message(BaseModel):
    text: str


@app.post("/chat")
def chat(msg: Message):
    result, is_chat = router.route(msg.text)

    if result:
        display = result.get("display", "")
        voice = result.get("voice", "")
        thought = result.get("thought", "")
        return {
            "type": "command",
            "text": display or voice or "Listo.",
            "voice": voice or display,
            "thought": thought,
        }

    if is_chat:
        reply = brain.chat(msg.text)
        return {"type": "chat", "text": reply, "voice": reply[:600]}

    return {"type": "unknown", "text": "No entendi el comando.", "voice": ""}


@app.post("/reset")
def reset():
    brain.reset()
    return {"ok": True}


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/", response_class=HTMLResponse)
def index():
    """Sirve la interfaz del orbe."""
    for name in [
        "jarvis-orb.html",
        "jarvis_orb.html",
        "jarvis-orb-connected.html",
        "jarvis-orb.html",
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
from fastapi import UploadFile, File
import tempfile
import os

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