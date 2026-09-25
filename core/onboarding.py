"""Onboarding wizard de JARVIS/Nitro.

Detecta dependencias al primer arranque y guia al usuario paso a paso.

Uso:
    python -m core.onboarding            # Wizard interactivo
    python -m core.onboarding --check    # Solo chequeo, no interactivo
    python -m core.onboarding --reset    # Reinicia el estado de onboarding
    python -m core.onboarding --status   # JSON con estado actual (para main.py)
"""

import json
import os
import sys
from pathlib import Path

from core.paths import (
    ROOT, SANDBOX_DIR, MEMORY_DIR, LOGS_DIR, CONFIG_DIR,
    FREECAD_CMD, BLENDER_CMD, ODA_CMD, SOFFICE_CMD, BRAVE_CMD, CHROME_CMD,
    ENV_N8N, ENV_GMAIL, ENV_CANVA, ENV_MAPS, ENV_TELEGRAM,
    ensure_dirs, resumen as paths_resumen,
)

# Marcador de onboarding completado
ONBOARDING_MARKER = ROOT / ".onboarding_done"

# Modelos esperados de Ollama (por orden de prioridad)
OLLAMA_URL = "http://localhost:11434/api/tags"
MODELOS_ESPERADOS = [
    ("llama3.2:3b", "Clasificador de intent (rapido)"),
    ("qwen2.5-coder:7b", "Agente ReAct y generacion de codigo"),
    ("dolphin-mistral", "Razonamiento y chat (opcional)"),
    ("llava:7b", "Vision por pantalla (opcional)"),
    ("minicpm-v", "Vision alternativa (opcional)"),
]


# ─── CHEQUEOS ──────────────────────────────────────────────────────────────

def check_ollama():
    """Verifica si Ollama esta corriendo y lista los modelos disponibles."""
    resultado = {
        "running": False,
        "models": [],
        "expected": [],
        "url": OLLAMA_URL,
    }

    try:
        import requests
        r = requests.get(OLLAMA_URL, timeout=3)
        if r.status_code == 200:
            data = r.json()
            resultado["running"] = True
            resultado["models"] = [m.get("name", "") for m in data.get("models", [])]

            # Detectar esperados presentes
            for nombre, desc in MODELOS_ESPERADOS:
                base = nombre.split(":")[0]
                tiene = any(m.startswith(base) for m in resultado["models"])
                resultado["expected"].append({
                    "name": nombre,
                    "desc": desc,
                    "present": tiene,
                })
    except Exception as e:
        resultado["error"] = str(e)

    return resultado


def check_tools():
    """Verifica herramientas externas (via core.paths)."""
    return {
        "freecad": {"path": FREECAD_CMD, "ok": bool(FREECAD_CMD)},
        "blender": {"path": BLENDER_CMD, "ok": bool(BLENDER_CMD)},
        "oda":     {"path": ODA_CMD,     "ok": bool(ODA_CMD)},
        "soffice": {"path": SOFFICE_CMD, "ok": bool(SOFFICE_CMD)},
        "brave":   {"path": BRAVE_CMD,   "ok": bool(BRAVE_CMD)},
        "chrome":  {"path": CHROME_CMD,  "ok": bool(CHROME_CMD)},
    }


def check_credentials():
    """Verifica que archivos .env de credenciales existen."""
    archivos = {
        "n8n":      {"path": ENV_N8N,      "ok": ENV_N8N.exists(),      "oblig": False},
        "gmail":    {"path": ENV_GMAIL,    "ok": ENV_GMAIL.exists(),    "oblig": False},
        "canva":    {"path": ENV_CANVA,    "ok": ENV_CANVA.exists(),    "oblig": False},
        "maps":     {"path": ENV_MAPS,     "ok": ENV_MAPS.exists(),     "oblig": False},
        "telegram": {"path": ENV_TELEGRAM, "ok": ENV_TELEGRAM.exists(), "oblig": False},
    }
    return {k: {"path": str(v["path"]), "ok": v["ok"], "oblig": v["oblig"]} for k, v in archivos.items()}


def check_dirs():
    """Verifica/créa directorios del proyecto."""
    try:
        ensure_dirs()
        dirs = {
            "sandbox": SANDBOX_DIR,
            "memory": MEMORY_DIR,
            "logs": LOGS_DIR,
            "config": CONFIG_DIR,
        }
        return {k: {"path": str(v), "ok": v.exists()} for k, v in dirs.items()}
    except Exception as e:
        return {"error": str(e)}


def check_python():
    """Verifica Python + version minima."""
    import sys
    v = sys.version_info
    ok = (v.major, v.minor) >= (3, 10)
    return {
        "version": f"{v.major}.{v.minor}.{v.micro}",
        "ok": ok,
        "minima": "3.10",
    }


