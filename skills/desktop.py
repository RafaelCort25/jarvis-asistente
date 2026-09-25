import os
import subprocess
import pyautogui
from pathlib import Path
from skills.base import Skill

HOME = Path.home()

from core.paths import BRAVE_CMD, CHROME_CMD

APPS = {
    "brave": BRAVE_CMD,
    "chrome": CHROME_CMD,
    "notepad": "notepad.exe",
    "calculadora": "calc.exe",
    "explorador": "explorer.exe",
    "cmd": "cmd.exe",
    "paint": "mspaint.exe",
    "spotify": "spotify.exe",
}

FOLDERS = {
    "descargas": HOME / "Downloads",
    "documentos": HOME / "Documents",
    "escritorio": HOME / "Desktop",
    "imagenes": HOME / "Pictures",
    "musica": HOME / "Music",
    "videos": HOME / "Videos",
}


class DesktopSkill(Skill):
    name = "desktop"
    description = "Abre apps, controla volumen, abre carpetas"

    def run(self, action, params):
        if action == "open_app":
            return self._open_app(params.get("app", ""))
        if action == "open_folder":
            return self._open_folder(params.get("folder", ""))
        if action == "volume_up":
            return self._volume("up")
        if action == "volume_down":
            return self._volume("down")
        if action == "mute":
            pyautogui.press("volumemute")
            return "Silenciado."
        return f"Accion desconocida: {action}"

    def _open_app(self, app):
        app = app.lower().strip()
        if app in APPS:
            try:
                subprocess.Popen(APPS[app], shell=True)
                return f"Abriendo {app}."
            except Exception as e:
                return f"Error al abrir {app}: {e}"
        return f"No conozco la app '{app}'."

    def _open_folder(self, folder):
        folder = folder.lower().strip()
        if folder in FOLDERS:
            try:
                os.startfile(FOLDERS[folder])
                return f"Abriendo carpeta {folder}."
            except Exception as e:
                return f"Error: {e}"
        return f"No conozco la carpeta '{folder}'."

    def _volume(self, direction):
        key = "volumeup" if direction == "up" else "volumedown"
        for _ in range(5):
            pyautogui.press(key)
        return "Volumen subido." if direction == "up" else "Volumen bajado."