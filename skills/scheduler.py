from skills.base import Skill
from scheduler.scheduler import get_scheduler


class SchedulerSkill(Skill):
    name = "scheduler"
    description = "Programa recordatorios y tareas recurrentes"

    def __init__(self):
        self.scheduler = get_scheduler()

    def run(self, action, params):
        if action == "add_once":
            secs = int(params.get("seconds", 60))
            msg = params.get("message", "Recordatorio")
            command = params.get("command") or None
            self.scheduler.add_once(secs, msg, command=command)
            mins = secs // 60
            cuando = f"en {mins} min" if mins >= 1 else f"en {secs}s"
            return f"Recordatorio programado {cuando}: {msg}"

        if action == "add_daily":
            time_str = params.get("time", "08:00")
            msg = params.get("message", "")
            command = params.get("command") or None
            self.scheduler.add_daily(time_str, msg, command=command)
            return f"Tarea diaria programada a las {time_str}: {msg}"

        if action == "add_interval":
            mins = int(params.get("every_minutes", 60))
            msg = params.get("message", "")
            command = params.get("command") or None
            self.scheduler.add_interval(mins, msg, command=command)
            return f"Tarea programada cada {mins} minutos: {msg}"

        if action == "list":
            return self.scheduler.list_tasks()

        if action == "cancel":
            return self.scheduler.cancel(params.get("identifier", ""))

        return f"Accion desconocida en scheduler: {action}"