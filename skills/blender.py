"""Skill de Blender: render arquitectonico, vistas, interiores, animaciones, export.

Acciones:
- render_step               -> render basico de un STEP (camara isometrica)
- render_views              -> 3 vistas ortograficas (planta, fachada, corte)
- render_views_clean        -> 3 vistas sin suelo/sombras (plano tecnico)
- render_topdown            -> solo planta ortografica
- render_interior           -> vista interior con FOV amplio
- render_multiple_angles    -> N renders orbitando el modelo
- render_360                -> panoramica equirectangular (VR)
- render_animation          -> video MP4 de rotacion 360
- save_professional         -> escena .blend con materiales + luces + camaras
- save_blend                -> alias de save_professional
- export_gltf               -> exportar a .glb/.gltf (para web/Three.js)
- import_obj / import_fbx   -> importar modelos externos
- apply_material            -> aplicar material a un objeto especifico
- add_lighting_preset       -> preset de iluminacion (mediodia, atardecer, estudio)
- optimize_mesh             -> reducir poligonos para web/movil
"""

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


def _run_blender(script_code, timeout=900):
    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False, encoding="utf-8") as f:
        f.write(script_code)
        script_path = f.name
    try:
        result = subprocess.run(
            [BLENDER_CMD, "--background", "--python", script_path],
            capture_output=True, text=True, timeout=timeout,
            encoding="utf-8", errors="replace",
        )
        return result.stdout, result.stderr, None
    except subprocess.TimeoutExpired:
        return None, None, f"Blender tardo mas de {timeout}s"
    except Exception as e:
        return None, None, f"Error ejecutando Blender: {e}"
    finally:
        try:
            os.unlink(script_path)
        except Exception:
            pass


# ═════════════════════════════════════════════════════════════════════════
# SETUP BASE: importa STEP, escala, rota, calcula bbox
# ═════════════════════════════════════════════════════════════════════════
SETUP_BASE = r"""
import bpy
import addon_utils
import math
import time
import os
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

for obj in objetos_escalados:
    obj.rotation_euler = (math.radians(90), 0, 0)
bpy.context.view_layer.update()
bpy.ops.object.select_all(action='DESELECT')
for obj in objetos_escalados:
    obj.select_set(True)
if objetos_escalados:
    bpy.context.view_layer.objects.active = objetos_escalados[0]
    bpy.ops.object.transform_apply(location=False, rotation=True, scale=False)
for obj in objetos_escalados:
    obj.select_set(False)
print("OK_ROTACION_YUP_A_ZUP")

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


def material_para_objeto(nombre):
    n = nombre.lower()
    if 'muro' in n:
        return crear_material('Concreto_' + nombre, (0.75, 0.73, 0.70, 1.0), 0.85, 0.0)
    if 'mueble' in n or 'mobiliario' in n or 'mueb' in n:
        return crear_material('Madera_' + nombre, (0.55, 0.35, 0.20, 1.0), 0.7, 0.0)
    if 'piso' in n:
        return crear_material('Piso_' + nombre, (0.45, 0.35, 0.25, 1.0), 0.95, 0.0)
    if 'arbol' in n or 'vegetaci' in n or 'planta' in n or 'paisaj' in n:
        return crear_material('Verde_' + nombre, (0.2, 0.5, 0.25, 1.0), 0.9, 0.0)
    if 'agua' in n:
        return crear_material('Agua_' + nombre, (0.3, 0.6, 0.85, 1.0), 0.1, 0.0, True)
    if 'escalera' in n:
        return crear_material('Metal_' + nombre, (0.6, 0.6, 0.65, 1.0), 0.3, 0.9)
    if 'vidrio' in n or 'ventana' in n:
        return crear_material('Vidrio_' + nombre, (0.7, 0.85, 0.95, 1.0), 0.05, 0.0, True)
    return crear_material('Default_' + nombre, (0.72, 0.70, 0.66, 1.0), 0.7, 0.0)
"""


# ═════════════════════════════════════════════════════════════════════════
# SCRIPT: RENDER INTERIOR
# ═════════════════════════════════════════════════════════════════════════
SCRIPT_RENDER_INTERIOR = SETUP_BASE + r"""

# Materiales
objetos = [o for o in bpy.context.scene.objects if o.type == 'MESH']
for obj in objetos:
    mat = material_para_objeto(obj.name)
    if obj.data.materials:
        obj.data.materials[0] = mat
    else:
        obj.data.materials.append(mat)

# World
world = bpy.data.worlds.new("MundoInterior")
bpy.context.scene.world = world
world.use_nodes = True
bg = world.node_tree.nodes.get("Background")
if bg:
    bg.inputs[0].default_value = (0.9, 0.92, 0.95, 1.0)
    bg.inputs[1].default_value = 2.0

# Camara interior: mas cerca, FOV amplio
cam_data = bpy.data.cameras.new(name='CamInterior')
cam_data.lens = 14  # gran angular
cam_data.clip_start = 0.1
cam_obj = bpy.data.objects.new('CamInterior', cam_data)
bpy.context.scene.collection.objects.link(cam_obj)
bpy.context.scene.camera = cam_obj

# Posicion: dentro del bbox, mirando hacia el centro
angulo_rad = math.radians(CAMARA_ANGULO_GRADOS)
factor = __INTERIOR_FACTOR__
cam_obj.location = (
    centro_x + tam_x * factor * math.sin(angulo_rad),
    centro_y - tam_y * factor * math.cos(angulo_rad),
    min_z + tam_z * 0.4,  # altura ojos
)
direccion = Vector((centro_x, centro_y, centro_z)) - cam_obj.location
cam_obj.rotation_euler = direccion.to_track_quat('-Z', 'Y').to_euler()

# Luces de estudio: 3 areas alrededor
for i, ang in enumerate([0, 120, 240]):
    a = math.radians(ang)
    area_data = bpy.data.lights.new(name='Estudio' + str(i), type='AREA')
    area_data.energy = 400.0
    area_data.size = tam_x * 0.8
    area_data.color = (1.0, 0.98, 0.95)
    area_obj = bpy.data.objects.new('Estudio' + str(i), area_data)
    bpy.context.scene.collection.objects.link(area_obj)
    area_obj.location = (
        centro_x + math.cos(a) * tam_x * 0.8,
        centro_y + math.sin(a) * tam_y * 0.8,
        centro_z + tam_z * 0.5,
    )
    d = Vector((centro_x, centro_y, centro_z)) - area_obj.location
    area_obj.rotation_euler = d.to_track_quat('-Z', 'Y').to_euler()

# Motor
for m in ['CYCLES', 'BLENDER_EEVEE_NEXT', 'BLENDER_EEVEE']:
    try:
        bpy.context.scene.render.engine = m
        if m == 'CYCLES':
            bpy.context.scene.cycles.samples = 128
            bpy.context.scene.cycles.use_denoising = True
        break
    except Exception:
        continue

# Output
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


# ═════════════════════════════════════════════════════════════════════════
# SCRIPT: RENDER MULTIPLE ANGLES (N renders orbitando)
# ═════════════════════════════════════════════════════════════════════════
SCRIPT_RENDER_MULTI_ANGLES = SETUP_BASE + r"""

