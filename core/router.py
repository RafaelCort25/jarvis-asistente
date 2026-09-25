"""Router principal de JARVIS/Nitro.

Responsabilidades:
- Recibir texto del usuario
- Detectar comandos rapidos (quick_match) sin LLM
- Detectar comandos complejos -> agente ReAct
- Detectar razonamiento puro -> brain.chat
- Detectar multi-objetivo -> agente
- Ejecutar skills con timeout y captura de errores
"""

import re
import signal
import threading
import unicodedata
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeout

from core.intent import IntentClassifier
from core.agent import Agent

from skills.desktop import DesktopSkill
from skills.browser import BrowserSkill
from skills.entertainment import EntertainmentSkill
from skills.productivity import ProductivitySkill
from skills.system import SystemSkill
from skills.files import FilesSkill
from skills.weather import WeatherSkill
from skills.translate import TranslateSkill
from skills.alarm import AlarmSkill
from skills.dev import DevSkill
from skills.vision import VisionSkill
from skills.docs import DocsSkill
from skills.clipboard import ClipboardSkill
from skills.scheduler import SchedulerSkill
from skills.terminal import TerminalSkill
from skills.git import GitSkill
from skills.spotify import SpotifySkill
from skills.office import OfficeSkill
from skills.image import ImageSkill
from skills.pdf import PdfSkill
from skills.telegram import TelegramSkill
from skills.edit import EditSkill
from skills.education import EducationSkill
from skills.macro import MacroSkill
from skills.n8n import N8nSkill
from skills.gmail import GmailSkill
from skills.canva import CanvaSkill
from skills.freecad import FreeCadSkill
from skills.maps import MapsSkill
from skills.blender import BlenderSkill
from skills.dwg import DwgSkill


# Timeout maximo por skill (segundos)
SKILL_TIMEOUT = 180

# Pool global reutilizable
_executor = ThreadPoolExecutor(max_workers=4)


NUM_MAP = {
    "1": 1, "uno": 1, "primero": 1, "primer": 1, "la primera": 1, "el primero": 1,
    "2": 2, "dos": 2, "segundo": 2, "la segunda": 2, "el segundo": 2,
    "3": 3, "tres": 3, "tercero": 3, "tercer": 3, "la tercera": 3, "el tercero": 3,
    "4": 4, "cuatro": 4, "cuarto": 4, "la cuarta": 4, "el cuarto": 4,
    "5": 5, "cinco": 5, "quinto": 5, "la quinta": 5, "el quinto": 5,
}

CANCEL_WORDS = ["cancela", "cancelar", "olvidalo", "nada"]


