"""
Configuración de marcadores ArUco — se ejecuta UNA SOLA VEZ por área.

Uso:
    python setup_arucos.py                     # área de juego  (IDs 0-3)
    python setup_arucos.py --position robo     # área de robo/pozo (IDs 4-7)

Pasos:
  1. Pega los 4 marcadores de la posición elegida en las esquinas del área.
  2. Mueve el robot a la posición base de esa área (tablero / tablero_robo).
  3. Para cada marcador visible en la imagen:
       - Mueve el TCP al centro exacto del marcador (a Z de recogida).
       - Pulsa la tecla con el ID del marcador.
       - Escribe las coordenadas X Y que muestra el teach pendant.
  4. Con al menos 3 marcadores registrados, pulsa T para guardar.

Salida: arucos_config.json  o  arucos_robo_config.json
"""

import cv2
import numpy as np
import json
import time
import os

CAMERA_INDEX = 2
Z_FIJA       = 0.039
DICT_TYPE    = cv2.aruco.DICT_4X4_50

HERE = os.path.dirname(os.path.abspath(__file__))

# IDS_POR_POSICION = {
#     "juego": [0, 1, 2, 3],   # ya calibrado — no tocar
#     "robo":  [4, 5, 6, 7],
# }
# OUTPUT_POR_POSICION = {
#     "juego": os.path.join(HERE, "arucos_config.json"),
#     "robo":  os.path.join(HERE, "arucos_robo_config.json"),
# }

POSICION    = "robo"
VALID_IDS   = [5, 6, 7, 8]
OUTPUT_PATH = os.path.join(HERE, "arucos_robo_config.json")


def _detectar(frame, aruco_dict, params):
    try:
        detector = cv2.aruco.ArucoDetector(aruco_dict, params)
        corners, ids, _ = detector.detectMarkers(frame)
    except AttributeError:
        corners, ids, _ = cv2.aruco.detectMarkers(frame, aruco_dict, parameters=params)
    return corners, ids


def main():
    valid_ids   = VALID_IDS
    output_path = OUTPUT_PATH

    print(f"\n=== Setup ArUco — posición: {POSICION.upper()} ===")
    print(f"  IDs esperados : {valid_ids}")
    print(f"  Salida        : {output_path}\n")

    aruco_dict = cv2.aruco.getPredefinedDictionary(DICT_TYPE)
    params     = cv2.aruco.DetectorParameters()

    cap = cv2.VideoCapture(CAMERA_INDEX, cv2.CAP_V4L2)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH,  2304)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 1296)
    time.sleep(2)

    if not cap.isOpened():
        print("[ERROR] No se puede abrir la cámara.")
        return

    ret, test = cap.read()
    if ret:
        h, w = test.shape[:2]
        print(f"[INFO] Cámara: {w}×{h} px")
    orig_w, orig_h = w, h

    markers_config = {}

    ids_str = " / ".join(str(i) for i in valid_ids)
    print(f"  Controles:")
    print(f"    {ids_str}  → registrar TCP del marcador visible")
    print( "    T              → guardar y salir (mínimo 3 marcadores)")
    print( "    D              → borrar el último registrado")
    print( "    Q / ESC        → salir sin guardar\n")

    while True:
        ret, frame = cap.read()
        if not ret:
            continue

        frame = cv2.rotate(frame, cv2.ROTATE_180)
        disp  = cv2.resize(frame, (800, 450))

        corners, ids = _detectar(disp, aruco_dict, params)

        if ids is not None:
            cv2.aruco.drawDetectedMarkers(disp, corners, ids)
            for i, mid in enumerate(ids.flatten()):
                cx = int(np.mean(corners[i][0][:, 0]))
                cy = int(np.mean(corners[i][0][:, 1]))
                done = int(mid) in markers_config
                color = (0, 220, 0) if done else (0, 140, 255)
                cv2.circle(disp, (cx, cy), 8, color, -1)
                label = f"ID{mid} {'OK' if done else '?'}"
                cv2.putText(disp, label, (cx + 10, cy - 8),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1)

        n = len(markers_config)
        color_hud = (0, 220, 0) if n >= 3 else (0, 140, 255)
        cv2.putText(disp, f"pos:{POSICION}  registrados {n}/4: {sorted(markers_config.keys())}  T=guardar  Q=salir",
                    (10, 26), cv2.FONT_HERSHEY_SIMPLEX, 0.5, color_hud, 1)

        cv2.imshow("Setup ArUco", disp)
        key = cv2.waitKey(30) & 0xFF

        if key in (ord('q'), 27):
            print("\n[!] Saliendo sin guardar.")
            break

        elif key == ord('d'):
            if markers_config:
                removed = markers_config.popitem()
                print(f"  [D] Eliminado marcador {removed[0]}")
            else:
                print("  [!] No hay marcadores registrados.")

        elif key == ord('t'):
            if n < 3:
                print(f"  [!] Necesitas al menos 3 marcadores (tienes {n}).")
                continue
            config = {
                "markers"      : {str(k): v for k, v in sorted(markers_config.items())},
                "z_fija"       : Z_FIJA,
                "camera_index" : CAMERA_INDEX,
                "resolution"   : [orig_w, orig_h],
                "dict_type"    : "DICT_4X4_50",
            }
            with open(output_path, "w") as f:
                json.dump(config, f, indent=4)
            print(f"\n[OK] Guardado en {output_path}")
            break

        else:
            # Teclas numéricas: IDs válidos para esta posición (soporta 0-9)
            pressed_id = None
            for mid in valid_ids:
                if mid < 10 and key == ord(str(mid)):
                    pressed_id = mid
                    break

            if pressed_id is not None:
                visible = ids is not None and pressed_id in ids.flatten()
                if not visible:
                    print(f"  [!] Marcador {pressed_id} no visible en la imagen.")
                    continue
                print(f"\n  [Marcador {pressed_id}] Mueve el TCP al centro del marcador a Z={Z_FIJA} m.")
                print("  Introduce  X Y  en metros (ej: 0.213 -0.187):  ", end="", flush=True)
                try:
                    raw = input().strip().split()
                    x, y = float(raw[0]), float(raw[1])
                    markers_config[pressed_id] = {"tcp_x": x, "tcp_y": y}
                    print(f"  OK: marcador {pressed_id} → X={x:.4f}  Y={y:.4f}")
                except (ValueError, IndexError):
                    print("  [!] Entrada no válida, marcador no guardado.")

    cap.release()
    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
