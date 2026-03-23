import zmq
import json
import time

def run_control():
    context = zmq.Context()
    socket = context.socket(zmq.REP)
    socket.bind("tcp://*:5556") # Escucha en el puerto 5556

    print("[CONTROL] Músculo (UR3e) conectado. Esperando comandos...")
    
    while True:
        # Recibe la orden del motor
        message = socket.recv_string()
        command = json.loads(message)
        
        if command["action"] == "MOVE":
            ficha = command["tile"]
            lado = command["side"]
            
            print(f"\n[CONTROL] >>> UR3e MOVILIZÁNDOSE <<<")
            print(f"[CONTROL] Agarrando ficha {ficha} y colocándola en el lado {lado}...")
            
            # Simulamos lo que tarda el brazo físico en hacer la trayectoria
            time.sleep(3) 
            
            print("[CONTROL] Movimiento completado. Brazo en posición de reposo.")
            
            # Avisa al motor de que ya puede seguir
            socket.send_string(json.dumps({"status": "success"}))

if __name__ == "__main__":
    run_control()