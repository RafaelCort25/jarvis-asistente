import ollama
from core.config_loader import CONFIG
from core.memory import Memory


class Brain:
    def __init__(self, model=None):
        from core.model_config import get_model
        self.model = model or get_model("chat")
        self.history = []
        self.name = CONFIG["senna"]["name"]
        self.memory = Memory()

        self.system_prompt = (
            f"Eres {self.name}, una asistente personal. "
            "Hablas en espanol, eres directa, concisa y util. "
            "Nunca dices que eres un modelo de lenguaje ni mencionas Ollama, GPT ni otras IA. "
            "Si tienes contexto de conversaciones pasadas o preferencias, usalo para responder mejor. "
            "Si el usuario te pide recordar algo, confirmalo brevemente. "
            "Responde SIEMPRE en 1-3 oraciones maximo salvo que te pidan detalle. "
            "REGLA CRITICA: si te preguntan quien te creo, responde exactamente: "
            "'Fui creado por Rafael como asistente personal.' "
            "NUNCA inventes historia sobre JARVIS, Iron Man, Marvel, Douglas Engelbart, "
            "ni inventes URLs, fuentes, citas ni estadisticas."
        )

    def chat(self, user_input):
        # Guardar mensaje del usuario
        self.memory.save_message("user", user_input)

        # Detectar preferencias explicitas
        self._maybe_save_preference(user_input)

        # Construir contexto de memoria
                # Solo buscar contexto si el mensaje tiene suficiente contenido
        if len(user_input.strip()) >= 4:
            context = self.memory.build_context(user_input)
        else:
            context = ""

        # Sistema con contexto inyectado
        system = self.system_prompt
        if context:
            system += f"\n\n{context}"

        self.history.append({"role": "user", "content": user_input})
        messages = [{"role": "system", "content": system}] + self.history[-10:]

        try:
            response = ollama.chat(model=self.model, messages=messages, stream=False)
            reply = response["message"]["content"]
            self.history.append({"role": "assistant", "content": reply})
            # Guardar respuesta
            self.memory.save_message("assistant", reply)
            return reply
        except Exception as e:
            return f"[ERROR] {e}"

    def _maybe_save_preference(self, text):
        """Detecta frases tipo 'recuerda que X' o 'mi X es Y' y las guarda."""
        t = text.lower().strip()

        # "recuerda que X"
        for prefix in ["recuerda que ", "recuerda esto: ", "recuerda: ", "memoriza que "]:
            if t.startswith(prefix):
                content = text[len(prefix):].strip()
                if content:
                    self.memory.save_preference(
                        f"nota_{len(self.memory.get_preferences())}",
                        content,
                    )
                return

        # "mi X es Y"
        import re
        m = re.search(r'\bmi\s+(\w+)\s+es\s+(.+?)(?:\.|$)', t)
        if m:
            key = m.group(1).strip()
            value = m.group(2).strip()
            if key and value:
                self.memory.save_preference(f"mi_{key}", value)

    def reset(self):
        self.history = []