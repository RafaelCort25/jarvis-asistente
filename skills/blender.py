"""Skill de Blender: renderiza STEP a PNG y guarda escenas profesionales."""
import os
import subprocess
import tempfile
import uuid
from pathlib import Path

from skills.base import Skill
from core import confirmation

ROOT = Path(__file__).resolve().parent.parent
SANDBOX = ROOT / "sandbox" / "blender"
SANDBOX.mkdir(parents=True, exist_ok=True)

from core.paths import BLENDER_CMD


def _run_blender(script_code):
    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False, encoding="utf-8") as f:
        f.write(script_code)
        script_path = f.name
    try:
        result = subprocess.run(
            [BLENDER_CMD, "--background", "--python", script_path],
            capture_output=True, text=True, timeout=900,
            encoding="utf-8", errors="replace",
        )
        return result.stdout, result.stderr, None
    except subprocess.TimeoutExpired:
        return None, None, "Blender tardo mas de 900s"
    except Exception as e:
        return None, None, f"Error ejecutando Blender: {e}"
    finally:
        try:
            os.unlink(script_path)
        except Exception:
            pass


SETUP_BASE = r"""
import bpy
import addon_utils
import math
import time
from mathutils import Vector

STEP_PATH = r'__STEP_PATH__'
CAMARA_ANGULO_GRADOS = __CAM_ANGULO__

bpy.ops.wm.read_factory_settings(use_empty=True)
addon_utils.enable("bl_ext.blender_org.step_importer", default_set=True)
time.sleep(0.5)
bpy.ops.import_scene.step(filepath=STEP_PATH)
print("OK_IMPORT")

objetos_escalados = [o for o in bpy.context.scene.objects if o.type == 'MESH']
for obj in objetos_escalados:
    obj.scale = (1000.0, 1000.0, 1000.0)
bpy.context.view_layer.update()
for obj in objetos_escalados:
    bpy.context.view_layer.objects.active = obj
    obj.select_set(True)
bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
for obj in objetos_escalados:
    obj.select_set(False)
print("OK_ESCALA")

min_x = min_y = min_z = float('inf')
max_x = max_y = max_z = float('-inf')
objetos = [o for o in bpy.context.scene.objects if o.type == 'MESH']
for obj in objetos:
    for corner in obj.bound_box:
        w = obj.matrix_world @ Vector(corner)
        min_x = min(min_x, w.x); min_y = min(min_y, w.y); min_z = min(min_z, w.z)
        max_x = max(max_x, w.x); max_y = max(max_y, w.y); max_z = max(max_z, w.z)

centro_x = (min_x + max_x) / 2
centro_y = (min_y + max_y) / 2
centro_z = (min_z + max_z) / 2
tam_x = max_x - min_x
tam_y = max_y - min_y
tam_z = max_z - min_z
diagonal = math.sqrt(tam_x*tam_x + tam_y*tam_y + tam_z*tam_z)
print("BBOX: " + str(round(tam_x,2)) + " x " + str(round(tam_y,2)) + " x " + str(round(tam_z,2)))
print("DIAGONAL: " + str(round(diagonal,2)))
"""


