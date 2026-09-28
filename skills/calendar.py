"""Skill de calendario: gestion de eventos locales con export a .ics.

Los eventos se guardan en sandbox/calendar/events.json
Se pueden exportar a formato iCalendar (.ics) para importar en:
- Google Calendar
- Outlook / Microsoft 365
- Apple Calendar
- Thunderbird / Lightning
"""
import json
import re
import uuid
from datetime import datetime, timedelta
from pathlib import Path

from skills.base import Skill
from core import confirmation

ROOT = Path(__file__).resolve().parent.parent
CALENDAR_DIR = ROOT / "sandbox" / "calendar"
CALENDAR_DIR.mkdir(parents=True, exist_ok=True)
EVENTS_FILE = CALENDAR_DIR / "events.json"

# Zona horaria (UTC offset en horas)
TIMEZONE_OFFSET = 0  # Cambiar si quieres zona especifica

# Meses en español
MESES = {
    "enero": 1, "febrero": 2, "marzo": 3, "abril": 4,
    "mayo": 5, "junio": 6, "julio": 7, "agosto": 8,
    "septiembre": 9, "setiembre": 9, "octubre": 10,
    "noviembre": 11, "diciembre": 12,
}

DIAS_SEMANA = {
    "lunes": 0, "martes": 1, "miercoles": 2, "miércoles": 2,
    "jueves": 3, "viernes": 4, "sabado": 5, "sábado": 5, "domingo": 6,
}


def _parse_date(text):
    """Parsea fechas en multiples formatos.

    Devuelve (datetime, es_solo_fecha) o (None, False).
    """
    text = (text or "").strip().lower()
    if not text:
        return None, False

    now = datetime.now()

    # "hoy", "mañana", "pasado mañana"
    if text in ("hoy",):
        return now.replace(hour=9, minute=0, second=0, microsecond=0), True
    if text in ("mañana", "manana"):
        d = now + timedelta(days=1)
        return d.replace(hour=9, minute=0, second=0, microsecond=0), True
    if text in ("pasado mañana", "pasado manana"):
        d = now + timedelta(days=2)
        return d.replace(hour=9, minute=0, second=0, microsecond=0), True

    # "lunes", "martes", etc (proximo dia de esa semana)
    for nombre, dia in DIAS_SEMANA.items():
        if text.startswith(nombre):
            delta = (dia - now.weekday()) % 7
            if delta == 0:
                delta = 7
            d = now + timedelta(days=delta)
            # Por defecto a las 9:00
            return d.replace(hour=9, minute=0, second=0, microsecond=0), True

    # "en 3 dias", "en 2 semanas"
    m = re.match(r"en\s+(\d+)\s+(dias?|días?|semanas?|meses?|horas?)", text)
    if m:
        n = int(m.group(1))
        unidad = m.group(2)
        if "dia" in unidad or "día" in unidad:
            d = now + timedelta(days=n)
        elif "semana" in unidad:
            d = now + timedelta(weeks=n)
        elif "mes" in unidad:
            d = now + timedelta(days=n * 30)
        elif "hora" in unidad:
            d = now + timedelta(hours=n)
            return d, False
        return d.replace(hour=9, minute=0, second=0, microsecond=0), True

    # "2026-09-27" o "2026/09/27"
    m = re.match(r"(\d{4})[-/](\d{1,2})[-/](\d{1,2})(?:\s+(\d{1,2}):(\d{2}))?", text)
    if m:
        year, month, day = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if m.group(4):
            hour, minute = int(m.group(4)), int(m.group(5))
            return datetime(year, month, day, hour, minute), False
        return datetime(year, month, day, 9, 0), True

    # "27/09/2026" o "27-09-2026"
    m = re.match(r"(\d{1,2})[-/](\d{1,2})[-/](\d{2,4})(?:\s+(\d{1,2}):(\d{2}))?", text)
    if m:
        day, month, year = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if year < 100:
            year += 2000
        if m.group(4):
            hour, minute = int(m.group(4)), int(m.group(5))
            return datetime(year, month, day, hour, minute), False
        return datetime(year, month, day, 9, 0), True

    # "27 de septiembre" o "27 de septiembre de 2026"
    m = re.match(r"(\d{1,2})\s+de\s+([a-záéíóúñ]+)(?:\s+de\s+(\d{4}))?", text)
    if m:
        day = int(m.group(1))
        mes_nombre = m.group(2).lower()
        year = int(m.group(3)) if m.group(3) else now.year
        if mes_nombre in MESES:
            return datetime(year, MESES[mes_nombre], day, 9, 0), True

    # "27/09" o "27-09" (asume año actual)
    m = re.match(r"(\d{1,2})[-/](\d{1,2})$", text)
    if m:
        day, month = int(m.group(1)), int(m.group(2))
        return datetime(now.year, month, day, 9, 0), True

    return None, False


