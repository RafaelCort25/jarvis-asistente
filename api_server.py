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
from core import onboarding as _onb

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
    # Asegurar que hay una conversación activa
    _conv.ensure_current()

    text = msg.text
    result_data = None

    # ─── MULTIAGENTE (si esta activado) ─────────────────────────────────
    if USE_MULTIAGENT:
        try:
            ma = _get_multiagent()
            res = ma.run(text, router=router)
            respuesta = res.get("respuesta", "")
            response = {
                "type": "multiagent",
                "text": respuesta,
                "voice": clean_voice(respuesta),
                "thought": f"Agentes: {', '.join(res.get('agentes_usados', []))}",
                "artifacts": [],
                "agentes": res.get("agentes_usados", []),
                "plan": res.get("plan", []),
            }
            result_data = {"display": respuesta, "thought": response["thought"], "artifacts": []}
            try:
                _conv.add_message("user", text)
                _conv.add_message(
                    "jarvis",
                    respuesta,
                    thought=response.get("thought"),
                    artifacts=None,
                )
            except Exception as _e:
                print(f"[CHAT/MULTIAGENT] Error guardando historial: {_e}")
            return response
        except Exception as e:
            import traceback
            print(f"[MULTIAGENT ERROR] {e}")
            traceback.print_exc()
            # Continuar con router normal

    try:
        result, is_chat = router.route(text)
    except Exception as e:
        import traceback
        print(f"[API/CHAT ERROR] {e}")
        traceback.print_exc()
        response = {
            "type": "error",
            "text": f"Error procesando el comando: {e}",
            "voice": "Hubo un error interno.",
            "thought": "",
            "artifacts": [],
        }
        result_data = {"display": response["text"], "thought": "", "artifacts": []}
        
        # Guardar en el historial
        try:
            _conv.add_message("user", text)
            _conv.add_message(
                "jarvis",
                result_data.get("display", ""),
                thought=result_data.get("thought"),
                artifacts=result_data.get("artifacts"),
            )
        except Exception as _e:
            print(f"[CHAT] Error guardando historial: {_e}")
        return response

    if result:
        display = result.get("display", "")
        voice = result.get("voice", "")
        thought = result.get("thought", "")
        artifacts = _extract_artifacts(display or voice)
        voice_clean = clean_voice(voice or display) or "Listo."
        
        response = {
            "type": "command",
            "text": display or voice or "Listo.",
            "voice": voice_clean,
            "thought": thought,
            "artifacts": artifacts,
        }
        result_data = {
            "display": response["text"],
            "thought": thought,
            "artifacts": artifacts,
        }

    elif is_chat:
        try:
            reply = brain.chat(text)
            response = {
                "type": "chat",
                "text": reply,
                "voice": clean_voice(reply),
                "artifacts": [],
            }
            result_data = {"display": reply, "thought": "", "artifacts": []}
        except Exception as e:
            print(f"[API/BRAIN ERROR] {e}")
            response = {
                "type": "error",
                "text": f"Error en el cerebro: {e}",
                "voice": "Error en el cerebro.",
                "thought": "",
                "artifacts": [],
            }
            result_data = {"display": response["text"], "thought": "", "artifacts": []}
    else:
        response = {
            "type": "unknown",
            "text": "No entendi el comando.",
            "voice": "",
            "artifacts": [],
        }
        result_data = {"display": response["text"], "thought": "", "artifacts": []}

    # Guardar en el historial
    try:
        _conv.add_message("user", text)
        _conv.add_message(
            "jarvis",
            result_data.get("display", result_data.get("voice", "")),
            thought=result_data.get("thought"),
            artifacts=result_data.get("artifacts"),
        )
    except Exception as _e:
        print(f"[CHAT] Error guardando historial: {_e}")

    return response
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
@app.post("/upload")
async def upload(file: UploadFile = File(...)):
    """Recibe un archivo y lo guarda en sandbox/uploads/."""
    uploads_dir = SANDBOX_DIR / "uploads"
    uploads_dir.mkdir(parents=True, exist_ok=True)

    # Sanear el nombre del archivo
    from pathlib import PurePath
    safe_name = PurePath(file.filename).name
    # Quitar caracteres problematicos
    safe_name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', safe_name)
    if not safe_name:
        return {"ok": False, "error": "Nombre de archivo invalido"}

    target = uploads_dir / safe_name

    # Si ya existe, anadir sufijo numerico
    if target.exists():
        stem = target.stem
        suffix = target.suffix
        i = 1
        while target.exists():
            target = uploads_dir / f"{stem}_{i}{suffix}"
            i += 1

    try:
        content = await file.read()
        target.write_bytes(content)
    except Exception as e:
        return {"ok": False, "error": str(e)}

    size_kb = len(content) // 1024
    print(f"[API] Upload: {target.name} ({size_kb} KB)")

    return {
        "ok": True,
        "path": str(target),
        "name": target.name,
        "size": len(content),
    }

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
# ═══════════════════════════════════════════════════════════════════════════
# ONBOARDING — Estado del sistema
# ═══════════════════════════════════════════════════════════════════════════