def check_all():
    """Ejecuta todos los chequeos y devuelve un dict consolidado."""
    return {
        "python": check_python(),
        "ollama": check_ollama(),
        "tools": check_tools(),
        "credentials": check_credentials(),
        "dirs": check_dirs(),
        "root": str(ROOT),
    }


# ─── PRESENTACION ──────────────────────────────────────────────────────────

def _mark(ok):
    return "[OK]" if ok else "[--]"


def print_status(status):
    """Imprime el estado formateado."""
    print()
    print("=" * 70)
    print("  JARVIS/Nitro - Estado del sistema")
    print("=" * 70)
    print()
    print(f"  Raiz del proyecto: {status['root']}")
    print()

    # Python
    py = status["python"]
    print(f"  {_mark(py['ok'])} Python {py['version']} (minimo {py['minima']})")

    # Ollama
    ol = status["ollama"]
    print()
    if ol["running"]:
        print(f"  [OK] Ollama corriendo en {ol['url']}")
        print(f"       Modelos disponibles: {len(ol['models'])}")
        for item in ol["expected"]:
            m = _mark(item["present"])
            print(f"       {m} {item['name']:<22} ({item['desc']})")
    else:
        print(f"  [--] Ollama NO esta corriendo")
        if "error" in ol:
            print(f"       {ol['error']}")
        print(f"       Inicia Ollama y vuelve a chequear.")

    # Tools
    print()
    print("  Herramientas externas:")
    for nombre, info in status["tools"].items():
        m = _mark(info["ok"])
        ruta = info["path"] or "(no detectada)"
        print(f"       {m} {nombre:<10} {ruta}")

    # Credenciales
    print()
    print("  Credenciales (.env):")
    for nombre, info in status["credentials"].items():
        m = _mark(info["ok"])
        estado = "configurado" if info["ok"] else "no configurado"
        print(f"       {m} {nombre:<10} {estado}")

    # Directorios
    print()
    print("  Directorios:")
    for nombre, info in status["dirs"].items():
        if "error" in info:
            print(f"       [--] {nombre}: error {info['error']}")
            continue
        m = _mark(info["ok"])
        print(f"       {m} {nombre:<10} {info['path']}")

    print()
    print("=" * 70)
    print()


def resumen_corto(status):
    """Devuelve un dict compacto con problemas encontrados."""
    problemas = []

    if not status["python"]["ok"]:
        problemas.append(f"Python {status['python']['version']} es menor que {status['python']['minima']}")

    if not status["ollama"]["running"]:
        problemas.append("Ollama no esta corriendo")
    else:
        faltantes = [i["name"] for i in status["ollama"]["expected"] if not i["present"]]
        if faltantes:
            problemas.append(f"Modelos faltantes: {', '.join(faltantes)}")

    tools_faltan = [k for k, v in status["tools"].items() if not v["ok"]]
    if tools_faltan:
        # Solo avisar de los obligatorios
        obligatorios_faltan = [t for t in tools_faltan if t in ("freecad", "blender")]
        if obligatorios_faltan:
            problemas.append(f"Herramientas clave no detectadas: {', '.join(obligatorios_faltan)}")

    return {
        "ok": not problemas,
        "problemas": problemas,
    }


# ─── MARCADOR ──────────────────────────────────────────────────────────────

def is_done():
    """True si el onboarding ya se completo."""
    return ONBOARDING_MARKER.exists()


def mark_done():
    """Marca el onboarding como completado."""
    try:
        ONBOARDING_MARKER.write_text("done", encoding="utf-8")
        return True
    except Exception:
        return False


def reset():
    """Elimina el marcador para forzar onboarding la proxima vez."""
    try:
        if ONBOARDING_MARKER.exists():
            ONBOARDING_MARKER.unlink()
        return True
    except Exception:
        return False


# ─── WIZARD INTERACTIVO ────────────────────────────────────────────────────

def _pedir(prompt, default=""):
    """Pide input al usuario con valor por defecto."""
    sufijo = f" [{default}]" if default else ""
    try:
        valor = input(f"  {prompt}{sufijo}: ").strip()
        return valor if valor else default
    except (EOFError, KeyboardInterrupt):
        print()
        return ""


