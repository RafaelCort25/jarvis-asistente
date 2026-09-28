"""Skill de retouch profesional: quitar fondo, upscaling, sombras, watermark.

Pipeline comun:
  1. remove_bg    -> quitar fondo con rembg (BRIA RMBG 2.0)
  2. white_bg     -> poner fondo blanco/color
  3. upscale      -> aumentar resolucion 2x/4x con Upscayl (Real-ESRGAN)
  4. enhance      -> brillo/contraste/saturacion/nitidez
  5. shadow       -> anadir sombra realista
  6. watermark    -> marca de agua de texto

Todo funciona en local y es gratuito.
"""
import io
import os
import re
import shutil
import subprocess
from datetime import datetime
from pathlib import Path

from PIL import Image, ImageEnhance, ImageFilter, ImageDraw, ImageFont

from skills.base import Skill
from core import confirmation

ROOT = Path(__file__).resolve().parent.parent
RETOUCH_DIR = ROOT / "sandbox" / "retouch"
RETOUCH_DIR.mkdir(parents=True, exist_ok=True)

# Rutas de Upscayl (se detectan automaticamente)
UPSCAYL_PATHS = [
    Path(r"C:\Program Files\Upscayl\resources\bin\upscayl-bin.exe"),
    Path(r"C:\Program Files (x86)\Upscayl\resources\bin\upscayl-bin.exe"),
]
UPSCAYL_MODELS_PATHS = [
    Path(r"C:\Program Files\Upscayl\resources\models"),
    Path(r"C:\Program Files (x86)\Upscayl\resources\models"),
]

# Modelos de upscayl disponibles
UPSCAYL_MODELS = {
    "estandar": "upscayl-standard-4x",
    "alta_fidelidad": "high-fidelity-4x",
    "ultramix": "ultramix-balanced-4x",
    "remacri": "remacri-4x",
    "ultrasharp": "ultrasharp-4x",
    "digital_art": "digital-art-4x",
    "lite": "upscayl-lite-4x",
}

# Extensiones soportadas
IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tiff", ".tif"}

# Modelos rembg (calidad vs velocidad)
# u2net = 176 MB, ~0.8s/imagen  <- RAPIDO y buena calidad (default)
# bria-rmbg = 977 MB, ~30s/imagen  <- Premium pero lentisimo
# isnet-general-use = 176 MB, ~1s/imagen  <- Muy buena calidad
REMBG_MODEL_DEFAULT = "u2net"

REMBG_MODELS = {
    "rapido": "u2net",           # 0.8s
    "calidad": "isnet-general-use",  # 1s, mejor calidad
    "premium": "bria-rmbg",      # 30s, mejor calidad premium
    "personas": "u2net_human_seg",
    "anime": "isnet-anime",
}

# Fondo
WHITE = (255, 255, 255)
BLACK = (0, 0, 0)

# ----------------------------------------------------------------


def _find_upscayl():
    """Devuelve (bin_path, models_dir) o (None, None)."""
    for p in UPSCAYL_PATHS:
        if p.exists():
            for m in UPSCAYL_MODELS_PATHS:
                if m.exists():
                    return p, m
    return None, None


def _slugify(text, maxlen=40):
    s = text.lower()
    for k, v in {"á":"a","é":"e","í":"i","ó":"o","ú":"u","ñ":"n","ü":"u"}.items():
        s = s.replace(k, v)
    s = re.sub(r'[^a-z0-9]+', '_', s)[:maxlen].strip("_")
    return s or "imagen"


