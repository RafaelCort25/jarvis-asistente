"""Vigilante proactivo: avisa por Telegram cuando hay problemas del sistema."""
import threading
import time
from datetime import datetime

import psutil

from core.config_loader import CONFIG

TICK_INTERVAL = 60        # revisar cada 60 segundos
COOLDOWN_MINUTES = 30     # no repetir la misma alerta antes de 30 min

# Umbrales
BATTERY_LOW = 20          # %
DISK_HIGH = 90            # %
RAM_HIGH = 90             # %
CPU_HIGH = 90             # %
CPU_SUSTAINED_TICKS = 3   # 3 ticks seguidos = 3 min

_watcher_instance = None


class Watcher:
    def __init__(self):
        self._stop = threading.Event()
        self._thread = None
        self._last_alert = {}          # {tipo: datetime}
        self._cpu_high_streak = 0

    # ── Cooldown ───────────────────────────────────────────────
    def _can_alert(self, key):
        last = self._last_alert.get(key)
        if last is None:
            return True
        delta_min = (datetime.now() - last).total_seconds() / 60
        return delta_min >= COOLDOWN_MINUTES

    def _mark_alert(self, key):
        self._last_alert[key] = datetime.now()

    # ── Notificación ───────────────────────────────────────────
    def _notify(self, key, message):
        if not self._can_alert(key):
            return
        self._mark_alert(key)
        print(f"[WATCHER] {message}")
        try:
            from integrations import notifier
            notifier.send(f"[{CONFIG['jarvis']['name']} - Sistema] {message}")
        except Exception as e:
            print(f"[WATCHER] Error telegram: {e}")

    # ── Chequeos ───────────────────────────────────────────────
    def _check_battery(self):
        try:
            bat = psutil.sensors_battery()
        except Exception:
            return
        if bat is None:
            return
        if bat.power_plugged:
            # Si está cargando y ya subió, reseteamos alerta
            if bat.percent > 30:
                self._last_alert.pop("battery", None)
            return
        if bat.percent < BATTERY_LOW:
            self._notify(
                "battery",
                f"Bateria baja: {bat.percent}%. Conecta el cargador.",
            )

    def _check_disk(self):
        try:
            disk = psutil.disk_usage("C:/")
        except Exception:
            return
        if disk.percent > DISK_HIGH:
            free_gb = (disk.total - disk.used) / 1e9
            self._notify(
                "disk",
                f"Disco C: al {disk.percent}%. Quedan {free_gb:.1f} GB libres.",
            )
        elif disk.percent < 85:
            self._last_alert.pop("disk", None)

    def _check_ram(self):
        try:
            ram = psutil.virtual_memory()
        except Exception:
            return
        if ram.percent > RAM_HIGH:
            used_gb = ram.used / 1e9
            total_gb = ram.total / 1e9
            self._notify(
                "ram",
                f"RAM al {ram.percent}% ({used_gb:.1f}/{total_gb:.1f} GB).",
            )
        elif ram.percent < 80:
            self._last_alert.pop("ram", None)

    def _check_cpu(self):
        try:
            cpu = psutil.cpu_percent(interval=None)
        except Exception:
            return
        if cpu > CPU_HIGH:
            self._cpu_high_streak += 1
            if self._cpu_high_streak >= CPU_SUSTAINED_TICKS:
                self._notify(
                    "cpu",
                    f"CPU sostenido al {cpu}% por {CPU_SUSTAINED_TICKS} min.",
                )
        else:
            self._cpu_high_streak = 0
            self._last_alert.pop("cpu", None)

    # ── Loop ───────────────────────────────────────────────────
    def _loop(self):
        print("[WATCHER] Vigilante iniciado.")
        # Primera lectura de CPU para inicializar
        psutil.cpu_percent(interval=None)
        while not self._stop.is_set():
            try:
                self._check_battery()
                self._check_disk()
                self._check_ram()
                self._check_cpu()
            except Exception as e:
                print(f"[WATCHER ERROR] {e}")
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


def get_watcher():
    global _watcher_instance
    if _watcher_instance is None:
        _watcher_instance = Watcher()
    return _watcher_instance