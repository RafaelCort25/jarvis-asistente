"""Generador de archivos IFC para JARVIS/Nitro.

Soporta:
- Muros (IfcWall)
- Puertas (IfcDoor)
- Ventanas (IfcWindow)
- Estructura Project -> Site -> Building -> Storey
"""

import os
import subprocess
import tempfile
from pathlib import Path

from core.paths import FREECAD_CMD

TIMEOUT_IFC = 300


def _generar_script(muros, puertas, ventanas, output_path,
                    nombre_proyecto="Proyecto Nitro",
                    nombre_edificio="Edificio", nombre_nivel="Nivel 0"):
    lineas_muros = []
    for m in muros:
        x1 = float(m.get("x1", 0)); y1 = float(m.get("y1", 0))
        x2 = float(m.get("x2", 0)); y2 = float(m.get("y2", 0))
        grosor = float(m.get("grosor", 0.15))
        altura = float(m.get("altura", 3.0))
        nombre = str(m.get("nombre", "Muro")).replace("'", "").replace('"', "")
        lineas_muros.append(
            f"    ({x1}, {y1}, {x2}, {y2}, {grosor}, {altura}, '{nombre}'),"
        )
    muros_str = "\n".join(lineas_muros) if lineas_muros else "    # (vacio)"

    lineas_puertas = []
    for p in puertas:
        x = float(p.get("x", 0)); y = float(p.get("y", 0))
        ancho = float(p.get("ancho", 0.9))
        alto = float(p.get("alto", 2.1))
        peana = float(p.get("altura_peana", 0.0))
        orient = str(p.get("orientacion", "horizontal"))
        nombre = str(p.get("nombre", "Puerta")).replace("'", "").replace('"', "")
        lineas_puertas.append(
            f"    ({x}, {y}, {ancho}, {alto}, {peana}, '{orient}', '{nombre}'),"
        )
    puertas_str = "\n".join(lineas_puertas) if lineas_puertas else "    # (vacio)"

    lineas_ventanas = []
    for v in ventanas:
        x = float(v.get("x", 0)); y = float(v.get("y", 0))
        ancho = float(v.get("ancho", 1.5))
        alto = float(v.get("alto", 1.2))
        peana = float(v.get("altura_peana", 0.9))
        orient = str(v.get("orientacion", "horizontal"))
        nombre = str(v.get("nombre", "Ventana")).replace("'", "").replace('"', "")
        lineas_ventanas.append(
            f"    ({x}, {y}, {ancho}, {alto}, {peana}, '{orient}', '{nombre}'),"
        )
    ventanas_str = "\n".join(lineas_ventanas) if lineas_ventanas else "    # (vacio)"

    out_esc = str(output_path).replace("\\", "/")
    proy_esc = nombre_proyecto.replace("'", "").replace('"', "")
    edif_esc = nombre_edificio.replace("'", "").replace('"', "")
    nivel_esc = nombre_nivel.replace("'", "").replace('"', "")

    script = f'''"""Genera IFC con muros + puertas + ventanas."""
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
puertas = [
{puertas_str}
]
ventanas = [
{ventanas_str}
]

print("INICIANDO: " + str(len(muros)) + " muros, " + str(len(puertas)) + " puertas, " + str(len(ventanas)) + " ventanas")

model = ifcopenshell.api.run("project.create_file", version="IFC4")
project = ifcopenshell.api.run("root.create_entity", model, ifc_class="IfcProject", name=NOMBRE_PROYECTO)

length_unit = model.create_entity("IfcSIUnit", UnitType="LENGTHUNIT", Name="METRE")
area_unit = model.create_entity("IfcSIUnit", UnitType="AREAUNIT", Name="SQUARE_METRE")
volume_unit = model.create_entity("IfcSIUnit", UnitType="VOLUMEUNIT", Name="CUBIC_METRE")
unit_assignment = model.create_entity("IfcUnitAssignment", Units=[length_unit, area_unit, volume_unit])
project.UnitsInContext = unit_assignment

model3d = ifcopenshell.api.run("context.add_context", model, context_type="Model")
body = ifcopenshell.api.run("context.add_context", model, context_type="Model",
    context_identifier="Body", target_view="MODEL_VIEW", parent=model3d)

site = ifcopenshell.api.run("root.create_entity", model, ifc_class="IfcSite", name="Terreno")
building = ifcopenshell.api.run("root.create_entity", model, ifc_class="IfcBuilding", name=NOMBRE_EDIFICIO)
storey = ifcopenshell.api.run("root.create_entity", model, ifc_class="IfcBuildingStorey", name=NOMBRE_NIVEL)

ifcopenshell.api.run("aggregate.assign_object", model, products=[site], relating_object=project)
ifcopenshell.api.run("aggregate.assign_object", model, products=[building], relating_object=site)
ifcopenshell.api.run("aggregate.assign_object", model, products=[storey], relating_object=building)


def crear_caja(nombre, x, y, ancho, alto, peana, orient, ifc_class):
    """Crea un elemento tipo caja (puerta/ventana) en la posicion dada."""
    dx = 1.0 if orient == "horizontal" else 0.0
    dy = 0.0 if orient == "horizontal" else 1.0

    elem = ifcopenshell.api.run("root.create_entity", model, ifc_class=ifc_class, name=nombre)
    ifcopenshell.api.run("spatial.assign_container", model, products=[elem], relating_structure=storey)

    placement = model.create_entity(
        "IfcLocalPlacement",
        RelativePlacement=model.create_entity(
            "IfcAxis2Placement3D",
            Location=model.create_entity("IfcCartesianPoint",
                Coordinates=(float(x), float(y), float(peana))),
            Axis=model.create_entity("IfcDirection", DirectionRatios=(0.0, 0.0, 1.0)),
            RefDirection=model.create_entity("IfcDirection", DirectionRatios=(dx, dy, 0.0)),
        ),
    )
    elem.ObjectPlacement = placement

    profile_position = model.create_entity(
        "IfcAxis2Placement2D",
        Location=model.create_entity("IfcCartesianPoint",
            Coordinates=(float(ancho) / 2.0, 0.0)),
    )
    profile = model.create_entity("IfcRectangleProfileDef", ProfileType="AREA",
        Position=profile_position, XDim=float(ancho), YDim=0.10)

    solid = model.create_entity("IfcExtrudedAreaSolid",
        SweptArea=profile,
        Position=model.create_entity("IfcAxis2Placement3D",
            Location=model.create_entity("IfcCartesianPoint", Coordinates=(0.0, 0.0, 0.0))),
        ExtrudedDirection=model.create_entity("IfcDirection", DirectionRatios=(0.0, 0.0, 1.0)),
        Depth=float(alto))

    shape_rep = model.create_entity("IfcShapeRepresentation",
        ContextOfItems=body, RepresentationIdentifier="Body",
        RepresentationType="SweptSolid", Items=[solid])
    product_def = model.create_entity("IfcProductDefinitionShape", Representations=[shape_rep])
    elem.Representation = product_def
    return elem


# MUROS
creados_m = 0
for idx, (x1, y1, x2, y2, grosor, altura, nombre) in enumerate(muros):
    try:
        dx = x2 - x1; dy = y2 - y1
        largo = math.sqrt(dx * dx + dy * dy)
        if largo < 0.01:
            continue
        angle = math.atan2(dy, dx)
        wall = ifcopenshell.api.run("root.create_entity", model, ifc_class="IfcWall", name=nombre + "_" + str(idx))
        ifcopenshell.api.run("spatial.assign_container", model, products=[wall], relating_structure=storey)
        placement = model.create_entity("IfcLocalPlacement",
            RelativePlacement=model.create_entity("IfcAxis2Placement3D",
                Location=model.create_entity("IfcCartesianPoint", Coordinates=(float(x1), float(y1), 0.0)),
                Axis=model.create_entity("IfcDirection", DirectionRatios=(0.0, 0.0, 1.0)),
                RefDirection=model.create_entity("IfcDirection",
                    DirectionRatios=(float(math.cos(angle)), float(math.sin(angle)), 0.0))))
        wall.ObjectPlacement = placement
        profile_position = model.create_entity("IfcAxis2Placement2D",
            Location=model.create_entity("IfcCartesianPoint", Coordinates=(float(largo) / 2.0, 0.0)))
        profile = model.create_entity("IfcRectangleProfileDef", ProfileType="AREA",
            Position=profile_position, XDim=float(largo), YDim=float(grosor))
        solid = model.create_entity("IfcExtrudedAreaSolid", SweptArea=profile,
            Position=model.create_entity("IfcAxis2Placement3D",
                Location=model.create_entity("IfcCartesianPoint", Coordinates=(0.0, 0.0, 0.0))),
            ExtrudedDirection=model.create_entity("IfcDirection", DirectionRatios=(0.0, 0.0, 1.0)),
            Depth=float(altura))
        shape_rep = model.create_entity("IfcShapeRepresentation", ContextOfItems=body,
            RepresentationIdentifier="Body", RepresentationType="SweptSolid", Items=[solid])
        product_def = model.create_entity("IfcProductDefinitionShape", Representations=[shape_rep])
        wall.Representation = product_def
        creados_m += 1
    except Exception as e:
        print("WARN muro " + str(idx) + ": " + str(e))

print("MUROS CREADOS: " + str(creados_m))

# PUERTAS
creados_p = 0
for idx, (x, y, ancho, alto, peana, orient, nombre) in enumerate(puertas):
    try:
        crear_caja(nombre + "_" + str(idx), x, y, ancho, alto, peana, orient, "IfcDoor")
        creados_p += 1
    except Exception as e:
        print("WARN puerta " + str(idx) + ": " + str(e))

print("PUERTAS CREADAS: " + str(creados_p))

# VENTANAS
creados_v = 0
for idx, (x, y, ancho, alto, peana, orient, nombre) in enumerate(ventanas):
    try:
        crear_caja(nombre + "_" + str(idx), x, y, ancho, alto, peana, orient, "IfcWindow")
        creados_v += 1
    except Exception as e:
        print("WARN ventana " + str(idx) + ": " + str(e))

print("VENTANAS CREADAS: " + str(creados_v))

if os.path.exists(OUTPUT):
    os.remove(OUTPUT)
model.write(OUTPUT)
print("OK_IFC: " + OUTPUT)
print("TAMANO: " + str(os.path.getsize(OUTPUT)) + " bytes")
'''
    return script


