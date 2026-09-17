import subprocess
from urllib.parse import quote_plus
from skills.base import Skill

BRAVE_PATH = r"C:\Program Files\BraveSoftware\Brave-Browser\Application\brave.exe"


class BrowserSkill(Skill):
    name = "browser"
    description = "Busca en YouTube, Google y reproduce videos"

    def __init__(self):
        self.pending_videos = []  # lista de videos pendientes por elegir

    def has_pending(self):
        return len(self.pending_videos) > 0

    def clear_pending(self):
        self.pending_videos = []

    def run(self, action, params):
        if action == "cancel_pending":
            self.clear_pending()
            return "Ok, cancelado."
        if action == "search_youtube":
            return self._youtube_search(params.get("query", ""))
        if action == "search_google":
            return self._google(params.get("query", ""))
        if action == "open_url":
            return self._open_url(params.get("url", ""))
        if action == "play_pending":
            return self._play_pending(params.get("index", 0))
        return f"Accion desconocida: {action}"

    # ─── YOUTUBE ─────────────────────────────────────────────────────────────

    def _youtube_search(self, query):
        if not query:
            return "No me dijiste que buscar en YouTube."
        try:
            import yt_dlp
        except ImportError:
            return "Falta yt-dlp. Ejecuta: pip install yt-dlp"

        ydl_opts = {
            "quiet": True,
            "no_warnings": True,
            "extract_flat": True,
            "skip_download": True,
        }
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                result = ydl.extract_info(f"ytsearch5:{query}", download=False)
                entries = (result or {}).get("entries") or []
        except Exception as e:
            return f"Error buscando en YouTube: {e}"

        if not entries:
            return f"No encontre resultados para: {query}"

        self.pending_videos = []
        for e in entries[:5]:
            vid = e.get("id")
            if not vid:
                continue
            self.pending_videos.append({
                "id": vid,
                "title": e.get("title", "(sin titulo)"),
                "url": f"https://www.youtube.com/watch?v={vid}",
            })

        if not self.pending_videos:
            return "No pude extraer videos."

        lines = [f"Encontre {len(self.pending_videos)} videos para: {query}"]
        for i, v in enumerate(self.pending_videos, 1):
            lines.append(f"{i}. {v['title']}")
        lines.append("Di el numero del que quieras o di 'cancela'.")
        return "\n".join(lines)

    def _play_pending(self, index):
        try:
            idx = int(index) - 1
        except (ValueError, TypeError):
            return "Numero invalido."

        if not (0 <= idx < len(self.pending_videos)):
            return f"Numero fuera de rango. Hay {len(self.pending_videos)} videos."

        video = self.pending_videos[idx]
        try:
            subprocess.Popen([BRAVE_PATH, video["url"]])
            self.clear_pending()
            return f"Reproduciendo: {video['title']}"
        except Exception as e:
            import webbrowser
            webbrowser.open(video["url"])
            self.clear_pending()
            return f"Reproduciendo (fallback): {video['title']}"

    # ─── GOOGLE / URL ────────────────────────────────────────────────────────

    def _google(self, query):
        if not query:
            return "No me dijiste que buscar en Google."
        url = f"https://www.google.com/search?q={quote_plus(query)}"
        return self._launch_brave(url, f"Buscando en Google: {query}")

    def _open_url(self, url):
        if not url:
            return "No me diste la URL."
        if not url.startswith("http"):
            url = "https://" + url
        return self._launch_brave(url, f"Abriendo {url}")

    def _launch_brave(self, url, success_msg):
        try:
            subprocess.Popen([BRAVE_PATH, url])
            return success_msg
        except Exception as e:
            import webbrowser
            webbrowser.open(url)
            return f"{success_msg} (fallback: {e})"