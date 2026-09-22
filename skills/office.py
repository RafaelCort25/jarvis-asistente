"""Skill de Office: Word (por ahora). Excel y PowerPoint vienen despues."""
import re
from pathlib import Path
from datetime import datetime

from docx import Document
from docx.shared import Pt, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH

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