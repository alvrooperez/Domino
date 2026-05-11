"""
Script principal: calibración automática con ArUcos + movimiento a ficha.

Flujo:
  1. Captura un frame.
  2. Detecta los marcadores ArUco → ajusta el modelo pixel→TCP al momento.
  3. Detecta fichas de dominó con ese modelo.
  4. El usuario elige la ficha → el robot se mueve y la agarra.

Uso:
    python test_move_to_tile.py
"""

import sys
import json
import time
import math
import cv2
import os

HERE = os.path.dirname(os.path.abspath(__file__))
# Añadir rutas del proyecto de forma relativa para importar los módulos.
# La estructura esperada es .../Laboratorio/Domino/prueba_dos/
DOMINO_DIR = os.path.abspath(os.path.join(HERE, '..'))
LABORATORIO_DIR = os.path.abspath(os.path.join(DOMINO_DIR, '..'))
sys.path.insert(0, LABORATORIO_DIR)
sys.path.insert(0, DOMINO_DIR)
sys.path.insert(0, os.path.join(DOMINO_DIR, "CameraCalibration"))
sys.path.insert(0, HERE)

from Deteccion_fichas import DominoDetector
from robot_controller import RobotController
from aruco_calibrator import calibrar_con_arucos

# ── Configuración ──────────────────────────────────────────────────────────────
ROBOT_IP           = "169.254.12.28"
CAMERA_INDEX       = 2
POSICION_BASE      = "tablero_robo"   # "tablero" o "tablero_robo"
Z_APROXIMACION     = 0.12        # altura de aproximación sobre la ficha (m)
Z_RECOGIDA         = 0.039       # altura de recogida (= z_fija de calibración)
CORRECCION_GRIPPER = 20.0        # corrección de ángulo en grados (+ horario)

ARUCO_CONFIG_PATH = (
    os.path.join(HERE, "arucos_robo_config.json") if POSICION_BASE == "tablero_robo"
    else os.path.join(HERE, "arucos_config.json")
)
# ──────────────────────────────────────────────────────────────────────────────


def capturar_frame():
    cap = cv2.VideoCapture(CAMERA_INDEX, cv2.CAP_V4L2)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH,  2304)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 1296)
    time.sleep(2)

    if not cap.isOpened():
        print("[ERROR] No se puede abrir la cámara.")
        return None

    ret, frame = cap.read()
    cap.release()

    if not ret:
        print("[ERROR] No se pudo capturar frame.")
        return None

    h, w = frame.shape[:2]
    print(f"[INFO] Resolución capturada: {w}×{h} px")
    if w != 2304 or h != 1296:
        print("[AVISO] Resolución inesperada — la calibración puede ser menos precisa.")

    return cv2.rotate(frame, cv2.ROTATE_180)


