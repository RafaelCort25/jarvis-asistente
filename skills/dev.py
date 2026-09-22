import os
import re
import shutil
import subprocess
import ollama
from datetime import datetime
from pathlib import Path
from skills.base import Skill
from core.config_loader import CONFIG
from core import confirmation

# Extensiones de código soportadas
CODE_EXTS = {
    ".py", ".js", ".jsx", ".ts", ".tsx", ".java", ".c", ".cpp", ".h", ".hpp",
    ".cs", ".go", ".rs", ".rb", ".php", ".swift", ".kt", ".scala",
    ".html", ".css", ".scss", ".sass", ".less",
    ".json", ".yaml", ".yml", ".toml", ".xml", ".sql",
    ".sh", ".bash", ".ps1", ".bat",
    ".md", ".txt",
}

IGNORE_DIRS = {
    "venv", "node_modules", "__pycache__", ".git", "dist", "build",
    ".venv", "env", ".idea", ".vscode", "target", "Library",
    ".next", ".nuxt", "coverage",
}

MAX_FILE_CHARS = 8000
MAX_PROJECT_FILES = 15
RUN_TIMEOUT = 30

ROOT = Path(__file__).resolve().parent.parent


class DevSkill(Skill):
    name = "dev"
    description = "Revisa codigo, explica archivos, genera codigo, escribe y prueba"

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
        if action == "write_file":
            return self._write_file(
                params.get("path", ""),
                params.get("content", ""),
            )
        if action == "run_file":
            return self._run_file(params.get("path", ""))
        if action == "create_and_test":
            return self._create_and_test(
                params.get("description", ""),
                params.get("language", "python"),
                params.get("path", ""),
            )
        return f"Accion desconocida: {action}"

    # ─── HELPERS ─────────────────────────────────────────────────────────

    def _resolve_path(self, path_str, must_exist=True):
        """Convierte string a Path. Si must_exist=False, permite rutas nuevas."""
        if not path_str:
            return None
        raw = path_str.strip().strip('"').strip("'")
        p = Path(raw)
        if not p.is_absolute():
            p = ROOT / p
        if must_exist and not p.exists():
            return None
        return p

    def _read_file(self, path):
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

    def _clean_code_block(self, text):
        """Quita ```language ... ``` que el LLM suele añadir."""
        # Bloque con backticks
        m = re.search(r"```[a-zA-Z0-9_+-]*\n?(.*?)```", text, re.DOTALL)
        if m:
            return m.group(1).strip()
        # Si no hay bloque, devolver tal cual (limpiando backticks sueltos)
        return text.replace("```", "").strip()

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

        files = []
        for root, dirs, filenames in os.walk(path):
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

        files.sort(key=lambda x: x[1], reverse=True)
        top_files = files[:MAX_PROJECT_FILES]

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

    def _generate_code_raw(self, description, language):
        """Devuelve solo el texto del codigo, sin envolver en dict."""
        prompt = f"""Genera codigo en {language} que haga lo siguiente:
{description}

Reglas:
- Devuelve UNICAMENTE el codigo, sin explicaciones.
- Incluye comentarios utiles.
- Usa buenas practicas.
- Si es funcion, incluye docstring.
- Si es un script ejecutable, incluye un bloque main que NO use input(). Usa valores de ejemplo hardcodeados para poder ejecutarlo sin interaccion.
- NUNCA uses input() ni reads interactivos."""

        raw = self._ask_llm(prompt, system="Eres un programador experto. Generas codigo limpio y funcional.")
        return self._clean_code_block(raw)

    def _generate_code(self, description, language):
        if not description:
            return "No me dijiste que generar."

        codigo = self._generate_code_raw(description, language)
        return {
            "thought": f"Generando {language}",
            "display": f"💻 Codigo generado:\n\n```{language}\n{codigo}\n```",
            "voice": "Listo, aqui esta el codigo.",
        }

    # ─── WRITE FILE (con confirmacion) ───────────────────────────────────

    def _write_file(self, path_str, content):
        path = self._resolve_path(path_str, must_exist=False)
        if not path:
            return f"Ruta invalida: {path_str}"
        if not content or not content.strip():
            return "No hay contenido para escribir."

        # Detectar si sobrescribe
        existe = path.exists()
        accion = "sobrescribir" if existe else "crear"

        # Si está fuera de ROOT, avisar
        fuera_de_root = False
        try:
            path.relative_to(ROOT)
        except ValueError:
            fuera_de_root = True

        aviso = ""
        if existe:
            aviso = f" (el archivo ya existe, se hara backup .bak)"
        if fuera_de_root:
            aviso += " [ATENCION: fuera del proyecto C:\\JARVIS]"
                    # Validacion de seguridad: si el archivo esta fuera de C:\JARVIS
        # y no esta en sandbox, pedir doble confirmacion
        dentro_de_proyecto = False
        try:
            path.relative_to(ROOT)
            dentro_de_proyecto = True
        except ValueError:
            pass
        if not dentro_de_proyecto:
            return f"Ruta fuera del proyecto, bloqueado por seguridad: {path}"

        summary = f"{accion} archivo: {path}{aviso}"

        if not confirmation.require("dev", "write_file", summary):
            return "Cancelado."

        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            if existe:
                backup = path.with_suffix(path.suffix + ".bak")
                shutil.copy2(path, backup)
            path.write_text(content, encoding="utf-8")
        except Exception as e:
            return f"Error escribiendo: {e}"

        return f"Archivo {'sobrescrito' if existe else 'creado'}: {path}"

    # ─── RUN FILE (con confirmacion) ─────────────────────────────────────

    def _run_file(self, path_str):
        path = self._resolve_path(path_str)
        if not path or not path.is_file():
            return f"No encontre el archivo: {path_str}"

        ext = path.suffix.lower()
        if ext == ".py":
            cmd = ["python", str(path)]
        elif ext == ".js":
            cmd = ["node", str(path)]
        elif ext == ".java":
            # Compilar y ejecutar
            cmd = ["java", str(path)]
        elif ext in (".sh", ".bash"):
            cmd = ["bash", str(path)]
        elif ext == ".ps1":
            cmd = ["powershell", "-File", str(path)]
        else:
            return f"No se ejecutar {ext}. Solo .py, .js, .java, .sh, .ps1"

        summary = f"Ejecutar {path.name}: {' '.join(cmd)}"
        if not confirmation.require("dev", "run_file", summary):
            return "Cancelado."

        try:
            result = subprocess.run(
                cmd,
                cwd=str(path.parent),
                capture_output=True,
                stdin=subprocess.DEVNULL,
                text=True,
                timeout=RUN_TIMEOUT,
                encoding="utf-8",
                errors="replace",
            )
        except subprocess.TimeoutExpired:
            return f"Timeout: el archivo tardo mas de {RUN_TIMEOUT}s."
        except FileNotFoundError as e:
            return f"No encontre el interprete: {e}"
        except Exception as e:
            return f"Error ejecutando: {e}"

        stdout = (result.stdout or "").strip()
        stderr = (result.stderr or "").strip()

        def clip(s, n=1500):
            return s if len(s) <= n else s[:n] + f"\n... (recortado, {len(s)-n} mas)"

        parts = [f"$ {' '.join(cmd)}", ""]
        if stdout:
            parts.append(f"[stdout]\n{clip(stdout)}")
        if stderr:
            parts.append(f"[stderr]\n{clip(stderr)}")
        parts.append(f"[exit code: {result.returncode}]")

        return "\n".join(parts)

    # ─── CREATE AND TEST (ciclo completo) ────────────────────────────────

    def _create_and_test(self, description, language, path_str):
        if not description:
            return "No me dijiste que crear."
        if not path_str:
            return "Necesito un path donde guardar el archivo."

        path = self._resolve_path(path_str, must_exist=False)
        if not path:
            return f"Ruta invalida: {path_str}"

        # 1. Generar codigo
        print(f"[DEV] Generando {language} con {self.model}...")
        codigo = self._generate_code_raw(description, language)
        if not codigo or codigo.startswith("[ERROR LLM]"):
            return f"Error generando codigo: {codigo}"

        # 2. Mostrar y confirmar escritura
        preview = codigo if len(codigo) <= 1500 else codigo[:1500] + "\n... (recortado)"
        print(f"\n[DEV] Codigo propuesto ({len(codigo)} chars):\n")
        print(preview)
        print()

        summary = f"Escribir {language} en {path} ({len(codigo)} chars)"
        if not confirmation.require("dev", "create_and_test", summary):
            return "Cancelado por el usuario."

        # 3. Escribir
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            if path.exists():
                backup = path.with_suffix(path.suffix + ".bak")
                shutil.copy2(path, backup)
            path.write_text(codigo, encoding="utf-8")
        except Exception as e:
            return f"Error escribiendo: {e}"

        print(f"[DEV] Archivo escrito: {path}")

        # 4. Confirmar ejecucion (si es ejecutable)
        ext = path.suffix.lower()
        if ext not in (".py", ".js", ".java", ".sh", ".ps1"):
            return f"Codigo guardado en {path}. (Formato no ejecutable, no se corre test.)"

        if not confirmation.require("dev", "run_file", f"Ejecutar {path.name} como test"):
            return f"Codigo guardado en {path}. Test omitido por el usuario."

        # 5. Ejecutar
        run_result = self._run_file_internal(path)
        return f"Codigo guardado en {path}.\n\nResultado del test:\n{run_result}"

    def _run_file_internal(self, path):
        """Ejecuta un archivo SIN pedir confirmacion (asumimos que ya se pidio)."""
        ext = path.suffix.lower()
        if ext == ".py":
            cmd = ["python", str(path)]
        elif ext == ".js":
            cmd = ["node", str(path)]
        elif ext == ".java":
            cmd = ["java", str(path)]
        elif ext in (".sh", ".bash"):
            cmd = ["bash", str(path)]
        elif ext == ".ps1":
            cmd = ["powershell", "-File", str(path)]
        else:
            return f"(Formato {ext} no ejecutable.)"

        try:
            result = subprocess.run(
                cmd,
                cwd=str(path.parent),
                capture_output=True,
                stdin=subprocess.DEVNULL,
                text=True,
                timeout=RUN_TIMEOUT,
                encoding="utf-8",
                errors="replace",
            )
        except subprocess.TimeoutExpired:
            return f"Timeout ({RUN_TIMEOUT}s)."
        except Exception as e:
            return f"Error ejecutando: {e}"

        stdout = (result.stdout or "").strip()
        stderr = (result.stderr or "").strip()
        parts = []
        if stdout:
            parts.append(stdout[:1200])
        if stderr:
            parts.append(f"[stderr]\n{stderr[:800]}")
        parts.append(f"[exit code: {result.returncode}]")
        return "\n".join(parts)