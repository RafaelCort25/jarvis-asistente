import os
import asyncio
from pathlib import Path
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
)

# Cargar variables de entorno
load_dotenv()
TOKEN = os.getenv("TELEGRAM_TOKEN")
if not TOKEN:
    raise SystemExit("Falta TELEGRAM_TOKEN en .env")

# Importar Jarvis
from core.brain import Brain
from core.router import Router
from core.config_loader import CONFIG

# Inicializar Jarvis una sola vez
print("[BOT] Inicializando Jarvis...")
brain = Brain()
router = Router()
print("[BOT] Jarvis listo.")


# Guardar ultimo chat_id para alertas
CHAT_ID_FILE = Path("memory/telegram_chat_id.txt")
CHAT_ID_FILE.parent.mkdir(parents=True, exist_ok=True)


def save_chat_id(chat_id):
    try:
        CHAT_ID_FILE.write_text(str(chat_id), encoding="utf-8")
    except Exception:
        pass


def get_saved_chat_id():
    try:
        return CHAT_ID_FILE.read_text(encoding="utf-8").strip()
    except Exception:
        return None


# ─── COMANDOS ───────────────────────────────────────────────────────────────

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    save_chat_id(chat_id)
    await update.message.reply_text(
        f"🤖 *{CONFIG['jarvis']['name']}* en linea.\n\n"
        "Escribeme un comando o pregunta.\n"
        "Ejemplos:\n"
        "• abre notepad\n"
        "• pon bad bunny\n"
        "• que clima hace en lima\n"
        "• abre el ultimo archivo de descargas\n\n"
        "Usa /help para mas info.",
        parse_mode="Markdown",
    )


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📖 *Comandos disponibles*\n\n"
        "*Skills de Jarvis:*\n"
        "• desktop: abre notepad, abre brave, sube el volumen\n"
        "• browser: pon bad bunny, busca en google X\n"
        "• productivity: guarda nota X, lee mis notas\n"
        "• system: toma una captura, bloquea la pc\n"
        "• files: lista descargas, abre el ultimo archivo\n"
        "• weather: que clima hace en lima\n"
        "• translate: traduce buenos dias al ingles\n"
        "• alarm: ponme una alarma en 5 minutos\n\n"
        "*Bot:*\n"
        "/start - Iniciar\n"
        "/help - Esta ayuda\n"
        "/id - Ver tu chat ID\n"
        "/ping - Verificar que el bot funciona\n"
        "/captura - Tomar captura de pantalla\n"
        "/status - Estado del sistema (CPU, RAM, disco)",
        parse_mode="Markdown",
    )


async def cmd_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    await update.message.reply_text(f"Tu chat ID es: `{chat_id}`", parse_mode="Markdown")


async def cmd_ping(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🏓 Pong! El bot funciona.")


async def cmd_screenshot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Toma captura y la envía directamente."""
    await update.message.chat.send_action(action="upload_photo")
    try:
        from datetime import datetime
        from pathlib import Path
        import mss
        import mss.tools

        screenshots_dir = Path.home() / "Pictures" / "JarvisScreenshots"
        screenshots_dir.mkdir(parents=True, exist_ok=True)
        filename = screenshots_dir / f"captura_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"

        with mss.mss() as sct:
            monitor = sct.monitors[0]
            img = sct.grab(monitor)
            mss.tools.to_png(img.rgb, img.size, output=str(filename))

        with open(filename, "rb") as f:
            await update.message.reply_photo(photo=f, caption=f"📸 {datetime.now().strftime('%H:%M:%S')}")
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {e}")


async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Estado actual de la PC."""
    try:
        import psutil

        cpu = psutil.cpu_percent(interval=1)
        ram = psutil.virtual_memory()
        disk = psutil.disk_usage("C:/")
        battery = psutil.sensors_battery()

        text = (
            f"💻 *Estado de la PC*\n\n"
            f"CPU: {cpu}%\n"
            f"RAM: {ram.percent}% ({ram.used/1e9:.1f} / {ram.total/1e9:.1f} GB)\n"
            f"Disco C: {disk.percent}% ({disk.used/1e9:.0f} / {disk.total/1e9:.0f} GB)"
        )

        if battery:
            text += f"\nBateria: {battery.percent}%"
            if battery.power_plugged:
                text += " (cargando)"

        await update.message.reply_text(text, parse_mode="Markdown")
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {e}")


# ─── MENSAJES ───────────────────────────────────────────────────────────────

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_text = update.message.text.strip()
    chat_id = update.effective_chat.id
    save_chat_id(chat_id)

    if not user_text:
        return

    # Mensaje de espera
    await update.message.chat.send_action(action="typing")

    try:
        # Procesar con el router
        result, is_chat = router.route(user_text)

        if result:
            # Es una accion (skill, agente, etc.)
            response_text = result.get("display") or result.get("voice") or "Listo."
            thought = result.get("thought", "")

            # Enviar respuesta
            await update.message.reply_text(response_text)

            # Si hay pensamiento, enviarlo en un mensaje separado mas pequeño
            if thought and CONFIG["jarvis"].get("debug"):
                try:
                    await update.message.reply_text(f"🤔 _{thought[:200]}_", parse_mode="Markdown")
                except Exception:
                    pass

        elif is_chat:
            # Conversacion normal con el brain
            reply = brain.chat(user_text)
            await update.message.reply_text(reply)

        else:
            await update.message.reply_text("No entendi el comando.")

    except Exception as e:
        await update.message.reply_text(f"❌ Error: {e}")
        print(f"[BOT ERROR] {e}")


# ─── MAIN ───────────────────────────────────────────────────────────────────

def main():
    print("[BOT] Iniciando bot de Telegram...")

    app = Application.builder().token(TOKEN).build()

    # Comandos
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("id", cmd_id))
    app.add_handler(CommandHandler("ping", cmd_ping))
    app.add_handler(CommandHandler("captura", cmd_screenshot))
    app.add_handler(CommandHandler("status", cmd_status))

    # Mensajes de texto normales (no comandos)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    print("[BOT] Bot corriendo. Abre Telegram y envía /start a tu bot.")
    print("[BOT] Presiona Ctrl+C para detener.")

    app.run_polling()


if __name__ == "__main__":
    main()