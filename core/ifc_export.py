"""Generador de archivos IFC para JARVIS/Nitro.

Usa ifcopenshell.api (dentro de FreeCAD 1.x) para construir un IFC valido
con estructura Project -> Site -> Building -> Storey -> IfcWall.
"""

import os
import subprocess
import tempfile
from pathlib import Path

from core.paths import FREECAD_CMD

TIMEOUT_IFC = 300


def _generar_script(muros, output_path, nombre_proyecto="Proyecto Nitro",
                    nombre_edificio="Edificio", nombre_nivel="Nivel 0"):
    lineas_muros = []
    for m in muros:
        x1 = float(m.get("x1", 0))
        y1 = float(m.get("y1", 0))
        x2 = float(m.get("x2", 0))
        y2 = float(m.get("y2", 0))
        grosor = float(m.get("grosor", 0.15))
        altura = float(m.get("altura", 3.0))
        nombre = str(m.get("nombre", "Muro")).replace("'", "").replace('"', "")
        lineas_muros.append(
            f"    ({x1}, {y1}, {x2}, {y2}, {grosor}, {altura}, '{nombre}'),"
        )
    muros_str = "\n".join(lineas_muros) if lineas_muros else "    # (vacio)"

    out_esc = str(output_path).replace("\\", "/")
    proy_esc = nombre_proyecto.replace("'", "").replace('"', "")
    edif_esc = nombre_edificio.replace("'", "").replace('"', "")
    nivel_esc = nombre_nivel.replace("'", "").replace('"', "")

    script = f'''"""Genera un archivo IFC con ifcopenshell.api (unidades en METROS)."""
import ifcopenshell
import ifcopenshell.api
import math
import os

OUTPUT = r"{out_esc}"
NOMBRE_PROYECTO = "{proy_esc}"
NOMBRE_EDIFICIO = "{edif_esc}"
NOMBRE_NIVEL = "{nivel_esc}"

muros = [
{muros_str}
]

print("INICIANDO: " + str(len(muros)) + " muros")

model = ifcopenshell.api.run("project.create_file", version="IFC4")

project = ifcopenshell.api.run(
    "root.create_entity", model,
    ifc_class="IfcProject",
    name=NOMBRE_PROYECTO,
)

# Unidades explicitas en METROS (no milimetros)
length_unit = model.create_entity(
    "IfcSIUnit", UnitType="LENGTHUNIT", Name="METRE"
)
area_unit = model.create_entity(
    "IfcSIUnit", UnitType="AREAUNIT", Name="SQUARE_METRE"
)
volume_unit = model.create_entity(
    "IfcSIUnit", UnitType="VOLUMEUNIT", Name="CUBIC_METRE"
)
unit_assignment = model.create_entity(
    "IfcUnitAssignment", Units=[length_unit, area_unit, volume_unit]
)
project.UnitsInContext = unit_assignment

# Contexto geometrico
model3d = ifcopenshell.api.run(
    "context.add_context", model,
    context_type="Model",
)
body = ifcopenshell.api.run(
    "context.add_context", model,
    context_type="Model",
    context_identifier="Body",
    target_view="MODEL_VIEW",
    parent=model3d,
)

# Jerarquia espacial
site = ifcopenshell.api.run(
    "root.create_entity", model,
    ifc_class="IfcSite",
    name="Terreno",
)
building = ifcopenshell.api.run(
    "root.create_entity", model,
    ifc_class="IfcBuilding",
    name=NOMBRE_EDIFICIO,
)
storey = ifcopenshell.api.run(
    "root.create_entity", model,
    ifc_class="IfcBuildingStorey",
    name=NOMBRE_NIVEL,
)

ifcopenshell.api.run(
    "aggregate.assign_object", model,
    products=[site], relating_object=project,
)
ifcopenshell.api.run(
    "aggregate.assign_object", model,
    products=[building], relating_object=site,
)
ifcopenshell.api.run(
    "aggregate.assign_object", model,
    products=[storey], relating_object=building,
)

creados = 0
for idx, (x1, y1, x2, y2, grosor, altura, nombre) in enumerate(muros):
    try:
        dx = x2 - x1
        dy = y2 - y1
        largo = math.sqrt(dx * dx + dy * dy)
        if largo < 0.01:
            continue

        angle = math.atan2(dy, dx)

        # Wall
        wall = ifcopenshell.api.run(
            "root.create_entity", model,
            ifc_class="IfcWall",
            name=nombre + "_" + str(idx),
        )
        ifcopenshell.api.run(
            "spatial.assign_container", model,
            products=[wall], relating_structure=storey,
        )

        # ObjectPlacement: ubicar el muro en su punto inicial con rotacion
        wall_placement = model.create_entity(
            "IfcLocalPlacement",
            RelativePlacement=model.create_entity(
                "IfcAxis2Placement3D",
                Location=model.create_entity(
                    "IfcCartesianPoint",
                    Coordinates=(float(x1), float(y1), 0.0)
                ),
                Axis=model.create_entity(
                    "IfcDirection", DirectionRatios=(0.0, 0.0, 1.0)
                ),
                RefDirection=model.create_entity(
                    "IfcDirection",
                    DirectionRatios=(float(math.cos(angle)), float(math.sin(angle)), 0.0),
                ),
            ),
        )
        wall.ObjectPlacement = wall_placement

        # Perfil del muro: rectangulo desplazado para que empiece en el origen local
        # IfcRectangleProfileDef centra el rectangulo en su Position
        # Asi que ponemos Position en (largo/2, 0) para que el rectangulo
        # empiece en (0,0) y termine en (largo, grosor)
        profile_position = model.create_entity(
            "IfcAxis2Placement2D",
            Location=model.create_entity(
                "IfcCartesianPoint",
                Coordinates=(float(largo) / 2.0, 0.0)
            ),
        )
        profile = model.create_entity(
            "IfcRectangleProfileDef",
            ProfileType="AREA",
            Position=profile_position,
            XDim=float(largo),
            YDim=float(grosor),
        )

        # Extrusion vertical por la altura
        solid = model.create_entity(
            "IfcExtrudedAreaSolid",
            SweptArea=profile,
            Position=model.create_entity(
                "IfcAxis2Placement3D",
                Location=model.create_entity(
                    "IfcCartesianPoint", Coordinates=(0.0, 0.0, 0.0)
                ),
            ),
            ExtrudedDirection=model.create_entity(
                "IfcDirection", DirectionRatios=(0.0, 0.0, 1.0)
            ),
            Depth=float(altura),
        )

        shape_rep = model.create_entity(
            "IfcShapeRepresentation",
            ContextOfItems=body,
            RepresentationIdentifier="Body",
            RepresentationType="SweptSolid",
            Items=[solid],
        )
        product_def = model.create_entity(
            "IfcProductDefinitionShape",
            Representations=[shape_rep],
        )
        wall.Representation = product_def

        creados += 1
    except Exception as e:
        print("WARN muro " + str(idx) + ": " + str(e))
        continue

print("MUROS CREADOS: " + str(creados))

if os.path.exists(OUTPUT):
    os.remove(OUTPUT)
model.write(OUTPUT)
print("OK_IFC: " + OUTPUT)
print("TAMANO: " + str(os.path.getsize(OUTPUT)) + " bytes")
'''
    return script


def export_walls_to_ifc(muros, output_path, nombre_proyecto="Proyecto Nitro",
                        nombre_edificio="Edificio", nombre_nivel="Nivel 0"):
    if not muros:
        return False, "No hay muros para exportar."

    if not FREECAD_CMD or not Path(FREECAD_CMD).exists():
        return False, f"No encuentro freecadcmd en {FREECAD_CMD}"

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    script = _generar_script(
        muros, output_path, nombre_proyecto, nombre_edificio, nombre_nivel
    )

    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".py", delete=False, encoding="utf-8"
    ) as f:
        f.write(script)
        sp = f.name

    try:
        r = subprocess.run(
            [FREECAD_CMD, sp],
            capture_output=True,
            text=True,
            timeout=TIMEOUT_IFC,
            encoding="utf-8",
            errors="replace",
        )
        stdout = r.stdout or ""
        if "OK_IFC:" not in stdout:
            return False, f"Fallo. Log: {stdout[-600:]}"
        return True, None
    except subprocess.TimeoutExpired:
        return False, f"Timeout de {TIMEOUT_IFC}s"
    except Exception as e:
        return False, f"Error: {e}"
    finally:
        try:
            os.unlink(sp)
        except Exception:
            pass