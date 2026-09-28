"""Skill de audio: transcripcion con faster-whisper (OpenAI Whisper optimizado).

Acciones:
- transcribe      -> transcribir a .txt
- transcribe_srt  -> transcribir a .srt (con marcas de tiempo)
- to_word         -> transcribir y guardar en Word
- batch           -> transcribir carpeta entera
- list            -> listar transcripciones
- info            -> detalles del audio (duracion, formato)
"""
import json
import re
import time
from datetime import datetime
from pathlib import Path

from skills.base import Skill
from core import confirmation

ROOT = Path(__file__).resolve().parent.parent
AUDIO_DIR = ROOT / "sandbox" / "audio"
TRANSCRIPTS_DIR = ROOT / "sandbox" / "transcripts"
AUDIO_DIR.mkdir(parents=True, exist_ok=True)
TRANSCRIPTS_DIR.mkdir(parents=True, exist_ok=True)

# Formatos soportados (via PyAV)
AUDIO_EXTS = {".mp3", ".wav", ".m4a", ".ogg", ".flac", ".webm", ".aac", ".wma", ".opus", ".mp4"}

# Modelos whisper disponibles
WHISPER_MODELS = {
    "rapido":     "tiny",
    "normal":     "base",
    "buena":      "small",
    "excelente":  "medium",   # default
    "maxima":     "large-v3",
}

# Modelo por defecto
DEFAULT_MODEL = "small"   # Ya esta en cache, es rapido y buena calidad


def _slugify(text, maxlen=40):
    s = text.lower()
    for k, v in {"á":"a","é":"e","í":"i","ó":"o","ú":"u","ñ":"n","ü":"u"}.items():
        s = s.replace(k, v)
    s = re.sub(r'[^a-z0-9]+', '_', s)[:maxlen].strip("_")
    return s or "audio"


def _format_duration(seconds):
    """Formatea segundos como HH:MM:SS."""
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    if h > 0:
        return f"{h:02d}:{m:02d}:{s:02d}"
    return f"{m:02d}:{s:02d}"


def _format_srt_time(seconds):
    """Formatea segundos como HH:MM:SS,mmm para SRT."""
    ms = int((seconds % 1) * 1000)
    s = int(seconds)
    h = s // 3600
    m = (s % 3600) // 60
    sec = s % 60
    return f"{h:02d}:{m:02d}:{sec:02d},{ms:03d}"


