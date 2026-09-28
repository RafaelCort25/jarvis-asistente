"""Skill de video: recortar, unir, convertir, comprimir, subtitulos, GIF."""

import json
import re
import subprocess
from datetime import datetime
from pathlib import Path
from skills.base import Skill
from core import confirmation

ROOT = Path(__file__).resolve().parent.parent
VIDEO_DIR = ROOT / "sandbox" / "video"
VIDEO_DIR.mkdir(parents=True, exist_ok=True)

FFMPEG = ROOT / "tools" / "ffmpeg.exe"

VIDEO_EXTS = {".mp4", ".mkv", ".avi", ".mov", ".webm", ".flv", ".wmv", ".m4v", ".mpg", ".mpeg", ".3gp"}


def _slugify(text, maxlen=40):
    s = text.lower()
    for k, v in {"a":"a","e":"e","i":"i","o":"o","u":"u","n":"n"}.items():
        s = s.replace(k, v)
    s = re.sub(r"[^a-z0-9]+", "_", s)[:maxlen].strip("_")
    return s or "video"


def _run(args, timeout=600):
    try:
        r = subprocess.run(
            [str(FFMPEG)] + [str(a) for a in args],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
        )
        return r.returncode, r.stdout or "", r.stderr or ""
    except subprocess.TimeoutExpired:
        return -1, "", f"Timeout ({timeout}s)"
    except Exception as e:
        return -1, "", str(e)


def _fmt_dur(seconds):
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    if h > 0:
        return f"{h:02d}:{m:02d}:{s:02d}"
    return f"{m:02d}:{s:02d}"


def _parse_time(text):
    if text is None:
        return None
    if isinstance(text, (int, float)):
        return float(text)
    t = str(text).strip().lower()
    if not t:
        return None
    m = re.match(r"^(?:(\d+(?:\.\d+)?)h)?(?:(\d+(?:\.\d+)?)m)?(?:(\d+(?:\.\d+)?)s)?$", t)
    if m and any(m.groups()):
        h = float(m.group(1) or 0)
        mi = float(m.group(2) or 0)
        se = float(m.group(3) or 0)
        return h * 3600 + mi * 60 + se
    if ":" in t:
        parts = t.split(":")
        try:
            parts = [float(p) for p in parts]
        except ValueError:
            return None
        if len(parts) == 2:
            return parts[0] * 60 + parts[1]
        if len(parts) == 3:
            return parts[0] * 3600 + parts[1] * 60 + parts[2]
    try:
        return float(t)
    except ValueError:
        return None