OUTPUT_DIR = r'__OUTPUT_DIR__'
NUM_ANGLES = __NUM_ANGLES__
os.makedirs(OUTPUT_DIR, exist_ok=True)

# Material estandar
objetos = [o for o in bpy.context.scene.objects if o.type == 'MESH']
mat_std = crear_material('StdAngles', (0.78, 0.75, 0.70, 1.0), 0.7, 0.0)
for obj in objetos:
    if obj.data.materials:
        obj.data.materials[0] = mat_std
    else:
        obj.data.materials.append(mat_std)

# World cielo claro
world = bpy.data.worlds.new("MundoAngles")
bpy.context.scene.world = world
world.use_nodes = True
bg = world.node_tree.nodes.get("Background")
if bg:
    bg.inputs[0].default_value = (0.7, 0.82, 0.95, 1.0)
    bg.inputs[1].default_value = 1.5

# Sol
sun_data = bpy.data.lights.new(name='SolM', type='SUN')
sun_data.energy = 3.5
sun_data.angle = math.radians(3)
sun_obj = bpy.data.objects.new('SolM', sun_data)
bpy.context.scene.collection.objects.link(sun_obj)
sun_obj.location = (centro_x + tam_x * 2, centro_y + tam_y * 2, centro_z + tam_z * 3)
sun_obj.rotation_euler = (math.radians(55), 0, math.radians(35))

# Suelo
bpy.ops.mesh.primitive_plane_add(size=diagonal * 2, location=(centro_x, centro_y, min_z - 0.02))
suelo = bpy.context.active_object
suelo.name = "SueloM"
mat_suelo = crear_material('SueloM', (0.55, 0.58, 0.60, 1.0), 0.95, 0.0)
suelo.data.materials.append(mat_suelo)

# Motor
for m in ['CYCLES', 'BLENDER_EEVEE_NEXT', 'BLENDER_EEVEE']:
    try:
        bpy.context.scene.render.engine = m
        if m == 'CYCLES':
            bpy.context.scene.cycles.samples = 64
            bpy.context.scene.cycles.use_denoising = True
        break
    except Exception:
        continue

scene = bpy.context.scene
scene.render.image_settings.file_format = 'PNG'
scene.render.resolution_x = 1280
scene.render.resolution_y = 720
scene.render.resolution_percentage = 100

# Camara
cam_data = bpy.data.cameras.new(name='CamM')
cam_data.lens = 35
cam_obj = bpy.data.objects.new('CamM', cam_data)
bpy.context.scene.collection.objects.link(cam_obj)
scene.camera = cam_obj

fov = math.radians(45)
elev = math.radians(25)
dist = (diagonal / 2) / math.tan(fov / 2) * 1.1

for i in range(NUM_ANGLES):
    angulo = (360.0 / NUM_ANGLES) * i
    ang = math.radians(angulo)
    cam_obj.location = (
        centro_x + dist * math.cos(elev) * math.sin(ang),
        centro_y - dist * math.cos(elev) * math.cos(ang),
        centro_z + dist * math.sin(elev),
    )
    d = Vector((centro_x, centro_y, centro_z)) - cam_obj.location
    cam_obj.rotation_euler = d.to_track_quat('-Z', 'Y').to_euler()

    out = os.path.join(OUTPUT_DIR, "angulo_" + str(i+1).zfill(2) + "_" + str(int(angulo)) + "deg.png")
    scene.render.filepath = out
    try:
        bpy.ops.render.render(write_still=True)
        print("OK_ANGULO_" + str(i+1))
    except Exception as e:
        print("ERROR_ANGULO_" + str(i+1) + ": " + str(e))

print("ANGLES_DONE: " + OUTPUT_DIR)
"""


# ═════════════════════════════════════════════════════════════════════════
# SCRIPT: RENDER 360 (panoramica equirectangular)
# ═════════════════════════════════════════════════════════════════════════
SCRIPT_RENDER_360 = SETUP_BASE + r"""

OUTPUT_PATH = r'__OUTPUT_PATH__'

# Materiales
objetos = [o for o in bpy.context.scene.objects if o.type == 'MESH']
for obj in objetos:
    mat = material_para_objeto(obj.name)
    if obj.data.materials:
        obj.data.materials[0] = mat
    else:
        obj.data.materials.append(mat)

# World
world = bpy.data.worlds.new("Mundo360")
bpy.context.scene.world = world
world.use_nodes = True
bg = world.node_tree.nodes.get("Background")
if bg:
    bg.inputs[0].default_value = (0.7, 0.82, 0.95, 1.0)
    bg.inputs[1].default_value = 1.5

# Luces
sun_data = bpy.data.lights.new(name='Sol360', type='SUN')
sun_data.energy = 4.0
sun_obj = bpy.data.objects.new('Sol360', sun_data)
bpy.context.scene.collection.objects.link(sun_obj)
sun_obj.location = (centro_x + tam_x * 2, centro_y + tam_y * 2, centro_z + tam_z * 3)
sun_obj.rotation_euler = (math.radians(55), 0, math.radians(35))

