"""Smoke test de skills - verifica routing sin ejecutar acciones peligrosas."""
import sys
from pathlib import Path

# Anadir el root al path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.router import Router

# Comandos de bajo riesgo
TESTS = [
    ("system", "¿qué hora es?"),
    ("system", "cuanta ram libre tengo"),
    ("desktop", "sube el volumen al 50"),
    ("browser", "busca en google python tutorial"),
    ("files", "busca archivos pdf en documentos"),
    ("clipboard", "qué hay en el portapapeles"),
    ("terminal", "ejecuta ipconfig"),
    ("translate", "traduce hola al inglés"),
    ("office", "crea un word con un informe sobre IA"),
    ("docs", "lista mis documentos indexados"),
    ("gmail", "cuántos correos sin leer tengo"),
    ("calendar", "qué eventos tengo esta semana"),
    ("notion", "lista mis páginas de notion"),
    ("n8n", "lista workflows de n8n"),
    ("scheduler", "qué tareas tengo programadas"),
    ("productivity", "qué tareas tengo pendientes"),
    ("dev", "cuenta las líneas de skills/dev.py"),
    ("git", "git status"),
    ("vision", "describe la pantalla"),
    ("image", "qué imágenes he generado hoy"),
    ("audio", "qué archivos de audio tengo"),
    ("video", "qué videos tengo"),
    ("retouch", "qué imágenes puedo procesar"),
    ("education", "hazme un diagrama simple"),
    ("dwg", "qué planos dwg tengo"),
    ("freecad", "qué documentos freecad tengo"),
    ("blender", "qué modelos blender tengo"),
    ("maps", "coordenadas de la Plaza Mayor de Lima"),
    ("spotify", "qué está sonando"),
    ("canva", "lista mis diseños de canva"),
    ("telegram", "envíame un mensaje de prueba"),
    ("entertainment", "qué música tengo disponible"),
    ("frases", "dime una frase célebre"),
    ("chiste", "cuéntame un chiste"),
    ("weather", "qué tiempo hace en Lima"),
    ("alarm", "qué alarmas tengo"),
    ("macro", "lista mis macros"),
]

print("=" * 80)
print(f"SMOKE TEST DE SKILLS - {len(TESTS)} comandos (solo routing)")
print("=" * 80)
print()

r = Router()
ok = 0
fail = 0
fallos = []

for skill, cmd in TESTS:
    try:
        res = r._quick_match(cmd)
        if not res or len(res) == 0:
            matched = "(LLM)"
            status = "SIN_MATCH"
            fail += 1
            fallos.append((skill, cmd, matched))
        else:
            matched = res[0].get("skill", "?")
            if matched == skill:
                status = "OK"
                ok += 1
            else:
                status = f"-> {matched}"
                fail += 1
                fallos.append((skill, cmd, matched))

        icon = "[OK] " if status == "OK" else "[LLM]" if "LLM" in status else "[FAIL]"
        print(f"{icon} {skill:15s} | {cmd[:55]:55s} {status if status != 'OK' else ''}")
    except Exception as e:
        print(f"[ERR] {skill:15s} | {cmd[:55]:55s} ERROR: {e}")
        fail += 1
        fallos.append((skill, cmd, f"ERR {e}"))

print()
print("=" * 80)
print(f"RESUMEN: {ok}/{len(TESTS)} OK | {fail}/{len(TESTS)} FAIL/LLM")
print("=" * 80)

if fallos:
    print()
    print("Comandos que fueron al LLM o fallaron:")
    for skill, cmd, matched in fallos:
        print(f"  - {skill:15s} -> {matched}")
