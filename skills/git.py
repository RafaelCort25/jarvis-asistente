import subprocess
from pathlib import Path

from skills.base import Skill
from core import confirmation

ROOT = Path(__file__).resolve().parent.parent

TIMEOUT = 30


def _git(args, timeout=TIMEOUT):
    """Ejecuta git con args como lista. Devuelve (code, stdout, stderr)."""
    try:
        result = subprocess.run(
            ["git"] + args,
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            timeout=timeout,
            encoding="utf-8",
            errors="replace",
        )
        return result.returncode, (result.stdout or "").strip(), (result.stderr or "").strip()
    except subprocess.TimeoutExpired:
        return -1, "", f"Timeout tras {timeout}s"
    except FileNotFoundError:
        return -1, "", "git no esta instalado o no esta en PATH"
    except Exception as e:
        return -1, "", f"Error: {e}"


def _clip(text, n=2000):
    if len(text) <= n:
        return text
    return text[:n] + f"\n... (recortado, {len(text)-n} caracteres mas)"


class GitSkill(Skill):
    name = "git"
    description = "Operaciones git locales (status, diff, add, commit, push, pull, log)"

    def run(self, action, params):
        if action == "status":
            return self._status()
        if action == "diff":
            return self._diff(params.get("staged", False))
        if action == "log":
            return self._log(params.get("n", 5))
        if action == "add":
            return self._add(params.get("paths", "."))
        if action == "commit":
            return self._commit(params.get("message", ""))
        if action == "push":
            return self._push()
        if action == "pull":
            return self._pull()
        return f"Accion desconocida en git: {action}"

    # ── Read-only ──────────────────────────────────────────────
    def _status(self):
        code, out, err = _git(["status", "--short", "--branch"])
        if code != 0:
            return f"Error git status: {err or out}"
        if not out:
            return "Sin cambios."
        return f"git status:\n{_clip(out)}"

    def _diff(self, staged=False):
        args = ["diff", "--stat"]
        if staged:
            args = ["diff", "--cached", "--stat"]
        code, out, err = _git(args)
        if code != 0:
            return f"Error git diff: {err or out}"
        if not out:
            return "No hay cambios en el diff."
        return f"git diff:\n{_clip(out)}"

    def _log(self, n=5):
        try:
            n = int(n)
        except (ValueError, TypeError):
            n = 5
        n = max(1, min(n, 30))
        code, out, err = _git(["log", f"-{n}", "--oneline"])
        if code != 0:
            return f"Error git log: {err or out}"
        if not out:
            return "Sin commits."
        return f"Ultimos {n} commits:\n{_clip(out)}"

    # ── Escritura con confirmacion ─────────────────────────────
    def _add(self, paths="."):
        paths = (paths or ".").strip()
        if not confirmation.require("git", "add", f"Hacer git add {paths}"):
            return "Cancelado."
        code, out, err = _git(["add"] + paths.split())
        if code != 0:
            return f"Error git add: {err or out}"
        # Mostrar que se añadió
        _, status_out, _ = _git(["status", "--short"])
        if status_out:
            return f"Cambios añadidos al staging:\n{_clip(status_out)}"
        return "Nada que añadir."

    def _commit(self, message):
        message = (message or "").strip()
        if not message:
            return "Necesito un mensaje para el commit."

        # Verificar que hay algo en staging
        code, staged, err = _git(["diff", "--cached", "--name-only"])
        if code != 0:
            return f"Error verificando staging: {err}"
        if not staged:
            return "No hay cambios en staging. Di 'añade todo al staging' primero."

        summary = f"Hacer commit con mensaje: \"{message}\""
        if not confirmation.require("git", "commit", summary):
            return "Cancelado."

        code, out, err = _git(["commit", "-m", message])
        if code != 0:
            return f"Error git commit: {err or out}"
        # Mostrar primera línea del output (el hash)
        first_line = out.split("\n")[0] if out else "Commit hecho."
        return f"Commit hecho: {first_line}"

    def _push(self):
        # Obtener rama actual
        code, branch, _ = _git(["rev-parse", "--abbrev-ref", "HEAD"])
        branch = branch.strip() if code == 0 else "actual"
        if not confirmation.require(
            "git", "push", f"Subir cambios al remoto en la rama {branch}"
        ):
            return "Cancelado."
        code, out, err = _git(["push"], timeout=60)
        if code != 0:
            return f"Error git push: {err or out}"
        return f"Push hecho.\n{_clip(out)}"

    def _pull(self):
        if not confirmation.require("git", "pull", "Bajar cambios del remoto"):
            return "Cancelado."
        code, out, err = _git(["pull"], timeout=60)
        if code != 0:
            return f"Error git pull: {err or out}"
        return f"Pull hecho.\n{_clip(out)}"