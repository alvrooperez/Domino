"""
Configuración de marcadores ArUco — se ejecuta UNA SOLA VEZ para medir los TCP.

Pasos:
  1. Pega los 4 marcadores (aruco_0..3.png) en las esquinas del área de juego.
  2. Ejecuta este script con el robot en modo Remote Control.
  3. Para cada marcador visible en la imagen:
       - Mueve el TCP del robot al centro exacto del marcador (a Z de recogida).
       - Pulsa la tecla con el ID del marcador (0, 1, 2 ó 3).
       - Escribe las coordenadas X Y que muestra el teach pendant.
  4. Con al menos 3 marcadores registrados, pulsa T para guardar.

Salida: arucos_config.json  (no tocar a mano)

A partir de aquí test_move_to_tile.py se calibra automáticamente en cada ejecución.
"""

import cv2
import numpy as np
import json
import time
import os

CAMERA_INDEX = 3
Z_FIJA       = 0.039          # altura de recogida en metros (igual que en test_move)
OUTPUT_PATH  = os.path.join(os.path.dirname(os.path.abspath(__file__)), "arucos_config.json")
DICT_TYPE    = cv2.aruco.DICT_4X4_50


def _detectar(frame, aruco_dict, params):
    try:
        detector = cv2.aruco.ArucoDetector(aruco_dict, params)
        corners, ids, _ = detector.detectMarkers(frame)
    except AttributeError:
        corners, ids, _ = cv2.aruco.detectMarkers(frame, aruco_dict, parameters=params)
    return corners, ids


def main():
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

    print("\n  Controles:")
    print("    0 / 1 / 2 / 3  → registrar TCP del marcador visible")
    print("    T              → guardar y salir (mínimo 3 marcadores)")
    print("    D              → borrar el último registrado")
    print("    Q / ESC        → salir sin guardar\n")

    waiting_input = False

    while True:
        ret, frame = cap.read()
        if not ret:
            continue

        frame = cv2.rotate(frame, cv2.ROTATE_180)
        disp  = cv2.resize(frame, (800, 450))
        scale_u = orig_w / 800.0
        scale_v = orig_h / 450.0

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
        cv2.putText(disp, f"Registrados {n}/4: {sorted(markers_config.keys())}  T=guardar  Q=salir",
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
            with open(OUTPUT_PATH, "w") as f:
                json.dump(config, f, indent=4)
            print(f"\n[OK] Guardado en {OUTPUT_PATH}")
            break

        elif key in [ord('0'), ord('1'), ord('2'), ord('3')]:
            marker_id = key - ord('0')
            visible = ids is not None and marker_id in ids.flatten()
            if not visible:
                print(f"  [!] Marcador {marker_id} no visible en la imagen.")
                continue
            print(f"\n  [Marcador {marker_id}] Mueve el TCP al centro del marcador a Z={Z_FIJA} m.")
            print("  Introduce  X Y  en metros (ej: 0.213 -0.187):  ", end="", flush=True)
            try:
                raw = input().strip().split()
                x, y = float(raw[0]), float(raw[1])
                markers_config[marker_id] = {"tcp_x": x, "tcp_y": y}
                print(f"  OK: marcador {marker_id} → X={x:.4f}  Y={y:.4f}")
            except (ValueError, IndexError):
                print("  [!] Entrada no válida, marcador no guardado.")

    cap.release()
    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
