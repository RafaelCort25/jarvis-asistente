import os
import asyncio
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()
TOKEN = os.getenv("TELEGRAM_TOKEN")

CHAT_ID_FILE = Path("memory/telegram_chat_id.txt")

# Extensiones que se envian como foto (no como documento)
IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp"}


def get_saved_chat_id():
    """Lee el chat_id guardado."""
    try:
        if CHAT_ID_FILE.exists():
            return CHAT_ID_FILE.read_text(encoding="utf-8").strip()
    except Exception:
        pass
    return None


async def _send_async(message, image_path=None, document_path=None):
    """Envia mensaje, imagen o documento por Telegram."""
    from telegram import Bot
    chat_id = get_saved_chat_id()
    if not chat_id or not TOKEN:
        return False

    try:
        bot = Bot(token=TOKEN)

        # Enviar documento (PDF, docx, xlsx, etc.)
        if document_path:
            p = Path(document_path)
            if not p.exists():
                await bot.send_message(chat_id=chat_id, text=f"[NOTIFIER] Archivo no existe: {p.name}")
                return False
            with open(p, "rb") as f:
                await bot.send_document(
                    chat_id=chat_id,
                    document=f,
                    filename=p.name,
                    caption=(message or "")[:1000],
                )
            return True

        # Enviar imagen (photo)
        if image_path and Path(image_path).exists():
            with open(image_path, "rb") as f:
                await bot.send_photo(chat_id=chat_id, photo=f, caption=(message or "")[:1000])
            return True

        # Solo texto
        await bot.send_message(chat_id=chat_id, text=(message or "")[:4000])
        return True

    except Exception as e:
        print(f"[NOTIFIER ERROR] {e}")
        return False


def _run_async(coro):
    """Ejecuta una coroutine en un event loop nuevo."""
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        result = loop.run_until_complete(coro)
        loop.close()
        return result
    except Exception as e:
        print(f"[NOTIFIER ERROR] {e}")
        return False


def send(message, image_path=None, document_path=None):
    """Envia notificacion (bloqueante)."""
    return _run_async(_send_async(message, image_path, document_path))


def send_async(message, image_path=None, document_path=None):
    """Version no-bloqueante."""
    import threading
    t = threading.Thread(
        target=send,
        args=(message, image_path, document_path),
        daemon=True,
    )
    t.start()
    return t


def send_file(path, caption=""):
    """
    Envia un archivo por Telegram.
    Detecta automaticamente si va como imagen (photo) o documento.
    Bloqueante.
    """
    p = Path(path)
    if not p.exists():
        print(f"[NOTIFIER] Archivo no existe: {p}")
        return False

    if p.suffix.lower() in IMAGE_EXTS:
        return send(caption or p.name, image_path=str(p))
    else:
        return send(caption or p.name, document_path=str(p))