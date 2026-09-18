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
            return {
                "thought": "Cancelar selección de video",
                "display": "Ok, cancelado.",
                "voice": "Cancelado.",
            }
        if action == "search_youtube":
            return self._youtube_search(params.get("query", ""))
        if action == "search_google":
            return self._google(params.get("query", ""))
        if action == "open_url":
            return self._open_url(params.get("url", ""))
        if action == "play_pending":
            return self._play_pending(params.get("index", 0))
        return {
            "thought": f"Acción desconocida: {action}",
            "display": f"Accion desconocida: {action}",
            "voice": "No entendí esa acción.",
        }

    # ─── YOUTUBE ─────────────────────────────────────────────────────────────

    def _youtube_search(self, query):
        if not query:
            return {
                "thought": "Búsqueda en YouTube vacía",
                "display": "No me dijiste qué buscar en YouTube.",
                "voice": "No me dijiste qué buscar.",
            }
        try:
            import yt_dlp
        except ImportError:
            return {
                "thought": "Librería yt-dlp no instalada",
                "display": "Falta yt-dlp. Ejecuta: pip install yt-dlp",
                "voice": "Falta instalar la librería de YouTube.",
            }

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
            return {
                "thought": f"Error en yt_dlp: {e}",
                "display": f"Error buscando en YouTube: {e}",
                "voice": "Ocurrió un error al buscar en YouTube.",
            }

        if not entries:
            return {
                "thought": f"Sin resultados para: {query}",
                "display": f"No encontré resultados para: {query}",
                "voice": "No encontré resultados.",
            }

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
            return {
                "thought": "No se pudieron extraer videos válidos",
                "display": "No pude extraer videos.",
                "voice": "No pude extraer los videos.",
            }

        # Display: lista completa
        display_lines = [f"🎵 Encontre {len(self.pending_videos)} videos para: {query}"]
        for i, v in enumerate(self.pending_videos, 1):
            display_lines.append(f"  {i}. {v['title']}")
        display_lines.append("Di el numero del que quieras o 'cancela'.")

        # Voice: solo lo esencial + lista numerada con titulos cortos
        titles_short = [v["title"][:60] for v in self.pending_videos]
        voice_parts = [f"Encontre {len(self.pending_videos)} canciones."]
        for i, t in enumerate(titles_short, 1):
            voice_parts.append(f"La {i}: {t}.")
        voice_parts.append("Cual pongo?")

        return {
            "thought": f"Buscar '{query}' en YouTube, ordenar resultados",
            "display": "\n".join(display_lines),
            "voice": " ".join(voice_parts),
        }

    def _play_pending(self, index):
        try:
            idx = int(index) - 1
        except (ValueError, TypeError):
            return {
                "thought": "Índice inválido enviado",
                "display": "Número inválido.",
                "voice": "Ese número no es válido.",
            }

        if not (0 <= idx < len(self.pending_videos)):
            return {
                "thought": "Índice fuera de rango",
                "display": f"Número fuera de rango. Hay {len(self.pending_videos)} videos.",
                "voice": "Número fuera de rango.",
            }

        video = self.pending_videos[idx]
        try:
            subprocess.Popen([BRAVE_PATH, video["url"]])
            self.clear_pending()
            return {
                "thought": f"Reproducir video {index}",
                "display": f"Reproduciendo: {video['title']}",
                "voice": "Reproduciendo.",
            }
        except Exception as e:
            import webbrowser
            webbrowser.open(video["url"])
            self.clear_pending()
            return {
                "thought": f"Reproducir video {index} (fallback)",
                "display": f"Reproduciendo (fallback): {video['title']}",
                "voice": "Reproduciendo.",
            }

    # ─── GOOGLE / URL ────────────────────────────────────────────────────────

    def _google(self, query):
        if not query:
            return {
                "thought": "Consulta de Google vacía",
                "display": "No me dijiste qué buscar en Google.",
                "voice": "No me dijiste qué buscar.",
            }
        url = f"https://www.google.com/search?q={quote_plus(query)}"
        self._launch_brave(url, "")
        return {
            "thought": f"Abrir Google con '{query}'",
            "display": f"Buscando en Google: {query}",
            "voice": "Listo.",
        }

    def _open_url(self, url):
        if not url:
            return {
                "thought": "URL vacía",
                "display": "No me diste la URL.",
                "voice": "No me diste la URL.",
            }
        if not url.startswith("http"):
            url = "https://" + url
        self._launch_brave(url, "")
        return {
            "thought": f"Abrir URL {url}",
            "display": f"Abriendo {url}",
            "voice": "Listo.",
        }

    def _launch_brave(self, url, success_msg):
        try:
            subprocess.Popen([BRAVE_PATH, url])
            return success_msg
        except Exception as e:
            import webbrowser
            webbrowser.open(url)
            return f"{success_msg} (fallback: {e})"