import cv2
import sys
from pathlib import Path


def capture_training_faces(person_name="alessandro", n_photos=15):
    """Captura N fotos de la cara y las guarda para entrenamiento."""
    output_dir = Path("security/faces") / person_name
    output_dir.mkdir(parents=True, exist_ok=True)

    face_cascade = cv2.CascadeClassifier(
        cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
    )

    cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        print("[FACE] No se pudo abrir la camara")
        return

    print(f"[FACE] Capturando {n_photos} fotos para '{person_name}'")
    print("[FACE] Instrucciones:")
    print("  - Mueve ligeramente la cabeza entre cada foto")
    print("  - Presiona ESPACIO para capturar")
    print("  - Presiona Q para salir")
    print(f"[FACE] Guardando en: {output_dir}\n")

    captured = 0

    while captured < n_photos:
        ret, frame = cap.read()
        if not ret:
            break

        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        faces = face_cascade.detectMultiScale(gray, 1.1, 4)

        for (x, y, w, h) in faces:
            cv2.rectangle(frame, (x, y), (x + w, y + h), (0, 255, 0), 2)

        cv2.putText(frame, f"Capturas: {captured}/{n_photos}", (10, 30),
                    cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)
        cv2.putText(frame, "ESPACIO: capturar | Q: salir", (10, 70),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)

        cv2.imshow("Jarvis - Captura de rostro", frame)

        key = cv2.waitKey(1) & 0xFF

        if key == ord("q"):
            break

        if key == 32 and len(faces) > 0:  # espacio
            (x, y, w, h) = faces[0]
            margin = 20
            y1 = max(0, y - margin)
            y2 = min(gray.shape[0], y + h + margin)
            x1 = max(0, x - margin)
            x2 = min(gray.shape[1], x + w + margin)
            face_crop = gray[y1:y2, x1:x2]
            face_crop = cv2.resize(face_crop, (200, 200))

            filename = output_dir / f"{person_name}_{captured:03d}.jpg"
            cv2.imwrite(str(filename), face_crop)
            print(f"[FACE] Foto {captured+1}/{n_photos} guardada: {filename.name}")
            captured += 1

            # Feedback visual
            cv2.putText(frame, "CAPTURADA!", (10, 110),
                        cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 255), 3)
            cv2.imshow("Jarvis - Captura de rostro", frame)
            cv2.waitKey(300)

    cap.release()
    cv2.destroyAllWindows()
    print(f"\n[FACE] Captura finalizada. {captured} fotos en {output_dir}")


if __name__ == "__main__":
    name = sys.argv[1] if len(sys.argv) > 1 else "alessandro"
    capture_training_faces(name)