"""Skill de macro recorder: graba y reproduce secuencias de teclado/raton."""
import ctypes
import json
import re
import threading
import time
from ctypes import wintypes
from datetime import datetime
from pathlib import Path

from pynput import keyboard, mouse

from skills.base import Skill
from core import confirmation

ROOT = Path(__file__).resolve().parent.parent
MACROS_DIR = ROOT / "sandbox" / "macros"
MACROS_DIR.mkdir(parents=True, exist_ok=True)

# Limites de seguridad
# Limites de seguridad
MAX_DURATION = 300        # 5 minutos max de grabacion
MAX_EVENTS = 5000         # max eventos por macro
MOVE_FILTER_MS = 50       # solo grabar mouse_move cada 50ms
PLAYBACK_ABORT_KEY = keyboard.Key.esc

# Blindaje: delay antes de reproducir (segundos)
PLAYBACK_DELAY_SEC = 5

# Blindaje: procesos en los que NO se reproduce por seguridad
PROCESS_BLACKLIST = {
    # Navegadores (evita el incidente con DeepSeek)
    "chrome.exe", "firefox.exe", "msedge.exe", "brave.exe",
    "opera.exe", "vivaldi.exe", "chromium.exe",
    # Mensajeria
    "whatsapp.exe", "telegram.exe", "discord.exe", "slack.exe",
    "signal.exe", "messenger.exe",
    # Correo
    "outlook.exe", "thunderbird.exe",
    # Bancos / pagos (por si acaso)
    "banking.exe",
    # PowerShell / Terminal (evita que escriba comandos)
    "powershell.exe", "pwsh.exe", "cmd.exe", "windowsterminal.exe",
}

def _slugify(text, maxlen=40):
    s = text.lower()
    for k, v in {"á":"a","é":"e","í":"i","ó":"o","ú":"u","ñ":"n","ü":"u"}.items():
        s = s.replace(k, v)
    s = re.sub(r'[^a-z0-9]+', '_', s)[:maxlen].strip("_")
    return s or "macro"


def _key_to_str(key):
    """Convierte una tecla de pynput a un string reproducible."""
    try:
        if isinstance(key, keyboard.Key):
            return f"__key__{key.name}"
        if hasattr(key, "char") and key.char:
            return key.char
        return None
    except Exception:
        return None


def _str_to_key(s):
    """Convierte un string a una tecla de pynput."""
    if s.startswith("__key__"):
        name = s[len("__key__"):]
        return getattr(keyboard.Key, name, None)
    if len(s) == 1:
        return s
    return None
def _get_active_window_info():
    """Devuelve dict con info de la ventana activa (title, pid, exe)."""
    try:
        hwnd = ctypes.windll.user32.GetForegroundWindow()
        if not hwnd:
            return None

        length = ctypes.windll.user32.GetWindowTextLengthW(hwnd)
        buff = ctypes.create_unicode_buffer(length + 1)
        ctypes.windll.user32.GetWindowTextW(hwnd, buff, length + 1)
        title = buff.value

        pid = wintypes.DWORD()
        ctypes.windll.user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        pid_val = pid.value

        exe = ""
        try:
            import psutil
            exe = psutil.Process(pid_val).name().lower()
        except Exception:
            pass

        return {
            "title": title,
            "pid": pid_val,
            "exe": exe,
        }
    except Exception:
        return None


def _is_blacklisted(exe_name):
    """True si el ejecutable esta en la lista negra."""
    if not exe_name:
        return False
    return exe_name.lower() in PROCESS_BLACKLIST


