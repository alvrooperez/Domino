"""
Genera imágenes de marcadores ArUco (IDs 0–3) para imprimir y pegar en la mesa.

Uso:
    python generate_arucos.py

Salida: aruco_0.png … aruco_3.png

Imprime cada imagen a ~5×5 cm. Cuanto más grande, más fiable la detección.
Pega los 4 marcadores en las esquinas del área de juego, fijos y planos.
"""

import cv2
import os

DICT_TYPE   = cv2.aruco.DICT_4X4_50
MARKER_SIZE = 300   # píxeles (imprime a unos 5–7 cm para mejor detección)
N_MARKERS   = 4
OUT_DIR     = os.path.dirname(os.path.abspath(__file__))

aruco_dict = cv2.aruco.getPredefinedDictionary(DICT_TYPE)

for marker_id in range(N_MARKERS):
    try:
        img = cv2.aruco.generateImageMarker(aruco_dict, marker_id, MARKER_SIZE)
    except AttributeError:
        img = cv2.aruco.drawMarker(aruco_dict, marker_id, MARKER_SIZE)

    # Borde blanco para ayudar a la detección
    img = cv2.copyMakeBorder(img, 30, 30, 30, 30, cv2.BORDER_CONSTANT, value=255)

    path = os.path.join(OUT_DIR, f"aruco_{marker_id}.png")
    cv2.imwrite(path, img)
    print(f"  Guardado: {path}")

print("\nImprime los 4 marcadores y pégalos en las esquinas del área de juego.")
print("Sugerencia de disposición:")
print("  [0] esquina superior-izquierda   [1] esquina superior-derecha")
print("  [2] esquina inferior-izquierda   [3] esquina inferior-derecha")
