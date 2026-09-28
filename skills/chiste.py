import requests
import random
from skills.base import Skill


# Chistes locales en español (fallback si no hay internet)
CHISTES_ES = [
    {"setup": "¿Qué le dice un bit a otro bit?", "punchline": "Nos vemos en el bus."},
    {"setup": "¿Cómo se despiden los químicos?", "punchline": "Ácido un placer."},
    {"setup": "¿Qué hace una abeja en el gimnasio?", "punchline": "Zum-ba."},
    {"setup": "¿Cuál es el colmo de un electricista?", "punchline": "Que su hijo se llame Apagón."},
    {"setup": "¿Qué le dice un jardinero a otro?", "punchline": "Nos vemos cuando podamos."},
    {"setup": "¿Cómo se llama el campeón de buceo japonés?", "punchline": "Tokofondo."},
    {"setup": "¿Qué le dijo un techo a otro techo?", "punchline": "Techo de menos."},
    {"setup": "—Doctor, me duele aquí.", "punchline": "—Pues no se ponga ahí."},
    {"setup": "¿Por qué los programadores prefieren el modo oscuro?", "punchline": "Porque la luz atrae a los bugs."},
    {"setup": "Hay 10 tipos de personas en el mundo:", "punchline": "los que entienden binario y los que no."},
    {"setup": "¿Qué es un terapeuta?", "punchline": "Un señor que te cobra por escucharte, como tu ex, pero legal."},
    {"setup": "—Camarero, hay una mosca en mi sopa.", "punchline": "—Tranquilo, no la cobramos."},
    {"setup": "¿Cómo se llama el hermano tonto de Batman?", "punchline": "Súper Sordo."},
    {"setup": "—Mamá, en la escuela me dicen distraído.", "punchline": "—Niño, que vives en la casa de al lado."},
    {"setup": "¿Qué hace un perro con un taladro?", "punchline": "Agujerear."},
    {"setup": "¿Cómo se dice 'pantalón' en japonés?", "punchline": "Komo."},
    {"setup": "—Tengo un problema con mi vista.", "punchline": "—Pues aquí no vendemos vistas."},
    {"setup": "¿Qué le dijo una impresora a otra?", "punchline": "Eres una copia barata."},
]


class JokeSkill(Skill):
    name = "chiste"
    description = "Cuenta un chiste aleatorio en español o inglés"

    def run(self, action, params):
        lang = (params.get("lang") or "").lower().strip()
        if action == "tell":
            # Detectar idioma pedido
            if lang in ("en", "english", "ingles", "inglés"):
                return self._tell_en()
            return self._tell_es()
        if action == "tell_es":
            return self._tell_es()
        if action == "tell_en":
            return self._tell_en()
        return {"thought": "Accion desconocida", "display": f"Accion desconocida: {action}", "voice": "Accion desconocida"}

    def _tell_es(self):
        # Solo chistes locales en espanol (la API Chuck Norris solo tiene en ingles)
        chiste = random.choice(CHISTES_ES)
        texto = f"{chiste['setup']} {chiste['punchline']}"
        return {
            "thought": "Chiste local en espanol",
            "display": f"Chiste: {texto}",
            "voice": texto,
        }

    def _tell_en(self):
        # API en ingles (jokes en ingles)
        try:
            response = requests.get("https://official-joke-api.appspot.com/random_joke", timeout=8)
            joke = response.json()
            text = f"{joke.get('setup','')} {joke.get('punchline','')}".strip()
            if text:
                return {
                    "thought": "Joke in English",
                    "display": f"Joke: {text}",
                    "voice": text,
                }
        except Exception:
            pass
        # Fallback si falla la API
        return {
            "thought": "API en ingles caida",
            "display": "Could not fetch an English joke right now. Try again in a moment.",
            "voice": "Could not fetch an English joke right now.",
        }