class MacroSkill(Skill):
    name = "macro"
    description = "Graba y reproduce secuencias de teclado y raton"

    def __init__(self):
        self._recording = False
        self._record_events = []
        self._record_start = 0.0
        self._record_name = ""
        self._last_move_t = 0.0
        self._kb_listener = None
        self._mouse_listener = None
        self._record_lock = threading.Lock()
        self._playback_abort = False
        self._record_window = None
        self._last_save_result = None

    # ─── DISPATCHER ──────────────────────────────────────────────────────

    def run(self, action, params):
        if action == "start":
            return self._start(params.get("name", ""))
        if action == "stop":
            return self._stop()
        if action == "play":
            return self._play(params.get("name", ""))
        if action == "list":
            return self._list()
        if action == "delete":
            return self._delete(params.get("name", ""))
        return f"Accion desconocida en macro: {action}"

    # ─── START RECORDING ─────────────────────────────────────────────────

    def _start(self, name):
        if self._recording:
            return {
                "thought": "",
                "display": "Ya estoy grabando. Di 'para de grabar' o pulsa ESC.",
                "voice": "Ya estoy grabando.",
            }

        name = (name or "").strip()
        if not name:
            return {
                "thought": "",
                "display": "Dime como quieres llamar al macro.",
                "voice": "Dime como llamarlo.",
            }

        slug = _slugify(name)
        summary = f"Empezar a grabar macro '{slug}' (pulsa ESC para parar)"
        if not confirmation.require("macro", "start", summary):
            return {
                "thought": "Cancelado por el usuario",
                "display": "Cancelado.",
                "voice": "Cancelado.",
            }

                # Capturar ventana activa antes de empezar a grabar
        active_window = _get_active_window_info()

        with self._record_lock:
            self._recording = True
            self._record_events = []
            self._record_start = time.time()
            self._record_name = slug
            self._last_move_t = 0.0
            self._record_window = active_window

        print(f"[MACRO] Grabando '{slug}'. Pulsa ESC para parar.")

        # Listener de teclado
        def on_press(key):
            if key == keyboard.Key.esc:
                self._recording = False
                return False  # detiene el listener
            if not self._recording:
                return False
            t = time.time() - self._record_start
            if t > MAX_DURATION:
                self._recording = False
                return False
            k = _key_to_str(key)
            if k:
                with self._record_lock:
                    if len(self._record_events) < MAX_EVENTS:
                        self._record_events.append({"t": round(t, 3), "type": "key_press", "key": k})

        def on_release(key):
            if not self._recording:
                return False
            t = time.time() - self._record_start
            k = _key_to_str(key)
            if k:
                with self._record_lock:
                    if len(self._record_events) < MAX_EVENTS:
                        self._record_events.append({"t": round(t, 3), "type": "key_release", "key": k})

        # Listener de raton
        def on_move(x, y):
            if not self._recording:
                return False
            t = time.time() - self._record_start
            if (t - self._last_move_t) * 1000 < MOVE_FILTER_MS:
                return
            self._last_move_t = t
            with self._record_lock:
                if len(self._record_events) < MAX_EVENTS:
                    self._record_events.append({"t": round(t, 3), "type": "mouse_move", "x": x, "y": y})

        def on_click(x, y, button, pressed):
            if not self._recording:
                return False
            t = time.time() - self._record_start
            btn = "left" if button == mouse.Button.left else "right" if button == mouse.Button.right else "middle"
            with self._record_lock:
                if len(self._record_events) < MAX_EVENTS:
                    self._record_events.append({
                        "t": round(t, 3),
                        "type": "mouse_click" if pressed else "mouse_release",
                        "x": x, "y": y, "button": btn,
                    })

        def on_scroll(x, y, dx, dy):
            if not self._recording:
                return False
            t = time.time() - self._record_start
            with self._record_lock:
                if len(self._record_events) < MAX_EVENTS:
                    self._record_events.append({"t": round(t, 3), "type": "mouse_scroll", "dx": dx, "dy": dy})

        self._kb_listener = keyboard.Listener(on_press=on_press, on_release=on_release)
        self._mouse_listener = mouse.Listener(on_move=on_move, on_click=on_click, on_scroll=on_scroll)
        self._kb_listener.start()
        self._mouse_listener.start()

        # Guardar en background cuando pare
        def _watcher():
            self._kb_listener.join()
            try:
                self._mouse_listener.stop()
            except Exception:
                pass
            self._save_recording()

        threading.Thread(target=_watcher, daemon=True).start()

        return {
            "thought": f"Grabando macro '{slug}'",
            "display": f"Grabando macro '{slug}'.\nPulsa ESC o di 'para de grabar' cuando termines.",
            "voice": "Grabando. Pulsa escape para parar.",
        }

    # ─── STOP RECORDING ──────────────────────────────────────────────────

    def _stop(self):
        if not self._recording:
            return {
                "thought": "",
                "display": "No estoy grabando.",
                "voice": "No estoy grabando.",
            }
        self._recording = False
        for listener in (self._kb_listener, self._mouse_listener):
            if listener:
                try:
                    listener.stop()
                except Exception:
                    pass
        time.sleep(0.6)
        # Si se guardo algo, devolver ese resultado
        if self._last_save_result:
            r = self._last_save_result
            self._last_save_result = None
            return r
        return {
            "thought": "",
            "display": "Detuve la grabacion.",
            "voice": "Detuve la grabacion.",
        }
    def _save_recording(self):
        with self._record_lock:
            events = list(self._record_events)
            name = self._record_name
            window_info = self._record_window
        self._recording = False

        if not events:
            print(f"[MACRO] Sin eventos. No se guarda '{name}'.")
            print(f"[MACRO] Causas comunes:")
            print(f"[MACRO]   - Se pulso ESC antes de tocar algo en la ventana objetivo")
            print(f"[MACRO]   - La ventana con foco no era la que se queria grabar")
            print(f"[MACRO]   - Solo se movio el raton, sin clicks ni teclas")
            return

        duration = events[-1]["t"]
        data = {
            "name": name,
            "created": datetime.now().isoformat(),
            "duration": duration,
            "events": events,
            "window": window_info,
        }

        path = MACROS_DIR / f"{name}.json"
        try:
            path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
            print(f"[MACRO] Guardado: {path} ({len(events)} eventos, {duration:.1f}s)")
            self._last_save_result = {
                "thought": f"Grabado '{name}'",
                "display": f"Macro '{name}' guardado ({len(events)} eventos, {duration:.1f}s)",
                "voice": "Macro guardado.",
            }
        except Exception as e:
            print(f"[MACRO] Error guardando: {e}")
            self._last_save_result = {
                "thought": "Error guardando macro",
                "display": f"Error guardando: {e}",
                "voice": "Error guardando.",
            }

    # ─── PLAY ────────────────────────────────────────────────────────────

    def _play(self, name):
        name = _slugify(name or "")
        path = MACROS_DIR / f"{name}.json"
        if not path.exists():
            return f"No encontre el macro '{name}'."

        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception as e:
            return f"Error leyendo el macro: {e}"

        events = data.get("events", [])
        if not events:
            return f"El macro '{name}' esta vacio."

        duration = data.get("duration", 0)
        saved_window = data.get("window") or {}
        saved_exe = saved_window.get("exe", "")
        saved_title = saved_window.get("title", "")

        # ═══ BLINDAJE 1: Lista negra de procesos ═══
        current = _get_active_window_info()
        current_exe = (current or {}).get("exe", "")

        if _is_blacklisted(current_exe):
            return {
                "thought": f"Bloqueado por lista negra ({current_exe})",
                "display": (
                    f"BLOQUEADO: el macro no se reproduce en '{current_exe}' "
                    f"(lista negra por seguridad). Cambia a otra ventana e intenta de nuevo."
                ),
                "voice": "Bloqueado por seguridad. Cambia de ventana.",
            }

        # ═══ BLINDAJE 2: Verificar ventana activa ═══
        if saved_exe and current_exe and saved_exe != current_exe:
            msg = (
                f"ADVERTENCIA: el macro se grabo en '{saved_exe}' "
                f"pero ahora estas en '{current_exe}'.\n"
                f"Los clics caeran en el sitio equivocado."
            )
            print(f"[MACRO] {msg}")
            summary = (
                f"Ejecutar macro '{name}' grabado en '{saved_exe}' "
                f"pero estas en '{current_exe}'. ¿Continuar de todas formas?"
            )
            if not confirmation.require("macro", "play_wrong_window", summary):
                return {
                    "thought": "Cancelado por ventana incorrecta",
                    "display": "Cancelado. Cambia a la ventana correcta e intenta otra vez.",
                    "voice": "Cancelado.",
                }

        # Confirmacion normal
        summary = (
            f"Ejecutar macro '{name}' "
            f"({len(events)} eventos, {duration:.1f}s)"
        )
        if not confirmation.require("macro", "play", summary):
            return {
                "thought": "Cancelado por el usuario",
                "display": "Cancelado.",
                "voice": "Cancelado.",
            }

        # ═══ BLINDAJE 3: Delay con opcion de abortar ═══
        print(f"[MACRO] Empezando en {PLAYBACK_DELAY_SEC} segundos. Pulsa ESC para abortar.")
        abort_early = False

        def on_press_early(key):
            nonlocal abort_early
            if key == keyboard.Key.esc:
                abort_early = True
                return False

        early_listener = keyboard.Listener(on_press=on_press_early)
        early_listener.start()

        t0 = time.time()
        while time.time() - t0 < PLAYBACK_DELAY_SEC:
            if abort_early:
                break
            time.sleep(0.05)

        try:
            early_listener.stop()
        except Exception:
            pass

        if abort_early:
            return {
                "thought": "Abortado antes de empezar",
                "display": "Cancelado por ESC antes de empezar.",
                "voice": "Cancelado.",
            }

        print(f"[MACRO] Reproduciendo '{name}' ({len(events)} eventos)...")
        print("[MACRO] Pulsa ESC para abortar.")

        # Abort listener: ESC durante reproduccion
        self._playback_abort = False
        def on_press(key):
            if key == keyboard.Key.esc:
                self._playback_abort = True
                return False

        abort_listener = keyboard.Listener(on_press=on_press)
        abort_listener.start()

        kb_ctrl = keyboard.Controller()
        mouse_ctrl = mouse.Controller()

        t0 = time.time()
        last_t = 0.0
        aborted = False

        try:
            for ev in events:
                if self._playback_abort:
                    aborted = True
                    break

                # Esperar hasta el momento exacto
                target = ev["t"]
                delay = target - last_t
                if delay > 0:
                    # Sleep en tramos para poder reaccionar al ESC
                    fin = time.time() + delay
                    while time.time() < fin:
                        if self._playback_abort:
                            aborted = True
                            break
                        time.sleep(0.02)
                    if aborted:
                        break
                last_t = target

                kind = ev["type"]
                try:
                    if kind == "mouse_move":
                        mouse_ctrl.position = (ev["x"], ev["y"])
                    elif kind == "mouse_click":
                        mouse_ctrl.position = (ev["x"], ev["y"])
                        btn = {
                            "left": mouse.Button.left,
                            "right": mouse.Button.right,
                            "middle": mouse.Button.middle,
                        }.get(ev.get("button", "left"), mouse.Button.left)
                        mouse_ctrl.press(btn)
                    elif kind == "mouse_release":
                        btn = {
                            "left": mouse.Button.left,
                            "right": mouse.Button.right,
                            "middle": mouse.Button.middle,
                        }.get(ev.get("button", "left"), mouse.Button.left)
                        mouse_ctrl.release(btn)
                    elif kind == "mouse_scroll":
                        mouse_ctrl.scroll(ev.get("dx", 0), ev.get("dy", 0))
                    elif kind == "key_press":
                        k = _str_to_key(ev["key"])
                        if k:
                            kb_ctrl.press(k)
                    elif kind == "key_release":
                        k = _str_to_key(ev["key"])
                        if k:
                            kb_ctrl.release(k)
                except Exception as e:
                    print(f"[MACRO] Error en evento: {e}")
                    continue
        finally:
            try:
                abort_listener.stop()
            except Exception:
                pass

        elapsed = time.time() - t0
        if aborted:
            print(f"[MACRO] Abortado por ESC tras {elapsed:.1f}s")
            return {
                "thought": "Macro abortado",
                "display": f"Macro '{name}' abortado por ESC tras {elapsed:.1f}s.",
                "voice": "Macro abortado.",
            }

        print(f"[MACRO] Completado en {elapsed:.1f}s")
        return {
            "thought": f"Macro '{name}' ejecutado",
            "display": f"Macro '{name}' completado ({len(events)} eventos, {elapsed:.1f}s).",
            "voice": f"Listo. Ejecute el macro {name}.",
        }

    # ─── LIST ────────────────────────────────────────────────────────────

    def _list(self):
        files = list(MACROS_DIR.glob("*.json"))
        if not files:
            return "No hay macros guardados."

        lines = [f"Macros guardados ({len(files)}):"]
        for f in sorted(files):
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                dur = data.get("duration", 0)
                n = len(data.get("events", []))
                lines.append(f"  {data.get('name', f.stem)}  -  {n} eventos, {dur:.1f}s")
            except Exception:
                lines.append(f"  {f.stem}  -  (dañado)")

        return {
            "thought": "",
            "display": "\n".join(lines),
            "voice": f"Tienes {len(files)} macros guardados.",
        }

    # ─── DELETE ──────────────────────────────────────────────────────────

    def _delete(self, name):
        name = _slugify(name or "")
        path = MACROS_DIR / f"{name}.json"
        if not path.exists():
            return f"No encontre el macro '{name}'."

        if not confirmation.require("macro", "delete", f"Borrar macro '{name}'"):
            return "Cancelado."

        try:
            path.unlink()
        except Exception as e:
            return f"Error borrando: {e}"

        return {
            "thought": f"Macro '{name}' borrado",
            "display": f"Macro '{name}' eliminado.",
            "voice": f"Borre el macro {name}.",
        }