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
    'DESCENSO_VOLTEO': 0.116,
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
            if action == "MOVE":
                # El motor nos manda la ficha y las poses, pero para usar mover_mano_a_tablero
                # necesitamos saber en qué SLOT de la mano está físicamente.
                # Como el motor gestiona el orden de la mano, podemos usar un mapeo o pedirlo.
                # Por ahora, intentamos deducir el slot basado en la pose o el orden.
                
                # TODO: El motor debería enviar el slot_index. 
                # Si no lo envía, lo estimamos o buscamos la ficha más cercana.
                slot_mano = cmd.get("slot_mano", 0) 
                slot_tablero = cmd.get("slot_tablero", 0)
                
                print(f" -> Ejecutando: mover_mano_a_tablero(slot_mano={slot_mano}, slot_tablero={slot_tablero})")
                robot.mover_mano_a_tablero(slot_mano, slot_tablero, CONFIG_MOVIMIENTO)

            elif action == "STEAL":
                # El motor ha decidido robar. 
                # Necesitamos: 1. Ir a la zona de pozo (pendiente definir posición fija)
                # 2. Detectar cual es la ficha a robar (grab_pose)
                # 3. Llamar a recoger_voltear_y_colocar
                
                grab = cmd["grab_pose"]
                slot_destino = cmd.get("slot_mano", 0)
                
                print(f" -> Ejecutando: recoger_voltear_y_colocar en slot {slot_destino}")
                robot.recoger_voltear_y_colocar(grab, slot_destino, CONFIG_MOVIMIENTO)

            socket_motor.send_string(json.dumps({"status": "done"}))
        
        except Exception as e:
            print(f"[ERROR] {e}")
            socket_motor.send_string(json.dumps({"status": "error", "message": str(e)}))

if __name__ == "__main__":
    run_control()