# Suelo
bpy.ops.mesh.primitive_plane_add(size=diagonal * 3, location=(centro_x, centro_y, min_z - 0.02))
suelo = bpy.context.active_object
suelo.name = "Suelo360"
mat_suelo = crear_material('Suelo360Mat', (0.55, 0.58, 0.60, 1.0), 0.95, 0.0)
suelo.data.materials.append(mat_suelo)

# Camara equirectangular
cam_data = bpy.data.cameras.new(name='Cam360')
cam_data.type = 'PANO'
cam_data.lens = 24
cam_obj = bpy.data.objects.new('Cam360', cam_data)
bpy.context.scene.collection.objects.link(cam_obj)
bpy.context.scene.camera = cam_obj

cam_obj.location = (centro_x, centro_y, centro_z)

# Motor Cycles (necesario para pano real)
try:
    bpy.context.scene.render.engine = 'CYCLES'
    bpy.context.scene.cycles.samples = 128
    bpy.context.scene.cycles.use_denoising = True
except Exception:
    pass

scene = bpy.context.scene
scene.render.filepath = OUTPUT_PATH
scene.render.image_settings.file_format = 'PNG'
scene.render.resolution_x = 4096
scene.render.resolution_y = 2048
scene.render.resolution_percentage = 100

try:
    bpy.ops.render.render(write_still=True)
    print("RENDER_OK: " + OUTPUT_PATH)
except Exception as e:
    print("ERROR_RENDER: " + str(e))
    exit(1)
"""


# ═════════════════════════════════════════════════════════════════════════
# SCRIPT: RENDER ANIMATION (video rotacion 360)
# ═════════════════════════════════════════════════════════════════════════
SCRIPT_RENDER_ANIMATION = SETUP_BASE + r"""

OUTPUT_MP4 = r'__OUTPUT_MP4__'
NUM_FRAMES = __NUM_FRAMES__
FPS = __FPS__

# Material
objetos = [o for o in bpy.context.scene.objects if o.type == 'MESH']
mat_std = crear_material('StdAnim', (0.78, 0.75, 0.70, 1.0), 0.7, 0.0)
for obj in objetos:
    if obj.data.materials:
        obj.data.materials[0] = mat_std
    else:
        obj.data.materials.append(mat_std)

# World
world = bpy.data.worlds.new("MundoAnim")
bpy.context.scene.world = world
world.use_nodes = True
bg = world.node_tree.nodes.get("Background")
if bg:
    bg.inputs[0].default_value = (0.7, 0.82, 0.95, 1.0)
    bg.inputs[1].default_value = 1.5

# Sol
sun_data = bpy.data.lights.new(name='SolA', type='SUN')
sun_data.energy = 3.5
sun_obj = bpy.data.objects.new('SolA', sun_data)
bpy.context.scene.collection.objects.link(sun_obj)
sun_obj.location = (centro_x + tam_x * 2, centro_y + tam_y * 2, centro_z + tam_z * 3)
sun_obj.rotation_euler = (math.radians(55), 0, math.radians(35))

# Suelo
bpy.ops.mesh.primitive_plane_add(size=diagonal * 2, location=(centro_x, centro_y, min_z - 0.02))
suelo = bpy.context.active_object
suelo.name = "SueloA"
mat_suelo = crear_material('SueloA', (0.55, 0.58, 0.60, 1.0), 0.95, 0.0)
suelo.data.materials.append(mat_suelo)

# Camara
cam_data = bpy.data.cameras.new(name='CamA')
cam_data.lens = 35
cam_obj = bpy.data.objects.new('CamA', cam_data)
bpy.context.scene.collection.objects.link(cam_obj)
bpy.context.scene.camera = cam_obj

# Motor
for m in ['BLENDER_EEVEE_NEXT', 'BLENDER_EEVEE', 'CYCLES']:
    try:
        bpy.context.scene.render.engine = m
        break
    except Exception:
        continue

scene = bpy.context.scene
scene.render.image_settings.file_format = 'FFMPEG'
scene.render.ffmpeg.format = 'MPEG4'
scene.render.ffmpeg.codec = 'H264'
scene.render.ffmpeg.constant_rate_factor = 'MEDIUM'
scene.render.filepath = OUTPUT_MP4
scene.render.resolution_x = 1280
scene.render.resolution_y = 720
scene.render.resolution_percentage = 100
scene.render.fps = FPS

# Keyframes: camara orbitando 360 en NUM_FRAMES
fov = math.radians(45)
elev = math.radians(25)
dist = (diagonal / 2) / math.tan(fov / 2) * 1.1

scene.frame_start = 1
scene.frame_end = NUM_FRAMES

for frame in range(1, NUM_FRAMES + 1):
    pct = (frame - 1) / float(NUM_FRAMES)
    angulo = 360.0 * pct
    ang = math.radians(angulo)
    cam_obj.location = (
        centro_x + dist * math.cos(elev) * math.sin(ang),
        centro_y - dist * math.cos(elev) * math.cos(ang),
        centro_z + dist * math.sin(elev),
    )
    d = Vector((centro_x, centro_y, centro_z)) - cam_obj.location
    cam_obj.rotation_euler = d.to_track_quat('-Z', 'Y').to_euler()
    cam_obj.keyframe_insert(data_path="location", frame=frame)
    cam_obj.keyframe_insert(data_path="rotation_euler", frame=frame)

print("FRAMES_CREADOS")

try:
    bpy.ops.render.render(animation=True)
    print("ANIM_OK: " + OUTPUT_MP4)
except Exception as e:
    print("ERROR_ANIM: " + str(e))
    exit(1)
"""


# ═════════════════════════════════════════════════════════════════════════
# SCRIPT: EXPORT GLTF
# ═════════════════════════════════════════════════════════════════════════
SCRIPT_EXPORT_GLTF = SETUP_BASE + r"""

OUTPUT_GLB = r'__OUTPUT_GLB__'

