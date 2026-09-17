import numpy as np
import sounddevice as sd
from openwakeword.model import Model

class WakeWord:
    def __init__(self, wakeword="hey_jarvis", device=1, threshold=0.25):
        print(f"[WAKE] Cargando modelo '{wakeword}'...")
        self.model = Model(wakeword_models=[wakeword], inference_framework="onnx")
        self.device = device
        self.threshold = threshold
        self.samplerate = 16000
        self.chunk_size = 1280
        print(f"[WAKE] Listo. Umbral: {threshold}")

    def wait_for_wake(self):
        with sd.InputStream(
            samplerate=self.samplerate,
            channels=1,
            dtype="int16",
            blocksize=self.chunk_size,
            device=self.device,
        ) as stream:
            while True:
                audio, _ = stream.read(self.chunk_size)
                prediction = self.model.predict(audio.flatten())
                for ww, score in prediction.items():
                    if score > self.threshold:
                        self.model.reset()
                        return True
