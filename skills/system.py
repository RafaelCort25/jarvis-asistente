import os
import subprocess
import ctypes
from datetime import datetime
from pathlib import Path
from skills.base import Skill

SCREENSHOTS_DIR = Path.home() / "Pictures" / "JarvisScreenshots"


class SystemSkill(Skill):
    name = "system"
    description = "Apaga, bloquea, captura pantalla, suspende"

    def run(self, action, params):
        if action == "lock":
            return self._lock()
        if action == "shutdown":
            return self._shutdown()
        if action == "restart":
            return self._restart()
        if action == "sleep":
            return self._sleep()
        if action == "screenshot":
            return self._screenshot()
        if action == "cancel_shutdown":
            return self._cancel_shutdown()
        return f"Accion desconocida: {action}"

    def _lock(self):
        try:
            ctypes.windll.user32.LockWorkStation()
            return "Bloqueando pantalla."
        except Exception as e:
            return f"Error al bloquear: {e}"

    def _shutdown(self):
        try:
            # 30 seg para cancelar
            subprocess.Popen("shutdown /s /t 30", shell=True)
            return "Apagando el PC en 30 segundos. Di 'cancela el apagado' si te arrepientes."
        except Exception as e:
            return f"Error al apagar: {e}"

    def _restart(self):
        try:
            subprocess.Popen("shutdown /r /t 30", shell=True)
            return "Reiniciando en 30 segundos."
        except Exception as e:
            return f"Error al reiniciar: {e}"

    def _cancel_shutdown(self):
        try:
            subprocess.Popen("shutdown /a", shell=True)
            return "Apagado cancelado."
        except Exception as e:
            return f"Error: {e}"

    def _sleep(self):
        try:
            # Suspender (sleep) - requiere privilegios
            subprocess.Popen(
                "rundll32.exe powrprof.dll,SetSuspendState 0,1,0",
                shell=True,
            )
            return "Suspendiendo."
        except Exception as e:
            return f"Error: {e}"

    def _screenshot(self):
        try:
            SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)
            filename = SCREENSHOTS_DIR / f"captura_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
            import mss
            import mss.tools
            with mss.mss() as sct:
                monitor = sct.monitors[0]  # todas las pantallas
                img = sct.grab(monitor)
                mss.tools.to_png(img.rgb, img.size, output=str(filename))
            return f"Captura guardada: {filename.name}"
        except Exception as e:
            return f"Error al capturar: {e}"