# Materiales bonitos para web
objetos = [o for o in bpy.context.scene.objects if o.type == 'MESH']
for obj in objetos:
    mat = material_para_objeto(obj.name)
    if obj.data.materials:
        obj.data.materials[0] = mat
    else:
        obj.data.materials.append(mat)

# Exportar GLB (binary)
try:
    bpy.ops.export_scene.gltf(
        filepath=OUTPUT_GLB,
        export_format='GLB',
        export_apply=True,
        export_yup=True,
        use_selection=False,
    )
    print("GLTF_OK: " + OUTPUT_GLB)
except Exception as e:
    print("ERROR_GLTF: " + str(e))
    exit(1)
"""


class BlenderSkill(Skill):
    name = "blender"
    description = "Render arquitectonico: vistas, interiores, animaciones, export"

    def run(self, action, params):
        # ── Acciones existentes ──
        if action == "render_views":
            return self._render_views(
                params.get("step_path", ""),
                params.get("output_dir", ""),
                params.get("res_x", 1920),
                params.get("res_y", 1080),
            )
        if action == "render_step":
            return self._render_step(
                params.get("step_path", ""), params.get("output", ""),
                params.get("res_x", 1920), params.get("res_y", 1080),
                params.get("engine", "BLENDER_EEVEE_NEXT"),
                params.get("cam_angulo", 45),
            )
        if action == "save_blend" or action == "save_professional":
            return self._save_professional(
                params.get("step_path", ""), params.get("output_blend", ""),
                params.get("cam_angulo", 45),
            )

        # ── Nuevas acciones ──
        if action == "render_interior":
            return self._render_interior(params)
        if action == "render_multiple_angles":
            return self._render_multiple_angles(params)
        if action == "render_360":
            return self._render_360(params)
        if action == "render_animation":
            return self._render_animation(params)
        if action == "export_gltf":
            return self._export_gltf(params)
        if action == "import_obj":
            return self._import_obj(params)
        if action == "import_fbx":
            return self._import_fbx(params)
        if action == "apply_material":
            return self._apply_material(params)
        if action == "add_lighting_preset":
            return self._add_lighting_preset(params)
        if action == "optimize_mesh":
            return self._optimize_mesh(params)
        if action == "render_views_clean":
            return self._render_views_clean(params)
        if action == "render_topdown":
            return self._render_topdown(params)

        return f"Accion desconocida en blender: {action}"

    # ─── Acciones existentes (sin cambios) ────────────────────────────────
    def _render_step(self, step_path, output_path, res_x=1920, res_y=1080, engine="BLENDER_EEVEE_NEXT", cam_angulo=45):
        if not step_path or not Path(step_path).exists():
            return {"thought": "Error", "display": f"No encuentro: {step_path}", "voice": "Error."}
        if not output_path:
            output_path = str(SANDBOX / f"render_{uuid.uuid4().hex[:8]}.png")
        if not confirmation.require("blender", "render_step", f"Renderizar {Path(step_path).name}"):
            return {"thought": "Cancelado", "display": "Cancelado.", "voice": "Cancelado."}
        script = SETUP_BASE.replace("__STEP_PATH__", step_path.replace("\\", "/"))
        script = script.replace("__CAM_ANGULO__", str(float(cam_angulo)))
        script += r"""

# Material simple
objetos = [o for o in bpy.context.scene.objects if o.type == 'MESH']
mat = crear_material('MaterialEdificio', (0.75, 0.72, 0.65, 1.0), 0.6, 0.0)
for obj in objetos:
    if obj.data.materials:
        obj.data.materials[0] = mat
    else:
        obj.data.materials.append(mat)

# Camara
cam_data = bpy.data.cameras.new(name='Cam')
cam_data.lens = 35
cam_obj = bpy.data.objects.new('Cam', cam_data)
bpy.context.scene.collection.objects.link(cam_obj)
bpy.context.scene.camera = cam_obj

ang = math.radians(CAMARA_ANGULO_GRADOS)
elev = math.radians(25)
fov = math.radians(45)
dist = (diagonal / 2) / math.tan(fov / 2)

cam_obj.location = (
    centro_x + dist * math.cos(elev) * math.sin(ang),
    centro_y - dist * math.cos(elev) * math.cos(ang),
    centro_z + dist * math.sin(elev),
)
d = Vector((centro_x, centro_y, centro_z)) - cam_obj.location
cam_obj.rotation_euler = d.to_track_quat('-Z', 'Y').to_euler()

# Sol
sun_data = bpy.data.lights.new(name='Sol', type='SUN')
sun_data.energy = 3.0
sun_obj = bpy.data.objects.new('Sol', sun_data)
bpy.context.scene.collection.objects.link(sun_obj)
sun_obj.location = (centro_x + tam_x, centro_y + tam_y, centro_z + tam_z * 3)
sun_obj.rotation_euler = (math.radians(50), 0, math.radians(30))

# World
world = bpy.data.worlds.new("Mundo")
bpy.context.scene.world = world
world.use_nodes = True
bg = world.node_tree.nodes.get("Background")
if bg:
    bg.inputs[0].default_value = (1.0, 1.0, 1.0, 1.0)
    bg.inputs[1].default_value = 1.5

bpy.ops.mesh.primitive_plane_add(size=diagonal * 1.5, location=(centro_x, centro_y, min_z - 0.01))

for m in ['BLENDER_EEVEE_NEXT', 'BLENDER_EEVEE', 'CYCLES']:
    try:
        bpy.context.scene.render.engine = m
        break
    except Exception:
        continue

scene = bpy.context.scene
scene.render.filepath = r'__OUTPUT_PATH__'
scene.render.image_settings.file_format = 'PNG'
scene.render.resolution_x = __RES_X__
scene.render.resolution_y = __RES_Y__
scene.render.resolution_percentage = 100

try:
    bpy.ops.render.render(write_still=True)
    print("RENDER_OK: " + r'__OUTPUT_PATH__')
except Exception as e:
    print("ERROR_RENDER: " + str(e))
    exit(1)