SCRIPT_RENDER_STEP = SETUP_BASE + r"""

mat = bpy.data.materials.new(name="MaterialEdificio")
mat.use_nodes = True
nodes = mat.node_tree.nodes
nodes.clear()
bsdf = nodes.new(type='ShaderNodeBsdfPrincipled')
bsdf.inputs['Base Color'].default_value = (0.75, 0.72, 0.65, 1.0)
bsdf.inputs['Roughness'].default_value = 0.6
output = nodes.new(type='ShaderNodeOutputMaterial')
mat.node_tree.links.new(bsdf.outputs['BSDF'], output.inputs['Surface'])

objetos = [o for o in bpy.context.scene.objects if o.type == 'MESH']
for obj in objetos:
    if obj.data.materials:
        obj.data.materials[0] = mat
    else:
        obj.data.materials.append(mat)

cam_data = bpy.data.cameras.new(name='NitroCam')
cam_data.lens = 35
cam_obj = bpy.data.objects.new('NitroCam', cam_data)
bpy.context.scene.collection.objects.link(cam_obj)
bpy.context.scene.camera = cam_obj

angulo_rad = math.radians(CAMARA_ANGULO_GRADOS)
elevacion_rad = math.radians(25)
fov_rad = math.radians(45)
distancia = (diagonal / 2) / math.tan(fov_rad / 2) * 1.0

cam_x = centro_x + distancia * math.cos(elevacion_rad) * math.sin(angulo_rad)
cam_y = centro_y - distancia * math.cos(elevacion_rad) * math.cos(angulo_rad)
cam_z = centro_z + distancia * math.sin(elevacion_rad)
cam_obj.location = (cam_x, cam_y, cam_z)
direccion = Vector((centro_x, centro_y, centro_z)) - cam_obj.location
cam_obj.rotation_euler = direccion.to_track_quat('-Z', 'Y').to_euler()

sun_data = bpy.data.lights.new(name='Sol', type='SUN')
sun_data.energy = 3.0
sun_obj = bpy.data.objects.new('Sol', sun_data)
bpy.context.scene.collection.objects.link(sun_obj)
sun_obj.location = (centro_x + tam_x, centro_y + tam_y, centro_z + tam_z * 3)
sun_obj.rotation_euler = (math.radians(50), 0, math.radians(30))

world = bpy.data.worlds.new("MundoNitro")
bpy.context.scene.world = world
world.use_nodes = True
bg = world.node_tree.nodes.get("Background")
if bg:
    bg.inputs[0].default_value = (0.85, 0.88, 0.92, 1.0)
    bg.inputs[1].default_value = 1.2

bpy.ops.mesh.primitive_plane_add(size=diagonal * 1.5, location=(centro_x, centro_y, min_z - 0.01))
suelo = bpy.context.active_object
suelo.name = "Suelo"

for m in ['BLENDER_EEVEE_NEXT', 'BLENDER_EEVEE', 'CYCLES']:
    try:
        bpy.context.scene.render.engine = m
        break
    except Exception:
        continue

OUTPUT_PATH = r'__OUTPUT_PATH__'
scene = bpy.context.scene
scene.render.filepath = OUTPUT_PATH
scene.render.image_settings.file_format = 'PNG'
scene.render.resolution_x = __RES_X__
scene.render.resolution_y = __RES_Y__
scene.render.resolution_percentage = 100

try:
    bpy.ops.render.render(write_still=True)
    print("RENDER_OK: " + OUTPUT_PATH)
except Exception as e:
    print("ERROR_RENDER: " + str(e))
    exit(1)
"""


