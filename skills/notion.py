"""Skill de Notion: crear paginas, notas y buscar en el workspace."""

import json
import re
from datetime import datetime
from pathlib import Path
from skills.base import Skill
from core import confirmation

ROOT = Path(__file__).resolve().parent.parent
NOTION_DIR = ROOT / "sandbox" / "notion"
NOTION_DIR.mkdir(parents=True, exist_ok=True)
CONFIG_FILE = NOTION_DIR / "config.json"


def _load_env_token():
    """Carga el token de Notion desde .env.personal."""
    env_file = ROOT / ".env.personal"
    if not env_file.exists():
        return None
    for line in env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line.startswith("NOTION_TOKEN="):
            return line.split("=", 1)[1].strip().strip('"').strip("'")
    return None


def _load_config():
    if not CONFIG_FILE.exists():
        return {}
    try:
        return json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_config(cfg):
    CONFIG_FILE.write_text(
        json.dumps(cfg, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


class NotionSkill(Skill):
    name = "notion"
    description = "Notion: crear paginas, notas, buscar"

    def __init__(self):
        self._client = None

    def _get_client(self):
        if self._client is not None:
            return self._client
        token = _load_env_token()
        if not token:
            raise RuntimeError("No encontre NOTION_TOKEN en .env.personal")
        try:
            from notion_client import Client
        except ImportError:
            raise RuntimeError("Falta instalar notion-client: pip install notion-client")
        self._client = Client(auth=token)
        return self._client

    def run(self, action, params):
        try:
            if action == "whoami":
                return self._whoami()
            if action == "search":
                return self._search(params.get("query", ""))
            if action == "list_pages":
                return self._list_pages(int(params.get("limit", 15) or 15))
            if action == "create_page":
                return self._create_page(params)
            if action == "save_note":
                return self._save_note(params)
            if action == "append_block":
                return self._append_block(params)
            if action == "set_default_parent":
                return self._set_default_parent(params.get("id", ""))
            if action == "config":
                return self._show_config()
            return f"Accion desconocida en notion: {action}"
        except Exception as e:
            return {"thought": "Error Notion", "display": f"Error: {e}", "voice": "Error conectando con Notion."}

    # ─── HELPERS ─────────────────────────────────────────────────────────
    def _extract_id(self, raw):
        """Acepta un ID o una URL de Notion y devuelve el UUID limpio."""
        if not raw:
            return ""
        s = raw.strip()
        # Si es una URL: extraer el ultimo bloque hex de 32 chars
        m = re.search(r"([0-9a-fA-F]{32})", s.replace("-", ""))
        if m:
            h = m.group(1)
            # Formatear con guiones (Notion acepta ambos, pero con guiones es estandar)
            return f"{h[:8]}-{h[8:12]}-{h[12:16]}-{h[16:20]}-{h[20:]}"
        return s

    def _rich_text(self, text):
        """Construye un objeto rich_text de Notion a partir de texto plano."""
        return [{"type": "text", "text": {"content": text}}]

    def _paragraph_block(self, text):
        return {
            "object": "block",
            "type": "paragraph",
            "paragraph": {"rich_text": self._rich_text(text)},
        }

    def _heading_block(self, text, level=2):
        key = f"heading_{level}"
        return {
            "object": "block",
            "type": key,
            key: {"rich_text": self._rich_text(text)},
        }

    def _bullet_block(self, text):
        return {
            "object": "block",
            "type": "bulleted_list_item",
            "bulleted_list_item": {"rich_text": self._rich_text(text)},
        }

    def _numbered_block(self, text):
        return {
            "object": "block",
            "type": "numbered_list_item",
            "numbered_list_item": {"rich_text": self._rich_text(text)},
        }

    def _quote_block(self, text):
        return {
            "object": "block",
            "type": "quote",
            "quote": {"rich_text": self._rich_text(text)},
        }

    def _code_block(self, text, lang="plain text"):
        return {
            "object": "block",
            "type": "code",
            "code": {
                "rich_text": self._rich_text(text),
                "language": lang,
            },
        }

    def _divider_block(self):
        return {"object": "block", "type": "divider", "divider": {}}

    def _parse_content_to_blocks(self, content):
        """Convierte markdown simple a bloques de Notion."""
        if not content:
            return []
        blocks = []
        lines = content.split("\n")
        i = 0
        while i < len(lines):
            line = lines[i].rstrip()
            if not line:
                i += 1
                continue
            # Bloque de codigo
            if line.startswith("```"):
                lang = line[3:].strip() or "plain text"
                code_lines = []
                i += 1
                while i < len(lines) and not lines[i].startswith("```"):
                    code_lines.append(lines[i])
                    i += 1
                blocks.append(self._code_block("\n".join(code_lines), lang))
                i += 1
                continue
            # Headings
            if line.startswith("### "):
                blocks.append(self._heading_block(line[4:], 3))
            elif line.startswith("## "):
                blocks.append(self._heading_block(line[3:], 2))
            elif line.startswith("# "):
                blocks.append(self._heading_block(line[2:], 1))
            # Bullets
            elif line.startswith("- ") or line.startswith("* "):
                blocks.append(self._bullet_block(line[2:]))
            # Numbered
            elif re.match(r"^\d+\.\s", line):
                text = re.sub(r"^\d+\.\s", "", line)
                blocks.append(self._numbered_block(text))
            # Quote
            elif line.startswith("> "):
                blocks.append(self._quote_block(line[2:]))
            # Divider
            elif line.strip() == "---":
                blocks.append(self._divider_block())
            else:
                blocks.append(self._paragraph_block(line))
            i += 1
        return blocks

    def _page_title(self, page):
        """Extrae el titulo de una page de Notion."""
        try:
            props = page.get("properties", {})
            for key in ("title", "Name", "Título", "Titulo"):
                if key in props:
                    p = props[key]
                    if p.get("type") == "title":
                        title_arr = p.get("title", [])
                        if title_arr:
                            return "".join(t.get("plain_text", "") for t in title_arr)
            # Fallback: buscar cualquier propiedad title
            for p in props.values():
                if isinstance(p, dict) and p.get("type") == "title":
                    title_arr = p.get("title", [])
                    if title_arr:
                        return "".join(t.get("plain_text", "") for t in title_arr)
        except Exception:
            pass
        return "(sin titulo)"

    # ─── WHOAMI (test de conexion) ───────────────────────────────────────
    def _whoami(self):
        client = self._get_client()
        me = client.users.me()
        nombre = me.get("name", "?")
        tipo = me.get("type", "?")
        bot = me.get("bot", {})
        owner = bot.get("owner", {})
        workspace = owner.get("workspace", True)
        return {
            "thought": f"Conectado a Notion como {nombre}",
            "display": (
                f"**Conexion Notion OK**\n"
                f"- Nombre: {nombre}\n"
                f"- Tipo: {tipo}\n"
                f"- Workspace: {workspace}"
            ),
            "voice": f"Conectado a Notion como {nombre}.",
        }

    # ─── SEARCH ──────────────────────────────────────────────────────────
    def _search(self, query):
        client = self._get_client()
        query = (query or "").strip()
        kwargs = {"page_size": 15}
        if query:
            kwargs["query"] = query
        res = client.search(**kwargs)
        results = res.get("results", [])
        if not results:
            return {
                "thought": "",
                "display": f"No encontre nada" + (f" con '{query}'." if query else "."),
                "voice": "Sin resultados.",
            }
        lineas = [f"**Resultados en Notion** ({len(results)}):"]
        for r in results[:15]:
            obj = r.get("object")
            if obj == "page":
                titulo = self._page_title(r)
                pid = r.get("id", "")
                lineas.append(f" [page] {titulo}")
                lineas.append(f" ID: {pid}")
            elif obj == "database":
                titulo_arr = r.get("title", [])
                nombre = "".join(t.get("plain_text", "") for t in titulo_arr) or "(sin titulo)"
                lineas.append(f" [database] {nombre}")
                lineas.append(f" ID: {r.get('id', '')}")
        return {
            "thought": f"{len(results)} resultados",
            "display": "\n".join(lineas),
            "voice": f"Encontre {len(results)} resultados.",
        }

    # ─── LIST PAGES ──────────────────────────────────────────────────────
    def _list_pages(self, limit=15):
        client = self._get_client()
        res = client.search(
            filter={"property": "object", "value": "page"},
            page_size=limit,
        )
        results = res.get("results", [])
        if not results:
            return {
                "thought": "",
                "display": "No hay paginas accesibles. Conecta la integracion a una pagina en Notion.",
                "voice": "Sin paginas.",
            }
        lineas = [f"**Paginas recientes en Notion** ({len(results)}):"]
        for r in results[:limit]:
            titulo = self._page_title(r)
            lineas.append(f" - {titulo}")
            lineas.append(f"   ID: {r.get('id', '')}")
        return {
            "thought": f"{len(results)} paginas",
            "display": "\n".join(lineas),
            "voice": f"Tienes {len(results)} paginas accesibles.",
        }

    # ─── CONFIG: parent page por defecto ─────────────────────────────────
    def _set_default_parent(self, page_id):
        pid = self._extract_id(page_id)
        if not pid:
            return {
                "thought": "",
                "display": "Necesito el ID o URL de la pagina padre.",
                "voice": "Falta el ID.",
            }
        cfg = _load_config()
        cfg["default_parent_id"] = pid
        _save_config(cfg)
        return {
            "thought": f"Parent por defecto guardado: {pid}",
            "display": f"Pagina padre por defecto guardada:\n{pid}",
            "voice": "Listo. Pagina padre configurada.",
        }

    def _show_config(self):
        cfg = _load_config()
        pid = cfg.get("default_parent_id", "(no configurado)")
        tiene_token = bool(_load_env_token())
        return {
            "thought": "Config Notion",
            "display": (
                f"**Config Notion**\n"
                f"- Token: {'OK' if tiene_token else 'FALTA'}\n"
                f"- Pagina padre por defecto: {pid}"
            ),
            "voice": "Mostrando configuracion.",
        }

    # ─── CREATE PAGE ─────────────────────────────────────────────────────
    def _create_page(self, params):
        client = self._get_client()
        titulo = (params.get("title", "") or "").strip()
        contenido = params.get("content", "") or ""
        parent_raw = params.get("parent_id", "")

        if not titulo:
            return {"thought": "", "display": "Necesito un titulo.", "voice": "Falta el titulo."}

        # Determinar parent
        if parent_raw:
            parent_id = self._extract_id(parent_raw)
        else:
            cfg = _load_config()
            parent_id = cfg.get("default_parent_id", "")

        if not parent_id:
            return {
                "thought": "",
                "display": "No hay pagina padre. Usa 'set_default_parent' o pasa parent_id.",
                "voice": "Falta la pagina padre.",
            }

        summary = f"Crear pagina Notion: '{titulo}'"
        if not confirmation.require("notion", "create_page", summary):
            return "Cancelado."

        children = self._parse_content_to_blocks(contenido)

        # El parent se asume page_id (no database). Para bases de datos, habria que
        # adaptar las properties.
        parent = {"type": "page_id", "page_id": parent_id}

        props = {
            "title": {
                "title": self._rich_text(titulo),
            }
        }

        try:
            page = client.pages.create(
                parent=parent,
                properties=props,
                children=children[:100],  # limite API
            )
        except Exception as e:
            return {"thought": "Error", "display": f"Error creando pagina: {e}", "voice": "Error."}

        pid = page.get("id", "")
        url = page.get("url", "")
        return {
            "thought": f"Pagina creada: {titulo}",
            "display": (
                f"**Pagina creada en Notion**\n"
                f"- Titulo: {titulo}\n"
                f"- Bloques: {len(children)}\n"
                f"- URL: {url}\n"
                f"- ID: {pid}"
            ),
            "voice": f"Pagina creada: {titulo}.",
        }

    # ─── SAVE NOTE (nota rapida) ─────────────────────────────────────────
    def _save_note(self, params):
        # Una nota rapida es una pagina con titulo (fecha) + contenido
        titulo = (params.get("title", "") or "").strip()
        contenido = (params.get("content", "") or "").strip()
        if not contenido and not titulo:
            return {"thought": "", "display": "Necesito contenido.", "voice": "Sin contenido."}
        if not titulo:
            # Titulo = primeras 60 chars del contenido
            titulo = contenido.split("\n")[0][:60] or f"Nota {datetime.now().strftime('%Y-%m-%d %H:%M')}"
        return self._create_page({
            "title": titulo,
            "content": contenido,
            "parent_id": params.get("parent_id", ""),
        })

    # ─── APPEND BLOCK ────────────────────────────────────────────────────
    def _append_block(self, params):
        client = self._get_client()
        page_raw = params.get("page_id", "")
        contenido = params.get("content", "") or ""
        if not page_raw:
            return {"thought": "", "display": "Necesito page_id.", "voice": "Falta page_id."}
        if not contenido.strip():
            return {"thought": "", "display": "Necesito contenido.", "voice": "Sin contenido."}
        page_id = self._extract_id(page_raw)
        blocks = self._parse_content_to_blocks(contenido)
        if not blocks:
            return {"thought": "", "display": "No hay bloques validos.", "voice": "Sin bloques."}
        try:
            client.blocks.children.append(block_id=page_id, children=blocks[:100])
        except Exception as e:
            return {"thought": "Error", "display": f"Error anadiendo bloques: {e}", "voice": "Error."}
        return {
            "thought": f"Anadidos {len(blocks)} bloques",
            "display": f"Anadidos {len(blocks)} bloques a la pagina {page_id}.",
            "voice": "Contenido anadido.",
        }
