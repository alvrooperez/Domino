"""
Script de prueba: detecta fichas con la cámara y mueve el robot a la que elijas.

Uso:
    python test_move_to_tile.py
"""

import sys
import json
import time
import math
import cv2

sys.path.insert(0, "/home/pedro/Laboratorio")
sys.path.insert(0, "/home/pedro/Laboratorio/Domino/CameraCalibration")

from Deteccion_fichas import DominoDetector

# ── Importar RobotController desde dev/control ────────────────────────────────
# Asegúrate de tener el branch dev/control accesible o copiar robot_controller.py
sys.path.insert(0, "/home/pedro/Laboratorio/Domino")
from robot_controller import RobotController

# ── Configuración ─────────────────────────────────────────────────────────────
ROBOT_IP       = "169.254.12.28"
CAMERA_INDEX   = 2
CALIB_PATH     = "/home/pedro/Laboratorio/Domino/CameraCalibration/calibracion_juego.json"
Z_APROXIMACION      = 0.12   # altura de aproximación sobre la ficha (metros)
Z_RECOGIDA          = 0.039  # altura de recogida (z_fija de calibración)
CORRECCION_GRIPPER  = 20.0   # corrección horaria en grados (+ horario, - antihorario)
POSICION_BASE       = "tablero"  # "tablero" o "tablero_robo"

# ── Punto de referencia para verificar/corregir la calibración en tiempo real ─
# Pon una marca física fija en la mesa (pegatina, tornillo...) y rellena
# sus coordenadas TCP reales aquí.  Si no quieres usar esta función, déjalo None.
# Para obtener el TCP: mueve el robot a esa marca a mano y lee getActualTCPPose().
REFERENCIA_TCP = [-0.041, 0.434]          # Ejemplo: [0.213, -0.187]  (X, Y en metros)
# ─────────────────────────────────────────────────────────────────────────────


def capturar_y_detectar(calib_model):
    cap = cv2.VideoCapture(CAMERA_INDEX, cv2.CAP_V4L2)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH,  2304)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 1296)
    time.sleep(2)

    if not cap.isOpened():
        print("[ERROR] No se puede abrir la cámara.")
        return None, None

    ret, frame = cap.read()
    cap.release()

    if not ret:
        print("[ERROR] No se pudo capturar frame.")
        return None, None

    h, w = frame.shape[:2]
    print(f"[INFO] Resolución capturada: {w}x{h} px")
    if w != 2304 or h != 1296:
        print(f"[AVISO] Resolución distinta a la de calibración (2304x1296). "
              f"Las coordenadas pueden ser incorrectas.")

    frame = cv2.rotate(frame, cv2.ROTATE_180)
    detector = DominoDetector(calib_model=calib_model)
    resultado_img, fichas, poses = detector.procesar(frame)

    cv2.imshow("Deteccion", resultado_img)
    cv2.waitKey(1000)
    cv2.destroyAllWindows()

    return fichas, poses


def verificar_calibracion(calib_model):
    """
    Muestra la imagen y pide al usuario que haga clic sobre la marca de referencia.
    Devuelve (offset_x, offset_y) que se suma a todas las predicciones TCP.
    Si REFERENCIA_TCP es None, devuelve (0, 0) sin hacer nada.
    """
    if REFERENCIA_TCP is None:
        return 0.0, 0.0

    print("\n[CAL] Verificando calibración con punto de referencia...")
    print(f"      TCP real conocido: X={REFERENCIA_TCP[0]:.4f}  Y={REFERENCIA_TCP[1]:.4f}")
    print("      Haz clic sobre la MARCA DE REFERENCIA en la imagen y cierra la ventana.")

    cap = cv2.VideoCapture(CAMERA_INDEX, cv2.CAP_V4L2)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH,  2304)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 1296)
    time.sleep(1)
    ret, frame = cap.read()
    cap.release()

    if not ret:
        print("[AVISO] No se pudo capturar imagen para verificación. Offset = 0.")
        return 0.0, 0.0

    orig_h, orig_w = frame.shape[:2]
    frame = cv2.rotate(frame, cv2.ROTATE_180)
    disp  = cv2.resize(frame, (800, 450))

    click_ref = []

    def _cb(event, x, y, flags, param):
        if event == cv2.EVENT_LBUTTONDOWN:
            click_ref.clear()
            click_ref.append((x, y))
            cv2.circle(disp, (x, y), 8, (0, 0, 255), -1)
            cv2.imshow("Referencia - clic sobre la marca", disp)

    cv2.namedWindow("Referencia - clic sobre la marca")
    cv2.setMouseCallback("Referencia - clic sobre la marca", _cb)
    cv2.imshow("Referencia - clic sobre la marca", disp)
    cv2.waitKey(0)
    cv2.destroyAllWindows()

    if not click_ref:
        print("[AVISO] No se hizo clic. Offset = 0.")
        return 0.0, 0.0

    # Convertir clic (800x450) → píxel nativo
    xu, yv = click_ref[0]
    u_nat = xu * (orig_w / 800.0)
    v_nat = yv * (orig_h / 450.0)

    m = calib_model
    pred_x = m["coef_x"][0] * u_nat + m["coef_x"][1] * v_nat + m["intercept_x"]
    pred_y = m["coef_y"][0] * u_nat + m["coef_y"][1] * v_nat + m["intercept_y"]

    off_x = REFERENCIA_TCP[0] - pred_x
    off_y = REFERENCIA_TCP[1] - pred_y
    print(f"[CAL] Predicción: X={pred_x:.4f}  Y={pred_y:.4f}")
    print(f"[CAL] Offset aplicado: ΔX={off_x*1000:.1f} mm  ΔY={off_y*1000:.1f} mm")
    return off_x, off_y


