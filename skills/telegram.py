"""Skill de Telegram: envia archivos generados al chat del usuario."""
from pathlib import Path

from skills.base import Skill
from core import confirmation

ROOT = Path(__file__).resolve().parent.parent
SANDBOX_DIR = ROOT / "sandbox"

# Carpetas donde buscar archivos, en orden de prioridad
SEARCH_DIRS = [
    SANDBOX_DIR / "office",
    SANDBOX_DIR / "images",
    SANDBOX_DIR,
]

# Mapeo de "tipo" en lenguaje natural -> extensiones
TYPE_MAP = {
    "pdf": {".pdf"},
    "word": {".docx", ".doc"},
    "excel": {".xlsx", ".xls", ".csv"},
    "imagen": {".jpg", ".jpeg", ".png", ".gif", ".webp"},
    "codigo": {".py", ".js", ".java", ".html", ".css"},
    "texto": {".txt", ".md"},
}


class TelegramSkill(Skill):
    name = "telegram"
    description = "Envia archivos generados a tu chat de Telegram"

    def run(self, action, params):
        if action == "send_last":
            return self._send_last(params.get("tipo", ""))
        if action == "send_file":
            return self._send_file(params.get("path", ""))
        return f"Accion desconocida en telegram: {action}"

    # ─── HELPERS ─────────────────────────────────────────────────────────

    def _find_latest(self, tipo=""):
        """Busca el archivo mas reciente, opcionalmente filtrado por tipo."""
        extensions = None
        if tipo:
            extensions = TYPE_MAP.get(tipo.lower())

        candidates = []
        for folder in SEARCH_DIRS:
            if not folder.exists():
                continue
            for p in folder.iterdir():
                if not p.is_file():
                    continue
                if extensions and p.suffix.lower() not in extensions:
                    continue
                # Ignorar .bak y temporales
                if p.suffix.lower() in (".bak", ".tmp"):
                    continue
                candidates.append(p)

        if not candidates:
            return None

        # El mas reciente por mtime
        return max(candidates, key=lambda p: p.stat().st_mtime)

    def _send_last(self, tipo=""):
        tipo_str = tipo or "cualquiera"
        print(f"[TELEGRAM] Buscando ultimo archivo (tipo={tipo_str})...")

        latest = self._find_latest(tipo)
        if not latest:
            if tipo:
                return f"No encontre ningun archivo de tipo '{tipo}' en sandbox/."
            return "No encontre ningun archivo generado en sandbox/."

        size_kb = latest.stat().st_size // 1024
        summary = f"Enviar {latest.name} ({size_kb} KB) por Telegram"

        if not confirmation.require("telegram", "send_last", summary):
            return "Cancelado."

        return self._do_send(latest)

    def _send_file(self, path_str):
        if not path_str:
            return "Necesito el path del archivo."

        p = Path(path_str.strip().strip('"').strip("'"))
        if not p.is_absolute():
            p = ROOT / p

        if not p.exists():
            return f"No encontre el archivo: {p}"

        try:
            p.relative_to(ROOT)
        except ValueError:
            return f"Ruta fuera del proyecto, bloqueado: {p}"

        size_kb = p.stat().st_size // 1024
        summary = f"Enviar {p.name} ({size_kb} KB) por Telegram"

        if not confirmation.require("telegram", "send_file", summary):
            return "Cancelado."

        return self._do_send(p)

    def _do_send(self, path):
        try:
            from integrations.notifier import send_file
        except ImportError as e:
            return f"Error importando notifier: {e}"

        try:
            ok = send_file(str(path), caption=f"📎 {path.name}")
        except Exception as e:
            return f"Error enviando por Telegram: {e}"

        if not ok:
            return "No pude enviar. Revisa que hayas hecho /start al bot."

        size_kb = path.stat().st_size // 1024
        print(f"[TELEGRAM] Enviado: {path.name} ({size_kb} KB)")

        return {
            "thought": f"Enviado por Telegram ({size_kb} KB)",
            "display": f"Enviado por Telegram: {path.name} ({size_kb} KB)",
            "voice": f"Listo. Envie {path.name} por Telegram.",
        }