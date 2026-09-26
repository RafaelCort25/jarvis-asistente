"""Auto-aplica el registro de una skill en router/schemas/confirmation.

Se llama desde skill_creator tras crear una skill nueva.
"""
import re
import shutil
from datetime import datetime
from pathlib import Path

from core import skill_registry

ROOT = Path(__file__).resolve().parent.parent


def _backup(archivo):
    """Hace backup de un archivo antes de modificarlo."""
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_dir = ROOT / "backups" / f"skill_registry_{ts}"
    backup_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(archivo, backup_dir / archivo.name)
    return backup_dir


def _aplicar_router_init(nombre, clase):
    """Anade el import + registro en Router.__init__."""
    p = ROOT / "core" / "router.py"
    c = p.read_text(encoding="utf-8")

    if f'"{nombre}":' in c:
        return False, "Ya esta registrada en Router.__init__"

    # 1. Anadir import despues del ultimo import de skills
    m = list(re.finditer(r'^from skills\.\w+ import \w+$', c, re.MULTILINE))
    if not m:
        return False, "No encontre imports de skills"

    ultimo = m[-1]
    nuevo_import = f'\nfrom skills.{nombre} import {clase}'
    c = c[:ultimo.end()] + nuevo_import + c[ultimo.end():]

    # 2. Anadir registro en self.skills = {...}
    # Buscar la ultima entrada antes del cierre del dict
    m_skills = re.search(r'self\.skills\s*=\s*\{', c)
    if not m_skills:
        return False, "No encontre self.skills = {"

    # Encontrar el cierre del dict
    inicio = m_skills.end()
    depth = 1
    i = inicio
    while i < len(c) and depth > 0:
        if c[i] == "{":
            depth += 1
        elif c[i] == "}":
            depth -= 1
        i += 1
    cierre = i - 1  # posicion del }

    # Insertar antes del cierre
    nuevo_reg = f'\n            "{nombre}": {clase}(),'
    c = c[:cierre] + nuevo_reg + "\n        " + c[cierre:]

    p.write_text(c, encoding="utf-8")
    return True, f"Import + registro anadidos en {p.name}"


def _aplicar_qm(nombre, acciones, frases):
    """Anade el bloque QM a _quick_match."""
    p = ROOT / "core" / "router.py"
    c = p.read_text(encoding="utf-8")

    if f'# === SKILL AUTO-GENERADA: {nombre} ===' in c:
        return False, "QM ya existe"

    bloque = skill_registry.generar_bloque_qm(nombre, acciones, frases)

    # Insertar ANTES del bloque MAPS (para que no se lo coma)
    ancla_maps = "        # MAPS: buscar edificios reales en OpenStreetMap"
    if ancla_maps in c:
        # Encontrar el inicio del bloque con ═══ antes de MAPS
        idx = c.find(ancla_maps)
        inicio = idx
        for i in range(idx - 1, max(0, idx - 300), -1):
            if c[i] == "\n":
                j = c.find("═", i, idx)
                if j > 0:
                    inicio = c.rfind("\n", 0, j) + 1
                    break
        nuevo = bloque + "\n" + c[inicio:]
        c = c[:inicio] + nuevo
        p.write_text(c, encoding="utf-8")
        return True, f"Bloque QM anadido antes de MAPS en {p.name}"

    # Fallback: insertar antes de return None
    anclas = [
        "        return None\n\n    def _normalize",
        "        return None\n    def _normalize",
    ]
    for ancla in anclas:
        if ancla in c:
            sep = "\n\n" if "\n\n" in ancla else "\n"
            nuevo = bloque + "        return None" + sep + "    def _normalize"
            c = c.replace(ancla, nuevo, 1)
            p.write_text(c, encoding="utf-8")
            return True, f"Bloque QM anadido (fallback) en {p.name}"
    return False, "No encontre donde insertar el QM"


