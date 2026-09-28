"""Skill de PDF: convierte Word a PDF + utilidades avanzadas.

Acciones:
- from_docx: convertir .docx a PDF
- list: listar PDFs en sandbox/
- info: metadatos (paginas, tamano, titulo, autor)
- extract_text: extraer texto de todo el PDF (o rango)
- to_images: convertir cada pagina a PNG
- watermark: anadir marca de agua con texto
- compress: reducir el tamano del PDF
"""
import shutil
import subprocess
from pathlib import Path

from skills.base import Skill
from core import confirmation

ROOT = Path(__file__).resolve().parent.parent
SANDBOX_DIR = ROOT / "sandbox"
OFFICE_DIR = SANDBOX_DIR / "office"

# Dependencias opcionales
try:
    from pypdf import PdfReader, PdfWriter
    HAS_PYPDF = True
except ImportError:
    HAS_PYPDF = False

try:
    from PIL import Image
    HAS_PIL = True
except ImportError:
    HAS_PIL = False


class PdfSkill(Skill):
    name = "pdf"
    description = "Convierte Word a PDF y utilidades (info, texto, imagenes, watermark)"

    def run(self, action, params):
        # ── Existente ──
        if action == "from_docx":
            return self._from_docx(
                params.get("path", ""),
                params.get("output", ""),
            )
        if action == "list":
            return self._list()

        # ── Nuevas acciones ──
        if action == "info":
            return self._info(params.get("path", ""))
        if action == "extract_text":
            return self._extract_text(
                params.get("path", ""),
                params.get("pages", []),
            )
        if action == "to_images":
            return self._to_images(
                params.get("path", ""),
                params.get("output_dir", ""),
                params.get("dpi", 150),
            )
        if action == "watermark":
            return self._watermark(
                params.get("path", ""),
                params.get("text", "CONFIDENCIAL"),
                params.get("output", ""),
            )
        if action == "compress":
            return self._compress(
                params.get("path", ""),
                params.get("output", ""),
            )

        # ── Edicion avanzada ──
        if action == "extract_pages":
            return self._extract_pages(
                params.get("path", ""),
                params.get("pages", []),
                params.get("output", ""),
            )
        if action == "insert_pages":
            return self._insert_pages(
                params.get("path", ""),
                params.get("insert_path", ""),
                params.get("at", 1),
                params.get("output", ""),
            )
        if action == "reorder":
            return self._reorder(
                params.get("path", ""),
                params.get("order", []),
                params.get("output", ""),
            )
        if action == "set_password":
            return self._set_password(
                params.get("path", ""),
                params.get("password", ""),
                params.get("output", ""),
            )
        if action == "remove_password":
            return self._remove_password(
                params.get("path", ""),
                params.get("password", ""),
                params.get("output", ""),
            )
        if action == "metadata":
            return self._metadata(
                params.get("path", ""),
                params.get("title", ""),
                params.get("author", ""),
                params.get("subject", ""),
                params.get("keywords", ""),
                params.get("output", ""),
            )
        if action == "merge_images":
            return self._merge_images(
                params.get("paths", []),
                params.get("output", ""),
            )
        if action == "sign":
            return self._sign(
                params.get("path", ""),
                params.get("signature_path", ""),
                params.get("page", 1),
                params.get("x", 50),
                params.get("y", 50),
                params.get("width", 200),
                params.get("output", ""),
            )
        if action == "stamp":
            return self._stamp(
                params.get("path", ""),
                params.get("stamp_path", ""),
                params.get("page", 1),
                params.get("x", 0),
                params.get("y", 0),
                params.get("width", 100),
                params.get("output", ""),
            )
        if action == "blank_page":
            return self._blank_page(
                params.get("path", ""),
                params.get("at", "end"),
                params.get("count", 1),
                params.get("output", ""),
            )
        if action == "page_numbers":
            return self._page_numbers(
                params.get("path", ""),
                params.get("position", "bottom-center"),
                params.get("start", 1),
                params.get("output", ""),
            )

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
                    "display": f"PDF creado: {out}\n({size_kb} KB)\n\nOrigen: {path.name}",
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

    # ─── INFO ────────────────────────────────────────────────────────────

    def _info(self, path_str):
        if not HAS_PYPDF:
            return "Falta pypdf."
        path = self._resolve_path(path_str)
        if not path or path.suffix.lower() != ".pdf":
            return f"No encontre el PDF: {path_str}"

        try:
            reader = PdfReader(str(path))
            n = len(reader.pages)
            meta = reader.metadata or {}
            size_kb = path.stat().st_size // 1024

            titulo = meta.get("/Title", "") or "(sin titulo)"
            autor = meta.get("/Author", "") or "(sin autor)"

            return {
                "thought": f"PDF con {n} paginas",
                "display": (
                    f"**PDF:** {path.name}\n"
                    f"**Paginas:** {n}\n"
                    f"**Tamano:** {size_kb} KB\n"
                    f"**Titulo:** {titulo}\n"
                    f"**Autor:** {autor}"
                ),
                "voice": f"El PDF tiene {n} paginas.",
            }
        except Exception as e:
            return f"Error leyendo PDF: {e}"

    # ─── EXTRACT TEXT ────────────────────────────────────────────────────

    def _extract_text(self, path_str, pages):
        if not HAS_PYPDF:
            return "Falta pypdf."
        path = self._resolve_path(path_str)
        if not path or path.suffix.lower() != ".pdf":
            return f"No encontre el PDF: {path_str}"

        try:
            reader = PdfReader(str(path))
            n = len(reader.pages)
            # Si no se dan pages, extraer todo
            rango = pages if pages else list(range(1, n + 1))

            texto_total = []
            for p_num in rango:
                if 1 <= p_num <= n:
                    page = reader.pages[p_num - 1]
                    t = page.extract_text() or ""
                    texto_total.append(f"--- Pagina {p_num} ---\n{t.strip()}")

            if not texto_total:
                return "No se pudo extraer texto."

            texto = "\n\n".join(texto_total)
            # Guardar en archivo tambien
            out_txt = path.with_suffix(".txt")
            out_txt.write_text(texto, encoding="utf-8")

            preview = texto[:2000]
            if len(texto) > 2000:
                preview += f"\n\n... (+{len(texto)-2000} caracteres mas)"

            return {
                "thought": f"Texto extraido de {len(rango)} paginas",
                "display": (
                    f"**Texto extraido de {path.name}**\n"
                    f"Guardado en: {out_txt.name}\n\n"
                    f"```\n{preview}\n```"
                ),
                "voice": f"Extraje texto de {len(rango)} paginas. Guardado en {out_txt.name}.",
            }
        except Exception as e:
            return f"Error extrayendo texto: {e}"

    # ─── TO IMAGES ───────────────────────────────────────────────────────

    def _to_images(self, path_str, output_dir, dpi):
        """Convierte cada pagina del PDF a una imagen PNG.

        Nota: requiere pdf2image (poppler) o fitz (PyMuPDF).
        """
        path = self._resolve_path(path_str)
        if not path or path.suffix.lower() != ".pdf":
            return f"No encontre el PDF: {path_str}"

        if output_dir:
            out_dir = Path(output_dir.strip().strip('"'))
            if not out_dir.is_absolute():
                out_dir = ROOT / out_dir
        else:
            out_dir = path.parent / f"{path.stem}_imagenes"

        try:
            out_dir.relative_to(ROOT)
        except ValueError:
            return f"Ruta fuera del proyecto: {out_dir}"

        out_dir.mkdir(parents=True, exist_ok=True)

        # Intento 1: PyMuPDF (fitz)
        try:
            import fitz
            doc = fitz.open(str(path))
            n = len(doc)
            for i in range(n):
                page = doc[i]
                # Renderizar a PNG
                zoom = dpi / 72
                mat = fitz.Matrix(zoom, zoom)
                pix = page.get_pixmap(matrix=mat)
                out_file = out_dir / f"{path.stem}_pag_{i+1:03d}.png"
                pix.save(str(out_file))
            doc.close()
            return {
                "thought": f"{n} paginas convertidas a PNG",
                "display": f"**PDF -> {n} imagenes PNG**\n\nGuardadas en: {out_dir}",
                "voice": f"Listo. Converti {n} paginas a imagenes.",
            }
        except ImportError:
            pass
        except Exception as e:
            return f"Error con PyMuPDF: {e}"

        # Intento 2: pdf2image (requiere poppler)
        try:
            from pdf2image import convert_from_path
            images = convert_from_path(str(path), dpi=int(dpi))
            for i, img in enumerate(images, 1):
                out_file = out_dir / f"{path.stem}_pag_{i:03d}.png"
                img.save(str(out_file), "PNG")
            return {
                "thought": f"{len(images)} paginas convertidas a PNG",
                "display": f"**PDF -> {len(images)} imagenes PNG**\n\nGuardadas en: {out_dir}",
                "voice": f"Listo. Converti {len(images)} paginas a imagenes.",
            }
        except ImportError:
            return (
                "Falta PyMuPDF o pdf2image para convertir paginas a imagenes. "
                "Instala: pip install PyMuPDF"
            )
        except Exception as e:
            return f"Error con pdf2image: {e}"

    # ─── WATERMARK ───────────────────────────────────────────────────────

    def _watermark(self, path_str, texto, output_str):
        """Anade una marca de agua con texto a todas las paginas."""
        if not HAS_PYPDF:
            return "Falta pypdf."
        path = self._resolve_path(path_str)
        if not path or path.suffix.lower() != ".pdf":
            return f"No encontre el PDF: {path_str}"

        try:
            from reportlab.pdfgen import canvas
            from reportlab.lib.pagesizes import letter
            from reportlab.lib.units import inch
        except ImportError:
            return "Falta reportlab. Ejecuta: pip install reportlab"

        try:
            import io
            reader = PdfReader(str(path))
            writer = PdfWriter()

            # Crear la marca de agua en memoria
            packet = io.BytesIO()
            can = canvas.Canvas(packet, pagesize=letter)
            can.setFont("Helvetica", 40)
            can.setFillColorRGB(0.7, 0.7, 0.7, alpha=0.3)
            # Diagonal
            can.saveState()
            can.translate(300, 400)
            can.rotate(45)
            can.drawCentredString(0, 0, texto)
            can.restoreState()
            can.save()
            packet.seek(0)

            watermark_page = PdfReader(packet).pages[0]

            for page in reader.pages:
                page.merge_page(watermark_page)
                writer.add_page(page)

            if output_str:
                out = Path(output_str.strip().strip('"').strip("'"))
                if not out.is_absolute():
                    out = ROOT / out
                if out.suffix.lower() != ".pdf":
                    out = out.with_suffix(".pdf")
            else:
                out = path.with_name(f"{path.stem}_watermark.pdf")

            try:
                out.relative_to(ROOT)
            except ValueError:
                return f"Ruta fuera del proyecto: {out}"

            with open(out, "wb") as f:
                writer.write(f)

            return {
                "thought": f"Marca de agua '{texto}' anadida",
                "display": f"**PDF con marca de agua:** {out.name}",
                "voice": f"Listo. Anadi la marca de agua.",
            }
        except Exception as e:
            return f"Error: {e}"

    # ─── COMPRESS ────────────────────────────────────────────────────────

    def _compress(self, path_str, output_str):
        """Reduce el tamano del PDF recomprimiendo los streams."""
        if not HAS_PYPDF:
            return "Falta pypdf."
        path = self._resolve_path(path_str)
        if not path or path.suffix.lower() != ".pdf":
            return f"No encontre el PDF: {path_str}"

        try:
            reader = PdfReader(str(path))
            writer = PdfWriter()

            # Anadir primero TODAS las paginas al writer
            for page in reader.pages:
                writer.add_page(page)

            # Ahora comprimir los streams de las paginas YA en el writer
            for page in writer.pages:
                try:
                    page.compress_content_streams()
                except Exception as e:
                    print(f"[PDF] No se pudo comprimir una pagina: {e}")

            # Comprimir metadatos
            writer.add_metadata({
                "/Producer": "Senna PDF Compressor",
            })

            if output_str:
                out = Path(output_str.strip().strip('"').strip("'"))
                if not out.is_absolute():
                    out = ROOT / out
                if out.suffix.lower() != ".pdf":
                    out = out.with_suffix(".pdf")
            else:
                out = path.with_name(f"{path.stem}_comprimido.pdf")

            try:
                out.relative_to(ROOT)
            except ValueError:
                return f"Ruta fuera del proyecto: {out}"

            with open(out, "wb") as f:
                writer.write(f)

            old_size = path.stat().st_size // 1024
            new_size = out.stat().st_size // 1024
            ahorro = old_size - new_size
            pct = round(ahorro / old_size * 100, 1) if old_size > 0 else 0

            return {
                "thought": f"PDF comprimido ({ahorro} KB menos)",
                "display": (
                    f"**PDF comprimido:** {out.name}\n\n"
                    f"Antes: {old_size} KB\n"
                    f"Ahora: {new_size} KB\n"
                    f"Ahorro: {ahorro} KB ({pct}%)"
                ),
                "voice": f"Listo. Reduje el PDF un {pct} por ciento.",
            }
        except Exception as e:
            return f"Error comprimiendo: {e}"

    # ─── EXTRACT PAGES ────────────────────────────────────────────────────

    def _extract_pages(self, path_str, pages, output_str):
        """Extrae paginas especificas a un nuevo PDF."""
        if not HAS_PYPDF:
            return "Falta pypdf."
        path = self._resolve_path(path_str)
        if not path or path.suffix.lower() != ".pdf":
            return f"No encontre el PDF: {path_str}"

        if not pages:
            return "Necesito los numeros de pagina a extraer."

        try:
            reader = PdfReader(str(path))
            n = len(reader.pages)

            writer = PdfWriter()
            for p in pages:
                try:
                    idx = int(p) - 1
                    if 0 <= idx < n:
                        writer.add_page(reader.pages[idx])
                except (ValueError, TypeError):
                    continue

            if len(writer.pages) == 0:
                return "Ninguna pagina valida para extraer."

            if output_str:
                out = Path(output_str.strip().strip('"').strip("'"))
                if not out.is_absolute():
                    out = ROOT / out
                if out.suffix.lower() != ".pdf":
                    out = out.with_suffix(".pdf")
            else:
                out = path.with_name(f"{path.stem}_extract.pdf")

            try:
                out.relative_to(ROOT)
            except ValueError:
                return f"Ruta fuera del proyecto: {out}"

            out.parent.mkdir(parents=True, exist_ok=True)
            with open(out, "wb") as f:
                writer.write(f)

            return {
                "thought": f"Extraidas {len(writer.pages)} paginas",
                "display": f"PDF nuevo: {out.name}\n({len(writer.pages)} paginas extraidas de {n})",
                "voice": f"Listo. Extraje {len(writer.pages)} paginas.",
            }
        except Exception as e:
            return f"Error: {e}"

    # ─── INSERT PAGES ─────────────────────────────────────────────────────

    def _insert_pages(self, path_str, insert_path_str, at, output_str):
        """Inserta un PDF dentro de otro en la posicion 'at' (1-based)."""
        if not HAS_PYPDF:
            return "Falta pypdf."
        path = self._resolve_path(path_str)
        insert_path = self._resolve_path(insert_path_str)
        if not path or path.suffix.lower() != ".pdf":
            return f"No encontre el PDF base: {path_str}"
        if not insert_path or insert_path.suffix.lower() != ".pdf":
            return f"No encontre el PDF a insertar: {insert_path_str}"

        try:
            at = int(at)
        except (ValueError, TypeError):
            at = 1

        try:
            reader1 = PdfReader(str(path))
            reader2 = PdfReader(str(insert_path))
            writer = PdfWriter()

            n1 = len(reader1.pages)
            # 'at' es 1-based, insertamos DESPUES de la pagina (at-1)
            insert_pos = max(0, min(at, n1))

            # Paginas antes del punto de insercion
            for i in range(insert_pos):
                writer.add_page(reader1.pages[i])
            # Paginas del PDF a insertar
            for page in reader2.pages:
                writer.add_page(page)
            # Paginas restantes
            for i in range(insert_pos, n1):
                writer.add_page(reader1.pages[i])

            if output_str:
                out = Path(output_str.strip().strip('"').strip("'"))
                if not out.is_absolute():
                    out = ROOT / out
                if out.suffix.lower() != ".pdf":
                    out = out.with_suffix(".pdf")
            else:
                out = path.with_name(f"{path.stem}_inserted.pdf")

            try:
                out.relative_to(ROOT)
            except ValueError:
                return f"Ruta fuera del proyecto: {out}"

            out.parent.mkdir(parents=True, exist_ok=True)
            with open(out, "wb") as f:
                writer.write(f)

            return {
                "thought": f"Insertadas {len(reader2.pages)} paginas",
                "display": f"PDF final: {out.name}\n({len(writer.pages)} paginas totales)",
                "voice": f"Listo. Inserto las paginas.",
            }
        except Exception as e:
            return f"Error: {e}"

    # ─── REORDER ──────────────────────────────────────────────────────────

    def _reorder(self, path_str, order, output_str):
        """Reordena las paginas segun el orden dado. order = [3,1,2] significa: nueva pag 1 = vieja pag 3, etc."""
        if not HAS_PYPDF:
            return "Falta pypdf."
        path = self._resolve_path(path_str)
        if not path or path.suffix.lower() != ".pdf":
            return f"No encontre el PDF: {path_str}"

        if not order:
            return "Necesito el orden de las paginas (ej: [3,1,2])."

        try:
            reader = PdfReader(str(path))
            n = len(reader.pages)
            writer = PdfWriter()

            for p in order:
                try:
                    idx = int(p) - 1
                    if 0 <= idx < n:
                        writer.add_page(reader.pages[idx])
                except (ValueError, TypeError):
                    continue

            if len(writer.pages) == 0:
                return "Ningun orden valido."

            if output_str:
                out = Path(output_str.strip().strip('"').strip("'"))
                if not out.is_absolute():
                    out = ROOT / out
                if out.suffix.lower() != ".pdf":
                    out = out.with_suffix(".pdf")
            else:
                out = path.with_name(f"{path.stem}_reordered.pdf")

            try:
                out.relative_to(ROOT)
            except ValueError:
                return f"Ruta fuera del proyecto: {out}"

            out.parent.mkdir(parents=True, exist_ok=True)
            with open(out, "wb") as f:
                writer.write(f)

            return {
                "thought": f"Reordenadas {len(writer.pages)} paginas",
                "display": f"PDF reordenado: {out.name}\n({len(writer.pages)} paginas)",
                "voice": "Listo. Reordene las paginas.",
            }
        except Exception as e:
            return f"Error: {e}"

    # ─── SET PASSWORD ─────────────────────────────────────────────────────

    def _set_password(self, path_str, password, output_str):
        """Anade contrasena a un PDF."""
        if not HAS_PYPDF:
            return "Falta pypdf."
        path = self._resolve_path(path_str)
        if not path or path.suffix.lower() != ".pdf":
            return f"No encontre el PDF: {path_str}"

        if not password:
            return "Necesito una contrasena."

        try:
            reader = PdfReader(str(path))
            writer = PdfWriter()
            for page in reader.pages:
                writer.add_page(page)

            writer.encrypt(password)

            if output_str:
                out = Path(output_str.strip().strip('"').strip("'"))
                if not out.is_absolute():
                    out = ROOT / out
                if out.suffix.lower() != ".pdf":
                    out = out.with_suffix(".pdf")
            else:
                out = path.with_name(f"{path.stem}_protegido.pdf")

            try:
                out.relative_to(ROOT)
            except ValueError:
                return f"Ruta fuera del proyecto: {out}"

            out.parent.mkdir(parents=True, exist_ok=True)
            with open(out, "wb") as f:
                writer.write(f)

            return {
                "thought": "PDF protegido con contrasena",
                "display": f"PDF protegido: {out.name}",
                "voice": "Listo. PDF protegido con contrasena.",
            }
        except Exception as e:
            return f"Error: {e}"

    # ─── REMOVE PASSWORD ──────────────────────────────────────────────────

    def _remove_password(self, path_str, password, output_str):
        """Quita la contrasena de un PDF."""
        if not HAS_PYPDF:
            return "Falta pypdf."
        path = self._resolve_path(path_str)
        if not path or path.suffix.lower() != ".pdf":
            return f"No encontre el PDF: {path_str}"

        try:
            reader = PdfReader(str(path))
            if reader.is_encrypted:
                try:
                    reader.decrypt(password or "")
                except Exception:
                    return "Contrasena incorrecta o PDF no desbloqueable."

            writer = PdfWriter()
            for page in reader.pages:
                writer.add_page(page)

            if output_str:
                out = Path(output_str.strip().strip('"').strip("'"))
                if not out.is_absolute():
                    out = ROOT / out
                if out.suffix.lower() != ".pdf":
                    out = out.with_suffix(".pdf")
            else:
                out = path.with_name(f"{path.stem}_sin_pass.pdf")

            try:
                out.relative_to(ROOT)
            except ValueError:
                return f"Ruta fuera del proyecto: {out}"

            out.parent.mkdir(parents=True, exist_ok=True)
            with open(out, "wb") as f:
                writer.write(f)

            return {
                "thought": "Contrasena eliminada",
                "display": f"PDF sin proteccion: {out.name}",
                "voice": "Listo. Contrasena eliminada.",
            }
        except Exception as e:
            return f"Error: {e}"

    # ─── METADATA ─────────────────────────────────────────────────────────

    def _metadata(self, path_str, title, author, subject, keywords, output_str):
        """Edita metadatos del PDF (titulo, autor, asunto, palabras clave)."""
        if not HAS_PYPDF:
            return "Falta pypdf."
        path = self._resolve_path(path_str)
        if not path or path.suffix.lower() != ".pdf":
            return f"No encontre el PDF: {path_str}"

        try:
            reader = PdfReader(str(path))
            writer = PdfWriter()
            for page in reader.pages:
                writer.add_page(page)

            meta = {}
            if title:
                meta["/Title"] = title
            if author:
                meta["/Author"] = author
            if subject:
                meta["/Subject"] = subject
            if keywords:
                meta["/Keywords"] = keywords

            if not meta:
                return "Necesito al menos un campo (title, author, subject, keywords)."

            writer.add_metadata(meta)

            if output_str:
                out = Path(output_str.strip().strip('"').strip("'"))
                if not out.is_absolute():
                    out = ROOT / out
                if out.suffix.lower() != ".pdf":
                    out = out.with_suffix(".pdf")
            else:
                out = path.with_name(f"{path.stem}_meta.pdf")

            try:
                out.relative_to(ROOT)
            except ValueError:
                return f"Ruta fuera del proyecto: {out}"

            out.parent.mkdir(parents=True, exist_ok=True)
            with open(out, "wb") as f:
                writer.write(f)

            return {
                "thought": f"Metadatos actualizados ({len(meta)} campos)",
                "display": f"PDF con metadatos: {out.name}\n" + "\n".join(f"  {k}: {v}" for k, v in meta.items()),
                "voice": "Listo. Metadatos actualizados.",
            }
        except Exception as e:
            return f"Error: {e}"

    # ─── MERGE IMAGES ─────────────────────────────────────────────────────

    def _merge_images(self, paths, output_str):
        """Crea un PDF desde varias imagenes (una por pagina)."""
        if not HAS_PIL:
            return "Falta Pillow."
        if not paths:
            return "Necesito la lista de imagenes."

        # Resolver
        img_paths = []
        for p in paths:
            ip = self._resolve_path(p)
            if ip and ip.suffix.lower() in (".png", ".jpg", ".jpeg", ".webp", ".bmp"):
                img_paths.append(ip)

        if not img_paths:
            return "No encontre imagenes validas."

        try:
            imgs = [Image.open(str(p)).convert("RGB") for p in img_paths]

            if output_str:
                out = Path(output_str.strip().strip('"').strip("'"))
                if not out.is_absolute():
                    out = ROOT / out
                if out.suffix.lower() != ".pdf":
                    out = out.with_suffix(".pdf")
            else:
                from datetime import datetime as _dt
                ts = int(_dt.now().timestamp())
                out = path_dir = img_paths[0].parent / f"imagenes_{ts}.pdf"

            try:
                out.relative_to(ROOT)
            except ValueError:
                return f"Ruta fuera del proyecto: {out}"

            out.parent.mkdir(parents=True, exist_ok=True)
            imgs[0].save(
                str(out),
                "PDF",
                save_all=True,
                append_images=imgs[1:],
                resolution=100.0,
            )

            return {
                "thought": f"PDF creado con {len(imgs)} imagenes",
                "display": f"PDF de imagenes: {out.name}\n({len(imgs)} paginas)",
                "voice": f"Listo. PDF con {len(imgs)} imagenes.",
            }
        except Exception as e:
            return f"Error: {e}"

    # ─── SIGN (firma) ─────────────────────────────────────────────────────

    def _sign(self, path_str, signature_str, page, x, y, width, output_str):
        """Anade una firma (imagen PNG con transparencia) en una pagina."""
        if not HAS_PYPDF:
            return "Falta pypdf."
        try:
            from reportlab.pdfgen import canvas
            from reportlab.lib.utils import ImageReader
        except ImportError:
            return "Falta reportlab."

        path = self._resolve_path(path_str)
        sig_path = self._resolve_path(signature_str)
        if not path or path.suffix.lower() != ".pdf":
            return f"No encontre el PDF: {path_str}"
        if not sig_path:
            return f"No encontre la firma: {signature_str}"

        try:
            page = int(page)
            x = float(x)
            y = float(y)
            width = float(width)
        except (ValueError, TypeError):
            return "Parametros invalidos (page, x, y, width)."

        try:
            reader = PdfReader(str(path))
            n = len(reader.pages)
            if not (1 <= page <= n):
                return f"Pagina {page} fuera de rango (1-{n})."

            target_page = reader.pages[page - 1]
            page_width = float(target_page.mediabox.width)
            page_height = float(target_page.mediabox.height)

            # Crear overlay con la firma
            import io as _io
            packet = _io.BytesIO()
            can = canvas.Canvas(packet, pagesize=(page_width, page_height))

            img = ImageReader(str(sig_path))
            iw, ih = img.getSize()
            aspect = ih / iw
            h = width * aspect

            can.drawImage(
                img,
                x, y,
                width=width,
                height=h,
                mask="auto",
                preserveAspectRatio=True,
            )
            can.save()
            packet.seek(0)

            overlay = PdfReader(packet).pages[0]
            target_page.merge_page(overlay)

            writer = PdfWriter()
            for i, p in enumerate(reader.pages):
                writer.add_page(p)

            if output_str:
                out = Path(output_str.strip().strip('"').strip("'"))
                if not out.is_absolute():
                    out = ROOT / out
                if out.suffix.lower() != ".pdf":
                    out = out.with_suffix(".pdf")
            else:
                out = path.with_name(f"{path.stem}_firmado.pdf")

            try:
                out.relative_to(ROOT)
            except ValueError:
                return f"Ruta fuera del proyecto: {out}"

            out.parent.mkdir(parents=True, exist_ok=True)
            with open(out, "wb") as f:
                writer.write(f)

            return {
                "thought": f"Firma anadida en pagina {page}",
                "display": f"PDF firmado: {out.name}",
                "voice": "Listo. Firma anadida.",
            }
        except Exception as e:
            return f"Error: {e}"

    # ─── STAMP (sello/imagen) ─────────────────────────────────────────────

    def _stamp(self, path_str, stamp_str, page, x, y, width, output_str):
        """Anade un sello/imagen (puede ser con transparencia)."""
        # Reutiliza _sign (misma logica)
        return self._sign(path_str, stamp_str, page, x, y, width, output_str)

    # ─── BLANK PAGE ───────────────────────────────────────────────────────

    def _blank_page(self, path_str, at, count, output_str):
        """Anade paginas en blanco al inicio, final o posicion."""
        if not HAS_PYPDF:
            return "Falta pypdf."
        try:
            from reportlab.pdfgen import canvas
        except ImportError:
            return "Falta reportlab."

        path = self._resolve_path(path_str)
        if not path or path.suffix.lower() != ".pdf":
            return f"No encontre el PDF: {path_str}"

        try:
            count = int(count)
        except (ValueError, TypeError):
            count = 1
        count = max(1, min(count, 50))

        try:
            reader = PdfReader(str(path))
            n = len(reader.pages)

            # Determinar posicion
            if at == "start":
                insert_pos = 0
            elif at == "end":
                insert_pos = n
            else:
                try:
                    insert_pos = max(0, min(int(at) - 1, n))
                except (ValueError, TypeError):
                    insert_pos = n

            # Crear paginas en blanco con tamaño de la primera
            first_page = reader.pages[0]
            pw = float(first_page.mediabox.width)
            ph = float(first_page.mediabox.height)

            import io as _io
            packet = _io.BytesIO()
            can = canvas.Canvas(packet, pagesize=(pw, ph))
            for _ in range(count):
                can.showPage()
            can.save()
            packet.seek(0)
            blank_reader = PdfReader(packet)

            writer = PdfWriter()
            for i in range(insert_pos):
                writer.add_page(reader.pages[i])
            for page in blank_reader.pages:
                writer.add_page(page)
            for i in range(insert_pos, n):
                writer.add_page(reader.pages[i])

            if output_str:
                out = Path(output_str.strip().strip('"').strip("'"))
                if not out.is_absolute():
                    out = ROOT / out
                if out.suffix.lower() != ".pdf":
                    out = out.with_suffix(".pdf")
            else:
                out = path.with_name(f"{path.stem}_blanks.pdf")

            try:
                out.relative_to(ROOT)
            except ValueError:
                return f"Ruta fuera del proyecto: {out}"

            out.parent.mkdir(parents=True, exist_ok=True)
            with open(out, "wb") as f:
                writer.write(f)

            return {
                "thought": f"{count} paginas en blanco anadidas",
                "display": f"PDF con paginas en blanco: {out.name}\n({len(writer.pages)} paginas totales)",
                "voice": f"Listo. Anadi {count} paginas en blanco.",
            }
        except Exception as e:
            return f"Error: {e}"

    # ─── PAGE NUMBERS ─────────────────────────────────────────────────────

    def _page_numbers(self, path_str, position, start, output_str):
        """Anade numeros de pagina a todas las paginas."""
        if not HAS_PYPDF:
            return "Falta pypdf."
        try:
            from reportlab.pdfgen import canvas
        except ImportError:
            return "Falta reportlab."

        path = self._resolve_path(path_str)
        if not path or path.suffix.lower() != ".pdf":
            return f"No encontre el PDF: {path_str}"

        try:
            start = int(start)
        except (ValueError, TypeError):
            start = 1

        # Posiciones validas
        positions = ["bottom-center", "bottom-right", "bottom-left",
                     "top-center", "top-right", "top-left"]
        if position not in positions:
            position = "bottom-center"

        try:
            reader = PdfReader(str(path))
            writer = PdfWriter()

            for i, page in enumerate(reader.pages):
                pw = float(page.mediabox.width)
                ph = float(page.mediabox.height)

                import io as _io
                packet = _io.BytesIO()
                can = canvas.Canvas(packet, pagesize=(pw, ph))
                can.setFont("Helvetica", 10)

                num = str(start + i)
                text_width = can.stringWidth(num, "Helvetica", 10)

                margin = 30
                if position == "bottom-center":
                    x = (pw - text_width) / 2
                    y = margin
                elif position == "bottom-right":
                    x = pw - text_width - margin
                    y = margin
                elif position == "bottom-left":
                    x = margin
                    y = margin
                elif position == "top-center":
                    x = (pw - text_width) / 2
                    y = ph - margin
                elif position == "top-right":
                    x = pw - text_width - margin
                    y = ph - margin
                else:  # top-left
                    x = margin
                    y = ph - margin

                can.drawString(x, y, num)
                can.save()
                packet.seek(0)

                overlay = PdfReader(packet).pages[0]
                page.merge_page(overlay)
                writer.add_page(page)

            if output_str:
                out = Path(output_str.strip().strip('"').strip("'"))
                if not out.is_absolute():
                    out = ROOT / out
                if out.suffix.lower() != ".pdf":
                    out = out.with_suffix(".pdf")
            else:
                out = path.with_name(f"{path.stem}_numerado.pdf")

            try:
                out.relative_to(ROOT)
            except ValueError:
                return f"Ruta fuera del proyecto: {out}"

            out.parent.mkdir(parents=True, exist_ok=True)
            with open(out, "wb") as f:
                writer.write(f)

            return {
                "thought": f"Numeros de pagina anadidos ({len(writer.pages)} paginas)",
                "display": f"PDF numerado: {out.name}\n(Posicion: {position})",
                "voice": "Listo. Numeros de pagina anadidos.",
            }
        except Exception as e:
            return f"Error: {e}"