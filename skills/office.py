"""Skill de Office: Word, Excel y PowerPoint.

Fase 1: tablas + negrita/cursiva + portada/indice en Word.
        formulas + formato condicional + freeze panes en Excel.
Fase 2: graficos, imagenes, layouts avanzados.
"""
import re
from pathlib import Path
from datetime import datetime

from docx import Document
from docx.shared import Pt, RGBColor, Inches
from docx.enum.text import WD_ALIGN_PARAGRAPH
from openpyxl import Workbook, load_workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter
from openpyxl.formatting.rule import ColorScaleRule
from pptx import Presentation
from pptx.util import Inches as PptxInches, Pt as PptxPt
from pptx.dml.color import RGBColor as PptxRGB

from skills.base import Skill
from core.config_loader import CONFIG
from core import confirmation
import ollama

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DIR = ROOT / "sandbox" / "office"


class OfficeSkill(Skill):
    name = "office"
    description = "Crea y lee documentos Word, Excel y PowerPoint"

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
        if action == "create_ppt":
            return self._create_ppt(
                params.get("description", ""),
                params.get("path", ""),
            )
        if action == "read_ppt":
            return self._read_ppt(params.get("path", ""))
        return f"Accion desconocida en office: {action}"

    # ─── HELPERS COMUNES ─────────────────────────────────────────────────

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
                stream=False,
            )
            return response["message"]["content"].strip()
        except Exception as e:
            return f"[ERROR LLM] {e}"

    # ─── WORD: PARSEO AVANZADO ───────────────────────────────────────────

    def _parse_content(self, raw):
        """Convierte markdown-like en estructura:
        - title, h1, h2: titulos
        - paragraph: parrafo normal
        - bullet, numbered: listas
        - table: tabla (rows)
        """
        items = []
        lines = raw.split("\n")
        i = 0
        while i < len(lines):
            line = lines[i].rstrip()

            if not line.strip():
                i += 1
                continue

            # ── Tabla: lineas consecutivas con | ──
            if "|" in line and line.strip().startswith("|"):
                tabla_lines = []
                while i < len(lines) and "|" in lines[i]:
                    tabla_lines.append(lines[i])
                    i += 1
                # Parsear tabla
                rows = []
                for tl in tabla_lines:
                    tl = tl.strip()
                    if tl.startswith("|"):
                        tl = tl[1:]
                    if tl.endswith("|"):
                        tl = tl[:-1]
                    cells = [c.strip() for c in tl.split("|")]
                    # Filtrar lineas separadoras de markdown (---|---)
                    if all(re.fullmatch(r'-{2,}', c) or c == "" for c in cells):
                        continue
                    rows.append(cells)
                if rows:
                    items.append({"type": "table", "rows": rows})
                continue

            # ── Titulos ──
            if line.startswith("### "):
                items.append({"type": "h2", "text": line[4:].strip()})
            elif line.startswith("## "):
                items.append({"type": "h1", "text": line[3:].strip()})
            elif line.startswith("# "):
                items.append({"type": "title", "text": line[2:].strip()})
            # ── Listas ──
            elif line.startswith("- ") or line.startswith("* "):
                items.append({"type": "bullet", "text": line[2:].strip()})
            elif re.match(r'^\d+\.\s', line):
                items.append({"type": "numbered", "text": re.sub(r'^\d+\.\s', '', line)})
            # ── Cita ──
            elif line.startswith("> "):
                items.append({"type": "quote", "text": line[2:].strip()})
            # ── Imagen: ![alt](ruta) ──
            elif re.match(r'^!\[.*?\]\(.+?\)', line):
                m = re.match(r'^!\[(.*?)\]\((.+?)\)', line)
                items.append({"type": "image", "alt": m.group(1), "path": m.group(2)})
            # ── Parrafo normal ──
            else:
                items.append({"type": "paragraph", "text": line.strip()})

            i += 1
        return items

    def _add_runs_with_format(self, paragraph, text):
        """Anade runs a un parrafo procesando **bold** y *italic*."""
        # Regex que captura **bold** o *italic* o texto normal
        parts = re.split(r'(\*\*[^*]+\*\*|\*[^*]+\*)', text)
        for part in parts:
            if not part:
                continue
            if part.startswith("**") and part.endswith("**"):
                run = paragraph.add_run(part[2:-2])
                run.bold = True
            elif part.startswith("*") and part.endswith("*"):
                run = paragraph.add_run(part[1:-1])
                run.italic = True
            else:
                paragraph.add_run(part)

    def _add_table(self, doc, rows):
        """Anade una tabla de Word. Defensivo contra datos raros."""
        if not rows:
            return
        # Sanitizar: cada fila debe ser una lista de strings
        rows_clean = []
        for r in rows:
            if isinstance(r, str):
                # Si es un string (raro), convertirlo en una celda
                rows_clean.append([r])
            elif isinstance(r, (list, tuple)):
                fila = []
                for cell in r:
                    if cell is None:
                        fila.append("")
                    elif isinstance(cell, str):
                        fila.append(cell)
                    else:
                        fila.append(str(cell))
                rows_clean.append(fila)
            else:
                rows_clean.append([str(r)])

        if not rows_clean:
            return

        n_cols = max(len(r) for r in rows_clean)
        if n_cols == 0:
            return

        # Rellenar filas con columnas faltantes
        for r in rows_clean:
            while len(r) < n_cols:
                r.append("")

        try:
            table = doc.add_table(rows=len(rows_clean), cols=n_cols)
            table.style = "Light Grid Accent 1"
            for i, row in enumerate(rows_clean):
                for j, cell_text in enumerate(row):
                    cell = table.cell(i, j)
                    cell.text = cell_text
                    # Primera fila en negrita
                    if i == 0:
                        for para in cell.paragraphs:
                            for run in para.runs:
                                run.bold = True
            doc.add_paragraph("")  # Espacio despues de la tabla
        except Exception as e:
            print(f"[OFFICE] Error anadiendo tabla: {e}")
            # Fallback: como texto plano
            for row in rows_clean:
                doc.add_paragraph(" | ".join(row))

    def _resolve_docx_path(self, path_str, description=""):
        if path_str:
            raw = path_str.strip().strip('"').strip("'")
            p = Path(raw)
            if not p.is_absolute():
                p = ROOT / p
            if p.suffix.lower() != ".docx":
                p = p.with_suffix(".docx")
        else:
            slug = re.sub(r'[^a-z0-9]+', '_', description.lower())[:40].strip("_")
            if not slug:
                slug = f"documento_{int(datetime.now().timestamp())}"
            p = DEFAULT_DIR / f"{slug}.docx"
        return p

    def _create_doc(self, description, path_str, title):
        description = (description or "").strip()
        if not description:
            return "Dime sobre que quieres el documento."

        print(f"[OFFICE] Generando contenido con {self.model}...")
        prompt = f"""Escribe el contenido de un documento sobre el siguiente tema:

{description}

Formato:
- Empieza con un titulo usando "# Titulo del documento"
- Usa "## Subtitulo" para secciones principales
- Usa "### Sub-subtitulo" si necesitas mas detalle
- Los parrafos van en texto normal (una linea por parrafo)
- Puedes usar "- " para bullets y "1. " para listas numeradas
- Puedes usar **negrita** y *cursiva* dentro del texto
- Puedes incluir tablas en formato markdown: | Col1 | Col2 | con filas debajo
- Puedes usar "> " para citas destacadas
- Se claro, estructurado y util

Si el tema lo amerita, incluye al menos una tabla comparativa o de datos.
NO incluyas explicaciones fuera del contenido. Empieza directamente con el titulo.
NO uses bloques de codigo ni backticks."""

        raw = self._ask_llm(
            prompt,
            system="Eres un redactor profesional en espanol. Escribes documentos claros, bien estructurados y utiles.",
        )
        if not raw or raw.startswith("[ERROR LLM]"):
            return f"Error generando contenido: {raw}"

        items = self._parse_content(raw)
        if not items:
            return "No pude estructurar el contenido."

        path = self._resolve_docx_path(path_str, description)
        try:
            path.relative_to(ROOT)
        except ValueError:
            return f"Ruta fuera del proyecto, bloqueado: {path}"

        # Preview
        preview_lines = []
        for it in items[:12]:
            t = it["type"]
            if t == "table":
                preview_lines.append(f"  [TABLA {len(it['rows'])}x{len(it['rows'][0])}]")
            elif t == "image":
                preview_lines.append(f"  [IMAGEN: {it.get('path', '')}]")
            elif t == "title":
                preview_lines.append(f"# {it['text'][:80]}")
            elif t == "h1":
                preview_lines.append(f"## {it['text'][:80]}")
            elif t == "h2":
                preview_lines.append(f"### {it['text'][:80]}")
            elif t == "bullet":
                preview_lines.append(f"  - {it['text'][:80]}")
            elif t == "numbered":
                preview_lines.append(f"  N. {it['text'][:80]}")
            elif t == "quote":
                preview_lines.append(f"  > {it['text'][:80]}")
            else:
                preview_lines.append(f"  {it['text'][:80]}")
        preview = "\n".join(preview_lines)
        if len(items) > 12:
            preview += f"\n... (+{len(items)-12} elementos)"

        print(f"\n[OFFICE] Documento propuesto ({len(items)} elementos):\n")
        print(preview)
        print()

        summary = f"Crear documento Word en {path.name} con {len(items)} elementos"
        if not confirmation.require("office", "create_doc", summary):
            return "Cancelado."

        # Construir el .docx
        try:
            doc = Document()

            style = doc.styles["Normal"]
            style.font.name = "Calibri"
            style.font.size = Pt(11)

            # Si hay > 20 elementos, anadir indice al inicio
            tiene_titulo = any(it["type"] == "title" for it in items)
            n_secciones = sum(1 for it in items if it["type"] in ("h1", "h2"))

            # Portada si hay muchos elementos
            if len(items) > 20 and tiene_titulo:
                # Encontrar el titulo
                titulo = next((it["text"] for it in items if it["type"] == "title"), description[:80])
                # Portada
                h = doc.add_heading(titulo, level=0)
                h.alignment = WD_ALIGN_PARAGRAPH.CENTER
                sub = doc.add_paragraph()
                sub.alignment = WD_ALIGN_PARAGRAPH.CENTER
                run = sub.add_run(f"Generado por Senna\n{datetime.now().strftime('%d/%m/%Y')}")
                run.italic = True
                run.font.color.rgb = RGBColor(120, 120, 120)
                # Salto de pagina
                doc.add_page_break()

            # Indice si hay >= 3 secciones
            if n_secciones >= 3:
                doc.add_heading("Indice", level=1)
                for it in items:
                    if it["type"] == "h1":
                        p = doc.add_paragraph(it["text"], style="List Number")
                    elif it["type"] == "h2":
                        p = doc.add_paragraph("    " + it["text"], style="List Bullet")
                doc.add_page_break()

            # Contenido
            for it in items:
                t = it["type"]

                if t == "title":
                    # Si ya pusimos portada, no duplicar
                    if len(items) > 20 and tiene_titulo:
                        continue
                    h = doc.add_heading(it["text"], level=0)
                    h.alignment = WD_ALIGN_PARAGRAPH.CENTER
                elif t == "h1":
                    doc.add_heading(it["text"], level=1)
                elif t == "h2":
                    doc.add_heading(it["text"], level=2)
                elif t == "bullet":
                    p = doc.add_paragraph(style="List Bullet")
                    self._add_runs_with_format(p, it["text"])
                elif t == "numbered":
                    p = doc.add_paragraph(style="List Number")
                    self._add_runs_with_format(p, it["text"])
                elif t == "quote":
                    p = doc.add_paragraph(style="Intense Quote")
                    self._add_runs_with_format(p, it["text"])
                elif t == "table":
                    self._add_table(doc, it["rows"])
                elif t == "image":
                    try:
                        img_path = Path(it["path"])
                        if not img_path.is_absolute():
                            img_path = ROOT / img_path
                        if img_path.exists():
                            doc.add_picture(str(img_path), width=Inches(5))
                            doc.add_paragraph("")
                    except Exception as e:
                        print(f"[OFFICE] No se pudo anadir imagen: {e}")
                else:  # paragraph
                    p = doc.add_paragraph()
                    self._add_runs_with_format(p, it["text"])

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
        # Leer tablas tambien
        tablas_txt = []
        for i, tabla in enumerate(doc.tables, 1):
            tablas_txt.append(f"\n--- Tabla {i} ---")
            for row in tabla.rows:
                cells = [c.text.strip() for c in row.cells]
                tablas_txt.append(" | ".join(cells))

        if not paragraphs and not tablas_txt:
            return f"El documento {path.name} esta vacio."

        preview = "\n".join(paragraphs[:30])
        if len(paragraphs) > 30:
            preview += f"\n... (+{len(paragraphs)-30} parrafos mas)"
        if tablas_txt:
            preview += "\n" + "\n".join(tablas_txt[:20])

        return {
            "thought": f"Leyendo {path.name}",
            "display": f"Contenido de {path.name}:\n\n{preview}",
            "voice": f"El documento {path.name} tiene {len(paragraphs)} parrafos y {len(doc.tables)} tablas.",
        }

    # ─── EXCEL ───────────────────────────────────────────────────────────

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
- Si tiene sentido, anade una columna con numeros para que se pueda sumar

