"""Almacen de conversaciones de JARVIS/Nitro.

Guarda cada conversacion como un archivo JSON individual en
memory/conversations/YYYY-MM-DD_HH-MM-SS_<id>.json

Ademas mantiene un puntero a la conversacion actual en
memory/conversations/_current.txt para poder retomarla.

Estructura de una conversacion:
{
  "id": "2026-09-25_19-45-12_abc123",
  "titulo": "Cuadro de superficies del plano test",
  "creada": "2026-09-25T19:45:12",
  "actualizada": "2026-09-25T19:47:30",
  "mensajes": [
    {"role": "user",   "text": "...", "ts": "..."},
    {"role": "jarvis", "text": "...", "thought": "...", "artifacts": [...], "ts": "..."}
  ]
}
"""
import json
import os
import uuid
from datetime import datetime
from pathlib import Path
from threading import Lock

ROOT = Path(__file__).resolve().parent.parent
CONV_DIR = ROOT / "memory" / "conversations"
CURRENT_FILE = CONV_DIR / "_current.txt"

_lock = Lock()


def _ensure_dir():
    CONV_DIR.mkdir(parents=True, exist_ok=True)


def _now_iso():
    return datetime.now().isoformat(timespec="seconds")


def _nuevo_id():
    ts = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    sufijo = uuid.uuid4().hex[:6]
    return f"{ts}_{sufijo}"


def _ruta(id_conv):
    return CONV_DIR / f"{id_conv}.json"


def _leer_conv(id_conv):
    ruta = _ruta(id_conv)
    if not ruta.exists():
        return None
    try:
        return json.loads(ruta.read_text(encoding="utf-8"))
    except Exception:
        return None


def _escribir_conv(conv):
    _ensure_dir()
    ruta = _ruta(conv["id"])
    ruta.write_text(
        json.dumps(conv, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def _titulo_desde_texto(texto, max_len=60):
    """Genera un titulo corto a partir del primer mensaje del usuario."""
    if not texto:
        return "Conversacion"
    t = texto.strip().split("\n")[0]
    if len(t) > max_len:
        t = t[:max_len - 1].rstrip() + "…"
    return t or "Conversacion"


# ─── API PUBLICA ──────────────────────────────────────────────────────────

def new_conversation(titulo=""):
    """Crea una conversacion nueva y la marca como actual."""
    with _lock:
        _ensure_dir()
        conv = {
            "id": _nuevo_id(),
            "titulo": titulo or "Nueva conversacion",
            "creada": _now_iso(),
            "actualizada": _now_iso(),
            "mensajes": [],
        }
        _escribir_conv(conv)
        CURRENT_FILE.write_text(conv["id"], encoding="utf-8")
        return conv


def get_current_id():
    """Devuelve el ID de la conversacion actual, o None."""
    if not CURRENT_FILE.exists():
        return None
    try:
        id_conv = CURRENT_FILE.read_text(encoding="utf-8").strip()
        if id_conv and _ruta(id_conv).exists():
            return id_conv
    except Exception:
        pass
    return None


def set_current_id(id_conv):
    """Marca una conversacion existente como la actual."""
    if not _ruta(id_conv).exists():
        return False
    _ensure_dir()
    CURRENT_FILE.write_text(id_conv, encoding="utf-8")
    return True


def ensure_current():
    """Si no hay conversacion actual, crea una nueva. Devuelve el ID."""
    id_conv = get_current_id()
    if id_conv:
        return id_conv
    conv = new_conversation()
    return conv["id"]


def add_message(role, text, thought=None, artifacts=None, tipo=None):
    """Añade un mensaje a la conversacion actual.

    role: "user" o "jarvis"
    text: contenido principal
    thought: cadena opcional (razonamiento interno)
    artifacts: lista opcional de artefactos generados
    tipo: "chat" o "comando" (para futura clasificacion)
    """
    with _lock:
        id_conv = get_current_id()
        if not id_conv:
            conv = new_conversation()
            id_conv = conv["id"]
        conv = _leer_conv(id_conv)
        if not conv:
            conv = new_conversation()
            id_conv = conv["id"]

        msg = {
            "role": role,
            "text": text or "",
            "ts": _now_iso(),
        }
        if thought:
            msg["thought"] = thought
        if artifacts:
            msg["artifacts"] = artifacts
        if tipo:
            msg["tipo"] = tipo

        conv["mensajes"].append(msg)
        conv["actualizada"] = msg["ts"]

        # Auto-titulo: si es el primer mensaje del usuario y el titulo es generico
        if role == "user" and conv.get("titulo") in (None, "", "Nueva conversacion"):
            conv["titulo"] = _titulo_desde_texto(text)

        _escribir_conv(conv)
        return msg


def list_conversations(limit=50):
    """Lista conversaciones ordenadas por fecha de actualizacion desc."""
    _ensure_dir()
    conversaciones = []
    for ruta in CONV_DIR.glob("*.json"):
        try:
            data = json.loads(ruta.read_text(encoding="utf-8"))
            conversaciones.append({
                "id": data.get("id", ruta.stem),
                "titulo": data.get("titulo", ""),
                "creada": data.get("creada", ""),
                "actualizada": data.get("actualizada", ""),
                "n_mensajes": len(data.get("mensajes", [])),
            })
        except Exception:
            continue
    conversaciones.sort(key=lambda c: c.get("actualizada", ""), reverse=True)
    return conversaciones[:limit]


def get_conversation(id_conv):
    """Devuelve la conversacion completa o None."""
    return _leer_conv(id_conv)


def delete_conversation(id_conv):
    """Borra una conversacion. Si era la actual, crea una nueva."""
    with _lock:
        ruta = _ruta(id_conv)
        if not ruta.exists():
            return False
        try:
            ruta.unlink()
        except Exception:
            return False
        # Si era la actual, resetear
        actual = get_current_id()
        if actual == id_conv:
            new_conversation()
        return True


def rename_conversation(id_conv, nuevo_titulo):
    """Cambia el titulo de una conversacion."""
    with _lock:
        conv = _leer_conv(id_conv)
        if not conv:
            return False
        conv["titulo"] = nuevo_titulo or conv.get("titulo", "")
        conv["actualizada"] = _now_iso()
        _escribir_conv(conv)
        return True


if __name__ == "__main__":
    # Test rapido
    print("Directorio:", CONV_DIR)
    conv = new_conversation("Test desde CLI")
    print("Creada:", conv["id"])
    add_message("user", "Hola, esto es una prueba")
    add_message("jarvis", "Hola, te escucho", thought="Saludo normal")
    print("Lista:")
    for c in list_conversations():
        print(f"  - {c['id']}: {c['titulo']} ({c['n_mensajes']} msgs)")