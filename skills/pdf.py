"""Skill de PDF: convierte Word (.docx) a PDF."""
import shutil
import subprocess
from pathlib import Path

from skills.base import Skill
from core import confirmation

ROOT = Path(__file__).resolve().parent.parent
SANDBOX_DIR = ROOT / "sandbox"
OFFICE_DIR = SANDBOX_DIR / "office"


class PdfSkill(Skill):
    name = "pdf"
    description = "Convierte documentos Word a PDF"

    def run(self, action, params):
        if action == "from_docx":
            return self._from_docx(
                params.get("path", ""),
                params.get("output", ""),
            )
        if action == "list":
            return self._list()
        return f"Accion desconocida en pdf: {action}"

    # ─── HELPERS ─────────────────────────────────────────────────────────

    def _resolve_path(self, path_str, must_exist=True):
        if not path_str:
            return None
        raw = path_str.strip().strip('"').strip("'")
        p = Path(raw)
        if not p.is_absolute():
            p = ROOT / p
        if must_exist and not p.exists():
            return None
        return p

    def _latest_docx(self):
        """Devuelve el .docx mas reciente de sandbox/office/."""
        if not OFFICE_DIR.exists():
            return None
        docxs = list(OFFICE_DIR.glob("*.docx"))
        if not docxs:
            return None
        return max(docxs, key=lambda p: p.stat().st_mtime)

    def _find_soffice(self):
        from core.paths import SOFFICE_CMD
        if SOFFICE_CMD and Path(SOFFICE_CMD).exists():
            return SOFFICE_CMD
        return shutil.which("soffice")

    # ─── CONVERT DOCX → PDF ──────────────────────────────────────────────

    def _from_docx(self, path_str, output_str):
        # Si no hay path, usar el .docx mas reciente
        if not path_str:
            latest = self._latest_docx()
            if not latest:
                return "No hay documentos Word en sandbox/office/ para convertir."
            path = latest
            print(f"[PDF] Usando el docx mas reciente: {path.name}")
        else:
            path = self._resolve_path(path_str)
            if not path:
                return f"No encontre el archivo: {path_str}"

        if path.suffix.lower() != ".docx":
            return f"Solo puedo convertir .docx (recibi {path.suffix})"

        # Resolver output
        if output_str:
            out_raw = output_str.strip().strip('"').strip("'")
            out = Path(out_raw)
            if not out.is_absolute():
                out = ROOT / out
            if out.suffix.lower() != ".pdf":
                out = out.with_suffix(".pdf")
        else:
            out = path.with_suffix(".pdf")

        try:
            out.relative_to(ROOT)
        except ValueError:
            return f"Ruta de salida fuera del proyecto, bloqueado: {out}"

        if out.exists():
            try:
                shutil.copy2(out, out.with_suffix(".pdf.bak"))
            except Exception:
                pass

        summary = f"Convertir {path.name} a PDF"
        if not confirmation.require("pdf", "from_docx", summary):
            return "Cancelado."

        print(f"[PDF] Convirtiendo {path.name}...")

        # Intento 1: docx2pdf
        try:
            from docx2pdf import convert
            convert(str(path), str(out))
            if out.exists():
                size_kb = out.stat().st_size // 1024
                print(f"[PDF] Guardado: {out} ({size_kb} KB)")
                return {
                    "thought": f"PDF generado ({size_kb} KB)",
                    "display": (
                        f"PDF creado: {out}\n"
                        f"({size_kb} KB)\n\n"
                        f"Origen: {path.name}"
                    ),
                    "voice": f"Listo. PDF guardado en {out.name}.",
                }
        except Exception as e:
            print(f"[PDF] docx2pdf fallo: {e}")

        # Intento 2: LibreOffice
        soffice = self._find_soffice()
        if soffice:
            print(f"[PDF] Fallback LibreOffice: {soffice}")
            try:
                result = subprocess.run(
                    [soffice, "--headless", "--convert-to", "pdf",
                     "--outdir", str(out.parent), str(path)],
                    capture_output=True, text=True, timeout=60,
                )
                if result.returncode == 0:
                    auto_out = out.parent / (path.stem + ".pdf")
                    if auto_out.exists() and auto_out != out:
                        auto_out.rename(out)
                    if out.exists():
                        size_kb = out.stat().st_size // 1024
                        return {
                            "thought": f"PDF generado con LibreOffice ({size_kb} KB)",
                            "display": f"PDF creado: {out}\n({size_kb} KB)",
                            "voice": f"Listo. PDF guardado en {out.name}.",
                        }
            except Exception as e:
                print(f"[PDF] LibreOffice fallo: {e}")

        return (
            "No pude convertir a PDF. "
            "Verifica que Word este instalado y no tenga un dialogo abierto."
        )

    # ─── LIST ────────────────────────────────────────────────────────────

    def _list(self):
        if not SANDBOX_DIR.exists():
            return "No hay PDFs todavia."

        pdfs = list(SANDBOX_DIR.rglob("*.pdf"))
        if not pdfs:
            return "No hay PDFs todavia."

        pdfs.sort(key=lambda p: p.stat().st_mtime, reverse=True)
        pdfs = pdfs[:10]

        lines = [f"Ultimos {len(pdfs)} PDFs:"]
        for p in pdfs:
            size_kb = p.stat().st_size // 1024
            lines.append(f"  - {p.name} ({size_kb} KB)")

        return {
            "thought": "",
            "display": "\n".join(lines),
            "voice": f"Tienes {len(pdfs)} PDFs generados.",
        }