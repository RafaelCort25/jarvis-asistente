"""Skill de DWG/DXF: lee, convierte y analiza planos CAD."""
import os
import re
import shutil
import subprocess
import tempfile
import uuid
from pathlib import Path

import ezdxf

from skills.base import Skill
from core import confirmation

ROOT = Path(__file__).resolve().parent.parent
SANDBOX = ROOT / "sandbox" / "dwg"
SANDBOX.mkdir(parents=True, exist_ok=True)

ODA_CMD = os.environ.get(
    "ODA_CMD",
    r"C:\Program Files\ODA\ODAFileConverter 27.1.0\ODAFileConverter.exe"
)
FREECAD_CMD = os.environ.get(
    "FREECAD_CMD", r"C:\Program Files\FreeCAD 1.1\bin\freecadcmd.exe"
)
TIMEOUT_ODA = 120


def _limpiar_texto(texto):
    if not texto:
        return ""
    s = str(texto)
    s = re.sub(r'\\[A-Za-z]+\d*(?:\.\d+)?[xX]?;', '', s)
    s = re.sub(r'\\[A-Za-z]+[^;]*;', '', s)
    s = s.replace('{', '').replace('}', '')
    s = s.replace('\\P', ' ').replace('\\p', ' ')
    s = re.sub(r'\s+', ' ', s).strip()
    return s


def _convertir_con_oda(input_path, output_format="DXF"):
    input_path = Path(input_path)
    if not input_path.exists():
        return None, f"No existe el archivo: {input_path}"
    if not Path(ODA_CMD).exists():
        return None, f"No encuentro ODA File Converter en: {ODA_CMD}"

    output_format = output_format.upper()
    if output_format not in ("DXF", "DWG"):
        return None, f"Formato no soportado: {output_format}"

    ext_input = input_path.suffix.lower().lstrip(".")
    if ext_input not in ("dwg", "dxf"):
        return None, f"Extension no soportada: .{ext_input}"

    with tempfile.TemporaryDirectory() as tmp_in, tempfile.TemporaryDirectory() as tmp_out:
        shutil.copy(input_path, Path(tmp_in) / input_path.name)
        try:
            result = subprocess.run(
                [ODA_CMD, tmp_in, tmp_out, "ACAD2018", output_format, "0", "1", f"*.{ext_input}"],
                capture_output=True, text=True, timeout=TIMEOUT_ODA,
                encoding="utf-8", errors="replace",
            )
        except subprocess.TimeoutExpired:
            return None, "ODA tardo mas de 120s"
        except Exception as e:
            return None, f"Error ejecutando ODA: {e}"

        ext_salida = output_format.lower()
        output_name = input_path.stem + "." + ext_salida
        produced = Path(tmp_out) / output_name
        if not produced.exists():
            archivos = list(Path(tmp_out).glob(f"*.{ext_salida}"))
            if not archivos:
                return None, f"ODA no genero archivo. stdout: {(result.stdout or '')[:300]}"
            produced = archivos[0]

        final_path = SANDBOX / f"{input_path.stem}_{uuid.uuid4().hex[:6]}.{ext_salida}"
        shutil.copy(produced, final_path)
        return str(final_path), None


def _abrir_dxf(path):
    path = Path(path)
    if not path.exists():
        return None, f"No existe: {path}"
    ext = path.suffix.lower()
    if ext == ".dwg":
        dxf, err = _convertir_con_oda(path, "DXF")
        if err:
            return None, err
        path = Path(dxf)
    elif ext != ".dxf":
        return None, f"Extension no soportada: {ext}"
    try:
        doc = ezdxf.readfile(str(path))
        return doc, None
    except Exception as e:
        return None, f"Error leyendo DXF: {e}"


