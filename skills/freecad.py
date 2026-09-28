"""Skill de FreeCAD: crea geometria 2D/3D y exporta DXF/PDF via freecadcmd."""
import json
import os
import re
import subprocess
import tempfile
import uuid
from pathlib import Path

from skills.base import Skill
from core import confirmation

ROOT = Path(__file__).resolve().parent.parent
SANDBOX = ROOT / "sandbox" / "freecad"
SANDBOX.mkdir(parents=True, exist_ok=True)
WORKSPACE = SANDBOX / "workspace.FCStd"

# Ruta a freecadcmd.exe: deteccion automatica desde core.paths
from core.paths import FREECAD_CMD
TIMEOUT = 120


def _run_freecad(script_code):
    """Ejecuta un script en freecadcmd y devuelve (stdout, stderr, error)."""
    if not Path(FREECAD_CMD).exists():
        return None, None, f"No encuentro freecadcmd en {FREECAD_CMD}"

    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".py", delete=False, encoding="utf-8"
    ) as f:
        f.write(script_code)
        script_path = f.name

    try:
        result = subprocess.run(
            [FREECAD_CMD, script_path],
            capture_output=True,
            text=True,
            timeout=TIMEOUT,
            encoding="utf-8",
            errors="replace",
        )
        # Si el script imprimio un error, devolverlo
        if result.returncode != 0:
            err_msg = result.stderr.strip() or f"freecadcmd retorno codigo {result.returncode}"
            print(f"[FREECAD] Error: {err_msg}")
        return result.stdout, result.stderr, None
    except subprocess.TimeoutExpired:
        return None, None, f"FreeCAD tardo mas de {TIMEOUT}s"
    except Exception as e:
        return None, None, f"Error ejecutando FreeCAD: {e}"
    finally:
        try:
            os.unlink(script_path)
        except Exception:
            pass


def _workspace_exists():
    return WORKSPACE.exists()


# ═══════════════════════════════════════════════════════════════════════════
# PLANTILLAS DE SCRIPT
# ═══════════════════════════════════════════════════════════════════════════

SCRIPT_NEW_DOC = """
import FreeCAD
import os

doc = FreeCAD.newDocument('NitroWorkspace')
doc.saveAs(r'{path}')
print('OK_NEW_DOC')
print('NAME=' + doc.Name)
"""

SCRIPT_OPEN_OR_NEW = """
import FreeCAD
import os

path = r'{path}'
if os.path.exists(path):
    doc = FreeCAD.openDocument(path)
else:
    doc = FreeCAD.newDocument('NitroWorkspace')
"""

SCRIPT_ADD_RECTANGLE = SCRIPT_OPEN_OR_NEW + """
import Part
import sys
try:
    box = Part.makeBox({width}, {height}, 0.01, FreeCAD.Vector({x1}, {y1}, 0))
    obj = doc.addObject('Part::Feature', 'Rectangle')
    obj.Shape = box
    obj.Label = '{label}'
    doc.recompute()
    doc.saveAs(r'{path}')
    print('OK_ADD_RECT')
    print('OBJ=' + obj.Name)
except Exception as e:
    sys.stderr.write('ERR_ADD_RECT: ' + str(e) + '\\n')
    sys.exit(1)
"""

SCRIPT_ADD_LINE = SCRIPT_OPEN_OR_NEW + """
import Draft
p1 = FreeCAD.Vector({x1}, {y1}, {z1})
p2 = FreeCAD.Vector({x2}, {y2}, {z2})
line = Draft.make_line(p1, p2)
line.Label = '{label}'
doc.recompute()
doc.saveAs(r'{path}')
print('OK_ADD_LINE')
print('OBJ=' + line.Name)
"""

SCRIPT_ADD_CIRCLE = SCRIPT_OPEN_OR_NEW + """
import Part
import sys
try:
    circle = Part.makeCircle({radius}, FreeCAD.Vector({cx}, {cy}, 0), FreeCAD.Vector(0, 0, 1))
    obj = doc.addObject('Part::Feature', 'Circle')
    obj.Shape = circle
    obj.Label = '{label}'
    doc.recompute()
    doc.saveAs(r'{path}')
    print('OK_ADD_CIRCLE')
    print('OBJ=' + obj.Name)
except Exception as e:
    sys.stderr.write('ERR_ADD_CIRCLE: ' + str(e) + '\\n')
    sys.exit(1)
"""

SCRIPT_ADD_TEXT = SCRIPT_OPEN_OR_NEW + """
import Draft
pos = FreeCAD.Vector({x}, {y}, 0)
text = Draft.make_text('{text}', pos)
text.Label = '{label}'
doc.recompute()
doc.saveAs(r'{path}')
print('OK_ADD_TEXT')
print('OBJ=' + text.Name)
"""

SCRIPT_ADD_WALL = SCRIPT_OPEN_OR_NEW + """
import Draft
# Un muro como un rectangulo extruido (simplificado en 2D)
p1 = FreeCAD.Vector({x1}, {y1}, 0)
p2 = FreeCAD.Vector({x2}, {y2}, 0)
line = Draft.make_line(p1, p2)
line.Label = '{label}'
doc.recompute()
doc.saveAs(r'{path}')
print('OK_ADD_WALL')
print('OBJ=' + line.Name)
"""

SCRIPT_LIST_OBJECTS = """
import FreeCAD
import os
path = r'{path}'
if not os.path.exists(path):
    print('ERROR_NO_WORKSPACE')
else:
    doc = FreeCAD.openDocument(path)
    print('OK_LIST')
    for obj in doc.Objects:
        print('OBJ|' + obj.Name + '|' + obj.Label + '|' + obj.TypeId)
"""

SCRIPT_EXPORT_DXF = SCRIPT_OPEN_OR_NEW + """
import importDXF
objs = [o for o in doc.Objects]
importDXF.export(objs, r'{out_path}')
print('OK_EXPORT_DXF')
print('PATH=' + r'{out_path}')
"""

SCRIPT_EXPORT_PDF = SCRIPT_OPEN_OR_NEW + """
try:
    # En FreeCAD 1.x el modulo importPDF no existe; intentamos usar TechDraw
    import TechDraw
    page = doc.addObject('TechDraw::DrawPage', 'Page')
    template = doc.addObject('TechDraw::DrawSVGTemplate', 'Template')
    # Sin template, no se puede renderizar; avisamos
    print('WARN_PDF: TechDraw requiere template manual. Usa export_dxf en su lugar.')
except Exception as e:
    print('ERROR_PDF=' + str(e))
"""

SCRIPT_SAVE_AS = SCRIPT_OPEN_OR_NEW + """
doc.saveAs(r'{out_path}')
print('OK_SAVE_AS')
print('PATH=' + r'{out_path}')
"""

SCRIPT_CLEAR = """
import os
path = r'{path}'
if os.path.exists(path):
    os.remove(path)
print('OK_CLEAR')
"""


def _extract(output, prefix):
    """Extrae el valor de una linea tipo PREFIX=valor."""
    if not output:
        return None
    for line in output.splitlines():
        if line.startswith(prefix + "="):
            return line[len(prefix) + 1 :].strip()
    return None


# ═══════════════════════════════════════════════════════════════════════════
# SKILL
# ═══════════════════════════════════════════════════════════════════════════

