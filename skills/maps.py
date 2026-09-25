"""Skill de Maps: busca edificios en OpenStreetMap y genera modelos CAD."""
import json
import math
import os
import re
import subprocess
import tempfile
import uuid
from pathlib import Path

import requests

from skills.base import Skill
from core import confirmation

ROOT = Path(__file__).resolve().parent.parent
SANDBOX = ROOT / "sandbox" / "freecad"
SANDBOX.mkdir(parents=True, exist_ok=True)

TIMEOUT = 30
NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
NOMINATIM_CACHE = {}  # query -> resultado
NOMINATIM_MIN_INTERVAL = 1.1  # segundos entre llamadas
_nominatim_last_call = [0.0]  # mutable para usar dentro de funcion
OVERPASS_SERVERS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
]
USER_AGENT = "Nitro-JARVIS/1.0 (personal assistant)"

FREECAD_CMD = os.environ.get(
    "FREECAD_CMD", r"C:\Program Files\FreeCAD 1.1\bin\freecadcmd.exe"
)


# ─── HELPERS GEO ──────────────────────────────────────────────────────────

def _latlon_a_metros(punto, lat_ref, lon_ref):
    """Convierte (lat, lng) a metros usando proyeccion equirectangular local."""
    R = 6371000.0  # radio tierra en metros
    lat, lon = punto
    dlat = math.radians(lat - lat_ref)
    dlon = math.radians(lon - lon_ref)
    x = R * dlon * math.cos(math.radians(lat_ref))
    y = R * dlat
    return (x, y)


def _calcular_centro(puntos):
    if not puntos:
        return (0, 0)
    lat = sum(p[0] for p in puntos) / len(puntos)
    lon = sum(p[1] for p in puntos) / len(puntos)
    return (lat, lon)


def _run_freecad(script_code):
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
            timeout=300,
            encoding="utf-8",
            errors="replace",
        )
        return result.stdout, result.stderr, None
    except subprocess.TimeoutExpired:
        return None, None, "FreeCAD tardo mas de 300s (timeout)"
    except Exception as e:
        return None, None, f"Error freecadcmd: {e}"
    finally:
        try:
            os.unlink(script_path)
        except Exception:
            pass


# ─── NOMINATIM (buscador) ─────────────────────────────────────────────────

def _nominatim_search(query):
    """Busca un lugar con cache + rate limit para no saturar Nominatim."""
    global _nominatim_last_call

    # Cache
    if query in NOMINATIM_CACHE:
        print(f"[MAPS] Cache hit: '{query}'")
        return NOMINATIM_CACHE[query], None

    # Rate limit: esperar si hace falta
    import time
    ahora = time.time()
    delta = ahora - _nominatim_last_call[0]
    if delta < NOMINATIM_MIN_INTERVAL:
        time.sleep(NOMINATIM_MIN_INTERVAL - delta)

    try:
        r = requests.get(
            NOMINATIM_URL,
            params={
                "q": query,
                "format": "json",
                "limit": 5,
                "polygon_geojson": 1,
                "extratags": 1,
                "addressdetails": 1,
            },
            headers={"User-Agent": USER_AGENT},
            timeout=TIMEOUT,
        )
        _nominatim_last_call[0] = time.time()
        if r.status_code != 200:
            return None, f"Nominatim respondio {r.status_code}"
        data = r.json()
        NOMINATIM_CACHE[query] = data
        return data, None
    except Exception as e:
        _nominatim_last_call[0] = time.time()
        return None, f"Error consultando Nominatim: {e}"


def _extraer_poligono_de_nominatim(lugar):
    """Extrae los puntos del poligono si Nominatim los devolvio."""
    geo = lugar.get("geojson")
    if not geo:
        return None

    tipo = geo.get("type", "")
    coords = geo.get("coordinates", [])

    if tipo == "Polygon":
        # coords = [[[lon, lat], [lon, lat], ...]]
        if coords and coords[0]:
            return [(p[1], p[0]) for p in coords[0]]  # convertir a (lat, lon)
    elif tipo == "MultiPolygon":
        # coords = [[[[lon, lat], ...]]]
        if coords and coords[0] and coords[0][0]:
            return [(p[1], p[0]) for p in coords[0][0]]
    elif tipo == "Point":
        return None  # solo tenemos un punto

    return None


