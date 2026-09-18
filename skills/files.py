import os
import shutil
import subprocess
from pathlib import Path
from datetime import datetime
from skills.base import Skill

HOME = Path.home()

COMMON_DIRS = {
    "descargas": HOME / "Downloads",
    "documentos": HOME / "Documents",
    "escritorio": HOME / "Desktop",
    "imagenes": HOME / "Pictures",
    "musica": HOME / "Music",
    "videos": HOME / "Videos",
    "jarvis": Path("C:/JARVIS"),
}

EXCLUDE_DIRS = {
    "venv", "node_modules", "__pycache__", "site-packages",
    ".git", "build", "dist", "target", "Library",
}


class FilesSkill(Skill):
    name = "files"
    description = "Busca, lista, abre archivos y carpetas"

    def run(self, action, params):
        if action == "find_file":
            return self._find_file(params.get("name", ""))
        if action == "list_folder":
            return self._list_folder(
                params.get("folder", ""),
                sort=params.get("sort", "name"),
                filter_ext=params.get("filter_ext", ""),
                limit=params.get("limit", 20),
            )
        if action == "pick":
            return self._pick(
                params.get("folder", ""),
                params.get("criteria", "mas_reciente"),
                filter_ext=params.get("filter_ext", ""),
            )
        if action == "info":
            return self._info(params.get("path", ""))
        if action == "open_path":
            return self._open_path(params.get("path", ""))
        if action == "create_folder":
            return self._create_folder(params.get("name", ""))
        if action == "move":
            return self._move(params.get("src", ""), params.get("dst", ""))
        return f"Accion desconocida: {action}"

    # ─── RESOLVER RUTA ──────────────────────────────────────────────────────

    def _resolve_folder(self, folder):
        """Convierte 'descargas' o ruta completa a Path."""
        folder = folder.lower().strip()
        if folder in COMMON_DIRS:
            return COMMON_DIRS[folder]
        p = Path(folder)
        if p.exists():
            return p
        return None

    # ─── LISTAR CON ORDEN Y FILTROS ─────────────────────────────────────────

    def _list_folder(self, folder, sort="name", filter_ext="", limit=20):
        path = self._resolve_folder(folder)
        if path is None:
            return f"No conozco la carpeta '{folder}'."
        if not path.exists():
            return f"No existe: {path}"

        try:
            items = list(path.iterdir())
        except Exception as e:
            return f"Error accediendo a {folder}: {e}"

        # Filtrar por extension
        if filter_ext:
            ext = filter_ext.lower().lstrip(".")
            items = [i for i in items if i.is_file() and i.suffix.lower() == f".{ext}"]

        # Ordenar
        try:
            if sort == "date_desc":
                items.sort(key=lambda x: x.stat().st_mtime, reverse=True)
            elif sort == "date_asc":
                items.sort(key=lambda x: x.stat().st_mtime)
            elif sort == "size_desc":
                items.sort(key=lambda x: x.stat().st_size, reverse=True)
            elif sort == "size_asc":
                items.sort(key=lambda x: x.stat().st_size)
            else:  # name
                items.sort(key=lambda x: x.name.lower())
        except Exception:
            pass

        total = len(items)
        items = items[:limit]

        # Construir salida
        lines = [f"Carpeta: {path.name} ({total} elementos)"]
        for item in items:
            try:
                st = item.stat()
                size_kb = st.st_size / 1024
                date = datetime.fromtimestamp(st.st_mtime).strftime("%Y-%m-%d")
                kind = "[DIR]" if item.is_dir() else ""
                lines.append(f"  {kind} {item.name} ({size_kb:.0f} KB) - {date}")
            except Exception:
                lines.append(f"  {item.name}")
        if total > limit:
            lines.append(f"  ... y {total - limit} mas")

        # Resultado para el agente (JSON estructurado)
        files_data = []
        for item in items:
            try:
                st = item.stat()
                files_data.append({
                    "name": item.name,
                    "path": str(item),
                    "size_kb": round(st.st_size / 1024, 1),
                    "date": datetime.fromtimestamp(st.st_mtime).strftime("%Y-%m-%d %H:%M"),
                    "is_dir": item.is_dir(),
                })
            except Exception:
                pass

        return {
            "thought": f"Listar {folder} ({total} elementos)",
            "display": "\n".join(lines),
            "voice": f"Hay {total} elementos en {folder}.",
            "data": files_data,
        }

    # ─── PICK: ELEGIR UN ARCHIVO SEGUN CRITERIO ─────────────────────────────

    def _pick(self, folder, criteria, filter_ext=""):
        path = self._resolve_folder(folder)
        if path is None:
            return {"error": f"No conozco la carpeta '{folder}'."}

        try:
            items = [i for i in path.iterdir() if i.is_file()]
        except Exception as e:
            return {"error": f"Error accediendo a {folder}: {e}"}

        if filter_ext:
            ext = filter_ext.lower().lstrip(".")
            items = [i for i in items if i.suffix.lower() == f".{ext}"]

        if not items:
            return {"error": f"No hay archivos en {folder}."}

        try:
            crit = criteria.lower().strip()
            if crit == "mas_reciente":
                items.sort(key=lambda x: x.stat().st_mtime, reverse=True)
            elif crit == "mas_antiguo":
                items.sort(key=lambda x: x.stat().st_mtime)
            elif crit == "mas_grande":
                items.sort(key=lambda x: x.stat().st_size, reverse=True)
            elif crit == "mas_pequeno":
                items.sort(key=lambda x: x.stat().st_size)
            elif crit == "ultimo":
                items.sort(key=lambda x: x.stat().st_mtime, reverse=True)
            elif crit == "primero":
                items.sort(key=lambda x: x.stat().st_mtime)
            else:
                items.sort(key=lambda x: x.name.lower())
        except Exception:
            pass

        chosen = items[0]
        try:
            st = chosen.stat()
            return {
                "path": str(chosen),
                "name": chosen.name,
                "size_kb": round(st.st_size / 1024, 1),
                "date": datetime.fromtimestamp(st.st_mtime).strftime("%Y-%m-%d %H:%M"),
            }
        except Exception as e:
            return {"error": str(e)}

    # ─── INFO ───────────────────────────────────────────────────────────────

    def _info(self, path):
        if not path:
            return "No me diste la ruta."
        p = Path(path)
        if not p.exists():
            return f"No existe: {path}"
        try:
            st = p.stat()
            size_kb = st.st_size / 1024
            modified = datetime.fromtimestamp(st.st_mtime).strftime("%Y-%m-%d %H:%M")
            kind = "carpeta" if p.is_dir() else "archivo"
            return (
                f"{kind.capitalize()}: {p.name}\n"
                f"Ruta: {p}\n"
                f"Tamaño: {size_kb:.1f} KB\n"
                f"Modificado: {modified}"
            )
        except Exception as e:
            return f"Error: {e}"

    # ─── ABRIR ──────────────────────────────────────────────────────────────

    def _open_path(self, path):
        if not path:
            return "No me diste la ruta."
        p = Path(path)
        if not p.exists():
            if path.lower() in COMMON_DIRS:
                p = COMMON_DIRS[path.lower()]
            else:
                return {"error": f"No existe: {path}"}
        try:
            os.startfile(p)
            return {
                "thought": f"Abrir {p.name}",
                "display": f"Abriendo {p.name}.",
                "voice": "Abriendo.",
            }
        except Exception as e:
            return {"error": str(e)}

    # ─── BUSCAR ─────────────────────────────────────────────────────────────

    def _find_file(self, name):
        if not name:
            return "No me dijiste que archivo buscar."
        name = name.lower().strip()

        matches = []
        for label, folder in COMMON_DIRS.items():
            if not folder.exists():
                continue
            for root, dirs, files in os.walk(folder):
                dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS and not d.startswith(".")]
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

    # ─── CREAR CARPETA ──────────────────────────────────────────────────────

    def _create_folder(self, name):
        if not name:
            return "No me dijiste el nombre de la carpeta."
        try:
            path = HOME / "Desktop" / name
            path.mkdir(parents=True, exist_ok=True)
            return f"Carpeta creada en el escritorio: {name}"
        except Exception as e:
            return f"Error al crear carpeta: {e}"

    # ─── MOVER ──────────────────────────────────────────────────────────────

    def _move(self, src, dst):
        if not src or not dst:
            return "Necesito origen y destino."
        src_p = Path(src)
        if not src_p.exists():
            return f"No existe: {src}"
        dst_p = self._resolve_folder(dst) if dst.lower() in COMMON_DIRS else Path(dst)
        try:
            if dst_p.is_dir():
                final = dst_p / src_p.name
            else:
                final = dst_p
            shutil.move(str(src_p), str(final))
            return f"Movido a {final}"
        except Exception as e:
            return f"Error moviendo: {e}"