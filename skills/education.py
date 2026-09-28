"""Skill de educacion: PSeInt, conversion de lenguajes, diagramas Mermaid."""
import re
from datetime import datetime
from pathlib import Path

import ollama
from skills.base import Skill
from core.config_loader import CONFIG
from core import confirmation

ROOT = Path(__file__).resolve().parent.parent
SANDBOX_DIR = ROOT / "sandbox"
PSEINT_DIR = SANDBOX_DIR / "pseint"
DIAGRAM_DIR = SANDBOX_DIR / "diagrams"
IMAGES_DIR = SANDBOX_DIR / "images"


class EducationSkill(Skill):
    name = "education"
    description = "PSeInt, conversion de codigo, diagramas Mermaid"

    def __init__(self):
        from core.model_config import get_model
        self.model = get_model("agent")

    def run(self, action, params):
        if action == "pseint":
            return self._pseint(params.get("description", ""))
        if action == "convert":
            return self._convert(
                params.get("code", ""),
                params.get("to_language", "python"),
            )
        if action == "diagram":
            return self._diagram(
                params.get("description", ""),
                params.get("kind", "flowchart"),
                params.get("format", "png"),
            )
        if action == "render":
            return self._render(
                params.get("name", ""),
                params.get("format", "png"),
            )
        if action == "list_diagrams":
            return self._list_diagrams()
        return f"Accion desconocida en education: {action}"

    # ─── HELPERS ─────────────────────────────────────────────────────────

    def _ask_llm(self, prompt, system=None, temperature=0.2):
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        try:
            resp = ollama.chat(
                model=self.model,
                messages=messages,
                options={"temperature": temperature},
                stream=False,
            )
            return resp["message"]["content"].strip()
        except Exception as e:
            return f"[ERROR LLM] {e}"

    def _clean_code_block(self, text):
        m = re.search(r"```[a-zA-Z0-9_+-]*\n?(.*?)```", text, re.DOTALL)
        if m:
            return m.group(1).strip()
        return text.replace("```", "").strip()

    def _slug(self, text, maxlen=40):
        s = text.lower()
        for k, v in {"á":"a","é":"e","í":"i","ó":"o","ú":"u","ñ":"n","ü":"u"}.items():
            s = s.replace(k, v)
        s = re.sub(r'[^a-z0-9]+', '_', s)[:maxlen].strip("_")
        return s or "algoritmo"

    # ─── PSEINT ──────────────────────────────────────────────────────────

    def _pseint(self, description):
        description = (description or "").strip()
        if not description:
            return "Dime que algoritmo quieres en PSeInt."

        print(f"[EDU] Generando PSeInt con {self.model}...")
        prompt = f"""Genera un algoritmo en PSeInt para lo siguiente:

{description}

Reglas:
- Usa la sintaxis clasica de PSeInt (Algoritmo/FinAlgoritmo, Definir, Escribir, Leer, Si/FinSi, Mientras/FinMientras, Para/FinPara, Segun/FinSegun).
- Incluye comentarios utiles con //.
- Si usa entrada, usa Leer apropiadamente.
- Devuelve UNICAMENTE el pseudocodigo, sin explicaciones.
- NO uses bloques de codigo markdown."""

        codigo = self._clean_code_block(
            self._ask_llm(prompt, system="Eres experto en PSeInt. Generas pseudocodigo correcto.", temperature=0.3)
        )
        if not codigo or codigo.startswith("[ERROR LLM]"):
            return f"Error generando PSeInt: {codigo}"

        # Guardar
        PSEINT_DIR.mkdir(parents=True, exist_ok=True)
        slug = self._slug(description)
        ts = int(datetime.now().timestamp())
        out = PSEINT_DIR / f"{slug}_{ts}.psc"
        out.write_text(codigo, encoding="utf-8")

        print(f"[EDU] PSeInt guardado: {out}")

        return {
            "thought": f"PSeInt generado ({len(codigo)} chars)",
            "display": (
                f"Codigo PSeInt:\n\n```\n{codigo}\n```\n\n"
                f"Guardado en: {out.name}"
            ),
            "voice": "Listo. Aqui esta el pseudocodigo PSeInt.",
        }

    # ─── CONVERT ─────────────────────────────────────────────────────────

    def _convert(self, code, to_language):
        code = (code or "").strip()
        if not code:
            return "Dime el codigo que quieres convertir."

        to_language = (to_language or "python").lower()
        if to_language not in ("python", "java", "c", "cpp", "csharp", "javascript", "go", "rust"):
            return f"Lenguaje no soportado: {to_language}. Usa python, java, c, cpp, csharp, javascript, go o rust."

        print(f"[EDU] Convirtiendo a {to_language} con {self.model}...")
        prompt = f"""Convierte el siguiente codigo (que puede estar en PSeInt, pseudocodigo o cualquier lenguaje) a {to_language}.

CODIGO ORIGINAL:
{code}

Reglas:
- Devuelve UNICAMENTE el codigo en {to_language}, sin explicaciones.
- Manten la misma funcionalidad.
- Usa buenas practicas del lenguaje destino.
- Incluye comentarios utiles.
- NO uses bloques de codigo markdown."""

        convertido = self._clean_code_block(
            self._ask_llm(prompt, system=f"Eres experto en {to_language}. Conviertes codigo entre lenguajes.", temperature=0.2)
        )
        if not convertido or convertido.startswith("[ERROR LLM]"):
            return f"Error convirtiendo: {convertido}"

        ext_map = {
            "python": ".py", "java": ".java", "c": ".c", "cpp": ".cpp",
            "csharp": ".cs", "javascript": ".js", "go": ".go", "rust": ".rs",
        }
        ext = ext_map.get(to_language, ".txt")

        PSEINT_DIR.mkdir(parents=True, exist_ok=True)
        ts = int(datetime.now().timestamp())
        out = PSEINT_DIR / f"convertido_{ts}{ext}"
        out.write_text(convertido, encoding="utf-8")

        return {
            "thought": f"Codigo convertido a {to_language}",
            "display": (
                f"Codigo en {to_language}:\n\n```{to_language}\n{convertido}\n```\n\n"
                f"Guardado en: {out.name}"
            ),
            "voice": f"Listo. Aqui esta el codigo en {to_language}.",
        }

    # ─── DIAGRAM ─────────────────────────────────────────────────────────

    # Mapeo de tipos de diagramas a sintaxis Mermaid
    DIAGRAM_KINDS = {
        "flujo": "flowchart TD",
        "flowchart": "flowchart TD",
        "secuencia": "sequenceDiagram",
        "sequence": "sequenceDiagram",
        "clases": "classDiagram",
        "class": "classDiagram",
        "estado": "stateDiagram-v2",
        "state": "stateDiagram-v2",
        "gantt": "gantt",
        "er": "erDiagram",
        # Nuevos tipos
        "mente": "mindmap",
        "mindmap": "mindmap",
        "linea": "timeline",
        "timeline": "timeline",
        "tarta": "pie",
        "pie": "pie",
        "viaje": "journey",
        "journey": "journey",
        "cuadrante": "quadrantChart",
        "quadrant": "quadrantChart",
        "git": "gitGraph",
        "gitgraph": "gitGraph",
    }

    def _find_mmdc(self):
        """Devuelve la ruta a mmdc o None si no esta instalado."""
        import shutil
        return shutil.which("mmdc")

    def _render_mermaid(self, mmd_path, formats=("png", "svg")):
        """Renderiza un archivo .mmd a PNG y/o SVG.

        Devuelve dict con {formato: Path} de los que se generaron.
        """
        mmdc = self._find_mmdc()
        if not mmdc:
            return {}

        import subprocess
        rendered = {}

        for fmt in formats:
            try:
                # Para PNG, usar fondo blanco (mas portable). Para SVG, transparente.
                bg = "white" if fmt == "png" else "transparent"
                out_file = mmd_path.with_suffix(f".{fmt}")

                print(f"[EDU] Renderizando {fmt.upper()} con mermaid-cli...")
                result = subprocess.run(
                    [mmdc, "-i", str(mmd_path), "-o", str(out_file), "-b", bg, "-s", "2"],
                    capture_output=True, text=True, timeout=90, shell=True,
                )

                if result.returncode == 0 and out_file.exists():
                    rendered[fmt] = out_file
                    print(f"[EDU] {fmt.upper()} generado: {out_file}")

                    # Copiar a sandbox/images/ para uso externo (office, etc.)
                    try:
                        IMAGES_DIR.mkdir(parents=True, exist_ok=True)
                        img_copy = IMAGES_DIR / out_file.name
                        import shutil as _sh
                        _sh.copy2(out_file, img_copy)
                    except Exception as _e:
                        print(f"[EDU] No pude copiar a images/: {_e}")
                else:
                    print(f"[EDU] Fallo {fmt}: {result.stderr[:200]}")
            except Exception as e:
                print(f"[EDU] Error renderizando {fmt}: {e}")

        return rendered

    def _diagram(self, description, kind, format="png"):
        description = (description or "").strip()
        if not description:
            return "Dime que diagrama quieres."

        kind = (kind or "flowchart").lower()
        if kind not in self.DIAGRAM_KINDS:
            kind = "flowchart"

        diagram_type = self.DIAGRAM_KINDS[kind]

        # Formatos a renderizar
        formats_req = (format or "png").lower().split(",")
        formats_req = [f.strip() for f in formats_req if f.strip() in ("png", "svg")]
        if not formats_req:
            formats_req = ["png"]

        print(f"[EDU] Generando diagrama Mermaid ({kind}) con {self.model}...")
        prompt = f"""Genera un diagrama Mermaid para lo siguiente:

{description}

Tipo de diagrama requerido: {diagram_type}

Reglas:
- Usa la sintaxis de Mermaid correcta y valida.
- Devuelve UNICAMENTE el codigo Mermaid.
- La PRIMERA linea debe ser exactamente: {diagram_type}
- NO uses bloques de codigo markdown.
- Nodos con texto claro y conciso.
- Maximo 15 nodos.
- NO uses caracteres especiales problemAticos (parentesis, corchetes anidados)."""

        mermaid = self._clean_code_block(
            self._ask_llm(prompt, system="Eres experto en Mermaid. Generas diagramas claros y validos.", temperature=0.3)
        )
        if not mermaid or mermaid.startswith("[ERROR LLM]"):
            return f"Error generando diagrama: {mermaid}"

        # Asegurar que empieza con el tipo correcto
        lines = mermaid.split("\n")
        first_word = diagram_type.split()[0]
        if not lines[0].strip().startswith(first_word):
            mermaid = f"{diagram_type}\n{mermaid}"

        # Guardar .mmd
        DIAGRAM_DIR.mkdir(parents=True, exist_ok=True)
        slug = self._slug(description)
        ts = int(datetime.now().timestamp())
        mmd_path = DIAGRAM_DIR / f"{slug}_{ts}.mmd"
        mmd_path.write_text(mermaid, encoding="utf-8")

        # Renderizar (PNG + SVG)
        rendered = self._render_mermaid(mmd_path, formats=tuple(formats_req))

        # Construir respuesta
        display_parts = [
            f"Diagrama Mermaid ({kind}):",
            "",
            "```mermaid",
            mermaid,
            "```",
            "",
            f"Codigo: {mmd_path.name}",
        ]

        if rendered:
            for fmt, path in rendered.items():
                display_parts.append(f"{fmt.upper()}: {path.name}")
        else:
            display_parts.append("(Sin render. Verifica que mmdc este instalado)")

        return {
            "thought": f"Diagrama {kind} generado ({len(rendered)} formatos)",
            "display": "\n".join(display_parts),
            "voice": f"Listo. Diagrama {kind} generado.",
        }

    def _render(self, name, format="png"):
        """Renderiza un .mmd existente a PNG/SVG sin regenerar el codigo."""
        if not name:
            return "Dime el nombre del archivo .mmd a renderizar."

        name = name.strip()
        # Buscar el archivo
        mmd_path = None
        if name.endswith(".mmd"):
            mmd_path = DIAGRAM_DIR / name
        else:
            # Buscar por nombre parcial
            matches = list(DIAGRAM_DIR.glob(f"*{name}*.mmd"))
            if matches:
                mmd_path = matches[-1]

        if not mmd_path or not mmd_path.exists():
            return f"No encontre el archivo: {name}"

        formats_req = (format or "png").lower().split(",")
        formats_req = [f.strip() for f in formats_req if f.strip() in ("png", "svg")]
        if not formats_req:
            formats_req = ["png"]

        rendered = self._render_mermaid(mmd_path, formats=tuple(formats_req))

        if not rendered:
            return f"No se pudo renderizar. Verifica que mmdc este instalado."

        lineas = [f"Renderizado: {mmd_path.name}"]
        for fmt, path in rendered.items():
            lineas.append(f"  {fmt.upper()}: {path.name}")

        return {
            "thought": f"Renderizado {mmd_path.name}",
            "display": "\n".join(lineas),
            "voice": f"Listo. Renderizado {mmd_path.name}.",
        }

    def _list_diagrams(self):
        """Lista los diagramas .mmd generados."""
        if not DIAGRAM_DIR.exists():
            return "No hay diagramas generados."

        mmds = sorted(DIAGRAM_DIR.glob("*.mmd"), key=lambda p: p.stat().st_mtime, reverse=True)[:15]
        if not mmds:
            return "No hay diagramas generados."

        lineas = [f"Ultimos {len(mmds)} diagramas:"]
        for mmd in mmds:
            png = mmd.with_suffix(".png")
            svg = mmd.with_suffix(".svg")
            formatos = []
            if png.exists():
                formatos.append("PNG")
            if svg.exists():
                formatos.append("SVG")
            fmt_str = f" [{', '.join(formatos)}]" if formatos else " [sin render]"
            lineas.append(f"  - {mmd.name}{fmt_str}")

        return {
            "thought": f"{len(mmds)} diagramas",
            "display": "\n".join(lineas),
            "voice": f"Tienes {len(mmds)} diagramas.",
        }