def _extraer_altura_de_nominatim(lugar):
    """Extrae altura con defaults inteligentes segun tipo de edificio."""
    extras = lugar.get("extratags", {}) or {}
    height = extras.get("height")
    levels = extras.get("building:levels")

    if height:
        try:
            return float(str(height).replace("m", "").strip())
        except Exception:
            pass
    if levels:
        try:
            return float(levels) * 3.0
        except Exception:
            pass

    # Defaults segun tipo de edificio (cuando OSM no tiene el dato)
    tipo = (extras.get("building") or lugar.get("type") or "").lower()
    defaults = {
        "cathedral": 35.0,
        "church": 20.0,
        "chapel": 15.0,
        "mosque": 25.0,
        "synagogue": 20.0,
        "temple": 20.0,
        "hotel": 30.0,
        "office": 25.0,
        "commercial": 15.0,
        "retail": 10.0,
        "apartments": 20.0,
        "residential": 12.0,
        "house": 6.0,
        "school": 10.0,
        "university": 15.0,
        "hospital": 20.0,
        "museum": 15.0,
        "government": 20.0,
        "civic": 15.0,
        "industrial": 10.0,
        "warehouse": 8.0,
        "garage": 4.0,
        "shed": 3.0,
    }
    # Buscar en todas las palabras del tipo
    for palabra in tipo.replace(";", " ").split():
        if palabra in defaults:
            return defaults[palabra]

    # Default razonable si no sabemos nada
    return 10.0


# ─── OVERPASS (obtener edificios) ─────────────────────────────────────────

def _overpass_building(lat, lon, radius_m=150, name_filter=None):
    """Busca la huella de un edificio cerca de las coords dadas."""
    # Query: edificios con building=* en un radio alrededor del punto
    filtro_nombre = ""
    if name_filter:
        # Escapar comillas y usar regex case-insensitive
        safe_name = name_filter.replace('"', "").strip()
        filtro_nombre = f'["name"~"{safe_name}",i]'

    query = f"""
[out:json][timeout:60];
(
  way["building"]{filtro_nombre}(around:{radius_m},{lat},{lon});
  relation["building"]{filtro_nombre}(around:{radius_m},{lat},{lon});
  way["building"]["name"](around:{radius_m},{lat},{lon});
  relation["building"]["name"](around:{radius_m},{lat},{lon});
);
out body;
>;
out skel qt;
"""
    for url in OVERPASS_SERVERS:
        try:
            r = requests.post(
                url,
                data={"data": query},
                headers={"User-Agent": USER_AGENT},
                timeout=60,
            )
            if r.status_code == 200:
                return r.json(), None
            print(f"[MAPS] {url} -> {r.status_code}, probando siguiente...")
        except Exception as e:
            print(f"[MAPS] {url} -> {e}, probando siguiente...")
            continue
    return None, "Todos los servidores Overpass fallaron (504/timeout)"


def _parsear_overpass(data):
    """Extrae edificios (con footprint + tags) del JSON de Overpass."""
    if not data or "elements" not in data:
        return []

    # Mapa de nodos: id -> (lat, lon)
    nodos = {}
    for el in data["elements"]:
        if el["type"] == "node":
            nodos[el["id"]] = (el["lat"], el["lon"])

    edificios = []
    for el in data["elements"]:
        if el["type"] not in ("way", "relation"):
            continue
        tags = el.get("tags", {})
        if "building" not in tags:
            continue

        # Obtener lista de nodos (way) o miembros (relation)
        if el["type"] == "way":
            node_ids = el.get("nodes", [])
        else:
            # Relation simple: extraer ways members
            node_ids = []
            for m in el.get("members", []):
                if m.get("type") == "way" and "ref" in m:
                    # No tenemos los nodos del way aqui, saltamos por simplicidad
                    pass
            if not node_ids:
                continue

        puntos = [nodos[nid] for nid in node_ids if nid in nodos]
        if len(puntos) < 3:
            continue

        # Cerrar el poligono si no lo esta
        if puntos[0] != puntos[-1]:
            puntos.append(puntos[0])

        edificios.append({
            "id": el.get("id"),
            "type": el["type"],
            "tags": tags,
            "footprint": puntos,
            "name": tags.get("name", ""),
            "building": tags.get("building", "yes"),
            "levels": tags.get("building:levels"),
            "height": tags.get("height"),
        })

    return edificios


