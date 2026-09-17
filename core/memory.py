import json
from pathlib import Path
from datetime import datetime

import chromadb
from chromadb.config import Settings

ROOT = Path(__file__).resolve().parent.parent
MEMORY_DIR = ROOT / "memory"
CHROMA_DIR = MEMORY_DIR / "chroma_db"
PREFS_FILE = MEMORY_DIR / "preferences.json"


class Memory:
    def __init__(self):
        MEMORY_DIR.mkdir(parents=True, exist_ok=True)
        CHROMA_DIR.mkdir(parents=True, exist_ok=True)

        self.client = chromadb.PersistentClient(path=str(CHROMA_DIR))
        self.collection = self.client.get_or_create_collection(
            name="conversations",
            metadata={"hnsw:space": "cosine"},
        )
        self.session_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.turno = 0

        # Preferencias (hechos sobre el usuario)
        if not PREFS_FILE.exists():
            PREFS_FILE.write_text("{}", encoding="utf-8")

    # ─── GUARDAR ────────────────────────────────────────────────────────────

    def save_message(self, role, content):
        """Guarda un mensaje en la coleccion de conversaciones."""
        self.turno += 1
        doc_id = f"{self.session_id}_{self.turno}_{role}"
        try:
            self.collection.add(
                documents=[content],
                metadatas=[{
                    "role": role,
                    "session": self.session_id,
                    "turno": self.turno,
                    "timestamp": datetime.now().isoformat(),
                }],
                ids=[doc_id],
            )
        except Exception as e:
            print(f"[MEMORY ERROR] {e}")

    def save_preference(self, key, value):
        """Guarda una preferencia del usuario (hecho permanente)."""
        try:
            prefs = json.loads(PREFS_FILE.read_text(encoding="utf-8"))
        except Exception:
            prefs = {}
        prefs[key] = value
        PREFS_FILE.write_text(
            json.dumps(prefs, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    # ─── RECUPERAR ──────────────────────────────────────────────────────────

    def search(self, query, n_results=3, exclude_current_session=True):
        """Busca mensajes relevantes al query."""
        try:
            where = {"session": {"$ne": self.session_id}} if exclude_current_session else None
            results = self.collection.query(
                query_texts=[query],
                n_results=n_results,
                where=where,
            )
            docs = results.get("documents", [[]])[0]
            metas = results.get("metadatas", [[]])[0]
            return list(zip(docs, metas))
        except Exception as e:
            print(f"[MEMORY SEARCH ERROR] {e}")
            return []

    def get_preferences(self):
        try:
            return json.loads(PREFS_FILE.read_text(encoding="utf-8"))
        except Exception:
            return {}

    # ─── CONTEXTO PARA EL LLM ───────────────────────────────────────────────

    def build_context(self, query, n_results=3):
        """Devuelve un string con contexto relevante para inyectar al prompt."""
        parts = []

        # Preferencias
        prefs = self.get_preferences()
        if prefs:
            pref_lines = [f"- {k}: {v}" for k, v in prefs.items()]
            parts.append("Cosas que se del usuario:\n" + "\n".join(pref_lines))

        # Conversaciones pasadas relevantes
        memories = self.search(query, n_results=n_results)
        if memories:
            mem_lines = []
            for doc, meta in memories:
                when = meta.get("timestamp", "")[:10]
                role = meta.get("role", "?")
                mem_lines.append(f"- [{when}] {role}: {doc}")
            parts.append("Conversaciones pasadas relevantes:\n" + "\n".join(mem_lines))

        if not parts:
            return ""
        return "\n\n".join(parts)