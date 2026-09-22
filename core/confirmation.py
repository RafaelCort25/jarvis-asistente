"""Capa de confirmación central: skills de riesgo piden autorización."""
import threading
import time
from datetime import datetime

# Handler externo: main.py inyecta la función que sabe preguntar por voz
_ask_handler = None
_handler_lock = threading.Lock()

# Timeout por defecto para esperar respuesta
DEFAULT_TIMEOUT = 30


# Niveles de riesgo por (skill, action).
# "low"    = auto-aprueba, no pregunta
# "medium" = pregunta siempre
# "high"   = pregunta siempre + advertencia
RISK_LEVELS = {
    # Skill desktop
    ("desktop", "open_app"): "low",
    ("desktop", "open_folder"): "low",
    ("desktop", "volume_up"): "low",
    ("desktop", "volume_down"): "low",
    ("desktop", "mute"): "low",

    # Browser
    ("browser", "search_youtube"): "low",
    ("browser", "search_google"): "low",
    ("browser", "open_url"): "low",
    ("browser", "play_pending"): "low",
    ("browser", "cancel_pending"): "low",

    # Sistema
    ("system", "screenshot"): "low",
    ("system", "lock"): "medium",
    ("system", "sleep"): "medium",
    ("system", "shutdown"): "high",
    ("system", "restart"): "high",
    ("system", "cancel_shutdown"): "low",

    # Files
    ("files", "find_file"): "low",
    ("files", "list_folder"): "low",
    ("files", "move"): "medium",
    ("files", "delete"): "high",

    # Dev
    ("dev", "review_file"): "low",
    ("dev", "review_project"): "low",
    ("dev", "explain"): "low",
    ("dev", "find_issues"): "low",
    ("dev", "generate_code"): "low",
        # Dev write/run
    ("dev", "write_file"): "high",
    ("dev", "run_file"): "high",
    ("dev", "create_and_test"): "high",
        # Office
    ("office", "create_doc"): "medium",
    ("office", "read_doc"): "low",

    # Docs / RAG
    ("docs", "ask"): "low",
    ("docs", "list"): "low",
    ("docs", "index_file"): "low",
    ("docs", "index_folder"): "low",
    ("docs", "delete"): "medium",

    # Clipboard
    ("clipboard", "read"): "low",
    ("clipboard", "write"): "low",

    # Scheduler
    ("scheduler", "add_once"): "low",
    ("scheduler", "add_daily"): "low",
    ("scheduler", "add_interval"): "low",
    ("scheduler", "list"): "low",
    ("scheduler", "cancel"): "low",

    # Vision
    ("vision", "describe_screen"): "low",
    ("vision", "explain_screen_code"): "low",

    # Terminal (futuro)
    ("terminal", "run"): "high",

    # Git
    ("git", "status"): "low",
    ("git", "diff"): "low",
    ("git", "log"): "low",
    ("git", "add"): "medium",
    ("git", "commit"): "medium",
    ("git", "push"): "high",
    ("git", "pull"): "medium",
        # Spotify (todo low)
    ("spotify", "play"): "low",
    ("spotify", "pause"): "low",
    ("spotify", "next"): "low",
    ("spotify", "previous"): "low",
    ("spotify", "current"): "low",
    ("spotify", "volume"): "low",

    # Correo (futuro)
    ("email", "send"): "high",
    ("email", "read"): "low",

    # GitHub (futuro)
    ("github", "commit"): "medium",
    ("github", "push"): "high",
    ("github", "list_issues"): "low",
}

def set_handler(fn):
    """
    main.py llama esto al arrancar para inyectar la función que sabe
    preguntar por voz. La función debe tener firma:

        fn(skill: str, action: str, summary: str, level: str) -> bool

    Y devolver True si el usuario confirmó, False si rechazó o si hubo timeout.
    """
    global _ask_handler
    with _handler_lock:
        _ask_handler = fn


def get_risk(skill, action):
    """Devuelve el nivel de riesgo ('low', 'medium', 'high') o 'medium' por defecto."""
    return RISK_LEVELS.get((skill, action), "medium")


def is_low_risk(skill, action):
    return get_risk(skill, action) == "low"


def require(skill, action, summary, params=None, timeout=DEFAULT_TIMEOUT):
    """
    Punto de entrada de las skills. Devuelve True si se autoriza ejecutar.

    - Riesgo "low": devuelve True sin preguntar.
    - Riesgo "medium"/"high": llama al handler y espera respuesta.
    - Si no hay handler inyectado: devuelve False (fail-safe) para acciones no-low.
    - Si el usuario no responde en `timeout` seg: devuelve False.
    """
    level = get_risk(skill, action)

    if level == "low":
        return True

    with _handler_lock:
        handler = _ask_handler

    if handler is None:
        print(f"[CONFIRM] Sin handler: rechazado por defecto ({skill}.{action})")
        return False

    try:
        confirmed = handler(skill, action, summary, level, timeout)
        return bool(confirmed)
    except Exception as e:
        print(f"[CONFIRM ERROR] {e}")
        return False