def _altura_metros(edificio, altura_default=3.0):
    """Calcula la altura del edificio en metros."""
    h = edificio.get("height")
    if h:
        try:
            return float(str(h).replace("m", "").strip())
        except Exception:
            pass
    niveles = edificio.get("levels")
    if niveles:
        try:
            return float(niveles) * 3.0  # 3m por nivel promedio
        except Exception:
            pass
    return altura_default


def _altura_es_real(edificio):
    """True si la altura viene de datos reales (no de un default)."""
    return bool(edificio.get("_altura_real"))


# ─── GENERADOR DE SCRIPT FREECAD (modelo simple) ──────────────────────────

def _generar_script_freecad(edificio, output_path, formato="step", altura_override=None):
    """Genera un script de FreeCAD para el edificio (prisma simple)."""
    footprint = edificio["footprint"]
    altura = altura_override or _altura_metros(edificio)

    # Centro de referencia
    lat_ref, lon_ref = _calcular_centro(footprint)

    # Convertir a metros
    puntos_m = [_latlon_a_metros(p, lat_ref, lon_ref) for p in footprint]

    # Formatear como lista de tuplas para el script
    pts_str = ", ".join(f"({x:.3f}, {y:.3f})" for x, y in puntos_m)

    script = f"""
import FreeCAD
import Part
import os

OUT = r'{output_path}'
ALTURA = {altura}
FORMATO = '{formato}'

for ext in ('.step', '.dxf', '.FCStd'):
    p = OUT.rsplit('.', 1)[0] + ext
    if os.path.exists(p):
        os.remove(p)

doc = FreeCAD.newDocument('EdificioOSM')

# Puntos del contorno en metros (proyeccion local)
puntos = [{pts_str}]

# Crear wire del contorno
vectores = [FreeCAD.Vector(x, y, 0) for x, y in puntos]
if vectores[0].x != vectores[-1].x or vectores[0].y != vectores[-1].y:
    vectores.append(vectores[0])

# DEBUG: imprimir puntos
print('[DEBUG] Puntos del contorno (metros):')
for idx, v in enumerate(vectores):
    print('  punto ' + str(idx) + ': (' + str(round(v.x, 2)) + ', ' + str(round(v.y, 2)) + ')')

# Crear wire + face con fallback robusto
solido = None
try:
    wire = Part.makePolygon(vectores)
    print('[DEBUG] wire creado OK')
    try:
        face = Part.Face(wire)
        print('[DEBUG] face creada OK')
        solido = face.extrude(FreeCAD.Vector(0, 0, ALTURA))
        print('[DEBUG] solido extruido desde face')
    except Exception as e_face:
        print('[WARN] Face() fallo, extruyendo el wire directamente: ' + str(e_face))
        solido = wire.extrude(FreeCAD.Vector(0, 0, ALTURA))
        print('[DEBUG] solido extruido desde wire')
except Exception as e:
    print('[ERROR] Fatal: ' + str(e))
    raise

obj = doc.addObject('Part::Feature', 'Edificio')
obj.Shape = solido
obj.Label = 'Edificio_OSM'
doc.recompute()

# Guardar FCStd
fcstd_path = OUT.rsplit('.', 1)[0] + '.FCStd'
doc.saveAs(fcstd_path)
print('[OK] FCStd: ' + fcstd_path)

# Exportar al formato pedido
try:
    import Import
    import importDXF
    if FORMATO == 'step':
        Import.export([obj], OUT)
        print('[OK] STEP: ' + OUT)
    elif FORMATO == 'dxf':
        dxf_path = OUT.rsplit('.', 1)[0] + '.dxf'
        importDXF.export([obj], dxf_path)
        print('[OK] DXF: ' + dxf_path)
    else:
        Import.export([obj], OUT.rsplit('.', 1)[0] + '.step')
        print('[OK] STEP: ' + OUT.rsplit('.', 1)[0] + '.step')
except Exception as e:
    print('[WARN] Error exportando: ' + str(e))

print('[INFO] Altura: ' + str(ALTURA) + 'm')
print('[INFO] Vertices del contorno: ' + str(len(puntos)))
"""
    return script


# ─── GENERADOR DE SCRIPT FREECAD (modelo detallado) ───────────────────────

