# core/schemas.py

SKILLS_VALIDAS = {
    "desktop": {
        "open_app": {"app": {"type": "string", "enum": ["brave", "chrome", "notepad", "calculadora", "explorador", "paint", "cmd", "spotify"]}},
        "open_folder": {"folder": {"type": "string", "enum": ["descargas", "documentos", "escritorio", "imagenes", "musica", "videos"]}},
        "volume_up": {},
        "volume_down": {},
        "mute": {},
    },
    "browser": {
        "search_youtube": {"query": {"type": "string"}},
        "search_google": {"query": {"type": "string"}},
        "open_url": {"url": {"type": "string"}},
        "play_pending": {"index": {"type": "integer", "minimum": 1, "maximum": 5}},
        "cancel_pending": {},
    },
    "entertainment": {
        "play_pause": {},
        "next_track": {},
        "prev_track": {},
    },
    "productivity": {
        "save_note": {"text": {"type": "string"}},
        "read_notes": {},
        "clear_notes": {},
    },
    "system": {
        "lock": {},
        "shutdown": {},
        "restart": {},
        "sleep": {},
        "cancel_shutdown": {},
        "screenshot": {},
    },
    "dev": {
        "review_file": {"path": {"type": "string"}},
        "review_project": {"path": {"type": "string"}},
        "explain": {"path": {"type": "string"}},
        "find_issues": {"path": {"type": "string"}},
        "generate_code": {
            "description": {"type": "string"},
            "language": {"type": "string", "enum": ["python", "javascript", "java", "c", "cpp", "csharp", "go", "rust", "ruby", "php"]},
        },
    },
    "vision": {
        "describe_screen": {},
        "explain_screen_code": {},
    },
    "files": {
        "find_file": {"name": {"type": "string"}},
    },
    "weather": {
        "current": {"city": {"type": "string"}},
    },
    "translate": {
        "text": {"text": {"type": "string"}, "to": {"type": "string"}},
    },
    "alarm": {
        "set": {"minutes": {"type": "integer", "minimum": 1}, "text": {"type": "string"}},
        "list": {},
        "cancel": {},
    },
    "none": {
        "chat": {},
    },
}

def build_json_schema():
    """
    Genera un JSON Schema que Ollama usa para forzar la estructura.
    Cada combinación skill+action es una opción dentro de un oneOf.
    """
    acciones = []
    for skill, acciones_skill in SKILLS_VALIDAS.items():
        for action, params_def in acciones_skill.items():
            # Construir propiedades de params
            propiedades = {}
            requeridos = []
            for param, definicion in params_def.items():
                propiedades[param] = definicion
                requeridos.append(param)
            
            accion_schema = {
                "type": "object",
                "properties": {
                    "skill": {"type": "string", "enum": [skill]},
                    "action": {"type": "string", "enum": [action]},
                    "params": {
                        "type": "object",
                        "properties": propiedades,
                        "required": requeridos,
                        "additionalProperties": False,
                    },
                },
                "required": ["skill", "action", "params"],
                "additionalProperties": False,
            }
            acciones.append(accion_schema)
    
    return {
        "type": "object",
        "properties": {
            "actions": {
                "type": "array",
                "items": {"oneOf": acciones},
                "minItems": 1,
            }
        },
        "required": ["actions"],
        "additionalProperties": False,
    }