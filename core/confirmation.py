"""Capa de confirmacion central: skills de riesgo piden autorizacion."""
import threading
import time
from datetime import datetime

# Handler externo: main.py inyecta la funcion que sabe preguntar por voz
_ask_handler = None
_handler_lock = threading.Lock()

# Timeout por defecto para esperar respuesta
DEFAULT_TIMEOUT = 30


# Niveles de riesgo por (skill, action).
# "low"    = auto-aprueba, no pregunta
# "medium" = pregunta siempre
# "high"   = pregunta siempre + advertencia
RISK_LEVELS = {
    # System - tiempo/fecha
    ("system", "time"): "low",
    ("system", "date"): "low",

    # Desktop
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

    # System - acciones
    ("system", "screenshot"): "low",
    ("system", "lock"): "medium",
    ("system", "sleep"): "medium",
    ("system", "shutdown"): "high",
    ("system", "restart"): "high",
    ("system", "cancel_shutdown"): "low",
    ("system", "disk_info"): "low",
    ("system", "list_big_files"): "low",
    ("system", "list_startup"): "low",
    ("system", "clean_temp"): "medium",
    ("system", "empty_recycle"): "high",

    # Macro
    ("macro", "start"): "medium",
    ("macro", "stop"): "low",
    ("macro", "play"): "high",
    ("macro", "list"): "low",
    ("macro", "delete"): "high",
        # n8n
    ("n8n", "list_workflows"): "low",
    ("n8n", "get_workflow"): "low",
    ("n8n", "list_executions"): "low",
    ("n8n", "activate"): "medium",
    ("n8n", "deactivate"): "medium",
    ("n8n", "delete_workflow"): "high",
    ("n8n", "search_templates"): "low",
    ("n8n", "get_template"): "low",
    ("n8n", "import_template"): "medium",
    ("n8n", "create_workflow"): "medium",

    # Files
    ("files", "find_file"): "low",
    ("files", "list_folder"): "low",
    ("files", "pick"): "low",
    ("files", "open_path"): "low",
    ("files", "info"): "low",
    ("files", "move"): "medium",
    ("files", "delete"): "high",

    # Dev - lectura
    ("dev", "review_file"): "low",
    ("dev", "review_project"): "low",
    ("dev", "explain"): "low",
    ("dev", "find_issues"): "low",
    ("dev", "generate_code"): "low",
    ("dev", "review_to_excel"): "medium",
    ("dev", "review_to_word"): "medium",

    # Dev - escritura/ejecucion
    ("dev", "write_file"): "high",
    ("dev", "run_file"): "high",
    ("dev", "create_and_test"): "high",

    # Office
    ("office", "create_doc"): "medium",
    ("office", "read_doc"): "low",
    ("office", "create_xlsx"): "medium",
    ("office", "read_xlsx"): "low",
    ("office", "create_ppt"): "medium",
    ("office", "read_ppt"): "low",

    # Imagenes
    ("image", "generate"): "low",
    ("image", "list"): "low",
    ("image", "to_word"): "low",

    # PDF
    ("pdf", "from_docx"): "low",
    ("pdf", "list"): "low",

    # Telegram
    ("telegram", "send_last"): "low",
    ("telegram", "send_file"): "low",

    # Edit
    ("edit", "modify"): "medium",
    ("edit", "list_uploads"): "low",

    # Docs / RAG
    ("docs", "ask"): "low",
    ("docs", "list"): "low",
    ("docs", "index_file"): "low",
    ("docs", "index_folder"): "low",
    ("docs", "delete"): "medium",
    ("docs", "ask_to_word"): "medium",

    # Education
    ("education", "pseint"): "low",
    ("education", "convert"): "low",
    ("education", "diagram"): "low",

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

    # Productivity
    ("productivity", "save_note"): "low",
    ("productivity", "read_notes"): "low",
    ("productivity", "clear_notes"): "medium",

    # Weather
    ("weather", "current"): "low",

    # Translate
    ("translate", "text"): "low",

    # Alarm
    ("alarm", "set"): "low",
    ("alarm", "list"): "low",
    ("alarm", "cancel"): "low",

    # Entertainment
    ("entertainment", "play_pause"): "low",
    ("entertainment", "next_track"): "low",
    ("entertainment", "prev_track"): "low",

    # Terminal
    ("terminal", "run"): "high",
    ("terminal", "suggest"): "medium",

    # Git
    ("git", "status"): "low",
    ("git", "diff"): "low",
    ("git", "log"): "low",
    ("git", "add"): "medium",
    ("git", "commit"): "medium",
    ("git", "push"): "high",
    ("git", "pull"): "medium",

    # Spotify
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
    main.py llama esto al arrancar para inyectar la funcion que sabe
    preguntar por voz. La funcion debe tener firma:

        fn(skill: str, action: str, summary: str, level: str) -> bool

    Y devolver True si el usuario confirmo, False si rechazo o si hubo timeout.
    """
    global _ask_handler
    with _handler_lock:
        _ask_handler = fn


def get_risk(skill, action):
    """Devuelve el nivel de riesgo ('low', 'medium', 'high') o 'medium' por defecto."""
    return RISK_LEVELS.get((skill, action), "medium")


def is_low_risk(skill, action):
    return get_risk(skill, action) == "low"


def _default_text_handler(skill, action, summary, level, timeout):
    """Handler de texto por defecto para uso desde consola interactiva."""
    print(f"\n[CONFIRMACION {level.upper()}] {summary}")
    try:
        resp = input("Confirmas? (s/n): ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        return False
    return resp in ("s", "si", "sí", "y", "yes")


def _install_default_if_tty():
    """Si estamos en una terminal interactiva y no hay handler, instalar uno de texto."""
    global _ask_handler
    if _ask_handler is not None:
        return
    try:
        import sys
        if sys.stdin and sys.stdin.isatty():
            _ask_handler = _default_text_handler
    except Exception:
        pass


# Auto-instalar el handler de texto si aplica
_install_default_if_tty()


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