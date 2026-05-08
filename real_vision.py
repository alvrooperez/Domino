import zmq
import json
import time
import cv2
import os
import sys

# Añadir rutas para importar módulos locales
HERE = os.path.dirname(os.path.abspath(__file__))
DOMINO_DIR = os.path.abspath(os.path.join(HERE, '..'))
CALIB_DIR = os.path.join(HERE, "CameraCalibration")
PRUEBA_DOS_DIR = os.path.join(HERE, "prueba_dos")

sys.path.insert(0, HERE)
sys.path.insert(0, CALIB_DIR)
sys.path.insert(0, PRUEBA_DOS_DIR)

from Deteccion_fichas import DominoDetector
from aruco_calibrator import calibrar_con_arucos

# --- CONFIGURACIÓN DE ZONAS (Ajustar según realidad) ---
# Estas coordenadas están en metros (espacio Robot)
# Basado en tu descripción: Centro es tablero, Izquierda es mano robot.
X_LIMITE_MANO = -0.2  # Ejemplo: lo que esté a la izquierda de X=-0.2 es la mano
ARUCO_CONFIG_PATH = os.path.join(PRUEBA_DOS_DIR, "arucos_config.json")
CAMERA_INDEX = 2
# -------------------------------------------------------

def run_vision():
    # Cargar config de ArUcos
    try:
        with open(ARUCO_CONFIG_PATH) as f:
            aruco_config = json.load(f)
        print(f"[REAL_VISION] Config ArUco cargada.")
    except Exception as e:
        print(f"[ERROR] No se pudo cargar config ArUco: {e}")
        return

    # Inicializar Cámara
    cap = cv2.VideoCapture(CAMERA_INDEX, cv2.CAP_V4L2)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH,  2304)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 1296)
    
    context = zmq.Context()
    socket_motor = context.socket(zmq.REP)
    socket_motor.bind("tcp://*:5555")

    print(f"[REAL_VISION] Servidor listo (Puerto 5555, Cámara {CAMERA_INDEX}). Esperando peticiones...")

    while True:
        message = socket_motor.recv_string()
        
        if message == "GET_STATE":
            # 0. Estabilización de la cámara (esperar a que el robot pare y la cámara enfoque)
            time.sleep(1.5)
            # Limpiar buffer de la cámara (leer frames viejos)
            for _ in range(5): cap.read()
            
            ret, frame = cap.read()
            if not ret:
                print("[REAL_VISION] ERROR: No se pudo capturar frame de la cámara.")
                socket_motor.send_string(json.dumps({"error": "No camera frame"}))
                continue
            
            # 1. Rotar y Calibrar dinámicamente con ArUcos
            frame = cv2.rotate(frame, cv2.ROTATE_180)
            calib_model, n_arucos, debug_frame = calibrar_con_arucos(frame, aruco_config)
            
            if calib_model is None:
                print(f"[REAL_VISION] ERROR: Solo {n_arucos} ArUcos detectados (necesarios 3).")
                socket_motor.send_string(json.dumps({"error": "Calibration failed - check ArUcos"}))
                continue

            # 2. Detectar fichas usando el modelo recién calculado
            detector = DominoDetector(calib_model=calib_model)
            res_img, all_tiles, all_poses = detector.procesar(frame)
            
            print(f"[REAL_VISION] Detecion completada. Total detectado: {len(all_poses)}")
            for k, p in all_poses.items():
                print(f"  -> {k} en X:{p['x']:.3f}, Y:{p['y']:.3f}, Th:{p['theta']:.1f}")

            # --- MOSTRAR VISIÓN PARA DEBUG ---
            cv2.imshow("DOMINO VISION - REAL TIME", res_img)
            cv2.waitKey(1) 
            # ---------------------------------
            
            # 3. Clasificar fichas por Zonas
            board_list = []
            hand_list = []
            
            for clave, pose in all_poses.items():
                if pose['x'] < X_LIMITE_MANO:
                    hand_list.append((clave, pose))
                else:
                    if not clave.startswith("reverso"):
                        board_list.append((clave, pose))
            
            # Ordenar MANO por Y (de arriba a abajo -> Y mayor a Y menor)
            hand_list.sort(key=lambda item: item[1]['y'], reverse=True)
            # Ordenar TABLERO por X (de izquierda a derecha)
            board_list.sort(key=lambda item: item[1]['x'])

            robot_hand = []
            robot_hand_poses = {}
            for i, (clave, pose) in enumerate(hand_list):
                if not clave.startswith("reverso"):
                    val1, val2 = map(int, clave.split('_'))
                    robot_hand.append([val1, val2])
                    pose['slot_index'] = i
                    robot_hand_poses[clave] = pose

            board = []
            board_poses = {}
            for i, (clave, pose) in enumerate(board_list):
                val1, val2 = map(int, clave.split('_'))
                board.append([val1, val2])
                pose['board_index'] = i
                board_poses[clave] = pose
            
            boneyard_poses = {k: v for k, v in all_poses.items() if k.startswith("reverso")}
            
            state = {
                "board": board,
                "robot_hand": robot_hand,
                "robot_hand_poses": robot_hand_poses,
                "board_poses": board_poses,
                "boneyard_poses": boneyard_poses,
                "human_hand_count": 7,
                "boneyard_empty": len(boneyard_poses) == 0
            }
            socket_motor.send_string(json.dumps(state))

        elif message == "SIMULATE_HUMAN_MOVE":
            socket_motor.send_string(json.dumps({"status": "done"}))

if __name__ == "__main__":
    run_vision()
