"""RAG: indice y consulta de documentos (PDF, DOCX, TXT, MD, codigo)."""
import json
from pathlib import Path

import chromadb
import ollama

from core.config_loader import CONFIG
from core.model_config import get_model

ROOT = Path(__file__).resolve().parent.parent
MEMORY_DIR = ROOT / "memory"
RAG_DIR = MEMORY_DIR / "rag_db"
DOCS_REGISTRY = MEMORY_DIR / "rag_documents.json"

EMBED_MODEL = "nomic-embed-text"

SUPPORTED_EXT = {".pdf", ".txt", ".md", ".docx", ".py", ".json", ".yaml", ".yml"}

# Carpetas que NUNCA se indexan (pesadas o irrelevantes)
EXCLUDE_DIRS = {
    "venv", ".venv", "env", ".env",
    "node_modules", "__pycache__", ".git", ".svn",
    "dist", "build", "target", "out", "bin", "obj",
    "site-packages", ".cache", ".pytest_cache", ".mypy_cache",
    "Library", "Temp", "tmp", "$RECYCLE.BIN", "System Volume Information",
}

# Tamaño maximo de archivo individual (MB) — evita archivos gigantes
MAX_FILE_MB = 50


def _read_pdf(path):
    from pypdf import PdfReader
    reader = PdfReader(str(path))
    return "\n".join(page.extract_text() or "" for page in reader.pages)


def _read_docx(path):
    from docx import Document
    doc = Document(str(path))
    return "\n".join(p.text for p in doc.paragraphs)


def _read_text(path):
    for enc in ("utf-8", "latin-1"):
        try:
            return path.read_text(encoding=enc)
        except UnicodeDecodeError:
            continue
    return ""


def read_file(path):
    ext = path.suffix.lower()
    if ext == ".pdf":
        return _read_pdf(path)
    if ext == ".docx":
        return _read_docx(path)
    if ext in {".txt", ".md", ".py", ".json", ".yaml", ".yml"}:
        return _read_text(path)
    return ""


def chunk_text(text, chunk_size=800, overlap=150):
    """Divide por parrafos agrupando hasta chunk_size con solapamiento."""
    text = text.strip()
    if not text:
        return []

    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    chunks = []
    current = ""

    for p in paragraphs:
        if len(current) + len(p) + 2 <= chunk_size:
            current = (current + "\n\n" + p).strip() if current else p
        else:
            if current:
                chunks.append(current)
            if len(p) > chunk_size:
                start = 0
                while start < len(p):
                    end = min(start + chunk_size, len(p))
                    chunks.append(p[start:end])
                    if end >= len(p):
                        break
                    start = end - overlap
                current = ""
            else:
                current = p

    if current:
        chunks.append(current)

    return chunks


