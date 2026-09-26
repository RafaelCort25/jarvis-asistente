import requests
from skills.base import Skill


class JokeSkill(Skill):
    name = "chiste"
    description = "Cuenta un chiste aleatorio"

    def run(self, action, params):
        if action == "tell":
            return self._tell()
        if action == "tell_es":
            return self._tell_es()
        return f"Accion desconocida: {action}"

    def _tell(self):
        try:
            response = requests.get("https://official-joke-api.appspot.com/random_joke", timeout=10)
            joke = response.json()
            return {
                "thought": "Cuentar un chiste en inglés",
                "display": f"Chuck Norris dice: {joke['setup']} {joke['punchline']}",
                "voice": f"Chuck Norris dice: {joke['setup']} {joke['punchline']}",
            }
        except Exception as e:
            return f"Error al obtener el chiste: {e}"

    def _tell_es(self):
        try:
            response = requests.get("https://official-joke-api.appspot.com/random_joke", timeout=10)
            joke = response.json()
            return {
                "thought": "Cuentar un chiste en español",
                "display": f"Chuck Norris dice: {joke['setup']} {joke['punchline']}",
                "voice": f"Chuck Norris dice: {joke['setup']} {joke['punchline']}",
            }
        except Exception as e:
            return f"Error al obtener el chiste: {e}"