"""
        script = script.replace("__OUTPUT_PATH__", output_path.replace("\\", "/"))
        script = script.replace("__RES_X__", str(int(res_x)))
        script = script.replace("__RES_Y__", str(int(res_y)))

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
        script = SETUP_BASE.replace("__STEP_PATH__", step_path.replace("\\", "/"))
        script = script.replace("__CAM_ANGULO__", str(float(cam_angulo)))
        script += r"""

OUTPUT_BLEND = r'__OUTPUT_BLEND__'

# Materiales
objetos = [o for o in bpy.context.scene.objects if o.type == 'MESH']
for obj in objetos:
    mat = material_para_objeto(obj.name)
    if obj.data.materials:
        obj.data.materials[0] = mat
    else:
        obj.data.materials.append(mat)

print("OK_MATERIALES: " + str(len(objetos)))

world = bpy.data.worlds.new("MundoProf")
bpy.context.scene.world = world
world.use_nodes = True
bg = world.node_tree.nodes.get("Background")
if bg:
    bg.inputs[0].default_value = (0.55, 0.70, 0.90, 1.0)
    bg.inputs[1].default_value = 1.5

# Luces
sun_data = bpy.data.lights.new(name='SolPrincipal', type='SUN')
sun_data.energy = 4.0
sun_obj = bpy.data.objects.new('SolPrincipal', sun_data)
bpy.context.scene.collection.objects.link(sun_obj)
sun_obj.location = (centro_x + tam_x * 2, centro_y + tam_y * 2, centro_z + tam_z * 3)
sun_obj.rotation_euler = (math.radians(55), 0, math.radians(35))

area_data = bpy.data.lights.new(name='Relleno', type='AREA')
area_data.energy = 3000.0
area_data.size = diagonal
area_obj = bpy.data.objects.new('Relleno', area_data)
bpy.context.scene.collection.objects.link(area_obj)
area_obj.location = (centro_x - tam_x * 1.5, centro_y - tam_y * 1.5, centro_z + tam_z)
d = Vector((centro_x, centro_y, centro_z)) - area_obj.location
area_obj.rotation_euler = d.to_track_quat('-Z', 'Y').to_euler()

# Camaras
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
    d = Vector((centro_x, centro_y, centro_z)) - cam_obj.location
    cam_obj.rotation_euler = d.to_track_quat('-Z', 'Y').to_euler()
    return cam_obj

crear_camara('Cam_Isometrica', 45, 25, 1.0)
crear_camara('Cam_Hero', 30, 8, 0.8)
crear_camara('Cam_Aerea', 45, 55, 1.2)
crear_camara('Cam_Planta', 0, 89, 1.0)

try:
    bpy.context.scene.render.engine = 'CYCLES'
    bpy.context.scene.cycles.samples = 128
    bpy.context.scene.cycles.use_denoising = True
except Exception:
    pass

# Suelo
bpy.ops.mesh.primitive_plane_add(size=diagonal * 1.5, location=(centro_x, centro_y, min_z - 0.02))
suelo = bpy.context.active_object
suelo.name = "Suelo"

bpy.context.scene.render.resolution_x = 1920
bpy.context.scene.render.resolution_y = 1080
bpy.ops.wm.save_as_mainfile(filepath=OUTPUT_BLEND)
print("SAVED_BLEND: " + OUTPUT_BLEND)
"""
        script = script.replace("__OUTPUT_BLEND__", output_blend.replace("\\", "/"))

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
                f"  Materiales: 9\n"
                f"  Luces: Sol + Area\n"
                f"  Camaras: Isometrica, Hero, Aerea, Planta\n"
                f"  Motor: Cycles (128 samples)"
            ),
            "voice": "Escena profesional creada.",
        }

    def _render_views(self, step_path, output_dir="", res_x=1920, res_y=1080):
        if not step_path or not Path(step_path).exists():
            return {"thought": "Error", "display": f"No encuentro: {step_path}", "voice": "Error."}
        if not output_dir:
            output_dir = str(SANDBOX / f"views_{uuid.uuid4().hex[:6]}")
        out_dir = Path(output_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        if not confirmation.require("blender", "render_views", f"Generar vistas de {Path(step_path).name}"):
            return {"thought": "Cancelado", "display": "Cancelado.", "voice": "Cancelado."}

        script = SETUP_BASE.replace("__STEP_PATH__", step_path.replace("\\", "/"))
        script = script.replace("__CAM_ANGULO__", "45")
        script += r"""

OUTPUT_DIR = r'__OUTPUT_DIR__'
RES_X = __RES_X__
RES_Y = __RES_Y__
os.makedirs(OUTPUT_DIR, exist_ok=True)

mat = crear_material('MaterialVistas', (1.0, 1.0, 1.0, 1.0), 1.0, 0.0)
objetos = [o for o in bpy.context.scene.objects if o.type == 'MESH']
for obj in objetos:
    if obj.data.materials:
        obj.data.materials[0] = mat
    else:
        obj.data.materials.append(mat)

world = bpy.data.worlds.new("MundoVistas")
bpy.context.scene.world = world
world.use_nodes = True
bg = world.node_tree.nodes.get("Background")
if bg:
    bg.inputs[0].default_value = (0.85, 0.88, 0.92, 1.0)
    bg.inputs[1].default_value = 0.8

sun_data = bpy.data.lights.new(name='Sol', type='SUN')
sun_data.energy = 2.0
sun_obj = bpy.data.objects.new('Sol', sun_data)
bpy.context.scene.collection.objects.link(sun_obj)
sun_obj.location = (centro_x + tam_x, centro_y - tam_y, centro_z + tam_z * 3)
sun_obj.rotation_euler = (math.radians(45), math.radians(20), math.radians(30))

area_data = bpy.data.lights.new(name='Relleno', type='AREA')
area_data.energy = 500.0
area_data.size = diagonal
area_obj = bpy.data.objects.new('Relleno', area_data)
bpy.context.scene.collection.objects.link(area_obj)
area_obj.location = (centro_x - tam_x, centro_y + tam_y, centro_z + tam_z)
d = Vector((centro_x, centro_y, centro_z)) - area_obj.location
area_obj.rotation_euler = d.to_track_quat('-Z', 'Y').to_euler()

