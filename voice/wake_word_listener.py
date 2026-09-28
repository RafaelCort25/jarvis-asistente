"""Escucha continua del micrófono para detectar 'Oye Senna' usando Whisper local."""
import threading
import time
import numpy as np
import sounddevice as sd
from voice import audio_state


class WakeWordListener:
    def __init__(self, stt, threshold=500, min_duration=0.8, max_duration=3.5, device=1):
        self.stt = stt
        self.threshold = threshold
        self.min_duration = min_duration
        self.max_duration = max_duration
        self.device = device
        self.samplerate = 16000
        self.frame_ms = 30
        self.frame_size = int(self.samplerate * self.frame_ms / 1000)
        self._running = False
        self._thread = None
        self._listeners = []
        self._lock = threading.Lock()
        self._last_detection = 0
        self._patterns = ["oye senna", "hey senna", "ey senna", "oi senna",
                          "hola senna", "senna", "sena", "oye sena"]

    def subscribe(self, callback):
        with self._lock:
            self._listeners.append(callback)

    def unsubscribe(self, callback):
        with self._lock:
            if callback in self._listeners:
                self._listeners.remove(callback)

    def _notify(self, text):
        with self._lock:
            for cb in list(self._listeners):
                try:
                    cb(text)
                except Exception as e:
                    print(f"[WAKE] Error en callback: {e}")

    def is_running(self):
        return self._running

    def _contains_wake(self, text):
        return any(p in text for p in self._patterns)

    def _loop(self):
        print("[WAKE] Listener iniciado en thread")
        try:
            with sd.InputStream(
                samplerate=self.samplerate,
                channels=1,
                dtype="int16",
                blocksize=self.frame_size,
                device=self.device,
            ) as stream:
                while self._running:
                    frame, _ = stream.read(self.frame_size)
                    if audio_state.is_speaking() or audio_state.in_cooldown():
                        continue

                    rms = float(np.sqrt(np.mean(frame.astype(np.float32) ** 2)))
                    if rms < self.threshold:
                        continue

                    frames = [frame.copy()]
                    silence_count = 0
                    silence_limit = int(500 / self.frame_ms)
                    total_frames = int(self.max_duration * 1000 / self.frame_ms)

                    while self._running and len(frames) < total_frames:
                        f, _ = stream.read(self.frame_size)
                        if audio_state.is_speaking():
                            break
                        frames.append(f.copy())
                        r = float(np.sqrt(np.mean(f.astype(np.float32) ** 2)))
                        if r < self.threshold:
                            silence_count += 1
                            if silence_count >= silence_limit:
                                break
                        else:
                            silence_count = 0

                    if len(frames) * self.frame_ms / 1000 < self.min_duration:
                        continue

                    audio = np.concatenate(frames, axis=0)
                    try:
                        text = self.stt.transcribe(audio, self.samplerate)
                        if not text:
                            continue
                        tl = text.lower().strip()
                        print(f"[WAKE] Escuche: {tl}")
                        if self._contains_wake(tl):
                            now = time.time()
                            if now - self._last_detection < 3:
                                continue
                            self._last_detection = now
                            print(f"[WAKE] *** DETECTADO: {tl} ***")
                            self._notify(tl)
                    except Exception as e:
                        print(f"[WAKE] Error transcribiendo: {e}")
        except Exception as e:
            print(f"[WAKE] Error en loop: {e}")
        finally:
            self._running = False
            print("[WAKE] Listener detenido")

    def start(self):
        if self._running:
            return False
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        return True

    def stop(self):
        if not self._running:
            return False
        self._running = False
        if self._thread:
            self._thread.join(timeout=3)
        return True
