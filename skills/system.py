import os
import shutil
import subprocess
import ctypes
import time
import winreg
from datetime import datetime, timedelta
from pathlib import Path

import psutil

from skills.base import Skill
from core import confirmation

SCREENSHOTS_DIR = Path.home() / "Pictures" / "JarvisScreenshots"


class SystemSkill(Skill):
    name = "system"
    description = "Apaga, bloquea, captura, limpia sistema, muestra info de discos"

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
        if action == "disk_info":
            return self._disk_info()
        if action == "clean_temp":
            return self._clean_temp()
        if action == "empty_recycle":
            return self._empty_recycle()
        if action == "list_big_files":
            return self._list_big_files(params.get("folder", ""), params.get("min_mb", 100))
        if action == "list_startup":
            return self._list_startup()
        return f"Accion desconocida: {action}"

    # ─── SISTEMA BASICO ──────────────────────────────────────────────────

    def _lock(self):
        try:
            ctypes.windll.user32.LockWorkStation()
            return "Bloqueando pantalla."
        except Exception as e:
            return f"Error al bloquear: {e}"

    def _shutdown(self):
        try:
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

            try:
                from integrations.notifier import send_async
                send_async(
                    f"Captura de pantalla\n{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
                    image_path=str(filename),
                )
            except Exception as e:
                print(f"[SCREENSHOT TELEGRAM] {e}")

            return {
                "thought": "Captura enviada por Telegram",
                "display": f"Captura guardada: {filename.name}\nEnviada por Telegram",
                "voice": "Listo, capture y envie la pantalla.",
            }

        except Exception as e:
            return f"Error al capturar: {e}"

    def _time(self):
        ahora = datetime.now()
        hora12 = ahora.strftime("%I:%M %p").lstrip("0")
        return {"thought": "", "display": f"Son las {hora12}", "voice": f"Son las {hora12}"}

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
        return {"thought": "", "display": texto, "voice": texto}

    # ─── INFO DE DISCOS ──────────────────────────────────────────────────

    def _disk_info(self):
        try:
            particiones = psutil.disk_partitions()
            lineas = []
            for p in particiones:
                try:
                    uso = psutil.disk_usage(p.mountpoint)
                    total_gb = uso.total / 1e9
                    libre_gb = uso.free / 1e9
                    usado_gb = uso.used / 1e9
                    pct = uso.percent
                    lineas.append(
                        f"{p.device} - {total_gb:.0f} GB total, "
                        f"{libre_gb:.0f} GB libres ({pct}% usado)"
                    )
                except PermissionError:
                    continue

            if not lineas:
                return "No pude leer informacion de discos."

            return {
                "thought": "",
                "display": "Info de discos:\n" + "\n".join(lineas),
                "voice": f"Tienes {len(lineas)} discos montados.",
            }
        except Exception as e:
            return f"Error consultando discos: {e}"

    # ─── LIMPIAR TEMPORALES ──────────────────────────────────────────────

    def _clean_temp(self):
        # Calcular tamano antes
        temp_dirs = [
            Path(os.environ.get("TEMP", "")),
            Path(os.environ.get("TMP", "")),
            Path(os.environ.get("LOCALAPPDATA", "")) / "Temp",
        ]
        # Quitar duplicados y directorios vacios
        temp_dirs = list({d for d in temp_dirs if d and str(d).strip() and d.exists()})

        if not temp_dirs:
            return "No encontre carpetas de temporales."

        # Calcular tamano
        total_size = 0
        total_files = 0
        for d in temp_dirs:
            try:
                for f in d.rglob("*"):
                    if f.is_file():
                        try:
                            total_size += f.stat().st_size
                            total_files += 1
                        except (OSError, PermissionError):
                            pass
            except (OSError, PermissionError):
                pass

        size_mb = total_size / 1e6
        summary = f"Limpiar temporales: {total_files} archivos, {size_mb:.1f} MB"
        if not confirmation.require("system", "clean_temp", summary):
            return "Cancelado."

        # Borrar
        borrados = 0
        fallidos = 0
        for d in temp_dirs:
            for f in d.glob("*"):
                try:
                    if f.is_file():
                        f.unlink()
                        borrados += 1
                    elif f.is_dir():
                        shutil.rmtree(f, ignore_errors=True)
                        borrados += 1
                except (OSError, PermissionError):
                    fallidos += 1

        return {
            "thought": f"Limpieza completada: {borrados} borrados, {fallidos} fallidos",
            "display": (
                f"Limpieza de temporales:\n"
                f"  Borrados: {borrados} archivos\n"
                f"  Fallidos (en uso): {fallidos}\n"
                f"  Espacio liberado (aprox): {size_mb:.1f} MB"
            ),
            "voice": f"Listo. Libere aproximadamente {size_mb:.0f} megas.",
        }

    # ─── VACIAR PAPELERA ─────────────────────────────────────────────────

    def _empty_recycle(self):
        try:
            # Calcular tamano de la papelera (aproximado por $Recycle.Bin en cada disco)
            total_size = 0
            for p in psutil.disk_partitions():
                recycle = Path(p.mountpoint) / "$Recycle.Bin"
                if recycle.exists():
                    try:
                        for f in recycle.rglob("*"):
                            if f.is_file():
                                try:
                                    total_size += f.stat().st_size
                                except (OSError, PermissionError):
                                    pass
                    except (OSError, PermissionError):
                        pass

            size_mb = total_size / 1e6

            summary = f"Vaciar papelera de reciclaje (~{size_mb:.1f} MB)"
            if not confirmation.require("system", "empty_recycle", summary):
                return "Cancelado."

            # SHEmptyRecycleBinW
            # Flags: SHERB_NOCONFIRMATION | SHERB_NOPROGRESSUI | SHERB_NOSOUND
            result = ctypes.windll.shell32.SHEmptyRecycleBinW(
                None, None, 0x00000007
            )
            if result == 0:
                return {
                    "thought": "Papelera vaciada",
                    "display": f"Papelera vaciada. Espacio liberado: ~{size_mb:.1f} MB",
                    "voice": f"Listo. Vaqie la papelera, libere {size_mb:.0f} megas.",
                }
            return f"No pude vaciar la papelera (codigo: {result})"
        except Exception as e:
            return f"Error vaciando papelera: {e}"

    # ─── LISTAR ARCHIVOS GRANDES ─────────────────────────────────────────

    def _list_big_files(self, folder, min_mb):
                # Mapeo de nombres en espanol -> nombres reales de Windows
        name_map = {
            "descargas": "Downloads",
            "downloads": "Downloads",
            "documentos": "Documents",
            "documents": "Documents",
            "escritorio": "Desktop",
            "desktop": "Desktop",
            "imagenes": "Pictures",
            "imágenes": "Pictures",
            "pictures": "Pictures",
            "videos": "Videos",
            "vídeos": "Videos",
            "musica": "Music",
            "música": "Music",
            "music": "Music",
        }

        if not folder:
            folder = Path.home() / "Downloads"
        else:
            folder_lower = folder.lower().strip()
            folder_real = name_map.get(folder_lower, folder)
            folder = Path(folder_real)
            if not folder.is_absolute():
                folder = Path.home() / folder

        if not folder.exists():
            return f"No encontre la carpeta: {folder}"

        try:
            min_mb = int(min_mb)
        except (ValueError, TypeError):
            min_mb = 100

        min_bytes = min_mb * 1024 * 1024

        big_files = []
        try:
            for f in folder.rglob("*"):
                if f.is_file():
                    try:
                        size = f.stat().st_size
                        if size >= min_bytes:
                            big_files.append((f, size))
                    except (OSError, PermissionError):
                        pass
        except (OSError, PermissionError):
            return f"No pude leer {folder}"

        if not big_files:
            return f"No hay archivos mayores a {min_mb} MB en {folder.name}"

        big_files.sort(key=lambda x: x[1], reverse=True)
        top = big_files[:20]

        lines = [f"Archivos > {min_mb} MB en {folder.name} (top {len(top)}):"]
        for f, size in top:
            size_mb = size / 1e6
            lines.append(f"  {size_mb:>7.1f} MB - {f.name}")

        total_gb = sum(s for _, s in big_files) / 1e9

        return {
            "thought": f"{len(big_files)} archivos grandes encontrados",
            "display": "\n".join(lines) + f"\n\nTotal: {total_gb:.2f} GB",
            "voice": f"Encontre {len(big_files)} archivos grandes.",
        }

    # ─── LISTAR PROGRAMAS DE INICIO ──────────────────────────────────────

    def _list_startup(self):
        try:
            programas = []

            # HKCU y HKLM: ...\CurrentVersion\Run
            keys = [
                (winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run", "Usuario"),
                (winreg.HKEY_LOCAL_MACHINE, r"Software\Microsoft\Windows\CurrentVersion\Run", "Sistema"),
            ]

            for hive, path, origen in keys:
                try:
                    with winreg.OpenKey(hive, path) as key:
                        i = 0
                        while True:
                            try:
                                nombre, valor, _ = winreg.EnumValue(key, i)
                                programas.append((origen, nombre, valor))
                                i += 1
                            except OSError:
                                break
                except FileNotFoundError:
                    pass

            if not programas:
                return "No encontre programas de inicio."

            lines = [f"Programas de inicio ({len(programas)}):"]
            for origen, nombre, valor in programas:
                lines.append(f"  [{origen}] {nombre}")

            return {
                "thought": "",
                "display": "\n".join(lines),
                "voice": f"Tienes {len(programas)} programas de inicio.",
            }
        except Exception as e:
            return f"Error consultando startup: {e}"