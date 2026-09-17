import numpy as np
import sounddevice as sd
from faster_whisper import WhisperModel
from scipy.io.wavfile import write
import tempfile
import os
import re


class STT:
    def __init__(self, model_size="small", language="es", device=1):
        print(f"[STT] Cargando modelo Whisper '{model_size}'...")
        self.model = WhisperModel(model_size, device="cpu", compute_type="int8")
        self.language = language
        self.device = device
        self.samplerate = 16000
        self.frame_ms = 30
        self.frame_size = int(self.samplerate * self.frame_ms / 1000)
        self.initial_prompt = (
            "Comandos para un asistente de PC: abre notepad, abre brave, "
            "abre youtube, pon musica, sube el volumen, el primero, "
            "el segundo, busca en google, abre la carpeta de descargas, "
            "busca el archivo, encuentra el archivo, guarda nota, "
            "toma una captura, bloquea la pantalla, siguiente cancion."
        )
        print(f"[STT] Modelo listo.")

    def _rms(self, frame):
        """Energia RMS del frame (int16)."""
        return float(np.sqrt(np.mean(frame.astype(np.float32) ** 2)))

    def record_until_silence(self, max_duration=15, start_timeout=6,
                             silence_ms=700, energy_threshold=350):
        """
        Graba hasta detectar silencio despues de voz.
        - energy_threshold: RMS minimo para considerar voz
        - silence_ms: cuanto silencio seguido para terminar
        - start_timeout: si no hay voz en X seg, abortar
        """
        print("[STT] Escuchando...")
        frames = []
        triggered = False
        silence_frames = 0
        silence_limit = int(silence_ms / self.frame_ms)
        max_frames = int(max_duration * 1000 / self.frame_ms)
        start_limit = int(start_timeout * 1000 / self.frame_ms)

        with sd.InputStream(
            samplerate=self.samplerate,
            channels=1,
            dtype="int16",
            blocksize=self.frame_size,
            device=self.device,
        ) as stream:
            while True:
                frame, _ = stream.read(self.frame_size)
                rms = self._rms(frame)

                if rms > energy_threshold:
                    triggered = True
                    silence_frames = 0
                    frames.append(frame.copy())
                else:
                    if triggered:
                        frames.append(frame.copy())
                        silence_frames += 1
                        if silence_frames >= silence_limit:
                            break
                    else:
                        if len(frames) == 0:
                            start_limit -= 1
                            if start_limit <= 0:
                                return None

                if len(frames) >= max_frames:
                    break

        if not frames:
            return None

        return np.concatenate(frames, axis=0), self.samplerate

    def listen_with_interrupt(self, tts, max_duration=15, silence_ms=700,
                              energy_threshold=350):
        """
        Escucha mientras TTS habla. Si detecta voz, para el TTS.
        Devuelve el texto o None.
        """
        import time
        interrupted = False
        frames = []
        triggered = False
        silence_frames = 0
        silence_limit = int(silence_ms / self.frame_ms)
        max_frames = int(max_duration * 1000 / self.frame_ms)

        with sd.InputStream(
            samplerate=self.samplerate,
            channels=1,
            dtype="int16",
            blocksize=self.frame_size,
            device=self.device,
        ) as stream:
            while True:
                frame, _ = stream.read(self.frame_size)
                rms = self._rms(frame)

                if rms > energy_threshold:
                    if not interrupted:
                        tts.stop()
                        interrupted = True
                    triggered = True
                    silence_frames = 0
                    frames.append(frame.copy())
                else:
                    if triggered:
                        frames.append(frame.copy())
                        silence_frames += 1
                        if silence_frames >= silence_limit:
                            break

                if len(frames) >= max_frames:
                    break

        if not frames:
            return None

        audio = np.concatenate(frames, axis=0)
        return self.transcribe(audio, self.samplerate)

    def transcribe(self, audio, samplerate):
        peak = int(np.abs(audio).max())
        if peak < 300:
            return ""

        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            wav_path = f.name
        try:
            write(wav_path, samplerate, audio)
            segments, _ = self.model.transcribe(
                wav_path,
                language=self.language,
                initial_prompt=self.initial_prompt,
                vad_filter=True,
                vad_parameters=dict(min_silence_duration_ms=200),
                beam_size=1,
                temperature=0.0,
                condition_on_previous_text=False,
            )
            text = " ".join(seg.text for seg in segments).strip()
            return self.clean(text)
        finally:
            if os.path.exists(wav_path):
                os.remove(wav_path)

    def clean(self, text):
        t = text.lower().strip()
        t = re.sub(r'^[\s,\.\?\!¡¿]+', '', t)
        t = re.sub(r'\bnote ?pad\b', 'notepad', t)
        t = re.sub(r'\b(abri|abrime|abreme|abrino)\b', 'abre', t)
        return t.strip()

    def listen(self):
        """Devuelve texto o None si no se detecto voz."""
        result = self.record_until_silence()
        if result is None:
            return None
        audio, sr = result
        text = self.transcribe(audio, sr)
        return text if text else None