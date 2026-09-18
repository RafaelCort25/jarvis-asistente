"""
Convierte los mensajes limpios en formato JSONL para entrenamiento.
Cada par (contexto_previo, tu_respuesta) es un ejemplo de entrenamiento.
"""
import json
import re
from pathlib import Path

INPUT_FILE = Path("whatsapp_clean/my_messages.txt")
OUTPUT_FILE = Path("whatsapp_clean/dataset.jsonl")

# Max caracteres del contexto (mensajes previos)
MAX_CONTEXT_CHARS = 300


def main():
    if not INPUT_FILE.exists():
        print(f"[ERROR] No existe {INPUT_FILE}")
        return

    lines = [l.strip() for l in INPUT_FILE.read_text(encoding="utf-8").split("\n") if l.strip()]
    print(f"[INFO] Mensajes cargados: {len(lines)}")

    examples = []

    # Crear pares: (contexto_anterior, respuesta)
    # Ventana deslizante de 3 mensajes previos
    for i, msg in enumerate(lines):
        if i < 1:
            continue

        # Los ultimos 1-3 mensajes forman el contexto
        context_start = max(0, i - 3)
        context = " ".join(lines[context_start:i])

        if len(context) > MAX_CONTEXT_CHARS:
            context = context[-MAX_CONTEXT_CHARS:]

        # Filtrar ejemplos de baja calidad
        if len(msg) < 5:
            continue
        if len(context) < 5:
            continue

        examples.append({
            "messages": [
                {"role": "user", "content": context},
                {"role": "assistant", "content": msg},
            ]
        })

    print(f"[INFO] Ejemplos generados: {len(examples)}")

    # Guardar JSONL
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        for ex in examples:
            f.write(json.dumps(ex, ensure_ascii=False) + "\n")

    print(f"[INFO] Guardado en: {OUTPUT_FILE}")

    # Stats
    size_kb = OUTPUT_FILE.stat().st_size / 1024
    print(f"[INFO] Tamaño: {size_kb:.1f} KB")

    # Mostrar ejemplo
    print("\n[EJEMPLO del dataset]")
    print(json.dumps(examples[0], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()