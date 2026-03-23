import zmq
import json
import time

def run_control():
    context = zmq.Context()
    
    # Socket para recibir órdenes del Motor
    socket_motor = context.socket(zmq.REP)
    socket_motor.bind("tcp://*:5556")

    # Socket para avisar a la Visión (REQ)
    socket_vision_update = context.socket(zmq.REQ)
    socket_vision_update.connect("tcp://localhost:5557")

    print("[UR3e] Esperando órdenes...")
    
    while True:
        cmd = json.loads(socket_motor.recv_string())
        
        if cmd["action"] == "MOVE":
            grab = cmd.get("grab_pose", {"x": 0.0, "y": 0.0, "theta": 0.0})
            place = cmd.get("place_pose", {"x": 0.0, "y": 0.0, "theta": 0.0})
            print(f"[UR3e] 1. RECOGER : Moviendo TCP a X:{grab['x']:.2f}, Y:{grab['y']:.2f} (Ficha {cmd['tile']})")
            print(f"[UR3e] 2. SOLTAR  : Moviendo TCP a X:{place['x']:.2f}, Y:{place['y']:.2f} en lado {cmd['side']}")
            time.sleep(2) # Tiempo de trayectoria física
            # Avisamos a la visión para que "vea" el cambio
            socket_vision_update.send_string(json.dumps(cmd))
            socket_vision_update.recv_string() # Esperamos confirmación de visión

        elif cmd["action"] == "STEAL":
            print("[UR3e] Robando ficha del pozo...")
            time.sleep(3)
            # Avisamos a la visión para que "vea" la nueva ficha en la mano
            socket_vision_update.send_string(json.dumps({"action": "STEAL"}))
            socket_vision_update.recv_string()

        # Respondemos al motor que el brazo ha terminado
        socket_motor.send_string(json.dumps({"status": "done"}))

if __name__ == "__main__":
    run_control()