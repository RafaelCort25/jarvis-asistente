"""Rutas dinamicas del proyecto JARVIS/Nitro.

Resuelve:
- ROOT: raiz del proyecto (independiente del PC donde se ejecute)
- Directorios del proyecto (sandbox, memory, logs, config, skills, core)
- Rutas de ejecutables externos (FreeCAD, Blender, ODA, LibreOffice, Brave, Chrome)
  con deteccion automatica + override por variable de entorno.

Uso:
    from core.paths import ROOT, SANDBOX_DIR, FREECAD_CMD, BLENDER_CMD

    # Para verificar en tiempo de ejecucion:
    from core.paths import resumen
    print(resumen())
"""

import os
from pathlib import Path


# ─── RAÍZ DEL PROYECTO ────────────────────────────────────────────────────
# __file__ esta en core/paths.py -> parent.parent = raiz del proyecto
ROOT = Path(__file__).resolve().parent.parent

# Directorios principales del proyecto
SANDBOX_DIR = ROOT / "sandbox"
MEMORY_DIR = ROOT / "memory"
LOGS_DIR = ROOT / "logs"
CONFIG_DIR = ROOT / "config"
SKILLS_DIR = ROOT / "skills"
CORE_DIR = ROOT / "core"

# Subdirectorios de sandbox
SANDBOX_FREECAD = SANDBOX_DIR / "freecad"
SANDBOX_BLENDER = SANDBOX_DIR / "blender"
SANDBOX_DWG = SANDBOX_DIR / "dwg"
SANDBOX_IMAGES = SANDBOX_DIR / "images"
SANDBOX_MACROS = SANDBOX_DIR / "macros"
SANDBOX_UPLOADS = SANDBOX_DIR / "uploads"
SANDBOX_DOCUMENTS = SANDBOX_DIR / "documents"
SANDBOX_PDF = SANDBOX_DIR / "pdf"

# Archivos de configuracion de credenciales
ENV_N8N = ROOT / ".env.n8n.tmp"
ENV_GMAIL = ROOT / ".env.gmail.tmp"
ENV_CANVA = ROOT / ".env.canva.tmp"
ENV_MAPS = ROOT / ".env.maps.tmp"
ENV_TELEGRAM = ROOT / ".env.telegram.tmp"


# ─── HELPERS DE DETECCION DE EJECUTABLES ──────────────────────────────────
def _program_files_roots():
    """Devuelve las rutas base de Program Files (y x86)."""
    roots = []
    for var in ("PROGRAMFILES", "PROGRAMFILES(X86)", "ProgramFiles", "ProgramFiles(x86)"):
        val = os.environ.get(var)
        if val:
            roots.append(Path(val))
    # Fallback a rutas estandar
    for fallback in (r"C:\Program Files", r"C:\Program Files (x86)"):
        p = Path(fallback)
        if p not in roots:
            roots.append(p)
    return [r for r in roots if r.exists()]


def _buscar_ejecutable(*patrones):
    """Busca un ejecutable con patrones de ruta.

    Cada patron es una tupla de partes del path. Cualquier parte puede
    contener un wildcard '*'. Ejemplo:

        _buscar_ejecutable(("FreeCAD*", "bin", "freecadcmd.exe"))
        _buscar_ejecutable(("Blender Foundation", "Blender*", "blender.exe"))
        _buscar_ejecutable(("ODA", "ODAFileConverter*", "ODAFileConverter.exe"))

    Devuelve la primera ruta encontrada o None.
    """
    for base in _program_files_roots():
        for pat in patrones:
            if not pat:
                continue
            # Construir el patron glob con separadores "/"
            glob_str = "/".join(pat)
            try:
                for match in base.glob(glob_str):
                    if match.exists() and match.is_file():
                        return str(match)
            except Exception:
                continue
    return None


def _detectar(*candidatos):
    """Devuelve el primer candidato que existe como archivo, o None."""
    for c in candidatos:
        if c and Path(c).exists():
            return str(c)
    return None


# ─── EJECUTABLES EXTERNOS ─────────────────────────────────────────────────
# Estrategia: variable de entorno > deteccion automatica > None

FREECAD_CMD = (
    os.environ.get("FREECAD_CMD")
    or _buscar_ejecutable(("FreeCAD*", "bin", "freecadcmd.exe"))
    or _buscar_ejecutable(("FreeCAD*", "bin", "FreeCADCmd.exe"))
)

BLENDER_CMD = (
    os.environ.get("BLENDER_CMD")
    or _buscar_ejecutable(("Blender Foundation", "Blender*", "blender.exe"))
)

ODA_CMD = (
    os.environ.get("ODA_CMD")
    or _buscar_ejecutable(("ODA", "ODAFileConverter*", "ODAFileConverter.exe"))
)

SOFFICE_CMD = (
    os.environ.get("SOFFICE_CMD")
    or _buscar_ejecutable(("LibreOffice", "program", "soffice.exe"))
)

BRAVE_CMD = (
    os.environ.get("BRAVE_CMD")
    or _buscar_ejecutable(("BraveSoftware", "Brave-Browser", "Application", "brave.exe"))
)

CHROME_CMD = (
    os.environ.get("CHROME_CMD")
    or _buscar_ejecutable(("Google", "Chrome", "Application", "chrome.exe"))
)


# ─── UTILIDADES ───────────────────────────────────────────────────────────
def ensure_dirs():
    """Crea los directorios del proyecto si no existen."""
    for d in [
        SANDBOX_DIR, SANDBOX_FREECAD, SANDBOX_BLENDER, SANDBOX_DWG,
        SANDBOX_IMAGES, SANDBOX_MACROS, SANDBOX_UPLOADS,
        SANDBOX_DOCUMENTS, SANDBOX_PDF,
        MEMORY_DIR, LOGS_DIR, CONFIG_DIR,
    ]:
        try:
            d.mkdir(parents=True, exist_ok=True)
        except Exception:
            pass


def resumen():
    """Devuelve un dict con el estado de todas las rutas y ejecutables."""
    return {
        "ROOT": str(ROOT),
        "SANDBOX": str(SANDBOX_DIR),
        "FREECAD_CMD": FREECAD_CMD or "[no detectado]",
        "BLENDER_CMD": BLENDER_CMD or "[no detectado]",
        "ODA_CMD": ODA_CMD or "[no detectado]",
        "SOFFICE_CMD": SOFFICE_CMD or "[no detectado]",
        "BRAVE_CMD": BRAVE_CMD or "[no detectado]",
        "CHROME_CMD": CHROME_CMD or "[no detectado]",
    }


if __name__ == "__main__":
    import json
    print(json.dumps(resumen(), indent=2, ensure_ascii=False))