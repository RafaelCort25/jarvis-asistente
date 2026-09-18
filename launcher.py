"""
Launcher principal de Jarvis.
Arranca: API server + Telegram bot + ventana nativa (con bandeja).
"""
import os
import sys
import time
import atexit
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent
os.chdir(ROOT)

PYTHON = sys.executable
procesos = []


def arrancar_api_server():
    """Lanza FastAPI/uvicorn en subproceso."""
    print("[LAUNCHER] Arrancando API server (puerto 8000)...")
    proc = subprocess.Popen(
        [PYTHON, "-m", "uvicorn", "api_server:app",
         "--port", "8000", "--log-level", "warning"],
        cwd=str(ROOT),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
    )
    procesos.append(proc)
    return proc


def arrancar_telegram_bot():
    """Lanza el bot de Telegram en subproceso."""
    print("[LAUNCHER] Arrancando bot de Telegram...")
    proc = subprocess.Popen(
        [PYTHON, "-m", "integrations.telegram_bot"],
        cwd=str(ROOT),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
    )
    procesos.append(proc)
    return proc


def limpiar():
    """Mata todos los subprocesos al salir."""
    print("\n[LAUNCHER] Cerrando servicios...")
    for proc in procesos:
        try:
            if proc.poll() is None:  # Aun corriendo
                proc.terminate()
                proc.wait(timeout=3)
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass
    print("[LAUNCHER] Listo. Adios.")


# Registrar limpieza automatica al salir
atexit.register(limpiar)


def main():
    print("=" * 55)
    print("  JARVIS — Launcher principal")
    print("=" * 55)

    # 1. API server
    arrancar_api_server()
    time.sleep(2)  # Dar tiempo a que uvicorn arranque

    # 2. Telegram bot
    arrancar_telegram_bot()
    time.sleep(1)

    # 3. Ventana nativa (bloquea hasta que el usuario salga)
    print("[LAUNCHER] Abriendo interfaz...")
    try:
        from desktop.app import main as desktop_main
        desktop_main()
    except ImportError as e:
        print(f"[LAUNCHER ERROR] No se pudo importar desktop.app: {e}")
        print("[LAUNCHER] Corre primero: pip install pywebview pystray pillow")


if __name__ == "__main__":
    main()