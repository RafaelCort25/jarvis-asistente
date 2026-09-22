"""Estado global de audio: evita que el micrófono capte el eco del TTS."""
import time
import threading

_lock = threading.Lock()
_speaking = False
_last_end = 0.0
COOLDOWN = 0.7  # segundos de silencio obligatorio tras terminar de hablar


def mark_start():
    global _speaking
    with _lock:
        _speaking = True


def mark_end():
    global _speaking, _last_end
    with _lock:
        _speaking = False
        _last_end = time.time()


def is_speaking():
    with _lock:
        return _speaking


def in_cooldown():
    """True si Jarvis está hablando o acaba de terminar (dentro del COOLDOWN)."""
    with _lock:
        if _speaking:
            return True
        return (time.time() - _last_end) < COOLDOWN