def _bounding_box(msp):
    min_x = min_y = float('inf')
    max_x = max_y = float('-inf')
    for entidad in msp:
        try:
            tipo = entidad.dxftype()
            if tipo == 'LINE':
                min_x = min(min_x, entidad.dxf.start.x, entidad.dxf.end.x)
                min_y = min(min_y, entidad.dxf.start.y, entidad.dxf.end.y)
                max_x = max(max_x, entidad.dxf.start.x, entidad.dxf.end.x)
                max_y = max(max_y, entidad.dxf.start.y, entidad.dxf.end.y)
            elif tipo == 'LWPOLYLINE':
                for punto in entidad.get_points('xy'):
                    min_x = min(min_x, punto[0]); min_y = min(min_y, punto[1])
                    max_x = max(max_x, punto[0]); max_y = max(max_y, punto[1])
            elif tipo in ('CIRCLE', 'ARC'):
                c = entidad.dxf.center; r = entidad.dxf.radius
                min_x = min(min_x, c.x - r); min_y = min(min_y, c.y - r)
                max_x = max(max_x, c.x + r); max_y = max(max_y, c.y + r)
            elif tipo == 'INSERT':
                p = entidad.dxf.insert
                min_x = min(min_x, p.x); min_y = min(min_y, p.y)
                max_x = max(max_x, p.x); max_y = max(max_y, p.y)
        except Exception:
            continue
    if min_x == float('inf'):
        return None
    return (min_x, min_y, max_x, max_y)