def _parse_time(text):
    """Parsea horas: '15:30', '3pm', '15h', 'a las 3 de la tarde'."""
    text = (text or "").strip().lower()
    if not text:
        return None

    # 24h formato "15:30" o "15:30hs"
    m = re.match(r"(\d{1,2}):(\d{2})", text)
    if m:
        return int(m.group(1)), int(m.group(2))

    # "3pm", "3 pm", "3PM"
    m = re.match(r"(\d{1,2})\s*(am|pm)", text)
    if m:
        h = int(m.group(1))
        if "pm" in m.group(2) and h < 12:
            h += 12
        if "am" in m.group(2) and h == 12:
            h = 0
        return h, 0

    # "15h" o "15"
    m = re.match(r"(\d{1,2})(?:h|hs|horas)?$", text)
    if m:
        return int(m.group(1)), 0

    return None


def _parse_duration(text):
    """Parsea duraciones: '1 hora', '30 minutos', '2h', 'media hora'."""
    text = (text or "").strip().lower()
    if not text:
        return 60  # default 1h
    if "media hora" in text:
        return 30
    m = re.match(r"(\d+)\s*(h|hs|hora|horas)", text)
    if m:
        return int(m.group(1)) * 60
    m = re.match(r"(\d+)\s*(m|min|minuto|minutos)", text)
    if m:
        return int(m.group(1))
    return 60


def _format_dt(dt):
    """Formatea datetime como 'Vie 27/09 15:30'."""
    dias = ["Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom"]
    return f"{dias[dt.weekday()]} {dt.day:02d}/{dt.month:02d} {dt.hour:02d}:{dt.minute:02d}"


def _ics_escape(text):
    """Escapa texto para iCalendar."""
    if not text:
        return ""
    return text.replace("\\", "\\\\").replace(",", "\\,").replace(";", "\\;").replace("\n", "\\n")


def _to_ics_dt(dt):
    """Convierte datetime a formato iCalendar (YYYYMMDDTHHMMSS)."""
    return dt.strftime("%Y%m%dT%H%M%S")