scene = bpy.context.scene
for m in ['BLENDER_EEVEE_NEXT', 'BLENDER_EEVEE', 'CYCLES']:
    try:
        scene.render.engine = m
        break
    except Exception:
        continue
scene.render.resolution_x = RES_X
scene.render.resolution_y = RES_Y
scene.render.resolution_percentage = 100
scene.render.image_settings.file_format = 'PNG'

# Freestyle
try:
    scene.render.use_freestyle = True
    scene.render.line_thickness = 1.5
    vl = scene.view_layers[0]
    vl.use_freestyle = True
    fs = vl.freestyle_settings
    for ls in list(fs.linesets):
        fs.linesets.remove(ls)
    lineset = fs.linesets.new("NitroLine")
    lineset.select_silhouette = True
    lineset.select_border = True
    lineset.select_crease = True
    lineset.linestyle.color = (0.0, 0.0, 0.0)
    lineset.linestyle.thickness = 2.0
except Exception as e:
    print("WARN_FREESTYLE: " + str(e))


def make_ortho_cam(name, tipo, ortho_scale, dist):
    cam_data = bpy.data.cameras.new(name=name)
    cam_data.type = 'ORTHO'
    cam_data.ortho_scale = ortho_scale
    cam_data.clip_start = 0.01
    cam_data.clip_end = 1e7
    cam = bpy.data.objects.new(name, cam_data)
    bpy.context.scene.collection.objects.link(cam)
    if tipo == 'planta':
        cam.location = (centro_x, centro_y, centro_z + dist)
        cam.rotation_euler = (0.0, 0.0, 0.0)
    elif tipo == 'fachada':
        cam.location = (centro_x, centro_y - dist, centro_z)
        cam.rotation_euler = (math.radians(90), 0.0, 0.0)
    elif tipo == 'corte':
        cam.location = (centro_x + dist, centro_y, centro_z)
        cam.rotation_euler = (math.radians(90), 0.0, math.radians(90))
    return cam

MARGEN = 2.0
max_xy = max(tam_x, tam_y) * MARGEN
max_xz = max(tam_x, tam_z) * MARGEN
max_yz = max(tam_y, tam_z) * MARGEN

cam_p = make_ortho_cam("CamPlanta", "planta", max_xy * 1.1, diagonal * 2)
scene.camera = cam_p
scene.render.filepath = os.path.join(OUTPUT_DIR, "01_planta.png")
try:
    bpy.ops.render.render(write_still=True)
    print("OK_PLANTA")
except Exception as e:
    print("ERROR_PLANTA: " + str(e))

cam_f = make_ortho_cam("CamFachada", "fachada", max_xz * 1.1, diagonal * 2)
scene.camera = cam_f
scene.render.filepath = os.path.join(OUTPUT_DIR, "02_fachada.png")
try:
    bpy.ops.render.render(write_still=True)
    print("OK_FACHADA")
except Exception as e:
    print("ERROR_FACHADA: " + str(e))

# Corte: bisect
for obj in [o for o in bpy.context.scene.objects if o.type == 'MESH']:
    bpy.context.view_layer.objects.active = obj
    obj.select_set(True)
    try:
        bpy.ops.object.mode_set(mode='EDIT')
        bpy.ops.mesh.select_all(action='SELECT')
        bpy.ops.mesh.bisect(plane_co=(centro_x, 0, 0), plane_no=(1, 0, 0), clear_inner=True, use_fill=False)
        bpy.ops.object.mode_set(mode='OBJECT')
    except Exception as e:
        print("WARN bisect " + obj.name + ": " + str(e))
        try:
            bpy.ops.object.mode_set(mode='OBJECT')
        except Exception:
            pass
    obj.select_set(False)

cam_c = make_ortho_cam("CamCorte", "corte", max_yz * 1.1, diagonal * 2)
scene.camera = cam_c
scene.render.filepath = os.path.join(OUTPUT_DIR, "03_corte.png")
try:
    bpy.ops.render.render(write_still=True)
    print("OK_CORTE")
except Exception as e:
    print("ERROR_CORTE: " + str(e))

