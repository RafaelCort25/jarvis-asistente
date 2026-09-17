import pyautogui
from skills.base import Skill


class EntertainmentSkill(Skill):
    name = "entertainment"
    description = "Control multimedia: play/pause, siguiente, anterior"

    def run(self, action, params):
        if action == "play_pause":
            pyautogui.press("playpause")
            return "Play/Pausa."
        if action == "next_track":
            pyautogui.press("nexttrack")
            return "Siguiente cancion."
        if action == "prev_track":
            pyautogui.press("prevtrack")
            return "Cancion anterior."
        return f"Accion desconocida: {action}"