@app.get("/onboarding/status")
def onboarding_status():
    """Estado completo del sistema: Python, Ollama, herramientas, credenciales."""
    status = _onb.check_all()
    resumen = _onb.resumen_corto(status)
    return {
        "done": _onb.is_done(),
        "ok": resumen["ok"],
        "problemas": resumen["problemas"],
        "detalle": {
            "python": status["python"],
            "ollama": status["ollama"],
            "tools": status["tools"],
            "credentials": status["credentials"],
            "dirs": status["dirs"],
            "root": status["root"],
        },
    }


@app.post("/onboarding/mark_done")
def onboarding_mark_done():
    ok = _onb.mark_done()
    return {"ok": ok}


@app.post("/onboarding/reset")
def onboarding_reset():
    ok = _onb.reset()
    return {"ok": ok}


# ═══════════════════════════════════════════════════════════════════════════
# CREDENCIALES — Guardar .env.tmp
# ═══════════════════════════════════════════════════════════════════════════

INTEGRACIONES = {
    "n8n": {
        "nombre": "n8n",
        "descripcion": "Automatizacion de workflows (localhost:5678)",
        "archivo": ".env.n8n.tmp",
        "url_docs": "http://localhost:5678/",
        "campos": [
            {"key": "N8N_API_KEY", "label": "API Key", "placeholder": "n8n_api_...", "tipo": "password"},
            {"key": "N8N_BASE_URL", "label": "URL base", "placeholder": "http://localhost:5678", "tipo": "text"},
        ],
    },
    "gmail": {
        "nombre": "Gmail",
        "descripcion": "Correo electronico (requiere 2FA + app password)",
        "archivo": ".env.gmail.tmp",
        "url_docs": "https://myaccount.google.com/apppasswords",
        "campos": [
            {"key": "GMAIL_USER", "label": "Correo de Gmail", "placeholder": "tu@gmail.com", "tipo": "email"},
            {"key": "GMAIL_APP_PASSWORD", "label": "App password (16 caracteres)", "placeholder": "abcd efgh ijkl mnop", "tipo": "password"},
        ],
    },
    "canva": {
        "nombre": "Canva",
        "descripcion": "Diseno grafico (OAuth + Connect API)",
        "archivo": ".env.canva.tmp",
        "url_docs": "https://www.canva.com/developers/",
        "campos": [
            {"key": "CANVA_CLIENT_ID", "label": "Client ID", "placeholder": "OC-...", "tipo": "text"},
            {"key": "CANVA_CLIENT_SECRET", "label": "Client Secret", "placeholder": "cnvca...", "tipo": "password"},
            {"key": "CANVA_REDIRECT_URI", "label": "Redirect URI", "placeholder": "http://127.0.0.1:8080/callback", "tipo": "text"},
        ],
    },
    "maps": {
        "nombre": "Google Maps",
        "descripcion": "Geocoding + Places (opcional, alternativa: OpenStreetMap)",
        "archivo": ".env.maps.tmp",
        "url_docs": "https://console.cloud.google.com/",
        "campos": [
            {"key": "GOOGLE_MAPS_API_KEY", "label": "API Key", "placeholder": "AIza...", "tipo": "password"},
        ],
    },
    "telegram": {
        "nombre": "Telegram",
        "descripcion": "Bot de Telegram para notificaciones",
        "archivo": ".env.telegram.tmp",
        "url_docs": "https://core.telegram.org/bots#how-do-i-create-a-bot",
        "campos": [
            {"key": "TELEGRAM_BOT_TOKEN", "label": "Bot Token", "placeholder": "123456789:ABC...", "tipo": "password"},
            {"key": "TELEGRAM_CHAT_ID", "label": "Chat ID", "placeholder": "123456789", "tipo": "text"},
        ],
    },
}


