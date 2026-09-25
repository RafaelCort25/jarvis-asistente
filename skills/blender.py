# skills/blender.py
"""Skill de Blender: renderiza archivos STEP/STL a imagenes."""
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

BLENDER_CMD = os.environ.get(
    "BLENDER_CMD",
    r"C:\Program Files\Blender Foundation\Blender 5.2\blender.exe"
)


def _run_blender(script_code):
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".py", delete=False, encoding="utf-8"
    ) as f:
        f.write(script_code)
        script_path = f.name
    try:
        result = subprocess.run(
            [BLENDER_CMD, "--background", "--python", script_path],
            capture_output=True,
            text=True,
            timeout=600,
            encoding="utf-8",
            errors="replace",
        )
        return result.stdout, result.stderr, None
    except subprocess.TimeoutExpired:
        return None, None, "Blender tardo mas de 600s (timeout)"
    except Exception as e:
        return None, None, f"Error ejecutando Blender: {e}"
    finally:
        try:
            os.unlink(script_path)
        except Exception:
            pass


SCRIPT_RENDER_STEP = r"""
import bpy
import addon_utils
import math
import os
import time
from mathutils import Vector

STEP_PATH = r'{step_path}'
OUTPUT_PATH = r'{output_path}'
RESOLUTION_X = {res_x}
RESOLUTION_Y = {res_y}
RENDER_ENGINE_PREF = '{engine}'
CAMARA_ANGULO_GRADOS = {cam_angulo}    # 0=frontal, 45=isometrico, 90=cenital

# ═══════════════════════════════════════════════════════════
# 1. LIMPIAR ESCENA
# ═══════════════════════════════════════════════════════════
bpy.ops.wm.read_factory_settings(use_empty=True)

# ═══════════════════════════════════════════════════════════
# 2. HABILITAR ADDON STEP
# ═══════════════════════════════════════════════════════════
posibles_addons = [
    "bl_ext.blender_org.step_importer",
    "bl_ext.user_default.step_importer",
    "io_scene_step",
    "step_importer",
]
addon_activado = False
for nombre in posibles_addons:
    try:
        addon_utils.enable(nombre, default_set=True)
        if addon_utils.check(nombre)[1]:
            print("OK_ADDON: " + nombre)
            addon_activado = True
            break
    except Exception as e:
        print("Addon '" + nombre + "' error: " + str(e))

if not addon_activado:
    print("ERROR: No pude activar el addon STEP Importer")
    exit(1)

time.sleep(0.5)

# ═══════════════════════════════════════════════════════════
# 3. IMPORTAR STEP
# ═══════════════════════════════════════════════════════════
try:
    bpy.ops.import_scene.step(filepath=STEP_PATH)
    print("OK_IMPORT_STEP")
except Exception as e:
    print("ERROR_IMPORT: " + str(e))
    exit(1)
    # ═══════════════════════════════════════════════════════════
# 3b. CORREGIR ESCALA (STEP viene en mm, Blender espera m)
# ═══════════════════════════════════════════════════════════
objetos_escalados = [o for o in bpy.context.scene.objects if o.type == 'MESH']
for obj in objetos_escalados:
    obj.scale = (1000.0, 1000.0, 1000.0)

# Forzar actualizacion de la escena
bpy.context.view_layer.update()
print("OK_ESCALA x1000 aplicada a " + str(len(objetos_escalados)) + " objetos")

# Despues de escalar, necesitamos aplicar la escala para que el bounding box
# y la camara usen los valores reales
for obj in objetos_escalados:
    bpy.context.view_layer.objects.active = obj
    obj.select_set(True)
bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
for obj in objetos_escalados:
    obj.select_set(False)

print("OK_TRANSFORM_APPLY")

# ═══════════════════════════════════════════════════════════
# 4. MATERIAL BONITO PARA TODOS LOS OBJETOS
# ═══════════════════════════════════════════════════════════
mat = bpy.data.materials.new(name="MaterialEdificio")
mat.use_nodes = True
nodes = mat.node_tree.nodes
nodes.clear()

# Principled BSDF (material estandar)
bsdf = nodes.new(type='ShaderNodeBsdfPrincipled')
bsdf.inputs['Base Color'].default_value = (0.75, 0.72, 0.65, 1.0)   # beige claro
bsdf.inputs['Roughness'].default_value = 0.6
bsdf.inputs['Metallic'].default_value = 0.0

output = nodes.new(type='ShaderNodeOutputMaterial')
mat.node_tree.links.new(bsdf.outputs['BSDF'], output.inputs['Surface'])

# Aplicar material a todos los meshes
objetos = [o for o in bpy.context.scene.objects if o.type == 'MESH']
for obj in objetos:
    if obj.data.materials:
        obj.data.materials[0] = mat
    else:
        obj.data.materials.append(mat)

print("OK_MATERIAL aplicado a " + str(len(objetos)) + " objetos")

# ═══════════════════════════════════════════════════════════
# 5. CALCULAR BOUNDING BOX
# ═══════════════════════════════════════════════════════════
min_x = min_y = min_z = float('inf')
max_x = max_y = max_z = float('-inf')

for obj in objetos:
    for corner in obj.bound_box:
        world_corner = obj.matrix_world @ Vector(corner)
        min_x = min(min_x, world_corner.x)
        min_y = min(min_y, world_corner.y)
        min_z = min(min_z, world_corner.z)
        max_x = max(max_x, world_corner.x)
        max_y = max(max_y, world_corner.y)
        max_z = max(max_z, world_corner.z)

centro_x = (min_x + max_x) / 2
centro_y = (min_y + max_y) / 2
centro_z = (min_z + max_z) / 2

tam_x = max_x - min_x
tam_y = max_y - min_y
tam_z = max_z - min_z
diagonal = math.sqrt(tam_x*tam_x + tam_y*tam_y + tam_z*tam_z)

print("BBOX: (" + str(round(tam_x, 2)) + ", " + str(round(tam_y, 2)) + ", " + str(round(tam_z, 2)) + ") m")
print("DIAGONAL: " + str(round(diagonal, 2)) + " m")

# ═══════════════════════════════════════════════════════════
# 6. CREAR CAMARA (encuadre automatico)
# ═══════════════════════════════════════════════════════════
cam_data = bpy.data.cameras.new(name='NitroCam')
cam_data.lens = 35  # focal normal (50 seria tele, 24 gran angular)
cam_obj = bpy.data.objects.new('NitroCam', cam_data)
bpy.context.scene.collection.objects.link(cam_obj)
bpy.context.scene.camera = cam_obj

# Posicionar la camara a un angulo alrededor del centro
angulo_rad = math.radians(CAMARA_ANGULO_GRADOS)
elevacion_rad = math.radians(25)  # 25 grados sobre el horizonte

# Distancia justa para que quepa
# FOV ~ 50 grados -> distancia = diagonal / (2 * tan(FOV/2))
fov_rad = math.radians(45)
distancia = (diagonal / 2) / math.tan(fov_rad / 2) * 1.6  # 1.6 = margen

cam_x = centro_x + distancia * math.cos(elevacion_rad) * math.sin(angulo_rad)
cam_y = centro_y - distancia * math.cos(elevacion_rad) * math.cos(angulo_rad)
cam_z = centro_z + distancia * math.sin(elevacion_rad)

cam_obj.location = (cam_x, cam_y, cam_z)

# Apuntar al centro
direccion = Vector((centro_x, centro_y, centro_z)) - cam_obj.location
cam_obj.rotation_euler = direccion.to_track_quat('-Z', 'Y').to_euler()

print("CAMARA: dist=" + str(round(distancia, 2)) + "m, pos=(" + str(round(cam_x, 1)) + ", " + str(round(cam_y, 1)) + ", " + str(round(cam_z, 1)) + ")")

# ═══════════════════════════════════════════════════════════
# 7. LUCES
# ═══════════════════════════════════════════════════════════
# Sol principal (key light)
sun_data = bpy.data.lights.new(name='SolPrincipal', type='SUN')
sun_data.energy = 3.0
sun_obj = bpy.data.objects.new('SolPrincipal', sun_data)
bpy.context.scene.collection.objects.link(sun_obj)
sun_obj.location = (centro_x + tam_x, centro_y + tam_y, centro_z + tam_z * 3)
sun_obj.rotation_euler = (math.radians(50), 0, math.radians(30))
print("OK_LUZ_SOL")

# Area de relleno
area_data = bpy.data.lights.new(name='Relleno', type='AREA')
area_data.energy = 2000.0
area_data.size = diagonal
area_obj = bpy.data.objects.new('Relleno', area_data)
bpy.context.scene.collection.objects.link(area_obj)
area_obj.location = (centro_x - tam_x, centro_y - tam_y, centro_z + tam_z)
direccion_luz = Vector((centro_x, centro_y, centro_z)) - area_obj.location
area_obj.rotation_euler = direccion_luz.to_track_quat('-Z', 'Y').to_euler()
print("OK_LUZ_AREA")

# ═══════════════════════════════════════════════════════════
# 8. FONDO DEGRADADO (world)
# ═══════════════════════════════════════════════════════════
world = bpy.data.worlds.new("MundoNitro")
bpy.context.scene.world = world
world.use_nodes = True
bg_node = world.node_tree.nodes.get("Background")
if bg_node:
    bg_node.inputs[0].default_value = (0.85, 0.88, 0.92, 1.0)
    bg_node.inputs[1].default_value = 1.2

# ═══════════════════════════════════════════════════════════
# 9. SUELO (para que no flote)
# ═══════════════════════════════════════════════════════════
bpy.ops.mesh.primitive_plane_add(size=diagonal * 4, location=(centro_x, centro_y, min_z - 0.01))
suelo = bpy.context.active_object
suelo.name = "Suelo"

mat_suelo = bpy.data.materials.new(name="MaterialSuelo")
mat_suelo.use_nodes = True
bsdf_suelo = mat_suelo.node_tree.nodes.get("Principled BSDF")
if bsdf_suelo:
    bsdf_suelo.inputs['Base Color'].default_value = (0.4, 0.42, 0.45, 1.0)
    bsdf_suelo.inputs['Roughness'].default_value = 0.9
suelo.data.materials.append(mat_suelo)
print("OK_SUELO")

# ═══════════════════════════════════════════════════════════
# 10. CONFIGURAR RENDER
# ═══════════════════════════════════════════════════════════
scene = bpy.context.scene
for m in [RENDER_ENGINE_PREF, 'BLENDER_EEVEE_NEXT', 'BLENDER_EEVEE', 'CYCLES']:
    try:
        scene.render.engine = m
        print("MOTOR: " + m)
        break
    except Exception:
        continue

scene.render.filepath = OUTPUT_PATH
scene.render.image_settings.file_format = 'PNG'
scene.render.resolution_x = RESOLUTION_X
scene.render.resolution_y = RESOLUTION_Y
scene.render.resolution_percentage = 100
scene.render.film_transparent = False

# ═══════════════════════════════════════════════════════════
# 11. RENDERIZAR
# ═══════════════════════════════════════════════════════════
try:
    bpy.ops.render.render(write_still=True)
    print("RENDER_OK: " + OUTPUT_PATH)
except Exception as e:
    print("ERROR_RENDER: " + str(e))
    exit(1)
"""


