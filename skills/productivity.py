import json
import re
from datetime import datetime
from pathlib import Path
from skills.base import Skill


NOTES_FILE = Path(__file__).resolve().parent.parent / "memory" / "notes.json"


class ProductivitySkill(Skill):
    name = "productivity"
    description = "Notas rapidas, recordatorios"

    def __init__(self):
        NOTES_FILE.parent.mkdir(parents=True, exist_ok=True)
        if not NOTES_FILE.exists():
            NOTES_FILE.write_text("[]", encoding="utf-8")

    def run(self, action, params):
        if action == "save_note":
            return self._save_note(params.get("text", ""))
        if action == "read_notes":
            return self._read_notes()
        if action == "clear_notes":
            return self._clear_notes()
        return f"Accion desconocida: {action}"

    def _load(self):
        try:
            return json.loads(NOTES_FILE.read_text(encoding="utf-8"))
        except Exception:
            return []

    def _save(self, notes):
        NOTES_FILE.write_text(
            json.dumps(notes, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def _save_note(self, text):
        text = (text or "").strip()
        if not text:
            return "No me dijiste que anotar."
        notes = self._load()
        notes.append({
            "text": text,
            "date": datetime.now().strftime("%Y-%m-%d %H:%M"),
        })
        self._save(notes)
        return f"Anotado: {text}"

    def _read_notes(self):
        notes = self._load()
        if not notes:
            return "No tienes notas guardadas."
        lines = [f"Tienes {len(notes)} notas:"]
        for i, n in enumerate(notes[-10:], 1):
            lines.append(f"{i}. [{n['date']}] {n['text']}")
        return "\n".join(lines)

    def _clear_notes(self):
        self._save([])
        return "Notas borradas."