"""
Convierte exports de WhatsApp en dataset limpio para entrenamiento.
Maneja multiples encodings y formatos de fecha/hora.
"""
import re
from pathlib import Path
from datetime import datetime

RAW_DIR = Path("whatsapp_raw")
CLEAN_DIR = Path("whatsapp_clean")
CLEAN_DIR.mkdir(exist_ok=True)

MY_NAMES = [
    "Alessandro",
    "Alessandro Cortijo",
    "Tú",
    "Yo",
    "Ale",
]


def read_file_robust(path):
    """Intenta leer el archivo con multiples encodings."""
    encodings = ["utf-8", "utf-8-sig", "utf-16", "utf-16-le", "cp1252", "latin-1"]
    for enc in encodings:
        try:
            content = path.read_text(encoding=enc)
            # Detectar si el decode fue malo (si hay caracteres raros)
            # Contar caracteres "raros" (fuera de latin comun)
            weird = sum(1 for c in content[:2000] if ord(c) > 0x2000 and c not in "“”‘’–—…")
            total = len(content[:2000])
            if weird / max(total, 1) < 0.05:
                return content
        except (UnicodeDecodeError, UnicodeError):
            continue
    # Fallback: latin-1 nunca falla
    return path.read_text(encoding="latin-1", errors="ignore")


def is_my_name(name):
    name = name.strip()
    for my_name in MY_NAMES:
        if name.lower() == my_name.lower():
            return True
    return False


def clean_message(text):
    """Limpia un mensaje individual."""
    text = re.sub(r'https?://\S+', '', text)
    text = re.sub(r'<Multimedia omitido>', '', text)
    text = re.sub(r'<Media omitted>', '', text)
    text = re.sub(r'<Se edit[oó] este mensaje\.?>', '', text)
    text = re.sub(r'<Este mensaje fue editado>', '', text)
    text = re.sub(r'imagen omitida', '', text, flags=re.IGNORECASE)
    text = re.sub(r'Llamada perdida', '', text, flags=re.IGNORECASE)
    text = re.sub(r'Llamada de voz', '', text, flags=re.IGNORECASE)
    text = re.sub(r'Videollamada', '', text, flags=re.IGNORECASE)
    text = re.sub(r'[Гўв‚¬ВЇГўв‚¬ЕЅ]+', ' ', text)  # limpiar caracteres rotos residuales
    text = re.sub(r'\s+', ' ', text).strip()
    return text


def process_file(txt_path):
    """Extrae mensajes tuyos de un archivo."""
    messages = []
    content = read_file_robust(txt_path)

    # Regex mejorado: acepta "p. m." / "a. m." y horas de 1 o 2 digitos
    # Formato: [dd/mm/aa, h:mm:ss p. m.] Nombre: mensaje
    LINE_PATTERN = re.compile(
        r'^\[(\d{1,2}/\d{1,2}/\d{2,4}),\s*(\d{1,2}:\d{2}(?::\d{2})?(?:\s*[ap]\.\s*m\.)?)\]\s*([^:]+):\s*(.*)$',
        re.IGNORECASE
    )

    for line in content.split("\n"):
        line = line.strip()
        if not line:
            continue
        match = LINE_PATTERN.match(line)
        if not match:
            continue
        date, time, name, message = match.groups()

        if not is_my_name(name):
            continue

        cleaned = clean_message(message)
        if len(cleaned) < 5:
            continue
        if not re.search(r'[a-zA-ZáéíóúñÁÉÍÓÚÑ]', cleaned):
            continue
        if any(kw in cleaned.lower() for kw in [
            "cifrado de extremo a extremo",
            "los mensajes y las llamadas están",
            "cambio de numero",
            "se unio",
            "salio del grupo",
            "añadio a",
        ]):
            continue

        messages.append({
            "date": date,
            "time": time,
            "text": cleaned,
            "source": txt_path.stem,
        })
    return messages


def main():
    print("=" * 60)
    print("PREPARACION DE DATASET WHATSAPP")
    print("=" * 60)

    txt_files = list(RAW_DIR.glob("*.txt"))
    if not txt_files:
        print(f"\n[ERROR] No hay archivos .txt en {RAW_DIR}")
        return

    print(f"\nEncontrados {len(txt_files)} archivos en {RAW_DIR}\n")

    all_messages = []
    for txt in txt_files:
        messages = process_file(txt)
        all_messages.extend(messages)
        print(f"  {txt.name}: {len(messages)} mensajes tuyos")

    if not all_messages:
        print("\n[ERROR] No se encontraron mensajes tuyos.")
        return

    all_messages.sort(key=lambda m: m["date"] + " " + m["time"])

    output_file = CLEAN_DIR / "my_messages.txt"
    with open(output_file, "w", encoding="utf-8") as f:
        for m in all_messages:
            f.write(m["text"] + "\n")

    stats_file = CLEAN_DIR / "stats.txt"
    with open(stats_file, "w", encoding="utf-8") as f:
        f.write(f"Total mensajes: {len(all_messages)}\n")
        f.write(f"Archivos procesados: {len(txt_files)}\n")
        f.write(f"Fecha: {datetime.now().isoformat()}\n\n")
        f.write("Fuentes:\n")
        for txt in txt_files:
            count = sum(1 for m in all_messages if m["source"] == txt.stem)
            f.write(f"  {txt.name}: {count}\n")

    total_chars = sum(len(m["text"]) for m in all_messages)
    avg_chars = total_chars / len(all_messages) if all_messages else 0

    print("\n" + "=" * 60)
    print(f"RESULTADO:")
    print(f"  Total mensajes tuyos: {len(all_messages)}")
    print(f"  Caracteres totales: {total_chars:,}")
    print(f"  Promedio por mensaje: {avg_chars:.1f} caracteres")
    print(f"  Archivo: {output_file}")
    print(f"  Stats: {stats_file}")
    print("=" * 60)

    if len(all_messages) < 3000:
        print(f"\n[AVISO] Tienes {len(all_messages)} mensajes, recomendado minimo 3,000.")
    elif len(all_messages) < 5000:
        print(f"\n[OK] Tienes {len(all_messages)} mensajes.")
    else:
        print(f"\n[EXCELENTE] Tienes {len(all_messages)} mensajes!")


if __name__ == "__main__":
    main()  