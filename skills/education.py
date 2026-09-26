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
            )
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

    def _diagram(self, description, kind):
        description = (description or "").strip()
        if not description:
            return "Dime que diagrama quieres."

        kind = (kind or "flowchart").lower()
        kind_map = {
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
        }
        if kind not in kind_map:
            kind = "flowchart"

        diagram_type = kind_map[kind]

        print(f"[EDU] Generando diagrama Mermaid ({kind}) con {self.model}...")
        prompt = f"""Genera un diagrama Mermaid para lo siguiente:

{description}

Tipo de diagrama requerido: {diagram_type}

Reglas:
- Usa la sintaxis de Mermaid correcta.
- Devuelve UNICAMENTE el codigo Mermaid.
- La PRIMERA linea debe ser exactamente: {diagram_type}
- NO uses bloques de codigo markdown.
- Nodos con texto claro y conciso.
- Maximo 15 nodos."""

        mermaid = self._clean_code_block(
            self._ask_llm(prompt, system="Eres experto en Mermaid. Generas diagramas claros.", temperature=0.3)
        )
        if not mermaid or mermaid.startswith("[ERROR LLM]"):
            return f"Error generando diagrama: {mermaid}"

        # Asegurar que empieza con el tipo correcto
        lines = mermaid.split("\n")
        if not lines[0].strip().startswith(diagram_type.split()[0]):
            mermaid = f"{diagram_type}\n{mermaid}"

        # Guardar
        DIAGRAM_DIR.mkdir(parents=True, exist_ok=True)
        slug = self._slug(description)
        ts = int(datetime.now().timestamp())
        out = DIAGRAM_DIR / f"{slug}_{ts}.mmd"
        out.write_text(mermaid, encoding="utf-8")

        # Intentar renderizar PNG si mermaid-cli esta disponible
        png_path = None
        try:
            import shutil
            import subprocess
            mmdc = shutil.which("mmdc")
            if mmdc:
                png_out = out.with_suffix(".png")
                print(f"[EDU] Renderizando PNG con mermaid-cli...")
                result = subprocess.run(
                    [mmdc, "-i", str(out), "-o", str(png_out), "-b", "transparent"],
                    capture_output=True, text=True, timeout=60,
                )
                if result.returncode == 0 and png_out.exists():
                    png_path = png_out
                    print(f"[EDU] PNG generado: {png_out}")
        except Exception as e:
            print(f"[EDU] No pude renderizar PNG: {e}")

        # Construir respuesta
        display_parts = [
            f"Diagrama Mermaid ({kind}):",
            "",
            f"```mermaid",
            mermaid,
            "```",
            "",
            f"Guardado: {out.name}",
        ]
        if png_path:
            display_parts.append(f"PNG: {png_path.name}")
        else:
            display_parts.append("(Para PNG: instala mermaid-cli con `npm install -g @mermaid-js/mermaid-cli`)")

        return {
            "thought": f"Diagrama Mermaid generado ({kind})",
            "display": "\n".join(display_parts),
            "voice": f"Listo. Aqui esta el diagrama {kind}.",
        }