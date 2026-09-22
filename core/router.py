import re
import unicodedata
from core.intent import IntentClassifier
from core.agent import Agent
from skills.desktop import DesktopSkill
from skills.browser import BrowserSkill
from skills.entertainment import EntertainmentSkill
from skills.productivity import ProductivitySkill
from skills.system import SystemSkill
from skills.files import FilesSkill
from skills.weather import WeatherSkill
from skills.translate import TranslateSkill
from skills.alarm import AlarmSkill
from skills.dev import DevSkill
from skills.vision import VisionSkill
from skills.docs import DocsSkill

NUM_MAP = {
    "1": 1, "uno": 1, "primero": 1, "primer": 1, "la primera": 1, "el primero": 1,
    "2": 2, "dos": 2, "segundo": 2, "la segunda": 2, "el segundo": 2,
    "3": 3, "tres": 3, "tercero": 3, "tercer": 3, "la tercera": 3, "el tercero": 3,
    "4": 4, "cuatro": 4, "cuarto": 4, "la cuarta": 4, "el cuarto": 4,
    "5": 5, "cinco": 5, "quinto": 5, "la quinta": 5, "el quinto": 5,
}

CANCEL_WORDS = ["cancela", "cancelar", "olvidalo", "nada"]


class Router:
    def __init__(self):
        self.classifier = IntentClassifier()
        self.agent = Agent()
        self.skills = {
            "desktop": DesktopSkill(),
            "browser": BrowserSkill(),
            "entertainment": EntertainmentSkill(),
            "productivity": ProductivitySkill(),
            "system": SystemSkill(),
            "files": FilesSkill(),
            "weather": WeatherSkill(),
            "translate": TranslateSkill(),
            "alarm": AlarmSkill(),
            "dev": DevSkill(),
            "vision": VisionSkill(),
            "docs": DocsSkill(),
        }

    # ─── HELPERS ────────────────────────────────────────────────────────────

    def _parse_choice(self, text):
        t = text.lower().strip()
        t = re.sub(r'[.,;:!?¿¡]', '', t)
        t = re.sub(r'\b(el|la|los|las|quiero|pon|ponme|reproduce|dale|vamos|ok|vale)\b', '', t)
        t = re.sub(r'\s+', ' ', t).strip()
        if t in NUM_MAP:
            return NUM_MAP[t]
        m = re.search(r'\b([1-5])\b', t)
        if m:
            return int(m.group(1))
        return None

    def _is_cancel(self, text):
        t = text.lower().strip()
        return any(w in t for w in CANCEL_WORDS)

    def _is_complex(self, text):
        """Detecta si el comando necesita razonamiento del agente."""
        t = text.lower().strip()
        t = unicodedata.normalize("NFD", t)
        t = "".join(c for c in t if unicodedata.category(c) != "Mn")

        # Si es un comando simple conocido, NO es complejo
        simple_patterns = [
            "abre ", "abrir ", "cierra ", "cerrar ",
            "sube ", "baja ", "silencia",
            "pausa", "play", "siguiente", "anterior",
            "pon ", "ponme ", "reproduce ",
            "guarda nota", "lee mis notas", "mis notas",
            "captura", "bloquea",
            "que clima", "clima en", "traduce",
            "alarma", "recuerdame", "avisame",
            "busca en google", "busca en youtube",
        ]

        for p in simple_patterns:
            if t.startswith(p) or f" {p}" in t:
                # Pero si tiene multiples acciones o "el mas/el ultimo" → complejo
                if " y " not in t and "el mas" not in t and "el ultimo" not in t and "la mas" not in t:
                    return False

        complex_keywords = [
            "el ultimo", "la ultima", "los ultimos", "las ultimas",
            "el primero de los archivos",
            "el mas ", "la mas ",
            "mas reciente", "mas grande", "mas pequeno", "mas antiguo",
            "cuantos archivos", "cuantas archivos", "cuantos pdf",
            "cuantas fotos", "cuantos videos", "cuantos mp4",
            "que archivos", "que documentos",
            "hay algun", "hay alguna", "existe algun",
            "organiza", "ordena", "renombra",
            "y luego", "despues de eso",
            "abre el archivo", "abre el ultimo archivo",
            "cual es el archivo", "cual es la carpeta",
        ]

        for kw in complex_keywords:
            if kw in t:
                return True

        # Multiples verbos con "y"
        if " y " in t:
            verbs = ["abre", "cierra", "busca", "pon", "lista", "muestra", "guarda", "mueve"]
            count = sum(1 for v in verbs if f" {v} " in f" {t} ")
            if count >= 2:
                return True

        return False

    def _quick_match(self, text):
        """Detecta comandos obvios sin llamar al LLM."""
        t = text.lower().strip()
                # Documentos indexados (RAG)
        if any(p in t for p in [
            "que documentos tienes", "que documentos hay", "lista mis documentos",
            "que has indexado", "documentos indexados", "mis documentos",
        ]):
            return [{"skill": "docs", "action": "list", "params": {}}]

        # Indexar archivo/carpeta (con ruta explicita)
        m = re.search(r'\b(?:indexa|aprende|procesa|lee|guarda)\s+(?:el\s+)?(?:archivo|pdf|documento|carpeta)\s+(.+)$', t)
        if m:
            path = m.group(1).strip(" .,!?¡¿")
            if path:
                action = "index_folder" if "carpeta" in t else "index_file"
                return [{"skill": "docs", "action": action, "params": {"path": path}}]

        # "pon X" → YouTube (excluye alarmas, volumen, etc.)
        m = re.search(r'\b(?:pon|pong|ponme|pongme|reproduce|reprodus|ponle|quiero escuchar|quiero oir|escuchar)\s+(.+)$', t)
        if m:
            q = m.group(1).strip(" .,!?¡¿")
            q = re.sub(r'\b(en\s+youtube|en\s+yt|en\s+brave|en\s+chrome|en\s+spotify)\b', '', q).strip()
            exclude = [
                "volumen", "brillo", "pantalla", "musica al", "silencio", "mute",
                "alarma", "alarmas", "temporizador", "timer", "recordatorio",
                "recordar", "recuerda", "recuérdame", "recuerdame", "aviso",
                "avisame", "avísame", "minuto", "minutos", "segundo", "segundos",
                "hora", "horas",
            ]
            if q and not any(e in q for e in exclude):
                return [{"skill": "browser", "action": "search_youtube", "params": {"query": q}}]

        # Buscar archivo
        m = re.search(
            r'\b(?:busca|buscar|encuentra|encontrar|donde esta|donde se encuentra)\s+(?:el|la|mi|los|las)?\s*archivo\s+(.+)$',
            t,
        )
        if m:
            name = m.group(1).strip(" .,!?¡¿")
            name = re.sub(r'\b(de|del|la|el|los|las)\b', '', name).strip()
            if name:
                return [{"skill": "files", "action": "find_file", "params": {"name": name}}]

        # Buscar en google
        m = re.search(r'\b(?:busca|buscar|googlea)\s+en\s+google\s+(.+)$', t)
        if m:
            q = m.group(1).strip(" .,!?¡¿")
            if q:
                return [{"skill": "browser", "action": "search_google", "params": {"query": q}}]

        # Buscar en youtube
        m = re.search(r'\b(?:busca|buscar)\s+en\s+(?:youtube|yt)\s+(.+)$', t)
        if m:
            q = m.group(1).strip(" .,!?¡¿")
            if q:
                return [{"skill": "browser", "action": "search_youtube", "params": {"query": q}}]

        # Listar carpeta
        m = re.search(r'\b(?:lista|muestra|que hay en)\s+(?:la\s+)?carpeta\s+(?:de\s+)?(descargas|documentos|escritorio|imagenes|musica|videos)\b', t)
        if m:
            return [{"skill": "files", "action": "list_folder", "params": {"folder": m.group(1)}}]

        return None

    def _normalize(self, result):
        """Convierte string o dict en dict {voice, display, thought}."""
        if isinstance(result, dict):
            if "voice" in result or "display" in result:
                return {
                    "voice": result.get("voice", ""),
                    "display": result.get("display", ""),
                    "thought": result.get("thought", ""),
                }
            return {
                "voice": result.get("voice", ""),
                "display": result.get("display", str(result)),
                "thought": result.get("thought", ""),
            }
        return {"voice": str(result), "display": str(result), "thought": ""}

    # ─── ROUTE PRINCIPAL ────────────────────────────────────────────────────

    def route(self, text):
        browser = self.skills["browser"]

        # 1. Videos pendientes
        if browser.has_pending():
            if self._is_cancel(text):
                browser.clear_pending()
                return {"voice": "Cancelado.", "display": "Ok, cancelado.", "thought": ""}, False
            num = self._parse_choice(text)
            if num is not None:
                result = browser.run("play_pending", {"index": num})
                return self._normalize(result), False
            browser.clear_pending()

        # 2. Frases de memoria
        t_lower = text.lower().strip()
        if any(t_lower.startswith(p) for p in [
            "recuerda que ", "recuerda esto", "recuerda:",
            "memoriza que ", "memoriza:", "guarda en memoria ",
            "aprende que ", "no olvides que ",
        ]):
            return None, True

        # 3. Pre-clasificador rapido (regex)
        quick = self._quick_match(text)
        if quick:
            actions = quick
        # 4. Si es complejo → AGENTE
        elif self._is_complex(text):
            agent_result = self.agent.run(text, self.skills)
            return agent_result, False
        # 5. LLM clasificador normal
        else:
            intent = self.classifier.classify(text)
            actions = intent.get("actions", [])

        if not actions:
            return None, False

        if all(a.get("skill") == "none" for a in actions):
            return None, True

        results = []
        for act in actions:
            skill_name = act.get("skill", "none")
            if skill_name == "none":
                continue
            skill = self.skills.get(skill_name)
            if not skill:
                continue
            action = act.get("action", "")
            params = act.get("params", {})

            # Fix: docs.ask siempre usa el texto original del usuario como query.
            if skill_name == "docs" and action == "ask":
                params = {"query": text}

            try:
                result = skill.run(action, params)
                if result:
                    results.append(self._normalize(result))
            except Exception as e:
                results.append({"voice": "Error.", "display": f"Error: {e}", "thought": ""})

        if not results:
            return None, True

        if len(results) == 1:
            return results[0], False

        return {
            "voice": " ".join(r["voice"] for r in results if r["voice"]),
            "display": "\n".join(r["display"] for r in results if r["display"]),
            "thought": " | ".join(r["thought"] for r in results if r["thought"]),
        }, False