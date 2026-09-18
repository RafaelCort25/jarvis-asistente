import cv2
import pickle
from pathlib import Path


MODEL_PATH = Path("security/recognizer_model.yml")
LABELS_PATH = Path("security/labels.pkl")
CONFIDENCE_THRESHOLD = 70  # menor = mas estricto


def test():
    if not MODEL_PATH.exists():
        print("[TEST] Falta el modelo. Ejecuta train_recognizer.py primero.")
        return

    recognizer = cv2.face.LBPHFaceRecognizer_create()
    recognizer.read(str(MODEL_PATH))

    with open(LABELS_PATH, "rb") as f:
        labels_data = pickle.load(f)
    id_to_name = labels_data["id_to_name"]

    face_cascade = cv2.CascadeClassifier(
        cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
    )

    cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        print("[TEST] No se pudo abrir la camara")
        return

    print("[TEST] Camara abierta. Presiona Q para salir.")
    print(f"[TEST] Umbral de confianza: {CONFIDENCE_THRESHOLD}")

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        faces = face_cascade.detectMultiScale(gray, 1.1, 4)

        for (x, y, w, h) in faces:
            roi = gray[y:y + h, x:x + w]
            roi = cv2.resize(roi, (200, 200))

            try:
                person_id, confidence = recognizer.predict(roi)
                name = id_to_name.get(person_id, "Desconocido")

                # Confianza: menor = mejor match
                # Si confidence > threshold → desconocido
                if confidence > CONFIDENCE_THRESHOLD:
                    label = "DESCONOCIDO"
                    color = (0, 0, 255)  # rojo
                else:
                    label = f"{name} ({int(confidence)})"
                    color = (0, 255, 0)  # verde
            except Exception as e:
                label = "Error"
                color = (0, 165, 255)
                confidence = 999

            cv2.rectangle(frame, (x, y), (x + w, y + h), color, 2)
            cv2.putText(frame, label, (x, y - 10),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.8, color, 2)

        cv2.imshow("Jarvis - Reconocimiento", frame)

        if cv2.waitKey(1) & 0xFF == ord("q"):
            break

    cap.release()
    cv2.destroyAllWindows()


if __name__ == "__main__":
    test()