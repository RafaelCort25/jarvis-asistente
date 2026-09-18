import cv2
import numpy as np
import pickle
from pathlib import Path


FACES_DIR = Path("security/faces")
MODEL_PATH = Path("security/recognizer_model.yml")
LABELS_PATH = Path("security/labels.pkl")


def train():
    """Entrena el reconocedor con todas las fotos en security/faces/."""
    if not FACES_DIR.exists():
        print(f"[TRAIN] No existe {FACES_DIR}. Captura fotos primero.")
        return

    # Listar personas (una carpeta = una persona)
    persons = [d for d in FACES_DIR.iterdir() if d.is_dir()]
    if not persons:
        print(f"[TRAIN] No hay carpetas de personas en {FACES_DIR}.")
        return

    print(f"[TRAIN] Personas encontradas: {[p.name for p in persons]}")

    faces = []
    labels = []
    label_map = {}  # nombre -> id
    current_id = 0

    for person_dir in persons:
        name = person_dir.name
        if name not in label_map:
            label_map[name] = current_id
            current_id += 1

        person_id = label_map[name]
        photos = list(person_dir.glob("*.jpg"))

        if not photos:
            print(f"[TRAIN] {name}: sin fotos, saltando")
            continue

        print(f"[TRAIN] {name}: {len(photos)} fotos")

        for photo_path in photos:
            img = cv2.imread(str(photo_path), cv2.IMREAD_GRAYSCALE)
            if img is None:
                continue
            # Asegurar tamaño 200x200
            if img.shape != (200, 200):
                img = cv2.resize(img, (200, 200))
            faces.append(img)
            labels.append(person_id)

    if not faces:
        print("[TRAIN] No se encontraron fotos validas.")
        return

    print(f"[TRAIN] Entrenando con {len(faces)} fotos...")

    # Crear y entrenar el reconocedor LBPH
    recognizer = cv2.face.LBPHFaceRecognizer_create()
    recognizer.train(faces, np.array(labels))

    # Guardar modelo
    recognizer.save(str(MODEL_PATH))
    print(f"[TRAIN] Modelo guardado en: {MODEL_PATH}")

    # Guardar mapa de etiquetas (id -> nombre y nombre -> id)
    id_to_name = {v: k for k, v in label_map.items()}
    with open(LABELS_PATH, "wb") as f:
        pickle.dump({"name_to_id": label_map, "id_to_name": id_to_name}, f)
    print(f"[TRAIN] Etiquetas guardadas en: {LABELS_PATH}")

    print(f"[TRAIN] Personas entrenadas: {list(label_map.keys())}")
    print("[TRAIN] Listo! Ya puedes usar el reconocimiento.")


if __name__ == "__main__":
    train()