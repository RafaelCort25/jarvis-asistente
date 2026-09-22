"""Skill de Office: Word (por ahora). Excel y PowerPoint vienen despues."""
import re
from pathlib import Path
from datetime import datetime

from docx import Document
from docx.shared import Pt, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from openpyxl import Workbook, load_workbook
from openpyxl.styles import Font, PatternFill, Alignment

from skills.base import Skill
from core.config_loader import CONFIG
from core import confirmation
import ollama

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DIR = ROOT / "sandbox" / "office"


class OfficeSkill(Skill):
    name = "office"
    description = "Crea y lee documentos Word (.docx)"

    def __init__(self):
        self.model = CONFIG["models"].get("default", "dolphin-directo")

    def run(self, action, params):
        if action == "create_doc":
            return self._create_doc(
                params.get("description", ""),
                params.get("path", ""),
                params.get("title", ""),
            )
        if action == "read_doc":
            return self._read_doc(params.get("path", ""))
        if action == "create_xlsx":
            return self._create_xlsx(
                params.get("description", ""),
                params.get("path", ""),
            )
        if action == "read_xlsx":
            return self._read_xlsx(params.get("path", ""))
        return f"Accion desconocida en office: {action}"

    # ─── HELPERS ─────────────────────────────────────────────────────────

    def _resolve_docx_path(self, path_str, description=""):
        """Resuelve el path del .docx. Si no se da path, genera uno."""
        if path_str:
            raw = path_str.strip().strip('"').strip("'")
            p = Path(raw)
            if not p.is_absolute():
                p = ROOT / p
            if not p.suffix:
                p = p.with_suffix(".docx")
            if p.suffix.lower() != ".docx":
                p = p.with_suffix(".docx")
        else:
            # Generar nombre a partir de la descripcion
            slug = re.sub(r'[^a-z0-9]+', '_', description.lower())[:40].strip("_")
            if not slug:
                slug = f"documento_{int(datetime.now().timestamp())}"
            p = DEFAULT_DIR / f"{slug}.docx"
        return p

    def _ask_llm(self, prompt, system=None):
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        try:
            response = ollama.chat(
                model=self.model,
                messages=messages,
                options={"temperature": 0.5},
            )
            return response["message"]["content"].strip()
        except Exception as e:
            return f"[ERROR LLM] {e}"

    def _parse_content(self, raw):
        """
        Convierte el texto del LLM en estructura:
        [{"type": "title"|"h1"|"h2"|"paragraph", "text": "..."}]
        El LLM devuelve markdown-like: # para H1, ## para H2, resto parrafos.
        """
        items = []
        for line in raw.split("\n"):
            line = line.rstrip()
            if not line.strip():
                continue
            if line.startswith("### "):
                items.append({"type": "h2", "text": line[4:].strip()})
            elif line.startswith("## "):
                items.append({"type": "h1", "text": line[3:].strip()})
            elif line.startswith("# "):
                items.append({"type": "title", "text": line[2:].strip()})
            elif line.startswith("- ") or line.startswith("* "):
                items.append({"type": "bullet", "text": line[2:].strip()})
            elif re.match(r'^\d+\.\s', line):
                items.append({"type": "numbered", "text": re.sub(r'^\d+\.\s', '', line)})
            else:
                items.append({"type": "paragraph", "text": line.strip()})
        return items

    # ─── CREATE DOC ──────────────────────────────────────────────────────

    def _create_doc(self, description, path_str, title):
        description = (description or "").strip()
        if not description:
            return "Dime sobre que quieres el documento."

        # 1. Generar contenido
        print(f"[OFFICE] Generando contenido con {self.model}...")
        prompt = f"""Escribe el contenido de un documento sobre el siguiente tema:

{description}

Formato:
- Empieza con un titulo usando "# Titulo del documento"
- Usa "## Subtitulo" para secciones principales
- Usa "### Sub-subtitulo" si necesitas mas detalle
- Los parrafos van en texto normal (una linea por parrafo)
- Puedes usar "- " para bullets y "1. " para listas numeradas
- Se claro, estructurado y util

NO incluyas explicaciones fuera del contenido. Empieza directamente con el titulo.
NO uses bloques de codigo ni backticks."""

        raw = self._ask_llm(prompt, system="Eres un redactor profesional en espanol. Escribes documentos claros y bien estructurados.")
        if not raw or raw.startswith("[ERROR LLM]"):
            return f"Error generando contenido: {raw}"

        items = self._parse_content(raw)
        if not items:
            return "No pude estructurar el contenido."

        # 2. Resolver path
        path = self._resolve_docx_path(path_str, description)

        # Bloquear fuera del proyecto
        try:
            path.relative_to(ROOT)
        except ValueError:
            return f"Ruta fuera del proyecto, bloqueado: {path}"

        # 3. Preview + confirmacion
        preview_lines = []
        for it in items[:12]:
            prefix = {"title": "# ", "h1": "## ", "h2": "### ", "bullet": "  - ", "numbered": "  N. ", "paragraph": "  "}[it["type"]]
            preview_lines.append(f"{prefix}{it['text'][:80]}")
        preview = "\n".join(preview_lines)
        if len(items) > 12:
            preview += f"\n... (+{len(items)-12} lineas)"

        print(f"\n[OFFICE] Documento propuesto ({len(items)} elementos):\n")
        print(preview)
        print()

        summary = f"Crear documento Word en {path.name} con {len(items)} elementos"
        if not confirmation.require("office", "create_doc", summary):
            return "Cancelado."

        # 4. Construir el .docx
        try:
            doc = Document()

            # Estilo base
            style = doc.styles["Normal"]
            style.font.name = "Calibri"
            style.font.size = Pt(11)

            for it in items:
                t = it["type"]
                text = it["text"]

                if t == "title":
                    h = doc.add_heading(text, level=0)
                    h.alignment = WD_ALIGN_PARAGRAPH.CENTER
                elif t == "h1":
                    doc.add_heading(text, level=1)
                elif t == "h2":
                    doc.add_heading(text, level=2)
                elif t == "bullet":
                    doc.add_paragraph(text, style="List Bullet")
                elif t == "numbered":
                    doc.add_paragraph(text, style="List Number")
                else:
                    doc.add_paragraph(text)

            path.parent.mkdir(parents=True, exist_ok=True)
            doc.save(str(path))
        except Exception as e:
            return f"Error creando documento: {e}"

        print(f"[OFFICE] Documento guardado: {path}")

        return {
            "thought": f"Documento Word creado con {len(items)} elementos",
            "display": f"Documento Word creado: {path}\n({len(items)} elementos, {path.stat().st_size} bytes)",
            "voice": f"Listo. Documento guardado en {path.name}.",
        }

    # ─── READ DOC ────────────────────────────────────────────────────────

    def _read_doc(self, path_str):
        if not path_str:
            return "Necesito el path del documento."

        raw = path_str.strip().strip('"').strip("'")
        path = Path(raw)
        if not path.is_absolute():
            path = ROOT / path

        if not path.exists():
            return f"No encontre el documento: {path}"
        if path.suffix.lower() != ".docx":
            return f"No es un .docx: {path}"

        try:
            doc = Document(str(path))
        except Exception as e:
            return f"Error leyendo documento: {e}"

        paragraphs = [p.text.strip() for p in doc.paragraphs if p.text.strip()]
        if not paragraphs:
            return f"El documento {path.name} esta vacio."

        # Limitar para no reventar TTS
        preview = "\n".join(paragraphs[:30])
        if len(paragraphs) > 30:
            preview += f"\n... (+{len(paragraphs)-30} parrafos mas)"

        return {
            "thought": f"Leyendo {path.name}",
            "display": f"Contenido de {path.name}:\n\n{preview}",
            "voice": f"El documento {path.name} tiene {len(paragraphs)} parrafos.",
        }
        # ─── CREATE XLSX ─────────────────────────────────────────────────────

    def _resolve_xlsx_path(self, path_str, description=""):
        if path_str:
            raw = path_str.strip().strip('"').strip("'")
            p = Path(raw)
            if not p.is_absolute():
                p = ROOT / p
            if p.suffix.lower() != ".xlsx":
                p = p.with_suffix(".xlsx")
        else:
            slug = re.sub(r'[^a-z0-9]+', '_', description.lower())[:60].strip("_")
            if not slug:
                slug = f"hoja_{int(datetime.now().timestamp())}"
            p = DEFAULT_DIR / f"{slug}.xlsx"
        return p

    def _create_xlsx(self, description, path_str):
        description = (description or "").strip()
        if not description:
            return "Dime que datos quieres en el Excel."

        print(f"[OFFICE] Generando hoja de calculo con {self.model}...")
        prompt = f"""Genera una hoja de calculo para lo siguiente:

{description}

Formato de respuesta OBLIGATORIO:
- Primera linea: nombres de columnas separados por "|"
- Siguientes lineas: filas de datos separadas por "|"
- NO uses comas como separador, usa "|"
- NO incluyas encabezados, ni markdown, ni explicaciones
- Solo la tabla cruda
- Maximo 30 filas de datos

Ejemplo:
Producto|Precio|Cantidad
Manzana|1.50|100
Naranja|2.00|80"""

        raw = self._ask_llm(prompt, system="Eres un experto en hojas de calculo. Devuelves solo tablas en formato pipe-separated.")
        if not raw or raw.startswith("[ERROR LLM]"):
            return f"Error generando datos: {raw}"

        lines = [l.strip() for l in raw.split("\n") if l.strip() and "|" in l]
        if len(lines) < 2:
            return "El modelo no genero una tabla valida."

        rows = []
        for line in lines:
            line = re.sub(r'^\|', '', line)
            line = re.sub(r'\|$', '', line)
            cells = [c.strip().strip("`*") for c in line.split("|")]

            # Filtrar lineas separadoras de markdown (--- | --- | ---)
            if all(re.fullmatch(r'-{2,}', c) or c == "" for c in cells):
                continue

            rows.append(cells)

        if len(rows) < 2:
            return "Solo hay encabezado, sin datos."

        header = rows[0]
        data_rows = rows[1:31]

        path = self._resolve_xlsx_path(path_str, description)
        try:
            path.relative_to(ROOT)
        except ValueError:
            return f"Ruta fuera del proyecto, bloqueado: {path}"

        preview_lines = [f"Columnas: {' | '.join(header)}"]
        preview_lines.append(f"Filas: {len(data_rows)}")
        preview_lines.append("")
        preview_lines.append("Primeras filas:")
        for r in data_rows[:5]:
            preview_lines.append("  " + " | ".join(r))
        if len(data_rows) > 5:
            preview_lines.append(f"  ... (+{len(data_rows)-5} filas)")
        print(f"\n[OFFICE] Hoja propuesta:\n")
        print("\n".join(preview_lines))
        print()

        summary = f"Crear Excel en {path.name} con {len(data_rows)} filas y {len(header)} columnas"
        if not confirmation.require("office", "create_xlsx", summary):
            return "Cancelado."

        try:
            wb = Workbook()
            ws = wb.active
            ws.title = "Datos"

            ws.append(header)
            header_fill = PatternFill(start_color="4472C4", end_color="4472C4", fill_type="solid")
            header_font = Font(bold=True, color="FFFFFF")
            for cell in ws[1]:
                cell.fill = header_fill
                cell.font = header_font
                cell.alignment = Alignment(horizontal="center")

            for row in data_rows:
                converted = []
                for c in row:
                    try:
                        if "." in c:
                            converted.append(float(c))
                        else:
                            converted.append(int(c))
                    except (ValueError, TypeError):
                        converted.append(c)
                ws.append(converted)

            for i, col in enumerate(ws.columns, 1):
                max_len = 0
                for cell in col:
                    if cell.value is not None:
                        max_len = max(max_len, len(str(cell.value)))
                ws.column_dimensions[chr(64 + i)].width = min(max_len + 3, 40)

            path.parent.mkdir(parents=True, exist_ok=True)
            wb.save(str(path))
        except Exception as e:
            return f"Error creando Excel: {e}"

        print(f"[OFFICE] Excel guardado: {path}")

        return {
            "thought": f"Excel creado con {len(data_rows)} filas",
            "display": f"Excel creado: {path}\n({len(data_rows)} filas, {len(header)} columnas, {path.stat().st_size} bytes)",
            "voice": f"Listo. Excel guardado en {path.name} con {len(data_rows)} filas.",
        }

    # ─── READ XLSX ───────────────────────────────────────────────────────

    def _read_xlsx(self, path_str):
        if not path_str:
            return "Necesito el path del Excel."

        raw = path_str.strip().strip('"').strip("'")
        path = Path(raw)
        if not path.is_absolute():
            path = ROOT / path

        if not path.exists():
            return f"No encontre el Excel: {path}"
        if path.suffix.lower() not in (".xlsx", ".xlsm"):
            return f"No es un Excel: {path}"

        try:
            wb = load_workbook(str(path), read_only=True, data_only=True)
        except Exception as e:
            return f"Error leyendo Excel: {e}"

        lines = []
        sheet_names = list(wb.sheetnames)
        for sheet_name in sheet_names[:3]:
            ws = wb[sheet_name]
            lines.append(f"\n=== Hoja: {sheet_name} ===")
            rows_read = 0
            for row in ws.iter_rows(values_only=True):
                if all(c is None for c in row):
                    continue
                cells = [str(c) if c is not None else "" for c in row]
                lines.append(" | ".join(cells))
                rows_read += 1
                if rows_read >= 20:
                    lines.append("... (hoja truncada a 20 filas)")
                    break

        wb.close()

        if not lines:
            return f"El Excel {path.name} esta vacio."

        return {
            "thought": f"Leyendo Excel {path.name}",
            "display": f"Contenido de {path.name}:\n{''.join(lines)}",
            "voice": f"El Excel {path.name} tiene {len(sheet_names)} hojas.",
        }