def _aplicar_schema(nombre, acciones):
    """Anade el schema de la skill."""
    p = ROOT / "core" / "schemas.py"
    c = p.read_text(encoding="utf-8")

    if f'"{nombre}":' in c:
        return False, "Schema ya existe"

    # Buscar el cierre del dict SCHEMAS
    m = re.search(r'SKILLS_VALIDAS\s*=\s*\{', c)
    if not m:
        return False, "No encontre SKILLS_VALIDAS = {"

    inicio = m.end()
    depth = 1
    i = inicio
    while i < len(c) and depth > 0:
        if c[i] == "{":
            depth += 1
        elif c[i] == "}":
            depth -= 1
        i += 1
    cierre = i - 1

    lineas = [f'        "{nombre}": {{']
    for accion in sorted(acciones):
        lineas.append(f'            "{accion}": {{}},')
    lineas.append("        },")
    bloque = "\n" + "\n".join(lineas)

    c = c[:cierre] + bloque + "\n    " + c[cierre:]
    p.write_text(c, encoding="utf-8")
    return True, f"Schema anadido en {p.name}"


def _aplicar_confirmation(nombre, acciones):
    """Anade niveles de riesgo 'low' para las acciones."""
    p = ROOT / "core" / "confirmation.py"
    c = p.read_text(encoding="utf-8")

    if f'("{nombre}",' in c:
        return False, "Confirmation ya existe"

    # Buscar el cierre del RISK_LEVELS
    m = re.search(r'RISK_LEVELS\s*=\s*\{', c)
    if not m:
        return False, "No encontre RISK_LEVELS = {"

    inicio = m.end()
    depth = 1
    i = inicio
    while i < len(c) and depth > 0:
        if c[i] == "{":
            depth += 1
        elif c[i] == "}":
            depth -= 1
        i += 1
    cierre = i - 1

    lineas = [f'\n    # Skill auto-generada: {nombre}']
    for accion in sorted(acciones):
        lineas.append(f'    ("{nombre}", "{accion}"): "low",')
    bloque = "\n".join(lineas)

    c = c[:cierre] + bloque + "\n    " + c[cierre:]
    p.write_text(c, encoding="utf-8")
    return True, f"Confirmation anadido en {p.name}"


def aplicar_registro(nombre):
    """Aplica el registro completo. Devuelve dict con detalle."""
    # 1. Extraer info
    reg = skill_registry.registrar_skill(nombre)
    if not reg["ok"]:
        return {"ok": False, "error": reg["error"], "pasos": []}

    acciones = reg["acciones"]
    frases = reg["frases"]
    clase = reg["clase"].__name__

    pasos = []

    # 2. Hacer backup de los 3 archivos
    for fname in ["router.py", "schemas.py", "confirmation.py"]:
        archivo = ROOT / "core" / fname
        if archivo.exists():
            _backup(archivo)

    # 3. Aplicar cada cambio
    ok, msg = _aplicar_router_init(nombre, clase)
    pasos.append(f"Router init: {msg}")

    ok, msg = _aplicar_qm(nombre, acciones, frases)
    pasos.append(f"Quick match: {msg}")

    ok, msg = _aplicar_schema(nombre, acciones)
    pasos.append(f"Schema: {msg}")

    ok, msg = _aplicar_confirmation(nombre, acciones)
    pasos.append(f"Confirmation: {msg}")

    return {"ok": True, "error": None, "pasos": pasos, "acciones": acciones, "clase": clase}


if __name__ == "__main__":
    print("=== Aplicando registro de 'chiste' ===")
    r = aplicar_registro("chiste")
    print(f"OK: {r['ok']}")
    if r["error"]:
        print(f"Error: {r['error']}")
    print(f"Acciones: {r.get('acciones')}")
    print(f"Clase: {r.get('clase')}")
    print()
    print("Pasos:")
    for p in r.get("pasos", []):
        print(f"  {p}")