class RetouchSkill(Skill):
    name = "retouch"
    description = "Retoque profesional: quitar fondo, upscaling, sombras, watermark"

    def run(self, action, params):
        if action == "remove_bg":
            return self._remove_bg(
                params.get("path", ""),
                params.get("output", ""),
                params.get("model", REMBG_MODEL_DEFAULT),
            )
        if action == "upscale":
            return self._upscale(
                params.get("path", ""),
                params.get("scale", 4),
                params.get("model", "estandar"),
                params.get("output", ""),
            )
        if action == "white_bg":
            return self._white_bg(
                params.get("path", ""),
                params.get("color", "white"),
                params.get("output", ""),
            )
        if action == "enhance":
            return self._enhance(
                params.get("path", ""),
                params.get("brightness", 1.0),
                params.get("contrast", 1.0),
                params.get("saturation", 1.0),
                params.get("sharpness", 1.0),
                params.get("output", ""),
            )
        if action == "shadow":
            return self._shadow(
                params.get("path", ""),
                params.get("blur", 15),
                params.get("offset_x", 5),
                params.get("offset_y", 8),
                params.get("opacity", 0.4),
                params.get("output", ""),
            )
        if action == "watermark":
            return self._watermark(
                params.get("path", ""),
                params.get("text", ""),
                params.get("position", "bottom-right"),
                params.get("opacity", 0.5),
                params.get("size", 30),
                params.get("output", ""),
            )
        if action == "pipeline":
            return self._pipeline(params)
        if action == "batch":
            return self._batch(params)
        return f"Accion desconocida en retouch: {action}"

    # ─── HELPERS ──────────────────────────────────────────────────────────

    def _resolve_input(self, path_str):
        """Resuelve un path de entrada. Acepta tambien el ultimo archivo en RETOUCH_DIR."""
        if not path_str:
            # Coger el ultimo archivo
            files = sorted(RETOUCH_DIR.glob("*"), key=lambda p: p.stat().st_mtime, reverse=True)
            files = [f for f in files if f.suffix.lower() in IMAGE_EXTS and "_out" not in f.stem]
            if not files:
                return None
            return files[0]

        raw = path_str.strip().strip('"').strip("'")
        p = Path(raw)
        if not p.is_absolute():
            p = ROOT / p
        if not p.exists():
            return None
        return p

    def _resolve_output(self, input_path, output_str, suffix):
        """Devuelve el path de salida."""
        if output_str:
            raw = output_str.strip().strip('"').strip("'")
            out = Path(raw)
            if not out.is_absolute():
                out = ROOT / out
            if not out.suffix:
                out = out.with_suffix(".png")
        else:
            out = input_path.with_name(f"{input_path.stem}{suffix}.png")

        # Seguridad: no salir de sandbox
        try:
            out.relative_to(ROOT / "sandbox")
        except ValueError:
            try:
                out.relative_to(ROOT)
            except ValueError:
                return None
        return out

    def _load_image(self, path):
        img = Image.open(str(path))
        return img

    # ─── REMOVE BG ────────────────────────────────────────────────────────

    def _remove_bg(self, path_str, output_str, model=REMBG_MODEL_DEFAULT):
        path = self._resolve_input(path_str)
        if not path:
            return {"thought": "", "display": "No encontre la imagen.", "voice": "No encontre la imagen."}

        if path.suffix.lower() not in IMAGE_EXTS:
            return f"Formato no soportado: {path.suffix}"

        out = self._resolve_output(path, output_str, "_nobg")
        if not out:
            return "Ruta de salida invalida."

        # Resolver nombre del modelo (acepta alias tipo "calidad" o el nombre directo)
        model_name = REMBG_MODELS.get(model.lower(), model)

        print(f"[RETOUCH] Quitando fondo de {path.name} (modelo: {model_name})...")
        try:
            from rembg import remove, new_session
            # Cache de sesiones para no recargar el modelo
            if not hasattr(self, "_rembg_sessions"):
                self._rembg_sessions = {}
            if model_name not in self._rembg_sessions:
                print(f"[RETOUCH] Cargando modelo {model_name}...")
                self._rembg_sessions[model_name] = new_session(model_name)
            sess = self._rembg_sessions[model_name]

            input_bytes = path.read_bytes()
            output_bytes = remove(input_bytes, session=sess)
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_bytes(output_bytes)
        except Exception as e:
            return {"thought": "Error rembg", "display": f"Error quitando fondo: {e}", "voice": "Error."}

        size_kb = out.stat().st_size // 1024
        print(f"[RETOUCH] Guardado: {out} ({size_kb} KB)")
        return {
            "thought": f"Fondo quitado ({size_kb} KB, modelo {model_name})",
            "display": f"Fondo quitado: {out.name}\n({size_kb} KB, modelo {model_name})",
            "voice": "Listo. Fondo eliminado.",
        }

    # ─── UPSCALE ──────────────────────────────────────────────────────────

    def _upscale(self, path_str, scale, model, output_str):
        upscayl, models_dir = _find_upscayl()
        if not upscayl:
            return {"thought": "", "display": "Upscayl no encontrado. Instala Upscayl.", "voice": "Upscayl no instalado."}

        path = self._resolve_input(path_str)
        if not path:
            return {"thought": "", "display": "No encontre la imagen.", "voice": "No encontre la imagen."}

        try:
            scale = int(scale)
        except (ValueError, TypeError):
            scale = 4
        if scale not in (2, 3, 4):
            scale = 4

        model_name = UPSCAYL_MODELS.get(model.lower(), UPSCAYL_MODELS["estandar"])

        out = self._resolve_output(path, output_str, f"_x{scale}")
        if not out:
            return "Ruta de salida invalida."

        try:
            out.parent.mkdir(parents=True, exist_ok=True)
            print(f"[RETOUCH] Upscaling {path.name} {scale}x con modelo {model_name}...")
            result = subprocess.run(
                [str(upscayl), "-i", str(path), "-o", str(out),
                 "-s", str(scale), "-m", str(models_dir), "-n", model_name, "-f", "png"],
                capture_output=True, text=True, timeout=300,
            )
            if result.returncode != 0 or not out.exists():
                return {"thought": "Error upscaling", "display": f"Error: {result.stderr[:300]}", "voice": "Error."}
        except subprocess.TimeoutExpired:
            return {"thought": "", "display": "Timeout al upscalear (mas de 5 min).", "voice": "Timeout."}
        except Exception as e:
            return {"thought": "", "display": f"Error: {e}", "voice": "Error."}

        # Obtener dimensiones
        try:
            img = Image.open(str(out))
            dims = f"{img.size[0]}x{img.size[1]}"
        except Exception:
            dims = "?"

        size_kb = out.stat().st_size // 1024
        return {
            "thought": f"Upscaled {scale}x ({dims})",
            "display": f"Upscaled {scale}x: {out.name}\n({dims}, {size_kb} KB, modelo {model_name})",
            "voice": f"Listo. Imagen {scale}x mas grande.",
        }

    # ─── WHITE BG ─────────────────────────────────────────────────────────

    def _white_bg(self, path_str, color, output_str):
        path = self._resolve_input(path_str)
        if not path:
            return "No encontre la imagen."

        out = self._resolve_output(path, output_str, "_fondo")
        if not out:
            return "Ruta de salida invalida."

        # Mapear color
        color_map = {
            "white": (255, 255, 255),
            "blanco": (255, 255, 255),
            "black": (0, 0, 0),
            "negro": (0, 0, 0),
            "transparent": None,
            "transparente": None,
        }
        bg_color = color_map.get(color.lower(), (255, 255, 255))

        try:
            img = self._load_image(path).convert("RGBA")
        except Exception as e:
            return f"Error abriendo imagen: {e}"

        if bg_color is None:
            # Solo guardar como PNG con transparencia
            out.parent.mkdir(parents=True, exist_ok=True)
            img.save(str(out), "PNG")
            return {
                "thought": "Guardado con transparencia",
                "display": f"Guardado con transparencia: {out.name}",
                "voice": "Listo. Imagen con transparencia.",
            }

        # Poner fondo
        bg = Image.new("RGBA", img.size, bg_color + (255,))
        bg.paste(img, (0, 0), img)
        out.parent.mkdir(parents=True, exist_ok=True)
        bg.convert("RGB").save(str(out), "PNG")

        size_kb = out.stat().st_size // 1024
        return {
            "thought": f"Fondo {color} aplicado",
            "display": f"Fondo {color}: {out.name}\n({size_kb} KB)",
            "voice": f"Listo. Fondo {color} aplicado.",
        }

    # ─── ENHANCE ──────────────────────────────────────────────────────────

    def _enhance(self, path_str, brightness, contrast, saturation, sharpness, output_str):
        path = self._resolve_input(path_str)
        if not path:
            return "No encontre la imagen."

        out = self._resolve_output(path, output_str, "_enhanced")
        if not out:
            return "Ruta de salida invalida."

        try:
            img = self._load_image(path)
        except Exception as e:
            return f"Error abriendo imagen: {e}"

        # Aplicar ajustes (los valores son multiplicadores: 1.0 = sin cambio)
        try:
            if float(brightness) != 1.0:
                img = ImageEnhance.Brightness(img).enhance(float(brightness))
            if float(contrast) != 1.0:
                img = ImageEnhance.Contrast(img).enhance(float(contrast))
            if float(saturation) != 1.0:
                img = ImageEnhance.Color(img).enhance(float(saturation))
            if float(sharpness) != 1.0:
                img = ImageEnhance.Sharpness(img).enhance(float(sharpness))
        except (ValueError, TypeError) as e:
            return f"Parametros invalidos: {e}"

        out.parent.mkdir(parents=True, exist_ok=True)
        img.save(str(out))

        size_kb = out.stat().st_size // 1024
        cambios = []
        if float(brightness) != 1.0:
            cambios.append(f"brillo={brightness}")
        if float(contrast) != 1.0:
            cambios.append(f"contraste={contrast}")
        if float(saturation) != 1.0:
            cambios.append(f"saturacion={saturation}")
        if float(sharpness) != 1.0:
            cambios.append(f"nitidez={sharpness}")

        return {
            "thought": f"Ajustes aplicados: {', '.join(cambios)}",
            "display": f"Imagen ajustada: {out.name}\n({size_kb} KB)\nCambios: {', '.join(cambios) or 'ninguno'}",
            "voice": "Listo. Ajustes aplicados.",
        }

    # ─── SHADOW ───────────────────────────────────────────────────────────

    def _shadow(self, path_str, blur, offset_x, offset_y, opacity, output_str):
        path = self._resolve_input(path_str)
        if not path:
            return "No encontre la imagen."

        out = self._resolve_output(path, output_str, "_shadow")
        if not out:
            return "Ruta de salida invalida."

        try:
            img = self._load_image(path).convert("RGBA")
        except Exception as e:
            return f"Error abriendo imagen: {e}"

        try:
            blur = int(blur)
            offset_x = int(offset_x)
            offset_y = int(offset_y)
            opacity = float(opacity)
        except (ValueError, TypeError):
            blur, offset_x, offset_y, opacity = 15, 5, 8, 0.4

        opacity = max(0.0, min(1.0, opacity))

        # Crear silueta negra de la imagen (usando alpha)
        alpha = img.split()[-1]
        shadow = Image.new("RGBA", img.size, (0, 0, 0, 0))
        black = Image.new("RGBA", img.size, (0, 0, 0, int(255 * opacity)))
        shadow.paste(black, (0, 0), alpha)

        # Aplicar blur
        shadow = shadow.filter(ImageFilter.GaussianBlur(blur))

        # Crear canvas mas grande para que quepa la sombra
        pad = blur * 2 + max(abs(offset_x), abs(offset_y)) + 20
        canvas_size = (img.size[0] + pad * 2, img.size[1] + pad * 2)
        canvas = Image.new("RGBA", canvas_size, (0, 0, 0, 0))

        # Pegar sombra con offset
        canvas.paste(shadow, (pad + offset_x, pad + offset_y), shadow)
        # Pegar imagen original encima
        canvas.paste(img, (pad, pad), img)

        out.parent.mkdir(parents=True, exist_ok=True)
        canvas.save(str(out), "PNG")

        size_kb = out.stat().st_size // 1024
        return {
            "thought": f"Sombra aplicada (blur={blur})",
            "display": f"Sombra aplicada: {out.name}\n({canvas_size[0]}x{canvas_size[1]}, {size_kb} KB)",
            "voice": "Listo. Sombra aplicada.",
        }

    # ─── WATERMARK ────────────────────────────────────────────────────────

    def _watermark(self, path_str, text, position, opacity, size, output_str):
        path = self._resolve_input(path_str)
        if not path:
            return "No encontre la imagen."

        if not text:
            text = "SENNA"

        out = self._resolve_output(path, output_str, "_wm")
        if not out:
            return "Ruta de salida invalida."

        try:
            img = self._load_image(path).convert("RGBA")
        except Exception as e:
            return f"Error abriendo imagen: {e}"

        try:
            size = int(size)
            opacity = float(opacity)
        except (ValueError, TypeError):
            size, opacity = 30, 0.5
        opacity = max(0.1, min(1.0, opacity))

        # Intentar cargar fuente
        try:
            font = ImageFont.truetype("arial.ttf", size)
        except Exception:
            font = ImageFont.load_default()

        # Capa transparente
        overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay)

        # Medir texto
        bbox = draw.textbbox((0, 0), text, font=font)
        tw = bbox[2] - bbox[0]
        th = bbox[3] - bbox[1]
        margin = 20

        # Posicion
        positions = {
            "top-left": (margin, margin),
            "top-right": (img.size[0] - tw - margin, margin),
            "bottom-left": (margin, img.size[1] - th - margin - 10),
            "bottom-right": (img.size[0] - tw - margin, img.size[1] - th - margin - 10),
            "center": ((img.size[0] - tw) // 2, (img.size[1] - th) // 2),
        }
        xy = positions.get(position.lower(), positions["bottom-right"])

        # Sombra del texto (para legibilidad)
        draw.text((xy[0] + 2, xy[1] + 2), text, font=font, fill=(0, 0, 0, int(255 * opacity * 0.6)))
        draw.text(xy, text, font=font, fill=(255, 255, 255, int(255 * opacity)))

        # Combinar
        combined = Image.alpha_composite(img, overlay)

        out.parent.mkdir(parents=True, exist_ok=True)
        combined.save(str(out), "PNG")

        size_kb = out.stat().st_size // 1024
        return {
            "thought": f"Watermark '{text}' aplicado",
            "display": f"Watermark aplicado: {out.name}\n(texto: '{text}', posicion: {position})",
            "voice": "Listo. Marca de agua aplicada.",
        }

    # ─── PIPELINE ─────────────────────────────────────────────────────────

    def _pipeline(self, params):
        """Ejecuta varios pasos en orden sobre una imagen.

        params:
          path: imagen de entrada
          steps: lista de strings, ej. ["remove_bg", "white_bg", "upscale"]
          ... y los parametros de cada paso con prefijo, ej. upscale_scale=4
        """
        path_str = params.get("path", "")
        steps = params.get("steps", [])
        if not steps:
            return "Necesito la lista de pasos (steps)."

        path = self._resolve_input(path_str)
        if not path:
            return "No encontre la imagen."

        current = path
        resultados = []

        for step in steps:
            print(f"[RETOUCH] Paso: {step}")
            if step == "remove_bg":
                r = self._remove_bg(str(current), "")
            elif step == "white_bg":
                color = params.get("bg_color", "white")
                r = self._white_bg(str(current), color, "")
            elif step == "upscale":
                scale = params.get("upscale_scale", 4)
                model = params.get("upscale_model", "estandar")
                r = self._upscale(str(current), scale, model, "")
            elif step == "enhance":
                r = self._enhance(
                    str(current),
                    params.get("brightness", 1.0),
                    params.get("contrast", 1.0),
                    params.get("saturation", 1.0),
                    params.get("sharpness", 1.0),
                    "",
                )
            elif step == "shadow":
                r = self._shadow(str(current), params.get("blur", 15), 5, 8, 0.4, "")
            elif step == "watermark":
                r = self._watermark(
                    str(current),
                    params.get("watermark_text", ""),
                    "bottom-right",
                    0.5,
                    params.get("watermark_size", 30),
                    "",
                )
            else:
                resultados.append(f"Paso desconocido: {step}")
                continue

            if isinstance(r, dict) and r.get("display"):
                # El output es la ultima palabra del display
                resultados.append(r.get("display", "")[:100])
                # Intentar extraer el path de la salida
                m = re.search(r':\s*(\S+\.png)', r.get("display", ""))
                if m:
                    candidate = ROOT / "sandbox" / "retouch" / m.group(1)
                    if candidate.exists():
                        current = candidate
            else:
                resultados.append(str(r)[:100])

        return {
            "thought": f"Pipeline completado: {' -> '.join(steps)}",
            "display": "Pipeline:\n" + "\n".join(f"  {i+1}. {r}" for i, r in enumerate(resultados)) + f"\n\nResultado final: {current}",
            "voice": "Listo. Retoque aplicado.",
        }

    # ─── BATCH ────────────────────────────────────────────────────────────

    def _batch(self, params):
        """Procesa una carpeta entera con una serie de pasos."""
        folder_str = params.get("path", "")
        steps = params.get("steps", [])
        if not steps:
            return "Necesito la lista de pasos (steps)."

        folder = Path(folder_str.strip().strip('"').strip("'"))
        if not folder.is_absolute():
            folder = ROOT / folder
        if not folder.exists():
            return f"No encontre la carpeta: {folder}"

        # Recoger imagenes
        imagenes = [f for f in folder.iterdir() if f.suffix.lower() in IMAGE_EXTS]
        if not imagenes:
            return f"No hay imagenes en {folder}"

        # Crear carpeta de salida
        out_dir = folder / "retocado"
        out_dir.mkdir(exist_ok=True)

        summary = f"Procesar {len(imagenes)} imagenes con pipeline {' -> '.join(steps)}"
        if not confirmation.require("retouch", "batch", summary):
            return "Cancelado."

        exitos = 0
        fallos = 0
        print(f"[RETOUCH] Procesando {len(imagenes)} imagenes...")

        for i, img in enumerate(imagenes, 1):
            print(f"[RETOUCH] {i}/{len(imagenes)}: {img.name}")
            # Copiar a output y aplicar pipeline
            current = img
            for step in steps:
                try:
                    if step == "remove_bg":
                        r = self._remove_bg(str(current), "")
                    elif step == "upscale":
                        r = self._upscale(str(current), params.get("upscale_scale", 4), params.get("upscale_model", "estandar"), "")
                    elif step == "white_bg":
                        r = self._white_bg(str(current), params.get("bg_color", "white"), "")
                    elif step == "enhance":
                        r = self._enhance(str(current), 1.1, 1.1, 1.05, 1.2, "")
                    else:
                        continue
                    # Actualizar current con el nuevo path
                    m = re.search(r':\s*(\S+\.png)', r.get("display", "") if isinstance(r, dict) else str(r))
                    if m:
                        candidate = ROOT / "sandbox" / "retouch" / m.group(1)
                        if candidate.exists():
                            current = candidate
                except Exception as e:
                    print(f"[RETOUCH] Error en paso {step}: {e}")

            # Mover a out_dir
            try:
                final = out_dir / current.name
                shutil.copy2(str(current), str(final))
                exitos += 1
            except Exception as e:
                print(f"[RETOUCH] Error copiando: {e}")
                fallos += 1

        return {
            "thought": f"Batch: {exitos} exitos, {fallos} fallos",
            "display": f"Batch completado:\n  {exitos} imagenes procesadas\n  {fallos} fallos\n\nGuardadas en: {out_dir}",
            "voice": f"Listo. Procese {exitos} imagenes.",
        }
