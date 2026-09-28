# Senna - Asistente Personal con IA Local

Asistente de escritorio con IA local que controla tu PC, automatiza
tareas, se integra con servicios externos y ejecuta pipelines CAD/BIM.

## Caracteristicas

- **38 skills operativas** con **338 acciones** en total
- **Multiagente profesional** - Supervisor + DEV / RESEARCH / EXECUTE / CHAT
- **RAG local** - Indexa tus documentos y pregunta sobre ellos
- **Pipeline CAD/BIM** - DWG -> analisis -> muros 3D -> IFC (Revit/ArchiCAD)
- **Retoque profesional** - Quitar fondo, upscaling 4x, sombras, watermark
- **Transcripcion con IA** - Whisper local (multiidioma)
- **Vision artificial** - Analizar pantalla e imagenes (OCR, descripcion, comparacion)
- **Modelado 3D** - Blender + FreeCAD para arquitectura y diseno interior
- **Generacion de imagenes** - Flux Schnell (Cloudflare) + Agnes AI
- **Voz + Wake word** - "Oye Senna" (backend Whisper local listo, integracion GUI en desarrollo)
- **GUI moderna** - Panel de sistema, credenciales, historial y modelos
- **100% local** - Ollama + ChromaDB, sin enviar datos a la nube

## Skills por categoria

| Categoria | Skills | Ejemplos |
|---|---|---|
| Fundamentales | 7 | system, desktop, browser, files, clipboard |
| Productividad | 10 | office, edit, pdf, gmail, calendar, notion, n8n |
| Dev y tecnologia | 3 | dev, git, vision |
| Multimedia | 5 | image, audio, video, retouch, education |
| CAD y 3D | 4 | dwg, freecad, blender, maps |
| Integraciones | 3 | spotify, canva, telegram |
| Entretenimiento | 6 | frases, chiste, entertainment, weather, alarm, macro |

Ver [SKILLS.md](SKILLS.md) para el catalogo completo.

## Requisitos

- **Windows 10/11** (64 bits)
- **Python 3.10+** (probado con 3.14)
- **Ollama** con modelos descargados:
  - llama3.2:3b (rapido, chat)
  - qwen2.5-coder:7b (codigo, documentos)
  - qwen2.5vl:7b (vision, el mejor)
  - llava-phi3:latest (vision alternativa)
  - nomic-embed-text (embeddings RAG)
- **RAM:** 8 GB minimo, 16 GB recomendado
- **GPU:** opcional pero muy recomendado (RTX 3060+)
- **Software externo** (opcional):
  - Blender 4.x (para skill blender)
  - FreeCAD 1.x (para skill freecad)
  - ODA File Converter (para DWG <-> DXF)
  - Upscayl (para upscaling de imagenes)
  - n8n (para skill n8n)

## Instalacion

### Opcion A: Instalador

Descarga SennaSetup.exe y ejecutalo.

### Opcion B: Manual (dev)

    git clone https://github.com/RafaelCort25/jarvis-asistente.git C:/JARVIS
    cd C:/JARVIS
    python -m venv venv
    .\venv\Scripts\Activate.ps1
    pip install -r requirements.txt
    python -m uvicorn api_server:app --port 8000

## Uso

1. Arranca Ollama: ollama serve
2. Arranca Senna: & "C:/jarvis-electron/dist/Senna.exe"
3. Escribe o habla. Ejemplos:
   - "Que hora es?"
   - "Hazme un script que sume dos numeros"
   - "Analiza el codigo de skills/dev.py"
   - "Quita el fondo de esta foto"
   - "Transcribe este audio"
   - "Cuadro de superficies del plano X.dxf"
   - "Renderiza 8 angulos del modelo 3D"
   - "Apunta en Notion que tengo reunion el lunes"

## Configuracion

### Modelos por agente

Abre Sistema -> Agentes Multiagente y elige el modelo de cada uno.

### Integraciones

Crea un archivo .env.personal en la raiz del proyecto con:

    NOTION_TOKEN=tu_token_aqui
    PEXELS_API_KEY=tu_key_aqui

Y en .env:

    SPOTIFY_CLIENT_ID=...
    SPOTIFY_CLIENT_SECRET=...
    SPOTIFY_REFRESH_TOKEN=...

Otras integraciones (Gmail, Canva, n8n) usan archivos especificos:

- .env.gmail.tmp - Gmail (usuario + app password)
- .env.canva.tmp - Canva (OAuth client_id + secret)
- .env.n8n.tmp - n8n (url + API key)

## API interna (FastAPI)

El servidor `api_server.py` expone los siguientes endpoints principales:

| Endpoint | Metodo | Descripcion |
|---|---|---|
| `/health` | GET | Estado del servidor |
| `/chat` | POST | Enviar comando al asistente (multiagente) |
| `/skills/list` | GET | Catalogo de las 38 skills con metadata completa |
| `/skills/combos` | GET | Combos destacados (flujos multi-skill) |
| `/onboarding/status` | GET | Estado del sistema (Python, Ollama, modelos, skills) |
| `/onboarding/mark_done` | POST | Marca el onboarding como completado |
| `/conversations/list` | GET | Lista de conversaciones guardadas |
| `/models/list` | GET | Modelos Ollama disponibles |
| `/models/set` | POST | Cambiar modelo activo |
| `/wake/enable` | POST | Activar deteccion de wake word "Oye Senna" |
| `/wake/disable` | POST | Desactivar wake word |
| `/wake/status` | GET | Estado del listener |
| `/wake/poll` | GET | Polling de deteccion (consume evento) |

La UI de escritorio (`jarvis-orb.html`) consume estos endpoints via fetch.

## Estructura del proyecto

    C:\JARVIS\
    |-- api_server.py        # Servidor FastAPI
    |-- core/                # Nucleo: router, agentes, RAG, config
    |-- skills/              # 38 skills modulares
    |-- sandbox/             # Archivos generados (imagenes, videos, docs...)
    |-- scripts/             # Utilidades (setup, generadores)
    |-- tools/               # Binarios externos (ffmpeg, etc.)
    |-- venv/                # Entorno virtual de Python
    |-- requirements.txt
    |-- SKILLS.md            # Catalogo de skills (generado auto)
    |-- README.md            # Este archivo

## Desarrollo

    # Activar entorno
    .\venv\Scripts\Activate.ps1

    # Regenerar SKILLS.md tras anadir/modificar una skill
    python scripts\generate_skills_md.py

    # Verificar que las 37 skills responden a sus comandos (routing)
    python scripts\verify_routing.py

    # Smoke test completo (listados + acciones)
    python scripts\smoke_test.py

    # Arrancar servidor API
    python -m uvicorn api_server:app --port 8000 --reload

## Documentacion adicional

- [SKILLS.md](SKILLS.md) - Catalogo de las 38 skills
- [DISCLAIMER.md](DISCLAIMER.md) - Aviso legal
- [PRIVACY.md](PRIVACY.md) - Politica de privacidad
- [TERMS.md](TERMS.md) - Terminos de uso

---

**Ultima actualizacion:** 2026-09-28 (rev. verificacion completa de skills)