class VideoSkill(Skill):
    name = "video"
    description = "Editor de video: trim, merge, convert, compress, gif, subtitulos"

    def run(self, action, params):
        if not FFMPEG.exists():
            return {"thought": "Falta ffmpeg", "display": f"No encuentro ffmpeg en {FFMPEG}", "voice": "Falta ffmpeg."}

        try:
            if action == "info":
                return self._info(params.get("path", ""))
            if action == "trim":
                return self._trim(params)
            if action == "merge":
                return self._merge(params)
            if action == "extract_audio":
                return self._extract_audio(params)
            if action == "extract_frames":
                return self._extract_frames(params)
            if action == "convert":
                return self._convert(params)
            if action == "compress":
                return self._compress(params)
            if action == "add_subtitles":
                return self._add_subtitles(params)
            if action == "add_music":
                return self._add_music(params)
            if action == "speed":
                return self._speed(params)
            if action == "gif":
                return self._gif(params)
            if action == "thumbnail":
                return self._thumbnail(params)
            if action == "rotate":
                return self._rotate(params)
            if action == "mute":
                return self._mute(params)
            if action == "list":
                return self._list()
            return f"Accion desconocida en video: {action}"
        except Exception as e:
            return {"thought": "Error", "display": f"Error: {e}", "voice": "Error en video."}

    def _resolve_input(self, path_str):
        if not path_str:
            files = sorted(VIDEO_DIR.glob("*"), key=lambda p: p.stat().st_mtime, reverse=True)
            files = [f for f in files if f.suffix.lower() in VIDEO_EXTS and "_out" not in f.stem]
            return files[0] if files else None
        raw = path_str.strip().strip('"').strip("'")
        p = Path(raw)
        if not p.is_absolute():
            p = ROOT / p
        return p if p.exists() else None

    def _resolve_output(self, input_path, output_str, suffix, ext):
        if output_str:
            raw = output_str.strip().strip('"').strip("'")
            out = Path(raw)
            if not out.is_absolute():
                out = ROOT / out
            if not out.suffix:
                out = out.with_suffix("." + ext)
        else:
            out = input_path.with_name(f"{input_path.stem}{suffix}.{ext}")
        try:
            out.relative_to(ROOT)
        except ValueError:
            return None
        return out

    def _parse_ffmpeg_info(self, stderr):
        info = {"duration": 0, "size_mb": 0, "bitrate": "", "streams": []}
        m = re.search(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)", stderr)
        if m:
            info["duration"] = int(m.group(1))*3600 + int(m.group(2))*60 + float(m.group(3))
        m = re.search(r"bitrate:\s*(\d+)\s*kb/s", stderr)
        if m:
            info["bitrate"] = m.group(1) + " kb/s"
        for line in stderr.splitlines():
            line = line.strip()
            if line.startswith("Stream #"):
                info["streams"].append(line)
        return info

    def _info(self, path_str):
        path = self._resolve_input(path_str)
        if not path:
            return {"thought": "", "display": "No encontre el video.", "voice": "No encontre el video."}
        code, _, err = _run(["-i", str(path)])
        info = self._parse_ffmpeg_info(err)
        size_mb = round(path.stat().st_size / 1024 / 1024, 2)
        dur = info["duration"]
        lineas = [
            "**Video:** " + path.name,
            f"**Tamano:** {size_mb} MB",
            f"**Duracion:** {_fmt_dur(dur)}",
        ]
        if info["bitrate"]:
            lineas.append("**Bitrate:** " + info["bitrate"])
        if info["streams"]:
            lineas.append("")
            lineas.append("**Streams:**")
            for s in info["streams"]:
                lineas.append("  " + s)
        return {
            "thought": f"Info: {_fmt_dur(dur)}",
            "display": "\n".join(lineas),
            "voice": f"El video dura {_fmt_dur(dur)}.",
        }

    def _trim(self, params):
        path = self._resolve_input(params.get("path", ""))
        if not path:
            return {"thought": "", "display": "No encontre el video.", "voice": "No encontre el video."}
        start = _parse_time(params.get("start", 0)) or 0
        end = _parse_time(params.get("end", None))
        duration = _parse_time(params.get("duration", None))
        if end is None and duration is None:
            return {"thought": "", "display": "Necesito end o duration.", "voice": "Faltan datos."}
        out = self._resolve_output(path, params.get("output", ""), "_trim", path.suffix.lstrip("."))
        if not out:
            return "Ruta de salida invalida."
        args = ["-y", "-ss", str(start), "-i", str(path)]
        if end is not None:
            args += ["-to", str(end)]
        elif duration is not None:
            args += ["-t", str(duration)]
        args += ["-c", "copy", str(out)]
        code, _, err = _run(args)
        if code != 0:
            args = ["-y", "-ss", str(start), "-i", str(path)]
            if end is not None:
                args += ["-to", str(end)]
            elif duration is not None:
                args += ["-t", str(duration)]
            args += ["-c:v", "libx264", "-c:a", "aac", "-preset", "fast", str(out)]
            code, _, err = _run(args)
            if code != 0:
                return {"thought": "Error trim", "display": f"Error: {err[:300]}", "voice": "Error."}
        size_mb = round(out.stat().st_size / 1024 / 1024, 2)
        return {
            "thought": f"Video recortado ({size_mb} MB)",
            "display": f"**Video recortado**\n- Inicio: {_fmt_dur(start)}\n- Archivo: {out.name}\n- Tamano: {size_mb} MB",
            "voice": "Video recortado.",
        }

    def _merge(self, params):
        paths_raw = params.get("paths", [])
        if not paths_raw or len(paths_raw) < 2:
            return {"thought": "", "display": "Necesito al menos 2 videos.", "voice": "Faltan videos."}
        paths = []
        for p in paths_raw:
            r = self._resolve_input(p)
            if r:
                paths.append(r)
        if len(paths) < 2:
            return {"thought": "", "display": "No encontre suficientes videos validos.", "voice": "Error."}
        out = self._resolve_output(paths[0], params.get("output", ""), "_merged", "mp4")
        if not out:
            return "Ruta de salida invalida."
        list_file = VIDEO_DIR / f"_merge_list_{int(datetime.now().timestamp())}.txt"
        list_file.write_text("\n".join("file '" + p.as_posix() + "'" for p in paths), encoding="utf-8")
        args = ["-y", "-f", "concat", "-safe", "0", "-i", str(list_file), "-c", "copy", str(out)]
        code, _, err = _run(args)
        if code != 0:
            args = ["-y", "-f", "concat", "-safe", "0", "-i", str(list_file), "-c:v", "libx264", "-c:a", "aac", "-preset", "fast", str(out)]
            code, _, err = _run(args)
            if code != 0:
                try:
                    list_file.unlink()
                except Exception:
                    pass
                return {"thought": "Error merge", "display": f"Error: {err[:300]}", "voice": "Error."}
        try:
            list_file.unlink()
        except Exception:
            pass
        size_mb = round(out.stat().st_size / 1024 / 1024, 2)
        return {
            "thought": f"Videos unidos ({len(paths)})",
            "display": f"**Videos unidos**\n- Total: {len(paths)} videos\n- Archivo: {out.name}\n- Tamano: {size_mb} MB",
            "voice": f"Listo. Uni {len(paths)} videos.",
        }

    def _extract_audio(self, params):
        path = self._resolve_input(params.get("path", ""))
        if not path:
            return {"thought": "", "display": "No encontre el video.", "voice": "No encontre el video."}
        fmt = (params.get("format", "mp3") or "mp3").lower()
        if fmt not in ("mp3", "wav", "m4a", "aac", "flac", "ogg"):
            fmt = "mp3"
        out = self._resolve_output(path, params.get("output", ""), "_audio", fmt)
        if not out:
            return "Ruta de salida invalida."
        codec_map = {"mp3": "libmp3lame", "wav": "pcm_s16le", "m4a": "aac", "aac": "aac", "flac": "flac", "ogg": "libvorbis"}
        code, _, err = _run(["-y", "-i", str(path), "-vn", "-c:a", codec_map[fmt], str(out)])
        if code != 0:
            return {"thought": "Error", "display": f"Error: {err[:300]}", "voice": "Error extrayendo audio."}
        size_mb = round(out.stat().st_size / 1024 / 1024, 2)
        return {
            "thought": f"Audio extraido ({fmt})",
            "display": f"**Audio extraido**\n- Formato: {fmt}\n- Archivo: {out.name}\n- Tamano: {size_mb} MB",
            "voice": f"Audio extraido a {fmt}.",
        }

    def _extract_frames(self, params):
        path = self._resolve_input(params.get("path", ""))
        if not path:
            return {"thought": "", "display": "No encontre el video.", "voice": "No encontre el video."}
        try:
            fps = float(params.get("fps", 1))
        except (ValueError, TypeError):
            fps = 1
        fps = max(0.1, min(fps, 60))
        out_dir = VIDEO_DIR / f"{path.stem}_frames"
        out_dir.mkdir(parents=True, exist_ok=True)
        pattern = out_dir / "frame_%04d.png"
        code, _, err = _run(["-y", "-i", str(path), "-vf", f"fps={fps}", str(pattern)], timeout=900)
        if code != 0:
            return {"thought": "Error", "display": f"Error: {err[:300]}", "voice": "Error."}
        frames = list(out_dir.glob("frame_*.png"))
        return {
            "thought": f"{len(frames)} frames extraidos",
            "display": f"**Frames extraidos**\n- Total: {len(frames)}\n- FPS: {fps}\n- Carpeta: {out_dir}",
            "voice": f"Extraidos {len(frames)} frames.",
        }

    def _convert(self, params):
        path = self._resolve_input(params.get("path", ""))
        if not path:
            return {"thought": "", "display": "No encontre el video.", "voice": "No encontre el video."}
        fmt = (params.get("format", "mp4") or "mp4").lower().lstrip(".")
        if fmt not in ("mp4", "mkv", "avi", "mov", "webm", "flv", "wmv", "gif"):
            fmt = "mp4"
        out = self._resolve_output(path, params.get("output", ""), f"_{fmt}", fmt)
        if not out:
            return "Ruta de salida invalida."
        code, _, err = _run(["-y", "-i", str(path), "-c:v", "libx264", "-c:a", "aac", "-preset", "fast", str(out)])
        if code != 0:
            return {"thought": "Error", "display": f"Error: {err[:300]}", "voice": "Error."}
        size_mb = round(out.stat().st_size / 1024 / 1024, 2)
        return {
            "thought": f"Convertido a {fmt}",
            "display": f"**Convertido a {fmt}**\n- Archivo: {out.name}\n- Tamano: {size_mb} MB",
            "voice": f"Convertido a {fmt}.",
        }

    def _compress(self, params):
        path = self._resolve_input(params.get("path", ""))
        if not path:
            return {"thought": "", "display": "No encontre el video.", "voice": "No encontre el video."}
        try:
            crf = int(params.get("crf", 28))
        except (ValueError, TypeError):
            crf = 28
        crf = max(18, min(crf, 40))
        height = params.get("height", None)
        out = self._resolve_output(path, params.get("output", ""), "_compressed", "mp4")
        if not out:
            return "Ruta de salida invalida."
        args = ["-y", "-i", str(path), "-c:v", "libx264", "-crf", str(crf), "-preset", "slow"]
        if height:
            try:
                h = int(height)
                args += ["-vf", f"scale=-2:{h}"]
            except (ValueError, TypeError):
                pass
        args += ["-c:a", "aac", "-b:a", "128k", str(out)]
        code, _, err = _run(args, timeout=1200)
        if code != 0:
            return {"thought": "Error", "display": f"Error: {err[:300]}", "voice": "Error."}
        orig_mb = path.stat().st_size / 1024 / 1024
        new_mb = out.stat().st_size / 1024 / 1024
        ahorro = (1 - new_mb / orig_mb) * 100 if orig_mb > 0 else 0
        return {
            "thought": f"Comprimido: {ahorro:.0f}% menos",
            "display": f"**Comprimido**\n- Original: {orig_mb:.2f} MB\n- Nuevo: {new_mb:.2f} MB\n- Ahorro: {ahorro:.1f}%\n- CRF: {crf}",
            "voice": f"Comprimido. Ahorro {ahorro:.0f}%.",
        }

    def _add_subtitles(self, params):
        path = self._resolve_input(params.get("path", ""))
        srt = self._resolve_input(params.get("srt", ""))
        if not path:
            return {"thought": "", "display": "No encontre el video.", "voice": "No encontre el video."}
        if not srt or srt.suffix.lower() != ".srt":
            return {"thought": "", "display": "Necesito un archivo SRT valido.", "voice": "Falta SRT."}
        out = self._resolve_output(path, params.get("output", ""), "_subs", "mp4")
        if not out:
            return "Ruta de salida invalida."
        srt_escaped = str(srt).replace("\\", "/").replace(":", "\\:")
        vf = "subtitles='" + srt_escaped + "'"
        code, _, err = _run(["-y", "-i", str(path), "-vf", vf, "-c:a", "copy", str(out)])
        if code != 0:
            return {"thought": "Error", "display": f"Error: {err[:400]}", "voice": "Error."}
        size_mb = round(out.stat().st_size / 1024 / 1024, 2)
        return {
            "thought": "Subtitulos quemados",
            "display": f"**Subtitulos anadidos**\n- Archivo: {out.name}\n- Tamano: {size_mb} MB",
            "voice": "Subtitulos anadidos.",
        }

    def _add_music(self, params):
        path = self._resolve_input(params.get("path", ""))
        music = params.get("music", "")
        if music:
            music = Path(music.strip().strip('"').strip("'"))
            if not music.is_absolute():
                music = ROOT / music
        if not path or not music or not music.exists():
            return {"thought": "", "display": "Necesito video + archivo de audio.", "voice": "Faltan datos."}
        mode = (params.get("mode", "mix") or "mix").lower()
        out = self._resolve_output(path, params.get("output", ""), "_music", "mp4")
        if not out:
            return "Ruta de salida invalida."
        if mode == "replace":
            args = ["-y", "-i", str(path), "-i", str(music), "-map", "0:v", "-map", "1:a", "-c:v", "copy", "-c:a", "aac", "-shortest", str(out)]
        else:
            args = ["-y", "-i", str(path), "-i", str(music), "-filter_complex", "[0:a][1:a]amix=inputs=2:duration=first[a]", "-map", "0:v", "-map", "[a]", "-c:v", "copy", "-c:a", "aac", str(out)]
        code, _, err = _run(args)
        if code != 0:
            return {"thought": "Error", "display": f"Error: {err[:300]}", "voice": "Error."}
        size_mb = round(out.stat().st_size / 1024 / 1024, 2)
        return {
            "thought": f"Musica anadida ({mode})",
            "display": f"**Musica anadida**\n- Modo: {mode}\n- Archivo: {out.name}\n- Tamano: {size_mb} MB",
            "voice": "Musica anadida.",
        }

    def _speed(self, params):
        path = self._resolve_input(params.get("path", ""))
        if not path:
            return {"thought": "", "display": "No encontre el video.", "voice": "No encontre el video."}
        try:
            factor = float(params.get("factor", 2))
        except (ValueError, TypeError):
            factor = 2
        factor = max(0.25, min(factor, 4))
        out = self._resolve_output(path, params.get("output", ""), f"_x{factor}", "mp4")
        if not out:
            return "Ruta de salida invalida."
        vf = f"setpts={1/factor}*PTS"
        af = f"atempo={factor}" if 0.5 <= factor <= 2 else "atempo=1"
        args = ["-y", "-i", str(path), "-filter_complex", f"[0:v]{vf}[v];[0:a]{af}[a]", "-map", "[v]", "-map", "[a]", "-c:v", "libx264", "-preset", "fast", "-c:a", "aac", str(out)]
        code, _, err = _run(args, timeout=900)
        if code != 0:
            args = ["-y", "-i", str(path), "-vf", vf, "-an", "-c:v", "libx264", "-preset", "fast", str(out)]
            code, _, err = _run(args, timeout=900)
            if code != 0:
                return {"thought": "Error", "display": f"Error: {err[:300]}", "voice": "Error."}
        size_mb = round(out.stat().st_size / 1024 / 1024, 2)
        return {
            "thought": f"Velocidad x{factor}",
            "display": f"**Velocidad ajustada a x{factor}**\n- Archivo: {out.name}\n- Tamano: {size_mb} MB",
            "voice": f"Velocidad x{factor}.",
        }

    def _gif(self, params):
        path = self._resolve_input(params.get("path", ""))
        if not path:
            return {"thought": "", "display": "No encontre el video.", "voice": "No encontre el video."}
        start = _parse_time(params.get("start", 0)) or 0
        duration = _parse_time(params.get("duration", 5)) or 5
        try:
            fps = int(params.get("fps", 12))
        except (ValueError, TypeError):
            fps = 12
        try:
            width = int(params.get("width", 480))
        except (ValueError, TypeError):
            width = 480
        out = self._resolve_output(path, params.get("output", ""), "_gif", "gif")
        if not out:
            return "Ruta de salida invalida."
        vf = f"fps={fps},scale={width}:-1:flags=lanczos"
        args = ["-y", "-ss", str(start), "-t", str(duration), "-i", str(path), "-vf", vf, "-loop", "0", str(out)]
        code, _, err = _run(args)
        if code != 0:
            return {"thought": "Error", "display": f"Error: {err[:300]}", "voice": "Error."}
        size_mb = round(out.stat().st_size / 1024 / 1024, 2)
        return {
            "thought": f"GIF creado ({size_mb} MB)",
            "display": f"**GIF creado**\n- Archivo: {out.name}\n- FPS: {fps}\n- Ancho: {width}px\n- Tamano: {size_mb} MB",
            "voice": "GIF creado.",
        }

    def _thumbnail(self, params):
        path = self._resolve_input(params.get("path", ""))
        if not path:
            return {"thought": "", "display": "No encontre el video.", "voice": "No encontre el video."}
        at = _parse_time(params.get("at", 0)) or 0
        out = self._resolve_output(path, params.get("output", ""), "_thumb", "png")
        if not out:
            return "Ruta de salida invalida."
        code, _, err = _run(["-y", "-ss", str(at), "-i", str(path), "-frames:v", "1", str(out)])
        if code != 0:
            return {"thought": "Error", "display": f"Error: {err[:300]}", "voice": "Error."}
        return {
            "thought": f"Thumbnail en {_fmt_dur(at)}",
            "display": f"**Thumbnail**\n- Archivo: {out.name}\n- Momento: {_fmt_dur(at)}",
            "voice": "Thumbnail creado.",
        }

    def _rotate(self, params):
        path = self._resolve_input(params.get("path", ""))
        if not path:
            return {"thought": "", "display": "No encontre el video.", "voice": "No encontre el video."}
        try:
            angle = int(params.get("angle", 90))
        except (ValueError, TypeError):
            angle = 90
        if angle not in (90, 180, 270):
            angle = 90
        out = self._resolve_output(path, params.get("output", ""), f"_rot{angle}", "mp4")
        if not out:
            return "Ruta de salida invalida."
        transpose_map = {90: "transpose=1", 180: "transpose=2,transpose=2", 270: "transpose=2"}
        vf = transpose_map[angle]
        code, _, err = _run(["-y", "-i", str(path), "-vf", vf, "-c:a", "copy", str(out)])
        if code != 0:
            return {"thought": "Error", "display": f"Error: {err[:300]}", "voice": "Error."}
        size_mb = round(out.stat().st_size / 1024 / 1024, 2)
        return {
            "thought": f"Rotado {angle} grados",
            "display": f"**Rotado {angle} grados**\n- Archivo: {out.name}\n- Tamano: {size_mb} MB",
            "voice": f"Rotado {angle} grados.",
        }

    def _mute(self, params):
        path = self._resolve_input(params.get("path", ""))
        if not path:
            return {"thought": "", "display": "No encontre el video.", "voice": "No encontre el video."}
        out = self._resolve_output(path, params.get("output", ""), "_mute", "mp4")
        if not out:
            return "Ruta de salida invalida."
        code, _, err = _run(["-y", "-i", str(path), "-c:v", "copy", "-an", str(out)])
        if code != 0:
            return {"thought": "Error", "display": f"Error: {err[:300]}", "voice": "Error."}
        size_mb = round(out.stat().st_size / 1024 / 1024, 2)
        return {
            "thought": "Video silenciado",
            "display": f"**Video sin audio**\n- Archivo: {out.name}\n- Tamano: {size_mb} MB",
            "voice": "Video silenciado.",
        }

    def _list(self):
        files = sorted(VIDEO_DIR.glob("*"), key=lambda p: p.stat().st_mtime, reverse=True)
        files = [f for f in files if f.suffix.lower() in VIDEO_EXTS]
        if not files:
            return {"thought": "", "display": "No hay videos.", "voice": "Sin videos."}
        lineas = [f"**Videos recientes ({len(files)}):**"]
        for f in files[:10]:
            size_mb = round(f.stat().st_size / 1024 / 1024, 2)
            lineas.append(f" - {f.name} ({size_mb} MB)")
        return {
            "thought": f"{len(files)} videos",
            "display": "\n".join(lineas),
            "voice": f"Tienes {len(files)} videos.",
        }
