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
X_LIMITE_MANO = -0.2
CAMERA_INDEX = 2

ZONES_CONFIG = {
    "BOARD": os.path.join(PRUEBA_DOS_DIR, "arucos_config.json"),
    "BONEYARD": os.path.join(PRUEBA_DOS_DIR, "arucos_robo_config.json")
}
# -------------------------------------------------------

def run_vision():
    # Cargar configs de ArUcos
    configs = {}
    for zone, path in ZONES_CONFIG.items():
        try:
            with open(path) as f:
                configs[zone] = json.load(f)
            print(f"[REAL_VISION] Config ArUco para {zone} cargada.")
        except Exception as e:
            print(f"[ERROR] No se pudo cargar config ArUco para {zone}: {e}")
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
        
        # Soportar tanto "GET_STATE" (retrocompatibilidad) como "GET_STATE:ZONE"
        zone = "BOARD"
        if ":" in message:
            _, zone = message.split(":")
        
        if message.startswith("GET_STATE"):
            if zone not in configs:
                socket_motor.send_string(json.dumps({"error": f"Unknown zone: {zone}"}))
                continue

            aruco_config = configs[zone]
            
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
            calib_model, n_arucos, debug_frame = calibrar_con_arucos(frame, aruco_config, cap)
            
            if calib_model is None:
                print(f"[REAL_VISION] ERROR: Solo {n_arucos} ArUcos detectados (necesarios 3) en zona {zone}.")
                # Mostrar el frame de calibración fallida para que el usuario sepa por qué falla
                cv2.imshow("DOMINO VISION", debug_frame)
                cv2.waitKey(1)
                socket_motor.send_string(json.dumps({"error": f"Calibration failed in {zone} - check ArUcos"}))
                continue

            # 2. Detectar fichas usando el modelo recién calculado
            detector = DominoDetector(calib_model=calib_model)
            res_img, all_tiles, all_poses = detector.procesar(frame)
            
            print(f"[REAL_VISION] Detección en {zone} completada. Total detectado: {len(all_poses)}")
            
            # --- MOSTRAR VISIÓN PARA DEBUG ---
            cv2.imshow("DOMINO VISION", res_img)
            cv2.waitKey(1) 
            # ---------------------------------
            
            # 3. Clasificar fichas por Zonas (solo relevante en BOARD)
            board_list = []
            hand_list = []
            boneyard_poses = {}
            
            if zone == "BOARD":
                for clave, pose in all_poses.items():
                    if pose['x'] < X_LIMITE_MANO:
                        hand_list.append((clave, pose))
                    else:
                        if not clave.startswith("reverso"):
                            board_list.append((clave, pose))
            else: # BONEYARD
                boneyard_poses = {k: v for k, v in all_poses.items() if k.startswith("reverso")}
            
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
            
            state = {
                "board": board,
                "robot_hand": robot_hand,
                "robot_hand_poses": robot_hand_poses,
                "board_poses": board_poses,
                "boneyard_poses": boneyard_poses,
                "human_hand_count": 7,
                "boneyard_empty": len(boneyard_poses) == 0 if zone == "BONEYARD" else False
            }
            socket_motor.send_string(json.dumps(state))

        elif message == "SIMULATE_HUMAN_MOVE":
            socket_motor.send_string(json.dumps({"status": "done"}))

if __name__ == "__main__":
    run_vision()
