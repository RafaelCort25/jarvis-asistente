"""RAG: indice y consulta de documentos (PDF, DOCX, TXT, MD, codigo)."""
import json
from pathlib import Path

import chromadb
import ollama

from core.config_loader import CONFIG

ROOT = Path(__file__).resolve().parent.parent
MEMORY_DIR = ROOT / "memory"
RAG_DIR = MEMORY_DIR / "rag_db"
DOCS_REGISTRY = MEMORY_DIR / "rag_documents.json"

EMBED_MODEL = "nomic-embed-text"

SUPPORTED_EXT = {".pdf", ".txt", ".md", ".docx", ".py", ".json", ".yaml", ".yml"}


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

        registry[doc_key] = {"name": path.name, "chunks": len(chunks)}
        self._save_registry(registry)

        return f"Indexado {path.name}: {len(chunks)} fragmentos."

    def index_folder(self, folder, recursive=True):
        folder = Path(folder).resolve()
        if not folder.exists() or not folder.is_dir():
            return f"No existe la carpeta: {folder}"

        pattern = "**/*" if recursive else "*"
        files = [
            p for p in folder.glob(pattern)
            if p.is_file() and p.suffix.lower() in SUPPORTED_EXT
        ]

        if not files:
            return f"No hay archivos compatibles en {folder}"

        total_chunks = 0
        indexed = 0
        for f in files:
            result = self.index_file(f)
            if result.startswith("Indexado"):
                indexed += 1
                try:
                    n = int(result.split(":")[1].split()[0])
                    total_chunks += n
                except Exception:
                    pass

        return f"Indexados {indexed} archivos ({total_chunks} fragmentos) desde {folder.name}."

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

        context = "\n\n---\n\n".join(d for d, _ in relevant)
        sources = list({m.get("name", "?") for _, m in relevant})

        prompt = (
            "Responde la pregunta usando SOLO la informacion del contexto. "
            "Si el contexto no contiene la respuesta, dilo claramente. "
            "Responde en espanol, de forma concisa.\n\n"
            f"Contexto:\n{context}\n\n"
            f"Pregunta: {query}\n\n"
            "Respuesta:"
        )

        try:
            resp = ollama.chat(
                model=CONFIG["models"].get("reasoning", CONFIG["models"]["default"]),
                messages=[{"role": "user", "content": prompt}],
                options={"temperature": 0.2},
            )
            answer = resp["message"]["content"].strip()
        except Exception as e:
            answer = f"Error al consultar el modelo: {e}"

        return {"answer": answer, "sources": sources}

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