class FreeCadSkill(Skill):
    name = "freecad"
    description = "Crea geometria 2D/3D y exporta a DXF/PDF con FreeCAD"

    def run(self, action, params):
        if action == "add_room_labels":
            return self._add_room_labels(params.get("labels", []))
        if action == "add_level_dimensions":
            return self._add_level_dimensions(
                float(params.get("height", 3.0)),
                int(params.get("num_floors", 1)), 
                )
        if action == "new_document":
            return self._new_document(params.get("name", "NitroWorkspace"))
        if action == "add_rectangle":
            return self._add_rectangle(params)
        if action == "add_line":
            return self._add_line(params)
        if action == "add_circle":
            return self._add_circle(params)
        if action == "add_text":
            return self._add_text(params)
        if action == "add_wall":
            return self._add_wall(params)
        if action == "list_objects":
            return self._list_objects()
        if action == "export_dxf":
            return self._export_dxf(params.get("path", ""))
        if action == "export_pdf":
            return self._export_pdf(params.get("path", ""))
        if action == "save_as":
            return self._save_as(params.get("path", ""))
        if action == "clear_workspace":
            return self._clear_workspace()
        # ── Arquitectura 3D ──
        if action == "add_wall_3d":
            return self._add_wall_3d(params)
        if action == "create_room":
            return self._create_room(params)
        if action == "add_door":
            return self._add_door(params)
        if action == "add_window":
            return self._add_window(params)
        if action == "add_dimension":
            return self._add_dimension(params)
        if action == "add_slab":
            return self._add_slab(params)
        if action == "add_column":
            return self._add_column(params)
        # ── Transformaciones ──
        if action == "move_object":
            return self._move_object(params)
        if action == "rotate_object":
            return self._rotate_object(params)
        if action == "array_objects":
            return self._array_objects(params)
        if action == "delete_object":
            return self._delete_object(params)
        if action == "boolean_op":
            return self._boolean_op(params)
        if action == "set_color":
            return self._set_color(params)
        # ── Import/Export ──
        if action == "export_step":
            return self._export_step(params.get("path", ""))
        if action == "export_obj":
            return self._export_obj(params.get("path", ""))
        if action == "export_stl":
            return self._export_stl(params.get("path", ""))
        if action == "import_step":
            return self._import_step(params.get("path", ""))
        # ── PDF mejorado ──
        if action == "export_pdf_techdraw":
            return self._export_pdf_techdraw(params.get("path", ""))
        return f"Accion desconocida en freecad: {action}"

    # ─── INTERNOS ───────────────────────────────────────────────────────

    def _new_document(self, name):
        if not confirmation.require("freecad", "new_document", f"Crear documento nuevo '{name}'"):
            return {"thought": "Cancelado", "display": "Cancelado.", "voice": "Cancelado."}

        code = SCRIPT_NEW_DOC.format(path=str(WORKSPACE).replace("\\", "\\\\"))
        stdout, stderr, err = _run_freecad(code)
        if err:
            return {"thought": "Error FreeCAD", "display": err, "voice": "No pude crear el documento."}

        if "OK_NEW_DOC" not in (stdout or ""):
            return {
                "thought": "Error",
                "display": f"FreeCAD no confirmo la creacion.\nSTDOUT: {stdout[:400]}\nSTDERR: {(stderr or '')[:400]}",
                "voice": "Error creando documento.",
            }

        return {
            "thought": f"Documento creado en {WORKSPACE}",
            "display": f"Documento FreeCAD creado.\n  Ruta: {WORKSPACE}",
            "voice": "Documento nuevo creado.",
        }

    def _add_rectangle(self, params):
        x1 = float(params.get("x1", 0))
        y1 = float(params.get("y1", 0))
        x2 = float(params.get("x2", 0))
        y2 = float(params.get("y2", 0))
        label = params.get("label", "Rectangulo")
        width = x2 - x1
        height = y2 - y1

        code = SCRIPT_ADD_RECTANGLE.format(
            path=str(WORKSPACE).replace("\\", "\\\\"),
            x1=x1, y1=y1, x2=x2, y2=y2,
            width=width, height=height,
            label=label,
        )
        stdout, stderr, err = _run_freecad(code)
        if err:
            return {"thought": "Error", "display": err, "voice": "Error."}
        if "OK_ADD_RECT" not in (stdout or ""):
            return {
                "thought": "Error",
                "display": f"No se pudo agregar rectangulo.\nSTDOUT: {stdout[:300]}",
                "voice": "Error.",
            }
        obj_id = _extract(stdout, "OBJ") or "?"
        return {
            "thought": f"Rectangulo {width}x{height} agregado",
            "display": f"Rectangulo agregado ({width}x{height} en {x1},{y1}).\n  objeto: {obj_id}",
            "voice": "Rectangulo agregado.",
        }

    def _add_line(self, params):
        code = SCRIPT_ADD_LINE.format(
            path=str(WORKSPACE).replace("\\", "\\\\"),
            x1=float(params.get("x1", 0)),
            y1=float(params.get("y1", 0)),
            z1=float(params.get("z1", 0)),
            x2=float(params.get("x2", 1)),
            y2=float(params.get("y2", 1)),
            z2=float(params.get("z2", 0)),
            label=params.get("label", "Linea"),
        )
        stdout, stderr, err = _run_freecad(code)
        if err:
            return {"thought": "Error", "display": err, "voice": "Error."}
        if "OK_ADD_LINE" not in (stdout or ""):
            return {"thought": "Error", "display": f"Fallo: {stdout[:300]}", "voice": "Error."}
        obj_id = _extract(stdout, "OBJ") or "?"
        return {
            "thought": "Linea agregada",
            "display": f"Linea agregada.\n  objeto: {obj_id}",
            "voice": "Linea agregada.",
        }

    def _add_circle(self, params):
        code = SCRIPT_ADD_CIRCLE.format(
            path=str(WORKSPACE).replace("\\", "\\\\"),
            cx=float(params.get("cx", 0)),
            cy=float(params.get("cy", 0)),
            radius=float(params.get("radius", 1)),
            label=params.get("label", "Circulo"),
        )
        stdout, stderr, err = _run_freecad(code)
        if err:
            return {"thought": "Error", "display": err, "voice": "Error."}
        if "OK_ADD_CIRCLE" not in (stdout or ""):
            return {"thought": "Error", "display": f"Fallo: {stdout[:300]}", "voice": "Error."}
        obj_id = _extract(stdout, "OBJ") or "?"
        return {
            "thought": "Circulo agregado",
            "display": f"Circulo agregado.\n  objeto: {obj_id}",
            "voice": "Circulo agregado.",
        }

    def _add_text(self, params):
        text = params.get("text", "").replace("'", "\\'")
        code = SCRIPT_ADD_TEXT.format(
            path=str(WORKSPACE).replace("\\", "\\\\"),
            x=float(params.get("x", 0)),
            y=float(params.get("y", 0)),
            text=text,
            label=params.get("label", "Texto"),
        )
        stdout, stderr, err = _run_freecad(code)
        if err:
            return {"thought": "Error", "display": err, "voice": "Error."}
        if "OK_ADD_TEXT" not in (stdout or ""):
            return {"thought": "Error", "display": f"Fallo: {stdout[:300]}", "voice": "Error."}
        obj_id = _extract(stdout, "OBJ") or "?"
        return {
            "thought": "Texto agregado",
            "display": f"Texto agregado.\n  objeto: {obj_id}",
            "voice": "Texto agregado.",
        }

    def _add_wall(self, params):
        return self._add_line({
            "x1": params.get("x1", 0),
            "y1": params.get("y1", 0),
            "z1": 0,
            "x2": params.get("x2", 1),
            "y2": params.get("y2", 1),
            "z2": 0,
            "label": params.get("label", "Muro"),
        })

    def _list_objects(self):
        code = SCRIPT_LIST_OBJECTS.format(path=str(WORKSPACE).replace("\\", "\\\\"))
        stdout, stderr, err = _run_freecad(code)
        if err:
            return {"thought": "Error", "display": err, "voice": "Error."}
        if "ERROR_NO_WORKSPACE" in (stdout or ""):
            return {
                "thought": "",
                "display": "No hay workspace. Crea uno con new_document primero.",
                "voice": "No hay workspace.",
            }
        objs = []
        for line in (stdout or "").splitlines():
            if line.startswith("OBJ|"):
                parts = line[4:].split("|")
                if len(parts) >= 3:
                    objs.append({"name": parts[0], "label": parts[1], "type": parts[2]})

        if not objs:
            return {"thought": "", "display": "Workspace vacio.", "voice": "No hay objetos."}

        lineas = [f"Objetos en el workspace ({len(objs)}):"]
        for o in objs:
            lineas.append(f"  - {o['label']} ({o['type'].split('::')[-1]}) [id: {o['name']}]")
        return {
            "thought": f"{len(objs)} objetos",
            "display": "\n".join(lineas),
            "voice": f"{len(objs)} objetos en el documento.",
        }

    def _export_dxf(self, out_path):
        if not out_path:
            out_path = str(SANDBOX / f"export_{uuid.uuid4().hex[:8]}.dxf")
        out_path = str(Path(out_path))

        code = SCRIPT_EXPORT_DXF.format(
            path=str(WORKSPACE).replace("\\", "\\\\"),
            out_path=out_path.replace("\\", "\\\\"),
        )
        stdout, stderr, err = _run_freecad(code)
        if err:
            return {"thought": "Error", "display": err, "voice": "Error exportando."}
        if "OK_EXPORT_DXF" not in (stdout or ""):
            return {
                "thought": "Error",
                "display": f"No pude exportar DXF.\nSTDOUT: {stdout[:400]}",
                "voice": "Error exportando DXF.",
            }
        return {
            "thought": f"DXF exportado a {out_path}",
            "display": f"Archivo DXF exportado.\n  Ruta: {out_path}\n\nAbrelo en AutoCAD, LibreCAD o DraftSight.",
            "voice": "DXF exportado.",
        }

    def _export_pdf(self, out_path):
        if not out_path:
            out_path = str(SANDBOX / f"export_{uuid.uuid4().hex[:8]}.pdf")
        out_path = str(Path(out_path))

        code = SCRIPT_EXPORT_PDF.format(
            path=str(WORKSPACE).replace("\\", "\\\\"),
            out_path=out_path.replace("\\", "\\\\"),
        )
        stdout, stderr, err = _run_freecad(code)
        if err:
            return {"thought": "Error", "display": err, "voice": "Error."}
        if "OK_EXPORT_PDF" not in (stdout or ""):
            return {
                "thought": "Error",
                "display": f"No pude exportar PDF. (importPDF puede no estar disponible).\nSTDOUT: {stdout[:300]}",
                "voice": "Error exportando PDF.",
            }
        return {
            "thought": f"PDF exportado a {out_path}",
            "display": f"PDF exportado.\n  Ruta: {out_path}",
            "voice": "PDF exportado.",
        }

    def _save_as(self, out_path):
        if not out_path:
            out_path = str(SANDBOX / f"nitro_{uuid.uuid4().hex[:8]}.FCStd")
        out_path = str(Path(out_path))
        code = SCRIPT_SAVE_AS.format(
            path=str(WORKSPACE).replace("\\", "\\\\"),
            out_path=out_path.replace("\\", "\\\\"),
        )
        stdout, stderr, err = _run_freecad(code)
        if err or "OK_SAVE_AS" not in (stdout or ""):
            return {"thought": "Error", "display": err or stdout[:200], "voice": "Error."}
        return {
            "thought": "Guardado",
            "display": f"Guardado como FCStd.\n  Ruta: {out_path}",
            "voice": "Guardado.",
        }
    def _add_room_labels(self, labels):
        """Anade textos 3D sobre el plano (etiquetas de ambientes).

        labels: lista de dicts [{"x": 5, "y": 3, "text": "SALA"}, ...]
        """
        if not labels:
            return {"thought": "", "display": "Falta la lista de etiquetas.", "voice": "Faltan etiquetas."}
        if not confirmation.require("freecad", "add_room_labels", f"Anadir {len(labels)} etiquetas de ambientes"):
            return {"thought": "Cancelado", "display": "Cancelado.", "voice": "Cancelado."}

        # Construir el script
        lineas = [
            "import FreeCAD",
            "import Draft",
            "import os",
            f"path = r'{str(WORKSPACE).replace(chr(92), chr(47))}'",
            "if os.path.exists(path):",
            "    doc = FreeCAD.openDocument(path)",
            "else:",
            "    doc = FreeCAD.newDocument('NitroWorkspace')",
            "etiquetas = [",
        ]
        for lab in labels:
            x = float(lab.get("x", 0))
            y = float(lab.get("y", 0))
            z = float(lab.get("z", 1.5))
            txt = str(lab.get("text", "")).replace("'", "\\'").replace('"', '\\"')
            lineas.append(f"    ({x}, {y}, {z}, '{txt}'),")
        lineas.extend([
            "]",
            "for i, (x, y, z, txt) in enumerate(etiquetas):",
            "    try:",
            "        pos = FreeCAD.Vector(x, y, z)",
            "        t = Draft.make_text(txt, pos)",
            "        t.Label = 'Etiqueta_' + str(i)",
            "    except Exception as e:",
            "        print('WARN etiqueta ' + str(i) + ': ' + str(e))",
            "doc.recompute()",
            "doc.saveAs(path)",
            "print('OK_LABELS')",
        ])
        script = "\n".join(lineas)
        stdout, stderr, err = _run_freecad(script)
        if err:
            return {"thought": "Error", "display": err, "voice": "Error."}
        if "OK_LABELS" not in (stdout or ""):
            return {"thought": "Error", "display": f"Fallo: {(stdout or '')[:300]}", "voice": "Error."}
        return {
            "thought": f"{len(labels)} etiquetas anadidas",
            "display": f"Etiquetas agregadas al plano.\n Total: {len(labels)}",
            "voice": f"{len(labels)} etiquetas agregadas.",
        }

    def _add_level_dimensions(self, height=3.0, num_floors=1):
        """Anade cotas de nivel (N.P.T.) a la fachada del edificio."""
        if height <= 0 or num_floors <= 0:
            return {"thought": "", "display": "Altura y pisos deben ser > 0.", "voice": "Datos invalidos."}
        if not confirmation.require("freecad", "add_level_dimensions", f"Anadir {num_floors + 1} cotas de nivel"):
            return {"thought": "Cancelado", "display": "Cancelado.", "voice": "Cancelado."}

        altura_piso = height / num_floors
        niveles = [i * altura_piso for i in range(num_floors + 1)]

        lineas = [
            "import FreeCAD",
            "import Draft",
            "import os",
            f"path = r'{str(WORKSPACE).replace(chr(92), chr(47))}'",
            "if os.path.exists(path):",
            "    doc = FreeCAD.openDocument(path)",
            "else:",
            "    doc = FreeCAD.newDocument('NitroWorkspace')",
            f"niveles = {niveles}",
            "x_ref = 2.0",
            "y_ref = -2.0",
            "for i, z in enumerate(niveles):",
            "    try:",
            "        txt = 'N.P.T. +{:.2f}'.format(z)",
            "        pos = FreeCAD.Vector(x_ref, y_ref, z)",
            "        t = Draft.make_text(txt, pos)",
            "        t.Label = 'Nivel_' + str(i)",
            "    except Exception as e:",
            "        print('WARN nivel ' + str(i) + ': ' + str(e))",
            "doc.recompute()",
            "doc.saveAs(path)",
            "print('OK_LEVELS')",
        ]
        script = "\n".join(lineas)
        stdout, stderr, err = _run_freecad(script)
        if err:
            return {"thought": "Error", "display": err, "voice": "Error."}
        if "OK_LEVELS" not in (stdout or ""):
            return {"thought": "Error", "display": f"Fallo: {(stdout or '')[:300]}", "voice": "Error."}
        return {
            "thought": f"{len(niveles)} cotas de nivel anadidas",
            "display": (
                f"Cotas de nivel agregadas.\n"
                f" Altura total: {height}m\n"
                f" Pisos: {num_floors}\n"
                f" Niveles: {', '.join(f'+{n:.2f}' for n in niveles)}"
            ),
            "voice": f"{len(niveles)} cotas de nivel agregadas.",
        }

    # ═══════════════════════════════════════════════════════════════════
    # ARQUITECTURA 3D
    # ═══════════════════════════════════════════════════════════════════

    def _add_wall_3d(self, params):
        x1 = float(params.get("x1", 0))
        y1 = float(params.get("y1", 0))
        x2 = float(params.get("x2", 5))
        y2 = float(params.get("y2", 0))
        height = float(params.get("height", 3.0))
        thickness = float(params.get("thickness", 0.15))
        label = params.get("label", "Muro")

        if not confirmation.require("freecad", "add_wall_3d", f"Muro 3D ({x1},{y1})-({x2},{y2}) h={height}m"):
            return {"thought": "Cancelado", "display": "Cancelado.", "voice": "Cancelado."}

        L = [chr(34) + "import FreeCAD" + chr(34),
             chr(34) + "import Part" + chr(34),
             chr(34) + "import math" + chr(34),
             chr(34) + "import os" + chr(34),
             "f" + chr(34) + "path = r'" + str(WORKSPACE).replace(chr(92), chr(47)) + "'" + chr(34),
             chr(34) + "if os.path.exists(path):" + chr(34),
             chr(34) + "    doc = FreeCAD.openDocument(path)" + chr(34),
             chr(34) + "else:" + chr(34),
             chr(34) + "    doc = FreeCAD.newDocument('NitroWorkspace')" + chr(34),
             "f" + chr(34) + "p1 = FreeCAD.Vector(" + str(x1) + ", " + str(y1) + ", 0)" + chr(34),
             "f" + chr(34) + "p2 = FreeCAD.Vector(" + str(x2) + ", " + str(y2) + ", 0)" + chr(34),
             chr(34) + "dx = p2.x - p1.x" + chr(34),
             chr(34) + "dy = p2.y - p1.y" + chr(34),
             chr(34) + "L = math.sqrt(dx*dx + dy*dy)" + chr(34),
             chr(34) + "if L < 0.001:" + chr(34),
             chr(34) + "    print('ERR_WALL_LEN0')" + chr(34),
             chr(34) + "    import sys; sys.exit(1)" + chr(34),
             chr(34) + "ux = -dy / L" + chr(34),
             chr(34) + "uy = dx / L" + chr(34),
             "f" + chr(34) + "ht = " + str(thickness) + " / 2.0" + chr(34),
             chr(34) + "c1 = FreeCAD.Vector(p1.x + ux*ht, p1.y + uy*ht, 0)" + chr(34),
             chr(34) + "c2 = FreeCAD.Vector(p2.x + ux*ht, p2.y + uy*ht, 0)" + chr(34),
             chr(34) + "c3 = FreeCAD.Vector(p2.x - ux*ht, p2.y - uy*ht, 0)" + chr(34),
             chr(34) + "c4 = FreeCAD.Vector(p1.x - ux*ht, p1.y - uy*ht, 0)" + chr(34),
             chr(34) + "w = Part.makePolygon([c1, c2, c3, c4, c1])" + chr(34),
             chr(34) + "f = Part.Face(w)" + chr(34),
             "f" + chr(34) + "solid = f.extrude(FreeCAD.Vector(0, 0, " + str(height) + "))" + chr(34),
             chr(34) + "obj = doc.addObject('Part::Feature', 'Muro3D')" + chr(34),
             chr(34) + "obj.Shape = solid" + chr(34),
             "f" + chr(34) + "obj.Label = '" + label + "'" + chr(34),
             chr(34) + "doc.recompute()" + chr(34),
             chr(34) + "doc.saveAs(path)" + chr(34),
             chr(34) + "print('OK_WALL3D')" + chr(34)]

        return self._run_script_list(L, "Muro 3D", f"Altura: {height}m, Grosor: {thickness}m", "OK_WALL3D")

    def _create_room(self, params):
        vertices = params.get("vertices", [])
        if not vertices or len(vertices) < 3:
            return {"thought": "", "display": "Necesito al menos 3 vertices.", "voice": "Faltan vertices."}
        height = float(params.get("height", 3.0))
        thickness = float(params.get("thickness", 0.15))
        floor = bool(params.get("floor", True))
        if not confirmation.require("freecad", "create_room", f"Habitacion {len(vertices)} vert, h={height}m"):
            return {"thought": "Cancelado", "display": "Cancelado.", "voice": "Cancelado."}

        verts_str = ", ".join(f"({float(v[0])}, {float(v[1])})" for v in vertices)
        L = [chr(34) + "import FreeCAD" + chr(34),
             chr(34) + "import Part" + chr(34),
             chr(34) + "import math" + chr(34),
             chr(34) + "import os" + chr(34),
             "f" + chr(34) + "path = r'" + str(WORKSPACE).replace(chr(92), chr(47)) + "'" + chr(34),
             chr(34) + "if os.path.exists(path):" + chr(34),
             chr(34) + "    doc = FreeCAD.openDocument(path)" + chr(34),
             chr(34) + "else:" + chr(34),
             chr(34) + "    doc = FreeCAD.newDocument('NitroWorkspace')" + chr(34),
             "f" + chr(34) + "verts = [" + verts_str + "]" + chr(34),
             "f" + chr(34) + "HEIGHT = " + str(height) + chr(34),
             "f" + chr(34) + "THICK = " + str(thickness) + chr(34),
             "f" + chr(34) + "CON_FLOOR = " + str(floor) + chr(34),
             chr(34) + "if CON_FLOOR:" + chr(34),
             chr(34) + "    pts3d = [FreeCAD.Vector(x, y, 0) for x, y in verts]" + chr(34),
             chr(34) + "    pts3d.append(pts3d[0])" + chr(34),
             chr(34) + "    wire = Part.makePolygon(pts3d)" + chr(34),
             chr(34) + "    face = Part.Face(wire)" + chr(34),
             chr(34) + "    suelo = doc.addObject('Part::Feature', 'Suelo')" + chr(34),
             chr(34) + "    suelo.Shape = face" + chr(34),
             chr(34) + "    suelo.Label = 'Suelo'" + chr(34),
             chr(34) + "for i in range(len(verts)):" + chr(34),
             chr(34) + "    j = (i + 1) % len(verts)" + chr(34),
             chr(34) + "    x1, y1 = verts[i]" + chr(34),
             chr(34) + "    x2, y2 = verts[j]" + chr(34),
             chr(34) + "    dx = x2 - x1" + chr(34),
             chr(34) + "    dy = y2 - y1" + chr(34),
             chr(34) + "    L = math.sqrt(dx*dx + dy*dy)" + chr(34),
             chr(34) + "    if L < 0.001:" + chr(34),
             chr(34) + "        continue" + chr(34),
             chr(34) + "    ux = -dy / L" + chr(34),
             chr(34) + "    uy = dx / L" + chr(34),
             chr(34) + "    ht = THICK / 2.0" + chr(34),
             chr(34) + "    c1 = FreeCAD.Vector(x1 + ux*ht, y1 + uy*ht, 0)" + chr(34),
             chr(34) + "    c2 = FreeCAD.Vector(x2 + ux*ht, y2 + uy*ht, 0)" + chr(34),
             chr(34) + "    c3 = FreeCAD.Vector(x2 - ux*ht, y2 - uy*ht, 0)" + chr(34),
             chr(34) + "    c4 = FreeCAD.Vector(x1 - ux*ht, y1 - uy*ht, 0)" + chr(34),
             chr(34) + "    w = Part.makePolygon([c1, c2, c3, c4, c1])" + chr(34),
             chr(34) + "    f = Part.Face(w)" + chr(34),
             chr(34) + "    solid = f.extrude(FreeCAD.Vector(0, 0, HEIGHT))" + chr(34),
             chr(34) + "    muro = doc.addObject('Part::Feature', 'Muro')" + chr(34),
             chr(34) + "    muro.Shape = solid" + chr(34),
             chr(34) + "    muro.Label = 'Muro_' + str(i+1)" + chr(34),
             chr(34) + "doc.recompute()" + chr(34),
             chr(34) + "doc.saveAs(path)" + chr(34),
             chr(34) + "print('OK_ROOM')" + chr(34)]

        return self._run_script_list(L, "Habitacion", f"Muros: {len(vertices)}, h={height}m", "OK_ROOM")

    def _add_door(self, params):
        wall_label = params.get("wall_label", "")
        x = float(params.get("x", 0))
        y = float(params.get("y", 0))
        z = float(params.get("z", 0))
        width = float(params.get("width", 0.9))
        height = float(params.get("height", 2.1))
        if not wall_label:
            return {"thought": "", "display": "Necesito wall_label.", "voice": "Falta wall_label."}
        if not confirmation.require("freecad", "add_door", f"Puerta en {wall_label}"):
            return {"thought": "Cancelado", "display": "Cancelado.", "voice": "Cancelado."}

        L = [chr(34) + "import FreeCAD" + chr(34),
             chr(34) + "import Part" + chr(34),
             chr(34) + "import os" + chr(34),
             "f" + chr(34) + "path = r'" + str(WORKSPACE).replace(chr(92), chr(47)) + "'" + chr(34),
             chr(34) + "if not os.path.exists(path):" + chr(34),
             chr(34) + "    print('ERR_NO_WORKSPACE')" + chr(34),
             chr(34) + "    import sys; sys.exit(1)" + chr(34),
             chr(34) + "doc = FreeCAD.openDocument(path)" + chr(34),
             "f" + chr(34) + "wall = doc.getObject('" + wall_label + "')" + chr(34),
             chr(34) + "if not wall:" + chr(34),
             chr(34) + "    print('ERR_WALL_NOT_FOUND')" + chr(34),
             chr(34) + "    import sys; sys.exit(1)" + chr(34),
             "f" + chr(34) + "box = Part.makeBox(" + str(width) + ", 0.5, " + str(height) + ", FreeCAD.Vector(" + str(x) + ", " + str(y) + ", " + str(z) + "))" + chr(34),
             chr(34) + "cut = wall.Shape.cut(box)" + chr(34),
             chr(34) + "wall.Shape = cut" + chr(34),
             chr(34) + "doc.recompute()" + chr(34),
             chr(34) + "doc.saveAs(path)" + chr(34),
             chr(34) + "print('OK_DOOR')" + chr(34)]

        return self._run_script_list(L, "Puerta", f"{width}x{height}m", "OK_DOOR")

    def _add_window(self, params):
        params.setdefault("width", 1.2)
        params.setdefault("height", 1.0)
        return self._add_door(params)

    def _add_dimension(self, params):
        x1 = float(params.get("x1", 0))
        y1 = float(params.get("y1", 0))
        x2 = float(params.get("x2", 1))
        y2 = float(params.get("y2", 1))
        label = params.get("label", "Cota")

        L = [chr(34) + "import FreeCAD" + chr(34),
             chr(34) + "import Draft" + chr(34),
             chr(34) + "import math" + chr(34),
             chr(34) + "import os" + chr(34),
             "f" + chr(34) + "path = r'" + str(WORKSPACE).replace(chr(92), chr(47)) + "'" + chr(34),
             chr(34) + "if os.path.exists(path):" + chr(34),
             chr(34) + "    doc = FreeCAD.openDocument(path)" + chr(34),
             chr(34) + "else:" + chr(34),
             chr(34) + "    doc = FreeCAD.newDocument('NitroWorkspace')" + chr(34),
             "f" + chr(34) + "p1 = FreeCAD.Vector(" + str(x1) + ", " + str(y1) + ", 0)" + chr(34),
             "f" + chr(34) + "p2 = FreeCAD.Vector(" + str(x2) + ", " + str(y2) + ", 0)" + chr(34),
             chr(34) + "dx = p2.x - p1.x" + chr(34),
             chr(34) + "dy = p2.y - p1.y" + chr(34),
             chr(34) + "dist = math.sqrt(dx*dx + dy*dy)" + chr(34),
             chr(34) + "dim = Draft.make_dimension(p1, p2)" + chr(34),
             "f" + chr(34) + "dim.Label = '" + label + " {:.2f}m'.format(dist)" + chr(34),
             chr(34) + "doc.recompute()" + chr(34),
             chr(34) + "doc.saveAs(path)" + chr(34),
             chr(34) + "print('OK_DIM')" + chr(34)]

        return self._run_script_list(L, "Cota", f"({x1},{y1})-({x2},{y2})", "OK_DIM")

    def _add_slab(self, params):
        x1 = float(params.get("x1", 0))
        y1 = float(params.get("y1", 0))
        x2 = float(params.get("x2", 5))
        y2 = float(params.get("y2", 5))
        z = float(params.get("z", 0))
        thickness = float(params.get("thickness", 0.2))
        label = params.get("label", "Losa")

        L = [chr(34) + "import FreeCAD" + chr(34),
             chr(34) + "import Part" + chr(34),
             chr(34) + "import os" + chr(34),
             "f" + chr(34) + "path = r'" + str(WORKSPACE).replace(chr(92), chr(47)) + "'" + chr(34),
             chr(34) + "if os.path.exists(path):" + chr(34),
             chr(34) + "    doc = FreeCAD.openDocument(path)" + chr(34),
             chr(34) + "else:" + chr(34),
             chr(34) + "    doc = FreeCAD.newDocument('NitroWorkspace')" + chr(34),
             "f" + chr(34) + "losa = Part.makeBox(" + str(x2-x1) + ", " + str(y2-y1) + ", " + str(thickness) + ", FreeCAD.Vector(" + str(x1) + ", " + str(y1) + ", " + str(z) + "))" + chr(34),
             chr(34) + "obj = doc.addObject('Part::Feature', 'Losa')" + chr(34),
             chr(34) + "obj.Shape = losa" + chr(34),
             "f" + chr(34) + "obj.Label = '" + label + "'" + chr(34),
             chr(34) + "doc.recompute()" + chr(34),
             chr(34) + "doc.saveAs(path)" + chr(34),
             chr(34) + "print('OK_SLAB')" + chr(34)]

        return self._run_script_list(L, "Losa", f"{x2-x1}x{y2-y1}m espesor {thickness}m", "OK_SLAB")

    def _add_column(self, params):
        x = float(params.get("x", 0))
        y = float(params.get("y", 0))
        height = float(params.get("height", 3.0))
        radius = float(params.get("radius", 0.15))
        shape = params.get("shape", "circle")
        label = params.get("label", "Columna")

        L = [chr(34) + "import FreeCAD" + chr(34),
             chr(34) + "import Part" + chr(34),
             chr(34) + "import os" + chr(34),
             "f" + chr(34) + "path = r'" + str(WORKSPACE).replace(chr(92), chr(47)) + "'" + chr(34),
             chr(34) + "if os.path.exists(path):" + chr(34),
             chr(34) + "    doc = FreeCAD.openDocument(path)" + chr(34),
             chr(34) + "else:" + chr(34),
             chr(34) + "    doc = FreeCAD.newDocument('NitroWorkspace')" + chr(34)]

        if shape == "circle":
            L.append("f" + chr(34) + "col = Part.makeCylinder(" + str(radius) + ", " + str(height) + ", FreeCAD.Vector(" + str(x) + ", " + str(y) + ", 0))" + chr(34))
        else:
            L.append("f" + chr(34) + "col = Part.makeBox(" + str(radius*2) + ", " + str(radius*2) + ", " + str(height) + ", FreeCAD.Vector(" + str(x-radius) + ", " + str(y-radius) + ", 0))" + chr(34))

        L.extend([chr(34) + "obj = doc.addObject('Part::Feature', 'Columna')" + chr(34),
                  chr(34) + "obj.Shape = col" + chr(34),
                  "f" + chr(34) + "obj.Label = '" + label + "'" + chr(34),
                  chr(34) + "doc.recompute()" + chr(34),
                  chr(34) + "doc.saveAs(path)" + chr(34),
                  chr(34) + "print('OK_COLUMN')" + chr(34)])

        return self._run_script_list(L, "Columna", f"{shape} h={height}m", "OK_COLUMN")

    # ═══════════════════════════════════════════════════════════════════
    # TRANSFORMACIONES
    # ═══════════════════════════════════════════════════════════════════

    def _move_object(self, params):
        label = params.get("label", "")
        dx = float(params.get("dx", 0))
        dy = float(params.get("dy", 0))
        dz = float(params.get("dz", 0))
        if not label:
            return {"thought": "", "display": "Necesito el label del objeto.", "voice": "Falta label."}
        if not confirmation.require("freecad", "move_object", f"Mover {label} en ({dx},{dy},{dz})"):
            return {"thought": "Cancelado", "display": "Cancelado.", "voice": "Cancelado."}

        L = [chr(34) + "import FreeCAD" + chr(34),
             chr(34) + "import os" + chr(34),
             "f" + chr(34) + "path = r'" + str(WORKSPACE).replace(chr(92), chr(47)) + "'" + chr(34),
             chr(34) + "doc = FreeCAD.openDocument(path)" + chr(34),
             "f" + chr(34) + "obj = doc.getObject('" + label + "')" + chr(34),
             chr(34) + "if not obj:" + chr(34),
             chr(34) + "    print('ERR_OBJ_NOT_FOUND')" + chr(34),
             chr(34) + "    import sys; sys.exit(1)" + chr(34),
             chr(34) + "import FreeCAD" + chr(34),
             "f" + chr(34) + "obj.Placement.Base.x += " + str(dx) + chr(34),
             "f" + chr(34) + "obj.Placement.Base.y += " + str(dy) + chr(34),
             "f" + chr(34) + "obj.Placement.Base.z += " + str(dz) + chr(34),
             chr(34) + "doc.recompute()" + chr(34),
             chr(34) + "doc.saveAs(path)" + chr(34),
             chr(34) + "print('OK_MOVE')" + chr(34)]

        return self._run_script_list(L, f"Movido {label}", f"delta ({dx},{dy},{dz})", "OK_MOVE")

    def _rotate_object(self, params):
        label = params.get("label", "")
        axis = params.get("axis", "z").lower()
        angle = float(params.get("angle", 90))
        cx = float(params.get("cx", 0))
        cy = float(params.get("cy", 0))
        cz = float(params.get("cz", 0))
        if not label:
            return {"thought": "", "display": "Necesito el label.", "voice": "Falta label."}
        if not confirmation.require("freecad", "rotate_object", f"Rotar {label} {angle} deg en eje {axis}"):
            return {"thought": "Cancelado", "display": "Cancelado.", "voice": "Cancelado."}

        axis_vec = {"x": "FreeCAD.Vector(1,0,0)", "y": "FreeCAD.Vector(0,1,0)", "z": "FreeCAD.Vector(0,0,1)"}.get(axis, "FreeCAD.Vector(0,0,1)")

        L = [chr(34) + "import FreeCAD" + chr(34),
             chr(34) + "import os" + chr(34),
             "f" + chr(34) + "path = r'" + str(WORKSPACE).replace(chr(92), chr(47)) + "'" + chr(34),
             chr(34) + "doc = FreeCAD.openDocument(path)" + chr(34),
             "f" + chr(34) + "obj = doc.getObject('" + label + "')" + chr(34),
             chr(34) + "if not obj:" + chr(34),
             chr(34) + "    print('ERR_OBJ_NOT_FOUND')" + chr(34),
             chr(34) + "    import sys; sys.exit(1)" + chr(34),
             "f" + chr(34) + "rot = FreeCAD.Rotation(" + axis_vec + ", " + str(angle) + ")" + chr(34),
             "f" + chr(34) + "centro = FreeCAD.Vector(" + str(cx) + ", " + str(cy) + ", " + str(cz) + ")" + chr(34),
             chr(34) + "obj.Placement = FreeCAD.Placement(centro, rot, centro)" + chr(34),
             chr(34) + "doc.recompute()" + chr(34),
             chr(34) + "doc.saveAs(path)" + chr(34),
             chr(34) + "print('OK_ROTATE')" + chr(34)]

        return self._run_script_list(L, f"Rotado {label}", f"{angle} deg eje {axis}", "OK_ROTATE")

    def _array_objects(self, params):
        label = params.get("label", "")
        nx = int(params.get("nx", 1))
        ny = int(params.get("ny", 1))
        nz = int(params.get("nz", 1))
        dx = float(params.get("dx", 1))
        dy = float(params.get("dy", 0))
        dz = float(params.get("dz", 0))
        if not label:
            return {"thought": "", "display": "Necesito el label.", "voice": "Falta label."}
        total = nx * ny * nz
        if total > 200:
            return {"thought": "", "display": f"Demasiadas copias ({total}). Max 200.", "voice": "Excede limite."}
        if not confirmation.require("freecad", "array_objects", f"Array {nx}x{ny}x{nz} de {label} ({total} copias)"):
            return {"thought": "Cancelado", "display": "Cancelado.", "voice": "Cancelado."}

        L = [chr(34) + "import FreeCAD" + chr(34),
             chr(34) + "import os" + chr(34),
             "f" + chr(34) + "path = r'" + str(WORKSPACE).replace(chr(92), chr(47)) + "'" + chr(34),
             chr(34) + "doc = FreeCAD.openDocument(path)" + chr(34),
             "f" + chr(34) + "orig = doc.getObject('" + label + "')" + chr(34),
             chr(34) + "if not orig:" + chr(34),
             chr(34) + "    print('ERR_OBJ_NOT_FOUND')" + chr(34),
             chr(34) + "    import sys; sys.exit(1)" + chr(34),
             "f" + chr(34) + "NX = " + str(nx) + chr(34),
             "f" + chr(34) + "NY = " + str(ny) + chr(34),
             "f" + chr(34) + "NZ = " + str(nz) + chr(34),
             "f" + chr(34) + "DX = " + str(dx) + chr(34),
             "f" + chr(34) + "DY = " + str(dy) + chr(34),
             "f" + chr(34) + "DZ = " + str(dz) + chr(34),
             chr(34) + "count = 0" + chr(34),
             chr(34) + "for i in range(NX):" + chr(34),
             chr(34) + "    for j in range(NY):" + chr(34),
             chr(34) + "        for k in range(NZ):" + chr(34),
             chr(34) + "            if i == 0 and j == 0 and k == 0:" + chr(34),
             chr(34) + "                continue" + chr(34),
             chr(34) + "            copia = doc.addObject('Part::Feature', 'Copia')" + chr(34),
             chr(34) + "            copia.Shape = orig.Shape.copy()" + chr(34),
             chr(34) + "            copia.Label = orig.Label + '_' + str(count)" + chr(34),
             "f" + chr(34) + "            copia.Placement.Base = FreeCAD.Vector(DX*i, DY*j, DZ*k)" + chr(34),
             chr(34) + "            count += 1" + chr(34),
             chr(34) + "doc.recompute()" + chr(34),
             chr(34) + "doc.saveAs(path)" + chr(34),
             chr(34) + "print('OK_ARRAY')" + chr(34),
             "f" + chr(34) + "print('TOTAL=' + str(count))" + chr(34)]

        return self._run_script_list(L, f"Array {label}", f"{total-1} copias generadas", "OK_ARRAY")

    def _delete_object(self, params):
        label = params.get("label", "")
        if not label:
            return {"thought": "", "display": "Necesito el label.", "voice": "Falta label."}
        if not confirmation.require("freecad", "delete_object", f"Borrar {label}"):
            return {"thought": "Cancelado", "display": "Cancelado.", "voice": "Cancelado."}

        L = [chr(34) + "import FreeCAD" + chr(34),
             chr(34) + "import os" + chr(34),
             "f" + chr(34) + "path = r'" + str(WORKSPACE).replace(chr(92), chr(47)) + "'" + chr(34),
             chr(34) + "doc = FreeCAD.openDocument(path)" + chr(34),
             "f" + chr(34) + "obj = doc.getObject('" + label + "')" + chr(34),
             chr(34) + "if not obj:" + chr(34),
             chr(34) + "    print('ERR_OBJ_NOT_FOUND')" + chr(34),
             chr(34) + "    import sys; sys.exit(1)" + chr(34),
             chr(34) + "doc.removeObject(obj.Name)" + chr(34),
             chr(34) + "doc.recompute()" + chr(34),
             chr(34) + "doc.saveAs(path)" + chr(34),
             chr(34) + "print('OK_DELETE')" + chr(34)]

        return self._run_script_list(L, f"Borrado {label}", "", "OK_DELETE")

    def _boolean_op(self, params):
        label1 = params.get("label1", "")
        label2 = params.get("label2", "")
        op = params.get("op", "cut").lower()
        if not label1 or not label2:
            return {"thought": "", "display": "Necesito 2 labels.", "voice": "Faltan labels."}
        if op not in ("cut", "union", "intersection"):
            return {"thought": "", "display": "op debe ser cut, union o intersection.", "voice": "op invalido."}
        if not confirmation.require("freecad", "boolean_op", f"{op} {label1} y {label2}"):
            return {"thought": "Cancelado", "display": "Cancelado.", "voice": "Cancelado."}

        op_str = {"cut": "shape1.cut(shape2)", "union": "shape1.fuse(shape2)", "intersection": "shape1.common(shape2)"}[op]

        L = [chr(34) + "import FreeCAD" + chr(34),
             chr(34) + "import Part" + chr(34),
             chr(34) + "import os" + chr(34),
             "f" + chr(34) + "path = r'" + str(WORKSPACE).replace(chr(92), chr(47)) + "'" + chr(34),
             chr(34) + "doc = FreeCAD.openDocument(path)" + chr(34),
             "f" + chr(34) + "obj1 = doc.getObject('" + label1 + "')" + chr(34),
             "f" + chr(34) + "obj2 = doc.getObject('" + label2 + "')" + chr(34),
             chr(34) + "if not obj1 or not obj2:" + chr(34),
             chr(34) + "    print('ERR_OBJ_NOT_FOUND')" + chr(34),
             chr(34) + "    import sys; sys.exit(1)" + chr(34),
             chr(34) + "shape1 = obj1.Shape" + chr(34),
             chr(34) + "shape2 = obj2.Shape" + chr(34),
             "f" + chr(34) + "resultado = " + op_str + chr(34),
             "f" + chr(34) + "nuevo = doc.addObject('Part::Feature', '" + op + "_result')" + chr(34),
             chr(34) + "nuevo.Shape = resultado" + chr(34),
             "f" + chr(34) + "nuevo.Label = '" + label1 + "_" + op + "_" + label2 + "'" + chr(34),
             chr(34) + "doc.removeObject(obj1.Name)" + chr(34),
             chr(34) + "doc.removeObject(obj2.Name)" + chr(34),
             chr(34) + "doc.recompute()" + chr(34),
             chr(34) + "doc.saveAs(path)" + chr(34),
             chr(34) + "print('OK_BOOLEAN')" + chr(34)]

        return self._run_script_list(L, f"Boolean {op}", f"{label1} + {label2}", "OK_BOOLEAN")

    def _set_color(self, params):
        label = params.get("label", "")
        r = float(params.get("r", 0.5))
        g = float(params.get("g", 0.5))
        b = float(params.get("b", 0.5))
        if not label:
            return {"thought": "", "display": "Necesito el label.", "voice": "Falta label."}

        L = [chr(34) + "import FreeCAD" + chr(34),
             chr(34) + "import os" + chr(34),
             "f" + chr(34) + "path = r'" + str(WORKSPACE).replace(chr(92), chr(47)) + "'" + chr(34),
             chr(34) + "doc = FreeCAD.openDocument(path)" + chr(34),
             "f" + chr(34) + "obj = doc.getObject('" + label + "')" + chr(34),
             chr(34) + "if not obj:" + chr(34),
             chr(34) + "    print('ERR_OBJ_NOT_FOUND')" + chr(34),
             chr(34) + "    import sys; sys.exit(1)" + chr(34),
             chr(34) + "if obj.ViewObject:" + chr(34),
             "f" + chr(34) + "    obj.ViewObject.ShapeColor = (" + str(r) + ", " + str(g) + ", " + str(b) + ")" + chr(34),
             chr(34) + "doc.saveAs(path)" + chr(34),
             chr(34) + "print('OK_COLOR')" + chr(34)]

        return self._run_script_list(L, f"Color {label}", f"RGB({r},{g},{b})", "OK_COLOR")

    # ═══════════════════════════════════════════════════════════════════
    # IMPORT/EXPORT (STEP, OBJ, STL)
    # ═══════════════════════════════════════════════════════════════════

    def _export_step(self, out_path):
        if not out_path:
            out_path = str(SANDBOX / f"export_{uuid.uuid4().hex[:8]}.step")
        out_path = str(Path(out_path))
        L = [chr(34) + "import FreeCAD" + chr(34),
             chr(34) + "import Part" + chr(34),
             chr(34) + "import os" + chr(34),
             "f" + chr(34) + "path = r'" + str(WORKSPACE).replace(chr(92), chr(47)) + "'" + chr(34),
             chr(34) + "if not os.path.exists(path):" + chr(34),
             chr(34) + "    print('ERR_NO_WORKSPACE')" + chr(34),
             chr(34) + "    import sys; sys.exit(1)" + chr(34),
             chr(34) + "doc = FreeCAD.openDocument(path)" + chr(34),
             "f" + chr(34) + "objs = [o for o in doc.Objects]" + chr(34),
             "f" + chr(34) + "Part.export(objs, r'" + out_path.replace(chr(92), chr(47)) + "')" + chr(34),
             chr(34) + "print('OK_EXPORT_STEP')" + chr(34)]

        r = self._run_script_list(L, "STEP exportado", out_path, "OK_EXPORT_STEP")
        if isinstance(r, dict) and "display" in r and "STEP" in r.get("display", ""):
            r["display"] = "STEP exportado:\n  " + out_path + "\n\nAbre en FreeCAD, Fusion 360, SolidWorks, etc."
        return r

    def _export_obj(self, out_path):
        if not out_path:
            out_path = str(SANDBOX / f"export_{uuid.uuid4().hex[:8]}.obj")
        out_path = str(Path(out_path))
        L = [chr(34) + "import FreeCAD" + chr(34),
             chr(34) + "import Mesh" + chr(34),
             chr(34) + "import os" + chr(34),
             "f" + chr(34) + "path = r'" + str(WORKSPACE).replace(chr(92), chr(47)) + "'" + chr(34),
             chr(34) + "if not os.path.exists(path):" + chr(34),
             chr(34) + "    print('ERR_NO_WORKSPACE')" + chr(34),
             chr(34) + "    import sys; sys.exit(1)" + chr(34),
             chr(34) + "doc = FreeCAD.openDocument(path)" + chr(34),
             "f" + chr(34) + "output = r'" + out_path.replace(chr(92), chr(47)) + "'" + chr(34),
             chr(34) + "import Part" + chr(34),
             chr(34) + "for obj in doc.Objects:" + chr(34),
             chr(34) + "    if hasattr(obj, 'Shape') and obj.Shape:" + chr(34),
             chr(34) + "        try:" + chr(34),
             chr(34) + "            mesh = Mesh.Mesh(obj.Shape.tessellate(0.1))" + chr(34),
             chr(34) + "        except Exception:" + chr(34),
             chr(34) + "            pass" + chr(34),
             chr(34) + "        try:" + chr(34),
             chr(34) + "            __import__('MeshPart').export([obj], output)" + chr(34),
             chr(34) + "            break" + chr(34),
             chr(34) + "        except Exception as e:" + chr(34),
             chr(34) + "            print('WARN: ' + str(e))" + chr(34),
             chr(34) + "print('OK_EXPORT_OBJ')" + chr(34)]

        return self._run_script_list(L, "OBJ exportado", out_path, "OK_EXPORT_OBJ")

    def _export_stl(self, out_path):
        if not out_path:
            out_path = str(SANDBOX / f"export_{uuid.uuid4().hex[:8]}.stl")
        out_path = str(Path(out_path))
        L = [chr(34) + "import FreeCAD" + chr(34),
             chr(34) + "import Mesh" + chr(34),
             chr(34) + "import MeshPart" + chr(34),
             chr(34) + "import os" + chr(34),
             "f" + chr(34) + "path = r'" + str(WORKSPACE).replace(chr(92), chr(47)) + "'" + chr(34),
             chr(34) + "if not os.path.exists(path):" + chr(34),
             chr(34) + "    print('ERR_NO_WORKSPACE')" + chr(34),
             chr(34) + "    import sys; sys.exit(1)" + chr(34),
             chr(34) + "doc = FreeCAD.openDocument(path)" + chr(34),
             "f" + chr(34) + "output = r'" + out_path.replace(chr(92), chr(47)) + "'" + chr(34),
             chr(34) + "exportado = False" + chr(34),
             chr(34) + "for obj in doc.Objects:" + chr(34),
             chr(34) + "    if hasattr(obj, 'Shape') and obj.Shape:" + chr(34),
             chr(34) + "        try:" + chr(34),
             chr(34) + "            mesh = doc.addObject('Mesh::Feature', 'STLExport')" + chr(34),
             chr(34) + "            mesh.Mesh = MeshPart.meshFromShape(Shape=obj.Shape, LinearDeflection=0.1, AngularDeflection=0.5, Relative=False)" + chr(34),
             chr(34) + "            mesh.Mesh.write(output)" + chr(34),
             chr(34) + "            doc.removeObject(mesh.Name)" + chr(34),
             chr(34) + "            exportado = True" + chr(34),
             chr(34) + "            break" + chr(34),
             chr(34) + "        except Exception as e:" + chr(34),
             chr(34) + "            print('WARN: ' + str(e))" + chr(34),
             chr(34) + "print('OK_EXPORT_STL')" + chr(34)]

        return self._run_script_list(L, "STL exportado", out_path, "OK_EXPORT_STL")

    def _import_step(self, step_path):
        if not step_path or not Path(step_path).exists():
            return {"thought": "", "display": f"No encuentro: {step_path}", "voice": "No encontrado."}
        step_path = str(Path(step_path))
        if not confirmation.require("freecad", "import_step", f"Importar {Path(step_path).name}"):
            return {"thought": "Cancelado", "display": "Cancelado.", "voice": "Cancelado."}

        L = [chr(34) + "import FreeCAD" + chr(34),
             chr(34) + "import Part" + chr(34),
             chr(34) + "import Import" + chr(34),
             chr(34) + "import os" + chr(34),
             "f" + chr(34) + "path = r'" + str(WORKSPACE).replace(chr(92), chr(47)) + "'" + chr(34),
             chr(34) + "if os.path.exists(path):" + chr(34),
             chr(34) + "    doc = FreeCAD.openDocument(path)" + chr(34),
             chr(34) + "else:" + chr(34),
             chr(34) + "    doc = FreeCAD.newDocument('NitroWorkspace')" + chr(34),
             "f" + chr(34) + "Import.insert(r'" + step_path.replace(chr(92), chr(47)) + "', doc.Name)" + chr(34),
             chr(34) + "doc.recompute()" + chr(34),
             chr(34) + "doc.saveAs(path)" + chr(34),
             chr(34) + "print('OK_IMPORT_STEP')" + chr(34),
             "f" + chr(34) + "print('NUM_OBJ=' + str(len(doc.Objects)))" + chr(34)]

        return self._run_script_list(L, "STEP importado", Path(step_path).name, "OK_IMPORT_STEP")

    def _export_pdf_techdraw(self, out_path):
        """Exporta las vistas a PDF usando TechDraw (mas fiable que importPDF)."""
        if not out_path:
            out_path = str(SANDBOX / f"export_{uuid.uuid4().hex[:8]}.pdf")
        out_path = str(Path(out_path))
        if not confirmation.require("freecad", "export_pdf_techdraw", f"Exportar a PDF: {Path(out_path).name}"):
            return {"thought": "Cancelado", "display": "Cancelado.", "voice": "Cancelado."}

        L = [chr(34) + "import FreeCAD" + chr(34),
             chr(34) + "import TechDraw" + chr(34),
             chr(34) + "import os" + chr(34),
             "f" + chr(34) + "path = r'" + str(WORKSPACE).replace(chr(92), chr(47)) + "'" + chr(34),
             chr(34) + "if not os.path.exists(path):" + chr(34),
             chr(34) + "    print('ERR_NO_WORKSPACE')" + chr(34),
             chr(34) + "    import sys; sys.exit(1)" + chr(34),
             chr(34) + "doc = FreeCAD.openDocument(path)" + chr(34),
             "f" + chr(34) + "output = r'" + out_path.replace(chr(92), chr(47)) + "'" + chr(34),
             chr(34) + "try:" + chr(34),
             chr(34) + "    page = doc.addObject('TechDraw::DrawPage', 'Page')" + chr(34),
             chr(34) + "    template = doc.addObject('TechDraw::DrawSVGTemplate', 'Template')" + chr(34),
             chr(34) + "    import TechDraw" + chr(34),
             chr(34) + "    import os.path" + chr(34),
             chr(34) + "    template.Template = os.path.join(TechDraw.getUserMacroDir(True), 'A4_LandscapeTD.svg')" + chr(34),
             chr(34) + "    page.Template = template" + chr(34),
             chr(34) + "    objs = [o for o in doc.Objects if hasattr(o, 'Shape') and o.Shape]" + chr(34),
             chr(34) + "    for i, obj in enumerate(objs):" + chr(34),
             chr(34) + "        view = doc.addObject('TechDraw::DrawViewPart', 'View' + str(i))" + chr(34),
             chr(34) + "        view.Source = [obj]" + chr(34),
             chr(34) + "        view.Direction = FreeCAD.Vector(1, 1, 1)" + chr(34),
             chr(34) + "        view.Scale = 1.0" + chr(34),
             chr(34) + "        page.addView(view)" + chr(34),
             chr(34) + "    doc.recompute()" + chr(34),
             chr(34) + "    TechDraw.writePageAsPdf(page, output)" + chr(34),
             chr(34) + "    print('OK_PDF_TECHDRAW')" + chr(34),
             chr(34) + "except Exception as e:" + chr(34),
             chr(34) + "    print('ERR_PDF: ' + str(e))" + chr(34)]

        r = self._run_script_list(L, "PDF exportado", out_path, "OK_PDF_TECHDRAW")
        if isinstance(r, dict) and "display" in r and "PDF" in r.get("display", ""):
            r["display"] = "PDF exportado (TechDraw):\n  " + out_path
        return r

    def _run_script_list(self, lineas, nombre, info, marcador):
        """Helper: ejecuta un script de FreeCAD desde una lista de lineas."""
        script = chr(10).join(lineas)
        stdout, stderr, err = _run_freecad(script)
        if err:
            return {"thought": "Error", "display": err, "voice": "Error."}
        if marcador not in (stdout or ""):
            return {"thought": "Error", "display": f"Fallo: {(stdout or '')[:400]}", "voice": "Error."}
        return {
            "thought": f"{nombre} creado",
            "display": f"{nombre} agregado.\n {info}",
            "voice": f"{nombre} agregado.",
        }

    def _clear_workspace(self):
        if not confirmation.require("freecad", "clear_workspace", "Borrar el workspace actual"):
            return {"thought": "Cancelado", "display": "Cancelado.", "voice": "Cancelado."}
        code = SCRIPT_CLEAR.format(path=str(WORKSPACE).replace("\\", "\\\\"))
        stdout, stderr, err = _run_freecad(code)
        if err:
            return {"thought": "Error", "display": err, "voice": "Error."}
        return {
            "thought": "Workspace borrado",
            "display": "Workspace borrado.",
            "voice": "Workspace borrado.",
        }