"""
Test de Ciclo Completo: Detecta fichas bocarabajo (reverso), las recoge,
las voltea dejándolas en la mano, y luego las mueve de la mano al tablero.

Uso:
    python test_ciclo_completo.py
"""

import sys
import json
import time
import math
import cv2
import os

HERE = os.path.dirname(os.path.abspath(__file__))
# Añadir rutas del proyecto de forma relativa para importar los módulos.
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
DESCENSO_VOLTEO    = 0.116
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
        return

    with open(ARUCO_CONFIG_PATH) as f:
        aruco_config = json.load(f)

    # ── Conectar robot ─────────────────────────────────────────────────────────
    robot = RobotController(ROBOT_IP)
    robot.connect()

    if robot.con_io is None:
        robot.disconnect()
        print("[ERROR] RTDEIOInterface no disponible.")
        return
    
    robot.move_to_fixed_joint(POSICION_BASE)

    # ── Capturar ───────────────────────────────────────────────────────────────
    print("[1] Capturando imagen...")
    frame = capturar_frame()
    if frame is None:
        robot.disconnect()
        return

    # ── Calibrar ───────────────────────────────────────────────────────────────
    print("[2] Calibrando con ArUcos...")
    calib_model, n_arucos, debug_frame = calibrar_con_arucos(frame, aruco_config)

    cv2.imshow("ArUco - Calibracion", debug_frame)
    cv2.waitKey(2000)
    cv2.destroyAllWindows()

    if calib_model is None:
        print(f"[ERROR] Solo {n_arucos} marcador(es) visible(s) (mínimo 3).")
        robot.disconnect()
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
        robot.disconnect()
        return

    # ── Filtrar solo las fichas bocarabajo (reverso) ───────────────────────────
    reverso = {k: v for k, v in poses.items() if k.startswith("reverso")}
    if not reverso:
        print("[!] No hay fichas bocarabajo para realizar el ciclo. Saliendo.")
        robot.disconnect()
        return

    print(f"\n[4] Se van a procesar {len(reverso)} fichas bocarabajo:")
    claves_reverso = list(reverso.keys())
    for i, clave in enumerate(claves_reverso):
        p = reverso[clave]
        print(f"  [{i}] {clave}  →  X={p['x']:.4f}  Y={p['y']:.4f}  θ={p['theta']:.1f}°")

    print("\n  ¿Iniciar secuencia completa? (s/n): ", end="")
    if input().strip().lower() != 's':
        robot.disconnect()
        return

    try:
        config = {
            'Z_APROXIMACION': Z_APROXIMACION,
            'Z_RECOGIDA': Z_RECOGIDA,
            'CORRECCION_GRIPPER': CORRECCION_GRIPPER,
            'DESCENSO_VOLTEO': DESCENSO_VOLTEO,
            'POSICION_BASE': POSICION_BASE
        }

        # ── FASE 1: Recoger, Voltear y Colocar en Mano ─────────────────────────
        print(f"\n{'='*50}\n[FASE 1] RECOGER, VOLTEAR Y PONER EN MANO\n{'='*50}")
        for slot_index, clave in enumerate(claves_reverso):
            pose_ficha = reverso[clave].copy() # Copia para no modificar el original
            if POSICION_BASE == "tablero_robo":
                pose_ficha['x'] = -pose_ficha['x']
                pose_ficha['y'] = -pose_ficha['y']
                
            print(f"\n---> Ficha {clave} (Hueco Mano: {slot_index}) <---")
            robot.recoger_voltear_y_colocar(pose_ficha, slot_index, config)

        # ── FASE 2: Mover de la Mano al Tablero ────────────────────────────────
        print(f"\n{'='*50}\n[FASE 2] MOVER DE LA MANO AL TABLERO\n{'='*50}")
        for slot_index in range(len(claves_reverso)):
            print(f"\n---> Hueco Mano: {slot_index} -> Tablero Pos: {slot_index} <---")
            robot.mover_mano_a_tablero(slot_index, slot_index, config)

        print(f"\n[5] Volviendo a posición segura '{POSICION_BASE}'...")
        robot.move_to_fixed_joint(POSICION_BASE)
        print("\n[OK] ¡Ciclo completo finalizado con éxito!")

    except Exception as e:
        print(f"\n[ERROR] {e}")
    finally:
        robot.disconnect()

if __name__ == "__main__":
    main()