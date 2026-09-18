"""
Limpia el archivo my_messages.txt eliminando lineas de llamadas y ruido.
"""
import re
from pathlib import Path

INPUT = Path("whatsapp_clean/my_messages.txt")
OUTPUT = Path("whatsapp_clean/my_messages_clean.txt")


def is_garbage(line):
    """Devuelve True si la linea es basura de WhatsApp."""
    # Quitar caracteres invisibles para verificar
    clean = re.sub(r'[\u200b-\u200f\u202a-\u202e\u2066-\u2069\ufeff]', '', line)
    clean = clean.strip()

    if not clean:
        return True

    # Patrones de llamadas/multimedia
    patterns = [
        r'^Llamada,?\s*\d+\s*s\.?$',
        r'^Videollamada,?\s*\d+\s*s\.?$',
        r'^Llamada perdida$',
        r'^Llamada de voz.*$',
        r'^Videollamada.*$',
        r'^Audio de \d+:\d+$',
        r'^Video de \d+:\d+$',
        r'^<Multimedia omitido>$',
        r'^imagen omitida$',
    ]
    for p in patterns:
        if re.match(p, clean, re.IGNORECASE):
            return True

    # Muy corto
    if len(clean) < 5:
        return True

    # Sin letras
    if not re.search(r'[a-zA-ZáéíóúñÁÉÍÓÚÑ]', clean):
        return True

    # Menos de 3 caracteres alfabeticos
    alpha = sum(1 for c in clean if c.isalpha())
    if alpha < 3:
        return True

    return False


def main():
    if not INPUT.exists():
        print(f"[ERROR] No existe {INPUT}")
        return

    print(f"[INFO] Leyendo {INPUT}")
    lines = INPUT.read_text(encoding="utf-8").split("\n")

    clean_lines = []
    removed = 0

    for line in lines:
        if is_garbage(line):
            removed += 1
        else:
            # Limpiar caracteres invisibles de las lineas validas
            clean = re.sub(r'[\u200b-\u200f\u202a-\u202e\u2066-\u2069\ufeff]', '', line).strip()
            clean_lines.append(clean)

    OUTPUT.write_text("\n".join(clean_lines), encoding="utf-8")

    print(f"[INFO] Lineas originales: {len(lines)}")
    print(f"[INFO] Lineas eliminadas: {removed}")
    print(f"[INFO] Lineas finales: {len(clean_lines)}")
    print(f"[INFO] Guardado en: {OUTPUT}")

    total_chars = sum(len(l) for l in clean_lines)
    avg = total_chars / len(clean_lines) if clean_lines else 0
    print(f"[INFO] Caracteres totales: {total_chars:,}")
    print(f"[INFO] Promedio por linea: {avg:.1f}")


if __name__ == "__main__":
    main()