class BlenderSkill(Skill):
    name = "blender"
    description = "Renderiza modelos 3D (STEP/STL) a imagenes con Blender"

    def run(self, action, params):
        if action == "render_step":
            return self._render_step(
                params.get("step_path", ""),
                params.get("output", ""),
                params.get("res_x", 1920),
                params.get("res_y", 1080),
                params.get("engine", "BLENDER_EEVEE_NEXT"),
                params.get("cam_angulo", 45),
            )
        return f"Accion desconocida en blender: {action}"

    def _render_step(self, step_path, output_path, res_x=1920, res_y=1080, engine="BLENDER_EEVEE_NEXT", cam_angulo=45):
        if not step_path or not Path(step_path).exists():
            return {
                "thought": "Error",
                "display": f"No encuentro el archivo: {step_path}",
                "voice": "Error.",
            }

        if not output_path:
            output_path = str(SANDBOX / f"render_{uuid.uuid4().hex[:8]}.png")

        if not confirmation.require(
            "blender", "render_step",
            f"Renderizar {Path(step_path).name} con Blender ({res_x}x{res_y}, angulo {cam_angulo}°)"
        ):
            return {"thought": "Cancelado", "display": "Cancelado.", "voice": "Cancelado."}

        script = SCRIPT_RENDER_STEP.format(
            step_path=step_path.replace("\\", "\\\\"),
            output_path=output_path.replace("\\", "\\\\"),
            res_x=int(res_x),
            res_y=int(res_y),
            engine=engine,
            cam_angulo=float(cam_angulo),
        )

        stdout, stderr, err = _run_blender(script)
        if err:
            return {"thought": "Error", "display": err, "voice": "Error."}

        if "RENDER_OK" not in (stdout or ""):
            info = []
            for line in (stdout or "").splitlines():
                if any(k in line for k in ["ERROR", "OK_", "BBOX", "DIAGONAL", "CAMARA", "MOTOR"]):
                    info.append(line)
            detalle = "\n".join(info[-12:]) if info else (stdout or "")[:500]
            return {
                "thought": "Error",
                "display": f"Blender no confirmo el render.\n{detalle}",
                "voice": "Error en el render.",
            }

        return {
            "thought": "Render completado",
            "display": (
                f"Render completado.\n"
                f"  Imagen: {output_path}\n"
                f"  Resolucion: {res_x}x{res_y}\n"
                f"  Camara: {cam_angulo}°\n\n"
                f"Abre el archivo para verlo."
            ),
            "voice": "Render completado.",
        }