"""Auto-registro de skills creadas por el usuario.

Cuando el Skill Creator genera una nueva skill, este modulo se encarga
de registrarla en router, schemas y confirmation.
"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _extraer_acciones(codigo):
    """Extrae las acciones del run() del codigo."""
    return list(set(re.findall(r'action\s*==\s*["\'](\w+)["\']', codigo)))


def _extraer_frases_trigger(nombre, acciones):
    """Genera frases tipicas para activar la skill."""
    frases = []
    for accion in acciones:
        # Variantes comunes
        frases.append(f"{accion} {nombre}")
        frases.append(f"haz {nombre}")
    # Frase generica
    frases.append(f"usa {nombre}")
    frases.append(f"{nombre}")
    return list(set(frases))


def registrar_skill(nombre, codigo=None):
    """Registra una skill en el router.

    - Importa dinamicamente la clase
    - La añade a Router.skills
    - Añade QM (quick_match) generico
    - Añade schema y confirmation basicos

    Devuelve dict {ok, error, acciones, frases}
    """
    result = {"ok": False, "error": None, "acciones": [], "frases": []}

    # 1. Importar la clase
    try:
        modulo = __import__(f"skills.{nombre}", fromlist=[nombre])
    except Exception as e:
        result["error"] = f"Error importando skill: {e}"
        return result

    # Buscar la clase que herede de Skill
    clase = None
    for attr_name in dir(modulo):
        attr = getattr(modulo, attr_name)
        if isinstance(attr, type) and attr_name.endswith("Skill") and attr_name != "Skill":
            clase = attr
            break

    if not clase:
        result["error"] = f"No encontre una clase *Skill en skills/{nombre}.py"
        return result

    # 2. Leer codigo para extraer acciones
    if codigo is None:
        p = ROOT / "skills" / f"{nombre}.py"
        codigo = p.read_text(encoding="utf-8") if p.exists() else ""

    acciones = _extraer_acciones(codigo)
    frases = _extraer_frases_trigger(nombre, acciones)

    result["acciones"] = acciones
    result["frases"] = frases
    result["ok"] = True
    result["clase"] = clase

    return result


def generar_bloque_qm(nombre, acciones, frases):
    """Genera el bloque de codigo para añadir a _quick_match."""
    lineas = [
        f"        # === SKILL AUTO-GENERADA: {nombre} ===",
        "        if any(p in t for p in [",
    ]
    for f in frases[:6]:
        lineas.append(f'            "{f}",')
    lineas.append("        ]):")
    if acciones:
        lineas.append(f'            return [{{"skill": "{nombre}", "action": "{acciones[0]}", "params": {{}}}}]')
    lineas.append("")
    return "\n".join(lineas)


def generar_bloque_router_init(nombre, clase=None):
    """Genera el import + registro para Router.__init__.

    clase: nombre real de la clase (opcional). Si no se pasa, se deduce.
    """
    if clase is None:
        # Intentar deducir el nombre de clase del modulo
        try:
            modulo = __import__(f"skills.{nombre}", fromlist=[nombre])
            for attr_name in dir(modulo):
                attr = getattr(modulo, attr_name)
                if isinstance(attr, type) and attr_name.endswith("Skill") and attr_name != "Skill":
                    clase = attr_name
                    break
        except Exception:
            pass
    if clase is None:
        clase = nombre.capitalize() + "Skill"
    return (
        f"from skills.{nombre} import {clase}\n"
        f'    "{nombre}": {clase}(),'
    )


def generar_bloque_schema(nombre, acciones):
    """Genera el bloque para schemas.py."""
    lineas = [f'    "{nombre}": {{']
    for accion in acciones:
        lineas.append(f'        "{accion}": {{}},')
    lineas.append("    },")
    return "\n".join(lineas)


def generar_bloque_confirmation(nombre, acciones):
    """Genera el bloque para confirmation.py (nivel low por defecto)."""
    lineas = []
    for accion in acciones:
        lineas.append(f'    ("{nombre}", "{accion}"): "low",')
    return "\n".join(lineas)


if __name__ == "__main__":
    # Test con la skill chiste
    print("=== Test de registro de 'chiste' ===")
    result = registrar_skill("chiste")
    print(f"OK: {result['ok']}")
    if result["error"]:
        print(f"Error: {result['error']}")
    print(f"Acciones: {result['acciones']}")
    print(f"Frases trigger: {result['frases']}")
    print()
    print("=== Bloque para _quick_match ===")
    print(generar_bloque_qm("chiste", result["acciones"], result["frases"]))
    print()
    print("=== Bloque para Router.__init__ ===")
    print(generar_bloque_router_init("chiste", result.get("clase").__name__ if result.get("clase") else None))
    print()
    print("=== Bloque para schemas.py ===")
    print(generar_bloque_schema("chiste", result["acciones"]))
    print()
    print("=== Bloque para confirmation.py ===")
    print(generar_bloque_confirmation("chiste", result["acciones"]))
