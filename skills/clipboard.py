import pyperclip
from skills.base import Skill


class ClipboardSkill(Skill):
    name = "clipboard"
    description = "Lee y escribe el portapapeles"

    def run(self, action, params):
        if action == "read":
            return self._read()
        if action == "write":
            return self._write(params.get("text", ""))
        return f"Accion desconocida en clipboard: {action}"

    def _read(self):
        try:
            content = pyperclip.paste()
        except Exception as e:
            return f"Error leyendo portapapeles: {e}"
        if not content or not content.strip():
            return "El portapapeles esta vacio."
        # Limitar para no leer 100k caracteres por voz
        preview = content.strip()
        if len(preview) > 500:
            preview = preview[:500] + "..."
        return f"Tengo copiado: {preview}"

    def _write(self, text):
        text = (text or "").strip()
        if not text:
            return "No me diste texto para copiar."
        try:
            pyperclip.copy(text)
            return f"Copiado al portapapeles: {text[:100]}"
        except Exception as e:
            return f"Error escribiendo portapapeles: {e}"