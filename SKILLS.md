# SKILLS.md — Catálogo completo de skills de Nitro

Documentación de las 30 skills operativas de JARVIS/Nitro, con acciones, parámetros, ejemplos y niveles de riesgo.

**Última actualización:** Bloque 1 de auditoría (30/30 skills integradas).

**Niveles de riesgo:**
- 🟢 **low** — No requiere confirmación. Solo lectura o acciones inocuas.
- 🟡 **medium** — Pide confirmación al usuario antes de ejecutar.
- 🔴 **high** — Pide confirmación con advertencia (acciones destructivas o irreversibles).

---

## 📑 Índice por categoría

1. [Fundamentales](#fundamentales)
2. [Dev y Productividad](#dev-y-productividad)
3. [Contenido](#contenido)
4. [Comunicación](#comunicación)
5. [Automatización](#automatización)
6. [Integraciones Externas](#integraciones-externas)
7. [Entretenimiento](#entretenimiento)

---

## Fundamentales

### `system` 🖥️
Sistema, discos, hora, fecha, limpieza.

| Acción | Riesgo | Parámetros | Descripción |
|---|---|---|---|
| `time` | 🟢 | — | Hora actual |
| `date` | 🟢 | — | Fecha actual |
| `disk_info` | 🟢 | — | Info de todos los discos |
| `clean_temp` | 🔴 | — | Limpia temporales de Windows |
| `empty_recycle` | 🔴 | — | Vacía la papelera |
| `list_big_files` | 🟢 | `folder` (str), `min_mb` (int) | Archivos grandes |
| `list_startup` | 🟢 | — | Programas de inicio de Windows |

**Ejemplos:**
- "¿Qué hora es?" → `system.time`
- "¿Cuánto espacio tengo?" → `system.disk_info`
- "Lista los archivos grandes de descargas" → `system.list_big_files(folder="descargas")`
- "Limpia los temporales" → `system.clean_temp`

---

### `desktop` 🪟
Control de apps, volumen, carpetas.

| Acción | Riesgo | Parámetros | Descripción |
|---|---|---|---|
| `open_app` | 🟢 | `app` (str) | Abre app conocida |
| `open_folder` | 🟢 | `path` (str) | Abre carpeta |
| `volume_up` | 🟢 | — | Sube volumen |
| `volume_down` | 🟢 | — | Baja volumen |
| `mute` | 🟢 | — | Silencia |

**Apps soportadas:** `brave`, `chrome`, `notepad`, `calculadora`, `explorador`, `paint`, `cmd`, `spotify`

**Ejemplos:**
- "Abre Chrome" → `desktop.open_app(app="chrome")`
- "Abre la calculadora" → `desktop.open_app(app="calculadora")`
- "Sube el volumen" → `desktop.volume_up`
- "Silencia" → `desktop.mute`

---

### `browser` 🌐
Búsquedas y reproducción en YouTube.

| Acción | Riesgo | Parámetros | Descripción |
|---|---|---|---|
| `search_google` | 🟢 | `query` (str) | Busca en Google |
| `search_youtube` | 🟢 | `query` (str) | Busca en YouTube |
| `play_pending` | 🟢 | `index` (int) | Reproduce video pendiente |
| `has_pending` | 🟢 | — | ¿Hay videos pendientes? |
| `clear_pending` | 🟢 | — | Limpia pendientes |

**Ejemplos:**
- "Busca en Google recetas de pasta" → `browser.search_google`
- "Busca en YouTube música relajante" → `browser.search_youtube`
- "Pon música de jazz" → `browser.search_youtube`

---

### `files` 📁
Búsqueda y listado de archivos.

| Acción | Riesgo | Parámetros | Descripción |
|---|---|---|---|
| `find_file` | 🟢 | `name` (str) | Busca archivo por nombre |
| `list_folder` | 🟢 | `folder` (str) | Lista carpeta común |

**Carpetas soportadas:** `descargas`, `documentos`, `escritorio`, `imagenes`, `musica`, `videos`

**Ejemplos:**
- "Busca el archivo informe.pdf" → `files.find_file`
- "¿Qué hay en la carpeta de descargas?" → `files.list_folder`

---

### `clipboard` 📋
Portapapeles.

| Acción | Riesgo | Parámetros | Descripción |
|---|---|---|---|
| `read` | 🟢 | — | Lee el portapapeles |
| `write` | 🟢 | `text` (str) | Escribe en portapapeles |

**Ejemplos:**
- "¿Qué tengo copiado?" → `clipboard.read`
- "Copia esto: hola mundo" → `clipboard.write(text="hola mundo")`

---

### `productivity` 📝
Notas rápidas.

| Acción | Riesgo | Parámetros | Descripción |
|---|---|---|---|
| `save_note` | 🟢 | `text` (str) | Guarda nota |
| `read_notes` | 🟢 | — | Lee todas las notas |
| `clear_notes` | 🟡 | — | Borra todas las notas |

**Ejemplos:**
- "Guarda una nota que diga comprar pan" → `productivity.save_note(text="comprar pan")`
- "Lee mis notas" → `productivity.read_notes`
- "Borra mis notas" → `productivity.clear_notes`

---

### `weather` ☀️
Clima actual.

| Acción | Riesgo | Parámetros | Descripción |
|---|---|---|---|
| `current` | 🟢 | `city` (str) | Clima de una ciudad |

**Ejemplos:**
- "¿Qué clima hace en Lima?" → `weather.current(city="Lima")`
- "¿Cómo está el clima en Cusco?" → `weather.current(city="Cusco")`
- "¿Va a llover?" → `weather.current(city="")` (usa ubicación por defecto)

---

### `alarm` ⏰
Alarmas y recordatorios temporales.

| Acción | Riesgo | Parámetros | Descripción |
|---|---|---|---|
| `set` | 🟢 | `minutes` (int), `text` (str) | Programa alarma |
| `list` | 🟢 | — | Lista alarmas activas |
| `cancel` | 🟢 | — | Cancela alarmas |

**Ejemplos:**
- "Pon una alarma en 5 minutos" → `alarm.set(minutes=5, text="Alarma")`
- "Despiértame en 10 minutos" → `alarm.set(minutes=10, text="Recordatorio")`
- "¿Qué alarmas tengo?" → `alarm.list`

---

### `scheduler` 📅
Tareas programadas recurrentes.

| Acción | Riesgo | Parámetros | Descripción |
|---|---|---|---|
| `add_once` | 🟡 | `minutes` (int), `task` (str) | Tarea única |
| `add_daily` | 🟡 | `hour` (int), `minute` (int), `task` (str) | Tarea diaria |
| `add_interval` | 🟡 | `interval_minutes` (int), `task` (str) | Tarea cada N min |
| `list` | 🟢 | — | Lista tareas programadas |
| `cancel` | 🟡 | — | Cancela tareas |

**Ejemplos:**
- "Todos los días a las 9 haz backup" → `scheduler.add_daily(hour=9, task="backup")`
- "En 5 minutos abre notepad" → `scheduler.add_once(minutes=5, task="notepad")`
- "¿Qué tareas tengo programadas?" → `scheduler.list`

---

### `translate` 🌍
Traducción de texto.

| Acción | Riesgo | Parámetros | Descripción |
|---|---|---|---|
| `text` | 🟢 | `text` (str), `to` (str) | Traduce texto |

**Idiomas:** `en`, `es`, `fr`, `de`, `it`, `pt`, `ja`, `zh`, `ru`

**Ejemplos:**
- "Traduce al inglés hola mundo" → `translate.text(text="hola mundo", to="en")`
- "Traduce al francés buenos días" → `translate.text(text="buenos días", to="fr")`

---

### `vision` 👁️
Análisis de pantalla con IA de visión.

| Acción | Riesgo | Parámetros | Descripción |
|---|---|---|---|
| `describe_screen` | 🟢 | — | Describe lo que se ve |
| `explain_screen_code` | 🟢 | — | Explica código visible |

**Ejemplos:**
- "¿Qué hay en mi pantalla?" → `vision.describe_screen`
- "Describe lo que ves" → `vision.describe_screen`
- "Explica el código de mi pantalla" → `vision.explain_screen_code`

---

### `entertainment` 🎬
Control de reproducción multimedia del sistema.

| Acción | Riesgo | Parámetros | Descripción |
|---|---|---|---|
| `play_pause` | 🟢 | — | Play/Pausa |
| `next_track` | 🟢 | — | Siguiente pista |
| `prev_track` | 🟢 | — | Pista anterior |

**Nota:** No confundir con `spotify.*`. Este controla reproductores del sistema (VLC, navegador, etc.).

**Ejemplos:**
- "Pausa la película" → `entertainment.play_pause`
- "Siguiente canción" → `entertainment.next_track`
- "Canción anterior" → `entertainment.prev_track`

---

## Dev y Productividad

### `dev` 💻
Generación, análisis y testing de código.

| Acción | Riesgo | Parámetros | Descripción |
|---|---|---|---|
| `generate_code` | 🟢 | `description`, `language` | Genera código |
| `create_and_test` | 🟡 | `description`, `language`, `path` | Genera + guarda + ejecuta |
| `write_file` | 🟡 | `path`, `content` | Escribe archivo |
| `run_file` | 🟡 | `path` | Ejecuta archivo |
| `review_file` | 🟢 | `path` | Revisa archivo |
| `review_project` | 🟢 | `path` | Revisa proyecto |
| `explain` | 🟢 | `path` | Explica código |
| `find_issues` | 🟢 | `path` | Encuentra problemas |
| `review_to_excel` | 🟡 | `path`, `output` | Revisión → Excel con bugs |
| `review_to_word` | 🟡 | `path`, `output` | Revisión → Word con análisis |

**Ejemplos:**
- "Crea un archivo .py que sume dos números en sandbox/suma.py" → `dev.create_and_test`
- "Revisa este archivo codigo.py y hazme un excel con los bugs" → `dev.review_to_excel`
- "Explícame sandbox/test.py" → `dev.explain`

---

### `terminal` 💲
Ejecución de comandos seguros.

| Acción | Riesgo | Parámetros | Descripción |
|---|---|---|---|
| `run` | 🔴 | `command` (str) | Ejecuta comando |
| `suggest` | 🟢 | `description` (str) | Sugiere comando |

**Comandos permitidos:** `git`, `pip`, `python`, `npm`, `node`, `dir`, `ls`, `where`, `echo`, `ping`, `curl`

**Ejemplos:**
- "Ejecuta git status" → `terminal.run(command="git status")`
- "Ejecuta pip list" → `terminal.run(command="pip list")`

---

### `git` 🔀
Control de versiones rápido.

| Acción | Riesgo | Parámetros | Descripción |
|---|---|---|---|
| `status` | 🟢 | — | Estado del repo |
| `diff` | 🟢 | — | Cambios sin commitear |
| `log` | 🟢 | `n` (int) | Últimos commits |
| `add` | 🟡 | `paths` (str) | Staging |
| `push` | 🟡 | — | Sube al remoto |
| `pull` | 🟡 | — | Baja del remoto |

**Ejemplos:**
- "¿Qué cambios tengo?" → `git.status`
- "Muéstrame los últimos commits" → `git.log(n=5)`
- "Sube los cambios" → `git.push`

---

### `office` 📄
Documentos Word, Excel, PowerPoint.

| Acción | Riesgo | Parámetros | Descripción |
|---|---|---|---|
| `create_doc` | 🟡 | `description`, `path`, `title` | Crea Word |
| `create_xlsx` | 🟡 | `description`, `path` | Crea Excel |
| `create_ppt` | 🟡 | `description`, `path` | Crea PowerPoint |
| `read_doc` | 🟢 | `path` | Lee Word |
| `read_xlsx` | 🟢 | `path` | Lee Excel |
| `read_ppt` | 🟢 | `path` | Lee PowerPoint |

**Ejemplos:**
- "Hazme un Word sobre el cambio climático" → `office.create_doc`
- "Crea un Excel con gastos mensuales" → `office.create_xlsx`
- "Hazme una presentación sobre el mar" → `office.create_ppt`

---

### `pdf` 📕
Conversión a PDF.

| Acción | Riesgo | Parámetros | Descripción |
|---|---|---|---|
| `from_docx` | 🟡 | `path`, `output` | Word → PDF |
| `list` | 🟢 | — | Lista PDFs generados |

**Ejemplos:**
- "Convierte informe.docx a PDF" → `pdf.from_docx(path="informe.docx")`
- "¿Qué PDFs tengo?" → `pdf.list`

---

### `spotify` 🎵
Control de Spotify.

| Acción | Riesgo | Parámetros | Descripción |
|---|---|---|---|
| `play` | 🟢 | `query` (str) | Reproduce |
| `pause` | 🟢 | — | Pausa |
| `next` | 🟢 | — | Siguiente |
| `previous` | 🟢 | — | Anterior |
| `current` | 🟢 | — | ¿Qué suena? |

**Ejemplos:**
- "Pon jazz en Spotify" → `spotify.play(query="jazz")`
- "¿Qué está sonando?" → `spotify.current`

---

## Contenido

### `image` 🎨
Generación de imágenes con doble motor (fast/HQ).

| Acción | Riesgo | Parámetros | Descripción |
|---|---|---|---|
| `generate` | 🟡 | `prompt`, `width`, `height`, `quality` | Genera imagen |
| `list` | 🟢 | — | Lista imágenes |
| `to_word` | 🟡 | `prompt`, `count`, `title` | Imágenes → Word |

**Calidades:** `fast` (rápido), `hq` (alta calidad)

**Ejemplos:**
- "Genera una imagen de un gato" → `image.generate(quality="fast")`
- "Genera 4 logos profesionales para mi marca" → `image.generate(count=4, quality="hq")`
- "Hazme un Word con imágenes de paisajes" → `image.to_word`

---

### `docs` 📚
RAG — preguntas sobre documentos indexados.

| Acción | Riesgo | Parámetros | Descripción |
|---|---|---|---|
| `index_file` | 🟡 | `path` (str) | Indexa archivo |
| `index_folder` | 🟡 | `path` (str) | Indexa carpeta |
| `list` | 🟢 | — | Lista documentos |
| `ask` | 🟢 | `query` (str) | Pregunta sobre docs |
| `ask_to_word` | 🟡 | `query`, `title` | Pregunta → Word |

**Ejemplos:**
- "Indexa mi CV" → `docs.index_file`
- "¿Qué dice mi CV sobre mi experiencia?" → `docs.ask`
- "Hazme un Word según mi CV" → `docs.ask_to_word`

---

### `edit` ✏️
Edición de archivos subidos.

| Acción | Riesgo | Parámetros | Descripción |
|---|---|---|---|
| `modify` | 🟡 | `path`, `instruction`, `output` | Modifica archivo |
| `list_uploads` | 🟢 | — | Lista uploads |

**Ejemplos:**
- "Modifica el último archivo de uploads cambiando 'hola' por 'adiós'" → `edit.modify`
- "¿Qué archivos tengo en uploads?" → `edit.list_uploads`

---

### `education` 🎓
PSeInt, diagramas, conversión de código.

| Acción | Riesgo | Parámetros | Descripción |
|---|---|---|---|
| `pseint` | 🟡 | `description` (str) | Algoritmo PSeInt |
| `diagram` | 🟡 | `description`, `kind` | Diagrama |
| `convert` | 🟢 | `code`, `to_language` | Convierte código |

**Tipos de diagrama:** `flowchart`, `sequence`, `class`, `state`, `er`

**Ejemplos:**
- "Hazme un algoritmo PSeInt que sume dos números" → `education.pseint`
- "Hazme un diagrama de flujo de login" → `education.diagram(kind="flowchart")`
- "Hazme un diagrama ER de una tienda" → `education.diagram(kind="er")`

---

## Comunicación

### `telegram` 📱
Envío de archivos por Telegram.

| Acción | Riesgo | Parámetros | Descripción |
|---|---|---|---|
| `send_last` | 🟡 | `tipo` (str) | Envía último de tipo |
| `send_file` | 🟡 | `path` (str) | Envía archivo específico |

**Tipos:** `pdf`, `word`, `excel`, `imagen`, `codigo`

**Ejemplos:**
- "Envíame el último PDF por Telegram" → `telegram.send_last(tipo="pdf")`
- "Manda informe.docx por Telegram" → `telegram.send_file(path="informe.docx")`

---

### `gmail` ✉️
Correo Gmail.

| Acción | Riesgo | Parámetros | Descripción |
|---|---|---|---|
| `list_recent` | 🟢 | `n` (int) | Últimos correos |
| `read` | 🟢 | `uid` (str) | Lee correo |
| `search` | 🟢 | `query` (str) | Busca correos |
| `send` | 🟡 | `to`, `subject`, `body` | Envía correo |
| `count_unread` | 🟢 | — | Cuenta sin leer |

**Ejemplos:**
- "Lee mis correos" → `gmail.list_recent(n=5)`
- "¿Cuántos correos sin leer tengo?" → `gmail.count_unread`
- "Busca correos de Amazon" → `gmail.search(query="Amazon")`
- "Envía un correo a juan@x.com diciendo hola" → `gmail.send`

---

## Automatización

### `macro` 🎥
Grabación y reproducción de secuencias.

| Acción | Riesgo | Parámetros | Descripción |
|---|---|---|---|
| `start` | 🟡 | `name` (str) | Empieza a grabar |
| `stop` | 🟡 | — | Para de grabar |
| `play` | 🟡 | `name` (str) | Reproduce macro |
| `list` | 🟢 | — | Lista macros |
| `delete` | 🔴 | `name` (str) | Borra macro |

**Nota:** Skill blindada con verificación de ventana activa, lista negra y delay.

**Ejemplos:**
- "Empieza a grabar macro abrir_chrome" → `macro.start`
- "Para de grabar" → `macro.stop`
- "Ejecuta macro abrir_chrome" → `macro.play`

---

### `n8n` ⚙️
Automatización de workflows con n8n.

| Acción | Riesgo | Parámetros | Descripción |
|---|---|---|---|
| `list_workflows` | 🟢 | — | Lista workflows |
| `get_workflow` | 🟢 | `id_or_name` | Detalle workflow |
| `activate` | 🟡 | `id_or_name` | Activa |
| `deactivate` | 🟡 | `id_or_name` | Desactiva |
| `delete_workflow` | 🔴 | `id_or_name` | Borra |
| `list_executions` | 🟢 | — | Últimas ejecuciones |
| `search_templates` | 🟢 | `query`, `limit` | Busca 12k+ templates |
| `get_template` | 🟢 | `id` | Detalle template |
| `import_template` | 🟡 | `id`, `name` | Importa template |
| `create_workflow` | 🟡 | `description`, `name` | Crea desde cero con LLM |

**Ejemplos:**
- "¿Qué workflows tengo en n8n?" → `n8n.list_workflows`
- "Activa el workflow Backup diario" → `n8n.activate`
- "Busca templates de WhatsApp" → `n8n.search_templates`
- "Crea un workflow que cada día a las 9 me mande un Telegram" → `n8n.create_workflow`
- "Créame un chatbot de WhatsApp para una clínica" → agente con flujo conversacional (Fase 4)

---

## Integraciones Externas
### `dwg` 📐
Lectura, análisis y generación de planos DWG/DXF.

| Acción | Riesgo | Parámetros | Descripción |
|---|---|---|---|
| `convert_to_dxf` | 🟡 | `path` | DWG → DXF |
| `convert_to_dwg` | 🟡 | `path` | DXF → DWG |
| `analyze` | 🟢 | `path` | Estadísticas del plano |
| `list_layers` | 🟢 | `path` | Capas |
| `list_texts` | 🟢 | `path` | Textos limpios |
| `list_blocks` | 🟢 | `path` | Bloques |
| `list_rooms` | 🟢 | `path` | Ambientes (por textos) |
| `info` | 🟢 | `path` | Dimensiones |
| `extract_layer` | 🟢 | `path`, `layer_name` | Extrae capa a DXF limpio |
| `annotate` | 🟡 | `path`, `output`, `offset` | Acotado automático |
| `extract_walls_3d` | 🟡 | `path`, `height` | Muros a STEP |
| `extract_all_layers_3d` | 🟡 | `path`, `output` | Todas las capas a STEP |
| `add_hatch` | 🟡 | `path`, `output` | Relleno rayado de muros (ANSI31) |
| `extract_rooms_with_areas` | 🟢 | `path` | Lista ambientes con sus áreas en m² |
| `cuadro_superficies_excel` | 🟡 | `path`, `output`, `titulo` | Genera Excel con cuadro de superficies |
| `export_ifc` | 🟡 | `path`, `output`, `nombre_proyecto`, `altura`, `grosor` | Exporta muros a formato IFC (BIM) |
| `export_ifc_full` | 🟡 | `path`, `output`, `puertas`, `ventanas`, `nombre_proyecto`, `altura`, `grosor` | Exporta muros + puertas + ventanas a IFC (BIM) |

**Requiere:** ODA File Converter + shapely + openpyxl.

**Límite conocido:** la extracción automática de ambientes funciona con planos bien dibujados (muros cerrados). Planos con gaps de puertas grandes requieren detección manual.

**Ejemplos:**
- "Analiza mi_plano.dwg" → `dwg.analyze`
- "Lista los ambientes del plano" → `dwg.extract_rooms_with_areas`
- "Cuadro de superficies del plano test_plan_fixture" → `dwg.cuadro_superficies_excel`
- "Acota el plano" → `dwg.annotate`
- "Convierte los muros a 3D" → `dwg.extract_walls_3d`

---

### `canva` 🎨
Diseño gráfico con Canva.

| Acción | Riesgo | Parámetros | Descripción |
|---|---|---|---|
| `authorize` | 🟢 | — | Conecta Canva (OAuth) |
| `whoami` | 🟢 | — | Info de conexión |
| `list_designs` | 🟢 | `limit` (int) | Lista diseños |
| `get_design` | 🟢 | `id` (str) | Detalle diseño |
| `create_design` | 🟡 | `design_type`, `title` | Crea diseño |
| `export_design` | 🟢 | `id`, `format` | Exporta |
| `list_assets` | 🟢 | — | Lista assets |
| `upload_asset_from_url` | 🟡 | `url`, `name` | Sube imagen |

**Tipos válidos:** `doc`, `email`, `presentation`, `whiteboard` (los demás requieren Enterprise)

**Ejemplos:**
- "¿Qué diseños tengo en Canva?" → `canva.list_designs`
- "Crea una presentación sobre el mar" → `canva.create_design(design_type="presentation", title="el mar")`
- "Exporta el diseño DAHVe_mH89A a PDF" → `canva.export_design`
- "Conecta Canva" → `canva.authorize`

---

### `freecad` 🏗️
Geometría CAD, planos técnicos, export DXF.

| Acción | Riesgo | Parámetros | Descripción |
|---|---|---|---|
| `new_document` | 🟡 | `name` | Nuevo documento |
| `add_rectangle` | 🟢 | `x1`, `y1`, `x2`, `y2`, `label` | Rectángulo |
| `add_line` | 🟢 | `x1`, `y1`, `z1`, `x2`, `y2`, `z2`, `label` | Línea |
| `add_circle` | 🟢 | `cx`, `cy`, `radius`, `label` | Círculo |
| `add_text` | 🟢 | `x`, `y`, `text`, `label` | Texto |
| `add_wall` | 🟢 | `x1`, `y1`, `x2`, `y2`, `label` | Muro |
| `list_objects` | 🟢 | — | Lista objetos |
| `export_dxf` | 🟡 | `path` | Exporta DXF |
| `export_pdf` | 🟡 | `path` | Exporta PDF |
| `save_as` | 🟡 | `path` | Guarda FCStd |
| `clear_workspace` | 🔴 | — | Limpia workspace |
| `add_room_labels` | 🟡 | `labels` (list) | Etiquetas de ambientes en 3D |
| `add_level_dimensions` | 🟡 | `height`, `num_floors` | Cotas de nivel (+0.00, +2.80...) |

**Nota:** cada acción tarda 2-4s porque abre `freecadcmd` como subproceso.

**Ejemplos:**
- "Nuevo plano" → `freecad.new_document`
- "Dibuja un rectángulo de 4x3" → `freecad.add_rectangle(x2=4, y2=3)`
- "Dibuja un círculo de radio 0.5" → `freecad.add_circle(radius=0.5)`
- "Exporta el plano a DXF" → `freecad.export_dxf`

---

### `maps` 🗺️
Búsqueda de edificios reales y generación de modelos 3D.

| Acción | Riesgo | Parámetros | Descripción |
|---|---|---|---|
| `search` | 🟢 | `query` | Busca lugar |
| `get_building` | 🟢 | `query` | Info del edificio |
| `create_model` | 🟡 | `query`, `output`, `formato`, `altura` | Modelo simple (prisma) |
| `create_detailed` | 🟡 | `query`, `num_pisos`, `altura`, `wall_thickness` | Modelo detallado |

**Fuente:** OpenStreetMap + Nominatim + Overpass. **No requiere API key.**

**Formatos:** `step` (3D), `dxf` (2D)

**Ejemplos:**
- "Info del Sheraton Lima Historic Center" → `maps.get_building`
- "Modela el Sheraton Lima" → `maps.create_model`
- "Hazme un modelo detallado de la Catedral de Lima" → `maps.create_detailed`

---

### `blender` 🎬
Renderizado de STEP a PNG.

| Acción | Riesgo | Parámetros | Descripción |
|---|---|---|---|
| `render_step` | 🟢 | `step_path`, `output`, `res_x`, `res_y`, `cam_angulo` | Render rápido |
| `save_blend` | 🟡 | `step_path`, `output_blend` | Guarda escena .blend |
| `save_professional` | 🟡 | `step_path`, `output_blend` | Escena pro (materiales + 4 cámaras) |

**Ángulos de cámara:** `0` (frontal), `45` (isométrico), `90` (planta)

**Ejemplos:**
- "Renderiza el último step" → `blender.render_step`
- "Haz un render del Sheraton" → `blender.render_step` con último STEP
- "Muéstrame el modelo en 3D" → `blender.render_step`
**Nota (CAD-4b):** la acción `render_views` genera 3 vistas ortográficas (planta/fachada/corte). La fachada y el corte funcionan correctamente; la planta tiene un bug conocido de orientación de cámara. Pendiente de polish en una sesión futura. Para visualización 3D completa, usar el IFC (abrible en Revit/ArchiCAD o viewer.ifcopenshell.org).
---

### `dwg` 📐
Lectura y análisis de planos DWG/DXF.

| Acción | Riesgo | Parámetros | Descripción |
|---|---|---|---|
| `convert_to_dxf` | 🟡 | `path` | DWG → DXF |
| `convert_to_dwg` | 🟡 | `path` | DXF → DWG |
| `analyze` | 🟢 | `path` | Estadísticas del plano |
| `list_layers` | 🟢 | `path` | Capas |
| `list_texts` | 🟢 | `path` | Textos limpios |
| `list_blocks` | 🟢 | `path` | Bloques |
| `list_rooms` | 🟢 | `path` | Ambientes |
| `info` | 🟢 | `path` | Dimensiones |
| `extract_layer` | 🟢 | `path`, `layer_name` | Extrae capa |
| `annotate` | 🟡 | `path`, `output`, `offset` | Acotado automático |
| `extract_walls_3d` | 🟡 | `path`, `height` | Muros a STEP |
| `extract_all_layers_3d` | 🟡 | `path`, `output` | Todas las capas a STEP |
| `add_hatch` | 🟡 | `path`, `output` | Relleno rayado de muros (ANSI31) |
| `extract_rooms_with_areas` | 🟢 | `path` | Lista ambientes con sus áreas en m² |
| `cuadro_superficies_excel` | 🟡 | `path`, `output`, `titulo` | Genera Excel con cuadro de superficies |

**Requiere:** ODA File Converter instalado.

**Ejemplos:**
- "Analiza mi_plano.dwg" → `dwg.analyze`
- "Lista los ambientes del plano" → `dwg.list_rooms`
- "Extrae la capa MUROS" → `dwg.extract_layer(layer_name="MUROS")`
- "Acota el plano" → `dwg.annotate`
- "Convierte los muros a 3D" → `dwg.extract_walls_3d`

---

### `n8n` (ver arriba)

---

## Entretenimiento

### `entertainment` (ver arriba)

---

## 🔒 Reglas críticas de enrutamiento

Para evitar confusiones, el router aplica estas reglas antes del clasificador LLM:

- **n8n vs dev/files/terminal:** Si el usuario habla de workflows/n8n/templates → solo `n8n.*`.
- **macro vs dev/terminal:** Si el usuario dice grabar/reproducir/macro → solo `macro.*`.
- **gmail vs browser/dev:** Si el usuario habla de correos/gmail → solo `gmail.*`.
- **canva vs browser/image:** Si el usuario habla de diseños/canva → solo `canva.*`.
- **maps vs browser/dev:** Si el usuario habla de edificios reales/lugares → solo `maps.*`.
- **blender vs maps:** Si el usuario dice "render" → **blender primero** (prioridad absoluta).
- **scheduler vs maps:** Si el usuario dice "todos los días a las X" → scheduler primero.
- **entertainment vs spotify:** Control del sistema → `entertainment.*`; solo Spotify → `spotify.*`.

---

## 📋 Cómo añadir una nueva skill

Checklist para que una skill quede 100% integrada:

1. ✅ Crear `skills/nombre.py` con `class NombreSkill(Skill)` y método `run(action, params)`.
2. ✅ Importar y registrar en `core/router.py` (`self.skills["nombre"] = NombreSkill()`).
3. ✅ Añadir entradas en `_quick_match` para frases obvias.
4. ✅ Añadir esquema en `core/schemas.py` (parámetros por acción).
5. ✅ Añadir niveles de riesgo en `core/confirmation.py`.
6. ✅ Añadir reglas en `core/intent.py` (prompt del clasificador).
7. ✅ Añadir descripción + acciones en `core/agent.py` (`AGENT_SYSTEM_PROMPT`).
8. ✅ Añadir regla crítica si puede confundirse con otra skill.
9. ✅ Probar 5-10 frases típicas.
10. ✅ Documentar en este `SKILLS.md`.

---

**Total:** 31 skills · 4 combos · n8n 100% · Gmail 100% · Canva 100% · Maps 100% · FreeCAD 100% · Blender 100% · DWG 100%.

Estado: **Bloque 1 CERRADO** · **CAD-1 CERRADO** · **CAD-2 CERRADO** · **CAD-3 CERRADO**.
Próximo: CAD-4 (puertas/ventanas reales + planta/fachada/corte).

Estado: **Bloque 1 (auditoría) CERRADO.** Próximo: Bloque 2 (portabilidad + onboarding + .exe).