def main():

    # Cargar calibración
    with open(CALIB_PATH) as f:
        calib_model = json.load(f)
    print(f"[OK] Calibración cargada (z_fija={calib_model['z_fija']} m)")

    # ── Verificar calibración con punto de referencia (opcional) ──────────────
    offset_x, offset_y = verificar_calibracion(calib_model)

    # Detectar fichas
    print("\n[1] Capturando imagen y detectando fichas...")
    fichas, poses = capturar_y_detectar(calib_model)

    if not fichas:
        print("[!] No se detectaron fichas. Saliendo.")
        return

    # Aplicar offset de calibración a todas las poses detectadas
    if offset_x != 0.0 or offset_y != 0.0:
        for p in poses.values():
            p['x'] = round(p['x'] + offset_x, 5)
            p['y'] = round(p['y'] + offset_y, 5)

    # Mostrar fichas detectadas
    print(f"\n[2] Fichas detectadas ({len(fichas)}):")
    claves = list(poses.keys())
    for i, clave in enumerate(claves):
        p = poses[clave]
        print(f"  [{i}] {clave}  →  X={p['x']:.4f}  Y={p['y']:.4f}  θ={p['theta']:.1f}°")

    # Elegir ficha objetivo
    print("\n  Elige el número de la ficha a la que mover el robot (o 'q' para salir): ", end="")
    sel = input().strip()
    if sel.lower() == 'q':
        return
    try:
        idx = int(sel)
        clave = claves[idx]
        pose_ficha = poses[clave]
    except (ValueError, IndexError):
        print("[!] Selección no válida.")
        return

    tcp_x = pose_ficha['x']
    tcp_y = pose_ficha['y']

    # Desde tablero_robo el marco está girado 180°: X e Y se negan
    if POSICION_BASE == "tablero_robo":
        tcp_x = -tcp_x
        tcp_y = -tcp_y

    print(f"\n[3] Objetivo: ficha {clave}  →  X={tcp_x:.4f}  Y={tcp_y:.4f}  θ={pose_ficha['theta']:.1f}°")

    # Conectar robot
    robot = RobotController(ROBOT_IP)
    robot.connect()

    if robot.con_io is None:
        robot.disconnect()
        print("[ERROR] RTDEIOInterface no disponible. Deshabilita EtherNet/IP o PROFINET en el teach pendant (Installation → Fieldbus) y vuelve a intentarlo.")
        return

    try:
        # ── [4] Ir a posición segura ──────────────────────────────────────────
        print(f"\n[4] Moviendo a posición '{POSICION_BASE}' (articular)...")
        robot.move_to_fixed_joint(POSICION_BASE)

        # ── [5] Calcular orientación TCP explícita: recto hacia abajo + ángulo ficha
        # Rotation vector para gripper perpendicular al tablero y alineado con la ficha:
        # Rz(θ)·Rx(π) → [π·cos(θ/2), π·sin(θ/2), 0]  (Rz=0 garantiza perpendicularidad)
        angulo_deseado = math.radians(pose_ficha['theta']) + math.pi / 2 + math.radians(CORRECCION_GRIPPER)
        orient = [math.pi * math.cos(angulo_deseado / 2),
                  math.pi * math.sin(angulo_deseado / 2),
                  0.0]

        # ── [6] Pre-posicionar joint 6 para que el IK no dé vueltas ──────────
        tcp_tablero = robot.get_current_pose()
        q_tablero   = list(robot.get_current_joints())

        alpha_actual = 2.0 * math.atan2(tcp_tablero[4], tcp_tablero[3])
        delta_j6     = angulo_deseado - alpha_actual
        delta_j6     = (delta_j6 + math.pi) % (2 * math.pi) - math.pi  # camino más corto

        q_tablero[5] += delta_j6
        print(f"\n[5] Pre-posicionando gripper (joint 6) Δ={math.degrees(delta_j6):.1f}°...")
        robot.move_joint(q_tablero, speed=0.5, acceleration=0.5)

        # ── [6] Aproximación: moveL con orientación explícita (recto hacia abajo)
        pose_aprox = [tcp_x, tcp_y, Z_APROXIMACION] + orient
        print(f"\n[6] Aproximación a Z={Z_APROXIMACION} m sobre la ficha...")
        robot.move_linear(pose_aprox, speed=0.15, acceleration=0.1)

        # ── [7] Descenso y agarre ─────────────────────────────────────────────

        print(f"\n  ¿Descender a Z={Z_RECOGIDA} m y agarrar? (s/n): ", end="")
        resp = input().strip().lower()
        if resp == 's':
            pose_recogida = [tcp_x, tcp_y, Z_RECOGIDA] + orient
            print("[7] Descendiendo a la ficha...")
            robot.move_linear(pose_recogida, speed=0.05, acceleration=0.05)

            # Cerrar pinza: 00 → 01
            robot.gripper_neutral()
            robot.gripper_close(delay=1.0)
            print("     Ficha agarrada.")

            input(f"\n  Pulsa ENTER para volver a posición '{POSICION_BASE}'...")

            # Subir con la ficha
            robot.move_to_fixed_joint(POSICION_BASE)

            # Soltar: 01 → 00 → 10 → 00
            robot.gripper_open(delay=0.5)
            robot.gripper_neutral()
        else:
            robot.move_to_fixed_joint(POSICION_BASE)

        print("\n[OK] Prueba completada.")

    finally:
        robot.disconnect()


if __name__ == "__main__":
    main()