class DwgSkill(Skill):
    name = "dwg"
    description = "Lee, convierte y analiza planos DWG/DXF"

    def run(self, action, params):
        if action == "convert_to_dxf":
            return self._convert(params.get("path", ""), "DXF")
        if action == "convert_to_dwg":
            return self._convert(params.get("path", ""), "DWG")
        if action == "analyze":
            return self._analyze(params.get("path", ""))
        if action == "list_layers":
            return self._list_layers(params.get("path", ""))
        if action == "list_texts":
            return self._list_texts(params.get("path", ""))
        if action == "list_blocks":
            return self._list_blocks(params.get("path", ""))
        if action == "info":
            return self._info(params.get("path", ""))
        if action == "extract_layer":
            return self.extract_layer(params.get("path", ""), params.get("layer_name", ""), params.get("output", ""))
        if action == "list_rooms":
            return self.list_rooms(params.get("path", ""))
        if action == "annotate":
            return self.annotate(params.get("path", ""), params.get("output", ""), float(params.get("offset", 0.5)))
        if action == "extract_walls_3d":
            return self.extract_walls_3d(params.get("path", ""), params.get("output", ""), float(params.get("height", 3.0)))
        if action == "extract_all_layers_3d":
            return self.extract_all_layers_3d(params.get("path", ""), params.get("output", ""))
        return f"Accion desconocida en dwg: {action}"

    def _convert(self, path, output_format):
        if not path:
            return {"thought": "", "display": "Falta la ruta del archivo.", "voice": "Falta la ruta."}
        path = Path(path)
        if not confirmation.require("dwg", "convert", f"Convertir {path.name} a {output_format}"):
            return {"thought": "Cancelado", "display": "Cancelado.", "voice": "Cancelado."}
        result, err = _convertir_con_oda(path, output_format)
        if err:
            return {"thought": "Error", "display": err, "voice": "Error convirtiendo."}
        return {"thought": f"Convertido a {output_format}", "display": f"Archivo convertido a {output_format}.\n  Ruta: {result}", "voice": f"Convertido a {output_format}."}

    def _analyze(self, path):
        if not path:
            return {"thought": "", "display": "Falta la ruta.", "voice": "Falta la ruta."}
        doc, err = _abrir_dxf(path)
        if err:
            return {"thought": "Error", "display": err, "voice": "Error."}
        msp = doc.modelspace()
        n_lineas = len(list(msp.query('LINE')))
        n_polilineas = len(list(msp.query('LWPOLYLINE')))
        n_textos = len(list(msp.query('TEXT MTEXT')))
        n_bloques = len(list(msp.query('INSERT')))
        n_arcos = len(list(msp.query('ARC CIRCLE')))
        bbox = _bounding_box(msp)
        dims = f"{bbox[2]-bbox[0]:.1f} x {bbox[3]-bbox[1]:.1f}" if bbox else "?"
        lineas = [
            f"Analisis de: {Path(path).name}",
            f"  Dimensiones: {dims} (unidades DXF)",
            f"  Lineas: {n_lineas}",
            f"  Polilineas: {n_polilineas}",
            f"  Arcos/circulos: {n_arcos}",
            f"  Bloques (INSERT): {n_bloques}",
            f"  Textos: {n_textos}",
            f"  Capas: {len(doc.layers)}",
        ]
        return {"thought": "Plano analizado", "display": "\n".join(lineas), "voice": f"Plano con {n_lineas} lineas y {n_bloques} bloques."}

    def _list_layers(self, path):
        if not path:
            return {"thought": "", "display": "Falta la ruta.", "voice": "Falta la ruta."}
        doc, err = _abrir_dxf(path)
        if err:
            return {"thought": "Error", "display": err, "voice": "Error."}
        capas = sorted([layer.dxf.name for layer in doc.layers])
        lineas = [f"Capas ({len(capas)}):"]
        for c in capas:
            lineas.append(f"  - {c}")
        return {"thought": f"{len(capas)} capas", "display": "\n".join(lineas), "voice": f"{len(capas)} capas."}

    def _list_texts(self, path):
        if not path:
            return {"thought": "", "display": "Falta la ruta.", "voice": "Falta la ruta."}
        doc, err = _abrir_dxf(path)
        if err:
            return {"thought": "Error", "display": err, "voice": "Error."}
        msp = doc.modelspace()
        textos = []
        for t in msp.query('TEXT MTEXT'):
            try:
                raw = t.text if t.dxftype() == 'MTEXT' else t.dxf.text
                limpio = _limpiar_texto(raw)
                if limpio and len(limpio) > 1:
                    textos.append(limpio)
            except Exception:
                continue
        if not textos:
            return {"thought": "", "display": "No hay textos.", "voice": "Sin textos."}
        lineas = [f"Textos ({len(textos)}):"]
        for t in textos[:50]:
            lineas.append(f"  - {t}")
        return {"thought": f"{len(textos)} textos", "display": "\n".join(lineas), "voice": f"{len(textos)} textos."}

    def _list_blocks(self, path):
        if not path:
            return {"thought": "", "display": "Falta la ruta.", "voice": "Falta la ruta."}
        doc, err = _abrir_dxf(path)
        if err:
            return {"thought": "Error", "display": err, "voice": "Error."}
        msp = doc.modelspace()
        conteo = {}
        for insert in msp.query('INSERT'):
            try:
                nombre = insert.dxf.name
                conteo[nombre] = conteo.get(nombre, 0) + 1
            except Exception:
                continue
        if not conteo:
            return {"thought": "", "display": "No hay bloques.", "voice": "Sin bloques."}
        ordenado = sorted(conteo.items(), key=lambda x: -x[1])
        lineas = [f"Bloques ({len(conteo)} tipos, {sum(conteo.values())} instancias):"]
        for nombre, n in ordenado[:40]:
            lineas.append(f"  [{n:4d}] {nombre}")
        return {"thought": f"{len(conteo)} tipos", "display": "\n".join(lineas), "voice": f"{len(conteo)} tipos."}

    def _info(self, path):
        if not path:
            return {"thought": "", "display": "Falta la ruta.", "voice": "Falta la ruta."}
        doc, err = _abrir_dxf(path)
        if err:
            return {"thought": "Error", "display": err, "voice": "Error."}
        msp = doc.modelspace()
        bbox = _bounding_box(msp)
        if bbox:
            dims_str = f"  Bounding box: ({bbox[0]:.2f}, {bbox[1]:.2f}) -> ({bbox[2]:.2f}, {bbox[3]:.2f})\n  Tamano: {bbox[2]-bbox[0]:.2f} x {bbox[3]-bbox[1]:.2f}"
        else:
            dims_str = "  Bounding box: no calculable"
        return {"thought": "Info", "display": f"Informacion de: {Path(path).name}\n{dims_str}", "voice": "Info."}

    def extract_layer(self, path, layer_name, output=""):
        if not path or not layer_name:
            return {"thought": "", "display": "Faltan datos.", "voice": "Faltan datos."}
        doc, err = _abrir_dxf(path)
        if err:
            return {"thought": "Error", "display": err, "voice": "Error."}
        msp = doc.modelspace()
        nuevas = ezdxf.new("R2018", setup=True)
        nuevo_msp = nuevas.modelspace()
        if layer_name in doc.layers:
            try:
                origen = doc.layers.get(layer_name)
                nuevas.layers.add(name=layer_name, color=origen.color if hasattr(origen, 'color') else 7)
            except Exception:
                pass
        count = 0
        for entidad in msp:
            try:
                if entidad.dxf.layer != layer_name:
                    continue
                nuevo_msp.add_foreign_entity(entidad, copy=True)
                count += 1
            except Exception as e:
                print(f"[DWG] Error copiando: {e}")
                continue
        if count == 0:
            return {"thought": "Sin entidades", "display": f"No hay entidades en '{layer_name}'.", "voice": "Capa vacia."}
        if not output:
            slug = re.sub(r"[^a-z0-9]+", "_", layer_name.lower())[:20]
            output = str(SANDBOX / f"{Path(path).stem}_{slug}_{uuid.uuid4().hex[:6]}.dxf")
        nuevas.saveas(output)
        return {"thought": f"{count} entidades", "display": f"Capa extraida.\n  Capa: {layer_name}\n  Entidades: {count}\n  Guardado en: {output}", "voice": f"Capa {layer_name} extraida."}

    def list_rooms(self, path):
        if not path:
            return {"thought": "", "display": "Falta la ruta.", "voice": "Falta la ruta."}
        doc, err = _abrir_dxf(path)
        if err:
            return {"thought": "Error", "display": err, "voice": "Error."}
        msp = doc.modelspace()
        ambientes = []
        niveles = []
        for t in msp.query('TEXT MTEXT'):
            try:
                raw = t.text if t.dxftype() == 'MTEXT' else t.dxf.text
                texto = _limpiar_texto(raw)
                if not texto or len(texto) < 2:
                    continue
                up = texto.upper()
                if 'N.P.T' in up or 'NPT' in up:
                    niveles.append(texto)
                    continue
                palabras = ['AULA', 'SS.HH', 'SSHH', 'BANO', 'BAÑO', 'COCINA', 'SALA', 'DORMITORIO', 'COMEDOR', 'PATIO', 'INGRESO', 'PASILLO', 'ZONA', 'MODULO', 'MÓDULO', 'HALL', 'RECEPCION', 'RECEPCIÓN', 'OFICINA', 'ALMACEN', 'ALMACÉN', 'GRUTA', 'JARDIN', 'JARDÍN', 'DEPOSITO', 'DEPÓSITO', 'CUARTO', 'ESCALERA', 'TERRAZA']
                if any(p in up for p in palabras):
                    ambientes.append(texto)
            except Exception:
                continue
        if not ambientes and not niveles:
            return {"thought": "", "display": "No detecte ambientes.", "voice": "Sin ambientes."}
        lineas = ["Ambientes detectados:"]
        for a in ambientes:
            lineas.append(f"  - {a}")
        if niveles:
            lineas.append("")
            lineas.append("Niveles (N.P.T.):")
            for n in niveles:
                lineas.append(f"  - {n}")
        return {"thought": f"{len(ambientes)} ambientes", "display": "\n".join(lineas), "voice": f"{len(ambientes)} ambientes."}

    def annotate(self, path, output="", offset=0.5):
        if not path:
            return {"thought": "", "display": "Falta la ruta.", "voice": "Falta la ruta."}
        doc, err = _abrir_dxf(path)
        if err:
            return {"thought": "Error", "display": err, "voice": "Error."}
        msp = doc.modelspace()
        if "Nitro_Cotas" not in doc.layers:
            doc.layers.add(name="Nitro_Cotas", color=2)
        candidatas_h = []
        candidatas_v = []
        for linea in msp.query('LINE'):
            try:
                p1 = linea.dxf.start
                p2 = linea.dxf.end
                if abs(p1.y - p2.y) < 0.01:
                    largo = abs(p2.x - p1.x)
                    if largo > 2.0:
                        candidatas_h.append((min(p1.x, p2.x), max(p1.x, p2.x), p1.y, largo))
                elif abs(p1.x - p2.x) < 0.01:
                    largo = abs(p2.y - p1.y)
                    if largo > 2.0:
                        candidatas_v.append((min(p1.y, p2.y), max(p1.y, p2.y), p1.x, largo))
            except Exception:
                continue
        candidatas_h.sort(key=lambda x: -x[3])
        candidatas_v.sort(key=lambda x: -x[3])
        def filtrar_unicas(cands):
            unicas = []
            for c in cands:
                dup = False
                for u in unicas:
                    if abs(c[2] - u[2]) < 1.0 and abs(c[3] - u[3]) < 5.0:
                        dup = True
                        break
                if not dup:
                    unicas.append(c)
                if len(unicas) >= 30:
                    break
            return unicas
        h_final = filtrar_unicas(candidatas_h)
        v_final = filtrar_unicas(candidatas_v)
        n_dims = 0
        for x1, x2, y, largo in h_final:
            try:
                dim = msp.add_linear_dim(base=(x1, y + offset), p1=(x1, y), p2=(x2, y))
                dim.dimension.dxf.layer = "Nitro_Cotas"
                dim.render()
                n_dims += 1
            except Exception as e:
                print(f"[DWG] Error dim h: {e}")
        for y1, y2, x, largo in v_final:
            try:
                dim = msp.add_linear_dim(base=(x + offset, y1), p1=(x, y1), p2=(x, y2), angle=90)
                dim.dimension.dxf.layer = "Nitro_Cotas"
                dim.render()
                n_dims += 1
            except Exception as e:
                print(f"[DWG] Error dim v: {e}")
        if not output:
            output = str(SANDBOX / f"{Path(path).stem}_acotado_{uuid.uuid4().hex[:6]}.dxf")
        doc.saveas(output)
        return {"thought": f"{n_dims} cotas", "display": f"Acotado completado.\n  Cotas anadidas: {n_dims}\n  Guardado en: {output}", "voice": f"{n_dims} cotas."}

    def extract_walls_3d(self, path, output="", height=3.0):
        """Extrae solo la capa MUROS y genera un STEP 3D."""
        if not path:
            return {"thought": "", "display": "Falta la ruta.", "voice": "Falta la ruta."}
        doc, err = _abrir_dxf(path)
        if err:
            return {"thought": "Error", "display": err, "voice": "Error."}
        msp = doc.modelspace()
        capas_muro = [l.dxf.name for l in doc.layers if 'muro' in l.dxf.name.lower()]
        if not capas_muro:
            return {"thought": "Sin capa MUROS", "display": "No encontre capas con 'muro'.", "voice": "Sin muros."}
        segmentos = self._extraer_segmentos(msp, capas_muro, min_largo=0.3)
        if not segmentos:
            return {"thought": "Sin segmentos", "display": "Capas sin segmentos validos.", "voice": "Sin segmentos."}
        output_final = output or str(SANDBOX / f"{Path(path).stem}_muros_3d_{uuid.uuid4().hex[:6]}.step")
        ok, err2 = self._exportar_step(segmentos, output_final, height, 0.4, "Muro")
        if not ok:
            return {"thought": "Error", "display": err2, "voice": "Error."}
        return {"thought": f"{len(segmentos)} segmentos a 3D", "display": f"Muros extraidos a 3D.\n  Capas: {', '.join(capas_muro)}\n  Segmentos: {len(segmentos)}\n  Altura: {height}m\n  STEP: {output_final}", "voice": f"Muros 3D con {len(segmentos)} segmentos."}

    def extract_all_layers_3d(self, path, output=""):
        """Extrae TODAS las capas con alturas proporcionales. Fase 1 del pipeline profesional."""
        if not path:
            return {"thought": "", "display": "Falta la ruta.", "voice": "Falta la ruta."}
        doc, err = _abrir_dxf(path)
        if err:
            return {"thought": "Error", "display": err, "voice": "Error."}
        msp = doc.modelspace()

        # Mapa de alturas por palabra clave en nombre de capa
        altura_por_capa = {
            "muro": 3.0,
            "mueble": 0.75,
            "mobiliario": 0.75,
            "piso": 0.05,
            "escalera": 1.5,
            "arbol": 2.5,
            "vegetaci": 1.0,
            "planta": 1.2,
            "nivel": 0.1,
            "cota": 0.02,
            "eje": 0.02,
            "text": 0.05,
            "tx": 0.05,
            "corte": 0.1,
            "proyec": 0.1,
            "paisaj": 0.8,
        }

        def altura_de_capa(nombre_capa):
            n = nombre_capa.lower()
            for palabra, h in altura_por_capa.items():
                if palabra in n:
                    return h
            return 0.3

        # Recopilar entidades por capa
        entidades_por_capa = {}
        for entidad in msp:
            try:
                capa = entidad.dxf.layer
                entidades_por_capa.setdefault(capa, []).append(entidad)
            except Exception:
                continue

        # Extraer segmentos por capa
        capas_data = {}
        total_segmentos = 0
        for capa, entidades in entidades_por_capa.items():
            segmentos = []
            for entidad in entidades:
                try:
                    tipo = entidad.dxftype()
                    if tipo == 'LINE':
                        p1 = entidad.dxf.start
                        p2 = entidad.dxf.end
                        largo = ((p2.x - p1.x) ** 2 + (p2.y - p1.y) ** 2) ** 0.5
                        if largo > 0.2:
                            segmentos.append((p1.x, p1.y, p2.x, p2.y))
                    elif tipo == 'LWPOLYLINE':
                        puntos = list(entidad.get_points('xy'))
                        for i in range(len(puntos) - 1):
                            x1, y1 = puntos[i]
                            x2, y2 = puntos[i + 1]
                            largo = ((x2 - x1) ** 2 + (y2 - y1) ** 2) ** 0.5
                            if largo > 1.0:
                                segmentos.append((x1, y1, x2, y2))
                    elif tipo == 'CIRCLE':
                        c = entidad.dxf.center
                        r = entidad.dxf.radius
                        if r > 0.1:
                            segmentos.append((c.x - r, c.y - r, c.x + r, c.y + r))
                except Exception:
                    continue
            if segmentos:
                capas_data[capa] = {
                    "altura": altura_de_capa(capa),
                    "segmentos": segmentos,
                    "count": len(segmentos),
                }
                total_segmentos += len(segmentos)

        if not capas_data:
            return {"thought": "Sin datos", "display": "No hay geometria extraible.", "voice": "Sin datos."}

        output_final = output or str(SANDBOX / f"{Path(path).stem}_completo_3d_{uuid.uuid4().hex[:6]}.step")
        out_esc = output_final.replace("\\", "/")

        # Generar script FreeCAD como lista de lineas
        lineas_script = [
            "import FreeCAD",
            "import Part",
            "import math",
            "",
            f"OUT = r'{out_esc}'",
            "doc = FreeCAD.newDocument('PlanoCompleto3D')",
            "",
        ]

        for capa, datos in capas_data.items():
            capa_safe = re.sub(r'[^a-zA-Z0-9_]', '_', capa)
            lineas_script.append(f"# Capa: {capa} (altura {datos['altura']}m, {datos['count']} segmentos)")
            lineas_script.append(f"capa_segs_{capa_safe} = [")
            for x1, y1, x2, y2 in datos["segmentos"]:
                lineas_script.append(f"    ({x1:.3f}, {y1:.3f}, {x2:.3f}, {y2:.3f}),")
            lineas_script.append("]")
            lineas_script.append(f"capa_altura_{capa_safe} = {datos['altura']}")
            lineas_script.append(f"capa_nombre_{capa_safe} = '{capa}'")
            lineas_script.append("")

        lineas_script.extend([
            "def crear_capa(segmentos, altura, nombre, grosor=None):",
            "    if grosor is None:",
            "        n = nombre.lower()",
            "        if 'muro' in n:",
            "            grosor = 0.4",
            "        elif 'mueble' in n or 'mobiliario' in n or 'mueb' in n:",
            "            grosor = 0.6",
            "        elif 'piso' in n or 'nivel' in n:",
            "            grosor = 0.05",
            "        elif 'arbol' in n or 'vegetaci' in n or 'paisaj' in n:",
            "            grosor = 0.5",
            "        elif 'escalera' in n:",
            "            grosor = 0.3",
            "        else:",
            "            grosor = 0.3",
            "    formas = []",
            "    for idx, (x1, y1, x2, y2) in enumerate(segmentos):",
            "        try:",
            "            dx = x2 - x1",
            "            dy = y2 - y1",
            "            largo = math.sqrt(dx*dx + dy*dy)",
            "            if largo < 0.05:",
            "                continue",
            "            ang = math.degrees(math.atan2(dy, dx))",
            "            caja = Part.makeBox(largo, grosor, altura)",
            "            caja.rotate(FreeCAD.Vector(0, 0, 0), FreeCAD.Vector(0, 0, 1), ang)",
            "            caja.translate(FreeCAD.Vector(x1, y1, 0))",
            "            formas.append(caja)",
            "        except Exception:",
            "            pass",
            "    if formas:",
            "        compuesto = Part.makeCompound(formas)",
            "        obj = doc.addObject('Part::Feature', nombre)",
            "        obj.Shape = compuesto",
            "",
        ])
        for capa in capas_data.keys():
            capa_safe = re.sub(r'[^a-zA-Z0-9_]', '_', capa)
            lineas_script.append(
                f"crear_capa(capa_segs_{capa_safe}, capa_altura_{capa_safe}, capa_nombre_{capa_safe})"
            )

        lineas_script.extend([
            "",
            "doc.recompute()",
            "todos = [o for o in doc.Objects if hasattr(o, 'Shape') and o.Shape]",
            "print('TOTAL OBJETOS: ' + str(len(todos)))",
            "if todos:",
            "    import Import",
            "    Import.export(todos, OUT)",
            "    print('OK_STEP: ' + OUT)",
            "else:",
            "    print('ERROR: no se creo nada')",
        ])

        script = "\n".join(lineas_script)

        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False, encoding="utf-8") as f:
            f.write(script)
            script_path = f.name
        try:
            result = subprocess.run(
                [FREECAD_CMD, script_path],
                capture_output=True, text=True, timeout=900,
                encoding="utf-8", errors="replace",
            )
            stdout = result.stdout or ""
        except Exception as e:
            return {"thought": "Error", "display": f"Error FreeCAD: {e}", "voice": "Error."}
        finally:
            try:
                os.unlink(script_path)
            except Exception:
                pass

        if "OK_STEP" not in stdout:
            return {"thought": "Error", "display": f"FreeCAD no completo. Log:\n{stdout[-800:]}", "voice": "Error."}

        lineas_resumen = [
            "Modelo completo 3D generado.",
            f"  Capas procesadas: {len(capas_data)}",
            f"  Total segmentos: {total_segmentos}",
            f"  STEP: {output_final}",
            "",
            "Detalle por capa:",
        ]
        for capa, datos in sorted(capas_data.items(), key=lambda x: -x[1]["count"]):
            lineas_resumen.append(f"  [{datos['count']:5d}] {capa} (altura {datos['altura']}m)")

        return {
            "thought": f"Modelo completo con {total_segmentos} segmentos",
            "display": "\n".join(lineas_resumen),
            "voice": f"Modelo completo con {len(capas_data)} capas y {total_segmentos} segmentos.",
        }

    # ─── HELPERS INTERNOS ───────────────────────────────────────────────

    def _extraer_segmentos(self, msp, capas, min_largo=0.3):
        """Extrae segmentos de las capas dadas."""
        segmentos = []
        for entidad in msp:
            try:
                if entidad.dxf.layer not in capas:
                    continue
                tipo = entidad.dxftype()
                if tipo == 'LINE':
                    p1 = entidad.dxf.start
                    p2 = entidad.dxf.end
                    largo = ((p2.x - p1.x) ** 2 + (p2.y - p1.y) ** 2) ** 0.5
                    if largo > min_largo:
                        segmentos.append((p1.x, p1.y, p2.x, p2.y))
                elif tipo == 'LWPOLYLINE':
                    puntos = list(entidad.get_points('xy'))
                    for i in range(len(puntos) - 1):
                        x1, y1 = puntos[i]
                        x2, y2 = puntos[i + 1]
                        largo = ((x2 - x1) ** 2 + (y2 - y1) ** 2) ** 0.5
                        if largo > 1.0:
                            segmentos.append((x1, y1, x2, y2))
            except Exception:
                continue
        return segmentos

    def _exportar_step(self, segmentos, output_path, altura, grosor, prefijo):
        """Exporta segmentos a STEP usando FreeCAD."""
        out_esc = output_path.replace("\\", "/")
        segs_str = ",\n    ".join(f"({x1:.3f}, {y1:.3f}, {x2:.3f}, {y2:.3f})" for x1, y1, x2, y2 in segmentos)

        lineas_script = [
            "import FreeCAD",
            "import Part",
            "import math",
            "",
            f"OUT = r'{out_esc}'",
            f"ALTURA = {altura}",
            f"GROSOR = {grosor}",
            f"PREFIJO = '{prefijo}'",
            "segmentos = [",
            "    " + segs_str,
            "]",
            "doc = FreeCAD.newDocument('Modelo3D')",
            "for idx, (x1, y1, x2, y2) in enumerate(segmentos):",
            "    try:",
            "        dx = x2 - x1",
            "        dy = y2 - y1",
            "        largo = math.sqrt(dx*dx + dy*dy)",
            "        if largo < 0.05:",
            "            continue",
            "        ang = math.degrees(math.atan2(dy, dx))",
            "        caja = Part.makeBox(largo, GROSOR, ALTURA)",
            "        caja.rotate(FreeCAD.Vector(0, 0, 0), FreeCAD.Vector(0, 0, 1), ang)",
            "        caja.translate(FreeCAD.Vector(x1, y1, 0))",
            "        obj = doc.addObject('Part::Feature', PREFIJO + str(idx))",
            "        obj.Shape = caja",
            "    except Exception:",
            "        pass",
            "doc.recompute()",
            "todos = [o for o in doc.Objects if hasattr(o, 'Shape') and o.Shape]",
            "if todos:",
            "    import Import",
            "    Import.export(todos, OUT)",
            "    print('OK_STEP: ' + OUT)",
            "else:",
            "    print('ERROR')",
        ]
        script = "\n".join(lineas_script)

        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False, encoding="utf-8") as f:
            f.write(script)
            script_path = f.name
        try:
            result = subprocess.run(
                [FREECAD_CMD, script_path],
                capture_output=True, text=True, timeout=900,
                encoding="utf-8", errors="replace",
            )
            stdout = result.stdout or ""
        except Exception as e:
            return False, f"Error FreeCAD: {e}"
        finally:
            try:
                os.unlink(script_path)
            except Exception:
                pass

        if "OK_STEP" not in stdout:
            return False, f"FreeCAD no completo. Log:\n{stdout[-500:]}"
        return True, None