def export_walls_to_ifc(muros, output_path, puertas=None, ventanas=None,
                        nombre_proyecto="Proyecto Nitro",
                        nombre_edificio="Edificio", nombre_nivel="Nivel 0"):
    """Exporta muros + puertas + ventanas a un archivo IFC.

    muros:    [{"x1", "y1", "x2", "y2", "grosor", "altura", "nombre"}, ...]
    puertas:  [{"x", "y", "ancho", "alto", "altura_peana", "orientacion", "nombre"}, ...]
    ventanas: [{"x", "y", "ancho", "alto", "altura_peana", "orientacion", "nombre"}, ...]

    orientacion: "horizontal" (eje X) o "vertical" (eje Y)
    """
    if not muros and not puertas and not ventanas:
        return False, "No hay geometria para exportar."

    if not FREECAD_CMD or not Path(FREECAD_CMD).exists():
        return False, f"No encuentro freecadcmd en {FREECAD_CMD}"

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    script = _generar_script(
        muros or [], puertas or [], ventanas or [], output_path,
        nombre_proyecto, nombre_edificio, nombre_nivel,
    )

    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".py", delete=False, encoding="utf-8"
    ) as f:
        f.write(script)
        sp = f.name

    try:
        r = subprocess.run(
            [FREECAD_CMD, sp],
            capture_output=True, text=True, timeout=TIMEOUT_IFC,
            encoding="utf-8", errors="replace",
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