@app.get("/credentials/list")
def credentials_list():
    """Lista de integraciones y su estado de configuracion."""
    resultado = []
    for key, info in INTEGRACIONES.items():
        archivo = ROOT / info["archivo"]
        configurado = False
        valores_mascara = {}
        if archivo.exists():
            configurado = True
            try:
                for line in archivo.read_text(encoding="utf-8").splitlines():
                    if "=" in line:
                        k, v = line.split("=", 1)
                        k = k.strip()
                        v = v.strip()
                        # Enmascarar valores sensibles
                        if len(v) > 6:
                            valores_mascara[k] = v[:3] + "…" + v[-3:]
                        else:
                            valores_mascara[k] = "…"
            except Exception:
                pass

        resultado.append({
            "id": key,
            "nombre": info["nombre"],
            "descripcion": info["descripcion"],
            "url_docs": info.get("url_docs", ""),
            "configurado": configurado,
            "campos": info["campos"],
            "valores_actuales": valores_mascara,
        })
    return {"integraciones": resultado}


class CredencialesPayload(BaseModel):
    integracion: str
    valores: dict


@app.post("/credentials/save")
def credentials_save(payload: CredencialesPayload):
    """Guarda los valores de una integracion en su .env.tmp."""
    if payload.integracion not in INTEGRACIONES:
        return {"ok": False, "error": "Integracion desconocida"}

    info = INTEGRACIONES[payload.integracion]
    archivo = ROOT / info["archivo"]

    # Leer existentes
    existentes = {}
    if archivo.exists():
        try:
            for line in archivo.read_text(encoding="utf-8-sig").splitlines():
                if "=" in line:
                    k, v = line.split("=", 1)
                    existentes[k.strip()] = v.strip()
        except Exception:
            pass

    # Actualizar (solo valores no vacios)
    for k, v in payload.valores.items():
        if v and str(v).strip():
            existentes[k] = str(v).strip()

    # Guardar
    try:
        lineas = [f"{k}={v}" for k, v in existentes.items()]
        archivo.write_text("\n".join(lineas) + "\n", encoding="utf-8")
        return {"ok": True, "archivo": str(archivo), "campos_guardados": len(existentes)}
    except Exception as e:
        return {"ok": False, "error": str(e)}


# ═══════════════════════════════════════════════════════════════════════════
# SKILLS — Listar y estado
# ═══════════════════════════════════════════════════════════════════════════

@app.get("/skills/list")
def skills_list():
    """Lista todas las skills registradas en el router."""
    try:
        from core.router import Router
        # Cache simple en memoria para no reinstanciar
        if not hasattr(skills_list, "_cache"):
            r = Router()
            skills_list._cache = sorted(r.skills.keys())
        return {"skills": skills_list._cache, "total": len(skills_list._cache)}
    except Exception as e:
        return {"skills": [], "total": 0, "error": str(e)}

    

# ═══════════════════════════════════════════════════════════════════════════
# AGENTES MULTIAGENTE
# ═══════════════════════════════════════════════════════════════════════════

USE_MULTIAGENT = False
_multiagent_instance = None

def _get_multiagent():
    global _multiagent_instance
    if _multiagent_instance is None:
        from core.agents.multiagent import MultiAgent
        _multiagent_instance = MultiAgent()
    return _multiagent_instance


AGENTES_INFO = [
    {"id": "supervisor", "nombre": "Supervisor", "descripcion": "Planifica qué agente usar"},
    {"id": "dev", "nombre": "DEV", "descripcion": "Programación, scripts, código"},
    {"id": "research", "nombre": "RESEARCH", "descripcion": "Investigación, explicaciones"},
    {"id": "execute", "nombre": "EXECUTE", "descripcion": "Control del sistema"},
    {"id": "chat", "nombre": "CHAT", "descripcion": "Conversación casual"},
]


