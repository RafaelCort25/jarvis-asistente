import time
from core import confirmation
from voice.tts import TTS
from voice.stt import STT

print("[TEST] Cargando TTS y STT...")
tts = TTS()
stt = STT()

def handler(skill, action, summary, level, timeout=30):
    prefix = "Atencion. " if level == "high" else ""
    tts.speak(f"{prefix}{summary}")
    time.sleep(0.4)

    for _ in range(3):
        tts.speak("Confirmas?")
        text = stt.listen()
        if not text:
            continue
        t = text.lower().strip()
        if any(w in t for w in ["si", "confirmo", "dale", "hazlo", "adelante", "vale", "ok"]):
            tts.speak("Confirmado.")
            return True
        if any(w in t for w in ["no", "cancela", "cancelar", "espera", "para", "stop"]):
            tts.speak("Cancelado.")
            return False
    tts.speak("Cancelado por falta de respuesta.")
    return False

confirmation.set_handler(handler)

print("\n=== TEST 1: accion low (NO debe preguntar) ===")
resultado = confirmation.require("desktop", "open_app", "abrir notepad")
print(f"Resultado: {resultado} (esperado True)")

print("\n=== TEST 2: accion high (DEBE preguntar por voz) ===")
print("Escucha a Nitro y responde 'si' o 'no'...")
resultado = confirmation.require("terminal", "run", "ejecutar pip install requests")
print(f"Resultado: {resultado}")

print("\n=== TEST 3: accion high, segunda vez ===")
print("Responde 'no' esta vez para ver la cancelacion...")
resultado = confirmation.require("terminal", "run", "borrar todos los archivos")
print(f"Resultado: {resultado} (esperado False)")