Ejemplo:
Producto|Precio|Cantidad
Manzana|1.50|100
Naranja|2.00|80"""

        raw = self._ask_llm(
            prompt,
            system="Eres un experto en hojas de calculo. Devuelves solo tablas en formato pipe-separated.",
        )
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

        summary = f"Crear Excel en {path.name} con {len(data_rows)} filas y {len(header)} columnas"
        if not confirmation.require("office", "create_xlsx", summary):
            return "Cancelado."

        try:
            wb = Workbook()
            ws = wb.active
            ws.title = "Datos"

            ws.append(header)
            header_fill = PatternFill(start_color="4472C4", end_color="4472C4", fill_type="solid")
            header_font = Font(bold=True, color="FFFFFF", size=11)
            thin = Side(border_style="thin", color="CCCCCC")
            border = Border(left=thin, right=thin, top=thin, bottom=thin)
            for cell in ws[1]:
                cell.fill = header_fill
                cell.font = header_font
                cell.alignment = Alignment(horizontal="center", vertical="center")
                cell.border = border

            # Detectar columnas numericas para auto-formula
            numeric_cols = set()
            for j in range(len(header)):
                is_numeric = True
                for r in data_rows:
                    if j >= len(r):
                        continue
                    val = r[j]
                    try:
                        float(val)
                    except (ValueError, TypeError):
                        is_numeric = False
                        break
                if is_numeric and len(data_rows) > 0:
                    numeric_cols.add(j)

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

            # Aplicar bordes a datos
            for row in ws.iter_rows(min_row=2, max_row=1+len(data_rows)):
                for cell in row:
                    cell.border = border

            # Ancho automatico de columnas
            for i, col in enumerate(ws.columns, 1):
                max_len = 0
                for cell in col:
                    if cell.value is not None:
                        max_len = max(max_len, len(str(cell.value)))
                ws.column_dimensions[get_column_letter(i)].width = min(max_len + 3, 40)

            # Freeze panes (congelar encabezado)
            ws.freeze_panes = "A2"

            # Auto-filter
            ws.auto_filter.ref = ws.dimensions

            # Formula SUMA para columnas numericas
            if numeric_cols and len(data_rows) > 0:
                last_row = len(data_rows) + 1
                sum_row = last_row + 1
                # Celda etiqueta
                ws.cell(row=sum_row, column=1, value="TOTAL").font = Font(bold=True)
                for j in numeric_cols:
                    col_letter = get_column_letter(j + 1)
                    formula = f"=SUM({col_letter}2:{col_letter}{last_row})"
                    cell = ws.cell(row=sum_row, column=j + 1, value=formula)
                    cell.font = Font(bold=True)
                    cell.fill = PatternFill(start_color="FFF2CC", end_color="FFF2CC", fill_type="solid")

            # Formato condicional: color scale en columnas numericas
            for j in numeric_cols:
                col_letter = get_column_letter(j + 1)
                rango = f"{col_letter}2:{col_letter}{len(data_rows)+1}"
                ws.conditional_formatting.add(
                    rango,
                    ColorScaleRule(
                        start_type="min", start_color="F8696B",
                        mid_type="percentile", mid_value=50, mid_color="FFEB84",
                        end_type="max", end_color="63BE7B",
                    ),
                )

            path.parent.mkdir(parents=True, exist_ok=True)
            wb.save(str(path))
        except Exception as e:
            return f"Error creando Excel: {e}"

        print(f"[OFFICE] Excel guardado: {path}")

        extras = []
        if numeric_cols:
            extras.append(f"{len(numeric_cols)} columnas con SUMA automatica")
        extras.append("freeze panes")
        extras.append("auto-filter")
        extras.append("formato condicional")
        extras_txt = ", ".join(extras)

        return {
            "thought": f"Excel creado con {len(data_rows)} filas, {extras_txt}",
            "display": f"Excel creado: {path}\n({len(data_rows)} filas, {len(header)} columnas, con {extras_txt})",
            "voice": f"Listo. Excel guardado con {len(data_rows)} filas.",
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

    # ─── POWERPOINT (dejamos lo existente por ahora) ─────────────────────

    def _resolve_pptx_path(self, path_str, description=""):
        if path_str:
            raw = path_str.strip().strip('"').strip("'")
            p = Path(raw)
            if not p.is_absolute():
                p = ROOT / p
            if p.suffix.lower() != ".pptx":
                p = p.with_suffix(".pptx")
        else:
            slug = re.sub(r'[^a-z0-9]+', '_', description.lower())[:60].strip("_")
            if not slug:
                slug = f"presentacion_{int(datetime.now().timestamp())}"
            p = DEFAULT_DIR / f"{slug}.pptx"
        return p

    def _ask_llm_slides(self, description):
        prompt = f"""Genera la estructura de una presentacion sobre:

