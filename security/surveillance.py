import cv2
import pickle
import time
import threading
from pathlib import Path
from datetime import datetime


MODEL_PATH = Path("security/recognizer_model.yml")
LABELS_PATH = Path("security/labels.pkl")
ALERTS_DIR = Path("security/alerts")
ALERTS_DIR.mkdir(parents=True, exist_ok=True)

CONFIDENCE_THRESHOLD = 70  # > umbral = desconocido
COOLDOWN_SECONDS = 30      # Esperar entre alertas
SCAN_INTERVAL = 1.0        # Segundos entre escaneos


class Surveillance:
    def __init__(self, camera_index=0, on_unknown=None):
        """
        on_unknown: callback(foto_path, confidence) que se llama cuando
                    se detecta un desconocido (para enviar a Telegram).
        """
        self.camera_index = camera_index
        self.on_unknown = on_unknown
        self.running = False
        self.thread = None
        self.last_alert_time = 0
        self.last_unknown_name = None

        # Cargar modelo
        if not MODEL_PATH.exists():
            raise FileNotFoundError(f"Falta el modelo: {MODEL_PATH}")

        self.recognizer = cv2.face.LBPHFaceRecognizer_create()
        self.recognizer.read(str(MODEL_PATH))

        with open(LABELS_PATH, "rb") as f:
            data = pickle.load(f)
        self.id_to_name = data["id_to_name"]

        self.face_cascade = cv2.CascadeClassifier(
            cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
        )

        print(f"[SURV] Modelo cargado. Personas conocidas: {list(self.id_to_name.values())}")

    def _process_frame(self, frame):
        """Detecta caras y devuelve lista de (nombre, confidence, roi_rect)."""
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        faces = self.face_cascade.detectMultiScale(gray, 1.1, 4)

        results = []
        for (x, y, w, h) in faces:
            roi = gray[y:y + h, x:x + w]
            roi = cv2.resize(roi, (200, 200))
            try:
                person_id, confidence = self.recognizer.predict(roi)
                name = self.id_to_name.get(person_id, "Desconocido")
                is_unknown = confidence > CONFIDENCE_THRESHOLD
                results.append({
                    "name": "Desconocido" if is_unknown else name,
                    "confidence": confidence,
                    "is_unknown": is_unknown,
                    "rect": (x, y, w, h),
                })
            except Exception as e:
                print(f"[SURV] Error predict: {e}")
        return results

    def _save_alert_photo(self, frame):
        """Guarda la foto del desconocido."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        path = ALERTS_DIR / f"unknown_{timestamp}.jpg"
        cv2.imwrite(str(path), frame)
        return path

    def _loop(self):
        """Loop principal de vigilancia."""
        cap = cv2.VideoCapture(self.camera_index)
        if not cap.isOpened():
            print("[SURV] No se pudo abrir la camara")
            self.running = False
            return

        print("[SURV] Vigilancia activa. Ctrl+C para detener.")

        try:
            while self.running:
                ret, frame = cap.read()
                if not ret:
                    time.sleep(0.5)
                    continue

                detections = self._process_frame(frame)
                now = time.time()

                for det in detections:
                    if det["is_unknown"]:
                        # Cooldown para no spamear
                        if now - self.last_alert_time < COOLDOWN_SECONDS:
                            continue

                        self.last_alert_time = now

                        # Guardar foto
                        photo_path = self._save_alert_photo(frame)
                        print(f"[SURV] 🚨 DESCONOCIDO detectado. Foto: {photo_path}")

                        # Notificar via callback
                        if self.on_unknown:
                            try:
                                self.on_unknown(str(photo_path), det["confidence"])
                            except Exception as e:
                                print(f"[SURV] Error en callback: {e}")

                        break  # solo 1 alerta por frame

                time.sleep(SCAN_INTERVAL)
        finally:
            cap.release()
            print("[SURV] Vigilancia detenida.")

    def start(self):
        """Inicia la vigilancia en un thread separado."""
        if self.running:
            print("[SURV] Ya esta corriendo.")
            return
        self.running = True
        self.thread = threading.Thread(target=self._loop, daemon=True)
        self.thread.start()
        print("[SURV] Thread de vigilancia iniciado.")

    def stop(self):
        """Detiene la vigilancia."""
        self.running = False
        if self.thread:
            self.thread.join(timeout=3)
        print("[SURV] Detenido.")

    def status(self):
        return "activa" if self.running else "detenida"


# ─── TEST STANDALONE ───────────────────────────────────────────────────────

def _test_alert(photo_path, confidence):
    """Callback de prueba: solo imprime."""
    print(f"[TEST ALERT] Foto: {photo_path}, Confianza: {confidence}")


if __name__ == "__main__":
    surv = Surveillance(on_unknown=_test_alert)
    surv.start()
    print("[TEST] Vigilancia activa 60 segundos. Sal con Ctrl+C.")
    try:
        time.sleep(60)
    except KeyboardInterrupt:
        pass
    surv.stop()