def _generar_script_building_detallado(footprint, output_path, altura_total, num_pisos, wall_thickness=0.15):
    """Genera un edificio con muros huecos + losas retraidas + ventanas optimizadas."""
    lat_ref, lon_ref = _calcular_centro(footprint)
    puntos_m = [_latlon_a_metros(p, lat_ref, lon_ref) for p in footprint]

    if puntos_m[0] != puntos_m[-1]:
        puntos_m.append(puntos_m[0])

    # Calcular area (shoelace) para saber la orientacion
    area = 0.0
    n = len(puntos_m) - 1
    for i in range(n):
        x1, y1 = puntos_m[i]
        x2, y2 = puntos_m[i + 1]
        area += x1 * y2 - x2 * y1
    signo = 1.0 if area > 0 else -1.0

    # Calcular poligono interno (offset hacia adentro)
    inner = []
    for i in range(n):
        prev = puntos_m[i - 1] if i > 0 else puntos_m[n - 1]
        curr = puntos_m[i]
        next_p = puntos_m[i + 1]

        dx1, dy1 = curr[0] - prev[0], curr[1] - prev[1]
        l1 = math.sqrt(dx1 * dx1 + dy1 * dy1) or 1.0
        nx1 = signo * (-dy1 / l1)
        ny1 = signo * (dx1 / l1)

        dx2, dy2 = next_p[0] - curr[0], next_p[1] - curr[1]
        l2 = math.sqrt(dx2 * dx2 + dy2 * dy2) or 1.0
        nx2 = signo * (-dy2 / l2)
        ny2 = signo * (dx2 / l2)

        nx, ny = (nx1 + nx2) / 2, (ny1 + ny2) / 2
        nl = math.sqrt(nx * nx + ny * ny)
        if nl > 0.001:
            nx, ny = nx / nl, ny / nl
        else:
            nx, ny = nx1, ny1

        inner.append((curr[0] + nx * wall_thickness, curr[1] + ny * wall_thickness))
    inner.append(inner[0])

    pts_outer_str = ", ".join(f"({x:.4f}, {y:.4f})" for x, y in puntos_m)
    pts_inner_str = ", ".join(f"({x:.4f}, {y:.4f})" for x, y in inner)

    altura_piso = altura_total / num_pisos

    script = f"""
import FreeCAD
import Part
import math
import os

OUT = r'{output_path}'
ALTURA_TOTAL = {altura_total}
NUM_PISOS = {num_pisos}
ALTURA_PISO = {altura_piso:.4f}
WALL_T = {wall_thickness}
SLAB_T = 0.10
ADD_WINDOWS = True
MAX_PISOS_VENTANA = 8
SEPARACION_VENT = 5.0
ANCHO_VENT = 2.0
ALTO_VENT = 1.5
ALT_PRE_VENT = 0.9

for ext in ('.step', '.FCStd'):
    p = OUT.rsplit('.', 1)[0] + ext
    if os.path.exists(p):
        os.remove(p)

doc = FreeCAD.newDocument('EdificioDetallado')

# ═══════════════════════════════════════════════════════════
# 1. FOOTPRINT (ext/int)
# ═══════════════════════════════════════════════════════════
puntos_ext = [{pts_outer_str}]
puntos_int = [{pts_inner_str}]

wire_ext = Part.makePolygon([FreeCAD.Vector(x, y, 0) for x, y in puntos_ext])
wire_int = Part.makePolygon([FreeCAD.Vector(x, y, 0) for x, y in puntos_int])
face_ext = Part.Face(wire_ext)
face_int = Part.Face(wire_int)
print('[OK] Footprint exterior: ' + str(len(puntos_ext)) + ' vertices')
print('[OK] Footprint interior: ' + str(len(puntos_int)) + ' vertices')

# ═══════════════════════════════════════════════════════════
# 2. MUROS HUECOS
# ═══════════════════════════════════════════════════════════
try:
    anillo = face_ext.cut(face_int)
    muros_solid = anillo.extrude(FreeCAD.Vector(0, 0, ALTURA_TOTAL))
    muros_obj = doc.addObject('Part::Feature', 'Muros')
    muros_obj.Shape = muros_solid
    muros_obj.Label = 'Muros_Huecos'
    print('[OK] Muros huecos extruidos a ' + str(ALTURA_TOTAL) + 'm')
except Exception as e:
    print('[ERROR] No pude hacer muros huecos: ' + str(e))
    solid = face_ext.extrude(FreeCAD.Vector(0, 0, ALTURA_TOTAL))
    muros_obj = doc.addObject('Part::Feature', 'Muros')
    muros_obj.Shape = solid
    muros_obj.Label = 'Muros_Solidos'

# ═══════════════════════════════════════════════════════════
# 3. LOSAS RETRAIDAS
# ═══════════════════════════════════════════════════════════
for i in range(NUM_PISOS + 1):
    z = i * ALTURA_PISO
    slab = Part.Face(wire_int).extrude(FreeCAD.Vector(0, 0, SLAB_T))
    slab.translate(FreeCAD.Vector(0, 0, z - SLAB_T / 2))
    slab_obj = doc.addObject('Part::Feature', 'Losa' + str(i))
    slab_obj.Shape = slab
    slab_obj.Label = 'Losa_Piso_' + str(i)
print('[OK] ' + str(NUM_PISOS + 1) + ' losas retraidas creadas')

# ═══════════════════════════════════════════════════════════
# 4. VENTANAS (optimizado: un solo compound + un solo cut)
# ═══════════════════════════════════════════════════════════
if ADD_WINDOWS:
    try:
        ventanas_shapes = []
        n_seg = len(puntos_ext) - 1

        for s in range(n_seg):
            x1, y1 = puntos_ext[s]
            x2, y2 = puntos_ext[s + 1]
            dx, dy = x2 - x1, y2 - y1
            longitud = math.sqrt(dx * dx + dy * dy)
            if longitud < 3.0:
                continue
            angulo = math.atan2(dy, dx)

            n_vent = max(1, int(longitud / SEPARACION_VENT))
            espacio = longitud / n_vent
            for v in range(n_vent):
                x_vent_centro = (v + 0.5) * espacio
                if x_vent_centro - ANCHO_VENT / 2 < 0.5:
                    continue
                if x_vent_centro + ANCHO_VENT / 2 > longitud - 0.5:
                    continue

                for piso in range(MAX_PISOS_VENTANA):
                    z_base = piso * ALTURA_PISO + ALT_PRE_VENT
                    hueco = Part.makeBox(ANCHO_VENT, WALL_T * 3, ALTO_VENT)
                    hueco.translate(FreeCAD.Vector(x_vent_centro - ANCHO_VENT / 2, -WALL_T, z_base))
                    hueco.rotate(FreeCAD.Vector(0, 0, 0), FreeCAD.Vector(0, 0, 1), math.degrees(angulo))
                    hueco.translate(FreeCAD.Vector(x1, y1, 0))
                    ventanas_shapes.append(hueco)

        if ventanas_shapes:
            print('[INFO] Total ventanas: ' + str(len(ventanas_shapes)))
            compound = Part.makeCompound(ventanas_shapes)
            print('[INFO] Compound creado, cortando...')
            muros_obj.Shape = muros_obj.Shape.cut(compound)
            print('[OK] Ventanas cortadas en muros')
        else:
            print('[INFO] Sin ventanas a cortar')
    except Exception as e:
        print('[WARN] Ventanas fallaron: ' + str(e))
else:
    print('[INFO] Ventanas desactivadas')

doc.recompute()

# ═══════════════════════════════════════════════════════════
# 5. EXPORTAR
# ═══════════════════════════════════════════════════════════
fcstd_path = OUT.rsplit('.', 1)[0] + '.FCStd'
doc.saveAs(fcstd_path)
print('[OK] FCStd: ' + fcstd_path)

try:
    import Import
    Import.export([o for o in doc.Objects if hasattr(o, 'Shape') and o.Shape], OUT)
    print('[OK] STEP: ' + OUT)
except Exception as e:
    print('[WARN] STEP fallo: ' + str(e))

print('[INFO] Objetos: ' + str(len(doc.Objects)))
print('[INFO] Altura: ' + str(ALTURA_TOTAL) + 'm en ' + str(NUM_PISOS) + ' pisos')
"""
    return script