class CalendarSkill(Skill):
    name = "calendar"
    description = "Gestiona eventos de calendario (local + export .ics)"

    def run(self, action, params):
        if action == "add":
            return self._add(params)
        if action == "list":
            return self._list(params.get("range", "week"))
        if action == "today":
            return self._list({"range": "today"})
        if action == "tomorrow":
            return self._list({"range": "tomorrow"})
        if action == "week":
            return self._list({"range": "week"})
        if action == "delete":
            return self._delete(params.get("id", ""))
        if action == "export":
            return self._export_ics(params.get("output", ""))
        if action == "find_free":
            return self._find_free_slot(params)
        return f"Accion desconocida en calendar: {action}"

    # ─── HELPERS ──────────────────────────────────────────────────────────

    def _load_events(self):
        if not EVENTS_FILE.exists():
            return []
        try:
            return json.loads(EVENTS_FILE.read_text(encoding="utf-8"))
        except Exception:
            return []

    def _save_events(self, events):
        EVENTS_FILE.write_text(
            json.dumps(events, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    # ─── ADD ──────────────────────────────────────────────────────────────

    def _add(self, params):
        titulo = (params.get("title", "") or "").strip()
        if not titulo:
            return {"thought": "", "display": "Necesito un titulo para el evento.", "voice": "Falta el titulo."}

        fecha_str = params.get("date", "")
        hora_str = params.get("time", "")
        duracion_str = params.get("duration", "")
        ubicacion = (params.get("location", "") or "").strip()
        notas = (params.get("notes", "") or "").strip()

        # Parsear fecha
        dt, solo_fecha = _parse_date(fecha_str)
        if dt is None:
            return {"thought": "", "display": f"No entendi la fecha: '{fecha_str}'. Prueba con 'mañana', '27/09', '2026-09-27'.", "voice": "No entendi la fecha."}

        # Parsear hora
        hora = _parse_time(hora_str)
        if hora:
            dt = dt.replace(hour=hora[0], minute=hora[1], second=0, microsecond=0)
            solo_fecha = False

        # Duracion
        duracion_min = _parse_duration(duracion_str)
        fin = dt + timedelta(minutes=duracion_min)

        event = {
            "id": uuid.uuid4().hex[:8],
            "title": titulo,
            "start": dt.isoformat(),
            "end": fin.isoformat(),
            "all_day": solo_fecha,
            "location": ubicacion,
            "notes": notas,
            "created": datetime.now().isoformat(),
        }

        events = self._load_events()
        events.append(event)
        events.sort(key=lambda e: e["start"])
        self._save_events(events)

        summary = f"Crear evento: {titulo} el {_format_dt(dt)}"
        if not confirmation.require("calendar", "add", summary):
            return "Cancelado."

        return {
            "thought": f"Evento creado: {titulo}",
            "display": (
                f"**Evento creado**\n"
                f"**{titulo}**\n"
                f"Fecha: {_format_dt(dt)}\n"
                f"Duracion: {duracion_min} min\n"
                + (f"Ubicacion: {ubicacion}\n" if ubicacion else "")
                + (f"Notas: {notas}\n" if notas else "")
                + f"ID: {event['id']}"
            ),
            "voice": f"Evento creado: {titulo} el {_format_dt(dt)}.",
        }

    # ─── LIST ─────────────────────────────────────────────────────────────

    def _list(self, rango_input="week"):
        # Acepta tanto un string ("week") como un dict ({"range": "week"})
        if isinstance(rango_input, dict):
            rango = (rango_input.get("range", "week") or "week").lower()
        else:
            rango = (rango_input or "week").lower()
        events = self._load_events()

        if not events:
            return {
                "thought": "",
                "display": "No hay eventos en el calendario.",
                "voice": "No tienes eventos.",
            }

        now = datetime.now()
        hoy_ini = now.replace(hour=0, minute=0, second=0, microsecond=0)

        if rango == "today":
            filtro_ini = hoy_ini
            filtro_fin = hoy_ini + timedelta(days=1)
            titulo = "Eventos de HOY"
        elif rango == "tomorrow":
            filtro_ini = hoy_ini + timedelta(days=1)
            filtro_fin = filtro_ini + timedelta(days=1)
            titulo = "Eventos de MAÑANA"
        elif rango == "week":
            filtro_ini = hoy_ini
            filtro_fin = hoy_ini + timedelta(days=7)
            titulo = "Eventos de los proximos 7 dias"
        elif rango == "month":
            filtro_ini = hoy_ini
            filtro_fin = hoy_ini + timedelta(days=30)
            titulo = "Eventos del proximo mes"
        elif rango == "all":
            filtro_ini = datetime(1970, 1, 1)
            filtro_fin = datetime(2100, 1, 1)
            titulo = "Todos los eventos"
        else:
            # Rango personalizado
            filtro_ini = hoy_ini
            filtro_fin = hoy_ini + timedelta(days=7)
            titulo = "Proximos 7 dias"

        # Filtrar
        filtrados = []
        for e in events:
            try:
                start = datetime.fromisoformat(e["start"])
            except Exception:
                continue
            if filtro_ini <= start < filtro_fin:
                filtrados.append(e)

        if not filtrados:
            return {
                "thought": "",
                "display": f"No hay eventos para {titulo.lower()}.",
                "voice": "No tienes eventos.",
            }

        lineas = [f"**{titulo}** ({len(filtrados)}):"]
        for e in filtrados[:20]:
            try:
                start = datetime.fromisoformat(e["start"])
            except Exception:
                continue
            hora = "todo el dia" if e.get("all_day") else f"{start.hour:02d}:{start.minute:02d}"
            extra = f" ({e.get('location')})" if e.get("location") else ""
            lineas.append(f"  [{e['id']}] {start.day:02d}/{start.month:02d} {hora} - {e['title']}{extra}")

        if len(filtrados) > 20:
            lineas.append(f"  ... y {len(filtrados) - 20} mas")

        return {
            "thought": f"{len(filtrados)} eventos",
            "display": "\n".join(lineas),
            "voice": f"Tienes {len(filtrados)} eventos.",
        }

    # ─── DELETE ───────────────────────────────────────────────────────────

    def _delete(self, event_id):
        if not event_id:
            return {"thought": "", "display": "Necesito el ID del evento.", "voice": "Falta el ID."}

        events = self._load_events()
        inicial = len(events)
        events = [e for e in events if e["id"] != event_id]

        if len(events) == inicial:
            return {"thought": "", "display": f"No encontre evento con ID {event_id}.", "voice": "No encontrado."}

        if not confirmation.require("calendar", "delete", f"Borrar evento {event_id}"):
            return "Cancelado."

        self._save_events(events)
        return {
            "thought": f"Evento {event_id} borrado",
            "display": f"Evento {event_id} eliminado.",
            "voice": "Evento eliminado.",
        }

    # ─── EXPORT ICS ───────────────────────────────────────────────────────

    def _export_ics(self, output_str):
        events = self._load_events()
        if not events:
            return {"thought": "", "display": "No hay eventos para exportar.", "voice": "Sin eventos."}

        # Construir contenido .ics
        lineas = [
            "BEGIN:VCALENDAR",
            "VERSION:2.0",
            "PRODID:-//Senna//Calendar//ES",
            "CALSCALE:GREGORIAN",
            "METHOD:PUBLISH",
            "X-WR-CALNAME:Senna Calendar",
        ]

        for e in events:
            try:
                start = datetime.fromisoformat(e["start"])
                end = datetime.fromisoformat(e["end"])
            except Exception:
                continue

            lineas.append("BEGIN:VEVENT")
            lineas.append(f"UID:{e['id']}@senna.local")
            lineas.append(f"SUMMARY:{_ics_escape(e['title'])}")
            lineas.append(f"DTSTART:{_to_ics_dt(start)}")
            lineas.append(f"DTEND:{_to_ics_dt(end)}")
            if e.get("location"):
                lineas.append(f"LOCATION:{_ics_escape(e['location'])}")
            if e.get("notes"):
                lineas.append(f"DESCRIPTION:{_ics_escape(e['notes'])}")
            lineas.append(f"DTSTAMP:{_to_ics_dt(datetime.now())}")
            lineas.append("END:VEVENT")

        lineas.append("END:VCALENDAR")

        # Path de salida
        if output_str:
            raw = output_str.strip().strip('"').strip("'")
            out = Path(raw)
            if not out.is_absolute():
                out = ROOT / out
            if out.suffix.lower() != ".ics":
                out = out.with_suffix(".ics")
        else:
            ts = int(datetime.now().timestamp())
            out = CALENDAR_DIR / f"senna_calendar_{ts}.ics"

        try:
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text("\r\n".join(lineas), encoding="utf-8")
        except Exception as ex:
            return {"thought": "", "display": f"Error guardando: {ex}", "voice": "Error."}

        size_kb = out.stat().st_size // 1024
        return {
            "thought": f"ICS exportado ({len(events)} eventos)",
            "display": (
                f"**Calendario exportado a .ics**\n"
                f"Archivo: {out}\n"
                f"Eventos: {len(events)}\n"
                f"Tamano: {size_kb} KB\n\n"
                f"Importalo en Google Calendar, Outlook o Apple Calendar."
            ),
            "voice": f"Calendario exportado en {out.name}.",
        }

    # ─── FIND FREE SLOT ───────────────────────────────────────────────────

    def _find_free_slot(self, params):
        fecha_str = params.get("date", "")
        duracion_min = _parse_duration(params.get("duration", "1 hora"))

        dt, _ = _parse_date(fecha_str)
        if dt is None:
            return {"thought": "", "display": "Necesito una fecha (ej: 'mañana', '27/09').", "voice": "Falta la fecha."}

        events = self._load_events()
        dia_ini = dt.replace(hour=8, minute=0, second=0, microsecond=0)
        dia_fin = dt.replace(hour=20, minute=0, second=0, microsecond=0)

        # Recoger eventos de ese dia
        ocupados = []
        for e in events:
            try:
                s = datetime.fromisoformat(e["start"])
                en = datetime.fromisoformat(e["end"])
            except Exception:
                continue
            if s.date() == dt.date():
                ocupados.append((s, en))
        ocupados.sort()

        # Buscar huecos
        cursor = dia_ini
        huecos = []
        for s, en in ocupados:
            if s > cursor and (s - cursor).total_seconds() >= duracion_min * 60:
                huecos.append((cursor, s))
            if en > cursor:
                cursor = en
        if cursor < dia_fin and (dia_fin - cursor).total_seconds() >= duracion_min * 60:
            huecos.append((cursor, dia_fin))

        if not huecos:
            return {
                "thought": "",
                "display": f"No hay hueco de {duracion_min} min el {dt.day:02d}/{dt.month:02d}.",
                "voice": "No hay hueco disponible.",
            }

        lineas = [f"**Huecos libres el {dt.day:02d}/{dt.month:02d}** ({duracion_min} min):"]
        for i, (s, e) in enumerate(huecos[:10], 1):
            lineas.append(f"  {i}. {s.hour:02d}:{s.minute:02d} - {e.hour:02d}:{e.minute:02d}")

        return {
            "thought": f"{len(huecos)} huecos libres",
            "display": "\n".join(lineas),
            "voice": f"Encontre {len(huecos)} huecos libres.",
        }
