"""Verifica que las 38 skills se activan correctamente con sus comandos representativos."""
from core.router import Router

r = Router()
TESTS = [
    ("system",        "¿Qué hora es?"),
    ("desktop",       "abre spotify"),
    ("browser",       "abre youtube"),
    ("browser",       "busca en google python"),
    ("files",         "busca archivos pdf en documentos"),
    ("clipboard",     "qué hay en el portapapeles"),
    ("terminal",      "ejecuta ipconfig"),
    ("translate",     "traduce esto al inglés: buenos días"),
    ("office",        "crea un word con un informe"),
    ("edit",          "añade una fila a este excel"),
    ("pdf",           "convierte este word a pdf"),
    ("docs",          "indexa mi carpeta de apuntes"),
    ("gmail",         "lee los últimos correos"),
    ("calendar",      "apunta reunión el lunes a las 10"),
    ("notion",        "apunta en notion que tengo reunión"),
    ("n8n",           "lista workflows de n8n"),
    ("scheduler",     "recuérdame llamar a mamá en 1 hora"),
    ("dev",           "revisa este archivo skills/dev.py"),
    ("git",           "git status"),
    ("vision",        "describe la pantalla"),
    ("image",         "genera una imagen de un gato"),
    ("audio",         "transcribe este audio"),
    ("video",         "recorta el video del 0:10 al 0:30"),
    ("retouch",       "quita el fondo de esta foto"),
    ("education",     "hazme un mindmap sobre energías renovables"),
    ("dwg",           "analiza el plano casa.dwg"),
    ("freecad",       "nuevo documento freecad"),
    ("blender",       "render interior"),
    ("maps",          "modela la sagrada familia"),
    ("spotify",       "qué está sonando"),
    ("canva",         "lista mis diseños de canva"),
    ("telegram",      "mándame un mensaje a telegram"),
    ("entertainment", "reproduce música"),
    ("frases",        "dime una frase célebre"),
    ("chiste",        "cuéntame un chiste"),
    ("weather",       "qué tiempo hace en Lima"),
    ("alarm",         "pon una alarma a las 7"),
    ("macro",         "graba una macro"),
]

if __name__ == "__main__":
    ok = 0
    fail = 0
    fallos = []
    for skill_esperada, cmd in TESTS:
        res = r._quick_match(cmd)
        matched = res[0].get("skill", "?") if res else "None"
        if matched == skill_esperada:
            ok += 1
        else:
            fail += 1
            fallos.append((skill_esperada, cmd, matched))
    print(f"RESUMEN: {ok}/{len(TESTS)} OK | {fail}/{len(TESTS)} FAIL")
    for skill, cmd, matched in fallos:
        print(f"  [FAIL] {skill:15s} | '{cmd}' -> {matched}")
    print()
    if fail == 0:
        print("*** TODAS LAS SKILLS FUNCIONAN ***")
