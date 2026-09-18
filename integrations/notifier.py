import os
import asyncio
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()
TOKEN = os.getenv("TELEGRAM_TOKEN")

CHAT_ID_FILE = Path("memory/telegram_chat_id.txt")


def get_saved_chat_id():
    """Lee el chat_id guardado."""
    try:
        if CHAT_ID_FILE.exists():
            return CHAT_ID_FILE.read_text(encoding="utf-8").strip()
    except Exception:
        pass
    return None


async def _send_async(message, image_path=None):
    """Envia mensaje (y opcionalmente imagen) por Telegram."""
    from telegram import Bot
    chat_id = get_saved_chat_id()
    if not chat_id or not TOKEN:
        return False
    try:
        bot = Bot(token=TOKEN)
        if image_path and Path(image_path).exists():
            with open(image_path, "rb") as f:
                await bot.send_photo(chat_id=chat_id, photo=f, caption=message[:1000])
        else:
            await bot.send_message(chat_id=chat_id, text=message[:4000])
        return True
    except Exception as e:
        print(f"[NOTIFIER ERROR] {e}")
        return False


def send(message, image_path=None):
    """Envia notificacion (bloqueante, para usar desde codigo sincrono)."""
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        result = loop.run_until_complete(_send_async(message, image_path))
        loop.close()
        return result
    except Exception as e:
        print(f"[NOTIFIER ERROR] {e}")
        return False


def send_async(message, image_path=None):
    """Version no-bloqueante. Retorna thread."""
    import threading
    t = threading.Thread(target=send, args=(message, image_path), daemon=True)
    t.start()
    return t