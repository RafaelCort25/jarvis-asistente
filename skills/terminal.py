import os
import shlex
import subprocess
from pathlib import Path

from skills.base import Skill
from core import confirmation

ROOT = Path(__file__).resolve().parent.parent

TIMEOUT_SECONDS = 60

# Lista negra: si el comando contiene alguno de estos fragmentos, se bloquea
BLOCKED = [
    "rm -rf /", "rm -rf /*",
    "format c:", "format d:",
    "del /f /s /q c:\\", "del /f /s /q d:\\",
    "mkfs", "dd if=",
    "shutdown /s", "shutdown /r",
    ":(){ :|:& };:",  # fork bomb
    "> /dev/sda",
    "cipher /w",
]


class TerminalSkill(Skill):
    name = "terminal"
    description = "Ejecuta comandos en el sistema (con confirmacion)"

    def run(self, action, params):
        if action == "run":
            return self._run(params.get("command", ""))
        if action == "suggest":
            return self._suggest(params.get("goal", ""))
        return f"Accion desconocida en terminal: {action}"

    def _is_blocked(self, command):
        low = command.lower()
        for b in BLOCKED:
            if b in low:
                return b
        return None

    def _run(self, command):
        command = (command or "").strip()
        if not command:
            return "No me diste comando."

        # Seguridad: lista negra
        blocked = self._is_blocked(command)
        if blocked:
            return f"Comando bloqueado por seguridad (contiene '{blocked}')."

        # Confirmacion obligatoria
        summary = f"Ejecutar en terminal: {command}"
        if not confirmation.require("terminal", "run", summary):
            return "Cancelado."

        try:
            result = subprocess.run(
                command,
                shell=True,
                cwd=str(ROOT),
                capture_output=True,
                text=True,
                timeout=TIMEOUT_SECONDS,
                encoding="utf-8",
                errors="replace",
            )
        except subprocess.TimeoutExpired:
            return f"El comando excedio {TIMEOUT_SECONDS}s y fue terminado."
        except Exception as e:
            return f"Error ejecutando: {e}"

        stdout = (result.stdout or "").strip()
        stderr = (result.stderr or "").strip()
        code = result.returncode

        # Limitar output para no reventar TTS/GUI
        def clip(s, n=2000):
            if len(s) <= n:
                return s
            return s[:n] + f"\n... (recortado, {len(s)-n} caracteres mas)"

        parts = [f"$ {command}"]
        if stdout:
            parts.append(clip(stdout))
        if stderr:
            parts.append(f"[stderr]\n{clip(stderr)}")
        parts.append(f"[exit code: {code}]")

        return "\n".join(parts)

    def _suggest(self, goal):
        """
        Sugerencia rapida basada en palabras clave del objetivo.
        No ejecuta nada. Solo propone.
        """
        goal = (goal or "").lower().strip()
        if not goal:
            return "Dime que quieres lograr y te sugiero el comando."

        suggestions = {
            "estado": "git status",
            "status": "git status",
            "commit": "git add . && git commit -m \"mensaje\"",
            "push": "git push",
            "pull": "git pull",
            "dependencias": "pip install -r requirements.txt",
            "instalar": "pip install -r requirements.txt",
            "tests": "python -m pytest",
            "pruebas": "python -m pytest",
            "version": "python --version",
            "python": "python --version",
            "node": "node --version",
            "npm": "npm --version",
            "ls": "dir",
            "listar": "dir",
        }

        for key, cmd in suggestions.items():
            if key in goal:
                return f"Sugerencia: {cmd}\nDime 'ejecuta {cmd}' para correrlo."

        return f"No tengo una sugerencia obvia para '{goal}'."