class AudioSkill(Skill):
    name = "audio"
    description = "Transcribe audio a texto con Whisper (local, privado)"

    def __init__(self):
        self._models_cache = {}

    def run(self, action, params):
        if action == "transcribe":
            return self._transcribe(
                params.get("path", ""),
                params.get("model", DEFAULT_MODEL),
                params.get("language", ""),
            )
        if action == "transcribe_srt":
            return self._transcribe_srt(
                params.get("path", ""),
                params.get("model", DEFAULT_MODEL),
                params.get("language", ""),
            )
        if action == "to_word":
            return self._to_word(
                params.get("path", ""),
                params.get("model", DEFAULT_MODEL),
                params.get("language", ""),
            )
        if action == "batch":
            return self._batch(
                params.get("path", ""),
                params.get("model", DEFAULT_MODEL),
                params.get("language", ""),
            )
        if action == "list":
            return self._list()
        if action == "info":
            return self._info(params.get("path", ""))
        return f"Accion desconocida en audio: {action}"

    # ─── HELPERS ──────────────────────────────────────────────────────────

    def _resolve_input(self, path_str):
        """Resuelve el path del audio."""
        if not path_str:
            # Coger el ultimo audio de sandbox/audio/
            files = sorted(AUDIO_DIR.glob("*"), key=lambda p: p.stat().st_mtime, reverse=True)
            files = [f for f in files if f.suffix.lower() in AUDIO_EXTS]
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

    def _resolve_output(self, input_path, suffix, ext):
        """Devuelve el path de salida en sandbox/transcripts/."""
        out = TRANSCRIPTS_DIR / f"{input_path.stem}{suffix}.{ext}"
        return out

    def _get_model(self, model_name):
        """Carga un modelo whisper (con cache)."""
        from faster_whisper import WhisperModel

        # Resolver alias
        real_name = WHISPER_MODELS.get(model_name.lower(), model_name)

        if real_name not in self._models_cache:
            print(f"[AUDIO] Cargando modelo whisper '{real_name}' (primera vez descarga)...")
            t0 = time.time()
            # Intenta usar GPU (CUDA), si falla usa CPU
            try:
                model = WhisperModel(real_name, device="cuda", compute_type="float16")
                print(f"[AUDIO] Modelo cargado en GPU en {time.time()-t0:.1f}s")
            except Exception as e:
                print(f"[AUDIO] GPU no disponible ({e}), usando CPU...")
                model = WhisperModel(real_name, device="cpu", compute_type="int8")
                print(f"[AUDIO] Modelo cargado en CPU en {time.time()-t0:.1f}s")
            self._models_cache[real_name] = model

        return self._models_cache[real_name]

    # ─── TRANSCRIBE ───────────────────────────────────────────────────────

    def _transcribe(self, path_str, model_name, language):
        path = self._resolve_input(path_str)
        if not path:
            return {"thought": "", "display": "No encontre el audio.", "voice": "No encontre el audio."}

        if path.suffix.lower() not in AUDIO_EXTS:
            return f"Formato no soportado: {path.suffix}. Usa: {', '.join(AUDIO_EXTS)}"

        out = self._resolve_output(path, "", "txt")
        if out.exists():
            if not confirmation.require("audio", "overwrite", f"Sobrescribir {out.name}"):
                return "Cancelado."

        print(f"[AUDIO] Transcribiendo {path.name} con modelo '{model_name}'...")
        try:
            model = self._get_model(model_name)
        except Exception as e:
            return {"thought": "Error cargando modelo", "display": f"Error: {e}", "voice": "Error."}

        try:
            t0 = time.time()
            segments, info = model.transcribe(
                str(path),
                language=language if language else None,
                beam_size=5,
                vad_filter=True,  # Filtrar silencios
            )

            # Recolectar texto
            texto_partes = []
            duracion_audio = info.duration
            idioma_detectado = info.language
            prob_idioma = info.language_probability

            for seg in segments:
                texto_partes.append(seg.text.strip())

            texto = " ".join(texto_partes)
            elapsed = time.time() - t0

            # Guardar
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(texto, encoding="utf-8")

        except Exception as e:
            return {"thought": "Error transcribiendo", "display": f"Error: {e}", "voice": "Error transcribiendo."}

        size_kb = out.stat().st_size // 1024
        preview = texto[:300] + ("..." if len(texto) > 300 else "")

        return {
            "thought": f"Transcrito en {elapsed:.1f}s ({len(texto)} chars, idioma: {idioma_detectado})",
            "display": (
                f"**Transcripcion completada**\n"
                f"Archivo: {out.name}\n"
                f"Duracion del audio: {_format_duration(duracion_audio)}\n"
                f"Idioma: {idioma_detectado} ({prob_idioma:.0%})\n"
                f"Caracteres: {len(texto)}\n"
                f"Tiempo: {elapsed:.1f}s\n\n"
                f"**Vista previa:**\n{preview}"
            ),
            "voice": f"Listo. Transcripcion guardada en {out.name}.",
        }

    # ─── TRANSCRIBE SRT ───────────────────────────────────────────────────

    def _transcribe_srt(self, path_str, model_name, language):
        path = self._resolve_input(path_str)
        if not path:
            return "No encontre el audio."

        if path.suffix.lower() not in AUDIO_EXTS:
            return f"Formato no soportado: {path.suffix}"

        out = self._resolve_output(path, "", "srt")

        print(f"[AUDIO] Transcribiendo {path.name} a SRT con '{model_name}'...")
        try:
            model = self._get_model(model_name)
        except Exception as e:
            return f"Error cargando modelo: {e}"

        try:
            t0 = time.time()
            segments, info = model.transcribe(
                str(path),
                language=language if language else None,
                beam_size=5,
                vad_filter=True,
            )

            # Escribir SRT
            srt_lines = []
            for i, seg in enumerate(segments, 1):
                start = _format_srt_time(seg.start)
                end = _format_srt_time(seg.end)
                text = seg.text.strip()
                srt_lines.append(f"{i}")
                srt_lines.append(f"{start} --> {end}")
                srt_lines.append(text)
                srt_lines.append("")

            srt_content = "\n".join(srt_lines)
            elapsed = time.time() - t0

            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(srt_content, encoding="utf-8")

        except Exception as e:
            return f"Error transcribiendo: {e}"

        size_kb = out.stat().st_size // 1024
        n_segmentos = len([l for l in srt_lines if l.isdigit() or l == "0"])

        return {
            "thought": f"SRT generado en {elapsed:.1f}s ({n_segmentos} segmentos)",
            "display": (
                f"**Subtitulos SRT generados**\n"
                f"Archivo: {out.name}\n"
                f"Segmentos: {n_segmentos}\n"
                f"Duracion: {_format_duration(info.duration)}\n"
                f"Tiempo: {elapsed:.1f}s"
            ),
            "voice": f"Listo. Subtitulos guardados en {out.name}.",
        }

    # ─── TO WORD ──────────────────────────────────────────────────────────

    def _to_word(self, path_str, model_name, language):
        path = self._resolve_input(path_str)
        if not path:
            return "No encontre el audio."

        print(f"[AUDIO] Transcribiendo a Word...")
        try:
            model = self._get_model(model_name)
        except Exception as e:
            return f"Error cargando modelo: {e}"

        try:
            t0 = time.time()
            segments, info = model.transcribe(
                str(path),
                language=language if language else None,
                beam_size=5,
                vad_filter=True,
            )

            # Recolectar segmentos con timestamps
            segmentos = []
            for seg in segments:
                segmentos.append({
                    "start": seg.start,
                    "end": seg.end,
                    "text": seg.text.strip(),
                })

            elapsed = time.time() - t0
        except Exception as e:
            return f"Error transcribiendo: {e}"

        # Crear Word
        try:
            from docx import Document
            from docx.shared import Pt, RGBColor

            doc = Document()
            style = doc.styles["Normal"]
            style.font.name = "Calibri"
            style.font.size = Pt(11)

            # Titulo
            titulo = f"Transcripcion: {path.stem}"
            doc.add_heading(titulo, level=0)

            # Metadata
            meta = doc.add_paragraph()
            run = meta.add_run(f"Archivo original: {path.name}\n")
            run.italic = True
            run.font.size = Pt(9)
            run.font.color.rgb = RGBColor(100, 100, 100)
            run2 = meta.add_run(f"Duracion: {_format_duration(info.duration)}\n")
            run2.italic = True
            run2.font.size = Pt(9)
            run2.font.color.rgb = RGBColor(100, 100, 100)
            run3 = meta.add_run(f"Idioma: {info.language} ({info.language_probability:.0%})\n")
            run3.italic = True
            run3.font.size = Pt(9)
            run3.font.color.rgb = RGBColor(100, 100, 100)
            run4 = meta.add_run(f"Modelo: {WHISPER_MODELS.get(model_name, model_name)}\n")
            run4.italic = True
            run4.font.size = Pt(9)
            run4.font.color.rgb = RGBColor(100, 100, 100)

            doc.add_paragraph("")

            # Transcripcion con timestamps
            doc.add_heading("Transcripcion", level=1)
            for seg in segmentos:
                p = doc.add_paragraph()
                time_run = p.add_run(f"[{_format_duration(seg['start'])}] ")
                time_run.bold = True
                time_run.font.size = Pt(9)
                time_run.font.color.rgb = RGBColor(80, 120, 200)
                p.add_run(seg["text"])

            # Guardar
            office_dir = ROOT / "sandbox" / "office"
            office_dir.mkdir(parents=True, exist_ok=True)
            ts = int(datetime.now().timestamp())
            out_docx = office_dir / f"transcripcion_{_slugify(path.stem)}_{ts}.docx"
            doc.save(str(out_docx))

        except Exception as e:
            return f"Error creando Word: {e}"

        size_kb = out_docx.stat().st_size // 1024
        return {
            "thought": f"Word creado con {len(segmentos)} segmentos",
            "display": (
                f"**Transcripcion en Word**\n"
                f"Archivo: {out_docx.name}\n"
                f"Segmentos: {len(segmentos)}\n"
                f"Duracion: {_format_duration(info.duration)}\n"
                f"Tiempo: {elapsed:.1f}s\n"
                f"Tamano: {size_kb} KB"
            ),
            "voice": f"Listo. Word guardado en {out_docx.name}.",
        }

    # ─── BATCH ────────────────────────────────────────────────────────────

    def _batch(self, path_str, model_name, language):
        folder = Path(path_str.strip().strip('"').strip("'")) if path_str else AUDIO_DIR
        if not folder.is_absolute():
            folder = ROOT / folder
        if not folder.exists():
            return f"No encontre la carpeta: {folder}"

        audios = [f for f in folder.iterdir() if f.suffix.lower() in AUDIO_EXTS]
        if not audios:
            return f"No hay audios en {folder}"

        summary = f"Transcribir {len(audios)} audios de {folder.name}"
        if not confirmation.require("audio", "batch", summary):
            return "Cancelado."

        exitos = 0
        fallos = 0
        print(f"[AUDIO] Transcribiendo {len(audios)} audios...")

        for i, audio in enumerate(audios, 1):
            print(f"[AUDIO] {i}/{len(audios)}: {audio.name}")
            try:
                r = self._transcribe(str(audio), model_name, language)
                if isinstance(r, dict):
                    exitos += 1
                else:
                    fallos += 1
            except Exception as e:
                print(f"[AUDIO] Error: {e}")
                fallos += 1

        return {
            "thought": f"Batch: {exitos}/{len(audios)} exitos",
            "display": f"**Batch completado**\n{exitos} transcripciones exitosas\n{fallos} fallos\n\nGuardadas en: {TRANSCRIPTS_DIR}",
            "voice": f"Listo. Transcribi {exitos} audios.",
        }

    # ─── LIST ─────────────────────────────────────────────────────────────

    def _list(self):
        if not TRANSCRIPTS_DIR.exists():
            return "No hay transcripciones todavia."

        files = sorted(TRANSCRIPTS_DIR.glob("*.txt"), key=lambda p: p.stat().st_mtime, reverse=True)
        srt_files = sorted(TRANSCRIPTS_DIR.glob("*.srt"), key=lambda p: p.stat().st_mtime, reverse=True)

        if not files and not srt_files:
            return "No hay transcripciones todavia."

        lineas = []
        if files:
            lineas.append(f"**Transcripciones TXT ({len(files)}):**")
            for f in files[:10]:
                size_kb = f.stat().st_size // 1024
                fecha = datetime.fromtimestamp(f.stat().st_mtime).strftime("%Y-%m-%d %H:%M")
                lineas.append(f"  - {f.name} ({size_kb} KB, {fecha})")
        if srt_files:
            lineas.append("")
            lineas.append(f"**Subtitulos SRT ({len(srt_files)}):**")
            for f in srt_files[:10]:
                size_kb = f.stat().st_size // 1024
                fecha = datetime.fromtimestamp(f.stat().st_mtime).strftime("%Y-%m-%d %H:%M")
                lineas.append(f"  - {f.name} ({size_kb} KB, {fecha})")

        return {
            "thought": f"{len(files)} TXT + {len(srt_files)} SRT",
            "display": "\n".join(lineas),
            "voice": f"Tienes {len(files)} transcripciones.",
        }

    # ─── INFO ─────────────────────────────────────────────────────────────

    def _info(self, path_str):
        path = self._resolve_input(path_str)
        if not path:
            return "No encontre el audio."

        try:
            import av
            container = av.open(str(path))
            duration = container.duration / av.time_base if container.duration else 0
            streams_info = []
            for s in container.streams:
                if s.type == "audio":
                    streams_info.append({
                        "codec": s.codec_context.name,
                        "channels": s.codec_context.channels,
                        "sample_rate": s.codec_context.sample_rate,
                    })
            container.close()

            size_kb = path.stat().st_size // 1024
            lineas = [
                f"**Archivo:** {path.name}",
                f"**Tamano:** {size_kb} KB",
                f"**Duracion:** {_format_duration(duration)}",
                f"**Formato:** {path.suffix}",
            ]
            if streams_info:
                s = streams_info[0]
                lineas.append(f"**Codec:** {s['codec']}")
                lineas.append(f"**Canales:** {s['channels']}")
                lineas.append(f"**Sample rate:** {s['sample_rate']} Hz")

            return {
                "thought": f"Info: {_format_duration(duration)}",
                "display": "\n".join(lineas),
                "voice": f"El audio dura {_format_duration(duration)}.",
            }
        except Exception as e:
            return f"Error leyendo info: {e}"
