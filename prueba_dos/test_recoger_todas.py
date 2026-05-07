"""
Test de recogida múltiple: detecta todas las fichas y las recoge en el orden indicado.

Flujo:
  1. Captura imagen y calibra con ArUcos.
  2. Detecta todas las fichas y las muestra numeradas.
  3. El usuario introduce el orden de recogida (ej: "0 2 1").
  4. El robot recoge cada ficha una a una y la lleva a 'tablero' donde la suelta.

Nota: la detección se hace una sola vez al inicio. Si una ficha se desplaza al
recoger otra, su posición ya no será válida. En ese caso vuelve a ejecutar el script.

Uso:
    python test_recoger_todas.py
"""

import sys
import json
import time
import math
import cv2
import os

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, "/home/pedro/Laboratorio")
sys.path.insert(0, "/home/pedro/Laboratorio/Domino")
sys.path.insert(0, "/home/pedro/Laboratorio/Domino/CameraCalibration")
sys.path.insert(0, HERE)

from Deteccion_fichas import DominoDetector
from robot_controller import RobotController
from aruco_calibrator import calibrar_con_arucos

# ── Configuración ──────────────────────────────────────────────────────────────
ROBOT_IP           = "169.254.12.28"
CAMERA_INDEX       = 3
ARUCO_CONFIG_PATH  = os.path.join(HERE, "arucos_config.json")
Z_APROXIMACION     = 0.12
Z_RECOGIDA         = 0.039
CORRECCION_GRIPPER = 20.0
POSICION_BASE      = "tablero"
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


def recoger_ficha(robot, tcp_x, tcp_y, theta):
    """Recoge una ficha y vuelve a POSICION_BASE con ella."""
    angulo_deseado = (math.radians(theta)
                      + math.pi / 2
                      + math.radians(CORRECCION_GRIPPER))
    orient = [
        math.pi * math.cos(angulo_deseado / 2),
        math.pi * math.sin(angulo_deseado / 2),
        0.0,
    ]

    # Pre-posicionar joint 6
    tcp_actual = robot.get_current_pose()
    q_actual   = list(robot.get_current_joints())
    alpha      = 2.0 * math.atan2(tcp_actual[4], tcp_actual[3])
    delta_j6   = angulo_deseado - alpha
    delta_j6   = (delta_j6 + math.pi) % (2 * math.pi) - math.pi
    q_actual[5] += delta_j6
    robot.move_joint(q_actual, speed=0.5, acceleration=0.5)

    # Aproximación
    robot.move_linear([tcp_x, tcp_y, Z_APROXIMACION] + orient, speed=0.15, acceleration=0.1)

    # Descenso
    robot.move_linear([tcp_x, tcp_y, Z_RECOGIDA] + orient, speed=0.05, acceleration=0.05)

    # Agarre
    robot.gripper_neutral()
    robot.gripper_close(delay=1.0)

    # Volver a base con la ficha
    robot.move_to_fixed_joint(POSICION_BASE)


def soltar_ficha(robot):
    """Suelta la ficha en POSICION_BASE y deja el gripper en neutro."""
    robot.gripper_open(delay=0.5)
    robot.gripper_neutral()


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

    if not fichas:
        print("[!] No se detectaron fichas. Saliendo.")
        return

    claves = list(poses.keys())
    print(f"\n[4] Fichas detectadas ({len(claves)}):")
    for i, clave in enumerate(claves):
        p = poses[clave]
        print(f"  [{i}] {clave}  →  X={p['x']:.4f}  Y={p['y']:.4f}  θ={p['theta']:.1f}°")

    # ── Elegir orden ───────────────────────────────────────────────────────────
    print(f"\n  Introduce el orden de recogida (ej: '0 2 1') o 'q' para salir: ", end="")
    sel = input().strip()
    if sel.lower() == 'q':
        return

    try:
        orden = [int(x) for x in sel.split()]
        if any(i < 0 or i >= len(claves) for i in orden):
            raise ValueError
    except ValueError:
        print("[!] Orden no válido.")
        return

    secuencia = [(claves[i], poses[claves[i]]) for i in orden]

    print(f"\n  Orden de recogida:")
    for paso, (clave, p) in enumerate(secuencia, 1):
        print(f"    {paso}. {clave}  X={p['x']:.4f}  Y={p['y']:.4f}")

    print("\n  ¿Confirmar y conectar el robot? (s/n): ", end="")
    if input().strip().lower() != 's':
        return

    # ── Conectar robot ─────────────────────────────────────────────────────────
    robot = RobotController(ROBOT_IP)
    robot.connect()

    if robot.con_io is None:
        robot.disconnect()
        print("[ERROR] RTDEIOInterface no disponible.")
        return

    try:
        print(f"\n[5] Moviendo a '{POSICION_BASE}'...")
        robot.move_to_fixed_joint(POSICION_BASE)
        robot.gripper_neutral()

        for paso, (clave, pose) in enumerate(secuencia, 1):
            tcp_x = pose['x']
            tcp_y = pose['y']
            if POSICION_BASE == "tablero_robo":
                tcp_x = -tcp_x
                tcp_y = -tcp_y

            print(f"\n── Paso {paso}/{len(secuencia)}: ficha {clave}  "
                  f"X={tcp_x:.4f}  Y={tcp_y:.4f}  θ={pose['theta']:.1f}° ──")

            recoger_ficha(robot, tcp_x, tcp_y, pose['theta'])
            print(f"   Ficha {clave} recogida → soltando en '{POSICION_BASE}'...")
            soltar_ficha(robot)
            print(f"   Ficha {clave} depositada.")

        print(f"\n[OK] Secuencia completada. {len(secuencia)} ficha(s) recogida(s).")

    except Exception as e:
        print(f"\n[ERROR] {e}")

    finally:
        robot.disconnect()


if __name__ == "__main__":
    main()
