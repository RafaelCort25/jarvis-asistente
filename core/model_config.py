"""Configuracion central de modelos de Ollama.

Lee y escribe config/models.json para que los agentes sepan
que modelo usar en cada categoria (chat, classifier, agent, vision).

Uso:
    from core.model_config import get_model
    modelo = get_model("chat")  # -> "dolphin-directo:latest"
"""
import json
from pathlib import Path
from threading import Lock

# Raiz del proyecto (__file__ esta en core/model_config.py)
ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT / "config" / "models.json"

# Defaults si el config no existe
DEFAULTS = {
    "chat": "llama3.2:3b",
    "classifier": "llama3.2:3b",
    "agent": "qwen2.5-coder:7b",
    "vision": "llava:7b",
}

_lock = Lock()

def _load():
    """Carga el config o devuelve defaults. Si falta alguna clave, la rellena."""
    if not CONFIG_PATH.exists():
        return dict(DEFAULTS)
    try:
        data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except Exception:
        return dict(DEFAULTS)
    for k, v in DEFAULTS.items():
        if k not in data or not data[k]:
            data[k] = v
    return data

def get_model(categoria: str) -> str:
    """Devuelve el modelo activo para una categoria.
    
    Categorias validas: chat, classifier, agent, vision.
    Si la categoria no existe, devuelve el default de 'chat'.
    """
    if categoria not in DEFAULTS:
        return DEFAULTS["chat"]
    return _load().get(categoria, DEFAULTS[categoria])

def set_model(categoria: str, modelo: str) -> bool:
    """Cambia el modelo de una categoria y guarda el config."""
    if categoria not in DEFAULTS:
        return False
    if not modelo or not modelo.strip():
        return False
    with _lock:
        data = _load()
        data[categoria] = modelo.strip()
        try:
            CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
            CONFIG_PATH.write_text(
                json.dumps(data, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
            return True
        except Exception:
            return False

def get_all() -> dict:
    """Devuelve el dict completo con todos los modelos activos."""
    return _load()

def list_categorias() -> dict:
    """Devuelve las categorias con metadata (nombre, descripcion)."""
    return {
        "chat": {
            "nombre": "Chat general",
            "descripcion": "Conversaciones normales, preguntas abiertas, brainstorming",
        },
        "classifier": {
            "nombre": "Clasificador de intent",
            "descripcion": "Detecta que skill usar para cada frase (rapido)",
        },
        "agent": {
            "nombre": "Agente (multi-paso)",
            "descripcion": "Tareas complejas que requieren varios pasos",
        },
        "vision": {
            "nombre": "Vision",
            "descripcion": "Analiza imagenes y pantalla",
        },
    }