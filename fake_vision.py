import zmq
import json

def run_vision():
    context = zmq.Context()
    socket = context.socket(zmq.REP) # REP = Reply (Servidor)
    socket.bind("tcp://*:5555")      # Escucha en el puerto 5555

    print("[VISIÓN] Ojo activado. Esperando peticiones...")
    
    while True:
        # Espera a que el motor pregunte algo
        message = socket.recv_string()
        
        if message == "SCAN_TABLE":
            print("[VISIÓN] Escaneando mesa...")
            # En el futuro, aquí leerás la cámara. Hoy enviamos un JSON falso.
            fake_state = {
                "status": "ok",
                "message": "Veo la mesa despejada y fichas en su sitio"
            }
            # Responde al motor
            socket.send_string(json.dumps(fake_state))

if __name__ == "__main__":
    run_vision()