class RAG:
    def __init__(self):
        RAG_DIR.mkdir(parents=True, exist_ok=True)

        self.client = chromadb.PersistentClient(path=str(RAG_DIR))
        self.collection = self.client.get_or_create_collection(
            name="documents",
            metadata={"hnsw:space": "cosine"},
        )

        if not DOCS_REGISTRY.exists():
            DOCS_REGISTRY.write_text("{}", encoding="utf-8")

    def _embed(self, texts):
        vectors = []
        for t in texts:
            resp = ollama.embeddings(model=EMBED_MODEL, prompt=t)
            vectors.append(resp["embedding"])
        return vectors

    def _load_registry(self):
        try:
            return json.loads(DOCS_REGISTRY.read_text(encoding="utf-8"))
        except Exception:
            return {}

    def _save_registry(self, data):
        DOCS_REGISTRY.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def index_file(self, path):
        path = Path(path).resolve()
        if not path.exists():
            return f"No existe el archivo: {path}"
        if path.suffix.lower() not in SUPPORTED_EXT:
            return f"Formato no soportado: {path.suffix}"

        text = read_file(path)
        if not text.strip():
            return f"No se pudo extraer texto de {path.name}"

        chunks = chunk_text(text)
        if not chunks:
            return f"Sin contenido util en {path.name}"

        doc_key = str(path)
        registry = self._load_registry()

        if doc_key in registry:
            self.collection.delete(where={"source": doc_key})

        ids = [f"chunk_{i}_{hash(doc_key) & 0xffffffff}" for i in range(len(chunks))]
        metadatas = [
            {"source": doc_key, "name": path.name, "chunk": i}
            for i in range(len(chunks))
        ]

        try:
            embeddings = self._embed(chunks)
        except Exception as e:
            return f"Error generando embeddings: {e}"

        self.collection.add(
            documents=chunks,
            embeddings=embeddings,
            metadatas=metadatas,
            ids=ids,
        )

        try:
            mtime = path.stat().st_mtime
            size_kb = round(path.stat().st_size / 1024, 1)
        except Exception:
            mtime = 0
            size_kb = 0

        registry[doc_key] = {
            "name": path.name,
            "chunks": len(chunks),
            "mtime": mtime,
            "size_kb": size_kb,
        }
        self._save_registry(registry)

        return f"Indexado {path.name}: {len(chunks)} fragmentos."

    def _collect_files(self, folder, recursive=True, extensions=None, max_size_mb=None):
        """Recolecta archivos validos saltando carpetas excluidas."""
        folder = Path(folder).resolve()
        exts = set(extensions) if extensions else SUPPORTED_EXT
        max_bytes = (max_size_mb or MAX_FILE_MB) * 1024 * 1024

        valid = []
        if recursive:
            for root, dirs, files in folder.walk():
                # Filtrar dirs in-place (asi os.walk/path.walk no entra en ellos)
                dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS and not d.startswith(".")]
                for f in files:
                    fp = root / f
                    if fp.suffix.lower() not in exts:
                        continue
                    try:
                        if fp.stat().st_size > max_bytes:
                            continue
                    except Exception:
                        continue
                    valid.append(fp)
        else:
            for fp in folder.iterdir():
                if not fp.is_file():
                    continue
                if fp.suffix.lower() not in exts:
                    continue
                try:
                    if fp.stat().st_size > max_bytes:
                        continue
                except Exception:
                    continue
                valid.append(fp)

        return valid

    def index_folder(self, folder, recursive=True, extensions=None, max_size_mb=None, reindex_only_changed=False):
        """Indexa una carpeta. Filtra carpetas pesadas (venv, node_modules, etc.).

        Args:
            folder: ruta de la carpeta
            recursive: si True, entra en subcarpetas
            extensions: lista de extensiones (ej. ['.pdf', '.docx']). Si None, usa todas
            max_size_mb: tamano maximo de archivo. Si None, usa MAX_FILE_MB (50)
            reindex_only_changed: si True, solo re-indexa archivos nuevos o modificados
        """
        folder = Path(folder).resolve()
        if not folder.exists() or not folder.is_dir():
            return f"No existe la carpeta: {folder}"

        files = self._collect_files(folder, recursive=recursive, extensions=extensions, max_size_mb=max_size_mb)

        if not files:
            return f"No hay archivos compatibles en {folder}"

        registry = self._load_registry()
        total_chunks = 0
        indexed = 0
        skipped = 0
        failed = 0

        print(f"[RAG] Indexando {len(files)} archivos de {folder.name}...")

        for i, f in enumerate(files, 1):
            doc_key = str(f)

            # Si reindex_only_changed, comprobar mtime
            if reindex_only_changed and doc_key in registry:
                try:
                    mtime_actual = f.stat().st_mtime
                    mtime_indexado = registry[doc_key].get("mtime", 0)
                    if mtime_actual <= mtime_indexado:
                        skipped += 1
                        continue
                except Exception:
                    pass

            if i % 10 == 0:
                print(f"[RAG] {i}/{len(files)}...")

            try:
                result = self.index_file(f)
                if result.startswith("Indexado"):
                    indexed += 1
                    try:
                        n = int(result.split(":")[1].split()[0])
                        total_chunks += n
                    except Exception:
                        pass
                elif result.startswith("Sin contenido") or result.startswith("No se pudo"):
                    failed += 1
            except Exception as e:
                failed += 1
                print(f"[RAG] Error con {f.name}: {e}")

        msg = f"Indexados {indexed} archivos ({total_chunks} fragmentos) de {folder.name}."
        if skipped:
            msg += f" Saltados {skipped} (sin cambios)."
        if failed:
            msg += f" Fallaron {failed}."
        return msg

    def ask(self, query, n_results=4):
        if not query.strip():
            return {"answer": "Pregunta vacia.", "sources": []}

        count = self.collection.count()
        if count == 0:
            return {"answer": "No hay documentos indexados todavia.", "sources": []}

        try:
            query_emb = self._embed([query])[0]
        except Exception as e:
            return {"answer": f"Error generando embedding: {e}", "sources": []}

        results = self.collection.query(
            query_embeddings=[query_emb],
            n_results=min(n_results, count),
        )

        docs = results.get("documents", [[]])[0]
        metas = results.get("metadatas", [[]])[0]
        dists = results.get("distances", [[]])[0]

        if not docs:
            return {"answer": "No encontre nada relevante.", "sources": []}

        relevant = [
            (d, m) for d, m, dist in zip(docs, metas, dists) if dist < 0.75
        ]
        if not relevant:
            return {"answer": "No encontre nada suficientemente relevante.", "sources": []}

        # Construir contexto con MARCADORES de fuente numerados
        context_parts = []
        sources = []
        for i, (d, m) in enumerate(relevant, 1):
            name = m.get("name", "?")
            chunk_idx = m.get("chunk", 0)
            marker = f"[FUENTE {i}]"
            context_parts.append(f"{marker} {name} (fragmento {chunk_idx})\n{d}")
            sources.append({
                "index": i,
                "name": name,
                "chunk": chunk_idx,
                "source": m.get("source", ""),
            })

        context = "\n\n---\n\n".join(context_parts)

        prompt = (
            "Eres un asistente que responde basandose en el contexto proporcionado.\n\n"
            "REGLAS:\n"
            "1. Puedes INFERIR y SINTETIZAR a partir de la informacion del contexto.\n"
            "2. NO inventes datos concretos (fechas, nombres, empresas, cifras).\n"
            "3. Si te piden una lista (ej: '5 fortalezas'), genera una lista coherente "
            "basada en lo que hay en el contexto.\n"
            "4. Si el contexto es TOTALMENTE irrelevante a la pregunta, di: "
            "'No tengo informacion sobre eso en los documentos'.\n"
            "5. Cuando uses informacion de una fuente, cita el marcador asi: [FUENTE 1].\n"
            "6. Responde en espanol, claro y directo. Usa bullets si es una lista.\n\n"
            f"Contexto:\n{context}\n\n"
            f"Pregunta: {query}\n\n"
            "Respuesta:"
        )

        try:
            resp = ollama.chat(
                model=get_model("agent"),
                messages=[{"role": "user", "content": prompt}],
                options={"temperature": 0.2},
                stream=False,
            )
            answer = resp["message"]["content"].strip()
        except Exception as e:
            answer = f"Error al consultar el modelo: {e}"

        # Devolver fuentes como strings bonitos (compatibilidad) + detalle
        sources_str = [f"{s['name']} (fragmento {s['chunk']})" for s in sources]
        return {
            "answer": answer,
            "sources": sources_str,
            "sources_detail": sources,
        }

    def get_stats(self):
        """Devuelve estadisticas del indice."""
        registry = self._load_registry()
        try:
            total_chunks = self.collection.count()
        except Exception:
            total_chunks = 0

        total_docs = len(registry)

        # Tamano del indice en disco
        total_size = 0
        if RAG_DIR.exists():
            for f in RAG_DIR.rglob("*"):
                if f.is_file():
                    total_size += f.stat().st_size
        size_mb = round(total_size / 1024 / 1024, 2)

        return {
            "total_documents": total_docs,
            "total_chunks": total_chunks,
            "index_size_mb": size_mb,
            "rag_dir": str(RAG_DIR),
        }

    def list_documents_detailed(self):
        """Lista de documentos con detalles (fecha, tamano, chunks)."""
        registry = self._load_registry()
        if not registry:
            return "No hay documentos indexados."

        lineas = [f"Documentos indexados ({len(registry)}):"]
        for k, v in registry.items():
            name = v.get("name", "?")
            chunks = v.get("chunks", 0)
            mtime = v.get("mtime", 0)
            from datetime import datetime as _dt
            fecha = _dt.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M") if mtime else "?"
            lineas.append(f"  - {name} ({chunks} fragmentos, {fecha})")

        stats = self.get_stats()
        lineas.append("")
        lineas.append(f"Total: {stats['total_documents']} docs, {stats['total_chunks']} fragmentos, {stats['index_size_mb']} MB")

        return "\n".join(lineas)

    def list_documents(self):
        registry = self._load_registry()
        if not registry:
            return "No hay documentos indexados."
        lines = [f"- {v['name']} ({v['chunks']} fragmentos)" for v in registry.values()]
        return "\n".join(lines)

    def delete_document(self, name):
        registry = self._load_registry()
        to_delete = [k for k, v in registry.items() if v["name"] == name or k.endswith(name)]
        if not to_delete:
            return f"No encontre documento: {name}"
        for k in to_delete:
            self.collection.delete(where={"source": k})
            del registry[k]
        self._save_registry(registry)
        return f"Eliminado: {name}"