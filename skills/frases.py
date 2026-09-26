import random
from skills.base import Skill


class FrasesSkill(Skill):
    name = "frases"
    description = "Frases motivacionales"

    def run(self, action, params):
        if action == "random":
            return self._random()
        return f"Accion desconocida: {action}"

    def _random(self):
        frases = [
            "La vida es 10% lo que te sucede y 90% cómo reaccionas a ello.",
            "El éxito no es la ausencia de fracasos, sino la persistencia frente a ellos.",
            "La única forma de hacer un gran trabajo es amar lo que haces.",
            "El verdadero valor de una vida no está en la cantidad de tiempo que le queda, sino en la cantidad de tiempo que le has dado a tus sueños.",
            "La única forma de hacer un gran trabajo es amar lo que haces.",
            "La vida es 10% lo que te sucede y 90% cómo reaccionas a ello.",
            "El éxito no es la ausencia de fracasos, sino la persistencia frente a ellos.",
            "La vida es 10% lo que te sucede y 90% cómo reaccionas a ello.",
            "El éxito no es la ausencia de fracasos, sino la persistencia frente a ellos.",
            "La vida es 10% lo que te sucede y 90% cómo reaccionas a ello.",
        ]
        return {
            "thought": "Elegir una frase motivacional aleatoria",
            "display": random.choice(frases),
            "voice": random.choice(frases),
        }