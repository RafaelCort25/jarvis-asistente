import re
import wave
import tempfile
import os
import winsound
import time
import threading
from pathlib import Path
from piper import PiperVoice
from voice import audio_state

ROOT = Path(__file__).resolve().parent.parent
VOICE_MODEL = ROOT / "models" / "voices" / "es_MX-claude-high.onnx"


def _wav_duration(path):
    """Devuelve la duración del wav en segundos."""
    with wave.open(path, "rb") as w:
        return w.getnframes() / float(w.getframerate())


class TTS:
    def __init__(self, model_path=None):
        self.model_path = model_path or VOICE_MODEL
        if not self.model_path.exists():
            raise FileNotFoundError(f"No se encontro la voz: {self.model_path}")
        config_path = Path(str(self.model_path) + ".json")
        print("[TTS] Cargando voz Piper...")
        self.voice = PiperVoice.load(str(self.model_path), config_path=str(config_path))
        print("[TTS] Voz lista.")
        self._end_timer = None

    def clean_for_tts(self, text):
        text = re.sub(r'[*_#`>]', '', text)
        text = re.sub(r'[\U0001F300-\U0001FAFF]', '', text)
        text = text.replace('¿', '').replace('¡', '')
        text = re.sub(r'[\(\)\[\]\{\}]', ' ', text)
        text = re.sub(r'\.{2,}', '.', text)
        text = re.sub(r'\s+', ' ', text)
        return text.strip()

    def _cancel_end_timer(self):
        if self._end_timer is not None:
            self._end_timer.cancel()
            self._end_timer = None

    def speak_async(self, text):
        """Reproduce sin bloquear. Marca audio_state para bloquear el micrófono."""
        if not text or not text.strip():
            return None
        clean = self.clean_for_tts(text)
        if not clean:
            return None
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            wav_path = f.name
        try:
            with wave.open(wav_path, "wb") as wav_file:
                self.voice.synthesize_wav(clean, wav_file)
            duration = _wav_duration(wav_path)

            # Marcar estado "hablando" ANTES de reproducir
            audio_state.mark_start()
            winsound.PlaySound(wav_path, winsound.SND_FILENAME | winsound.SND_ASYNC)

            # Programar fin tras la duración del audio (con margen pequeño)
            self._cancel_end_timer()
            self._end_timer = threading.Timer(duration + 0.05, audio_state.mark_end)
            self._end_timer.daemon = True
            self._end_timer.start()

            return wav_path
        except Exception as e:
            print(f"[TTS ERROR] {e}")
            audio_state.mark_end()
            return None

    def stop(self):
        """Detiene el audio actual y libera el estado."""
        try:
            winsound.PlaySound(None, winsound.SND_PURGE)
        except Exception:
            pass
        self._cancel_end_timer()
        audio_state.mark_end()

    def cleanup(self, wav_path):
        if wav_path and os.path.exists(wav_path):
            try:
                os.remove(wav_path)
            except Exception:
                pass

    def speak(self, text):
        """Habla y bloquea hasta terminar. Marca audio_state correctamente."""
        wav_path = self.speak_async(text)
        if not wav_path:
            return
        try:
            duration = _wav_duration(wav_path)
            time.sleep(duration)
        finally:
            self.cleanup(wav_path)