def run_wizard():
    """Wizard interactivo de primer arranque."""
    print()
    print("=" * 70)
    print("  Bienvenido a JARVIS/Nitro")
    print("=" * 70)
    print()
    print("  Voy a revisar tu sistema y guiarte para configurar lo que falte.")
    print("  Puedes salir con Ctrl+C en cualquier momento.")
    print()

    status = check_all()
    print_status(status)

    resumen = resumen_corto(status)

    if resumen["ok"]:
        print("  Todo se ve bien. No hay nada que configurar.")
        print()
        if mark_done():
            print(f"  Marcador creado: {ONBOARDING_MARKER}")
        return True

    print("  Elementos a revisar:")
    for p in resumen["problemas"]:
        print(f"    - {p}")
    print()

    continuar = _pedir("Quieres que te guie para resolverlos? (s/n)", "s").lower()
    if continuar not in ("s", "si", "y", "yes"):
        print("  Ok. Puedes volver a ejecutar el onboarding cuando quieras:")
        print(f"  python -m core.onboarding")
        return False

    # ─── OLLAMA ──────────────────────────────────────────────────────────
    ol = status["ollama"]
    if not ol["running"]:
        print()
        print("  --- OLLAMA ---")
        print("  Ollama no esta corriendo. Pasos:")
        print("    1. Descarga e instala Ollama: https://ollama.com/download")
        print("    2. Abre una terminal y ejecuta: ollama serve")
        print("    3. En otra terminal: ollama pull llama3.2:3b")
        print("    4. Vuelve a ejecutar este wizard.")
        _pedir("Enter cuando lo tengas listo")
    else:
        faltantes = [i for i in ol["expected"] if not i["present"]]
        if faltantes:
            print()
            print("  --- MODELOS FALTANTES ---")
            for item in faltantes:
                cmd = f"ollama pull {item['name']}"
                print(f"    - {item['name']:<22} ({item['desc']})")
                print(f"      Comando: {cmd}")
            print()

    # ─── HERRAMIENTAS ────────────────────────────────────────────────────
    tools = status["tools"]
    obligatorias_faltan = [k for k in ("freecad", "blender") if not tools[k]["ok"]]
    if obligatorias_faltan:
        print()
        print("  --- HERRAMIENTAS ---")
        urls = {
            "freecad": "https://www.freecad.org/downloads.php",
            "blender": "https://www.blender.org/download/",
        }
        for k in obligatorias_faltan:
            print(f"    - {k}: {urls.get(k, '(sin URL)')}")
        print()
        print("    Sin estas, los skills de CAD y render no funcionaran.")
        print("    Los demas skills si funcionaran igual.")

    # ─── CREDENCIALES ────────────────────────────────────────────────────
    creds = status["credentials"]
    faltantes_creds = [k for k, v in creds.items() if not v["ok"]]
    if faltantes_creds:
        print()
        print("  --- CREDENCIALES OPCIONALES ---")
        for k in faltantes_creds:
            print(f"    - {k}: crea {Path(creds[k]['path']).name} con tus credenciales")
        print()
        print("    Estos son opcionales. Los skills funcionan sin ellos,")
        print("    pero no podras usar las integraciones externas (correo,")
        print("    canva, n8n, etc.).")

    # ─── FINAL ───────────────────────────────────────────────────────────
    print()
    print("=" * 70)
    finalizar = _pedir("Marcar onboarding como completado? (s/n)", "s").lower()
    if finalizar in ("s", "si", "y", "yes"):
        if mark_done():
            print(f"  Marcador creado: {ONBOARDING_MARKER}")
            print("  El wizard no volvera a aparecer.")
            print("  Para volver a ejecutarlo: python -m core.onboarding --reset")
            return True

    print("  Onboarding no marcado como completado.")
    return False


# ─── ENTRYPOINT CLI ────────────────────────────────────────────────────────

def main():
    args = sys.argv[1:]

    if "--help" in args or "-h" in args:
        print(__doc__)
        return

    if "--reset" in args:
        if reset():
            print("Onboarding reiniciado.")
        else:
            print("No se pudo reiniciar.")
        return

    if "--status" in args:
        # Devuelve JSON con el estado (para main.py)
        status = check_all()
        resumen = resumen_corto(status)
        salida = {
            "done": is_done(),
            "ok": resumen["ok"],
            "problemas": resumen["problemas"],
        }
        print(json.dumps(salida, indent=2, ensure_ascii=False))
        return

    if "--check" in args:
        # Solo chequeo, no interactivo
        status = check_all()
        print_status(status)
        resumen = resumen_corto(status)
        print(f"  Estado general: {'OK' if resumen['ok'] else 'REQUIERE ATENCION'}")
        if resumen["problemas"]:
            print("  Problemas:")
            for p in resumen["problemas"]:
                print(f"    - {p}")
        return

    # Default: wizard interactivo
    if is_done() and "--force" not in args:
        print()
        print("  El onboarding ya se completo anteriormente.")
        print("  Para volver a ejecutarlo: python -m core.onboarding --reset")
        print("  Para forzarlo ahora:      python -m core.onboarding --force")
        print()
        return

    run_wizard()


if __name__ == "__main__":
    main()