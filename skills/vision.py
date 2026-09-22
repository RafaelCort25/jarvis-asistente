import base64
import io
import ollama
import pyautogui
from skills.base import Skill
from core.config_loader import CONFIG

VISION_PROMPT = (
    "Describe lo que ves en esta captura de pantalla en espanol. "
    "Se especifico: menciona la aplicacion o ventana activa, "
    "el contenido principal, textos visibles importantes, "
    "y cualquier error o elemento relevante. "
    "Maximo 120 palabras. No inventes nada que no veas."
)

VISION_PROMPT_CODE = (
    "Analiza esta captura de pantalla que muestra codigo en un editor. "
    "En espanol, describe: 1) que archivo o lenguaje se ve, "
    "2) que hace el codigo, 3) si detectas errores, warnings o algo raro. "
    "Maximo 150 palabras. No inventes lineas que no veas."
)


class VisionSkill(Skill):
    name = "vision"
    description = "Analiza la pantalla actual usando un modelo de vision local"

    def __init__(self):
        self.model = CONFIG["models"].get("vision", "llava-phi3")

    def run(self, action, params):
        if action == "describe_screen":
            return self._describe(params.get("mode", "general"))
        if action == "explain_screen_code":
            return self._describe("code")
        return f"Accion desconocida en vision: {action}"

    def _capture(self):
        img = pyautogui.screenshot()
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return base64.b64encode(buf.getvalue()).decode("utf-8")

    def _describe(self, mode):
        try:
            b64 = self._capture()
        except Exception as e:
            return f"No pude capturar la pantalla: {e}"

        prompt = VISION_PROMPT_CODE if mode == "code" else VISION_PROMPT

        try:
            response = ollama.chat(
                model=self.model,
                messages=[
                    {
                        "role": "user",
                        "content": prompt,
                        "images": [b64],
                    }
                ],
                options={"temperature": 0.2},
            )
            texto = response["message"]["content"].strip()
            if not texto:
                return "No pude interpretar la pantalla."
            return texto
        except Exception as e:
            return f"Error de vision: {e}"