@app.get("/agents/list")
def agents_list():
    """Devuelve el estado del multiagente + config + modelos disponibles."""
    import json
    cfg_path = ROOT / "config" / "agents.json"
    config = {}
    try:
        if cfg_path.exists():
            config = json.loads(cfg_path.read_text(encoding="utf-8"))
    except Exception:
        pass
    modelos = []
    try:
        import requests as _rq
        r = _rq.get("http://localhost:11434/api/tags", timeout=3)
        if r.status_code == 200:
            modelos = sorted([m.get("name", "") for m in r.json().get("models", [])])
    except Exception:
        pass
    return {
        "ok": True,
        "enabled": USE_MULTIAGENT,
        "agentes": AGENTES_INFO,
        "config": config,
        "modelos": modelos,
    }


@app.post("/agents/toggle")
def agents_toggle(payload: dict):
    global USE_MULTIAGENT
    USE_MULTIAGENT = bool(payload.get("enabled", False))
    return {"ok": True, "enabled": USE_MULTIAGENT}


class AgentModelPayload(BaseModel):
    agente: str
    modelo: str


@app.post("/agents/set-model")
def agents_set_model(payload: AgentModelPayload):
    import json
    if payload.agente not in ("supervisor", "dev", "research", "execute", "chat"):
        return {"ok": False, "error": "Agente desconocido"}
    cfg_path = ROOT / "config" / "agents.json"
    try:
        config = json.loads(cfg_path.read_text(encoding="utf-8")) if cfg_path.exists() else {}
        config[payload.agente] = {"model": payload.modelo, "enabled": True}
        cfg_path.write_text(json.dumps(config, indent=2, ensure_ascii=False), encoding="utf-8")
        # Resetear la instancia para que recoja los nuevos modelos
        global _multiagent_instance
        _multiagent_instance = None
        return {"ok": True, "config": config}
    except Exception as e:
        return {"ok": False, "error": str(e)}


# ═══════════════════════════════════════════════════════════════════════════
# CONVERSACIONES — Historial de chats
# ═══════════════════════════════════════════════════════════════════════════

from core import conversation_store as _conv

@app.get("/conversations/list")
def conversations_list():
    """Lista todas las conversaciones guardadas."""
    try:
        items = _conv.list_conversations(limit=100)
        actual = _conv.get_current_id()
        return {"ok": True, "conversaciones": items, "actual": actual}
    except Exception as e:
        return {"ok": False, "error": str(e), "conversaciones": [], "actual": None}

@app.get("/conversations/get")
def conversations_get(id: str = Query(..., description="ID de la conversacion")):
    """Devuelve una conversacion completa."""
    try:
        conv = _conv.get_conversation(id)
        if not conv:
            return {"ok": False, "error": "Conversacion no encontrada"}
        return {"ok": True, "conversacion": conv}
    except Exception as e:
        return {"ok": False, "error": str(e)}

class ConvSelectPayload(BaseModel):
    id: str = ""

@app.post("/conversations/new")
def conversations_new():
    """Crea una conversacion nueva y la marca como actual."""
    try:
        conv = _conv.new_conversation()
        return {"ok": True, "conversacion": conv}
    except Exception as e:
        return {"ok": False, "error": str(e)}

@app.post("/conversations/select")
def conversations_select(payload: ConvSelectPayload):
    """Marca una conversacion como la actual."""
    try:
        if not payload.id:
            return {"ok": False, "error": "ID vacio"}
        if not _conv.set_current_id(payload.id):
            return {"ok": False, "error": "No existe esa conversacion"}
        return {"ok": True, "actual": payload.id}
    except Exception as e:
        return {"ok": False, "error": str(e)}

@app.post("/conversations/delete")
def conversations_delete(payload: ConvSelectPayload):
    """Borra una conversacion."""
    try:
        if not payload.id:
            return {"ok": False, "error": "ID vacio"}
        if not _conv.delete_conversation(payload.id):
            return {"ok": False, "error": "No se pudo borrar"}
        return {"ok": True}
    except Exception as e:
        return {"ok": False, "error": str(e)}

