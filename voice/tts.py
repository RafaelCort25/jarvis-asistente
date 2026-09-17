import re
import wave
import tempfile
import os
import winsound
import time
from pathlib import Path
from piper import PiperVoice

ROOT = Path(__file__).resolve().parent.parent
VOICE_MODEL = ROOT / "models" / "voices" / "es_MX-claude-high.onnx"


class TTS:
    def __init__(self, model_path=None):
        self.model_path = model_path or VOICE_MODEL
        if not self.model_path.exists():
            raise FileNotFoundError(f"No se encontro la voz: {self.model_path}")
        config_path = Path(str(self.model_path) + ".json")
        print("[TTS] Cargando voz Piper...")
        self.voice = PiperVoice.load(str(self.model_path), config_path=str(config_path))
        print("[TTS] Voz lista.")

    def clean_for_tts(self, text):
        text = re.sub(r'[*_#`>]', '', text)
        text = re.sub(r'[\U0001F300-\U0001FAFF]', '', text)
        text = text.replace('¿', '').replace('¡', '')
        text = re.sub(r'[\(\)\[\]\{\}]', ' ', text)
        text = re.sub(r'\.{2,}', '.', text)
        text = re.sub(r'\s+', ' ', text)
        return text.strip()

    def speak_async(self, text):
        """Reproduce sin bloquear. Devuelve la ruta del wav temporal."""
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
            winsound.PlaySound(wav_path, winsound.SND_FILENAME | winsound.SND_ASYNC)
            return wav_path
        except Exception as e:
            print(f"[TTS ERROR] {e}")
            return None

    def stop(self):
        """Detiene el audio actual."""
        try:
            winsound.PlaySound(None, winsound.SND_PURGE)
        except Exception:
            pass

    def cleanup(self, wav_path):
        if wav_path and os.path.exists(wav_path):
            try:
                os.remove(wav_path)
            except Exception:
                pass

    def speak(self, text):
        wav_path = self.speak_async(text)
        if not wav_path:
            return
        try:
            # Esperar duracion del wav
            with wave.open(wav_path, "rb") as w:
                duration = w.getnframes() / float(w.getframerate())
            time.sleep(duration)
        finally:
            self.cleanup(wav_path)