import cv2


def detect_faces_once(camera_index=0, save_path=None):
    """Abre la camara, detecta caras, y opcionalmente guarda una foto."""
    face_cascade = cv2.CascadeClassifier(
        cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
    )

    cap = cv2.VideoCapture(camera_index)
    if not cap.isOpened():
        print("[FACE] No se pudo abrir la camara")
        return False

    print("[FACE] Camara abierta. Presiona Q para salir.")
    print("[FACE] Cuando detecte tu cara, presiona S para guardar.")

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        faces = face_cascade.detectMultiScale(gray, 1.1, 4)

        # Dibujar rectangulos
        for (x, y, w, h) in faces:
            cv2.rectangle(frame, (x, y), (x + w, y + h), (0, 255, 0), 2)

        cv2.putText(
            frame,
            f"Caras: {len(faces)}",
            (10, 30),
            cv2.FONT_HERSHEY_SIMPLEX,
            1,
            (0, 255, 0),
            2,
        )

        cv2.imshow("Jarvis - Deteccion de caras", frame)

        key = cv2.waitKey(1) & 0xFF
        if key == ord("q"):
            break
        if key == ord("s") and len(faces) > 0:
            if save_path:
                cv2.imwrite(save_path, frame)
                print(f"[FACE] Guardado: {save_path}")
                break

    cap.release()
    cv2.destroyAllWindows()
    return True


if __name__ == "__main__":
    detect_faces_once()