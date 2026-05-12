import zmq
import json
import time
import os
import sys

# Añadir rutas para importar módulos locales
HERE = os.path.dirname(os.path.abspath(__file__))
DOMINO_DIR = os.path.abspath(os.path.join(HERE, '..'))
sys.path.insert(0, DOMINO_DIR)

from robot_controller import RobotController

# --- CONFIGURACIÓN ROBOT ---
ROBOT_IP = "169.254.12.28"
CONFIG_MOVIMIENTO = {
    'Z_APROXIMACION': 0.12,
    'Z_RECOGIDA': 0.039,
    'CORRECCION_GRIPPER': 20.0,
    'DESCENSO_VOLTEO': 0.13,
    'POSICION_BASE': "tablero"
}
# ---------------------------

def run_control():
    robot = RobotController(ROBOT_IP)
    try:
        robot.connect()
    except Exception as e:
        print(f"[ERROR] No se pudo conectar al robot: {e}")
        return

    context = zmq.Context()
    socket_motor = context.socket(zmq.REP)
    socket_motor.bind("tcp://*:5556")

    print("[REAL_CONTROL] UR3e listo (Puerto 5556).")
    robot.move_to_fixed_joint(CONFIG_MOVIMIENTO['POSICION_BASE'])

    while True:
        msg_str = socket_motor.recv_string()
        cmd = json.loads(msg_str)
        
        action = cmd.get("action")
        print(f"[REAL_CONTROL] Recibida acción: {action}")

        try:
            if action == "MOVE_TO_POSITION":
                pos = cmd.get("position", "tablero")
                robot.move_to_fixed_joint(pos)
                
            elif action == "MOVE":
                # Asegurar que la posición base es tablero para jugar
                CONFIG_MOVIMIENTO['POSICION_BASE'] = "tablero"
                
                slot_mano = cmd.get("slot_mano", 0) 
                slot_tablero = cmd.get("slot_tablero", 0)
                
                # Obtener la pose de destino enviada por el motor
                place_pose = cmd.get("place_pose")
                
                if place_pose:
                    print(f"[REAL_CONTROL] Movimiento a tablero: X={place_pose['x']:.3f}, Y={place_pose['y']:.3f}, Theta={place_pose['theta']:.1f}")
                    # Aquí el robot debería usar place_pose para el destino final
                    # por ahora el método mover_mano_a_tablero usa un desplazamiento fijo,
                    # deberíamos actualizarlo para usar la pose real si queremos precisión.
                
                robot.mover_mano_a_tablero(slot_mano, place_pose, CONFIG_MOVIMIENTO)

            elif action == "STEAL":
                # Asegurar que la posición base es tablero_robo para robar
                CONFIG_MOVIMIENTO['POSICION_BASE'] = "tablero_robo"
                
                grab = cmd["grab_pose"]
                slot_destino = cmd.get("slot_mano", 0)
                
                robot.recoger_voltear_y_colocar(grab, slot_destino, CONFIG_MOVIMIENTO)

            socket_motor.send_string(json.dumps({"status": "done"}))
        
        except Exception as e:
            print(f"[ERROR] {e}")
            socket_motor.send_string(json.dumps({"status": "error", "message": str(e)}))

if __name__ == "__main__":
    run_control()
