"""
App de escritorio de Jarvis con bandeja del sistema (v2).
- Mantiene el tray vivo siempre
- Al cerrar la ventana → se oculta, no cierra
- Icono personalizado en taskbar
"""
import os
import sys
import time
import socket
import subprocess
import threading
from pathlib import Path

import webview
from PIL import Image
import pystray
import ctypes
from ctypes import wintypes


def set_taskbar_icon(icon_path):
    """Fuerza el icono en la barra de tareas de Windows."""
    try:
        import win32gui
        import win32con

        # Cargar el icono desde el archivo
        icon_flags = win32con.LR_LOADFROMFILE | win32con.LR_DEFAULTSIZE
        hicon = win32gui.LoadImage(
            0, str(icon_path), win32con.IMAGE_ICON,
            0, 0, icon_flags
        )

        # Encontrar la ventana de pywebview por su clase o título
        # La clase de la ventana de pywebview en Windows suele ser 'WebViewHost'
        hwnd = win32gui.FindWindow('WebViewHost', None)
        if hwnd == 0:
            # Intentar con el título si la clase no funciona
            hwnd = win32gui.FindWindow(None, 'Jarvis — Asistente')

        if hwnd:
            # Enviar el mensaje para establecer el icono (pequeño y grande)
            win32gui.SendMessage(hwnd, win32con.WM_SETICON, win32con.ICON_SMALL, hicon)
            win32gui.SendMessage(hwnd, win32con.WM_SETICON, win32con.ICON_BIG, hicon)
            print(f"[ICON] Icono de la barra de tareas establecido.")
            return True
        else:
            print("[ICON] No se encontro la ventana de pywebview.")
            return False
    except Exception as e:
        print(f"[ICON ERROR] {e}")
        return False


ROOT = Path(__file__).resolve().parent.parent
os.chdir(ROOT)

ICON_PATH = ROOT / "desktop" / "assets" / "jarvis.ico"
STREAMLIT_PORT = 8501


def is_port_open(port=STREAMLIT_PORT):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.5)
        return s.connect_ex(("127.0.0.1", port)) == 0


def start_streamlit():
    cmd = [
        sys.executable, "-m", "streamlit", "run", "gui.py",
        "--server.port", str(STREAMLIT_PORT),
        "--server.headless", "true",
        "--browser.gatherUsageStats", "false",
        "--global.developmentMode", "false",
    ]
    return subprocess.Popen(
        cmd,
        cwd=str(ROOT),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
    )


def wait_for_streamlit(timeout=60):
    start = time.time()
    while time.time() - start < timeout:
        if is_port_open(STREAMLIT_PORT):
            return True
        time.sleep(0.5)
    return False


class JarvisApp:
    def __init__(self):
        self.window = None
        self.streamlit_proc = None
        self.tray_icon = None

    def on_show(self, icon=None, item=None):
        """Muestra la ventana."""
        if self.window:
            try:
                self.window.show()
                self.window.restore()
            except Exception as e:
                print(f"[APP] Error mostrando: {e}")

    def on_hide(self, icon=None, item=None):
        """Oculta la ventana."""
        if self.window:
            try:
                self.window.hide()
            except Exception as e:
                print(f"[APP] Error ocultando: {e}")

    def on_quit(self, icon=None, item=None):
        """Cierra todo de verdad."""
        print("[APP] Cerrando Jarvis...")
        try:
            if self.tray_icon:
                self.tray_icon.visible = False
                self.tray_icon.stop()
        except Exception:
            pass
        try:
            if self.window:
                self.window.destroy()
        except Exception:
            pass
        try:
            if self.streamlit_proc:
                self.streamlit_proc.terminate()
                self.streamlit_proc.wait(timeout=5)
        except Exception:
            if self.streamlit_proc:
                self.streamlit_proc.kill()
        print("[APP] Adios.")
        os._exit(0)

    def on_window_closing(self):
        """Se llama cuando el usuario pulsa X en la ventana."""
        # Devolver False cancela el cierre; ocultamos en su lugar
        self.on_hide()
        return False  # Cancelar cierre real

    def run_tray(self):
        """Corre el icono de la bandeja."""
        try:
            icon_img = Image.open(str(ICON_PATH)).convert("RGBA")
            # Redimensionar para la bandeja
            icon_img = icon_img.resize((64, 64), Image.LANCZOS)
        except Exception as e:
            print(f"[APP] Error cargando icono: {e}")
            icon_img = Image.new("RGBA", (64, 64), (30, 30, 60, 255))

        menu = pystray.Menu(
            pystray.MenuItem("Mostrar Jarvis", self.on_show, default=True),
            pystray.MenuItem("Ocultar", self.on_hide),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Salir", self.on_quit),
        )

        self.tray_icon = pystray.Icon(
            "jarvis",
            icon_img,
            "Jarvis — Asistente",
            menu,
        )
        self.tray_icon.run()

    def start(self):
        print("=" * 50)
        print("  JARVIS — Iniciando...")
        print("=" * 50)

        # 1. Streamlit
        if is_port_open(STREAMLIT_PORT):
            print("[APP] Streamlit ya estaba corriendo.")
            self.streamlit_proc = None
        else:
            print("[APP] Lanzando Streamlit...")
            self.streamlit_proc = start_streamlit()
            print("[APP] Esperando a Streamlit (15-30 seg)...")
            if not wait_for_streamlit():
                print("[APP ERROR] Streamlit no respondio.")
                if self.streamlit_proc:
                    self.streamlit_proc.terminate()
                return
            print("[APP] Streamlit listo.")

        # 2. Tray icon en thread separado
        tray_thread = threading.Thread(target=self.run_tray, daemon=True)
        tray_thread.start()
        time.sleep(1.5)

        # 3. Crear ventana
        print("[APP] Abriendo ventana...")

        # Icono para la taskbar
        if ICON_PATH.exists():
            icon_path_str = str(ICON_PATH)
        else:
            icon_path_str = None

        self.window = webview.create_window(
            title="Jarvis — Asistente",
            url=f"http://127.0.0.1:{STREAMLIT_PORT}",
            width=1400,
            height=900,
            min_size=(900, 600),
            confirm_close=False,
            background_color="#0a0a1a",
        )

        # Intercepta el cierre de ventana para ocultar en lugar de salir
        self.window.events.closing += self.on_window_closing

        # Hilo para forzar el icono después de que la ventana aparezca
        def apply_icon():
            time.sleep(4)  # Esperar a que la ventana se cree
            if ICON_PATH.exists():
                set_taskbar_icon(ICON_PATH)

        threading.Thread(target=apply_icon, daemon=True).start()

        # Arrancar webview
        webview.start(icon=icon_path_str)

        # Si llegamos aqui, webview cerro la ventana de verdad
        print("[APP] Ventana cerrada. Jarvis sigue en bandeja.")
        print("[APP] Click derecho en el icono para salir.")
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            self.on_quit()


def main():
    app = JarvisApp()
    app.start()


if __name__ == "__main__":
    main()