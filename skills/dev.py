import os
import re
import ollama
from pathlib import Path
from skills.base import Skill
from core.config_loader import CONFIG

# Extensiones de código soportadas
CODE_EXTS = {
    ".py", ".js", ".jsx", ".ts", ".tsx", ".java", ".c", ".cpp", ".h", ".hpp",
    ".cs", ".go", ".rs", ".rb", ".php", ".swift", ".kt", ".scala",
    ".html", ".css", ".scss", ".sass", ".less",
    ".json", ".yaml", ".yml", ".toml", ".xml", ".sql",
    ".sh", ".bash", ".ps1", ".bat",
    ".md", ".txt",
}

# Carpetas a ignorar
IGNORE_DIRS = {
    "venv", "node_modules", "__pycache__", ".git", "dist", "build",
    ".venv", "env", ".idea", ".vscode", "target", "Library",
    ".next", ".nuxt", "coverage",
}

# Tamaño máximo del archivo a analizar (para no saturar al LLM)
MAX_FILE_CHARS = 8000
MAX_PROJECT_FILES = 15


class DevSkill(Skill):
    name = "dev"
    description = "Revisa codigo, encuentra bugs, explica archivos, genera codigo"

    def __init__(self):
        self.model = CONFIG["models"].get("coding", "qwen2.5-coder:7b")

    def run(self, action, params):
        if action == "review_file":
            return self._review_file(params.get("path", ""))
        if action == "review_project":
            return self._review_project(params.get("path", ""))
        if action == "explain":
            return self._explain(params.get("path", ""))
        if action == "find_issues":
            return self._find_issues(params.get("path", ""))
        if action == "generate_code":
            return self._generate_code(
                params.get("description", ""),
                params.get("language", "python"),
            )
        return f"Accion desconocida: {action}"

    # ─── HELPERS ─────────────────────────────────────────────────────────

    def _resolve_path(self, path_str):
        """Convierte string a Path, resolviendo alias comunes."""
        if not path_str:
            return None
        p = Path(path_str.strip().strip('"').strip("'"))
        if p.exists():
            return p
        # Probar con HOME
        home_path = Path.home() / path_str
        if home_path.exists():
            return home_path
        return None

    def _read_file(self, path):
        """Lee un archivo con encoding robusto."""
        try:
            content = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            try:
                content = path.read_text(encoding="latin-1", errors="ignore")
            except Exception as e:
                return None, f"Error leyendo archivo: {e}"
        except Exception as e:
            return None, f"Error leyendo archivo: {e}"
        return content, None

    def _ask_llm(self, prompt, system=None):
        """Llama a qwen2.5-coder via Ollama."""
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        try:
            response = ollama.chat(
                model=self.model,
                messages=messages,
                options={"temperature": 0.2},
            )
            return response["message"]["content"].strip()
        except Exception as e:
            return f"[ERROR LLM] {e}"

    # ─── REVIEW FILE ─────────────────────────────────────────────────────

    def _review_file(self, path_str):
        path = self._resolve_path(path_str)
        if not path:
            return f"No encontre el archivo: {path_str}"
        if not path.is_file():
            return f"No es un archivo: {path}"

        content, err = self._read_file(path)
        if err:
            return err

        # Si es muy grande, truncar
        truncated = False
        if len(content) > MAX_FILE_CHARS:
            content = content[:MAX_FILE_CHARS]
            truncated = True

        lang = path.suffix.lstrip(".")
        prompt = f"""Analiza este codigo {lang} y da un resumen ejecutivo en espanol.

ARCHIVO: {path.name}
{content}

Responde con este formato exacto:
1. **Proposito**: 1-2 frases sobre que hace el archivo.
2. **Estructura**: lista de funciones/clases principales (max 5).
3. **Bugs/Problemas**: errores o code smells que veas.
4. **Mejoras sugeridas**: 2-3 ideas concretas.

Se conciso. Si no ves bugs, di "Sin bugs evidentes"."""

        result = self._ask_llm(prompt, system="Eres un revisor de codigo senior. Hablas espanol, eres directo y practico.")
        note = f"\n\n_(Archivo truncado a {MAX_FILE_CHARS} caracteres)_" if truncated else ""

        return {
            "thought": f"Revisando {path.name} con {self.model}",
            "display": f"📝 Revision de {path.name}:\n\n{result}{note}",
            "voice": f"Revise {path.name}. {result[:200]}",
        }

    # ─── REVIEW PROJECT ──────────────────────────────────────────────────

    def _review_project(self, path_str):
        path = self._resolve_path(path_str)
        if not path:
            return f"No encontre la carpeta: {path_str}"
        if not path.is_dir():
            return f"No es una carpeta: {path}"

        # Escanear archivos de código
        files = []
        for root, dirs, filenames in os.walk(path):
            # Excluir carpetas
            dirs[:] = [d for d in dirs if d not in IGNORE_DIRS and not d.startswith(".")]
            for f in filenames:
                ext = Path(f).suffix.lower()
                if ext in CODE_EXTS:
                    full = Path(root) / f
                    try:
                        size = full.stat().st_size
                        files.append((full, size))
                    except Exception:
                        pass
            if len(files) >= MAX_PROJECT_FILES * 2:
                break

        if not files:
            return f"No encontre archivos de codigo en {path}"

        # Ordenar por tamaño (los más relevantes primero)
        files.sort(key=lambda x: x[1], reverse=True)
        top_files = files[:MAX_PROJECT_FILES]

        # Construir resumen del proyecto
        summary_lines = [
            f"Proyecto: {path.name}",
            f"Total archivos de codigo: {len(files)}",
            "",
            "Archivos principales:",
        ]
        for f, size in top_files:
            rel = f.relative_to(path)
            summary_lines.append(f"  - {rel} ({size} bytes)")

        prompt = f"""Resume este proyecto de software en espanol.

{chr(10).join(summary_lines)}

Sin ver el contenido de cada archivo, dame:
1. **Tipo de proyecto**: que tipo de aplicacion parece ser.
2. **Stack probable**: lenguajes y frameworks.
3. **Estructura**: como esta organizado.
4. **Sugerencias**: que revisar o mejorar.

Maximo 200 palabras."""

        result = self._ask_llm(prompt, system="Eres arquitecto de software. Hablas espanol, eres conciso.")
        return {
            "thought": f"Analizando proyecto {path.name} ({len(files)} archivos)",
            "display": f"📁 Revision de proyecto: {path.name}\n\n{result}",
            "voice": f"Analice el proyecto {path.name}. Tiene {len(files)} archivos de codigo.",
        }

    # ─── EXPLAIN ─────────────────────────────────────────────────────────

    def _explain(self, path_str):
        path = self._resolve_path(path_str)
        if not path or not path.is_file():
            return f"No encontre el archivo: {path_str}"

        content, err = self._read_file(path)
        if err:
            return err

        if len(content) > MAX_FILE_CHARS:
            content = content[:MAX_FILE_CHARS]

        lang = path.suffix.lstrip(".")
        prompt = f"""Explica este codigo {lang} paso a paso en espanol, para alguien que aprende.

{content}

Explica:
1. Que hace en general (2 frases).
2. Cada funcion/clase principal y su proposito.
3. Como se conectan las partes.

Se claro y didactico. Maximo 300 palabras."""

        result = self._ask_llm(prompt, system="Eres un profesor de programacion. Explicas simple y claro en espanol.")
        return {
            "thought": f"Explicando {path.name}",
            "display": f"📖 Explicacion de {path.name}:\n\n{result}",
            "voice": f"Te explico {path.name}.",
        }

    # ─── FIND ISSUES ─────────────────────────────────────────────────────

    def _find_issues(self, path_str):
        path = self._resolve_path(path_str)
        if not path or not path.is_file():
            return f"No encontre el archivo: {path_str}"

        content, err = self._read_file(path)
        if err:
            return err

        if len(content) > MAX_FILE_CHARS:
            content = content[:MAX_FILE_CHARS]

        lang = path.suffix.lstrip(".")
        prompt = f"""Analiza este codigo {lang} y encuentra TODOS los problemas.

{content}

Busca especificamente:
- Bugs logicos
- Errores de seguridad (inyeccion SQL, XSS, hardcoded secrets)
- Problemas de rendimiento
- Code smells
- Manejo de errores faltante

Formato:
[SEVERIDAD] Linea XX: Descripcion del problema
→ Sugerencia: como arreglarlo

Si no hay problemas, di "Sin problemas evidentes".
Se directo y conciso."""

        result = self._ask_llm(prompt, system="Eres auditor de seguridad y code reviewer. Encuentras bugs que otros no ven. Hablas espanol.")
        return {
            "thought": f"Buscando bugs en {path.name}",
            "display": f"🐛 Bugs encontrados en {path.name}:\n\n{result}",
            "voice": f"Encontre algunos problemas en {path.name}.",
        }

    # ─── GENERATE CODE ───────────────────────────────────────────────────

    def _generate_code(self, description, language):
        if not description:
            return "No me dijiste que generar."

        prompt = f"""Genera codigo en {language} que haga lo siguiente:
{description}

Reglas:
- Devuelve UNICAMENTE el codigo, sin explicaciones.
- Incluye comentarios utiles.
- Usa buenas practicas.
- Si es funcion, incluye docstring."""

        result = self._ask_llm(prompt, system="Eres un programador experto. Generas codigo limpio y funcional.")
        return {
            "thought": f"Generando {language}",
            "display": f"💻 Codigo generado:\n\n{result}",
            "voice": "Listo, aqui esta el codigo.",
        }