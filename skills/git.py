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
        # ── Nuevas acciones ──
        if action == "branches":
            return self._branches()
        if action == "checkout":
            return self._checkout(
                params.get("branch", ""),
                create=params.get("create", False),
            )
        if action == "stash":
            return self._stash(params.get("message", ""))
        if action == "stash_pop":
            return self._stash_pop()
        if action == "stash_list":
            return self._stash_list()
        if action == "reset":
            return self._reset(
                params.get("mode", "soft"),
                params.get("n", 1),
            )
        if action == "show":
            return self._show(params.get("ref", "HEAD"))
        if action == "blame":
            return self._blame(params.get("file", ""))
        if action == "remotes":
            return self._remotes()
        if action == "config":
            return self._config()
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

    # ─── RAMAS ────────────────────────────────────────────────────────────

    def _branches(self):
        """Lista las ramas locales y remotas."""
        code, out, err = _git(["branch", "-a", "-vv"])
        if code != 0:
            return f"Error git branch: {err or out}"
        if not out:
            return "No hay ramas."
        return f"Ramas:\n{_clip(out)}"

    def _checkout(self, branch, create=False):
        """Cambia de rama (opcionalmente la crea)."""
        branch = (branch or "").strip()
        if not branch:
            return "Necesito el nombre de la rama."

        accion = "Crear y cambiar a" if create else "Cambiar a"
        if not confirmation.require("git", "checkout", f"{accion} rama '{branch}'"):
            return "Cancelado."

        args = ["checkout", "-b", branch] if create else ["checkout", branch]
        code, out, err = _git(args)
        if code != 0:
            return f"Error git checkout: {err or out}"
        return f"En rama '{branch}'.\n{_clip(out)}"

    # ─── STASH ────────────────────────────────────────────────────────────

    def _stash(self, message=""):
        """Guarda los cambios temporalmente en el stash."""
        message = (message or "").strip()
        if not confirmation.require("git", "stash", f"Guardar cambios en stash"):
            return "Cancelado."
        args = ["stash", "push"]
        if message:
            args += ["-m", message]
        code, out, err = _git(args)
        if code != 0:
            return f"Error git stash: {err or out}"
        return f"Cambios guardados en stash.\n{_clip(out)}"

    def _stash_pop(self):
        """Restaura los cambios del ultimo stash."""
        if not confirmation.require("git", "stash_pop", "Restaurar cambios del stash"):
            return "Cancelado."
        code, out, err = _git(["stash", "pop"])
        if code != 0:
            return f"Error git stash pop: {err or out}"
        return f"Stash restaurado.\n{_clip(out)}"

    def _stash_list(self):
        """Lista los stashes guardados."""
        code, out, err = _git(["stash", "list"])
        if code != 0:
            return f"Error: {err or out}"
        if not out:
            return "No hay stashes guardados."
        return f"Stashes:\n{_clip(out)}"

    # ─── RESET ────────────────────────────────────────────────────────────

    def _reset(self, mode="soft", n=1):
        """Deshace los ultimos N commits (soft/media/hard)."""
        try:
            n = int(n)
        except (ValueError, TypeError):
            n = 1
        n = max(1, min(n, 10))

        mode = (mode or "soft").lower()
        if mode not in ("soft", "mixed", "hard"):
            mode = "soft"

        descripciones = {
            "soft": "sin perder cambios (staging intacto)",
            "mixed": "sin perder cambios (staging limpio)",
            "hard": "PERDIENDO los cambios (cuidado!)",
        }

        summary = f"Deshacer {n} commit(s) ({mode}: {descripciones[mode]})"
        if not confirmation.require("git", "reset", summary):
            return "Cancelado."

        code, out, err = _git(["reset", f"--{mode}", f"HEAD~{n}"])
        if code != 0:
            return f"Error git reset: {err or out}"
        return f"Reset {mode} de {n} commit(s) hecho.\n{_clip(out)}"

    # ─── SHOW ─────────────────────────────────────────────────────────────

    def _show(self, ref="HEAD"):
        """Muestra los detalles de un commit."""
        ref = (ref or "HEAD").strip()
        code, out, err = _git(["show", "--stat", ref])
        if code != 0:
            return f"Error git show: {err or out}"
        return _clip(out, 3000)

    # ─── BLAME ────────────────────────────────────────────────────────────

    def _blame(self, filepath):
        """Muestra quien escribio cada linea de un archivo."""
        filepath = (filepath or "").strip()
        if not filepath:
            return "Necesito el archivo para hacer blame."
        code, out, err = _git(["blame", "--line-porcelain", filepath])
        if code != 0:
            # Fallback: formato normal
            code, out, err = _git(["blame", filepath])
            if code != 0:
                return f"Error git blame: {err or out}"
        return _clip(out, 2500)

    # ─── REMOTES ──────────────────────────────────────────────────────────

    def _remotes(self):
        """Lista los remotos configurados."""
        code, out, err = _git(["remote", "-v"])
        if code != 0:
            return f"Error: {err or out}"
        if not out:
            return "No hay remotos configurados."
        return f"Remotos:\n{_clip(out)}"

    # ─── CONFIG ───────────────────────────────────────────────────────────

    def _config(self):
        """Muestra la configuracion de git (usuario, email)."""
        code_u, user, _ = _git(["config", "user.name"])
        code_e, email, _ = _git(["config", "user.email"])
        code_b, branch, _ = _git(["rev-parse", "--abbrev-ref", "HEAD"])
        code_r, remote, _ = _git(["remote", "get-url", "origin"])

        lineas = [
            f"Usuario: {user or '(no configurado)'}",
            f"Email: {email or '(no configurado)'}",
            f"Rama actual: {branch or '?'}",
            f"Remoto origin: {remote or '(no configurado)'}",
        ]
        return "\n".join(lineas)