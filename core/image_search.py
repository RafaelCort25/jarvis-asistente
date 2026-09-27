"""Motor de búsqueda y generación de imágenes para documentos.

Modos:
- pexels: buscar fotos reales en Pexels (gratis)
- ai: generar con Stable Diffusion (local via Cloudflare Flux)
- local: usar imágenes de una carpeta
"""
import os
import re
from pathlib import Path
from typing import List, Dict

import requests
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env.personal")

PEXELS_API_KEY = os.getenv("PEXELS_API_KEY", "")
PEXELS_BASE = "https://api.pexels.com/v1/search"


def _slug(text: str, maxlen: int = 40) -> str:
    """Convierte un texto en slug válido para archivo."""
    t = text.lower()
    for k, v in {"á": "a", "é": "e", "í": "i", "ó": "o", "ú": "u", "ñ": "n"}.items():
        t = t.replace(k, v)
    t = re.sub(r"[^a-z0-9]+", "_", t)[:maxlen].strip("_")
    return t or "imagen"


def extract_queries(description: str, n: int = 3) -> List[str]:
    """Extrae N queries de búsqueda a partir de la descripción del documento.

    Usa el LLM para analizar el tema y generar queries cortas en inglés
    (Pexels funciona mejor en inglés).
    """
    try:
        import ollama
        from core.model_config import get_model

        prompt = f"""Analiza este tema para un documento y genera {n} queries cortas
(en INGLES, 2-4 palabras cada una) para buscar fotos profesionales en Pexels.

Tema: {description}

Reglas:
- Cada query en ingles
- Cortas: 2-4 palabras
- Relevantes al tema
- Diversas (no todas iguales)

Responde SOLO con las {n} queries, una por linea, sin numeros ni markdown.
Ejemplo:
gothic cathedral interior
rose window stained glass
gothic architecture facade"""

        response = ollama.chat(
            model=get_model("chat"),
            messages=[{"role": "user", "content": prompt}],
            options={"temperature": 0.3, "num_predict": 150},
            stream=False,
        )
        raw = response["message"]["content"].strip()
        queries = [q.strip() for q in raw.split("\n") if q.strip() and len(q.strip()) > 3]
        # Limpiar numeros o bullets al inicio
        queries = [re.sub(r"^[\d\.\-\*\s]+", "", q).strip() for q in queries]
        return queries[:n] if queries else [description[:50]]
    except Exception as e:
        print(f"[IMAGE_SEARCH] Error extrayendo queries: {e}")
        return [description[:50]]


def search_pexels(query: str, n: int = 5) -> List[Dict]:
    """Busca N fotos en Pexels con una query."""
    if not PEXELS_API_KEY:
        print("[IMAGE_SEARCH] PEXELS_API_KEY no configurada")
        return []

    try:
        r = requests.get(
            PEXELS_BASE,
            params={"query": query, "per_page": n, "orientation": "landscape"},
            headers={"Authorization": PEXELS_API_KEY},
            timeout=15,
        )
        if r.status_code != 200:
            print(f"[IMAGE_SEARCH] Pexels error {r.status_code}: {r.text[:100]}")
            return []

        data = r.json()
        photos = []
        for p in data.get("photos", []):
            # Elegir el mejor tamaño (large, 940px ancho)
            src = p.get("src", {})
            url = src.get("large") or src.get("medium") or src.get("original", "")
            photos.append({
                "id": p.get("id"),
                "url": url,
                "url_thumb": src.get("small", ""),
                "photographer": p.get("photographer", ""),
                "photographer_url": p.get("photographer_url", ""),
                "alt": p.get("alt", query),
                "source": "pexels",
                "query": query,
            })
        return photos
    except Exception as e:
        print(f"[IMAGE_SEARCH] Error Pexels: {e}")
        return []


def download_image(url: str, output_path: Path) -> bool:
    """Descarga una imagen a disco. Devuelve True si OK."""
    try:
        r = requests.get(url, timeout=30, stream=True)
        if r.status_code != 200:
            return False
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "wb") as f:
            for chunk in r.iter_content(8192):
                f.write(chunk)
        return True
    except Exception as e:
        print(f"[IMAGE_SEARCH] Error descargando: {e}")
        return False


def search_for_document(description: str, n_queries: int = 3, per_query: int = 2) -> List[Dict]:
    """Busca fotos para un documento.

    1. Extrae N queries del tema
    2. Busca per_query fotos por cada query
    3. Devuelve lista consolidada
    """
    queries = extract_queries(description, n=n_queries)
    print(f"[IMAGE_SEARCH] Queries generadas: {queries}")

    all_photos = []
    for q in queries:
        photos = search_pexels(q, n=per_query)
        all_photos.extend(photos)

    # Deduplicar por ID
    seen = set()
    unique = []
    for p in all_photos:
        if p["id"] not in seen:
            seen.add(p["id"])
            unique.append(p)

    print(f"[IMAGE_SEARCH] {len(unique)} fotos unicas encontradas")
    return unique


if __name__ == "__main__":
    # Test rapido
    print("=== Test extract_queries ===")
    queries = extract_queries("catedrales goticas", n=3)
    for q in queries:
        print(f"  - {q}")
    print()

    print("=== Test search_pexels ===")
    photos = search_pexels("gothic cathedral", n=3)
    for i, p in enumerate(photos, 1):
        print(f"  {i}. {p['alt'][:60]} - por {p['photographer']}")
    print()

    print("=== Test search_for_document ===")
    results = search_for_document("catedrales goticas", n_queries=2, per_query=2)
    for i, p in enumerate(results, 1):
        print(f"  {i}. [{p['query']}] {p['alt'][:50]}")