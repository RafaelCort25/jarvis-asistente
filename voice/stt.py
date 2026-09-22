import numpy as np
import sounddevice as sd
from faster_whisper import WhisperModel
from scipy.io.wavfile import write
import tempfile
import os
import re
import time
from voice import audio_state


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
            "toma una captura, bloquea la pantalla, siguiente cancion. "
            "Comandos de desarrollo: git status, git diff, git log, "
            "git add, git commit, git push, git pull, staging, "
            "haz un commit, añade todo al staging, sube los cambios, "
            "baja los cambios, que cambios tengo, ultimos commits."
            " pon X en spotify, pausa la musica, siguiente cancion, "
            "cancion anterior, que esta sonando, volumen de spotify."
        )
        print(f"[STT] Modelo listo.")

    def _rms(self, frame):
        """Energia RMS del frame (int16)."""
        return float(np.sqrt(np.mean(frame.astype(np.float32) ** 2)))

    def record_until_silence(self, max_duration=15, start_timeout=6,
                             silence_ms=600, energy_threshold=350):
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

    def listen_with_interrupt(self, tts, max_duration=15, silence_ms=600,
                              energy_threshold=900):
        """
        Escucha mientras TTS habla. Si detecta voz, para el TTS.
        Devuelve el texto o None.
        """
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

                # Ignorar cualquier audio mientras Jarvis sigue hablando
                if audio_state.is_speaking():
                    continue

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
        t0 = time.time()
        peak = int(np.abs(audio).max())
        
        # Si el audio dura menos de 0.5 seg → ruido
        if len(audio) < samplerate * 0.5:
            print(f"[STT] audio muy corto ({len(audio)/samplerate:.2f}s), ignorado")
            return ""
        if peak < 500:
            print(f"[STT] peak bajo ({peak}), ignorado")
            return ""

        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            wav_path = f.name
        try:
            write(wav_path, samplerate, audio)
            duration = len(audio) / samplerate
            t1 = time.time()
            print(f"[STT] audio={duration:.2f}s peak={peak}")
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
            t2 = time.time()
            print(f"[STT] whisper={t2-t1:.2f}s raw={text!r}")
            cleaned = self.clean(text)
            if cleaned.lower() in ("hasta luego", "gracias", "adios", "ok"):
                print(f"[STT] filtrado alucinacion: {cleaned!r}")
                return ""
            if cleaned:
                print(f"[STT] limpio={cleaned!r}")
            return cleaned
        finally:
            if os.path.exists(wav_path):
                os.remove(wav_path)

    def clean(self, text):
        t = text.lower().strip()

        # FILTRO 1: alucinaciones exactas
        exact_hallucinations = {
            "hasta luego", "hasta luego.", "hasta luego!",
            "gracias.", "gracias", "adios.", "adios",
            "ok.", "ok", "subtitulos", "subtitulos.",
            "gracias por ver", "gracias por ver el video",
            "suscribete", "suscribete.", "amara.org",
            "www.", "valen.", "valen",
        }
        if t in exact_hallucinations:
            return ""

        # FILTRO 2: alucinaciones parciales en textos cortos
        hallucinations_substr = [
            "gracias por ver", "subtitulos", "subtítulos",
            "amara.org", "suscribete", "suscríbete",
        ]
        if len(t) < 40 and any(h in t for h in hallucinations_substr):
            return ""

        # FILTRO 3: limpieza basica
        t = t.replace(",", " ").replace("  ", " ").strip()
        t = re.sub(r'^[\s,\.\?\!¡¿]+', '', t)
        t = re.sub(r'\bnote ?pad\b', 'notepad', t)
        t = re.sub(r'\b(abri|abrime|abreme|abrino)\b', 'abre', t)
        t = re.sub(r'\bpong\b', 'pon', t)
        t = re.sub(r'\bponle\b', 'pon', t)

        corrections = {
            r'\b(pong\s*,?\s*bat\s*,?\s*boni|pong\s*,?\s*bat\s*,?\s*booni|pong\s*,?\s*bat\s*,?\s*bunny)\b': 'pon bad bunny',
            r'\b(pombat ?bonnie|bat ?booni|bat ?boni|bat ?bunny|bad ?boni|bat ?buny|bad ?bonni|bat ?boni|bat ?bonni|bat ?buny)\b': 'bad bunny',
            r'\b(bay ?boni|beibi ?boni)\b': 'bad bunny',
            r'\b(feo ?de ?verdad|feid)\b': 'feid',
            r'\b(karol ?g|karolg|carol ?g)\b': 'karol g',
            r'\b(ozuna|osuna)\b': 'ozuna',
            r'\b(daddy ?yankee|dadi ?yanki)\b': 'daddy yankee',
            r'\b(maluma|malumba)\b': 'maluma',
            r'\b(anuel|manuel ?aa|anuel ?aa)\b': 'anuel aa',
            r'\b(rauw ?alejandro|rau ?alejandro|rauw)\b': 'rauw alejandro',
            r'\b(duki|dooky)\b': 'duki',
            r'\b(mora|moraa)\b': 'mora',
            r'\b(tiago ?pzk|tiago ?pizc|tiago)\b': 'tiago pzk',
            r'\b(shakira|chakira)\b': 'shakira',
            r'\b(michael ?jackson|maicol ?yacson)\b': 'michael jackson',
            r'\b(luis ?miguel|luis ?migel)\b': 'luis miguel',
            r'\b(juan ?gabriel|guan ?gabriel)\b': 'juan gabriel',
                        # Dev / git
            r'\bcomits?\b': 'commits',
            r'\bcomit\b': 'commit',
            r'\best[aá]jien\b': 'staging',
            r'\bestaging\b': 'staging',
            r'\binstagram\b': 'staging',
            r'\binsta\b': 'staging',
            r'\besta?yin\b': 'staging',
            r'\bgit\s+estatus\b': 'git status',
            r'\bgrid\s+status\b': 'git status',
            r'\bgit\s+estado\b': 'git status',
            r'\bgit\s+adb\b': 'git add',
            r'\bgit\s+comi\b': 'git commit',
            r'\bgit\s+comit\b': 'git commit',
            r'\bgit\s+pus\b': 'git push',
            r'\bgit\s+pul\b': 'git pull',
            r'\bpañade\b': 'añade',
            r'\bpanade\b': 'añade',
            r'\bagnade\b': 'añade',
                        # Spotify
            r'\bespoti?fai?\b': 'spotify',
            r'\bespotify\b': 'spotify',
            r'\bsiguente\b': 'siguiente',
            r'\bsiguient\b': 'siguiente',
            r'\bcanción\b': 'cancion',
            r'\bcanció?n\b': 'cancion',
        }

        for pattern, replacement in corrections.items():
            t = re.sub(pattern, replacement, t)

        return t.strip()

    def listen(self):
        """Devuelve texto o None si no se detecto voz."""
        result = self.record_until_silence()
        if result is None:
            return None
        audio, sr = result
        text = self.transcribe(audio, sr)
        return text if text else None