SCRIPT_SAVE_PROFESSIONAL = SETUP_BASE + r"""

OUTPUT_BLEND = r'__OUTPUT_BLEND__'

def crear_material(nombre, color_rgba, roughness=0.6, metallic=0.0, transparente=False):
    mat = bpy.data.materials.new(name=nombre)
    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    nodes.clear()
    bsdf = nodes.new(type='ShaderNodeBsdfPrincipled')
    bsdf.inputs['Base Color'].default_value = color_rgba
    bsdf.inputs['Roughness'].default_value = roughness
    bsdf.inputs['Metallic'].default_value = metallic
    if transparente:
        bsdf.inputs['Alpha'].default_value = 0.3
        mat.blend_method = 'BLEND'
    output = nodes.new(type='ShaderNodeOutputMaterial')
    mat.node_tree.links.new(bsdf.outputs['BSDF'], output.inputs['Surface'])
    return mat

materiales = dict()
materiales['concreto'] = crear_material('Concreto', (0.75, 0.73, 0.70, 1.0), 0.85, 0.0)
materiales['madera'] = crear_material('Madera', (0.55, 0.35, 0.20, 1.0), 0.7, 0.0)
materiales['vidrio'] = crear_material('Vidrio', (0.7, 0.85, 0.95, 1.0), 0.05, 0.0, True)
materiales['verde'] = crear_material('Vegetacion', (0.2, 0.5, 0.25, 1.0), 0.9, 0.0)
materiales['tierra'] = crear_material('Tierra', (0.45, 0.35, 0.25, 1.0), 0.95, 0.0)
materiales['agua'] = crear_material('Agua', (0.3, 0.6, 0.85, 1.0), 0.1, 0.0, True)
materiales['metal'] = crear_material('Metal', (0.6, 0.6, 0.65, 1.0), 0.3, 0.9)
materiales['rojo'] = crear_material('Rojo', (0.75, 0.25, 0.2, 1.0), 0.6, 0.0)
materiales['default'] = crear_material('Default', (0.72, 0.70, 0.66, 1.0), 0.7, 0.0)

def material_para_objeto(nombre):
    n = nombre.lower()
    if 'muro' in n:
        return materiales['concreto']
    if 'mueble' in n or 'mobiliario' in n or 'mueb' in n:
        return materiales['madera']
    if 'piso' in n:
        return materiales['tierra']
    if 'arbol' in n or 'vegetaci' in n or 'planta' in n or 'paisaj' in n:
        return materiales['verde']
    if 'agua' in n:
        return materiales['agua']
    if 'escalera' in n:
        return materiales['metal']
    if 'vidrio' in n or 'ventana' in n:
        return materiales['vidrio']
    return materiales['default']

objetos = [o for o in bpy.context.scene.objects if o.type == 'MESH']
for obj in objetos:
    mat = material_para_objeto(obj.name)
    if obj.data.materials:
        obj.data.materials[0] = mat
    else:
        obj.data.materials.append(mat)

print("OK_MATERIALES: " + str(len(objetos)))

world = bpy.data.worlds.new("MundoNitro")
bpy.context.scene.world = world
world.use_nodes = True
bg = world.node_tree.nodes.get("Background")
if bg:
    bg.inputs[0].default_value = (0.55, 0.70, 0.90, 1.0)
    bg.inputs[1].default_value = 1.5

sun_data = bpy.data.lights.new(name='SolPrincipal', type='SUN')
sun_data.energy = 4.0
sun_data.angle = math.radians(3)
sun_data.color = (1.0, 0.95, 0.85)
sun_obj = bpy.data.objects.new('SolPrincipal', sun_data)
bpy.context.scene.collection.objects.link(sun_obj)
sun_obj.location = (centro_x + tam_x * 2, centro_y + tam_y * 2, centro_z + tam_z * 3)
sun_obj.rotation_euler = (math.radians(55), 0, math.radians(35))

area_data = bpy.data.lights.new(name='Relleno', type='AREA')
area_data.energy = 3000.0
area_data.size = diagonal
area_data.color = (0.9, 0.95, 1.0)
area_obj = bpy.data.objects.new('Relleno', area_data)
bpy.context.scene.collection.objects.link(area_obj)
area_obj.location = (centro_x - tam_x * 1.5, centro_y - tam_y * 1.5, centro_z + tam_z)
dir_luz = Vector((centro_x, centro_y, centro_z)) - area_obj.location
area_obj.rotation_euler = dir_luz.to_track_quat('-Z', 'Y').to_euler()

rim_data = bpy.data.lights.new(name='RimLight', type='AREA')
rim_data.energy = 1500.0
rim_data.size = diagonal * 0.5
rim_data.color = (1.0, 0.98, 0.95)
rim_obj = bpy.data.objects.new('RimLight', rim_data)
bpy.context.scene.collection.objects.link(rim_obj)
rim_obj.location = (centro_x, centro_y + tam_y * 2, centro_z + tam_z * 0.8)
dir_rim = Vector((centro_x, centro_y, centro_z)) - rim_obj.location
rim_obj.rotation_euler = dir_rim.to_track_quat('-Z', 'Y').to_euler()

print("OK_LUCES")

bpy.ops.mesh.primitive_plane_add(size=diagonal * 1.5, location=(centro_x, centro_y, min_z - 0.02))
suelo = bpy.context.active_object
suelo.name = "Suelo"
mat_suelo = crear_material('SueloMat', (0.35, 0.38, 0.40, 1.0), 0.95, 0.0)
suelo.data.materials.append(mat_suelo)

scene = bpy.context.scene
try:
    scene.render.engine = 'CYCLES'
    scene.cycles.samples = 128
    scene.cycles.use_denoising = True
    scene.cycles.max_bounces = 8
    print("OK_CYCLES")
except Exception as e:
    print("AVISO: Cycles no disponible")
    scene.render.engine = 'BLENDER_EEVEE_NEXT'

try:
    scene.eevee.use_gtao = True
    scene.eevee.gtao_distance = 1.0
except Exception:
    pass

try:
    scene.view_settings.view_transform = 'Filmic'
    scene.view_settings.look = 'Medium High Contrast'
except Exception:
    pass

scene.render.resolution_x = 1920
scene.render.resolution_y = 1080
scene.render.image_settings.file_format = 'PNG'
scene.render.film_transparent = False

def crear_camara(nombre, angulo_deg, elevacion_deg, distancia_factor=1.0):
    cam_data = bpy.data.cameras.new(name=nombre)
    cam_data.lens = 35
    cam_obj = bpy.data.objects.new(nombre, cam_data)
    bpy.context.scene.collection.objects.link(cam_obj)

    ang = math.radians(angulo_deg)
    elev = math.radians(elevacion_deg)
    fov = math.radians(45)
    dist = (diagonal / 2) / math.tan(fov / 2) * distancia_factor

    cam_obj.location = (
        centro_x + dist * math.cos(elev) * math.sin(ang),
        centro_y - dist * math.cos(elev) * math.cos(ang),
        centro_z + dist * math.sin(elev),
    )
    direc = Vector((centro_x, centro_y, centro_z)) - cam_obj.location
    cam_obj.rotation_euler = direc.to_track_quat('-Z', 'Y').to_euler()
    return cam_obj

cam_iso = crear_camara('Cam_Isometrica', 45, 25, 1.0)
cam_hero = crear_camara('Cam_Hero', 30, 8, 0.8)
cam_aerea = crear_camara('Cam_Aerea', 45, 55, 1.2)
cam_planta = crear_camara('Cam_Planta', 0, 89, 1.0)

scene.camera = cam_iso
print("OK_CAMARAS")

# Intentar dejar viewport en Material Preview
try:
    for area in bpy.context.screen.areas:
        if area.type == 'VIEW_3D':
            for space in area.spaces:
                if space.type == 'VIEW_3D':
                    space.shading.type = 'MATERIAL'
except Exception:
    pass

bpy.ops.wm.save_as_mainfile(filepath=OUTPUT_BLEND)
print("SAVED_BLEND: " + OUTPUT_BLEND)
"""