@app.post("/conversations/rename")
def conversations_rename(payload: dict):
    """Renombra una conversacion."""
    try:
        id_conv = payload.get("id", "")
        titulo = payload.get("titulo", "")
        if not id_conv:
            return {"ok": False, "error": "ID vacio"}
        if not _conv.rename_conversation(id_conv, titulo):
            return {"ok": False, "error": "No se pudo renombrar"}
        return {"ok": True}
    except Exception as e:
        return {"ok": False, "error": str(e)}
    # ═══════════════════════════════════════════════════════════════════════════
# MODELOS — Selección de modelos de Ollama
# ═══════════════════════════════════════════════════════════════════════════

MODELS_CONFIG_PATH = ROOT / "config" / "models.json"

# Modelo por defecto si el config no existe o está corrupto
MODELOS_DEFAULT = {
    "chat": "llama3.2:3b",
    "classifier": "llama3.2:3b",
    "agent": "qwen2.5-coder:7b",
    "vision": "llava:7b",
}

# Categorías con descripción
CATEGORIAS_MODELO = {
    "chat": {
        "nombre": "Chat general",
        "descripcion": "Conversaciones normales, preguntas abiertas, brainstorming",
        "criterio": "Modelo rápido y generalista",
    },
    "classifier": {
        "nombre": "Clasificador de intent",
        "descripcion": "Detecta qué skill usar para cada frase (rápido)",
        "criterio": "Muy rápido, se llama muchas veces",
    },
    "agent": {
        "nombre": "Agente (multi-paso)",
        "descripcion": "Tareas complejas que requieren varios pasos",
        "criterio": "Bueno en código y razonamiento",
    },
    "vision": {
        "nombre": "Visión",
        "descripcion": "Analiza imágenes y pantalla",
        "criterio": "Modelo multimodal (llava, minicpm-v)",
    },
}


def _load_models_config():
    """Carga config/models.json o devuelve los defaults."""
    if not MODELS_CONFIG_PATH.exists():
        return dict(MODELOS_DEFAULT)
    try:
        import json as _json
        data = _json.loads(MODELS_CONFIG_PATH.read_text(encoding="utf-8"))
        # Rellenar faltantes con defaults
        for k, v in MODELOS_DEFAULT.items():
            if k not in data:
                data[k] = v
        return data
    except Exception as e:
        print(f"[MODELS] Error leyendo config: {e}")
        return dict(MODELOS_DEFAULT)


def _save_models_config(config):
    """Guarda config/models.json."""
    try:
        MODELS_CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
        import json as _json
        MODELS_CONFIG_PATH.write_text(
            _json.dumps(config, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        return True
    except Exception as e:
        print(f"[MODELS] Error guardando config: {e}")
        return False


@app.get("/models/list")
def models_list():
    """Devuelve los modelos disponibles en Ollama + el activo por categoría."""
    try:
        import requests as _rq
        r = _rq.get("http://localhost:11434/api/tags", timeout=3)
        if r.status_code != 200:
            return {"ok": False, "error": "Ollama no responde"}
        data = r.json()
        modelos = [m.get("name", "") for m in data.get("models", [])]
        modelos.sort()
        return {
            "ok": True,
            "modelos": modelos,
            "activo": _load_models_config(),
            "categorias": CATEGORIAS_MODELO,
        }
    except Exception as e:
        return {"ok": False, "error": str(e), "modelos": [], "activo": _load_models_config(), "categorias": CATEGORIAS_MODELO}


class ModeloPayload(BaseModel):
    categoria: str
    modelo: str


@app.post("/models/set")
def models_set(payload: ModeloPayload):
    """Cambia el modelo activo para una categoría."""
    if payload.categoria not in MODELOS_DEFAULT:
        return {"ok": False, "error": f"Categoría desconocida: {payload.categoria}"}
    if not payload.modelo.strip():
        return {"ok": False, "error": "Modelo vacío"}

    config = _load_models_config()
    config[payload.categoria] = payload.modelo.strip()
    if _save_models_config(config):
        return {"ok": True, "activo": config}
    return {"ok": False, "error": "No se pudo guardar"}