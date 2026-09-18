import json
import re
import ollama
from skills.base import Skill
from core.config_loader import CONFIG


LANGUAGES = {
    "ingles": "English", "inglés": "English", "english": "English",
    "espanol": "Spanish", "español": "Spanish", "spanish": "Spanish",
    "frances": "French", "francés": "French", "french": "French",
    "aleman": "German", "alemán": "German", "german": "German",
    "italiano": "Italian", "portugues": "Portuguese", "portugués": "Portuguese",
    "japones": "Japanese", "japonés": "Japanese",
    "chino": "Chinese", "mandarin": "Chinese",
    "ruso": "Russian", "arabe": "Arabic", "árabe": "Arabic",
    "coreano": "Korean", "hindi": "Hindi",
}


class TranslateSkill(Skill):
    name = "translate"
    description = "Traduce texto a otro idioma"

    def run(self, action, params):
        if action == "text":
            return self._translate(params.get("text", ""), params.get("to", ""))
        return f"Accion desconocida: {action}"

    def _translate(self, text, target_lang):
        if not text:
            return "No me dijiste que traducir."
        if not target_lang:
            return "No me dijiste a que idioma."

        lang_key = target_lang.lower().strip()
        # Buscar idioma
        english_lang = LANGUAGES.get(lang_key)
        if not english_lang:
            # Intentar como viene
            english_lang = target_lang.capitalize()

        model = CONFIG["models"].get("intent", CONFIG["models"]["default"])
        prompt = f"Traduce el siguiente texto al {english_lang}. Responde UNICAMENTE con la traduccion, sin explicaciones, sin comillas, sin texto extra.\n\nTexto: {text}"

        try:
            response = ollama.chat(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                options={"temperature": 0.2},
            )
            translation = response["message"]["content"].strip()
            translation = re.sub(r'^["\']|["\']$', '', translation)

            return {
                "thought": f"Traducir a {english_lang}",
                "display": f"🌐 Original: {text}\n📖 Traduccion: {translation}",
                "voice": translation,
            }
        except Exception as e:
            return f"Error traduciendo: {e}"