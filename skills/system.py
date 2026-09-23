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
        if action == "time":
            return self._time()
        if action == "date":
            return self._date()
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
                monitor = sct.monitors[0]
                img = sct.grab(monitor)
                mss.tools.to_png(img.rgb, img.size, output=str(filename))

            # Enviar a Telegram (si hay chat_id guardado)
            try:
                from integrations.notifier import send_async
                send_async(
                    f"📸 Captura de pantalla\n{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
                    image_path=str(filename),
                )
            except Exception as e:
                print(f"[SCREENSHOT TELEGRAM] {e}")

            return {
                "thought": "Captura enviada por Telegram",
                "display": f"📸 Captura guardada: {filename.name}\n📤 Enviada por Telegram",
                "voice": "Listo, capture y envie la pantalla."
            }
        
        except Exception as e:
            return f"Error al capturar: {e}"

    def _time(self):
        ahora = datetime.now()
        hora12 = ahora.strftime("%I:%M %p").lstrip("0")
        return {
            "thought": "",
            "display": f"Son las {hora12}",
            "voice": f"Son las {hora12}",
        }

    def _date(self):
        ahora = datetime.now()
        dias = ["lunes", "martes", "miercoles", "jueves", "viernes", "sabado", "domingo"]
        meses = [
            "enero", "febrero", "marzo", "abril", "mayo", "junio",
            "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre",
        ]
        dia_semana = dias[ahora.weekday()]
        mes = meses[ahora.month - 1]
        texto = f"Hoy es {dia_semana} {ahora.day} de {mes} de {ahora.year}"
        return {
            "thought": "",
            "display": texto,
            "voice": texto,
        }