"""Genera SKILLS.md automaticamente desde skills/*.py.

Uso:
    python scripts/generate_skills_md.py
"""
import re
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SKILLS_DIR = ROOT / "skills"
OUTPUT = ROOT / "SKILLS.md"

# Categorizacion manual (se puede ajustar)
CATEGORIAS = {
    "Fundamentales": ["system", "desktop", "browser", "files", "clipboard", "terminal", "translate"],
    "Productividad": ["office", "edit", "pdf", "docs", "gmail", "calendar", "notion", "n8n", "scheduler", "productivity"],
    "Dev y tecnologia": ["dev", "git", "vision"],
    "Multimedia": ["image", "audio", "video", "retouch", "education"],
    "CAD y 3D": ["dwg", "freecad", "blender", "maps"],
    "Integraciones": ["spotify", "canva", "telegram"],
    "Entretenimiento": ["frases", "chiste", "entertainment", "weather", "alarm", "macro"],
}

# Orden de aparicion deseado
ORDEN_FINAL = [
    "Fundamentales", "Productividad", "Dev y tecnologia",
    "Multimedia", "CAD y 3D", "Integraciones", "Entretenimiento",
]


def extraer_info_skill(path):
    """Extrae info de un archivo de skill."""
    c = path.read_text(encoding="utf-8-sig", errors="replace")

    # Descripcion: docstring del modulo (primera linea util)
    descripcion = ""
    docstring_match = re.match(r'\s*"""(.+?)"""', c, re.DOTALL)
    if docstring_match:
        lineas = [l.strip() for l in docstring_match.group(1).strip().split("\n")]
        descripcion = lineas[0] if lineas else ""

    # Nombre de la clase (XXXSkill)
    clase_match = re.search(r"class\s+([A-Z][A-Za-z0-9]+Skill)\b", c)
    clase = clase_match.group(1) if clase_match else "?"

    # Acciones: if action == "xxx"
    acciones = sorted(set(re.findall(r'if\s+action\s*==\s*"([a-z_0-9]+)"', c)))

    # Si la skill tiene un "name = 'xxx'" en la clase, usarlo
    name_match = re.search(r'name\s*=\s*"([a-z_0-9]+)"', c)
    skill_name = name_match.group(1) if name_match else path.stem

    return {
        "skill_name": skill_name,
        "clase": clase,
        "descripcion": descripcion or f"Skill {skill_name}",
        "acciones": acciones,
        "archivo": path.name,
    }


def generar_markdown(skills_por_categoria, total_skills, total_acciones):
    lines = []
    lines.append("# SKILLS.md — Catálogo completo de skills de Senna\n")
    lines.append(f"Documentación de las **{total_skills} skills operativas** de Senna "
                 f"con un total de **{total_acciones} acciones**.\n")
    lines.append(f"**Última actualización:** {datetime.now().strftime('%Y-%m-%d')} "
                 f"(generado automáticamente por `scripts/generate_skills_md.py`)\n")
    lines.append("**Niveles de riesgo:**")
    lines.append("- 🟢 **low** — No requiere confirmación. Solo lectura o acciones inocuas.")
    lines.append("- 🟡 **medium** — Pide confirmación al usuario antes de ejecutar.")
    lines.append("- 🔴 **high** — Pide confirmación con advertencia (acciones destructivas o irreversibles).\n")
    lines.append("---\n")

    # Índice
    lines.append("## 📑 Índice por categoría\n")
    for i, cat in enumerate(ORDEN_FINAL, 1):
        n = len(skills_por_categoria.get(cat, []))
        lines.append(f"{i}. [{cat}](#{cat.lower().replace(' ', '-').replace('í', 'i')}) ({n} skills)")
    lines.append("")
    lines.append("---\n")

    # Secciones
    for cat in ORDEN_FINAL:
        skills = skills_por_categoria.get(cat, [])
        if not skills:
            continue
        lines.append(f"## {cat}\n")
        for s in skills:
            lines.append(f"### `{s['skill_name']}`")
            lines.append(f"{s['descripcion']}\n")
            lines.append(f"**Clase:** `{s['clase']}`  ")
            lines.append(f"**Archivo:** `skills/{s['archivo']}`  ")
            lines.append(f"**Acciones:** {len(s['acciones'])}\n")
            if s["acciones"]:
                for a in s["acciones"]:
                    lines.append(f"- `{a}`")
            lines.append("")
        lines.append("---\n")

    return "\n".join(lines)


def main():
    print(f"[INFO] Leyendo {SKILLS_DIR}...")
    archivos = sorted(p for p in SKILLS_DIR.glob("*.py") if p.stem not in ("__init__", "base"))

    skills_info = []
    for p in archivos:
        try:
            info = extraer_info_skill(p)
            skills_info.append(info)
        except Exception as e:
            print(f"[WARN] Error con {p.name}: {e}")

    total_skills = len(skills_info)
    total_acciones = sum(len(s["acciones"]) for s in skills_info)
    print(f"[OK] {total_skills} skills, {total_acciones} acciones")

    # Agrupar por categoria
    por_categoria = {}
    sin_categoria = []

    # Mapa inverso: skill -> categoria
    skill_a_cat = {}
    for cat, skills_list in CATEGORIAS.items():
        for sk in skills_list:
            skill_a_cat[sk] = cat

    for s in skills_info:
        nombre = s["skill_name"]
        cat = skill_a_cat.get(nombre)
        if cat:
            por_categoria.setdefault(cat, []).append(s)
        else:
            sin_categoria.append(s)

    # Skills sin categoria -> a "Otras"
    if sin_categoria:
        por_categoria.setdefault("Otras", []).extend(sin_categoria)
        if "Otras" not in ORDEN_FINAL:
            ORDEN_FINAL.append("Otras")

    # Ordenar skills dentro de cada categoria alfabeticamente
    for cat in por_categoria:
        por_categoria[cat].sort(key=lambda x: x["skill_name"])

    print("\n[INFO] Distribucion por categoria:")
    for cat in ORDEN_FINAL:
        n = len(por_categoria.get(cat, []))
        if n:
            print(f"  {cat}: {n}")

    if sin_categoria:
        print(f"\n[WARN] Skills sin categoria ({len(sin_categoria)}):")
        for s in sin_categoria:
            print(f"  - {s['skill_name']}")

    # Generar
    contenido = generar_markdown(por_categoria, total_skills, total_acciones)
    OUTPUT.write_text(contenido, encoding="utf-8")
    print(f"\n[OK] Generado: {OUTPUT}")
    print(f"[OK] Tamano: {len(contenido)} chars")


if __name__ == "__main__":
    main()