class Router:
    def __init__(self):
        self.classifier = IntentClassifier()
        self.agent = Agent()
        self.skills = {
            "desktop": DesktopSkill(),
            "browser": BrowserSkill(),
            "entertainment": EntertainmentSkill(),
            "productivity": ProductivitySkill(),
            "system": SystemSkill(),
            "files": FilesSkill(),
            "weather": WeatherSkill(),
            "translate": TranslateSkill(),
            "alarm": AlarmSkill(),
            "dev": DevSkill(),
            "vision": VisionSkill(),
            "docs": DocsSkill(),
            "clipboard": ClipboardSkill(),
            "scheduler": SchedulerSkill(),
            "terminal": TerminalSkill(),
            "git": GitSkill(),
            "spotify": SpotifySkill(),
            "office": OfficeSkill(),
            "image": ImageSkill(),
            "pdf": PdfSkill(),
            "telegram": TelegramSkill(),
            "edit": EditSkill(),
            "education": EducationSkill(),
            "macro": MacroSkill(),
            "n8n": N8nSkill(),
            "gmail": GmailSkill(),
            "canva": CanvaSkill(),
            "freecad": FreeCadSkill(),
            "maps": MapsSkill(),
            "blender": BlenderSkill(),
            "dwg": DwgSkill(),
            
        }

    # ─── HELPERS ────────────────────────────────────────────────────────────

    def _parse_choice(self, text):
        t = text.lower().strip()
        t = re.sub(r'[.,;:!?¿¡]', '', t)
        t = re.sub(r'\b(el|la|los|las|quiero|pon|ponme|reproduce|dale|vamos|ok|vale)\b', '', t)
        t = re.sub(r'\s+', ' ', t).strip()
        if t in NUM_MAP:
            return NUM_MAP[t]
        m = re.search(r'\b([1-5])\b', t)
        if m:
            return int(m.group(1))
        return None

    def _is_cancel(self, text):
        t = text.lower().strip()
        return any(w in t for w in CANCEL_WORDS)

    def _is_complex(self, text):
        """Detecta si el comando necesita razonamiento del agente."""
        t = text.lower().strip()

        # Filtro de seguridad: textos muy cortos nunca son complejos
        palabras = t.split()
        if len(palabras) < 3:
            return False
        if len(t) < 10:
            return False

        # Normalizar acentos ANTES de comprobar separadores
        t = unicodedata.normalize("NFD", t)
        t = "".join(c for c in t if unicodedata.category(c) != "Mn")

        # Comandos compuestos con conectores -> agente
        separadores = [
            " y luego ", " luego ", " y despues ", " despues de eso ",
            " y tambien ", " y ademas ", " seguido de ",
            " y por ultimo ", " y por ultimo ",
        ]
        if any(sep in f" {t} " for sep in separadores):
            return True

        # Si es un comando simple conocido, NO es complejo
        simple_patterns = [
            "abre ", "abrir ", "cierra ", "cerrar ",
            "sube ", "baja ", "silencia",
            "pausa", "play", "siguiente", "anterior",
            "pon ", "ponme ", "reproduce ",
            "guarda nota", "lee mis notas", "mis notas",
            "captura", "bloquea",
            "que clima", "clima en", "traduce",
            "alarma", "recuerdame", "avisame",
            "busca en google", "busca en youtube",
        ]

        for p in simple_patterns:
            if t.startswith(p) or f" {p}" in t:
                if " y " not in t and "el mas" not in t and "el ultimo" not in t and "la mas" not in t:
                    return False

        complex_keywords = [
            "el ultimo", "la ultima", "los ultimos", "las ultimas",
            "el primero de los archivos",
            "el mas ", "la mas ",
            "mas reciente", "mas grande", "mas pequeno", "mas antiguo",
            "cuantos archivos", "cuantas archivos", "cuantos pdf",
            "cuantas fotos", "cuantos videos", "cuantos mp4",
            "que archivos", "que documentos",
            "hay algun", "hay alguna", "existe algun",
            "organiza", "ordena", "renombra",
            "y luego", "despues de eso",
            "abre el archivo", "abre el ultimo archivo",
            "cual es el archivo", "cual es la carpeta",
        ]

        for kw in complex_keywords:
            if kw in t:
                return True

        # Multiples verbos con "y"
        if " y " in t:
            verbs = ["abre", "cierra", "busca", "pon", "lista", "muestra", "guarda", "mueve"]
            count = sum(1 for v in verbs if f" {v} " in f" {t} ")
            if count >= 2:
                return True

        return False

    def _is_multi_objetivo(self, text):
        """Detecta si la frase tiene 2+ objetivos unidos por 'y'/'tambien'/'ademas'."""
        t = text.lower().strip()
        palabras = t.split()
        if len(palabras) < 5:
            return False
        if len(t) < 15:
            return False

        # Partir por " y ", " e ", " tambien ", " ademas "
        partes = re.split(r'\s+(?:y|e|tambien|también|ademas|además)\s+', t)

        # Verificar que al menos 2 partes tengan 2+ palabras
        partes_sustanciales = [p for p in partes if len(p.split()) >= 2]
        if len(partes_sustanciales) < 2:
            return False

        # Asegurar que cada parte sustancial tenga un verbo o intencion clara
        intenciones = [
            "abre", "abrir", "cierra", "cerrar",
            "busca", "buscar", "muestra", "muestrame",
            "lista", "listar", "dime", "cuanto", "cuanta", "cuantos", "cuantas",
            "que", "cual", "cuales",
            "genera", "crea", "hazme", "haz",
            "envia", "enviame", "manda", "mandame",
            "guarda", "guardame", "pon", "ponme",
            "reproduce", "revisa", "revisar",
            "limpia", "vacia", "borra", "elimina",
            "convierte", "traduce", "exporta",
            "espacio", "disco", "hora", "fecha", "clima",
            "programas", "arranca", "inicia", "archivos",
            "notas", "documentos", "apuntes", "pdfs",
        ]

        count_con_intencion = 0
        for parte in partes_sustanciales:
            if any(f" {w} " in f" {parte} " or parte.startswith(f"{w} ") for w in intenciones):
                count_con_intencion += 1

        return count_con_intencion >= 2

    def _is_pure_reasoning(self, text):
        """Detecta frases de razonamiento puro que deben ir al chat, no a skills."""
        t = text.lower().strip()
        patterns = [
            r'\bdame\s+\d*\s*ideas?\b',
            r'\bdame\s+\d*\s*consejos?\b',
            r'\baconsejame\b',
            r'\bexplicame\b',
            r'\bexplícame\b',
            r'\bque opinas\b',
            r'\bque piensas\b',
            r'\bque es\b',
            r'\bque significa\b',
            r'\bpor que\b',
            r'\bpor qué\b',
            r'\bcomo\s+(?:puedo|hago|mejorar|empiezo)\b',
            r'\bcómo\s+(?:puedo|hago|mejorar|empiezo)\b',
            r'\bescribeme\b',
            r'\bescríbeme\b',
            r'\bcuentame\b',
            r'\bcuéntame\b',
            r'\bplanifica\b',
            r'\bresume\b',
            r'\bresúmeme\b',
            r'\bexplica\b',
            r'\bdime\s+(?:algo|sobre|acerca)\b',
            r'\bdame\s+una\s+opinion\b',
            r'\bque\s+recomiendas\b',
        ]
        return any(re.search(p, t) for p in patterns)

    # ─── QUICK MATCH ────────────────────────────────────────────────────────

    def _quick_match(self, text):
        """Detecta comandos obvios sin llamar al LLM."""
        t = text.lower().strip()

        # ═══════════════════════════════════════════════════════════════════
        # N8N: workflows y automatizacion
        # ═══════════════════════════════════════════════════════════════════

        # Listar workflows
        if any(p in t for p in [
            "workflows en n8n", "workflows de n8n", "que workflows tengo",
            "lista workflows", "listar workflows", "muestra workflows",
            "mis workflows",
        ]):
            return [{"skill": "n8n", "action": "list_workflows", "params": {}}]

        # Listar ejecuciones
        if any(p in t for p in [
            "ejecuciones de n8n", "ejecuciones n8n", "ultimas ejecuciones",
            "que se ejecuto", "historial de n8n",
        ]):
            return [{"skill": "n8n", "action": "list_executions", "params": {}}]

        # Ver detalle de workflow
        m = re.search(
            r'\b(?:muestra|detalle|detalles|info|ver)\s+(?:el\s+|del\s+)?workflow\s+(.+)$',
            t, re.IGNORECASE
        )
        if m:
            name = m.group(1).strip(" .,!?¡¿")
            if name:
                return [{"skill": "n8n", "action": "get_workflow", "params": {"id_or_name": name}}]

        # Activar workflow
        m = re.search(
            r'\b(?:activa|activar|enciende|prende)\s+(?:el\s+|la\s+)?workflow\s+(.+)$',
            t, re.IGNORECASE
        )
        if m:
            name = m.group(1).strip(" .,!?¡¿")
            if name:
                return [{"skill": "n8n", "action": "activate", "params": {"id_or_name": name}}]

        # Desactivar workflow
        m = re.search(
            r'\b(?:desactiva|desactivar|apaga|para)\s+(?:el\s+|la\s+)?workflow\s+(.+)$',
            t, re.IGNORECASE
        )
        if m:
            name = m.group(1).strip(" .,!?¡¿")
            if name:
                return [{"skill": "n8n", "action": "deactivate", "params": {"id_or_name": name}}]

        # Borrar workflow
        m = re.search(
            r'\b(?:borra|elimina|quita)\s+(?:el\s+|la\s+)?workflow\s+(.+)$',
            t, re.IGNORECASE
        )
        if m:
            name = m.group(1).strip(" .,!?¡¿")
            if name:
                return [{"skill": "n8n", "action": "delete_workflow", "params": {"id_or_name": name}}]

        # Buscar templates en n8n.io
        m = re.search(
            r'\b(?:busca|buscar|encuentra)\s+(?:templates?|plantillas?|workflows?)\s+(?:de\s+|sobre\s+|para\s+)?(.+?)(?:\s+en\s+n8n)?$',
            t,
            re.IGNORECASE,
        )
        if m:
            query = m.group(1).strip(" .,!?¡¿")
            if query:
                return [{"skill": "n8n", "action": "search_templates", "params": {"query": query, "limit": 5}}]

        # Ver detalle de template
        m = re.search(
            r'\b(?:ver|muestra|detalle|detalles)\s+(?:el\s+)?template\s+(\d+)$',
            t,
            re.IGNORECASE,
        )
        if m:
            return [{"skill": "n8n", "action": "get_template", "params": {"id": m.group(1)}}]

        # Importar template
        m = re.search(
            r'\b(?:importa|descarga|instala|trae)\s+(?:el\s+)?template\s+(\d+)$',
            t,
            re.IGNORECASE,
        )
        if m:
            return [{"skill": "n8n", "action": "import_template", "params": {"id": m.group(1), "name": ""}}]

        # Crear workflow nuevo con LLM
        m = re.search(
            r'\b(?:crea|crear|genera|generar|hazme|haz)\s+(?:un\s+|el\s+)?workflow\s+(?:en\s+n8n\s+)?(?:que\s+|para\s+|de\s+)?(.+)$',
            t,
            re.IGNORECASE,
        )
        if m:
            desc = m.group(1).strip(" .,!?¡¿")
            if desc:
                return [{"skill": "n8n", "action": "create_workflow", "params": {"description": desc, "name": ""}}]

        # N8N BUILDER: frases que piden un workflow complejo (chatbot, automatizacion, etc.)
        m = re.search(
            r'\b(?:crea|crear|hazme|haz|genera|generar)\s+(?:un\s+|una\s+)?'
            r'(chatbot|bot|asistente virtual|automatizacion|automatización|flujo complejo|workflow complejo)\b',
            t,
            re.IGNORECASE,
        )
        if m:
            return "__N8N_BUILDER__"

        # ═══════════════════════════════════════════════════════════════════
        # GMAIL: correos
        # ═══════════════════════════════════════════════════════════════════

        # Contar sin leer
        if any(p in t for p in [
            "tengo correos", "correos sin leer", "cuantos correos",
            "hay correos nuevos", "correos nuevos",
        ]):
            return [{"skill": "gmail", "action": "count_unread", "params": {}}]

        # Listar recientes
        if any(p in t for p in [
            "lee mis correos", "leeme los correos", "leeme mis correos",
            "correos de hoy", "ultimos correos", "muestra mis correos",
            "revisa mi correo", "revisa mis correos",
        ]):
            n = 5
            m = re.search(r'\b(\d+)\s+correos?\b', t)
            if m:
                n = min(int(m.group(1)), 20)
            return [{"skill": "gmail", "action": "list_recent", "params": {"n": n}}]

        # Buscar correos
        m = re.search(
            r'\b(?:busca|buscar|encuentra)\s+(?:correos?\s+(?:de|sobre|con)\s+)(.+)$',
            t, re.IGNORECASE,
        )
        if m:
            query = m.group(1).strip(" .,!?¡¿")
            if query:
                return [{"skill": "gmail", "action": "search", "params": {"query": query}}]

        # Enviar correo
        m = re.search(
            r'\b(?:envia|enviar|mandale|mandar|escribele|escribir)\s+(?:un\s+)?(?:correo|email|mail)\s+a\s+([^\s]+@[^\s]+)',
            t, re.IGNORECASE,
        )
        if m:
            to = m.group(1).strip(" .,!?¡¿")
            resto = t[m.end():].strip()
            asunto = ""
            cuerpo = resto
            m_asunto = re.search(r'(?:asunto|sobre|diciendo|que diga)\s+(.+)$', resto, re.IGNORECASE)
            if m_asunto:
                cuerpo = m_asunto.group(1).strip(" .,!?¡¿")
            return [{
                "skill": "gmail",
                "action": "send",
                "params": {"to": to, "subject": asunto or "(sin asunto)", "body": cuerpo},
            }]

        # Leer un correo por UID
        m = re.search(r'\b(?:lee|abre|muestra)\s+(?:el\s+)?correo\s+(\d+)\b', t)
        if m:
            return [{"skill": "gmail", "action": "read", "params": {"uid": m.group(1)}}]

        # ═══════════════════════════════════════════════════════════════════
        # CANVA: disenos
        # ═══════════════════════════════════════════════════════════════════

        # Listar disenos
        if any(p in t for p in [
            "que disenos tengo", "mis disenos", "disenos en canva",
            "lista mis disenos", "muestra mis disenos", "lista disenos",
        ]):
            return [{"skill": "canva", "action": "list_designs", "params": {"limit": 10}}]

        # Ver detalle de un diseno
        m = re.search(
            r'\b(?:muestra|detalle|detalles|info|ver)\s+(?:el\s+|del\s+)?diseno\s+(\S+)',
            text, re.IGNORECASE,
        )
        if m:
            did = m.group(1).strip(" .,!?¡¿")
            if did:
                return [{"skill": "canva", "action": "get_design", "params": {"id": did}}]

        # Crear diseno
        m = re.search(
            r'\b(?:crea|crear|hazme|haz|genera|generar)\s+(?:un\s+|una\s+)?'
            r'(?:post\s+de\s+|publicacion\s+de\s+)?'
            r'(instagram|facebook|twitter|youtube|thumbnail|presentacion|documento|doc|poster|flyer|post)\s+'
            r'(?:para\s+|de\s+|sobre\s+)?(.+)$',
            t, re.IGNORECASE,
        )
        if m:
            tipo = m.group(1).strip()
            desc = m.group(2).strip(" .,!?¡¿")
            if desc:
                return [{
                    "skill": "canva",
                    "action": "create_design",
                    "params": {"design_type": tipo, "title": desc[:50]},
                }]

        # Exportar diseno
        m = re.search(
            r'\b(?:exporta|exportar)\s+(?:el\s+)?diseno\s+(\S+?)(?:\s+(?:a|en|como)\s+(png|jpg|jpeg|pdf|pptx|gif|mp4))?$',
            text, re.IGNORECASE,
        )
        if m:
            did = m.group(1).strip(" .,!?¡¿")
            fmt = (m.group(2) or "png").lower()
            if fmt == "jpeg":
                fmt = "jpg"
            if did:
                return [{
                    "skill": "canva",
                    "action": "export_design",
                    "params": {"id": did, "format": fmt},
                }]

        # Autorizar
        if any(p in t for p in [
            "conecta canva", "conectar canva", "autoriza canva", "autorizar canva",
            "login canva", "inicia canva",
        ]):
            return [{"skill": "canva", "action": "authorize", "params": {}}]

                # Exportar a IFC (BIM)
        if any(p in t for p in [
            "exporta el plano a ifc", "exportar a ifc", "guardar como ifc",
            "convierte el plano a ifc", "plano en ifc", "archivo ifc",
            "exporta a bim", "convierte a bim",
        ]):
            from core.paths import SANDBOX_DWG as sandbox_dwg
            m_path = re.search(r'([A-Za-z]:\\[^\s]+\.(?:dxf|dwg)|[^\s]+\.(?:dxf|dwg))', t)
            if m_path:
                path = m_path.group(1)
            else:
                candidatos = sorted(
                    sandbox_dwg.glob("*.dxf"),
                    key=lambda p: p.stat().st_mtime,
                    reverse=True,
                )
                path = str(candidatos[0]) if candidatos else ""
            return [{"skill": "dwg", "action": "export_ifc",
                     "params": {"path": path, "output": "",
                                "nombre_proyecto": "Proyecto Nitro",
                                "altura": 3.0, "grosor": 0.15}}]


                # ═══════════════════════════════════════════════════════════════════
        # DWG: cuadro de superficies y analisis de planos
        # ═══════════════════════════════════════════════════════════════════

        # Extraer ambientes con areas
        if any(p in t for p in [
            "ambientes del plano", "lista los ambientes", "que ambientes hay",
            "extrae los ambientes",
        ]):
            from core.paths import SANDBOX_DWG as sandbox_dwg
            # Extraer path si existe
            m_path = re.search(r'([A-Za-z]:\\[^\s]+\.(?:dxf|dwg)|[^\s]+\.(?:dxf|dwg))', t)
            if m_path:
                path = m_path.group(1)
            else:
                # Usar el DXF mas reciente (excluyendo el fixture)
                candidatos = sorted(
                    sandbox_dwg.glob("*.dxf"),
                    key=lambda p: p.stat().st_mtime,
                    reverse=True,
                )
                path = str(candidatos[0]) if candidatos else ""
            return [{"skill": "dwg", "action": "extract_rooms_with_areas",
                     "params": {"path": path}}]

        m = re.search(
            r'\b(?:cuadro\s+de\s+superficies|tabla\s+de\s+areas|tabla\s+de\s+superficies|resumen\s+de\s+areas)\s+(?:de|del|para)\s+(?:el\s+|la\s+)?(?:plano\s+|archivo\s+|dxf\s+)?(.+)$',
            t, re.IGNORECASE,
        )
        if m:
            archivo = m.group(1).strip(" .,!?¡¿")
            # Quitar extensiones previas
            archivo = re.sub(r'\.(dxf|dwg)$', '', archivo, flags=re.IGNORECASE)
            # Buscar en sandbox/dwg
            from core.paths import SANDBOX_DWG as sandbox_dwg
            candidatos = list(sandbox_dwg.glob(f"*{archivo}*.dxf")) + list(sandbox_dwg.glob(f"*{archivo}*.dwg"))
            if candidatos:
                path = str(sorted(candidatos, key=lambda p: p.stat().st_mtime, reverse=True)[0])
            else:
                path = archivo + ".dxf"
            return [{"skill": "dwg", "action": "cuadro_superficies_excel",
                     "params": {"path": path, "output": "", "titulo": "Cuadro de Superficies"}}]
        # ═══════════════════════════════════════════════════════════════════
        # FREECAD: geometria y planos
        # ═══════════════════════════════════════════════════════════════════

        # Nuevo documento
        if any(p in t for p in [
            "nuevo plano", "nuevo documento freecad", "nuevo dibujo cad",
            "crea un plano nuevo",
        ]):
            return [{"skill": "freecad", "action": "new_document", "params": {}}]

        # Listar objetos
        if any(p in t for p in [
            "que hay en el plano", "lista los objetos del plano", "que objetos tengo",
            "objetos del dibujo",
        ]):
            return [{"skill": "freecad", "action": "list_objects", "params": {}}]

        # Rectangulo
        m = re.search(
            r'\b(?:dibuja|hazme|crea|agrega|anade|añade)\s+(?:un\s+)?(?:rectangulo|rectángulo|cuadrado)\s+(?:de\s+)?(\d+(?:\.\d+)?)\s*(?:x|por)\s*(\d+(?:\.\d+)?)',
            text, re.IGNORECASE,
        )
        if m:
            ancho = float(m.group(1))
            alto = float(m.group(2))
            return [{
                "skill": "freecad",
                "action": "add_rectangle",
                "params": {"x1": 0, "y1": 0, "x2": ancho, "y2": alto, "label": "Rectangulo"},
            }]

        # Circulo
        m = re.search(
            r'\b(?:dibuja|hazme|crea|agrega|anade|añade)\s+(?:un\s+)?(?:circulo|círculo|columna)\s+(?:de\s+)?(?:radio\s+)?(\d+(?:\.\d+)?)',
            text, re.IGNORECASE,
        )
        if m:
            r = float(m.group(1))
            return [{
                "skill": "freecad",
                "action": "add_circle",
                "params": {"cx": 0, "cy": 0, "radius": r, "label": "Circulo"},
            }]

        # Linea / muro
        m = re.search(
            r'\b(?:dibuja|hazme|crea|agrega|anade|añade)\s+(?:un\s+)?(?:linea|línea|muro)\s+(?:de\s+)?(\d+(?:\.\d+)?)',
            text, re.IGNORECASE,
        )
        if m:
            largo = float(m.group(1))
            return [{
                "skill": "freecad",
                "action": "add_line",
                "params": {"x1": 0, "y1": 0, "z1": 0, "x2": largo, "y2": 0, "z2": 0, "label": "Linea"},
            }]

        # Exportar DXF
        if any(p in t for p in [
            "exporta el plano a dxf", "exporta a dxf", "guardar como dxf",
            "exporta el plano a autocad",
        ]):
            return [{
                "skill": "freecad",
                "action": "export_dxf",
                "params": {"path": ""},
            }]

        # Exportar PDF
        if any(p in t for p in [
            "exporta el plano a pdf", "exporta a pdf el plano cad",
        ]):
            return [{
                "skill": "freecad",
                "action": "export_pdf",
                "params": {"path": ""},
            }]

        # ═══════════════════════════════════════════════════════════════════
        # BLENDER: prioridad si pide "render" (antes que Maps)
        # ═══════════════════════════════════════════════════════════════════
        if any(p in t for p in ["haz un render", "hazme un render", "render del", "render de el", "render de la"]):
            from core.paths import SANDBOX_FREECAD as sandbox_fc
            detallados = sorted(sandbox_fc.glob("detallado_*.step"), key=lambda p: p.stat().st_mtime, reverse=True)
            simples = sorted(sandbox_fc.glob("edificio_*.step"), key=lambda p: p.stat().st_mtime, reverse=True)
            steps = detallados + simples
            if steps:
                return [{"skill": "blender", "action": "render_step", "params": {"step_path": str(steps[0]), "output": "", "cam_angulo": 45}}]
            # Sin STEPs: igual va a blender (que dara error claro)
            return [{"skill": "blender", "action": "render_step", "params": {"step_path": "", "output": "", "cam_angulo": 45}}]

        # ═══════════════════════════════════════════════════════════════════
        # SCHEDULER: tareas programadas
        # ═══════════════════════════════════════════════════════════════════

        # Programar tarea diaria
        m = re.search(
            r'\b(?:todos\s+los\s+dias?|cada\s+dia)\s+a\s+las?\s+(\d{1,2})(?::(\d{2}))?\s*(?:h|hrs?|horas?)?\s+(?:haz|hazme|ejecuta|corre|abre|mandame|envia)\s+(.+)$',
            text, re.IGNORECASE,
        )
        if m:
            hora = int(m.group(1))
            minuto = int(m.group(2) or 0)
            tarea = m.group(3).strip(" .,!?¡¿")
            if tarea and 0 <= hora < 24 and 0 <= minuto < 60:
                return [{"skill": "scheduler", "action": "add_daily",
                         "params": {"hour": hora, "minute": minuto, "task": tarea}}]

        # Programar tarea una vez
        m = re.search(
            r'\b(?:en|dentro\s+de)\s+(\d+)\s*(?:minutos?|min|m|horas?|h)\s+(?:haz|hazme|ejecuta|corre|abre|mandame|envia)\s+(.+)$',
            text, re.IGNORECASE,
        )
        if m:
            cantidad = int(m.group(1))
            tarea = m.group(2).strip(" .,!?¡¿")
            return [{"skill": "scheduler", "action": "add_once",
                     "params": {"minutes": cantidad, "task": tarea}}]

        # Listar tareas programadas
        if any(p in t for p in [
            "que tareas tengo programadas", "lista mis tareas programadas",
            "mis tareas programadas", "que tengo programado",
        ]):
            return [{"skill": "scheduler", "action": "list", "params": {}}]

        # Cancelar tarea programada
        if any(p in t for p in [
            "cancela la tarea programada", "borra la tarea programada",
            "elimina la tarea programada",
        ]):
            return [{"skill": "scheduler", "action": "cancel", "params": {}}]

        # ═══════════════════════════════════════════════════════════════════


        # VISION: analizar pantalla
        # ═══════════════════════════════════════════════════════════════════
        if any(p in t for p in [
            "que hay en mi pantalla", "que se ve en mi pantalla",
            "describe mi pantalla", "describe lo que ves",
            "que estoy viendo", "mira mi pantalla",
            "analiza mi pantalla",
        ]):
            return [{"skill": "vision", "action": "describe_screen", "params": {}}]

        if any(p in t for p in [
            "explica el codigo de mi pantalla", "explica lo que se ve",
            "explícame el código", "explica este codigo",
            "que hace este codigo en pantalla",
        ]):
            return [{"skill": "vision", "action": "explain_screen_code", "params": {}}]


        # ═══════════════════════════════════════════════════════════════════
        # MAPS: buscar edificios reales en OpenStreetMap
        # ═══════════════════════════════════════════════════════════════════

        # Info de un edificio
        m = re.search(
            r'\b(?:info|informacion|información|detalles|ficha)\s+de(?:l)?\s+(?:edificio\s+|lugar\s+)?(.+)$',
            text, re.IGNORECASE,
        )
        if m:
            q = m.group(1).strip(" .,!?¡¿")
            if q:
                return [{"skill": "maps", "action": "get_building", "params": {"query": q}}]

        # Modelar un edificio real
        m = re.search(
            r'\b(?:modela|modelar|hazme|haz|crea|genera|disena|diseña)\s+'
            r'(?:(?:un\s+)?(?:modelo|proyecto|edificio|plano)\s+)?'
            r'(?:3d\s+)?(?:de|del|como|basado\s+en)?\s*'
            r'(?:el\s+|la\s+)?(.+)$',
            text, re.IGNORECASE,
        )
        if m:
            q = m.group(1).strip(" .,!?¡¿")
            if q:
                return [{"skill": "maps", "action": "create_model", "params": {"query": q, "output": "", "formato": "step", "altura": None}}]

        # Buscar un edificio
        m = re.search(
            r'\b(?:busca|buscar|encuentra|donde esta|donde se encuentra)\s+(?:el\s+|la\s+)?(?:edificio\s+|lugar\s+)?(.+?)(?:\s+en\s+(?:el\s+)?mapa)?$',
            text, re.IGNORECASE,
        )
        if m and "mapa" in t:
            q = m.group(1).strip(" .,!?¡¿")
            if q:
                return [{"skill": "maps", "action": "search", "params": {"query": q}}]

        # ═══════════════════════════════════════════════════════════════════
        # BLENDER: render 3D (ultimo step, muestrame)
        # ═══════════════════════════════════════════════════════════════════

        if any(p in t for p in [
            "renderiza el ultimo", "renderiza el último", "render del ultimo",
            "renderiza este step", "renderiza este modelo",
            "muestrame en 3d", "muestrame el modelo en 3d", "muestrame el 3d",
            "ver en 3d", "visualiza el 3d", "visualizar el modelo",
            "renderiza en blender",
        ]):
            from core.paths import SANDBOX_FREECAD as sandbox_fc
            detallados = sorted(sandbox_fc.glob("detallado_*.step"), key=lambda p: p.stat().st_mtime, reverse=True)
            simples = sorted(sandbox_fc.glob("edificio_*.step"), key=lambda p: p.stat().st_mtime, reverse=True)
            steps = detallados + simples
            if steps:
                return [{"skill": "blender", "action": "render_step", "params": {"step_path": str(steps[0]), "output": "", "cam_angulo": 45}}]

        # Renderizar un STEP especifico
        m = re.search(
            r'\b(?:renderiza|renderizar|render)\s+(?:el\s+|este\s+|la\s+)?(?:step|archivo|modelo)\s+(.+\.step)\b',
            text, re.IGNORECASE,
        )
        if m:
            step_path = m.group(1).strip(" .,!?¡¿")
            return [{"skill": "blender", "action": "render_step", "params": {"step_path": step_path, "output": "", "cam_angulo": 45}}]

        # ═══════════════════════════════════════════════════════════════════
        # MACRO: grabar/reproducir secuencias
        # ═══════════════════════════════════════════════════════════════════

        # Empezar a grabar
        m = re.search(
            r'\b(?:empieza|empezar|inicia|iniciar|comienza|comenzar)\s+(?:a\s+)?grabar\s+(?:el\s+|un\s+|la\s+)?(?:macro\s+)?(.+)$',
            t,
            re.IGNORECASE,
        )
        if m:
            name = m.group(1).strip(" .,!?¡¿")
            if name:
                return [{"skill": "macro", "action": "start", "params": {"name": name}}]

        # Parar de grabar
        if any(p in t for p in [
            "para de grabar", "detén la grabación", "deten la grabacion",
            "termina de grabar", "finaliza la grabacion", "stop grabacion",
        ]):
            return [{"skill": "macro", "action": "stop", "params": {}}]

        # Reproducir
        m = re.search(
            r'\b(?:ejecuta|reproduce|corre|lanza|haz)\s+(?:el\s+|la\s+)?macro\s+(.+)$',
            t,
            re.IGNORECASE,
        )
        if m:
            name = m.group(1).strip(" .,!?¡¿")
            if name:
                return [{"skill": "macro", "action": "play", "params": {"name": name}}]

        # Listar
        if any(p in t for p in [
            "que macros tengo", "lista mis macros", "lista los macros",
            "macros guardados",
        ]):
            return [{"skill": "macro", "action": "list", "params": {}}]

        # Borrar
        m = re.search(
            r'\b(?:borra|elimina|quita)\s+(?:el\s+|la\s+)?macro\s+(.+)$',
            t,
            re.IGNORECASE,
        )
        if m:
            name = m.group(1).strip(" .,!?¡¿")
            if name:
                return [{"skill": "macro", "action": "delete", "params": {"name": name}}]

        # ═══════════════════════════════════════════════════════════════════
        # ABRIR APP CONOCIDA (va antes que terminal/clasificador)
        # ═══════════════════════════════════════════════════════════════════
        m = re.search(
            r'\b(?:abre|abrir|lanza|inicia|ejecuta)\s+(?:la\s+|el\s+)?'
            r'(brave|chrome|notepad|bloc\s+de\s+notas|bloc\s+de\s+nota|'
            r'calculadora|calc|explorador|explorer|paint|cmd|spotify)\b',
            t,
            re.IGNORECASE,
        )
        if m:
            raw_app = m.group(1).lower().strip()
            app_map = {
                "bloc de notas": "notepad",
                "bloc de nota": "notepad",
                "calc": "calculadora",
                "explorer": "explorador",
            }
            app = app_map.get(raw_app, raw_app)
            if app in ("brave", "chrome", "notepad", "calculadora", "explorador", "paint", "cmd", "spotify"):
                return [{"skill": "desktop", "action": "open_app", "params": {"app": app}}]

        # ═══════════════════════════════════════════════════════════════════
        # COMBO: RAG -> Word (PRIORIDAD ALTA: antes que Office / RAG basico)
        # ═══════════════════════════════════════════════════════════════════
        if re.search(r'\b(?:word|docx|documento|informe|reporte)\b', t) and any(p in t for p in [
            "segun mi", "segun mis", "de mi cv", "de mi curriculum", "de mis apuntes",
            "de mis pdfs", "de mis documentos", "que dice mi", "que dicen mis",
        ]):
            return [{
                "skill": "docs",
                "action": "ask_to_word",
                "params": {"query": text, "title": ""},
            }]

        # ═══════════════════════════════════════════════════════════════════
        # EDUCATION: PSeInt, conversion, diagramas
        # ═══════════════════════════════════════════════════════════════════

        # PSeInt
        m = re.search(
            r'\b(?:hazme|genera|crea|escribe)\s+(?:un\s+|una\s+)?(?:algoritmo|pseudocodigo|pseudocódigo|pseint)\s+(?:de\s+|para\s+|que\s+)?(.+)$',
            t,
            re.IGNORECASE,
        )
        if m:
            desc = m.group(1).strip(" .,!?¡¿")
            if desc:
                return [{
                    "skill": "education",
                    "action": "pseint",
                    "params": {"description": desc},
                }]

        # Diagrama
        m = re.search(
            r'\b(?:hazme|genera|crea|dibuja)\s+(?:un\s+|una\s+)?(?:diagrama|flowchart|flujo)\s+(?:de\s+|para\s+|sobre\s+)?(.+)$',
            t,
            re.IGNORECASE,
        )
        if m:
            desc = m.group(1).strip(" .,!?¡¿")
            kind = "flowchart"
            if "secuencia" in t or "sequence" in t:
                kind = "sequence"
            elif "clase" in t or "class" in t:
                kind = "class"
            elif "estado" in t or "state" in t:
                kind = "state"
            elif re.search(r'\ber\b', t) or "entidad" in t or "entidades" in t:
                kind = "er"
            if desc:
                return [{
                    "skill": "education",
                    "action": "diagram",
                    "params": {"description": desc, "kind": kind},
                }]

        # Convertir codigo
        m = re.search(
            r'\b(?:convierte|pasa|traduce)\s+(?:este\s+|el\s+|ese\s+)?(?:codigo|código|pseudocodigo|algoritmo)?\s*(?:a\s+)(python|java|c|cpp|csharp|javascript|go|rust|pseint)\b',
            t,
            re.IGNORECASE,
        )
        if m:
            lang = m.group(1).lower()
            return [{
                "skill": "education",
                "action": "convert",
                "params": {"code": "", "to_language": lang},
            }]

        # ═══════════════════════════════════════════════════════════════════
        # COMBO IMAGEN -> WORD (antes que office)
        # ═══════════════════════════════════════════════════════════════════
        if re.search(r'\b(?:word|docx|documento)\b', t) and re.search(r'\b(?:genera|crea|dibuja|hazme)\b', t):
            # Variante: "hazme un word con las ultimas imagenes"
            if re.search(r'\b(?:ultimas?|ultimo|recientes?)\s+(?:imagenes?|logos?|fotos?)\b', t):
                return [{
                    "skill": "image",
                    "action": "to_word",
                    "params": {"prompt": "", "count": 1, "title": ""},
                }]

            # Variante: "hazme un word con imagenes de X"
            m = re.search(
                r'\bhazme\s+un\s+(?:word|documento|docx)\s+con\s+(?:(\d+)\s+)?(?:imagen(?:es)?|logos?|fotos?|dibujos?)\s+(?:de\s+|sobre\s+)?(.+)$',
                t,
                re.IGNORECASE,
            )
            if m:
                count = int(m.group(1)) if m.group(1) else 1
                prompt = m.group(2).strip(" .,!?¡¿")
                if prompt:
                    return [{
                        "skill": "image",
                        "action": "to_word",
                        "params": {"prompt": prompt, "count": count, "title": ""},
                    }]

            # Variante principal
            m = re.search(
                r'\b(?:genera|crea|dibuja)\s+(?:(\d+)\s+)?(?:(?:un|una|el|la|los|las|mi|mis)\s+)?(imagen(?:es)?|logo(?:s)?|foto(?:s)?|dibujo(?:s)?|ilustracion(?:es)?|diseno(?:s)?|diseño(?:s)?)\s+(.+?)\s+(?:y\s+)?(?:hazme|crea|genera|mete|pon)\b',
                t,
                re.IGNORECASE,
            )
            if m:
                count = int(m.group(1)) if m.group(1) else 1
                tipo = m.group(2)
                detalle = m.group(3).strip(" .,!?¡¿")
                prompt = f"{tipo} {detalle}".strip()
                if prompt:
                    return [{
                        "skill": "image",
                        "action": "to_word",
                        "params": {"prompt": prompt, "count": count, "title": ""},
                    }]

        # ═══════════════════════════════════════════════════════════════════
        # COMBOS DEV (antes de office para evitar intersecciones)
        # ═══════════════════════════════════════════════════════════════════

        # Combo: revisar codigo -> Excel con bugs
        palabras_excel = ["excel", "xlsx", "hoja"]
        palabras_revisar = ["revisa", "revisar", "audita", "analiza", "encuentra", "busca"]
        palabras_bugs = ["bug", "bugs", "error", "errores", "problema", "problemas"]
        tiene_excel = any(p in t for p in palabras_excel)
        tiene_revisar = any(p in t for p in palabras_revisar)
        tiene_bugs = any(p in t for p in palabras_bugs)
        if tiene_excel and tiene_revisar and tiene_bugs:
            m_path = re.search(
                r'([A-Za-z]:\\[^\s]+\.\w{2,5}|[^\s]+\.(?:py|js|java|txt|md|ts|go|rb|cpp|cs))',
                t,
            )
            path = m_path.group(1) if m_path else ""
            return [{
                "skill": "dev",
                "action": "review_to_excel",
                "params": {"path": path, "output": ""},
            }]

        # Combo: revisar codigo -> Word con analisis
        palabras_word = ["word", "docx", "informe", "reporte"]
        tiene_word = any(p in t for p in palabras_word)
        menciona_codigo = any(p in t for p in [
            "codigo", "código", ".py", ".js", ".java", "archivo.py",
            "este archivo", "ese archivo", "el archivo",
        ])
        if tiene_word and tiene_revisar and menciona_codigo:
            m_path = re.search(
                r'([A-Za-z]:\\[^\s]+\.\w{2,5}|[^\s]+\.(?:py|js|java|txt|md|ts|go|rb|cpp|cs))',
                t,
            )
            path = m_path.group(1) if m_path else ""
            return [{
                "skill": "dev",
                "action": "review_to_word",
                "params": {"path": path, "output": ""},
            }]

        # ═══════════════════════════════════════════════════════════════════
        # PRIORIDAD MAXIMA: si la frase EMPIEZA con verbo de edicion, es edit.
        # ═══════════════════════════════════════════════════════════════════
        if re.match(r'^(?:modifica|edita|actualiza|corrige)\b', t):
            path = ""
            m_path = re.search(
                r'([A-Za-z]:\\[^\s]+\.\w{2,5}|[^\s]+\.(?:docx|xlsx|txt|pdf|py|md|csv))',
                t,
            )
            if m_path:
                path = m_path.group(1)

            m_instr = re.sub(r'^(?:modifica|edita|actualiza|corrige)\s+', '', t)
            m_instr = m_instr.strip(" .,!?¡¿")

            if m_instr:
                return [{
                    "skill": "edit",
                    "action": "modify",
                    "params": {"path": path, "instruction": m_instr, "output": ""},
                }]

        # Portapapeles: leer
        if any(p in t for p in [
            "que tengo copiado", "que hay en el portapapeles",
            "lee el portapapeles", "leer el portapapeles", "muestra el portapapeles",
        ]):
            return [{"skill": "clipboard", "action": "read", "params": {}}]

        # Portapapeles: escribir
        m = re.search(r'\b(?:copia|copiar|guarda en el portapapeles)\s+(?:esto:?\s*)?(.+)$', t)
        if m and "portapapeles" not in m.group(1).lower()[:20]:
            text_to_copy = m.group(1).strip(" .,!?¡¿")
            if text_to_copy:
                return [{"skill": "clipboard", "action": "write", "params": {"text": text_to_copy}}]

        # Hora y fecha
        if any(p in t for p in [
            "que hora es", "que hora tienes", "dime la hora", "dame la hora",
            "hora actual", "hora es",
        ]):
            return [{"skill": "system", "action": "time", "params": {}}]

        if any(p in t for p in [
            "que dia es hoy", "que dia es", "que fecha es hoy", "que fecha es",
            "dime la fecha", "dame la fecha", "fecha actual",
        ]):
            return [{"skill": "system", "action": "date", "params": {}}]

        # ═══════════════════════════════════════════════════════════════════
        # SYSTEM: discos, limpieza, startup, archivos grandes
        # ═══════════════════════════════════════════════════════════════════

        # Discos / espacio
        if any(p in t for p in [
            "cuanto espacio tengo", "cuanto espacio libre", "espacio en disco",
            "espacio del disco", "cuanto disco", "info de discos",
            "informacion de discos",
        ]):
            return [{"skill": "system", "action": "disk_info", "params": {}}]

        # Limpiar temporales
        if any(p in t for p in [
            "limpia temporales", "limpia los temporales", "borra temporales",
            "borra los temporales", "limpia temp", "limpia el temp",
        ]):
            return [{"skill": "system", "action": "clean_temp", "params": {}}]

        # Vaciar papelera
        if any(p in t for p in [
            "vacia la papelera", "vacía la papelera", "vacia papelera",
            "limpia la papelera", "borra la papelera",
        ]):
            return [{"skill": "system", "action": "empty_recycle", "params": {}}]

        # Listar archivos grandes
        if any(p in t for p in [
            "archivos grandes", "archivos pesados", "que ocupa mas",
            "que ocupa mas espacio", "que es lo que mas pesa",
        ]):
            folder = ""
            min_mb = 100
            for carpeta in ["descargas", "downloads", "documentos", "escritorio", "videos", "musica"]:
                if carpeta in t:
                    folder = carpeta
                    break
            m_num = re.search(r'(\d+)\s*(?:mb|megas?|gb|gigas?)', t)
            if m_num:
                val = int(m_num.group(1))
                if "gb" in t or "giga" in t:
                    min_mb = val * 1024
                else:
                    min_mb = val
            return [{
                "skill": "system",
                "action": "list_big_files",
                "params": {"folder": folder, "min_mb": min_mb},
            }]

        # Listar programas de inicio
        if any(p in t for p in [
            "programas de inicio", "que arranca con windows",
            "que inicia con windows", "startup", "programas que arrancan",
        ]):
            return [{"skill": "system", "action": "list_startup", "params": {}}]

        # Terminal: comando explicito con "ejecuta" + prefijos conocidos
        m = re.search(r'\b(?:ejecuta|corre|lanza|haz)\s+(?:el\s+comando\s+|en\s+terminal\s+)?(.+)$', t)
        if m:
            cmd = m.group(1).strip(" .,!?¡¿")
            if cmd and any(cmd.startswith(p) for p in [
                "git ", "pip ", "python ", "npm ", "node ", "dir", "ls",
                "where ", "echo ", "ping ", "curl ",
            ]):
                return [{"skill": "terminal", "action": "run", "params": {"command": cmd}}]

        # Git rapido
        git_quick = [
            (["git status", "estado del repo", "que cambios tengo", "que hay sin commitear", "estado de git"], "status", {}),
            (["git diff", "muestrame los cambios", "que modifique", "que cambie"], "diff", {}),
            (["git log", "ultimos commits", "historial de commits", "ultimos comits"], "log", {"n": 5}),
            (["añade todo al staging", "anade todo al staging", "agrega todo al staging", "git add"], "add", {"paths": "."}),
            (["sube los cambios", "sube al remoto", "git push"], "push", {}),
            (["baja los cambios", "actualiza del remoto", "git pull"], "pull", {}),
        ]
        for frases, action, params in git_quick:
            if any(f in t for f in frases):
                return [{"skill": "git", "action": action, "params": params}]

        # ═══════════════════════════════════════════════════════════════════
        # ORDEN IMPORTANTE: indexar y office ANTES de docs.ask
        # ═══════════════════════════════════════════════════════════════════

        # 1. INDEXAR: "indexa X", "aprende X", "procesa X"
        m = re.search(
            r'\b(?:indexa|aprende|procesa|ingesta|guarda)\s+(?:el\s+|la\s+)?(?:archivo|pdf|documento|carpeta)\s+(.+)$',
            t,
        )
        if m:
            path = m.group(1).strip(" .,!?¡¿")
            path = re.sub(r'\s+en\s+.*$', '', path).strip()
            if path:
                action = "index_folder" if "carpeta" in t else "index_file"
                return [{"skill": "docs", "action": action, "params": {"path": path}}]

        m = re.search(
            r'\b(?:indexa|aprende|procesa|ingesta)\s+(?:mi|mis|el|la)\s+(cv|curriculum|currículum|apuntes|documentos|pdfs|notas)\b',
            t,
        )
        if m:
            from pathlib import Path
            home = Path.home()
            encontrados = []
            for carpeta in ["Downloads", "Documents", "Desktop"]:
                base = home / carpeta
                if not base.exists():
                    continue
                for ext in ("*.pdf", "*.docx", "*.txt"):
                    for f in base.glob(ext):
                        nombre = f.name.lower()
                        if "cv" in nombre or "curriculum" in nombre or "currículum" in nombre:
                            encontrados.append(str(f))
            if encontrados:
                return [{
                    "skill": "docs",
                    "action": "index_file",
                    "params": {"path": encontrados[0]},
                }]
            return None

        # 2. OFFICE: "hazme un word/excel/documento sobre X"
        m = re.search(
            r'\b(?:hazme|crea|genera|escribe|redacta)\s+(?:un\s+|una\s+)?(?:documento|informe|reporte|ensayo|word|docx)\s+(?:sobre|de|acerca\s+de|con|segun|según|basado\s+en)\s+(.+)$',
            t,
            re.IGNORECASE,
        )
        if m:
            desc = m.group(1).strip(" .,!?¡¿")
            if desc:
                return [{
                    "skill": "office",
                    "action": "create_doc",
                    "params": {"description": desc, "path": "", "title": ""},
                }]

        m = re.search(
            r'\b(?:hazme|crea|genera)\s+(?:un\s+|una\s+)?(?:excel|hoja\s+de\s+calculo|spreadsheet)\s+(?:sobre|de|con|para|segun|según)\s+(.+)$',
            t,
            re.IGNORECASE,
        )
        if m:
            desc = m.group(1).strip(" .,!?¡¿")
            if desc:
                return [{
                    "skill": "office",
                    "action": "create_xlsx",
                    "params": {"description": desc, "path": ""},
                }]

        # 3. LISTAR documentos indexados
        if any(p in t for p in [
            "que documentos tienes", "que documentos hay", "lista mis documentos",
            "que has indexado", "documentos indexados",
        ]):
            return [{"skill": "docs", "action": "list", "params": {}}]

        # 4. DOCS.ASK: preguntas sobre contenido
        docs_ask_triggers = [
            "que dice mi", "que dice el", "que dice la",
            "segun mi", "segun el", "segun la",
            "de que trata mi", "de que trata el",
            "que sabes sobre mi", "que sabes de mi",
            "que habilidades tengo", "que experiencia tengo",
            "busca en mi", "busca en mis",
            "en mi curriculum", "en mi cv", "mi curriculum", "mi cv",
            "en mis apuntes", "en mis pdfs", "en mis documentos",
        ]
        if any(p in t for p in docs_ask_triggers):
            return [{"skill": "docs", "action": "ask", "params": {"query": text}}]

        # Spotify
        m = re.search(r'\b(?:pon|ponme|reproduce|quiero\s+escuchar)\s+(.+?)\s+en\s+spotify\b', t)
        if m:
            return [{"skill": "spotify", "action": "play", "params": {"query": m.group(1).strip()}}]

        if "spotify" in t:
            if any(p in t for p in ["pausa", "pausar"]):
                return [{"skill": "spotify", "action": "pause", "params": {}}]
            if any(p in t for p in ["siguiente", "salta", "avanza"]):
                return [{"skill": "spotify", "action": "next", "params": {}}]
            if any(p in t for p in ["anterior", "vuelve atras", "regresa"]):
                return [{"skill": "spotify", "action": "previous", "params": {}}]
            if any(p in t for p in ["que esta sonando", "que suena", "que cancion"]):
                return [{"skill": "spotify", "action": "current", "params": {}}]

        if any(p in t for p in ["pausa la musica", "pausa la cancion", "para la musica"]):
            return [{"skill": "spotify", "action": "pause", "params": {}}]

        # "pon X" -> YouTube
        m = re.search(r'\b(?:pon|pong|ponme|pongme|reproduce|reprodus|ponle|quiero escuchar|quiero oir|escuchar)\s+(.+)$', t)
        if m:
            q = m.group(1).strip(" .,!?¡¿")
            q = re.sub(r'\b(en\s+youtube|en\s+yt|en\s+brave|en\s+chrome|en\s+spotify)\b', '', q).strip()
            exclude = [
                "volumen", "brillo", "pantalla", "musica al", "silencio", "mute",
                "alarma", "alarmas", "temporizador", "timer", "recordatorio",
                "recordar", "recuerda", "recuerdame", "recuérdame", "aviso",
                "avisame", "avísame", "minuto", "minutos", "segundo", "segundos",
                "hora", "horas",
            ]
            if q and not any(e in q for e in exclude):
                return [{"skill": "browser", "action": "search_youtube", "params": {"query": q}}]

        # Buscar archivo
        m = re.search(
            r'\b(?:busca|buscar|encuentra|encontrar|donde esta|donde se encuentra)\s+(?:el|la|mi|los|las)?\s*archivo\s+(.+)$',
            t,
        )
        if m:
            name = m.group(1).strip(" .,!?¡¿")
            name = re.sub(r'\b(de|del|la|el|los|las)\b', '', name).strip()
            if name:
                return [{"skill": "files", "action": "find_file", "params": {"name": name}}]

        # Buscar en google
        m = re.search(r'\b(?:busca|buscar|googlea)\s+en\s+google\s+(.+)$', t)
        if m:
            q = m.group(1).strip(" .,!?¡¿")
            if q:
                return [{"skill": "browser", "action": "search_google", "params": {"query": q}}]

        # Buscar en youtube
        m = re.search(r'\b(?:busca|buscar)\s+en\s+(?:youtube|yt)\s+(.+)$', t)
        if m:
            q = m.group(1).strip(" .,!?¡¿")
            if q:
                return [{"skill": "browser", "action": "search_youtube", "params": {"query": q}}]

        # Listar carpeta
        m = re.search(r'\b(?:lista|muestra|que hay en)\s+(?:la\s+)?carpeta\s+(?:de\s+)?(descargas|documentos|escritorio|imagenes|musica|videos)\b', t)
        if m:
            return [{"skill": "files", "action": "list_folder", "params": {"folder": m.group(1)}}]

        # PDF: convertir Word a PDF
        if re.search(r'\bpdf\b', t) and any(w in t for w in ["convierte", "convertir", "pasa", "exporta", "haz"]):
            m = re.search(r'\b(?:convierte|convertir|pasa|exporta)\s+(.+\.docx)\s+(?:a\s+|en\s+)?pdf', t, re.IGNORECASE)
            if m:
                return [{
                    "skill": "pdf",
                    "action": "from_docx",
                    "params": {"path": m.group(1).strip(), "output": ""},
                }]
            return [{"skill": "pdf", "action": "from_docx", "params": {"path": "", "output": ""}}]

        # PDF: listar
        if any(p in t for p in ["que pdfs tengo", "lista mis pdfs", "pdfs generados"]):
            return [{"skill": "pdf", "action": "list", "params": {}}]

        # Imagenes: generar
        m = re.search(
            r'\b(?:genera|crea|hazme|dibuja|imagina)\s+(?:(\d+)\s+)?(?:una?s?\s+|el\s+|la\s+|los\s+|las\s+)?(imagen(?:es)?|foto(?:s)?|dibujo(?:s)?|ilustracion(?:es)?|logo(?:s)?|moodboard|propuesta(?:s)?|opciones?(?:\s+visuales?)?|variantes?|estilos?(?:\s+visuales?)?|diseno(?:s)?|diseño(?:s)?)\s+(?:(de|sobre|con|para)\s+)?(.+)$',
            t,
            re.IGNORECASE,
        )
        if m:
            sustantivo = m.group(2).strip()
            preposicion = m.group(3) if m.group(3) else ""
            detalle = m.group(4).strip(" .,!?¡¿")
            if preposicion:
                prompt = f"{sustantivo} {preposicion} {detalle}".strip()
            else:
                prompt = f"{sustantivo} {detalle}".strip()
            if prompt:
                palabras_hq = [
                    "alta calidad", "profesional", "detallad", "hq",
                    "para presentacion", "para cliente", "final",
                    "moodboard", "estilos visuales", "opciones visuales",
                    "opciones de diseño", "propuesta", "variantes",
                    "4k", "2k", "para mi marca", "para marca",
                ]
                quality = "hq" if any(w in t for w in palabras_hq) else "fast"
                return [{
                    "skill": "image",
                    "action": "generate",
                    "params": {"prompt": prompt, "width": 1024, "height": 1024, "quality": quality},
                }]

        # Imagenes: listar
        if any(p in t for p in [
            "que imagenes tengo", "lista mis imagenes", "muestra mis imagenes",
            "imagenes generadas",
        ]):
            return [{"skill": "image", "action": "list", "params": {}}]

        # Office Word: leer documento
        m = re.search(
            r'\b(?:lee|leeme|abre)\s+(?:el\s+)?(?:documento|word|docx)\s+(.+\.docx)\b',
            t,
            re.IGNORECASE,
        )
        if m:
            return [{
                "skill": "office",
                "action": "read_doc",
                "params": {"path": m.group(1).strip()},
            }]

        # Office Excel: leer
        m = re.search(
            r'\b(?:lee|leeme|abre)\s+(?:el\s+)?(?:excel|xlsx)\s+(.+\.xlsx)\b',
            t,
            re.IGNORECASE,
        )
        if m:
            return [{
                "skill": "office",
                "action": "read_xlsx",
                "params": {"path": m.group(1).strip()},
            }]

        # Office PowerPoint: crear presentacion
        m = re.search(
            r'\b(?:hazme|crea|genera)\s+(?:una\s+|un\s+)?(?:presentacion|powerpoint|ppt|diapositivas)\s+(?:sobre|de|acerca\s+de|para)\s+(.+)$',
            t,
            re.IGNORECASE,
        )
        if m:
            desc = m.group(1).strip(" .,!?¡¿")
            if desc:
                return [{
                    "skill": "office",
                    "action": "create_ppt",
                    "params": {"description": desc, "path": ""},
                }]

        # Office PowerPoint: leer
        m = re.search(
            r'\b(?:lee|leeme|abre)\s+(?:la\s+)?(?:presentacion|powerpoint|pptx)\s+(.+\.pptx)\b',
            t,
            re.IGNORECASE,
        )
        if m:
            return [{
                "skill": "office",
                "action": "read_ppt",
                "params": {"path": m.group(1).strip()},
            }]

        # Telegram: enviar archivo
        if "telegram" in t and any(w in t for w in ["envia", "envíame", "enviame", "manda", "mandame", "mándame", "pasa", "pasame", "pásame", "comparte"]):
            tipo = ""
            if "pdf" in t:
                tipo = "pdf"
            elif "word" in t or "docx" in t or "documento" in t:
                tipo = "word"
            elif "excel" in t or "xlsx" in t or "hoja" in t:
                tipo = "excel"
            elif "imagen" in t or "foto" in t or "logo" in t or "jpg" in t or "png" in t:
                tipo = "imagen"
            elif "codigo" in t or "código" in t or ".py" in t:
                tipo = "codigo"
            return [{
                "skill": "telegram",
                "action": "send_last",
                "params": {"tipo": tipo},
            }]

        # Envio con path explicito por telegram
        m = re.search(
            r'\b(?:envia|enviame|envíame|manda|mandame|mándame|pasa|pasame|pásame)\s+([^\s]+\.\w{2,5})\s+(?:por|a)\s+telegram',
            t,
            re.IGNORECASE,
        )
        if m:
            return [{
                "skill": "telegram",
                "action": "send_file",
                "params": {"path": m.group(1).strip()},
            }]

        # Edit: modificar archivo
        es_edicion = any(w in t for w in ["modifica", "edita", "actualiza", "corrige", "cambia"])
        menciona_archivo = (
            "uploads" in t
            or ".docx" in t
            or ".xlsx" in t
            or ".txt" in t
            or ".pdf" in t
            or ".py" in t
            or ".md" in t
            or "\\" in t
            or "/" in t
        )
        if es_edicion and menciona_archivo:
            path = ""
            m_path = re.search(
                r'([A-Za-z]:\\[^\s]+\.\w{2,5}|[^\s]+\.(?:docx|xlsx|txt|pdf|py|md|csv))',
                t,
            )
            if m_path:
                path = m_path.group(1)
            m_instr = re.search(
                r'\b(?:cambiando|reemplazando|para\s+que\s+diga|que\s+diga|cambia)\s+(.+)$',
                t,
                re.IGNORECASE,
            )
            if m_instr:
                instruction = m_instr.group(1).strip(" .,!?¡¿")
                if path:
                    instruction = f"cambia {instruction}"
            else:
                instruction = text
            return [{
                "skill": "edit",
                "action": "modify",
                "params": {"path": path, "instruction": instruction, "output": ""},
            }]

        # Edit: "modifica el ultimo archivo de uploads cambiando X por Y"
        m = re.search(
            r'\b(?:modifica|edita|actualiza|corrige|cambia)\b.*?\b(?:uploads|subidos?)\b.*?\b(?:cambiando|por|para\s+que\s+diga)\s+(.+)$',
            t,
            re.IGNORECASE,
        )
        if m:
            return [{
                "skill": "edit",
                "action": "modify",
                "params": {"path": "", "instruction": m.group(0), "output": ""},
            }]

        # Edit: listar uploads
        if any(p in t for p in [
            "que archivos tengo en uploads",
            "lista los archivos de uploads",
            "lista mis uploads",
        ]):
            return [{"skill": "edit", "action": "list_uploads", "params": {}}]

        # Dev: crear y probar (ciclo completo)
        m = re.search(
            r'\b(?:crea|genera|escribe)\s+(?:un\s+|una\s+)?(?:archivo|script|programa|funcion)?\s*(.+?)\s+(?:en|como)\s+(.+)\b',
            t,
            re.IGNORECASE,
        )
        if m:
            desc = m.group(1).strip()
            path = m.group(2).strip()

            path = path.replace("barra", "/").replace("slash", "/")
            path = re.sub(r'\bpunto\s+py\b', '.py', path)
            path = re.sub(r'\bpunto\s+js\b', '.js', path)
            path = re.sub(r'\bpunto\s+java\b', '.java', path)
            path = re.sub(r'[,;]', '', path)
            path = re.sub(r'\s+', ' ', path).strip()
            path = path.strip(".,!?¡¿ ")
            path = re.sub(r'\s*/\s*', '/', path)
            path = re.sub(r'\s*\.\s*', '.', path)

            if " " in path:
                partes = path.split()
                path = partes[0] + "/" + "".join(partes[1:])

            if path.endswith(".p"):
                path = path[:-2] + ".py"
            elif path.endswith(".j"):
                path = path[:-2] + ".js"

            ext = ""
            if "." in path.split("/")[-1]:
                ext = path.rsplit(".", 1)[-1].lower()

            if ext in ("py", "js", "java"):
                if "/" not in path and "\\" not in path:
                    path = "sandbox/" + path
                lang = {"py": "python", "js": "javascript", "java": "java"}[ext]
                return [{
                    "skill": "dev",
                    "action": "create_and_test",
                    "params": {"description": desc, "language": lang, "path": path},
                }]

        # ═══════════════════════════════════════════════════════════════════
        # ENTERTAINMENT: control de reproduccion multimedia
        # ═══════════════════════════════════════════════════════════════════
        if any(p in t for p in [
            "pausa la pelicula", "pausa el video", "pausa la musica",
            "play", "reproduce", "continua la pelicula", "continua el video",
            "play_pause",
        ]) and any(p in t for p in ["pelicula", "video", "musica", "play", "pausa"]):
            return [{"skill": "entertainment", "action": "play_pause", "params": {}}]

        if any(p in t for p in [
            "siguiente cancion", "siguiente pista", "salta la cancion",
            "pasa la cancion", "next track",
        ]):
            return [{"skill": "entertainment", "action": "next_track", "params": {}}]

        if any(p in t for p in [
            "cancion anterior", "pista anterior", "vuelve la cancion",
            "anterior cancion",
        ]):
            return [{"skill": "entertainment", "action": "prev_track", "params": {}}]

        # ═══════════════════════════════════════════════════════════════════
        # ALARM: alarmas
        # ═══════════════════════════════════════════════════════════════════
        m = re.search(
            r'\b(?:pon|ponme|crea|configura|setea)\s+(?:una\s+)?alarma\s+(?:en\s+|a\s+las?\s+|para\s+)?(\d+)\s*(?:minutos?|min|m)\b',
            t, re.IGNORECASE,
        )
        if m:
            return [{"skill": "alarm", "action": "set", "params": {"minutes": int(m.group(1)), "text": "Alarma"}}]

        m = re.search(
            r'\b(?:despiertame|avisame|recuerdame)\s+en\s+(\d+)\s*(?:minutos?|min|m)\b',
            t, re.IGNORECASE,
        )
        if m:
            return [{"skill": "alarm", "action": "set", "params": {"minutes": int(m.group(1)), "text": "Recordatorio"}}]

        if any(p in t for p in [
            "que alarmas tengo", "lista mis alarmas", "mis alarmas",
        ]):
            return [{"skill": "alarm", "action": "list", "params": {}}]

        if any(p in t for p in [
            "cancela la alarma", "borra la alarma", "elimina la alarma",
            "quita la alarma",
        ]):
            return [{"skill": "alarm", "action": "cancel", "params": {}}]

        # ═══════════════════════════════════════════════════════════════════
        # PRODUCTIVITY: notas
        # ═══════════════════════════════════════════════════════════════════
        m = re.search(
            r'\b(?:guarda una nota|guarda nota|anota que|toma nota de|apunta que|apunta esto)(?:\s+que\s+diga)?\s*:?\s*(.+)$',
            text, re.IGNORECASE,
        )
        if m:
            nota = m.group(1).strip(" .,!?¡¿")
            if nota:
                return [{"skill": "productivity", "action": "save_note", "params": {"text": nota}}]

        if any(p in t for p in [
            "lee mis notas", "leeme las notas", "muestra mis notas",
            "que notas tengo", "mis notas",
        ]):
            return [{"skill": "productivity", "action": "read_notes", "params": {}}]

        if any(p in t for p in [
            "borra mis notas", "limpia las notas", "borra todas las notas",
        ]):
            return [{"skill": "productivity", "action": "clear_notes", "params": {}}]

        # ═══════════════════════════════════════════════════════════════════
        # TRANSLATE: traducir texto
        # ═══════════════════════════════════════════════════════════════════
        m = re.search(
            r'\b(?:traduce|traducir|traduceme)\s+(?:al\s+|a\s+|en\s+)?(ingles|inglés|english|espanol|español|spanish|frances|francés|french|aleman|alemán|german|italiano|italian|portugues|portugués|portuguese|japones|japonés|japanese|chino|chinese|ruso|russian)\s+(.+)$',
            text, re.IGNORECASE,
        )
        if m:
            idioma = m.group(1).lower().strip()
            texto_a_traducir = m.group(2).strip(" .,!?¡¿")
            mapa_idiomas = {
                "ingles": "en", "inglés": "en", "english": "en",
                "espanol": "es", "español": "es", "spanish": "es",
                "frances": "fr", "francés": "fr", "french": "fr",
                "aleman": "de", "alemán": "de", "german": "de",
                "italiano": "it", "italian": "it",
                "portugues": "pt", "portugués": "pt", "portuguese": "pt",
                "japones": "ja", "japonés": "ja", "japanese": "ja",
                "chino": "zh", "chinese": "zh",
                "ruso": "ru", "russian": "ru",
            }
            to = mapa_idiomas.get(idioma, "en")
            if texto_a_traducir:
                return [{"skill": "translate", "action": "text", "params": {"text": texto_a_traducir, "to": to}}]

        # ═══════════════════════════════════════════════════════════════════
        # WEATHER: clima
        # ═══════════════════════════════════════════════════════════════════
        m = re.search(
            r'\b(?:que\s+clima(?:\s+hace)?(?:\s+en)?|clima\s+en|como\s+esta\s+el\s+clima\s+en|temperatura\s+en)\s+([a-zA-Záéíóúñ][a-zA-Záéíóúñ\s]*?)(?:\s+hoy|\s+ahora|\?|$|\.)',
            text, re.IGNORECASE,
        )
        if m:
            ciudad = m.group(1).strip(" .,!?¡¿")
            if ciudad:
                return [{"skill": "weather", "action": "current", "params": {"city": ciudad}}]

        if any(p in t for p in [
            "que clima hace", "como esta el clima", "va a llover",
        ]):
            return [{"skill": "weather", "action": "current", "params": {"city": ""}}]
        return None

    def _normalize(self, result):
        """Convierte string o dict en dict {voice, display, thought}."""
        if isinstance(result, dict):
            if "voice" in result or "display" in result:
                return {
                    "voice": result.get("voice", ""),
                    "display": result.get("display", ""),
                    "thought": result.get("thought", ""),
                }
            return {
                "voice": result.get("voice", ""),
                "display": result.get("display", str(result)),
                "thought": result.get("thought", ""),
            }
        return {"voice": str(result), "display": str(result), "thought": ""}

    # ─── ROUTE PRINCIPAL ────────────────────────────────────────────────────

    def route(self, text):
        browser = self.skills["browser"]

        # 0. ¿Hay pregunta pendiente del agente?
        try:
            if self.agent.has_pending_question():
                if self._is_cancel(text):
                    self.agent.clear_pending()
                    return {"voice": "Cancelado.", "display": "Ok, cancelado.", "thought": ""}, False

                result = self.agent.resume(text, self.skills)
                if result:
                    return result, False
        except Exception as e:
            print(f"[ROUTER] Error resumiendo agente: {e}")
            self.agent.clear_pending()

        # Rechazar palabras sueltas que no son comandos validos
        t_stripped = text.lower().strip().strip(".,!?¡¿ ")
        if t_stripped in ("no", "si", "sí", "ok", "ya", "aha", "aja", "eh", "mmm"):
            return {"voice": "", "display": "", "thought": ""}, False

        # 1. Videos pendientes
        try:
            if browser.has_pending():
                if self._is_cancel(text):
                    browser.clear_pending()
                    return {"voice": "Cancelado.", "display": "Ok, cancelado.", "thought": ""}, False
                num = self._parse_choice(text)
                if num is not None:
                    result = self._safe_run(browser, "play_pending", {"index": num})
                    return self._normalize(result), False
                browser.clear_pending()
        except Exception as e:
            print(f"[ROUTER] Error en videos pendientes: {e}")

        # 2. Frases de memoria
        t_lower = text.lower().strip()
        if any(t_lower.startswith(p) for p in [
            "recuerda que ", "recuerda esto", "recuerda:",
            "memoriza que ", "memoriza:", "guarda en memoria ",
            "aprende que ", "no olvides que ",
        ]):
            return None, True

        # 3. Multi-objetivo explicito -> AGENTE PRIMERO (antes que quick_match)
        if self._is_multi_objetivo(text):
            try:
                agent_result = self.agent.run(text, self.skills)
                return agent_result, False
            except Exception as e:
                print(f"[ROUTER] Error en agente (multi): {e}")
                # Fallback: continuar con el flujo normal
                pass

        # 4. Pre-clasificador rapido (regex)
        try:
            quick = self._quick_match(text)
        except Exception as e:
            print(f"[ROUTER] Error en _quick_match: {e}")
            quick = None

        if quick == "__N8N_BUILDER__":
            try:
                agent_result = self.agent.run(text, self.skills)
                return agent_result, False
            except Exception as e:
                print(f"[ROUTER] Error en n8n builder: {e}")
                return {"voice": "El agente fallo.", "display": f"Error: {e}", "thought": ""}, False
        elif quick:
            actions = quick
        # 5. Razonamiento puro -> brain.chat (sin skills)
        elif self._is_pure_reasoning(text):
            return None, True
        # 6. Si es complejo -> AGENTE
        elif self._is_complex(text):
            try:
                agent_result = self.agent.run(text, self.skills)
                return agent_result, False
            except Exception as e:
                print(f"[ROUTER] Error en agente: {e}")
                return {"voice": "El agente fallo.", "display": f"Error del agente: {e}", "thought": ""}, False
        # 7. LLM clasificador normal
        else:
            try:
                intent = self.classifier.classify(text)
                actions = intent.get("actions", [])
            except Exception as e:
                print(f"[ROUTER] Error en clasificador: {e}")
                return {"voice": "Error clasificando.", "display": f"Error: {e}", "thought": ""}, False

        if not actions:
            return None, False

        if all(a.get("skill") == "none" for a in actions):
            return None, True

        results = []
        for act in actions:
            skill_name = act.get("skill", "none")
            if skill_name == "none":
                continue
            skill = self.skills.get(skill_name)
            if not skill:
                print(f"[ROUTER] Skill no encontrada: {skill_name}")
                continue

            action = act.get("action", "")
            params = act.get("params", {})

            # Fix: docs.ask siempre usa el texto original
            if skill_name == "docs" and action == "ask":
                params = {"query": text}

            result = self._safe_run(skill, action, params)
            if result:
                results.append(self._normalize(result))

        if not results:
            return None, True

        if len(results) == 1:
            return results[0], False

        return {
            "voice": " ".join(r["voice"] for r in results if r["voice"]),
            "display": "\n".join(r["display"] for r in results if r["display"]),
            "thought": " | ".join(r["thought"] for r in results if r["thought"]),
        }, False

    def _safe_run(self, skill, action, params):
        """Ejecuta skill.run() con timeout y captura de errores."""
        skill_name = getattr(skill, "name", "desconocida")
        try:
            future = _executor.submit(skill.run, action, params)
            try:
                result = future.result(timeout=SKILL_TIMEOUT)
                return result
            except FutureTimeout:
                print(f"[ROUTER] Timeout: {skill_name}.{action} (> {SKILL_TIMEOUT}s)")
                return {
                    "voice": f"La accion {skill_name} tardo demasiado.",
                    "display": f"Timeout de {skill_name}.{action} tras {SKILL_TIMEOUT}s.",
                    "thought": "",
                }
        except Exception as e:
            print(f"[ROUTER] Error en {skill_name}.{action}: {e}")
            import traceback
            traceback.print_exc()
            # FIX: sin , False — debe devolver solo un dict
            return {
                "voice": f"Error en {skill_name}.",
                "display": f"Error ejecutando {skill_name}.{action}: {e}",
                "thought": "",
            }