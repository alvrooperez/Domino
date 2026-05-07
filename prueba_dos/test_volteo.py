"""
Test de volteo: detecta fichas en reverso, las recoge y las voltea.

Flujo:
  1. Captura imagen y calibra con ArUcos.
  2. Detecta todas las fichas; muestra las que están en reverso.
  3. El usuario elige cuál voltear.
  4. Robot recoge la ficha → va a 'tablero' (pinza cerrada) →
     va a 'pre_volteo' (pinza cerrada) → baja 0.116 m (pinza cerrada).

Antes de ejecutar: define 'pre_volteo' en robot_controller.py.

Uso:
    python test_volteo.py
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
ARUCO_CONFIG_PATH  = os.path.join(HERE, "arucos_config.json")
Z_APROXIMACION     = 0.12
Z_RECOGIDA         = 0.039
CORRECCION_GRIPPER = 20.0
POSICION_BASE      = "tablero"
DESCENSO_VOLTEO    = 0.116   # metros que baja desde pre_volteo
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
    print(f"[INFO] Resolución: {w}×{h} px")
    return cv2.rotate(frame, cv2.ROTATE_180)


def main():
    # ── Cargar config ArUco ────────────────────────────────────────────────────
    if not os.path.exists(ARUCO_CONFIG_PATH):
        print(f"[ERROR] No se encuentra {ARUCO_CONFIG_PATH}")
        print("        Ejecuta primero setup_arucos.py.")
        return

    with open(ARUCO_CONFIG_PATH) as f:
        aruco_config = json.load(f)

    # ── Capturar ───────────────────────────────────────────────────────────────
    print("[1] Capturando imagen...")
    frame = capturar_frame()
    if frame is None:
        return

    # ── Calibrar ───────────────────────────────────────────────────────────────
    print("[2] Calibrando con ArUcos...")
    calib_model, n_arucos, debug_frame = calibrar_con_arucos(frame, aruco_config)

    cv2.imshow("ArUco - Calibracion", debug_frame)
    cv2.waitKey(2000)
    cv2.destroyAllWindows()

    if calib_model is None:
        print(f"[ERROR] Solo {n_arucos} marcador(es) visible(s) (mínimo 3).")
        return

    # ── Detectar fichas ────────────────────────────────────────────────────────
    print("[3] Detectando fichas...")
    detector = DominoDetector(calib_model=calib_model)
    resultado_img, fichas, poses = detector.procesar(frame)

    cv2.imshow("Deteccion", resultado_img)
    cv2.waitKey(2000)
    cv2.destroyAllWindows()

    if not poses:
        print("[!] No se detectó ninguna ficha. Saliendo.")
        return

    # ── Mostrar fichas en reverso ──────────────────────────────────────────────
    reverso = {k: v for k, v in poses.items() if k.startswith("reverso")}
    cara    = {k: v for k, v in poses.items() if not k.startswith("reverso")}

    if not reverso:
        print("[!] No hay fichas en reverso. Saliendo.")
        return

    print(f"\n[4] Fichas en reverso ({len(reverso)}):")
    claves_reverso = list(reverso.keys())
    for i, clave in enumerate(claves_reverso):
        p = reverso[clave]
        print(f"  [{i}] {clave}  →  X={p['x']:.4f}  Y={p['y']:.4f}  θ={p['theta']:.1f}°")

    if cara:
        print(f"\n  (También detectadas cara-arriba: {list(cara.keys())})")

    # ── Elegir ficha y hueco ───────────────────────────────────────────────────
    print("\n  Número de ficha a voltear (o 'q' para salir): ", end="")
    sel = input().strip()
    if sel.lower() == 'q':
        return
    try:
        idx        = int(sel)
        clave      = claves_reverso[idx]
        pose_ficha = reverso[clave]
    except (ValueError, IndexError):
        print("[!] Selección no válida.")
        return

    print("  Número de hueco en la mano para dejarla (0, 1, 2...): ", end="")
    sel_hueco = input().strip()
    try:
        slot_index = int(sel_hueco)
    except ValueError:
        print("[!] Número de hueco no válido.")
        return

    tcp_x = pose_ficha['x']
    tcp_y = pose_ficha['y']
    if POSICION_BASE == "tablero_robo":
        tcp_x = -tcp_x
        tcp_y = -tcp_y

    print(f"\n[5] Objetivo: {clave}  X={tcp_x:.4f}  Y={tcp_y:.4f}  θ={pose_ficha['theta']:.1f}°")

    # ── Conectar robot ─────────────────────────────────────────────────────────
    robot = RobotController(ROBOT_IP)
    robot.connect()

    if robot.con_io is None:
        robot.disconnect()
        print("[ERROR] RTDEIOInterface no disponible.")
        return

    try:
        # [6] Ir a posición base
        print(f"\n[6] Moviendo a '{POSICION_BASE}'...")
        robot.move_to_fixed_joint(POSICION_BASE)
        robot.gripper_neutral()

        # [7] Calcular orientación del gripper alineada con la ficha
        angulo_deseado = (math.radians(pose_ficha['theta'])
                          + math.pi / 2
                          + math.radians(CORRECCION_GRIPPER))
        orient = [
            math.pi * math.cos(angulo_deseado / 2),
            math.pi * math.sin(angulo_deseado / 2),
            0.0,
        ]

        # [8] Pre-posicionar joint 6
        tcp_tablero  = robot.get_current_pose()
        q_tablero    = list(robot.get_current_joints())
        alpha_actual = 2.0 * math.atan2(tcp_tablero[4], tcp_tablero[3])
        delta_j6     = angulo_deseado - alpha_actual
        delta_j6     = (delta_j6 + math.pi) % (2 * math.pi) - math.pi
        q_tablero[5] += delta_j6
        print(f"\n[7] Pre-posicionando gripper  Δ={math.degrees(delta_j6):.1f}°...")
        robot.move_joint(q_tablero, speed=0.5, acceleration=0.5)

        # [9] Aproximación
        print(f"\n[8] Aproximación a Z={Z_APROXIMACION} m...")
        robot.move_linear([tcp_x, tcp_y, Z_APROXIMACION] + orient, speed=0.15, acceleration=0.1)

        # [10] Descenso y agarre
        print(f"\n[9] Descendiendo a Z={Z_RECOGIDA} m...")
        robot.move_linear([tcp_x, tcp_y, Z_RECOGIDA] + orient, speed=0.05, acceleration=0.05)
        robot.gripper_neutral()
        robot.gripper_close(delay=1.0)
        print("    Ficha agarrada.")

        # [11] Volver a tablero con la ficha (pinza cerrada)
        print(f"\n[10] Volviendo a '{POSICION_BASE}' con la ficha (pinza cerrada)...")
        robot.move_to_fixed_joint(POSICION_BASE)

        # [12] Ir a pre_volteo (pinza cerrada)
        print("\n[11] Moviendo a 'pre_volteo' (pinza cerrada)...")
        robot.move_to_fixed_joint("pre_volteo")

        # [13] Bajar DESCENSO_VOLTEO metros en Z
        print(f"\n[12] Bajando {DESCENSO_VOLTEO*100:.0f} cm en Z (pinza cerrada)...")
        robot.move_relative_cartesian([0.0, 0.0, -DESCENSO_VOLTEO, 0.0, 0.0, 0.0],
                                      speed=0.05, acceleration=0.05)

        # [14] Desplazar -Y 0.045 m (empuje lateral para voltear)
        print("\n[13] Desplazando -Y 4.5 cm...")
        robot.move_relative_cartesian([0.0, -0.045, 0.0, 0.0, 0.0, 0.0],
                                      speed=0.05, acceleration=0.05)
        time.sleep(0.5)

        # [15] Subir 0.05 m en Z
        print("\n[14] Subiendo 5 cm en Z...")
        robot.move_relative_cartesian([0.0, 0.0, 0.05, 0.0, 0.0, 0.0],
                                      speed=0.05, acceleration=0.05)

        # [16] Ir a post_volteo
        print("\n[15] Moviendo a 'post_volteo'...")
        robot.move_to_fixed_joint("post_volteo")
        time.sleep(0.5)

        # [17] Bajar 0.067 m en Z para depositar
        print("\n[16] Bajando 6.7 cm en Z para depositar...")
        robot.move_relative_cartesian([0.0, 0.0, -0.072, 0.0, 0.0, 0.0],
                                      speed=0.05, acceleration=0.05)

        # [18] Abrir pinza
        print("\n[17] Abriendo pinza...")
        robot.gripper_open(delay=0.5)
        robot.gripper_neutral()

        # [19] Volver a pre_volteo y luego a tablero
        print("\n[18] Volviendo a 'pre_volteo'...")
        robot.move_to_fixed_joint("pre_volteo")

        print(f"\n[19] Volviendo a '{POSICION_BASE}'...")
        robot.move_to_fixed_joint(POSICION_BASE)

        print("\n[OK] Volteo completado.")

    except Exception as e:
        print(f"\n[ERROR] {e}")

    finally:
        robot.disconnect()


if __name__ == "__main__":
    main()
