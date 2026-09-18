"""
App de escritorio de Jarvis — usa el ORBE como interfaz principal.
Se conecta al api_server.py que sirve el orbe y expone /chat.
"""
import os
import sys
import time
import socket
import threading
from pathlib import Path

import webview
from PIL import Image
import pystray

ROOT = Path(__file__).resolve().parent.parent
os.chdir(ROOT)

ICON_PATH = ROOT / "desktop" / "assets" / "jarvis.ico"
API_PORT = 8000
API_URL = f"http://127.0.0.1:{API_PORT}/"


def is_port_open(port=API_PORT):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.5)
        return s.connect_ex(("127.0.0.1", port)) == 0


def wait_for_api(timeout=30):
    """Espera a que el api_server este escuchando."""
    start = time.time()
    while time.time() - start < timeout:
        if is_port_open(API_PORT):
            return True
        time.sleep(0.5)
    return False


class JarvisApp:
    def __init__(self):
        self.window = None
        self.tray_icon = None

    def on_show(self, icon=None, item=None):
        if self.window:
            try:
                self.window.show()
                self.window.restore()
            except Exception as e:
                print(f"[APP] Error mostrando: {e}")

    def on_hide(self, icon=None, item=None):
        if self.window:
            try:
                self.window.hide()
            except Exception as e:
                print(f"[APP] Error ocultando: {e}")

    def on_quit(self, icon=None, item=None):
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
        print("[APP] Adios.")
        os._exit(0)

    def on_window_closing(self):
        self.on_hide()
        return False  # No cerrar, ocultar

    def run_tray(self):
        try:
            icon_img = Image.open(str(ICON_PATH)).convert("RGBA")
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
            "jarvis", icon_img, "Jarvis — Asistente", menu,
        )
        self.tray_icon.run()

    def start(self):
        print("=" * 55)
        print("  JARVIS — Iniciando interfaz...")
        print("=" * 55)

        # Esperar a que el api_server este listo
        if not is_port_open(API_PORT):
            print(f"[APP] Esperando al api_server en puerto {API_PORT}...")
            if not wait_for_api(30):
                print(f"[APP ERROR] api_server no respondio en puerto {API_PORT}.")
                print("[APP ERROR] Inicia primero: python launcher.py")
                return
        print(f"[APP] API server listo en puerto {API_PORT}.")

        # Icono de la bandeja en thread
        tray_thread = threading.Thread(target=self.run_tray, daemon=True)
        tray_thread.start()
        time.sleep(1.5)

        # Crear ventana nativa apuntando al orbe
        print("[APP] Abriendo ventana del orbe...")
        icon_path_str = str(ICON_PATH) if ICON_PATH.exists() else None

        self.window = webview.create_window(
            title="Jarvis — Asistente",
            url=API_URL,
            width=1400,
            height=900,
            min_size=(900, 600),
            confirm_close=False,
            background_color="#0a0908",
        )
        self.window.events.closing += self.on_window_closing

        webview.start(icon=icon_path_str)
        print("[APP] Ventana cerrada. Jarvis sigue en la bandeja.")

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