{description}

Formato OBLIGATORIO (una linea por elemento):
TITULO: <titulo de la portada>
SLIDE: <titulo de diapositiva>
- <bullet 1>
- <bullet 2>
- <bullet 3>
SLIDE: <siguiente titulo>
- <bullet 1>
- <bullet 2>

Reglas:
- Entre 5 y 10 diapositivas
- Cada diapositiva: 3-5 bullets maximo
- Bullets cortos (max 12 palabras cada uno)
- NO incluyas explicaciones fuera de esta estructura
- Empieza directamente con TITULO:
- NO uses markdown, NO uses #, solo el formato indicado"""

        return self._ask_llm(
            prompt,
            system="Eres un disenador de presentaciones. Estructuras contenido claro y visual.",
        )

    def _parse_slides(self, raw):
        slides = []
        current = None
        title_overall = None

        for line in raw.split("\n"):
            line = line.rstrip()
            if not line.strip():
                continue

            if line.startswith("TITULO:"):
                title_overall = line[7:].strip()
            elif line.startswith("SLIDE:"):
                if current:
                    slides.append(current)
                current = {"title": line[6:].strip(), "bullets": []}
            elif line.startswith("- ") and current:
                current["bullets"].append(line[2:].strip())

        if current:
            slides.append(current)

        return title_overall, slides

    def _create_ppt(self, description, path_str):
        description = (description or "").strip()
        if not description:
            return "Dime sobre que quieres la presentacion."

        print(f"[OFFICE] Generando presentacion con {self.model}...")
        raw = self._ask_llm_slides(description)
        if not raw or raw.startswith("[ERROR LLM]"):
            return f"Error generando contenido: {raw}"

        title_overall, slides = self._parse_slides(raw)
        if not title_overall:
            title_overall = description[:80]
        if not slides:
            return "El modelo no genero diapositivas validas."

        path = self._resolve_pptx_path(path_str, description)
        try:
            path.relative_to(ROOT)
        except ValueError:
            return f"Ruta fuera del proyecto, bloqueado: {path}"

        summary = f"Crear PowerPoint en {path.name} con {len(slides)+1} diapositivas"
        if not confirmation.require("office", "create_ppt", summary):
            return "Cancelado."

        try:
            prs = Presentation()
            prs.slide_width = PptxInches(13.333)
            prs.slide_height = PptxInches(7.5)

            slide = prs.slides.add_slide(prs.slide_layouts[0])
            slide.shapes.title.text = title_overall
            if len(slide.placeholders) > 1:
                slide.placeholders[1].text = "Generado por Senna"

            for s in slides:
                slide = prs.slides.add_slide(prs.slide_layouts[1])
                slide.shapes.title.text = s["title"]
                body = slide.placeholders[1]
                tf = body.text_frame
                if s["bullets"]:
                    tf.text = s["bullets"][0]
                    for b in s["bullets"][1:]:
                        p = tf.add_paragraph()
                        p.text = b

            path.parent.mkdir(parents=True, exist_ok=True)
            prs.save(str(path))
        except Exception as e:
            return f"Error creando PPTX: {e}"

        print(f"[OFFICE] Presentacion guardada: {path}")

        return {
            "thought": f"Presentacion creada con {len(slides)+1} slides",
            "display": f"Presentacion creada: {path}\n({len(slides)+1} diapositivas, {path.stat().st_size} bytes)",
            "voice": f"Listo. Presentacion guardada en {path.name} con {len(slides)+1} diapositivas.",
        }

    def _read_ppt(self, path_str):
        if not path_str:
            return "Necesito el path de la presentacion."

        raw = path_str.strip().strip('"').strip("'")
        path = Path(raw)
        if not path.is_absolute():
            path = ROOT / path

        if not path.exists():
            return f"No encontre la presentacion: {path}"
        if path.suffix.lower() != ".pptx":
            return f"No es un PPTX: {path}"

        try:
            prs = Presentation(str(path))
        except Exception as e:
            return f"Error leyendo PPTX: {e}"

        lines = []
        n_slides = len(prs.slides)
        for i, slide in enumerate(prs.slides, 1):
            lines.append(f"\n--- Slide {i} ---")
            for shape in slide.shapes:
                if shape.has_text_frame:
                    for para in shape.text_frame.paragraphs:
                        txt = para.text.strip()
                        if txt:
                            lines.append(txt)
            if len(lines) > 40:
                lines.append("... (presentacion truncada)")
                break

        return {
            "thought": f"Leyendo PPTX {path.name}",
            "display": f"Contenido de {path.name}:\n{''.join(lines)}",
            "voice": f"La presentacion {path.name} tiene {n_slides} diapositivas.",
        }