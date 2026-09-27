"""Skill de edicion: modifica archivos existentes con instrucciones en lenguaje natural."""
import json
import re
import shutil
from datetime import datetime
from pathlib import Path

import ollama
from docx import Document
from openpyxl import load_workbook
from openpyxl.styles import PatternFill

# Para PDFs
try:
    from pypdf import PdfReader, PdfWriter
    HAS_PYPDF = True
except ImportError:
    HAS_PYPDF = False

# Para imagenes
try:
    from PIL import Image
    HAS_PIL = True
except ImportError:
    HAS_PIL = False

from skills.base import Skill
from core.config_loader import CONFIG
from core import confirmation

ROOT = Path(__file__).resolve().parent.parent
UPLOADS_DIR = ROOT / "sandbox" / "uploads"

# Tipos soportados
DOCX_EXTS = {".docx"}
XLSX_EXTS = {".xlsx", ".xlsm"}
TEXT_EXTS = {".txt", ".md", ".py", ".js", ".java", ".html", ".css",
             ".json", ".yaml", ".yml", ".csv", ".sh", ".ps1"}


class EditSkill(Skill):
    name = "edit"
    description = "Modifica archivos existentes (Word, Excel, texto) con instrucciones"

    def __init__(self):
        from core.model_config import get_model
        self.model = get_model("chat")

    def run(self, action, params):
        # ── Modify (Word/Excel/texto) ──
        if action == "modify":
            return self._modify(
                params.get("path", ""),
                params.get("instruction", ""),
                params.get("output", ""),
            )
        if action == "list_uploads":
            return self._list_uploads()

        # ── PDF ──
        if action == "pdf_merge":
            return self._pdf_merge(
                params.get("files", []),
                params.get("output", ""),
            )
        if action == "pdf_split":
            return self._pdf_split(
                params.get("path", ""),
                params.get("output_dir", ""),
            )
        if action == "pdf_remove_pages":
            return self._pdf_remove_pages(
                params.get("path", ""),
                params.get("pages", []),
                params.get("output", ""),
            )
        if action == "pdf_rotate":
            return self._pdf_rotate(
                params.get("path", ""),
                params.get("pages", []),
                params.get("angle", 90),
                params.get("output", ""),
            )

        # ── Imagenes ──
        if action == "image_resize":
            return self._image_resize(
                params.get("path", ""),
                params.get("width", 0),
                params.get("height", 0),
                params.get("output", ""),
            )
        if action == "image_crop":
            return self._image_crop(
                params.get("path", ""),
                params.get("box", []),
                params.get("output", ""),
            )
        if action == "image_rotate":
            return self._image_rotate(
                params.get("path", ""),
                params.get("angle", 90),
                params.get("output", ""),
            )
        if action == "image_convert":
            return self._image_convert(
                params.get("path", ""),
                params.get("format", "png"),
                params.get("output", ""),
            )

        # ── JSON / YAML / CSV ──
        if action == "json_modify":
            return self._json_modify(
                params.get("path", ""),
                params.get("instruction", ""),
                params.get("output", ""),
            )
        if action == "yaml_modify":
            return self._yaml_modify(
                params.get("path", ""),
                params.get("instruction", ""),
                params.get("output", ""),
            )
        if action == "csv_modify":
            return self._csv_modify(
                params.get("path", ""),
                params.get("instruction", ""),
                params.get("output", ""),
            )

        return f"Accion desconocida en edit: {action}"

    # ─── HELPERS ─────────────────────────────────────────────────────────

    def _resolve_path(self, path_str):
        if not path_str:
            return None
        raw = path_str.strip().strip('"').strip("'")
        p = Path(raw)
        if not p.is_absolute():
            p = ROOT / p
        if p.exists():
            return p
        return None

    def _latest_in_uploads(self):
        """Devuelve el archivo mas reciente en sandbox/uploads/."""
        if not UPLOADS_DIR.exists():
            return None
        files = [f for f in UPLOADS_DIR.iterdir() if f.is_file()]
        if not files:
            return None
        return max(files, key=lambda p: p.stat().st_mtime)

    def _resolve_output(self, original, output_str):
        """Devuelve el path de salida. Si no se da, usa <nombre>_mod.<ext>."""
        if output_str:
            out = Path(output_str.strip().strip('"').strip("'"))
            if not out.is_absolute():
                out = ROOT / out
            if not out.suffix:
                out = out.with_suffix(original.suffix)
            return out
        return original.with_name(f"{original.stem}_mod{original.suffix}")

    def _ask_llm_for_replacements(self, instruction, content_preview, file_type):
        """Le pide al LLM que traduzca la instruccion en cambios concretos."""
        prompt = f"""El usuario quiere modificar un archivo de tipo {file_type}.
Su instruccion: "{instruction}"

Contenido del archivo para contexto:
---INICIO---
{content_preview[:3000]}
---FIN---

Devuelve un objeto JSON con la lista de reemplazos exactos.
Cada reemplazo debe tener una clave "old" (texto que existe literalmente en el archivo)
y una clave "new" (texto de reemplazo).

NUNCA inventes texto que no exista en el archivo.
Responde SOLO con el JSON."""

        schema = {
            "type": "object",
            "properties": {
                "replacements": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "old": {"type": "string"},
                            "new": {"type": "string"},
                        },
                        "required": ["old", "new"],
                    },
                },
            },
            "required": ["replacements"],
        }

        try:
            resp = ollama.chat(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                options={"temperature": 0.1},
                format=schema,
                stream=False,
            )
            raw = resp["message"]["content"].strip()
            print(f"[EDIT] Respuesta del LLM: {raw[:300]}")
            return self._parse_json(raw)
        except Exception as e:
            return {"error": str(e)}

    def _parse_json(self, raw):
        """Extrae el JSON de la respuesta del LLM. Soporta objeto o array."""
        # Quitar ```json ... ```
        m = re.search(r'```(?:json)?\s*([\{\[][\s\S]*?[\}\]])\s*```', raw)
        if m:
            raw = m.group(1)
        else:
            # Buscar el primer { o [ y el ultimo } o ]
            first_obj = raw.find("{")
            first_arr = raw.find("[")
            if first_obj == -1 and first_arr == -1:
                return {"error": "No hay JSON en la respuesta"}
            if first_arr >= 0 and (first_obj == -1 or first_arr < first_obj):
                start = first_arr
                end = raw.rfind("]")
            else:
                start = first_obj
                end = raw.rfind("}")
            if start >= 0 and end > start:
                raw = raw[start:end + 1]
        try:
            parsed = json.loads(raw)
            # Normalizar: si es array, envolverlo en {"operations": [...]}
            if isinstance(parsed, list):
                return {"operations": parsed}
            return parsed
        except Exception as e:
            return {"error": f"JSON invalido: {e}", "raw": raw[:500]}

    # ─── PREVIEW ─────────────────────────────────────────────────────────

    def _preview_for_llm(self, path, file_type):
        """Devuelve texto de muestra del archivo para dar contexto al LLM."""
        try:
            if file_type == "docx":
                doc = Document(str(path))
                return "\n".join(p.text for p in doc.paragraphs if p.text.strip())[:3000]
            elif file_type == "xlsx":
                wb = load_workbook(str(path), read_only=True, data_only=True)
                lines = []
                for sn in wb.sheetnames[:2]:
                    ws = wb[sn]
                    lines.append(f"[Hoja: {sn}]")
                    for i, row in enumerate(ws.iter_rows(values_only=True)):
                        if i >= 20:
                            break
                        cells = [str(c) if c is not None else "" for c in row]
                        lines.append(" | ".join(cells))
                wb.close()
                return "\n".join(lines)[:3000]
            else:
                return path.read_text(encoding="utf-8", errors="replace")[:3000]
        except Exception as e:
            return f"(no se pudo leer el archivo: {e})"

    # ─── APLICAR CAMBIOS POR FORMATO ─────────────────────────────────────

    def _apply_docx(self, path, out_path, replacements):
        doc = Document(str(path))
        total = 0
        for rep in replacements:
            old = rep.get("old", "")
            new = rep.get("new", "")
            if not old:
                continue
            # Recorrer parrafos y runs
            for para in doc.paragraphs:
                for run in para.runs:
                    if old in run.text:
                        run.text = run.text.replace(old, new)
                        total += 1
            # Tambien tablas
            for table in doc.tables:
                for row in table.rows:
                    for cell in row.cells:
                        for para in cell.paragraphs:
                            for run in para.runs:
                                if old in run.text:
                                    run.text = run.text.replace(old, new)
                                    total += 1
        doc.save(str(out_path))
        return total

    def _apply_xlsx(self, path, out_path, replacements):
        wb = load_workbook(str(path))
        total = 0
        for rep in replacements:
            old = rep.get("old", "")
            new = rep.get("new", "")
            if not old:
                continue
            for ws in wb.worksheets:
                for row in ws.iter_rows():
                    for cell in row:
                        if isinstance(cell.value, str) and old in cell.value:
                            cell.value = cell.value.replace(old, new)
                            total += 1
        wb.save(str(out_path))
        return total

    def _apply_text(self, path, out_path, replacements):
        content = path.read_text(encoding="utf-8", errors="replace")
        total = 0
        for rep in replacements:
            old = rep.get("old", "")
            new = rep.get("new", "")
            if not old:
                continue
            count = content.count(old)
            if count > 0:
                content = content.replace(old, new)
                total += count
        out_path.write_text(content, encoding="utf-8")
        return total

    # ─── MODIFY ──────────────────────────────────────────────────────────

    def _modify(self, path_str, instruction, output_str):
        instruction = (instruction or "").strip()
        if not instruction:
            return "Dime que modificacion quieres hacer."

        # Resolver path: explicito o ultimo en uploads
        if path_str:
            path = self._resolve_path(path_str)
            if not path:
                return f"No encontre el archivo: {path_str}"
        else:
            path = self._latest_in_uploads()
            if not path:
                return (
                    "No hay archivos en sandbox/uploads/ para modificar. "
                    "Pon un archivo ahi o dime el path completo."
                )
            print(f"[EDIT] Usando el archivo mas reciente de uploads: {path.name}")

        ext = path.suffix.lower()
        if ext in DOCX_EXTS:
            file_type = "docx"
        elif ext in XLSX_EXTS:
            file_type = "xlsx"
        elif ext in TEXT_EXTS:
            file_type = "texto"
        else:
            return f"Formato no soportado: {ext}"

        try:
            path.relative_to(ROOT)
        except ValueError:
            return f"Ruta fuera del proyecto, bloqueado: {path}"

        out_path = self._resolve_output(path, output_str)
        try:
            out_path.relative_to(ROOT)
        except ValueError:
            return f"Ruta de salida fuera del proyecto: {out_path}"

        # 1. Contexto para el LLM
        print(f"[EDIT] Analizando {path.name} ({file_type})...")
        preview = self._preview_for_llm(path, file_type)

        # 2. Pedir cambios al LLM
        print(f"[EDIT] Interpretando instruccion con {self.model}...")
        result = self._ask_llm_for_replacements(instruction, preview, file_type)

        if "error" in result:
            return f"Error interpretando la instruccion: {result['error']}"

        replacements = result.get("replacements", [])
        if not replacements:
            return "El modelo no encontro cambios concretos para esa instruccion."

        # 3. Preview + confirmacion
        preview_lines = [f"Cambios propuestos ({len(replacements)}):"]
        for r in replacements[:10]:
            old = r.get("old", "")[:60]
            new = r.get("new", "")[:60]
            preview_lines.append(f'  "{old}" -> "{new}"')
        if len(replacements) > 10:
            preview_lines.append(f"  ... (+{len(replacements)-10} mas)")
        print("\n[EDIT] " + "\n       ".join(preview_lines) + "\n")

        summary = f"Modificar {path.name} con {len(replacements)} cambios"
        if not confirmation.require("edit", "modify", summary):
            return "Cancelado."

        # 4. Aplicar cambios
        try:
            if file_type == "docx":
                total = self._apply_docx(path, out_path, replacements)
            elif file_type == "xlsx":
                total = self._apply_xlsx(path, out_path, replacements)
            else:
                total = self._apply_text(path, out_path, replacements)
        except Exception as e:
            return f"Error aplicando cambios: {e}"

        if total == 0:
            return (
                "Ningun cambio se aplico. El texto a buscar no coincide "
                "con el contenido del archivo."
            )

        size_bytes = out_path.stat().st_size
        size_kb = size_bytes // 1024 if size_bytes >= 1024 else 0
        size_str = f"{size_kb} KB" if size_kb > 0 else f"{size_bytes} bytes"
        print(f"[EDIT] Guardado: {out_path} ({total} cambios aplicados)")

        return {
            "thought": f"{total} cambios aplicados en {file_type}",
            "display": (
                f"Archivo modificado: {out_path}\n"
                f"({total} cambios aplicados, {size_str}) KB)\n\n"
                f"Origen: {path.name}"
            ),
            "voice": f"Listo. Modifique {path.name} con {total} cambios.",
        }

    # ─── LIST UPLOADS ────────────────────────────────────────────────────

    # ─── PDF ─────────────────────────────────────────────────────────────

    def _resolve_output_pdf(self, original_path, output_str, suffix=""):
        if output_str:
            out = Path(output_str.strip().strip('"').strip("'"))
            if not out.is_absolute():
                out = ROOT / out
            if not out.suffix:
                out = out.with_suffix(".pdf")
            return out
        stem = original_path.stem + suffix
        return original_path.with_name(f"{stem}.pdf")

    def _pdf_merge(self, files, output_str):
        if not HAS_PYPDF:
            return "Falta pypdf. Ejecuta: pip install pypdf"
        if not files or len(files) < 2:
            return "Necesito al menos 2 PDFs para unir."
        paths = []
        for f in files:
            p = self._resolve_path(f)
            if p and p.suffix.lower() == ".pdf":
                paths.append(p)
            else:
                return f"No encontre el PDF: {f}"
        try:
            writer = PdfWriter()
            for pdf in paths:
                reader = PdfReader(str(pdf))
                for page in reader.pages:
                    writer.add_page(page)
            if output_str:
                out = self._resolve_output_pdf(paths[0], output_str)
            else:
                out = paths[0].with_name(f"{paths[0].stem}_merged.pdf")
            try:
                out.relative_to(ROOT)
            except ValueError:
                return f"Ruta fuera del proyecto: {out}"
            out.parent.mkdir(parents=True, exist_ok=True)
            with open(out, "wb") as f:
                writer.write(f)
            return {
                "thought": f"Unidos {len(paths)} PDFs",
                "display": f"PDF unido: {out.name}\n({len(paths)} PDFs, {out.stat().st_size // 1024} KB)",
                "voice": f"Listo. Uni {len(paths)} PDFs en {out.name}.",
            }
        except Exception as e:
            return f"Error uniendo PDFs: {e}"

    def _pdf_split(self, path_str, output_dir):
        if not HAS_PYPDF:
            return "Falta pypdf."
        path = self._resolve_path(path_str)
        if not path or path.suffix.lower() != ".pdf":
            return f"No encontre el PDF: {path_str}"
        try:
            reader = PdfReader(str(path))
            n = len(reader.pages)
            if output_dir:
                out_dir = Path(output_dir.strip().strip('"'))
                if not out_dir.is_absolute():
                    out_dir = ROOT / out_dir
            else:
                out_dir = path.parent / f"{path.stem}_paginas"
            try:
                out_dir.relative_to(ROOT)
            except ValueError:
                return f"Ruta fuera del proyecto: {out_dir}"
            out_dir.mkdir(parents=True, exist_ok=True)
            for i, page in enumerate(reader.pages, 1):
                writer = PdfWriter()
                writer.add_page(page)
                out_file = out_dir / f"{path.stem}_pag_{i:03d}.pdf"
                with open(out_file, "wb") as f:
                    writer.write(f)
            return {
                "thought": f"Dividido en {n} paginas",
                "display": f"PDF dividido en {n} paginas: {out_dir}",
                "voice": f"Listo. Dividi el PDF en {n} paginas.",
            }
        except Exception as e:
            return f"Error dividiendo PDF: {e}"

    def _pdf_remove_pages(self, path_str, pages, output_str):
        if not HAS_PYPDF:
            return "Falta pypdf."
        path = self._resolve_path(path_str)
        if not path or path.suffix.lower() != ".pdf":
            return f"No encontre el PDF: {path_str}"
        if not pages:
            return "Necesito los numeros de pagina a eliminar."
        try:
            reader = PdfReader(str(path))
            n = len(reader.pages)
            to_remove = set()
            for p in pages:
                if 1 <= p <= n:
                    to_remove.add(p - 1)
            writer = PdfWriter()
            for i, page in enumerate(reader.pages):
                if i not in to_remove:
                    writer.add_page(page)
            out = self._resolve_output_pdf(path, output_str, "_sin_paginas")
            try:
                out.relative_to(ROOT)
            except ValueError:
                return f"Ruta fuera del proyecto: {out}"
            with open(out, "wb") as f:
                writer.write(f)
            return {
                "thought": f"Eliminadas {len(to_remove)} paginas",
                "display": f"PDF modificado: {out.name}\n({len(to_remove)} paginas eliminadas de {n})",
                "voice": f"Listo. Elimine {len(to_remove)} paginas.",
            }
        except Exception as e:
            return f"Error: {e}"

    def _pdf_rotate(self, path_str, pages, angle, output_str):
        if not HAS_PYPDF:
            return "Falta pypdf."
        path = self._resolve_path(path_str)
        if not path or path.suffix.lower() != ".pdf":
            return f"No encontre el PDF: {path_str}"
        if angle not in (90, 180, 270):
            return "Angulo invalido. Usa 90, 180 o 270."
        try:
            reader = PdfReader(str(path))
            writer = PdfWriter()
            rotate_all = not pages
            for i, page in enumerate(reader.pages):
                page_num = i + 1
                if rotate_all or page_num in pages:
                    page.rotate(angle)
                writer.add_page(page)
            out = self._resolve_output_pdf(path, output_str, f"_rot{angle}")
            try:
                out.relative_to(ROOT)
            except ValueError:
                return f"Ruta fuera del proyecto: {out}"
            with open(out, "wb") as f:
                writer.write(f)
            objetivo = "todas las paginas" if rotate_all else f"{len(pages)} paginas"
            return {
                "thought": f"Rotadas {objetivo} {angle} grados",
                "display": f"PDF rotado: {out.name}\n({objetivo} a {angle} grados)",
                "voice": f"Listo. Rote {objetivo}.",
            }
        except Exception as e:
            return f"Error: {e}"

    # ─── IMAGENES ────────────────────────────────────────────────────────

    def _resolve_output_image(self, original_path, output_str, suffix=""):
        if output_str:
            out = Path(output_str.strip().strip('"').strip("'"))
            if not out.is_absolute():
                out = ROOT / out
            if not out.suffix:
                out = out.with_suffix(original_path.suffix)
            return out
        return original_path.with_name(f"{original_path.stem}{suffix}{original_path.suffix}")

    def _image_resize(self, path_str, width, height, output_str):
        if not HAS_PIL:
            return "Falta Pillow."
        path = self._resolve_path(path_str)
        if not path:
            return f"No encontre la imagen: {path_str}"
        if not width or not height:
            return "Necesito ancho y alto."
        try:
            img = Image.open(str(path))
            old_size = img.size
            img = img.resize((int(width), int(height)), Image.LANCZOS)
            out = self._resolve_output_image(path, output_str, f"_{width}x{height}")
            try:
                out.relative_to(ROOT)
            except ValueError:
                return f"Ruta fuera del proyecto: {out}"
            img.save(str(out))
            return {
                "thought": f"Redimensionada a {width}x{height}",
                "display": f"Imagen guardada: {out.name}\n({old_size[0]}x{old_size[1]} -> {width}x{height})",
                "voice": f"Listo. Cambie el tamano a {width} por {height}.",
            }
        except Exception as e:
            return f"Error: {e}"

    def _image_crop(self, path_str, box, output_str):
        if not HAS_PIL:
            return "Falta Pillow."
        path = self._resolve_path(path_str)
        if not path:
            return f"No encontre la imagen: {path_str}"
        if not box or len(box) != 4:
            return "Necesito box = [left, top, right, bottom]."
        try:
            img = Image.open(str(path))
            img = img.crop(tuple(int(x) for x in box))
            out = self._resolve_output_image(path, output_str, "_crop")
            try:
                out.relative_to(ROOT)
            except ValueError:
                return f"Ruta fuera del proyecto: {out}"
            img.save(str(out))
            return {
                "thought": f"Recortada a {img.size}",
                "display": f"Imagen recortada: {out.name}\n(nuevo tamano: {img.size[0]}x{img.size[1]})",
                "voice": "Listo. Recorte la imagen.",
            }
        except Exception as e:
            return f"Error: {e}"

    def _image_rotate(self, path_str, angle, output_str):
        if not HAS_PIL:
            return "Falta Pillow."
        path = self._resolve_path(path_str)
        if not path:
            return f"No encontre la imagen: {path_str}"
        try:
            img = Image.open(str(path))
            img = img.rotate(-int(angle), expand=True)
            out = self._resolve_output_image(path, output_str, f"_rot{angle}")
            try:
                out.relative_to(ROOT)
            except ValueError:
                return f"Ruta fuera del proyecto: {out}"
            img.save(str(out))
            return {
                "thought": f"Rotada {angle} grados",
                "display": f"Imagen rotada: {out.name}",
                "voice": f"Listo. Rote {angle} grados.",
            }
        except Exception as e:
            return f"Error: {e}"

    def _image_convert(self, path_str, formato, output_str):
        if not HAS_PIL:
            return "Falta Pillow."
        path = self._resolve_path(path_str)
        if not path:
            return f"No encontre la imagen: {path_str}"
        formato = formato.lower().lstrip(".")
        if formato == "jpg":
            formato = "jpeg"
        if formato not in ("png", "jpeg", "webp", "bmp", "gif"):
            return f"Formato no soportado: {formato}"
        try:
            img = Image.open(str(path))
            if formato == "jpeg" and img.mode in ("RGBA", "P"):
                img = img.convert("RGB")
            ext = ".jpg" if formato == "jpeg" else f".{formato}"
            if output_str:
                out = Path(output_str.strip().strip('"').strip("'"))
                if not out.is_absolute():
                    out = ROOT / out
                if not out.suffix:
                    out = out.with_suffix(ext)
            else:
                out = path.with_suffix(ext)
            try:
                out.relative_to(ROOT)
            except ValueError:
                return f"Ruta fuera del proyecto: {out}"
            img.save(str(out), format=formato.upper())
            return {
                "thought": f"Convertida a {formato}",
                "display": f"Imagen convertida: {out.name}",
                "voice": f"Listo. Converti a {formato}.",
            }
        except Exception as e:
            return f"Error: {e}"

    # ─── JSON ────────────────────────────────────────────────────────────

    def _ask_llm_for_json_ops(self, content_preview, instruction, file_type):
        """Pide al LLM las operaciones concretas para modificar el JSON/YAML."""
        prompt = f"""El usuario quiere modificar un archivo {file_type}.

Instruccion: "{instruction}"

Contenido actual:
---INICIO---
{content_preview[:2500]}
---FIN---

Devuelve un JSON con la lista de operaciones. Cada operacion debe tener:
- "op": "set" (cambiar/crear valor), "delete" (borrar clave)
- "path": lista de claves para llegar al valor. Ej: ["servidor", "puerto"]
- "value": el nuevo valor (solo para "set"). Puede ser string, number, bool, null o lista/dict simple.

Ejemplos:
- Cambiar "nombre" a "Juan": [{{"op": "set", "path": ["nombre"], "value": "Juan"}}]
- Cambiar "servidor.puerto" a 8080: [{{"op": "set", "path": ["servidor", "puerto"], "value": 8080}}]
- Borrar "debug": [{{"op": "delete", "path": ["debug"]}}]

REGLAS CRITICAS:
- SOLO haz las operaciones que el usuario pidio. NADA mas.
- Si el usuario pide UN cambio, devuelve EXACTAMENTE UNA operacion.
- Si el usuario pide cambiar el "nombre", NO cambies "puerto", "version" ni nada mas.
- Los valores van directos. Ejemplo correcto:
  [{{"op": "set", "path": ["nombre"], "value": "Juan"}}]
- Devuelve un ARRAY JSON, no un objeto. Ejemplo:
  [{{"op": "set", "path": ["nombre"], "value": "Juan"}}]
- NO envuelvas en {{"operations": [...]}}, solo el array directo.

Responde SOLO con el JSON."""

        try:
            resp = ollama.chat(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                options={"temperature": 0.1, "num_predict": 500},
                stream=False,
            )
            raw = resp["message"]["content"].strip()
            print(f"[EDIT] Respuesta LLM: {raw[:300]}")
            return self._parse_json(raw)
        except Exception as e:
            return {"error": str(e)}

    def _apply_json_ops(self, data, ops):
        """Aplica operaciones al dict/list de forma segura."""
        changed = 0
        for op in ops:
            path = op.get("path", [])
            if not isinstance(path, list) or not path:
                continue
            kind = op.get("op", "set")

            # Navegar al padre
            current = data
            ok = True
            for key in path[:-1]:
                if isinstance(current, dict) and key in current:
                    current = current[key]
                else:
                    ok = False
                    break

            if not ok:
                continue

            last_key = path[-1]

            if kind == "set":
                if isinstance(current, dict):
                    current[last_key] = op.get("value")
                    changed += 1
            elif kind == "delete":
                if isinstance(current, dict) and last_key in current:
                    del current[last_key]
                    changed += 1
        return changed

    def _json_modify(self, path_str, instruction, output_str):
        path = self._resolve_path(path_str)
        if not path:
            return f"No encontre el archivo: {path_str}"
        if path.suffix.lower() != ".json":
            return f"No es un .json: {path}"

        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception as e:
            return f"Error leyendo JSON: {e}"

        preview = json.dumps(data, indent=2, ensure_ascii=False)[:2500]
        print(f"[EDIT] Interpretando instruccion con {self.model}...")
        result = self._ask_llm_for_json_ops(preview, instruction, "JSON")
        if "error" in result:
            return f"Error LLM: {result['error']}"

        ops = result.get("operations", [])
        if not ops:
            return "El LLM no genero operaciones."

        preview_lines = [f"Operaciones ({len(ops)}):"]
        for o in ops[:10]:
            preview_lines.append(f"  {o.get('op')} {'/'.join(o.get('path', []))} = {o.get('value', '')}")
        print("\n[EDIT] " + "\n       ".join(preview_lines) + "\n")

        if not confirmation.require("edit", "modify", f"Modificar {path.name} con {len(ops)} operaciones"):
            return "Cancelado."

        try:
            total = self._apply_json_ops(data, ops)
            if total == 0:
                return "Ninguna operacion se aplico."

            out = self._resolve_output(path, output_str)
            try:
                out.relative_to(ROOT)
            except ValueError:
                return f"Ruta fuera del proyecto: {out}"
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
            return {
                "thought": f"{total} operaciones aplicadas al JSON",
                "display": f"JSON modificado: {out.name}\n({total} operaciones)",
                "voice": f"Listo. Modifique {path.name}.",
            }
        except Exception as e:
            return f"Error aplicando: {e}"

    # ─── YAML ────────────────────────────────────────────────────────────

    def _yaml_modify(self, path_str, instruction, output_str):
        path = self._resolve_path(path_str)
        if not path:
            return f"No encontre el archivo: {path_str}"
        if path.suffix.lower() not in (".yaml", ".yml"):
            return f"No es un YAML: {path}"

        try:
            import yaml
        except ImportError:
            return "Falta PyYAML. Ejecuta: pip install PyYAML"

        try:
            data = yaml.safe_load(path.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                return "El YAML no es un diccionario."
        except Exception as e:
            return f"Error leyendo YAML: {e}"

        preview = yaml.dump(data, allow_unicode=True)[:2500]
        print(f"[EDIT] Interpretando instruccion con {self.model}...")
        result = self._ask_llm_for_json_ops(preview, instruction, "YAML")
        if "error" in result:
            return f"Error LLM: {result['error']}"

        ops = result.get("operations", [])
        if not ops:
            return "El LLM no genero operaciones."

        if not confirmation.require("edit", "modify", f"Modificar {path.name} con {len(ops)} operaciones"):
            return "Cancelado."

        try:
            total = self._apply_json_ops(data, ops)
            if total == 0:
                return "Ninguna operacion se aplico."

            out = self._resolve_output(path, output_str)
            try:
                out.relative_to(ROOT)
            except ValueError:
                return f"Ruta fuera del proyecto: {out}"
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(yaml.dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8")
            return {
                "thought": f"{total} operaciones aplicadas al YAML",
                "display": f"YAML modificado: {out.name}\n({total} operaciones)",
                "voice": f"Listo. Modifique {path.name}.",
            }
        except Exception as e:
            return f"Error aplicando: {e}"

    # ─── CSV ─────────────────────────────────────────────────────────────

    def _csv_modify(self, path_str, instruction, output_str):
        path = self._resolve_path(path_str)
        if not path:
            return f"No encontre el archivo: {path_str}"
        if path.suffix.lower() != ".csv":
            return f"No es un .csv: {path}"

        try:
            import csv
            content = path.read_text(encoding="utf-8")
            rows = list(csv.reader(content.splitlines()))
            if not rows:
                return "El CSV esta vacio."
        except Exception as e:
            return f"Error leyendo CSV: {e}"

        header = rows[0] if rows else []
        preview = "\n".join([", ".join(r) for r in rows[:20]])[:2500]

        print(f"[EDIT] Interpretando instruccion con {self.model}...")

        prompt = f"""El usuario quiere modificar un CSV.

Instruccion: "{instruction}"

Columnas (primera fila): {header}
Contenido (primeras 20 filas):
---INICIO---
{preview}
---FIN---

Devuelve un JSON con la lista de operaciones. Cada operacion debe tener:
- "op": "set_column" (cambiar todos los valores de una columna), "set_cell" (cambiar una celda), "delete_row" (borrar fila por indice), "append_row" (añadir fila al final)
- "column": nombre de columna (para set_column)
- "row": numero de fila (para set_cell/delete_row, 1-based sin contar header)
- "value": valor o lista de valores

Ejemplos:
- Cambiar todos los precios a 100: [{{"op": "set_column", "column": "precio", "value": 100}}]
- Cambiar celda fila 3 de la columna nombre a Juan: [{{"op": "set_cell", "row": 3, "column": "nombre", "value": "Juan"}}]
- Borrar fila 5: [{{"op": "delete_row", "row": 5}}]
- Añadir fila: [{{"op": "append_row", "value": ["Juan", 30, "Madrid"]}}]

Responde SOLO con el JSON."""

        try:
            resp = ollama.chat(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                options={"temperature": 0.1, "num_predict": 500},
                stream=False,
            )
            result = self._parse_json(resp["message"]["content"].strip())
        except Exception as e:
            return f"Error LLM: {e}"

        if "error" in result:
            return f"Error LLM: {result['error']}"

        ops = result.get("operations", [])
        if not ops:
            return "El LLM no genero operaciones."

        preview_lines = [f"Operaciones ({len(ops)}):"]
        for o in ops[:10]:
            preview_lines.append(f"  {o.get('op')} {o.get('column', '')} {o.get('row', '')} = {o.get('value', '')}")
        print("\n[EDIT] " + "\n       ".join(preview_lines) + "\n")

        if not confirmation.require("edit", "modify", f"Modificar {path.name} con {len(ops)} operaciones"):
            return "Cancelado."

        try:
            col_idx = {name: i for i, name in enumerate(header)}
            changed = 0
            # Aplicar de atras hacia adelante para delete_row
            for op in sorted(ops, key=lambda o: -int(o.get("row", 0)) if o.get("op") == "delete_row" else 0):
                kind = op.get("op")

                if kind == "set_column":
                    col = op.get("column")
                    val = op.get("value")
                    if col in col_idx:
                        i = col_idx[col]
                        for r in rows[1:]:
                            if i < len(r):
                                r[i] = str(val)
                                changed += 1

                elif kind == "set_cell":
                    row_num = op.get("row", 0)
                    col = op.get("column")
                    val = op.get("value")
                    if col in col_idx and 1 <= row_num < len(rows):
                        i = col_idx[col]
                        r = rows[row_num]
                        if i < len(r):
                            r[i] = str(val)
                            changed += 1

                elif kind == "delete_row":
                    row_num = op.get("row", 0)
                    if 1 <= row_num < len(rows):
                        del rows[row_num]
                        changed += 1

                elif kind == "append_row":
                    val = op.get("value", [])
                    if isinstance(val, list):
                        rows.append([str(v) for v in val])
                        changed += 1

            if changed == 0:
                return "Ninguna operacion se aplico."

            out = self._resolve_output(path, output_str)
            try:
                out.relative_to(ROOT)
            except ValueError:
                return f"Ruta fuera del proyecto: {out}"
            out.parent.mkdir(parents=True, exist_ok=True)
            with open(out, "w", encoding="utf-8", newline="") as f:
                writer = csv.writer(f)
                writer.writerows(rows)
            return {
                "thought": f"{changed} cambios aplicados al CSV",
                "display": f"CSV modificado: {out.name}\n({changed} cambios)",
                "voice": f"Listo. Modifique {path.name}.",
            }
        except Exception as e:
            return f"Error aplicando: {e}"

    def _list_uploads(self):
        if not UPLOADS_DIR.exists():
            return "No hay carpeta de uploads todavia."

        files = [f for f in UPLOADS_DIR.iterdir() if f.is_file()]
        if not files:
            return "La carpeta sandbox/uploads/ esta vacia."

        files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
        lines = [f"Archivos en uploads ({len(files)}):"]
        for f in files[:15]:
            size_kb = f.stat().st_size // 1024
            lines.append(f"  - {f.name} ({size_kb} KB)")

        return {
            "thought": "",
            "display": "\n".join(lines),
            "voice": f"Tienes {len(files)} archivos en uploads.",
        }