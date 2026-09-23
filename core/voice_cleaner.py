"""Limpia el texto de la voz antes del TTS: sin rutas, sin fuentes, sin tecnicismos."""
import re


def clean_voice(text):
    """
    Toma un texto de display y devuelve una version corta, natural y sin tecnicismos
    para pasar al TTS. No toca el display original.
    """
    if not text:
        return ""

    t = text.strip()

    # 1. Cortar todo lo que venga despues de "Fuentes:" (informacion interna)
    t = re.split(r'\n?\s*Fuentes?\s*:', t, maxsplit=1, flags=re.IGNORECASE)[0]

    # 2. Quitar la ruta completa de archivo, dejar solo el nombre
    #    C:\JARVIS\sandbox\office\foo.docx  ->  foo.docx
    t = re.sub(r'[A-Za-z]:\\[^\s\n]+', lambda m: _basename_from_path(m.group(0)), t)

    # 3. Quitar detalles tecnicos entre parentesis: "(13 elementos, 36256 bytes)"
    t = re.sub(r'\(\s*\d+\s*(?:elementos?|filas?|chunks?|fragmentos?)[^)]*\)', '', t, flags=re.IGNORECASE)
    t = re.sub(r'\(\s*\d+\s*(?:KB|MB|bytes?)[^)]*\)', '', t, flags=re.IGNORECASE)
    t = re.sub(r'\(\s*\d+\s*x\s*\d+[^)]*\)', '', t, flags=re.IGNORECASE)

    # 4. Quitar bloques de codigo, markdown y backticks
    t = re.sub(r'```[\s\S]*?```', '', t)
    t = re.sub(r'`([^`]*)`', r'\1', t)
    t = re.sub(r'\*\*([^*]*)\*\*', r'\1', t)
    t = re.sub(r'\*([^*]*)\*', r'\1', t)
    t = re.sub(r'^#{1,6}\s+', '', t, flags=re.MULTILINE)

    # 5. Si empieza con "Lo siento, pero no puedo proporcionar..." -> reemplazar
    #    por una version mas corta y natural.
    t = re.sub(
        r'^Lo siento,?\s*(?:pero)?\s*no puedo proporcionar(?:te)?\s+(?:la\s+)?informaci[oó]n[^.]*\.\s*',
        'No tengo esa informacion en el contexto. ',
        t,
        flags=re.IGNORECASE,
    )
    t = re.sub(
        r'^El contexto no contiene[^.]*\.\s*',
        '',
        t,
        flags=re.IGNORECASE,
    )
    t = re.sub(
        r'No hay informaci[oó]n espec[ií]fica sobre[^.]*\.\s*',
        'No tengo esa informacion. ',
        t,
        flags=re.IGNORECASE,
    )

    # 6. Quitar emojis
    t = re.sub(r'[\U0001F300-\U0001FAFF\u2600-\u27BF]', '', t)

    # 7. Colapsar espacios y lineas
    t = re.sub(r'\n+', '. ', t)
    t = re.sub(r'\s+', ' ', t)
    t = re.sub(r'\.\s*\.', '.', t)
    t = t.strip(" .;,:")

    if not t:
        return ""

    # 8. Si es muy largo, quedarse con la primera o dos primeras oraciones
    if len(t) > 280:
        # Buscar el primer punto despues de 80 chars
        cut = t.find(". ", 80)
        if 0 < cut < 280:
            t = t[:cut + 1]
        else:
            t = t[:277].rstrip() + "..."

    return t.strip()


def _basename_from_path(path_str):
    """Extrae solo el nombre del archivo de una ruta completa."""
    # Windows
    m = re.search(r'[\\/]([^\\/]+)$', path_str)
    if m:
        return m.group(1)
    return path_str