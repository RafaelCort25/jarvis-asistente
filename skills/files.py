import os
import subprocess
from pathlib import Path
from datetime import datetime
from skills.base import Skill

HOME = Path.home()

# Carpetas comunes con alias
COMMON_DIRS = {
    "descargas": HOME / "Downloads",
    "documentos": HOME / "Documents",
    "escritorio": HOME / "Desktop",
    "imagenes": HOME / "Pictures",
    "musica": HOME / "Music",
    "videos": HOME / "Videos",
    "jarvis": Path("C:/JARVIS"),
}


class FilesSkill(Skill):
    name = "files"
    description = "Busca archivos, gestiona carpetas, informacion de archivos"

    def run(self, action, params):
        if action == "find_file":
            return self._find_file(params.get("name", ""))
        if action == "list_folder":
            return self._list_folder(params.get("folder", ""))
        if action == "file_info":
            return self._file_info(params.get("path", ""))
        if action == "open_path":
            return self._open_path(params.get("path", ""))
        if action == "create_folder":
            return self._create_folder(params.get("name", ""))
        return f"Accion desconocida: {action}"

    def _find_file(self, name):
        if not name:
            return "No me dijiste que archivo buscar."
        name = name.lower().strip()

        # Buscar en carpetas comunes (rapido, no en todo el disco)
        matches = []
        # Carpetas a excluir
        EXCLUDE = {"venv", "node_modules", "__pycache__", "site-packages",
                   ".git", "build", "dist", "target", "Library"}
        for label, folder in COMMON_DIRS.items():
            if not folder.exists():
                continue
            for root, dirs, files in os.walk(folder):
                # Excluir carpetas comunes
                dirs[:] = [d for d in dirs if d not in EXCLUDE and not d.startswith(".")]
                if any(part.startswith(".") or part.startswith("$") for part in Path(root).parts):
                    continue
                for f in files:
                    if name in f.lower():
                        matches.append(Path(root) / f)
                        if len(matches) >= 10:
                            break
                if len(matches) >= 10:
                    break
            if len(matches) >= 10:
                break

        if not matches:
            return f"No encontre archivos con '{name}'."

        lines = [f"Encontre {len(matches)} coincidencias:"]
        for m in matches[:10]:
            try:
                size_kb = m.stat().st_size / 1024
                lines.append(f"- {m.name} ({size_kb:.0f} KB) en {m.parent}")
            except Exception:
                lines.append(f"- {m}")
        return "\n".join(lines)

    def _list_folder(self, folder):
        if not folder:
            return "No me dijiste que carpeta."
        folder = folder.lower().strip()

        # Buscar en COMMON_DIRS primero
        path = COMMON_DIRS.get(folder)
        if path is None:
            # Intentar como ruta directa
            path = Path(folder)
            if not path.exists():
                return f"No conozco la carpeta '{folder}'."

        try:
            items = sorted(path.iterdir())
            dirs = [i for i in items if i.is_dir()]
            files = [i for i in items if i.is_file()]
            lines = [f"Contenido de {path.name} ({len(dirs)} carpetas, {len(files)} archivos):"]
            for d in dirs[:10]:
                lines.append(f"  [DIR] {d.name}")
            for f in files[:15]:
                try:
                    size = f.stat().st_size / 1024
                    lines.append(f"  {f.name} ({size:.0f} KB)")
                except Exception:
                    lines.append(f"  {f.name}")
            if len(items) > 25:
                lines.append(f"  ... y {len(items) - 25} mas")
            return "\n".join(lines)
        except Exception as e:
            return f"Error listando {folder}: {e}"

    def _file_info(self, path):
        if not path:
            return "No me diste la ruta."
        p = Path(path)
        if not p.exists():
            return f"No existe: {path}"
        try:
            stat = p.stat()
            size_kb = stat.st_size / 1024
            modified = datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M")
            kind = "carpeta" if p.is_dir() else "archivo"
            return (
                f"{kind.capitalize()}: {p.name}\n"
                f"Ruta: {p}\n"
                f"Tamaño: {size_kb:.1f} KB\n"
                f"Modificado: {modified}"
            )
        except Exception as e:
            return f"Error: {e}"

    def _open_path(self, path):
        if not path:
            return "No me diste la ruta."
        p = Path(path)
        if not p.exists():
            # Probar como alias
            if path.lower() in COMMON_DIRS:
                p = COMMON_DIRS[path.lower()]
            else:
                return f"No existe: {path}"
        try:
            os.startfile(p)
            return f"Abriendo {p.name}."
        except Exception as e:
            return f"Error: {e}"

    def _create_folder(self, name):
        if not name:
            return "No me dijiste el nombre de la carpeta."
        try:
            path = HOME / "Desktop" / name
            path.mkdir(parents=True, exist_ok=True)
            return f"Carpeta creada en el escritorio: {name}"
        except Exception as e:
            return f"Error al crear carpeta: {e}"