import threading
import time
import winsound
from datetime import datetime, timedelta
from skills.base import Skill


class AlarmSkill(Skill):
    name = "alarm"
    description = "Alarmas y recordatorios con hora"

    def __init__(self):
        self.alarms = []  # cada alarma: {"text", "end_time", "minutes", "stop_event"}

    def run(self, action, params):
        if action == "set":
            return self._set(params.get("minutes", 0), params.get("text", ""))
        if action == "list":
            return self._list()
        if action == "cancel":
            return self._cancel_all()
        return f"Accion desconocida: {action}"

    def _set(self, minutes, text):
        try:
            minutes = float(minutes)
        except (ValueError, TypeError):
            return "Duracion invalida."
        if minutes <= 0:
            return "La duracion debe ser positiva."
        if not text:
            text = "Alarma"

        end_time = datetime.now() + timedelta(minutes=minutes)
        stop_event = threading.Event()
        alarm_info = {
            "text": text,
            "end_time": end_time,
            "minutes": minutes,
            "stop_event": stop_event,
        }

        def _run():
            # Espera la duracion o hasta que se cancele
            cancelled = stop_event.wait(timeout=minutes * 60)
            if cancelled:
                return
            # Sonar alarma
            print(f"\n⏰ ALARMA: {text}")
            # Notificar a Telegram
            try:
                from integrations.notifier import send_async
                send_async(f"⏰ *ALARMA:* {text}\n{datetime.now().strftime('%H:%M:%S')}")
            except Exception as e:
                print(f"[ALARM TELEGRAM] {e}")
            for _ in range(10):
                if stop_event.is_set():
                    break
                try:
                    winsound.Beep(1000, 400)
                    time.sleep(0.15)
                    winsound.Beep(1500, 200)
                    time.sleep(0.15)
                except Exception:
                    pass
            self.alarms = [a for a in self.alarms if a is not alarm_info]

        thread = threading.Thread(target=_run, daemon=True)
        thread.start()
        self.alarms.append(alarm_info)

        return {
            "thought": f"Programar alarma en {minutes} min",
            "display": f"⏰ Alarma: {text} en {minutes} min (a las {end_time.strftime('%H:%M:%S')})",
            "voice": f"Listo, alarma en {int(minutes)} minutos.",
        }

    def _list(self):
        if not self.alarms:
            return "No hay alarmas activas."
        lines = ["⏰ Alarmas activas:"]
        for a in self.alarms:
            remaining = (a["end_time"] - datetime.now()).total_seconds() / 60
            if remaining > 0:
                lines.append(f"  - {a['text']} (quedan {remaining:.1f} min)")
        return "\n".join(lines)

    def _cancel_all(self):
        count = len(self.alarms)
        # Activar el stop_event de cada alarma
        for a in self.alarms:
            a["stop_event"].set()
        self.alarms = []
        return f"Canceladas {count} alarmas."