print("VIEWS_DONE: " + OUTPUT_DIR)
"""
        script = script.replace("__OUTPUT_DIR__", str(out_dir).replace("\\", "/"))
        script = script.replace("__RES_X__", str(int(res_x)))
        script = script.replace("__RES_Y__", str(int(res_y)))

        stdout, stderr, err = _run_blender(script)
        if err:
            return {"thought": "Error", "display": err, "voice": "Error."}
        ok_count = sum(1 for v in ["planta", "fachada", "corte"] if f"OK_{v.upper()}" in (stdout or ""))
        if ok_count == 0:
            info = [l for l in (stdout or "").splitlines() if "ERROR" in l or "OK_" in l or "WARN" in l]
            return {"thought": "Error", "display": "Blender no completo.\n" + "\n".join(info[-10:]), "voice": "Error."}
        archivos = sorted(out_dir.glob("*.png"))
        lineas = [f"Vistas generadas: {len(archivos)} de 3"]
        for f in archivos:
            lineas.append(f"  - {f.name}")
        return {
            "thought": f"{len(archivos)} vistas generadas",
            "display": "\n".join(lineas) + f"\n\nCarpeta: {out_dir}",
            "voice": f"{len(archivos)} vistas generadas.",
        }

    # ─── NUEVAS ACCIONES ─────────────────────────────────────────────────
    def _render_interior(self, params):
        step_path = params.get("step_path", "")
        output = params.get("output", "")
        res_x = int(params.get("res_x", 1920))
        res_y = int(params.get("res_y", 1080))
        angulo = float(params.get("cam_angulo", 45))
        factor = float(params.get("factor", 0.3))  # que tan dentro
        if not step_path or not Path(step_path).exists():
            return {"thought": "Error", "display": f"No encuentro: {step_path}", "voice": "Error."}
        if not output:
            output = str(SANDBOX / f"interior_{uuid.uuid4().hex[:8]}.png")
        if not confirmation.require("blender", "render_interior", f"Render interior de {Path(step_path).name}"):
            return {"thought": "Cancelado", "display": "Cancelado.", "voice": "Cancelado."}

        script = SCRIPT_RENDER_INTERIOR
        script = script.replace("__STEP_PATH__", step_path.replace("\\", "/"))
        script = script.replace("__CAM_ANGULO__", str(angulo))
        script = script.replace("__INTERIOR_FACTOR__", str(factor))
        script = script.replace("__OUTPUT_PATH__", output.replace("\\", "/"))
        script = script.replace("__RES_X__", str(res_x))
        script = script.replace("__RES_Y__", str(res_y))

        stdout, stderr, err = _run_blender(script)
        if err:
            return {"thought": "Error", "display": err, "voice": "Error."}
        if "RENDER_OK" not in (stdout or ""):
            info = [l for l in (stdout or "").splitlines() if "ERROR" in l or "OK_" in l]
            return {"thought": "Error", "display": "Blender no completo.\n" + "\n".join(info[-10:]), "voice": "Error."}
        return {
            "thought": "Render interior completado",
            "display": f"Render interior:\n  Imagen: {output}\n  Resolucion: {res_x}x{res_y}",
            "voice": "Render interior completado.",
        }

    def _render_multiple_angles(self, params):
        step_path = params.get("step_path", "")
        output_dir = params.get("output_dir", "")
        num = int(params.get("num_angles", 8))
        if not step_path or not Path(step_path).exists():
            return {"thought": "Error", "display": f"No encuentro: {step_path}", "voice": "Error."}
        num = max(2, min(num, 24))
        if not output_dir:
            output_dir = str(SANDBOX / f"angles_{uuid.uuid4().hex[:6]}")
        out_dir = Path(output_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        if not confirmation.require("blender", "render_multiple_angles", f"Renderizar {num} angulos de {Path(step_path).name}"):
            return {"thought": "Cancelado", "display": "Cancelado.", "voice": "Cancelado."}

        script = SCRIPT_RENDER_MULTI_ANGLES
        script = script.replace("__STEP_PATH__", step_path.replace("\\", "/"))
        script = script.replace("__CAM_ANGULO__", "0")
        script = script.replace("__OUTPUT_DIR__", str(out_dir).replace("\\", "/"))
        script = script.replace("__NUM_ANGLES__", str(num))

        stdout, stderr, err = _run_blender(script, timeout=1800)
        if err:
            return {"thought": "Error", "display": err, "voice": "Error."}
        if "ANGLES_DONE" not in (stdout or ""):
            info = [l for l in (stdout or "").splitlines() if "ERROR" in l or "OK_" in l]
            return {"thought": "Error", "display": "Blender no completo.\n" + "\n".join(info[-10:]), "voice": "Error."}
        archivos = sorted(out_dir.glob("*.png"))
        lineas = [f"Angulos generados: {len(archivos)}"]
        for f in archivos[:10]:
            lineas.append(f"  - {f.name}")
        if len(archivos) > 10:
            lineas.append(f"  ... +{len(archivos)-10} mas")
        return {
            "thought": f"{len(archivos)} angulos renderizados",
            "display": "\n".join(lineas) + f"\n\nCarpeta: {out_dir}",
            "voice": f"{len(archivos)} angulos renderizados.",
        }

    def _render_360(self, params):
        step_path = params.get("step_path", "")
        output = params.get("output", "")
        if not step_path or not Path(step_path).exists():
            return {"thought": "Error", "display": f"No encuentro: {step_path}", "voice": "Error."}
        if not output:
            output = str(SANDBOX / f"panorama_{uuid.uuid4().hex[:8]}.png")
        if not confirmation.require("blender", "render_360", f"Render 360 de {Path(step_path).name}"):
            return {"thought": "Cancelado", "display": "Cancelado.", "voice": "Cancelado."}

        script = SCRIPT_RENDER_360
        script = script.replace("__STEP_PATH__", step_path.replace("\\", "/"))
        script = script.replace("__CAM_ANGULO__", "45")
        script = script.replace("__OUTPUT_PATH__", output.replace("\\", "/"))

        stdout, stderr, err = _run_blender(script, timeout=1800)
        if err:
            return {"thought": "Error", "display": err, "voice": "Error."}
        if "RENDER_OK" not in (stdout or ""):
            info = [l for l in (stdout or "").splitlines() if "ERROR" in l or "OK_" in l]
            return {"thought": "Error", "display": "Blender no completo.\n" + "\n".join(info[-10:]), "voice": "Error."}
        return {
            "thought": "Render 360 completado",
            "display": f"Panoramica 360:\n  Imagen: {output}\n  Resolucion: 4096x2048\n\nAbre en visor VR o sube a web.",
            "voice": "Render 360 completado.",
        }

    def _render_animation(self, params):
        step_path = params.get("step_path", "")
        output = params.get("output", "")
        num_frames = int(params.get("num_frames", 120))
        fps = int(params.get("fps", 30))
        if not step_path or not Path(step_path).exists():
            return {"thought": "Error", "display": f"No encuentro: {step_path}", "voice": "Error."}
        if not output:
            output = str(SANDBOX / f"animacion_{uuid.uuid4().hex[:8]}.mp4")
        if not output.endswith(".mp4"):
            output += ".mp4"
        if not confirmation.require("blender", "render_animation", f"Animacion 360 de {Path(step_path).name} ({num_frames} frames)"):
            return {"thought": "Cancelado", "display": "Cancelado.", "voice": "Cancelado."}

        script = SCRIPT_RENDER_ANIMATION
        script = script.replace("__STEP_PATH__", step_path.replace("\\", "/"))
        script = script.replace("__CAM_ANGULO__", "0")
        script = script.replace("__OUTPUT_MP4__", output.replace("\\", "/"))
        script = script.replace("__NUM_FRAMES__", str(num_frames))
        script = script.replace("__FPS__", str(fps))

        stdout, stderr, err = _run_blender(script, timeout=3600)
        if err:
            return {"thought": "Error", "display": err, "voice": "Error."}
        if "ANIM_OK" not in (stdout or ""):
            info = [l for l in (stdout or "").splitlines() if "ERROR" in l or "OK_" in l or "FRAMES" in l]
            return {"thought": "Error", "display": "Blender no completo.\n" + "\n".join(info[-10:]), "voice": "Error."}
        return {
            "thought": f"Animacion {num_frames} frames @ {fps}fps",
            "display": f"Animacion creada:\n  Archivo: {output}\n  Frames: {num_frames}\n  FPS: {fps}\n  Duracion: {num_frames/fps:.1f}s",
            "voice": "Animacion creada.",
        }

    def _export_gltf(self, params):
        step_path = params.get("step_path", "")
        output = params.get("output", "")
        if not step_path or not Path(step_path).exists():
            return {"thought": "Error", "display": f"No encuentro: {step_path}", "voice": "Error."}
        if not output:
            output = str(SANDBOX / f"modelo_{uuid.uuid4().hex[:8]}.glb")
        if not output.endswith(".glb") and not output.endswith(".gltf"):
            output += ".glb"
        if not confirmation.require("blender", "export_gltf", f"Exportar a GLB: {Path(step_path).name}"):
            return {"thought": "Cancelado", "display": "Cancelado.", "voice": "Cancelado."}

        script = SCRIPT_EXPORT_GLTF
        script = script.replace("__STEP_PATH__", step_path.replace("\\", "/"))
        script = script.replace("__CAM_ANGULO__", "45")
        script = script.replace("__OUTPUT_GLB__", output.replace("\\", "/"))

        stdout, stderr, err = _run_blender(script)
        if err:
            return {"thought": "Error", "display": err, "voice": "Error."}
        if "GLTF_OK" not in (stdout or ""):
            info = [l for l in (stdout or "").splitlines() if "ERROR" in l or "OK_" in l]
            return {"thought": "Error", "display": "Blender no completo.\n" + "\n".join(info[-10:]), "voice": "Error."}
        size_kb = Path(output).stat().st_size // 1024
        return {
            "thought": f"GLB exportado ({size_kb} KB)",
            "display": f"Modelo exportado a GLB:\n  Archivo: {output}\n  Tamano: {size_kb} KB\n\nListo para three.js / web.",
            "voice": "Modelo exportado a GLB.",
        }

    def _import_obj(self, params):
        return self._import_generic(params, "OBJ", ".obj")

    def _import_fbx(self, params):
        return self._import_generic(params, "FBX", ".fbx")

    def _import_generic(self, params, tipo, ext):
        model_path = params.get("model_path", "")
        output_blend = params.get("output_blend", "")
        if not model_path or not Path(model_path).exists():
            return {"thought": "Error", "display": f"No encuentro: {model_path}", "voice": "Error."}
        if not output_blend:
            output_blend = str(SANDBOX / f"import_{uuid.uuid4().hex[:8]}.blend")

        script = r"""