class BlenderSkill(Skill):
    name = "blender"
    description = "Renderiza STEP a PNG y guarda escenas profesionales"

    def run(self, action, params):
        if action == "render_step":
            return self._render_step(
                params.get("step_path", ""), params.get("output", ""),
                params.get("res_x", 1920), params.get("res_y", 1080),
                params.get("engine", "BLENDER_EEVEE_NEXT"),
                params.get("cam_angulo", 45),
            )
        if action == "save_blend":
            return self._save_professional(
                params.get("step_path", ""), params.get("output_blend", ""),
                params.get("cam_angulo", 45),
            )
        if action == "save_professional":
            return self._save_professional(
                params.get("step_path", ""), params.get("output_blend", ""),
                params.get("cam_angulo", 45),
            )
        return f"Accion desconocida en blender: {action}"

    def _render_step(self, step_path, output_path, res_x=1920, res_y=1080, engine="BLENDER_EEVEE_NEXT", cam_angulo=45):
        if not step_path or not Path(step_path).exists():
            return {"thought": "Error", "display": f"No encuentro: {step_path}", "voice": "Error."}
        if not output_path:
            output_path = str(SANDBOX / f"render_{uuid.uuid4().hex[:8]}.png")
        if not confirmation.require("blender", "render_step", f"Renderizar {Path(step_path).name}"):
            return {"thought": "Cancelado", "display": "Cancelado.", "voice": "Cancelado."}

        script = SCRIPT_RENDER_STEP
        script = script.replace("__STEP_PATH__", step_path.replace("\\", "/"))
        script = script.replace("__OUTPUT_PATH__", output_path.replace("\\", "/"))
        script = script.replace("__RES_X__", str(int(res_x)))
        script = script.replace("__RES_Y__", str(int(res_y)))
        script = script.replace("__CAM_ANGULO__", str(float(cam_angulo)))

        stdout, stderr, err = _run_blender(script)
        if err:
            return {"thought": "Error", "display": err, "voice": "Error."}
        if "RENDER_OK" not in (stdout or ""):
            info = [l for l in (stdout or "").splitlines() if "ERROR" in l or "OK_" in l or "BBOX" in l or "DIAGONAL" in l]
            return {"thought": "Error", "display": "Blender no completo.\n" + "\n".join(info[-10:]), "voice": "Error."}
        return {"thought": "Render completado", "display": f"Render completado.\n  Imagen: {output_path}\n  Resolucion: {res_x}x{res_y}", "voice": "Render completado."}

    def _save_professional(self, step_path, output_blend="", cam_angulo=45):
        if not step_path or not Path(step_path).exists():
            return {"thought": "Error", "display": f"No encuentro: {step_path}", "voice": "Error."}
        if not output_blend:
            output_blend = str(SANDBOX / f"profesional_{uuid.uuid4().hex[:8]}.blend")
        if not confirmation.require("blender", "save_professional", "Crear escena profesional (materiales + luces + 4 camaras)"):
            return {"thought": "Cancelado", "display": "Cancelado.", "voice": "Cancelado."}

        script = SCRIPT_SAVE_PROFESSIONAL
        script = script.replace("__STEP_PATH__", step_path.replace("\\", "/"))
        script = script.replace("__OUTPUT_BLEND__", output_blend.replace("\\", "/"))
        script = script.replace("__CAM_ANGULO__", str(float(cam_angulo)))

        stdout, stderr, err = _run_blender(script)
        if err:
            return {"thought": "Error", "display": err, "voice": "Error."}
        if "SAVED_BLEND" not in (stdout or ""):
            info = [l for l in (stdout or "").splitlines() if "ERROR" in l or "OK_" in l or "AVISO" in l or "DIAGONAL" in l]
            return {"thought": "Error", "display": "Blender no completo.\n" + "\n".join(info[-10:]), "voice": "Error."}
        return {
            "thought": "Escena profesional creada",
            "display": (
                f"Escena profesional creada.\n"
                f"  Archivo: {output_blend}\n"
                f"  Materiales: 9 (concreto, madera, vidrio, verde, tierra, agua, metal, rojo, default)\n"
                f"  Luces: Sol + Area + Rim\n"
                f"  Camaras: Isometrica, Hero, Aerea, Planta\n"
                f"  Motor: Cycles (128 samples, denoising)\n"
                f"  Color: Filmic + Medium High Contrast\n\n"
                f"Abre el .blend con doble clic."
            ),
            "voice": "Escena profesional creada.",
        }