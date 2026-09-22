"""Motor de tareas programadas para Nitro."""
import json
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path

from core.config_loader import CONFIG

ROOT = Path(__file__).resolve().parent.parent
TASKS_FILE = ROOT / "scheduler" / "tasks.json"
TICK_INTERVAL = 20  # segundos entre revisiones

_scheduler_instance = None


class Scheduler:
    def __init__(self):
        self.tasks = self._load()
        self._stop = threading.Event()
        self._thread = None
        self._lock = threading.Lock()
        self._router = None
        self._last_tick = 0

    # ── Persistencia ───────────────────────────────────────────
    def _load(self):
        if not TASKS_FILE.exists():
            return []
        try:
            return json.loads(TASKS_FILE.read_text(encoding="utf-8"))
        except Exception:
            return []

    def _save(self):
        try:
            TASKS_FILE.parent.mkdir(parents=True, exist_ok=True)
            TASKS_FILE.write_text(
                json.dumps(self.tasks, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except Exception as e:
            print(f"[SCHEDULER] Error guardando: {e}")

    # ── API pública ────────────────────────────────────────────
    def set_router(self, router):
        self._router = router

    def add_once(self, delay_seconds, message, command=None, notify=None):
        when = datetime.now() + timedelta(seconds=delay_seconds)
        task = self._make_task("once", message, command, notify, {"at": when.isoformat()})
        with self._lock:
            self.tasks.append(task)
        self._save()
        return task["id"]

    def add_daily(self, time_str, message, command=None, notify=None):
        # time_str formato "HH:MM"
        task = self._make_task("daily", message, command, notify, {"time": time_str})
        with self._lock:
            self.tasks.append(task)
        self._save()
        return task["id"]

    def add_interval(self, every_minutes, message, command=None, notify=None):
        task = self._make_task("interval", message, command, notify,
                               {"every_minutes": int(every_minutes)})
        task["last_run"] = None
        with self._lock:
            self.tasks.append(task)
        self._save()
        return task["id"]

    def list_tasks(self):
        if not self.tasks:
            return "No hay tareas programadas."
        lines = []
        for i, t in enumerate(self.tasks, 1):
            state = "ON " if t.get("enabled", True) else "OFF"
            tipo = t["type"]
            when = t.get("when", {})
            if tipo == "once":
                detalle = f"en {when.get('at', '?')}"
            elif tipo == "daily":
                detalle = f"todos los dias a las {when.get('time', '?')}"
            else:
                detalle = f"cada {when.get('every_minutes', '?')} min"
            msg = t.get("message", "")[:50]
            lines.append(f"{i}. [{state}] {tipo} {detalle} - {msg}")
        return "\n".join(lines)

    def cancel(self, identifier):
        with self._lock:
            target = None
            # Por id exacto
            for t in self.tasks:
                if t["id"] == identifier:
                    target = t
                    break
            # Por índice (numero)
            if target is None:
                try:
                    idx = int(identifier) - 1
                    if 0 <= idx < len(self.tasks):
                        target = self.tasks[idx]
                except (ValueError, TypeError):
                    pass
            if target is None:
                return f"No encontre tarea: {identifier}"
            self.tasks.remove(target)
        self._save()
        return f"Tarea eliminada: {target.get('message', target['id'])[:60]}"

    def _make_task(self, tipo, message, command, notify, when):
        return {
            "id": f"task_{int(time.time() * 1000)}_{len(self.tasks)}",
            "type": tipo,
            "created": datetime.now().isoformat(),
            "last_run": None,
            "enabled": True,
            "message": message or "",
            "command": command,
            "when": when,
            "notify": notify or ["telegram", "log"],
        }

    # ── Lógica de ejecución ────────────────────────────────────
    def _should_run(self, task, now):
        if not task.get("enabled", True):
            return False
        tipo = task["type"]
        when = task.get("when", {})
        last = task.get("last_run")

        if tipo == "once":
            try:
                at = datetime.fromisoformat(when["at"])
            except Exception:
                return False
            return now >= at and last is None

        if tipo == "daily":
            try:
                hh, mm = when["time"].split(":")
                objetivo = now.replace(hour=int(hh), minute=int(mm), second=0, microsecond=0)
            except Exception:
                return False
            # Ventana de 60 seg para evitar perder la ejecución si el tick cae justo antes/después
            delta = (now - objetivo).total_seconds()
            if delta < 0 or delta > 60:
                return False
            if last:
                try:
                    if datetime.fromisoformat(last).date() == now.date():
                        return False
                except Exception:
                    pass
            return True

        if tipo == "interval":
            every = int(when.get("every_minutes", 60))
            if not last:
                return True
            try:
                last_dt = datetime.fromisoformat(last)
            except Exception:
                return True
            return (now - last_dt).total_seconds() >= every * 60

        return False

    def _execute(self, task):
        message = task.get("message", "")
        command = task.get("command")

        text = message
        if command and self._router is not None:
            try:
                result, _ = self._router.route(command)
                if result:
                    text = result.get("voice") or result.get("display") or message
            except Exception as e:
                text = f"{message} (error ejecutando: {e})"

        notify = task.get("notify", [])
        if "telegram" in notify:
            try:
                from integrations import notifier
                notifier.send(f"[{CONFIG['jarvis']['name']}] {text}")
            except Exception as e:
                print(f"[SCHEDULER] Error telegram: {e}")

        if "log" in notify:
            print(f"[SCHEDULER] >> {task['id']}: {text}")

    # ── Thread ─────────────────────────────────────────────────
    def _loop(self):
        print("[SCHEDULER] Motor iniciado.")
        while not self._stop.is_set():
            try:
                now = datetime.now()
                changed = False
                for task in list(self.tasks):
                    if self._should_run(task, now):
                        try:
                            self._execute(task)
                        except Exception as e:
                            print(f"[SCHEDULER ERROR] {task['id']}: {e}")
                        task["last_run"] = now.isoformat()
                        if task["type"] == "once":
                            task["enabled"] = False
                        changed = True
                if changed:
                    self._save()
            except Exception as e:
                print(f"[SCHEDULER LOOP ERROR] {e}")
            self._stop.wait(TICK_INTERVAL)

    def start(self):
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=3)


def get_scheduler():
    """Singleton para que main.py y las skills compartan instancia."""
    global _scheduler_instance
    if _scheduler_instance is None:
        _scheduler_instance = Scheduler()
    return _scheduler_instance