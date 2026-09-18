"""
Vigilancia que envia alertas por Telegram.
Ejecutar en paralelo al bot de Telegram.
"""
import time
from security.surveillance import Surveillance
from integrations.notifier import send, get_saved_chat_id


def send_alert(photo_path, confidence):
    """Envia la foto del desconocido por Telegram."""
    if not get_saved_chat_id():
        print("[ALERT] No hay chat_id guardado. Abre el bot en Telegram primero.")
        return

    msg = (
        f"🚨 *ALERTA DE SEGURIDAD*\n\n"
        f"Persona desconocida detectada frente a tu PC.\n"
        f"Confianza: {int(confidence)}\n"
        f"Hora: {time.strftime('%H:%M:%S')}"
    )
    ok = send(msg, image_path=photo_path)
    if ok:
        print(f"[ALERT] ✅ Enviado a Telegram: {photo_path}")
    else:
        print(f"[ALERT] ❌ Error enviando a Telegram")


def main():
    print("=" * 60)
    print("VIGILANCIA CON ALERTAS A TELEGRAM")
    print("=" * 60)

    chat_id = get_saved_chat_id()
    if not chat_id:
        print("[WARN] No hay chat_id guardado.")
        print("[WARN] Abre tu bot en Telegram y envia /start primero.")
        return

    print(f"[INFO] Chat ID configurado: {chat_id}")
    print("[INFO] Iniciando vigilancia...")

    surv = Surveillance(on_unknown=send_alert)
    surv.start()

    # Enviar aviso inicial a Telegram
    send("🛡️ Vigilancia iniciada. Te avisare si veo desconocidos.")

    print("[INFO] Vigilancia activa. Presiona Ctrl+C para detener.")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n[INFO] Deteniendo...")
    finally:
        surv.stop()
        send("🛡️ Vigilancia detenida.")


if __name__ == "__main__":
    main()