# ─── SKILL ────────────────────────────────────────────────────────────────

class MapsSkill(Skill):
    name = "maps"
    description = "Busca edificios en OpenStreetMap y genera modelos CAD"

    def run(self, action, params):
        if action == "search":
            return self._search(params.get("query", ""))
        if action == "get_building":
            return self._get_building_info(params.get("query", ""))
        if action == "create_model":
            altura_override = params.get("altura")
            if altura_override:
                try:
                    altura_override = float(altura_override)
                except Exception:
                    altura_override = None
            return self._create_model(
                params.get("query", ""),
                params.get("output", ""),
                params.get("formato", "step"),
                altura_override,
            )
        if action == "create_detailed":
            return self._create_detailed(params)
        return f"Accion desconocida en maps: {action}"

    def _create_detailed(self, params):
        """Genera un edificio con muros reales + losas por piso + ventanas."""
        query = (params.get("query") or "").strip()
        if not query:
            return {"thought": "", "display": "Dime el edificio.", "voice": "Falta el nombre."}

        altura_override = params.get("altura")
        num_pisos = params.get("num_pisos")
        wall_t = float(params.get("wall_thickness", 0.15))

        # Buscar en Nominatim
        data, err = _nominatim_search(query)
        if err or not data:
            return {"thought": "Error", "display": err or "No encontrado.", "voice": "No lo encontre."}

        lugar_con_poly = None
        for lugar in data:
            if _extraer_poligono_de_nominatim(lugar):
                lugar_con_poly = lugar
                break

        if not lugar_con_poly:
            return {
                "thought": "",
                "display": f"No encontre el contorno exacto de '{query}' en OpenStreetMap.",
                "voice": "Sin contorno.",
            }

        footprint = _extraer_poligono_de_nominatim(lugar_con_poly)
        nombre = lugar_con_poly.get("display_name", query).split(",")[0]
        extras = lugar_con_poly.get("extratags", {}) or {}

        # Altura
        if altura_override:
            try:
                altura = float(altura_override)
            except Exception:
                altura = _extraer_altura_de_nominatim(lugar_con_poly)
        else:
            altura = _extraer_altura_de_nominatim(lugar_con_poly)

        # Num pisos
        if num_pisos:
            try:
                num_pisos = int(num_pisos)
            except Exception:
                num_pisos = max(1, int(altura / 3.0))
        else:
            levels = extras.get("building:levels")
            if levels:
                try:
                    num_pisos = int(levels)
                except Exception:
                    num_pisos = max(1, int(altura / 3.0))
            else:
                num_pisos = max(1, int(altura / 3.0))

        # Output
        slug = re.sub(r"[^a-z0-9]+", "_", query.lower())[:30]
        output = str(SANDBOX / f"detallado_{slug}_{uuid.uuid4().hex[:6]}.step")

        if not confirmation.require(
            "maps", "create_detailed",
            f"Generar modelo detallado de '{nombre}' ({altura:.0f}m, {num_pisos} pisos, muros {wall_t*100:.0f}cm)"
        ):
            return {"thought": "Cancelado", "display": "Cancelado.", "voice": "Cancelado."}

        # Generar script + ejecutar
        script = _generar_script_building_detallado(footprint, output, altura, num_pisos, wall_t)
        stdout, stderr, err = _run_freecad(script)

        if err:
            return {"thought": "Error", "display": err, "voice": "Error."}

        if "[OK] STEP" not in (stdout or ""):
            return {
                "thought": "Error",
                "display": f"Error generando.\nSTDOUT:\n{(stdout or '')[:600]}\nSTDERR:\n{(stderr or '')[:300]}",
                "voice": "Error generando.",
            }

        return {
            "thought": f"Modelo detallado creado: {output}",
            "display": (
                f"Edificio detallado generado.\n"
                f"  Edificio: {nombre}\n"
                f"  Altura: {altura:.1f}m\n"
                f"  Pisos: {num_pisos}\n"
                f"  Grosor de muro: {wall_t*100:.0f}cm\n"
                f"  Vertices del footprint: {len(footprint)}\n"
                f"  Archivo: {output}\n\n"
                f"Componentes:\n"
                f"  - Muros huecos con grosor real\n"
                f"  - {num_pisos + 1} losas de piso\n"
                f"  - Ventanas en las fachadas\n\n"
                f"Abrelo en AutoCAD, FreeCAD, Fusion 360 o Blender."
            ),
            "voice": f"Edificio detallado de {nombre} creado con {num_pisos} pisos.",
        }

    def _search(self, query):
        query = (query or "").strip()
        if not query:
            return {"thought": "", "display": "Dime que buscar.", "voice": "Dime que buscar."}

        data, err = _nominatim_search(query)
        if err:
            return {"thought": "Error", "display": err, "voice": "Error buscando."}
        if not data:
            return {"thought": "", "display": f"No encontre '{query}'.", "voice": "No encontre nada."}

        lineas = [f"Resultados para '{query}':"]
        for i, r in enumerate(data, 1):
            lineas.append(f"  {i}. {r.get('display_name', '?')}")
            lineas.append(f"     lat: {r.get('lat')}, lng: {r.get('lon')}")
        return {
            "thought": f"{len(data)} resultados",
            "display": "\n".join(lineas),
            "voice": f"Encontre {len(data)} resultados.",
        }

    def _get_building_info(self, query):
        query = (query or "").strip()
        if not query:
            return {"thought": "", "display": "Dime el nombre del edificio.", "voice": "Falta el nombre."}

        # 1. Nominatim
        data, err = _nominatim_search(query)
        if err or not data:
            return {"thought": "Error", "display": err or "No encontrado.", "voice": "No lo encontre."}

        # 2. Preferir el resultado con poligono
        lugar_con_poly = None
        for lugar in data:
            if _extraer_poligono_de_nominatim(lugar):
                lugar_con_poly = lugar
                break

        if lugar_con_poly:
            poligono = _extraer_poligono_de_nominatim(lugar_con_poly)
            altura = _extraer_altura_de_nominatim(lugar_con_poly)
            nombre = lugar_con_poly.get("display_name", query).split(",")[0]
            extras = lugar_con_poly.get("extratags", {}) or {}

            return {
                "thought": f"Poligono exacto encontrado: {nombre}",
                "display": (
                    f"Edificio: {nombre}\n"
                    f"  Coords: {lugar_con_poly['lat']}, {lugar_con_poly['lon']}\n"
                    f"  Niveles: {extras.get('building:levels', '?')}\n"
                    f"  Altura aprox: {altura:.1f}m\n"
                    f"  Vertices del contorno: {len(poligono)}\n"
                    f"  Fuente: Nominatim polygon_geojson"
                ),
                "voice": f"Encontre {nombre} con {len(poligono)} vertices y {altura:.0f} metros de altura.",
            }

        # 3. Fallback: usar Overpass
        lugar = data[0]
        lat = float(lugar["lat"])
        lon = float(lugar["lon"])

        keyword = query.split()[0] if query else ""
        osm_data, err = _overpass_building(lat, lon, radius_m=150, name_filter=keyword)
        if err:
            return {"thought": "Error", "display": err, "voice": "Error consultando OSM."}

        edificios = _parsear_overpass(osm_data)
        if not edificios:
            return {
                "thought": "",
                "display": f"No encontre el contorno cerca de '{query}'.\nCoords: {lat}, {lon}",
                "voice": "No encontre contorno.",
            }

        def score(e):
            s = 0
            if e.get("name") and query.lower()[:6] in e["name"].lower():
                s += 100
            if e.get("name"):
                s += 20
            s += min(len(e.get("footprint", [])), 50)
            if e.get("levels"):
                s += 10
            if e.get("height"):
                s += 10
            return s

        elegido = sorted(edificios, key=score, reverse=True)[0]
        altura = _altura_metros(elegido)

        return {
            "thought": f"Encontre {elegido.get('name') or '(sin nombre)'}",
            "display": (
                f"Edificio: {elegido.get('name') or '(sin nombre)'}\n"
                f"  Coords: {lat:.4f}, {lon:.4f}\n"
                f"  Niveles: {elegido.get('levels', '?')}\n"
                f"  Altura aprox: {altura:.1f}m\n"
                f"  Vertices del contorno: {len(elegido['footprint'])}\n"
                f"  Fuente: Overpass (fallback)"
            ),
            "voice": f"Encontre {elegido.get('name') or 'un edificio'}, altura {altura:.0f} metros.",
        }

    def _create_model(self, query, output, formato, altura_override=None):
        query = (query or "").strip()
        if not query:
            return {"thought": "", "display": "Dime que edificio modelar.", "voice": "Falta el nombre."}

        formato = (formato or "step").lower()
        if formato not in ("step", "dxf"):
            formato = "step"

        # 1. Nominatim
        data, err = _nominatim_search(query)
        if err or not data:
            return {"thought": "Error", "display": err or "No encontrado.", "voice": "No lo encontre."}

        # 2. Preferir poligono de Nominatim
        lugar_con_poly = None
        for lugar in data:
            if _extraer_poligono_de_nominatim(lugar):
                lugar_con_poly = lugar
                break

        if lugar_con_poly:
            footprint = _extraer_poligono_de_nominatim(lugar_con_poly)
            extras = lugar_con_poly.get("extratags", {}) or {}
            altura_real = bool(extras.get("height") or extras.get("building:levels"))
            if altura_override:
                altura = altura_override
                altura_real = False
            else:
                altura = _extraer_altura_de_nominatim(lugar_con_poly)
            nombre = lugar_con_poly.get("display_name", query).split(",")[0]
            edificio = {
                "footprint": footprint,
                "name": nombre,
                "height": str(altura),
                "levels": extras.get("building:levels"),
                "_altura_real": altura_real,
            }
        else:
            lugar = data[0]
            lat = float(lugar["lat"])
            lon = float(lugar["lon"])
            keyword = query.split()[0].lower() if query else ""
            osm_data, err = _overpass_building(lat, lon, radius_m=200, name_filter=keyword)

            edificio_valido = None
            if not err:
                edificios = _parsear_overpass(osm_data)
                for e in edificios:
                    enombre = (e.get("name") or "").lower()
                    if keyword and keyword in enombre:
                        if edificio_valido is None:
                            edificio_valido = e
                        elif len(e.get("footprint", [])) > len(edificio_valido.get("footprint", [])):
                            edificio_valido = e

            if not edificio_valido:
                return {
                    "thought": "Sin poligono exacto",
                    "display": (
                        f"No encontre el contorno exacto de '{query}'.\n\n"
                        f"Posibles causas:\n"
                        f"  - El edificio no tiene poligono en OpenStreetMap\n"
                        f"  - Overpass esta saturado (504/timeout)\n"
                        f"  - El nombre no coincide con el registrado en OSM\n\n"
                        f"Sugerencias:\n"
                        f"  - Prueba con el nombre oficial completo\n"
                        f"  - Intenta de nuevo en unos minutos (Overpass se satura)\n"
                        f"  - Busca por direccion: 'Av. X 123, Ciudad'"
                    ),
                    "voice": f"No encontre el contorno de {query}.",
                }

            edificio = edificio_valido
            altura_real = bool(edificio.get("height") or edificio.get("levels"))
            if altura_override:
                altura = altura_override
                altura_real = False
            else:
                altura = _altura_metros(edificio)
            edificio["_altura_real"] = altura_real

        # 3. Output path
        if not output:
            slug = re.sub(r"[^a-z0-9]+", "_", query.lower())[:30]
            ext = "step" if formato == "step" else "dxf"
            output = str(SANDBOX / f"edificio_{slug}_{uuid.uuid4().hex[:6]}.{ext}")

        # 4. Confirmacion
        if not confirmation.require(
            "maps", "create_model",
            f"Generar modelo 3D de '{edificio.get('name') or query}' ({altura:.0f}m) como {formato.upper()}"
        ):
            return {"thought": "Cancelado", "display": "Cancelado.", "voice": "Cancelado."}

        # 5. FreeCAD
        script = _generar_script_freecad(edificio, output, formato)
        stdout, stderr, err = _run_freecad(script)

        if err:
            return {"thought": "Error", "display": err, "voice": "Error generando modelo."}

        if "[OK]" not in (stdout or ""):
            return {
                "thought": "Error",
                "display": f"Error generando modelo.\nSTDOUT: {(stdout or '')[:400]}\nSTDERR: {(stderr or '')[:200]}",
                "voice": "Error generando.",
            }

        fuente_altura = "real (OSM)" if _altura_es_real(edificio) else "estimada"
        return {
            "thought": f"Modelo creado: {output}",
            "display": (
                f"Modelo generado.\n"
                f"  Edificio: {edificio.get('name') or query}\n"
                f"  Altura: {altura:.1f}m ({fuente_altura})\n"
                f"  Vertices: {len(edificio['footprint'])}\n"
                f"  Archivo: {output}\n\n"
                f"Abrelo en AutoCAD, FreeCAD, Fusion 360 o Blender."
            ),
            "voice": f"Modelo de {edificio.get('name') or query} creado.",
        }