import base64
import io
import ollama
import pyautogui
from skills.base import Skill
from core.config_loader import CONFIG

VISION_PROMPT = (
    "Describe esta captura de pantalla en espanol. "
    "Se breve y concreto. Menciona: nombre exacto de la aplicacion si lo puedes leer, "
    "que tipo de contenido se ve, y 2-3 elementos especificos que observes. "
    "Si no puedes leer un texto, di 'no legible' en vez de adivinar. "
    "NO inventes elementos que no esten claramente visibles. Maximo 80 palabras."
)

VISION_PROMPT_CODE = (
    "En esta captura hay codigo en un editor. Responde en espanol: "
    "1) Nombre del archivo si es legible, o 'no legible'. "
    "2) Lenguaje de programacion. "
    "3) Que hace el codigo segun lo que ves. "
    "4) Errores o warnings visibles. Si no ves ninguno, di 'ninguno visible'. "
    "Se estricto: si no puedes leer algo con claridad, di 'no legible'. "
    "NO inventes nombres, funciones ni errores. Maximo 120 palabras."
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