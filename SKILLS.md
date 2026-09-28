# SKILLS.md — Catálogo completo de skills de Senna

Documentación de las **38 skills operativas** de Senna con un total de **338 acciones**.

**Última actualización:** 2026-09-28 (generado automáticamente por `scripts/generate_skills_md.py`)

**Niveles de riesgo:**
- 🟢 **low** — No requiere confirmación. Solo lectura o acciones inocuas.
- 🟡 **medium** — Pide confirmación al usuario antes de ejecutar.
- 🔴 **high** — Pide confirmación con advertencia (acciones destructivas o irreversibles).

---

## 📑 Índice por categoría

1. [Fundamentales](#fundamentales) (7 skills)
2. [Productividad](#productividad) (10 skills)
3. [Dev y tecnologia](#dev-y-tecnologia) (3 skills)
4. [Multimedia](#multimedia) (5 skills)
5. [CAD y 3D](#cad-y-3d) (4 skills)
6. [Integraciones](#integraciones) (3 skills)
7. [Entretenimiento](#entretenimiento) (6 skills)

---

## Fundamentales

### `browser`
Skill browser

**Clase:** `BrowserSkill`  
**Archivo:** `skills/browser.py`  
**Acciones:** 5

- `cancel_pending`
- `open_url`
- `play_pending`
- `search_google`
- `search_youtube`

### `clipboard`
Skill clipboard

**Clase:** `ClipboardSkill`  
**Archivo:** `skills/clipboard.py`  
**Acciones:** 2

- `read`
- `write`

### `desktop`
Skill desktop

**Clase:** `DesktopSkill`  
**Archivo:** `skills/desktop.py`  
**Acciones:** 5

- `mute`
- `open_app`
- `open_folder`
- `volume_down`
- `volume_up`

### `files`
Skill de archivos: buscar, listar, analizar.

**Clase:** `FilesSkill`  
**Archivo:** `skills/files.py`  
**Acciones:** 11

- `create_folder`
- `duplicates`
- `find_advanced`
- `find_content`
- `find_file`
- `info`
- `list_folder`
- `move`
- `open_path`
- `pick`
- `recent`

### `system`
Skill system

**Clase:** `SystemSkill`  
**Archivo:** `skills/system.py`  
**Acciones:** 13

- `cancel_shutdown`
- `clean_temp`
- `date`
- `disk_info`
- `empty_recycle`
- `list_big_files`
- `list_startup`
- `lock`
- `restart`
- `screenshot`
- `shutdown`
- `sleep`
- `time`

### `terminal`
Skill terminal

**Clase:** `TerminalSkill`  
**Archivo:** `skills/terminal.py`  
**Acciones:** 2

- `run`
- `suggest`

### `translate`
Skill translate

**Clase:** `TranslateSkill`  
**Archivo:** `skills/translate.py`  
**Acciones:** 1

- `text`

---

## Productividad

### `calendar`
Skill de calendario: gestion de eventos locales con export a .ics.

**Clase:** `CalendarSkill`  
**Archivo:** `skills/calendar.py`  
**Acciones:** 8

- `add`
- `delete`
- `export`
- `find_free`
- `list`
- `today`
- `tomorrow`
- `week`

### `docs`
Skill docs

**Clase:** `DocsSkill`  
**Archivo:** `skills/docs.py`  
**Acciones:** 9

- `ask`
- `ask_to_word`
- `delete`
- `index_file`
- `index_folder`
- `index_folder_advanced`
- `list`
- `list_detailed`
- `stats`

### `edit`
Skill de edicion: modifica archivos existentes con instrucciones en lenguaje natural.

**Clase:** `EditSkill`  
**Archivo:** `skills/edit.py`  
**Acciones:** 13

- `csv_modify`
- `image_convert`
- `image_crop`
- `image_resize`
- `image_rotate`
- `json_modify`
- `list_uploads`
- `modify`
- `pdf_merge`
- `pdf_remove_pages`
- `pdf_rotate`
- `pdf_split`
- `yaml_modify`

### `gmail`
Skill de Gmail: leer, buscar y enviar correos via IMAP/SMTP.

**Clase:** `GmailSkill`  
**Archivo:** `skills/gmail.py`  
**Acciones:** 14

- `archive`
- `count_unread`
- `delete`
- `download_attachments`
- `list_attachments`
- `list_recent`
- `mark_read`
- `mark_unread`
- `read`
- `reply`
- `search`
- `search_advanced`
- `send`
- `send_attachment`

### `n8n`
Skill de n8n: controla workflows + busca/importa templates de n8n.io.

**Clase:** `N8nSkill`  
**Archivo:** `skills/n8n.py`  
**Acciones:** 10

- `activate`
- `create_workflow`
- `deactivate`
- `delete_workflow`
- `get_template`
- `get_workflow`
- `import_template`
- `list_executions`
- `list_workflows`
- `search_templates`

### `notion`
Skill de Notion: crear paginas, notas y buscar en el workspace.

**Clase:** `NotionSkill`  
**Archivo:** `skills/notion.py`  
**Acciones:** 8

- `append_block`
- `config`
- `create_page`
- `list_pages`
- `save_note`
- `search`
- `set_default_parent`
- `whoami`

### `office`
Skill de Office: Word, Excel y PowerPoint.

**Clase:** `OfficeSkill`  
**Archivo:** `skills/office.py`  
**Acciones:** 6

- `create_doc`
- `create_ppt`
- `create_xlsx`
- `read_doc`
- `read_ppt`
- `read_xlsx`

### `pdf`
Skill de PDF: convierte Word a PDF + utilidades avanzadas.

**Clase:** `PdfSkill`  
**Archivo:** `skills/pdf.py`  
**Acciones:** 18

- `blank_page`
- `compress`
- `extract_pages`
- `extract_text`
- `from_docx`
- `info`
- `insert_pages`
- `list`
- `merge_images`
- `metadata`
- `page_numbers`
- `remove_password`
- `reorder`
- `set_password`
- `sign`
- `stamp`
- `to_images`
- `watermark`

### `productivity`
Skill productivity

**Clase:** `ProductivitySkill`  
**Archivo:** `skills/productivity.py`  
**Acciones:** 3

- `clear_notes`
- `read_notes`
- `save_note`

### `scheduler`
Skill scheduler

**Clase:** `SchedulerSkill`  
**Archivo:** `skills/scheduler.py`  
**Acciones:** 5

- `add_daily`
- `add_interval`
- `add_once`
- `cancel`
- `list`

---

## Dev y tecnologia

### `dev`
Skill dev

**Clase:** `DevSkill`  
**Archivo:** `skills/dev.py`  
**Acciones:** 16

- `count_lines`
- `create_and_test`
- `create_venv`
- `explain`
- `find_issues`
- `format_code`
- `generate_code`
- `lint_code`
- `review_file`
- `review_project`
- `review_to_excel`
- `review_to_word`
- `run_file`
- `run_tests`
- `search_code`
- `write_file`

### `git`
Skill git

**Clase:** `GitSkill`  
**Archivo:** `skills/git.py`  
**Acciones:** 17

- `add`
- `blame`
- `branches`
- `checkout`
- `commit`
- `config`
- `diff`
- `log`
- `pull`
- `push`
- `remotes`
- `reset`
- `show`
- `stash`
- `stash_list`
- `stash_pop`
- `status`

### `vision`
Skill de vision: analisis de pantalla e imagenes con Ollama (vision-language models).

**Clase:** `VisionSkill`  
**Archivo:** `skills/vision.py`  
**Acciones:** 15

- `capture`
- `compare_images`
- `describe_image`
- `describe_screen`
- `describe_ui`
- `detect_objects`
- `explain_screen_code`
- `find_text`
- `list_models`
- `ocr`
- `ocr_image`
- `read_error`
- `read_table`
- `set_model`
- `translate_screen`

---

## Multimedia

### `audio`
Skill de audio: transcripcion con faster-whisper (OpenAI Whisper optimizado).

**Clase:** `AudioSkill`  
**Archivo:** `skills/audio.py`  
**Acciones:** 6

- `batch`
- `info`
- `list`
- `to_word`
- `transcribe`
- `transcribe_srt`

### `education`
Skill de educacion: PSeInt, conversion de lenguajes, diagramas Mermaid.

**Clase:** `EducationSkill`  
**Archivo:** `skills/education.py`  
**Acciones:** 5

- `convert`
- `diagram`
- `list_diagrams`
- `pseint`
- `render`

### `image`
Skill de generacion de imagenes: Agnes AI (hq) + Cloudflare Flux (fast).

**Clase:** `ImageSkill`  
**Archivo:** `skills/image.py`  
**Acciones:** 8

- `generate`
- `generate_advanced`
- `history`
- `list`
- `regenerate`
- `search_history`
- `to_word`
- `variations`

### `retouch`
Skill de retouch profesional: quitar fondo, upscaling, sombras, watermark.

**Clase:** `RetouchSkill`  
**Archivo:** `skills/retouch.py`  
**Acciones:** 8

- `batch`
- `enhance`
- `pipeline`
- `remove_bg`
- `shadow`
- `upscale`
- `watermark`
- `white_bg`

### `video`
Skill de video: recortar, unir, convertir, comprimir, subtitulos, GIF.

**Clase:** `VideoSkill`  
**Archivo:** `skills/video.py`  
**Acciones:** 15

- `add_music`
- `add_subtitles`
- `compress`
- `convert`
- `extract_audio`
- `extract_frames`
- `gif`
- `info`
- `list`
- `merge`
- `mute`
- `rotate`
- `speed`
- `thumbnail`
- `trim`

---

## CAD y 3D

### `blender`
Skill de Blender: render arquitectonico, vistas, interiores, animaciones, export.

**Clase:** `BlenderSkill`  
**Archivo:** `skills/blender.py`  
**Acciones:** 15

- `add_lighting_preset`
- `apply_material`
- `export_gltf`
- `import_fbx`
- `import_obj`
- `optimize_mesh`
- `render_360`
- `render_animation`
- `render_interior`
- `render_multiple_angles`
- `render_step`
- `render_topdown`
- `render_views`
- `render_views_clean`
- `save_blend`

### `dwg`
Skill de DWG/DXF: lee, convierte y analiza planos CAD.

**Clase:** `DwgSkill`  
**Archivo:** `skills/dwg.py`  
**Acciones:** 21

- `add_dimensions`
- `add_hatch`
- `analyze`
- `annotate`
- `convert_to_dwg`
- `convert_to_dxf`
- `cuadro_superficies_excel`
- `export_ifc`
- `export_ifc_full`
- `export_pdf`
- `extract_all_layers_3d`
- `extract_layer`
- `extract_rooms_with_areas`
- `extract_walls_3d`
- `info`
- `list_blocks`
- `list_layers`
- `list_rooms`
- `list_texts`
- `merge_dxf`
- `search_text`

### `freecad`
Skill de FreeCAD: crea geometria 2D/3D y exporta DXF/PDF via freecadcmd.

**Clase:** `FreeCadSkill`  
**Archivo:** `skills/freecad.py`  
**Acciones:** 31

- `add_circle`
- `add_column`
- `add_dimension`
- `add_door`
- `add_level_dimensions`
- `add_line`
- `add_rectangle`
- `add_room_labels`
- `add_slab`
- `add_text`
- `add_wall`
- `add_wall_3d`
- `add_window`
- `array_objects`
- `boolean_op`
- `clear_workspace`
- `create_room`
- `delete_object`
- `export_dxf`
- `export_obj`
- `export_pdf`
- `export_pdf_techdraw`
- `export_step`
- `export_stl`
- `import_step`
- `list_objects`
- `move_object`
- `new_document`
- `rotate_object`
- `save_as`
- `set_color`

### `maps`
Skill de Maps: busca edificios en OpenStreetMap y genera modelos CAD.

**Clase:** `MapsSkill`  
**Archivo:** `skills/maps.py`  
**Acciones:** 10

- `create_detailed`
- `create_model`
- `distance`
- `get_building`
- `get_coordinates`
- `get_elevation`
- `get_route`
- `nearby_search`
- `reverse_geocode`
- `search`

---

## Integraciones

### `canva`
Skill de Canva: crear, leer y exportar diseños via Connect API.

**Clase:** `CanvaSkill`  
**Archivo:** `skills/canva.py`  
**Acciones:** 8

- `authorize`
- `create_design`
- `export_design`
- `get_design`
- `list_assets`
- `list_designs`
- `upload_asset_from_url`
- `whoami`

### `spotify`
Skill de control de Spotify via Web API (requiere Premium).

**Clase:** `SpotifySkill`  
**Archivo:** `skills/spotify.py`  
**Acciones:** 6

- `current`
- `next`
- `pause`
- `play`
- `previous`
- `volume`

### `telegram`
Skill de Telegram: envia archivos generados al chat del usuario.

**Clase:** `TelegramSkill`  
**Archivo:** `skills/telegram.py`  
**Acciones:** 2

- `send_file`
- `send_last`

---

## Entretenimiento

### `alarm`
Skill alarm

**Clase:** `AlarmSkill`  
**Archivo:** `skills/alarm.py`  
**Acciones:** 3

- `cancel`
- `list`
- `set`

### `chiste`
Skill chiste

**Clase:** `JokeSkill`  
**Archivo:** `skills/chiste.py`  
**Acciones:** 2

- `tell`
- `tell_es`

### `entertainment`
Skill entertainment

**Clase:** `EntertainmentSkill`  
**Archivo:** `skills/entertainment.py`  
**Acciones:** 3

- `next_track`
- `play_pause`
- `prev_track`

### `frases`
Frases motivacionales curadas.

**Clase:** `FrasesSkill`  
**Archivo:** `skills/frases.py`  
**Acciones:** 4

- `by_author`
- `count`
- `list`
- `random`

### `macro`
Skill de macro recorder: graba y reproduce secuencias de teclado/raton.

**Clase:** `MacroSkill`  
**Archivo:** `skills/macro.py`  
**Acciones:** 9

- `delete`
- `duplicate`
- `edit_speed`
- `info`
- `list`
- `play`
- `rename`
- `start`
- `stop`

### `weather`
Skill weather

**Clase:** `WeatherSkill`  
**Archivo:** `skills/weather.py`  
**Acciones:** 1

- `current`

---
