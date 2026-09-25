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
    import importPDF
    importPDF.export([o for o in doc.Objects], r'{out_path}')
    print('OK_EXPORT_PDF')
    print('PATH=' + r'{out_path}')
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