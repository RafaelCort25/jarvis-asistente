"""Sistema de aprendizaje de procedimientos de Senna.

Permite grabar secuencias de comandos y reproducirlas con un solo nombre.

Ejemplo:
    > aprende el procedimiento matutino
    > abre gmail
    > lee mis correos
    > resume el ultimo correo
    > termina el procedimiento

    > ejecuta el procedimiento matutino
    (Senna hace los 3 pasos automaticamente)
"""
import json
from datetime import datetime
from pathlib import Path
from threading import Lock

ROOT = Path(__file__).resolve().parent.parent
PROCEDURES_FILE = ROOT / "memory" / "procedures.json"

_lock = Lock()

# Estado global de grabacion (en memoria)
_recording = {
    "active": False,
    "name": "",
    "steps": [],
    "started_at": None,
}


def _ensure_dir():
    PROCEDURES_FILE.parent.mkdir(parents=True, exist_ok=True)


def _load_all():
    """Carga todos los procedimientos guardados."""
    if not PROCEDURES_FILE.exists():
        return {}
    try:
        return json.loads(PROCEDURES_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_all(data):
    """Guarda todos los procedimientos."""
    _ensure_dir()
    PROCEDURES_FILE.write_text(
        json.dumps(data, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def _normalize_name(name):
    """Normaliza el nombre: minusculas, sin espacios extra."""
    return name.strip().lower()


# ─── GRABACION ────────────────────────────────────────────────────────────

def start_recording(name):
    """Empieza a grabar un procedimiento."""
    with _lock:
        if _recording["active"]:
            return False, f"Ya estoy grabando '{_recording['name']}'. Termina primero."

        name = _normalize_name(name)
        if not name:
            return False, "Necesito un nombre para el procedimiento."

        _recording["active"] = True
        _recording["name"] = name
        _recording["steps"] = []
        _recording["started_at"] = datetime.now().isoformat(timespec="seconds")

        return True, f"Grabando procedimiento '{name}'. Di 'termina el procedimiento' cuando acabes."


def add_step(text):
    """Anade un paso durante la grabacion."""
    with _lock:
        if not _recording["active"]:
            return False

        text = text.strip()
        if not text:
            return False

        # No guardar el comando de terminar
        if _es_terminar(text):
            return False

        _recording["steps"].append({
            "text": text,
            "ts": datetime.now().isoformat(timespec="seconds"),
        })
        return True


def stop_recording():
    """Termina la grabacion y guarda el procedimiento."""
    with _lock:
        if not _recording["active"]:
            return False, "No estoy grabando ningun procedimiento."

        name = _recording["name"]
        steps = _recording["steps"]

        _recording["active"] = False
        _recording["name"] = ""
        _recording["steps"] = []

        if not steps:
            return False, f"El procedimiento '{name}' quedo vacio. No lo guarde."

        # Guardar en el archivo
        data = _load_all()
        data[name] = {
            "name": name,
            "steps": steps,
            "creado": _recording.get("started_at") or datetime.now().isoformat(timespec="seconds"),
            "actualizado": datetime.now().isoformat(timespec="seconds"),
            "n_pasos": len(steps),
        }
        _save_all(data)

        return True, f"Procedimiento '{name}' guardado con {len(steps)} pasos."


def is_recording():
    return _recording["active"]


def current_recording_name():
    return _recording["name"] if _recording["active"] else ""


def current_steps_count():
    return len(_recording["steps"]) if _recording["active"] else 0


# ─── LISTAR / OBTENER ─────────────────────────────────────────────────────

def list_procedures():
    """Devuelve lista de procedimientos guardados."""
    data = _load_all()
    resultado = []
    for name, info in data.items():
        resultado.append({
            "name": name,
            "n_pasos": info.get("n_pasos", len(info.get("steps", []))),
            "creado": info.get("creado", ""),
            "actualizado": info.get("actualizado", ""),
        })
    resultado.sort(key=lambda x: x.get("actualizado", ""), reverse=True)
    return resultado


def get_procedure(name):
    """Devuelve los pasos de un procedimiento o None."""
    data = _load_all()
    return data.get(_normalize_name(name))


def delete_procedure(name):
    """Borra un procedimiento."""
    with _lock:
        data = _load_all()
        name = _normalize_name(name)
        if name not in data:
            return False
        del data[name]
        _save_all(data)
        return True


# ─── HELPERS ──────────────────────────────────────────────────────────────

def _es_terminar(text):
    """Detecta si el texto es un comando de terminar grabacion."""
    t = text.lower().strip()
    return any(p in t for p in [
        "termina el procedimiento", "termina procedimiento",
        "para el procedimiento", "para de grabar",
        "termina de grabar", "deten la grabacion",
    ])


if __name__ == "__main__":
    # Test rapido
    print("=== Test de procedures.py ===")

    ok, msg = start_recording("test")
    print(f"start: {ok} -> {msg}")

    add_step("abre gmail")
    add_step("lee mis correos")
    add_step("resume el ultimo correo")

    print(f"Pasos grabados: {current_steps_count()}")

    ok, msg = stop_recording()
    print(f"stop: {ok} -> {msg}")

    print()
    print("=== Procedimientos guardados ===")
    for p in list_procedures():
        print(f"  {p['name']}: {p['n_pasos']} pasos")

    print()
    print("=== Detalle de 'test' ===")
    proc = get_procedure("test")
    if proc:
        for i, s in enumerate(proc["steps"], 1):
            print(f"  {i}. {s['text']}")
