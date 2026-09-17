import re
from core.intent import IntentClassifier
from skills.desktop import DesktopSkill
from skills.browser import BrowserSkill
from skills.entertainment import EntertainmentSkill
from skills.productivity import ProductivitySkill
from skills.system import SystemSkill
from skills.files import FilesSkill


NUM_MAP = {
    "1": 1, "uno": 1, "primero": 1, "primer": 1, "la primera": 1, "el primero": 1,
    "2": 2, "dos": 2, "segundo": 2, "la segunda": 2, "el segundo": 2,
    "3": 3, "tres": 3, "tercero": 3, "tercer": 3, "la tercera": 3, "el tercero": 3,
    "4": 4, "cuatro": 4, "cuarto": 4, "la cuarta": 4, "el cuarto": 4,
    "5": 5, "cinco": 5, "quinto": 5, "la quinta": 5, "el quinto": 5,
}

CANCEL_WORDS = ["cancela", "cancelar", "olvidalo", "olvidalo", "nada"]


class Router:
    def __init__(self):
        self.classifier = IntentClassifier()
        self.skills = {
            "desktop": DesktopSkill(),
            "browser": BrowserSkill(),
            "entertainment": EntertainmentSkill(),
            "productivity": ProductivitySkill(),
            "system": SystemSkill(),
            "files": FilesSkill(),
        }

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

    def _quick_match(self, text):
        """Detecta comandos obvios sin llamar al LLM. Devuelve lista de acciones o None."""
        t = text.lower().strip()
        # Buscar archivo: "busca el archivo X", "busca mi archivo X", "encuentra archivo X"
        m = re.search(
            r'\b(?:busca|buscar|encuentra|encontrar|donde esta|donde se encuentra)\s+(?:el|la|mi|los|las)?\s*archivo\s+(.+)$',
            t,
        )
        if m:
            name = m.group(1).strip(" .,!?¡¿")
            name = re.sub(r'\b(de|del|la|el|los|las)\b', '', name).strip()
            if name:
                return [{"skill": "files", "action": "find_file", "params": {"name": name}}]

        # Buscar en google: "busca en google X"
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

        # Buscar en descargas/documentos/etc
        m = re.search(r'\b(?:lista|muestra|que hay en)\s+(?:la\s+)?carpeta\s+(?:de\s+)?(descargas|documentos|escritorio|imagenes|musica|videos)\b', t)
        if m:
            return [{"skill": "files", "action": "list_folder", "params": {"folder": m.group(1)}}]

        return None

    def route(self, text):
        browser = self.skills["browser"]

        # 1. Videos pendientes
        if browser.has_pending():
            if self._is_cancel(text):
                browser.clear_pending()
                return "Ok, cancelado.", False

            num = self._parse_choice(text)
            if num is not None:
                result = browser.run("play_pending", {"index": num})
                return result, False

            browser.clear_pending()
                    # Frases de memoria: dejar que el Brain las procese (no es skill)
        t_lower = text.lower().strip()
        if any(t_lower.startswith(p) for p in [
            "recuerda que ", "recuerda esto", "recuerda:",
            "memoriza que ", "memoriza:", "guarda en memoria ",
            "aprende que ", "no olvides que ",
        ]):
            return None, True  # va a brain.chat(), que guarda la preferencia

        # 2. Pre-clasificador por regex (rapido y preciso para casos obvios)
        quick = self._quick_match(text)
        if quick:
            actions = quick
        else:
            # 3. LLM clasifica el resto
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
            try:
                result = skill.run(action, params)
                if result:
                    results.append(result)
            except Exception as e:
                results.append(f"Error en {skill_name}.{action}: {e}")

        if not results:
            return None, True

        return "\n".join(results), False