def main():
    # ── Cargar configuración ArUco ─────────────────────────────────────────────
    if not os.path.exists(ARUCO_CONFIG_PATH):
        print(f"[ERROR] No se encuentra {ARUCO_CONFIG_PATH}")
        print("        Ejecuta primero setup_arucos.py para medir los TCP de los marcadores.")
        return

    with open(ARUCO_CONFIG_PATH) as f:
        aruco_config = json.load(f)
    print(f"[OK] Config ArUco: {len(aruco_config['markers'])} marcadores definidos "
          f"(IDs {sorted(aruco_config['markers'].keys())})")
    

    robot = RobotController(ROBOT_IP)
    robot.connect()

    if robot.con_io is None:
        robot.disconnect()
        print("[ERROR] RTDEIOInterface no disponible.")
        print("        Deshabilita EtherNet/IP o PROFINET en Installation → Fieldbus.")
        return

    # [6] Posición base
    print(f"\n[0] Moviendo a '{POSICION_BASE}'...")
    robot.move_to_fixed_joint(POSICION_BASE)

    # ── Capturar imagen ────────────────────────────────────────────────────────
    print("\n[1] Capturando imagen...")
    frame = capturar_frame()
    if frame is None:
        return

    # ── Calibración con ArUcos ─────────────────────────────────────────────────
    print("[2] Calibrando con ArUcos...")
    calib_model, n_arucos, debug_frame = calibrar_con_arucos(frame, aruco_config)

    cv2.imshow("ArUco - Calibracion", debug_frame)
    cv2.waitKey(2000)
    cv2.destroyAllWindows()

    if calib_model is None:
        print(f"[ERROR] Solo {n_arucos} marcador(es) visible(s) (mínimo 3).")
        print("        Revisa iluminación, que los ArUcos estén en el campo de visión y planos.")
        return

    print(f"[OK] Modelo calibrado con {n_arucos} ArUcos.")

    # ── Detección de fichas ────────────────────────────────────────────────────
    print("[3] Detectando fichas de dominó...")
    detector = DominoDetector(calib_model=calib_model)
    resultado_img, fichas, poses = detector.procesar(frame)

    cv2.imshow("Deteccion", resultado_img)
    cv2.waitKey(2000)
    cv2.destroyAllWindows()

    if not fichas:
        print("[!] No se detectaron fichas. Saliendo.")
        return

    # ── Elegir ficha ───────────────────────────────────────────────────────────
    print(f"\n[4] Fichas detectadas ({len(fichas)}):")
    claves = list(poses.keys())
    for i, clave in enumerate(claves):
        p = poses[clave]
        print(f"  [{i}] {clave}  →  X={p['x']:.4f}  Y={p['y']:.4f}  θ={p['theta']:.1f}°")

    print("\n  Número de ficha objetivo (o 'q' para salir): ", end="")
    sel = input().strip()
    if sel.lower() == 'q':
        return
    try:
        idx        = int(sel)
        clave      = claves[idx]
        pose_ficha = poses[clave]
    except (ValueError, IndexError):
        print("[!] Selección no válida.")
        return

    tcp_x = pose_ficha['x']
    tcp_y = pose_ficha['y']

    if POSICION_BASE == "tablero_robo":
        tcp_x = tcp_x
        tcp_y = tcp_y

    print(f"\n[5] Objetivo: {clave}  X={tcp_x:.4f}  Y={tcp_y:.4f}  θ={pose_ficha['theta']:.1f}°")

    # ── Conectar robot ─────────────────────────────────────────────────────────
    

    try:
        

        # [7] Calcular orientación: gripper perpendicular al tablero, alineado con la ficha
        angulo_deseado = (math.radians(pose_ficha['theta'])
                          + math.pi / 2
                          + math.radians(CORRECCION_GRIPPER))
        orient = [
            math.pi * math.cos(angulo_deseado / 2),
            math.pi * math.sin(angulo_deseado / 2),
            0.0,
        ]

        # [8] Pre-posicionar joint 6 (camino más corto, evita vuelta completa)
        print(f"\n[7] Pre-posicionando gripper...")
        robot.pre_rotate_gripper(angulo_deseado, speed=0.5, acceleration=0.5)
        # [9] Aproximación
        pose_aprox = [tcp_x, tcp_y, Z_APROXIMACION] + orient
        print(f"\n[8] Aproximación a Z={Z_APROXIMACION} m sobre la ficha...")
        robot.move_linear(pose_aprox, speed=0.15, acceleration=0.1)

        # [10] Descenso y agarre
        print(f"\n  ¿Descender a Z={Z_RECOGIDA} m y agarrar? (s/n): ", end="")
        if input().strip().lower() == 's':
            pose_recogida = [tcp_x, tcp_y, Z_RECOGIDA] + orient
            print("[9] Descendiendo...")
            robot.move_linear(pose_recogida, speed=0.05, acceleration=0.05)

            robot.gripper_neutral()
            robot.gripper_close(delay=1.0)
            print("    Ficha agarrada.")

            input(f"\n  Pulsa ENTER para volver a '{POSICION_BASE}'...")
            robot.move_to_fixed_joint(POSICION_BASE)
            robot.gripper_open(delay=0.5)
            robot.gripper_neutral()
        else:
            robot.move_to_fixed_joint(POSICION_BASE)

        print("\n[OK] Prueba completada.")

    finally:
        robot.disconnect()


if __name__ == "__main__":
    main()