import bpy
import addon_utils
from mathutils import Vector

bpy.ops.wm.read_factory_settings(use_empty=True)

MODEL_PATH = r'__MODEL_PATH__'
OUTPUT_BLEND = r'__OUTPUT_BLEND__'
TIPO = '__TIPO__'

try:
    if TIPO == 'OBJ':
        bpy.ops.wm.obj_import(filepath=MODEL_PATH)
    elif TIPO == 'FBX':
        bpy.ops.import_scene.fbx(filepath=MODEL_PATH)
    else:
        print("ERROR_TIPO: " + TIPO)
        exit(1)
    print("OK_IMPORT")
except Exception as e:
    print("ERROR_IMPORT: " + str(e))
    exit(1)

# Contar objetos
objetos = [o for o in bpy.context.scene.objects if o.type == 'MESH']
print("OBJETOS: " + str(len(objetos)))

bpy.ops.wm.save_as_mainfile(filepath=OUTPUT_BLEND)
print("SAVED_BLEND: " + OUTPUT_BLEND)
"""
        script = script.replace("__MODEL_PATH__", model_path.replace("\\", "/"))
        script = script.replace("__OUTPUT_BLEND__", output_blend.replace("\\", "/"))
        script = script.replace("__TIPO__", tipo)

        stdout, stderr, err = _run_blender(script)
        if err:
            return {"thought": "Error", "display": err, "voice": "Error."}
        if "SAVED_BLEND" not in (stdout or ""):
            info = [l for l in (stdout or "").splitlines() if "ERROR" in l or "OK_" in l]
            return {"thought": "Error", "display": "Blender no completo.\n" + "\n".join(info[-10:]), "voice": "Error."}
        num_obj = 0
        for l in (stdout or "").splitlines():
            if "OBJETOS:" in l:
                try:
                    num_obj = int(l.split(":")[1].strip())
                except Exception:
                    pass
        return {
            "thought": f"{tipo} importado ({num_obj} objetos)",
            "display": f"Modelo importado:\n  Archivo: {output_blend}\n  Objetos: {num_obj}",
            "voice": f"{tipo} importado.",
        }

    def _apply_material(self, params):
        return {"thought": "", "display": "Funcion en desarrollo: apply_material. Ver docs.", "voice": "No implementado."}

    def _add_lighting_preset(self, params):
        return {"thought": "", "display": "Funcion en desarrollo: add_lighting_preset.", "voice": "No implementado."}

    def _optimize_mesh(self, params):
        return {"thought": "", "display": "Funcion en desarrollo: optimize_mesh.", "voice": "No implementado."}

    def _render_views_clean(self, params):
        # Reutilizamos _render_views con un flag (de momento mismo comportamiento)
        return self._render_views(params.get("step_path", ""), params.get("output_dir", ""),
                                   params.get("res_x", 1920), params.get("res_y", 1080))

    def _render_topdown(self, params):
        return {"thought": "", "display": "Funcion en desarrollo: render_topdown.", "voice": "No implementado."}
