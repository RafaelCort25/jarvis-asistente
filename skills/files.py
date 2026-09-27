"""Skill de archivos: buscar, listar, analizar.

Funciones:
- find_file: buscar por nombre
- find_content: buscar TEXTO dentro de archivos (PDF, txt, docx, py, etc.)
- find_advanced: buscar por extension + rango de fechas + tamano
- list_folder: listar con orden y filtros
- recent: los N archivos modificados mas recientemente
- duplicates: encontrar duplicados por hash
- pick: elegir un archivo por criterio
- info: detalles de un archivo
- open_path: abrir en el explorador
- create_folder: crear carpeta
- move: mover archivo
"""
import hashlib
import os
import shutil
from datetime import datetime, timedelta
from pathlib import Path

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

# Extensiones de texto que se pueden leer directamente
TEXT_EXTS = {".txt", ".md", ".py", ".js", ".html", ".css", ".json",
             ".xml", ".yaml", ".yml", ".ini", ".cfg", ".log", ".csv", ".sql"}

# Extensiones que requieren librerias extra
RICH_EXTS = {".pdf", ".docx", ".doc", ".xlsx", ".xls", ".pptx"}


class FilesSkill(Skill):
    name = "files"
    description = "Busca, lista, abre y analiza archivos y carpetas"

    def run(self, action, params):
        if action == "find_file":
            return self._find_file(params.get("name", ""))
        if action == "find_content":
            return self._find_content(
                params.get("text", ""),
                params.get("folder", ""),
                params.get("ext", ""),
                params.get("limit", 20),
            )
        if action == "find_advanced":
            return self._find_advanced(
                params.get("folder", ""),
                params.get("ext", ""),
                params.get("min_kb", 0),
                params.get("max_kb", 0),
                params.get("days", 0),
                params.get("limit", 30),
            )
        if action == "list_folder":
            return self._list_folder(
                params.get("folder", ""),
                sort=params.get("sort", "name"),
                filter_ext=params.get("filter_ext", ""),
                limit=params.get("limit", 20),
            )
        if action == "recent":
            return self._recent(
                params.get("folder", ""),
                params.get("limit", 10),
                params.get("ext", ""),
            )
        if action == "duplicates":
            return self._duplicates(
                params.get("folder", ""),
                params.get("limit", 50),
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

    # ─── RESOLVER RUTA ────────────────────────────────────────────────────

    def _resolve_folder(self, folder):
        folder = folder.lower().strip()
        if folder in COMMON_DIRS:
            return COMMON_DIRS[folder]
        p = Path(folder)
        if p.exists():
            return p
        return None

    # ─── LISTAR ───────────────────────────────────────────────────────────

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

        if filter_ext:
            ext = filter_ext.lower().lstrip(".")
            items = [i for i in items if i.is_file() and i.suffix.lower() == f".{ext}"]

        try:
            if sort == "date_desc":
                items.sort(key=lambda x: x.stat().st_mtime, reverse=True)
            elif sort == "date_asc":
                items.sort(key=lambda x: x.stat().st_mtime)
            elif sort == "size_desc":
                items.sort(key=lambda x: x.stat().st_size, reverse=True)
            elif sort == "size_asc":
                items.sort(key=lambda x: x.stat().st_size)
            else:
                items.sort(key=lambda x: x.name.lower())
        except Exception:
            pass

        total = len(items)
        items = items[:limit]

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

    # ─── BUSCAR POR TEXTO DENTRO DE ARCHIVOS ──────────────────────────────

    def _find_content(self, text, folder="", ext="", limit=20):
        """Busca un texto dentro de archivos."""
        if not text:
            return {
                "thought": "Falta texto a buscar",
                "display": "Dime que texto buscar dentro de los archivos.",
                "voice": "No me dijiste que buscar.",
            }

        text_low = text.lower().strip()

        # Carpetas donde buscar
        if folder:
            base = self._resolve_folder(folder)
            if base is None:
                return {
                    "thought": f"Carpeta no encontrada: {folder}",
                    "display": f"No conozco la carpeta '{folder}'.",
                    "voice": "No encontre esa carpeta.",
                }
            folders = [base]
        else:
            folders = [d for d in COMMON_DIRS.values() if d.exists()]

        # Extensiones permitidas
        ext_filter = None
        if ext:
            ext_filter = ext.lower().lstrip(".")
            if not ext_filter.startswith("."):
                ext_filter = "." + ext_filter

        matches = []

        for base in folders:
            for root, dirs, files in os.walk(base):
                dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS and not d.startswith(".")]
                for f in files:
                    if len(matches) >= limit:
                        break
                    fp = Path(root) / f
                    try:
                        ext_low = fp.suffix.lower()
                        # Filtro de extension
                        if ext_filter and ext_low != ext_filter:
                            continue
                        # Solo texto plano
                        if ext_low not in TEXT_EXTS:
                            continue
                        # Leer y buscar
                        content = fp.read_text(encoding="utf-8", errors="ignore")
                        if text_low in content.lower():
                            # Extraer contexto (linea donde aparece)
                            contexto = ""
                            for linea in content.split("\n"):
                                if text_low in linea.lower():
                                    contexto = linea.strip()[:100]
                                    break
                            matches.append({
                                "path": str(fp),
                                "name": fp.name,
                                "folder": str(fp.parent),
                                "size_kb": round(fp.stat().st_size / 1024, 1),
                                "contexto": contexto,
                            })
                    except Exception:
                        continue
                if len(matches) >= limit:
                    break
            if len(matches) >= limit:
                break

        if not matches:
            return {
                "thought": f"Sin coincidencias de '{text}'",
                "display": f"No encontre archivos con '{text}'.",
                "voice": "No encontre nada.",
            }

        lines = [f"Encontre {len(matches)} archivos con '{text}':"]
        for m in matches:
            lines.append(f"  {m['name']} en {m['folder']}")
            if m["contexto"]:
                lines.append(f"     > {m['contexto']}")

        return {
            "thought": f"Buscar '{text}' en contenido ({len(matches)} matches)",
            "display": "\n".join(lines),
            "voice": f"Encontre {len(matches)} archivos con ese texto.",
            "data": matches,
        }

    # ─── BUSQUEDA AVANZADA ────────────────────────────────────────────────

    def _find_advanced(self, folder="", ext="", min_kb=0, max_kb=0, days=0, limit=30):
        """Busqueda por extension + rango de fechas + tamano."""
        if folder:
            base = self._resolve_folder(folder)
            if base is None:
                return {
                    "thought": f"Carpeta no encontrada: {folder}",
                    "display": f"No conozco la carpeta '{folder}'.",
                    "voice": "No encontre esa carpeta.",
                }
            folders = [base]
        else:
            folders = [d for d in COMMON_DIRS.values() if d.exists()]

        ext_filter = None
        if ext:
            ext_filter = ext.lower().lstrip(".")
            if not ext_filter.startswith("."):
                ext_filter = "." + ext_filter

        fecha_limite = None
        if days and int(days) > 0:
            fecha_limite = datetime.now() - timedelta(days=int(days))

        matches = []
        for base in folders:
            for root, dirs, files in os.walk(base):
                dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS and not d.startswith(".")]
                for f in files:
                    if len(matches) >= limit:
                        break
                    fp = Path(root) / f
                    try:
                        if not fp.is_file():
                            continue
                        # Filtro extension
                        if ext_filter and fp.suffix.lower() != ext_filter:
                            continue
                        # Filtro tamano
                        size_kb = fp.stat().st_size / 1024
                        if min_kb and size_kb < float(min_kb):
                            continue
                        if max_kb and size_kb > float(max_kb):
                            continue
                        # Filtro fecha
                        if fecha_limite:
                            mtime = datetime.fromtimestamp(fp.stat().st_mtime)
                            if mtime < fecha_limite:
                                continue
                        matches.append({
                            "path": str(fp),
                            "name": fp.name,
                            "size_kb": round(size_kb, 1),
                            "date": datetime.fromtimestamp(fp.stat().st_mtime).strftime("%Y-%m-%d"),
                        })
                    except Exception:
                        continue
                if len(matches) >= limit:
                    break
            if len(matches) >= limit:
                break

        if not matches:
            return {
                "thought": "Sin resultados en busqueda avanzada",
                "display": "No encontre archivos con esos criterios.",
                "voice": "No encontre nada.",
            }

        lines = [f"Encontre {len(matches)} archivos:"]
        for m in matches:
            lines.append(f"  {m['name']} ({m['size_kb']} KB) - {m['date']}")

        return {
            "thought": f"Busqueda avanzada ({len(matches)} resultados)",
            "display": "\n".join(lines),
            "voice": f"Encontre {len(matches)} archivos.",
            "data": matches,
        }

    # ─── ARCHIVOS RECIENTES ───────────────────────────────────────────────

    def _recent(self, folder="", limit=10, ext=""):
        """Devuelve los N archivos mas recientes.
        
        Si la carpeta especificada no tiene archivos, busca en TODAS
        las carpetas comunes como fallback.
        """
        if folder:
            base = self._resolve_folder(folder)
            if base is None:
                return {
                    "thought": f"Carpeta no encontrada: {folder}",
                    "display": f"No conozco la carpeta '{folder}'.",
                    "voice": "No encontre esa carpeta.",
                }
            folders = [base]
        else:
            folders = [d for d in COMMON_DIRS.values() if d.exists()]

        ext_filter = None
        if ext:
            ext_filter = ext.lower().lstrip(".")
            if not ext_filter.startswith("."):
                ext_filter = "." + ext_filter

        all_files = []
        for base in folders:
            for root, dirs, files in os.walk(base):
                dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS and not d.startswith(".")]
                for f in files:
                    fp = Path(root) / f
                    try:
                        if not fp.is_file():
                            continue
                        if ext_filter and fp.suffix.lower() != ext_filter:
                            continue
                        all_files.append(fp)
                    except Exception:
                        continue

        # Fallback: si la carpeta especifica no tenia archivos, buscar en todas
        if not all_files and folder:
            print(f"[FILES] '{folder}' vacia, buscando en todas las carpetas comunes")
            folders = [d for d in COMMON_DIRS.values() if d.exists()]
            for base in folders:
                for root, dirs, files in os.walk(base):
                    dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS and not d.startswith(".")]
                    for f in files:
                        fp = Path(root) / f
                        try:
                            if not fp.is_file():
                                continue
                            if ext_filter and fp.suffix.lower() != ext_filter:
                                continue
                            all_files.append(fp)
                        except Exception:
                            continue

        all_files.sort(key=lambda x: x.stat().st_mtime, reverse=True)
        top = all_files[:int(limit)]

        lines = [f"Ultimos {len(top)} archivos modificados:"]
        for fp in top:
            try:
                st = fp.stat()
                date = datetime.fromtimestamp(st.st_mtime).strftime("%Y-%m-%d %H:%M")
                lines.append(f"  {fp.name} ({st.st_size / 1024:.0f} KB) - {date}")
            except Exception:
                lines.append(f"  {fp.name}")

        return {
            "thought": f"Top {len(top)} archivos recientes",
            "display": "\n".join(lines),
            "voice": f"Estos son los {len(top)} archivos mas recientes.",
        }

    # ─── DUPLICADOS ───────────────────────────────────────────────────────

    def _duplicates(self, folder="", limit=50):
        """Encuentra archivos duplicados por hash MD5."""
        if folder:
            base = self._resolve_folder(folder)
            if base is None:
                return {
                    "thought": f"Carpeta no encontrada: {folder}",
                    "display": f"No conozco la carpeta '{folder}'.",
                    "voice": "No encontre esa carpeta.",
                }
            folders = [base]
        else:
            folders = [d for d in COMMON_DIRS.values() if d.exists()]

        hashes = {}
        for base in folders:
            for root, dirs, files in os.walk(base):
                dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS and not d.startswith(".")]
                for f in files:
                    fp = Path(root) / f
                    try:
                        if not fp.is_file() or fp.stat().st_size == 0:
                            continue
                        h = hashlib.md5()
                        with open(fp, "rb") as fh:
                            for chunk in iter(lambda: fh.read(8192), b""):
                                h.update(chunk)
                        digest = h.hexdigest()
                        hashes.setdefault(digest, []).append(str(fp))
                    except Exception:
                        continue

        duplicados = {h: paths for h, paths in hashes.items() if len(paths) > 1}
        if not duplicados:
            return {
                "thought": "Sin duplicados",
                "display": "No encontre archivos duplicados.",
                "voice": "No hay duplicados.",
            }

        # Calcular espacio desperdiciado
        total_dup = 0
        for h, paths in duplicados.items():
            try:
                size = Path(paths[0]).stat().st_size
                total_dup += size * (len(paths) - 1)
            except Exception:
                pass

        lines = [f"Encontre {len(duplicados)} grupos de duplicados ({total_dup / 1024 / 1024:.1f} MB):"]
        for i, (h, paths) in enumerate(list(duplicados.items())[:int(limit)], 1):
            lines.append(f"\nGrupo {i}:")
            for p in paths:
                lines.append(f"  {p}")

        return {
            "thought": f"{len(duplicados)} grupos de duplicados",
            "display": "\n".join(lines),
            "voice": f"Encontre {len(duplicados)} grupos de duplicados.",
            "data": duplicados,
        }

    # ─── PICK: ELEGIR UN ARCHIVO ──────────────────────────────────────────

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
            if crit in ("mas_reciente", "ultimo"):
                items.sort(key=lambda x: x.stat().st_mtime, reverse=True)
            elif crit in ("mas_antiguo", "primero"):
                items.sort(key=lambda x: x.stat().st_mtime)
            elif crit == "mas_grande":
                items.sort(key=lambda x: x.stat().st_size, reverse=True)
            elif crit == "mas_pequeno":
                items.sort(key=lambda x: x.stat().st_size)
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

    # ─── INFO ─────────────────────────────────────────────────────────────

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
                f"Tamano: {size_kb:.1f} KB\n"
                f"Modificado: {modified}"
            )
        except Exception as e:
            return f"Error: {e}"

    # ─── ABRIR ────────────────────────────────────────────────────────────

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

    # ─── BUSCAR POR NOMBRE ────────────────────────────────────────────────

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

    # ─── CREAR CARPETA ────────────────────────────────────────────────────

    def _create_folder(self, name):
        if not name:
            return "No me dijiste el nombre de la carpeta."
        try:
            path = HOME / "Desktop" / name
            path.mkdir(parents=True, exist_ok=True)
            return f"Carpeta creada en el escritorio: {name}"
        except Exception as e:
            return f"Error al crear carpeta: {e}"

    # ─── MOVER ────────────────────────────────────────────────────────────

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