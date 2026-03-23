import zmq
import json
import random

def run_vision():
    context = zmq.Context()
    
    # Socket para responder al Motor (GET_STATE)
    socket_motor = context.socket(zmq.REP)
    socket_motor.bind("tcp://*:5555")

    # Socket para escuchar confirmaciones del Control (ACTION_DONE)
    socket_control = context.socket(zmq.REP)
    socket_control.bind("tcp://*:5557") # Un puerto nuevo

    # --- ESTADO INICIAL FALSO ---
    print("[VISIÓN] Creando mazo de dominó...")
    all_dominoes = [(i, j) for i in range(7) for j in range(i, 7)]
    random.shuffle(all_dominoes)
    
    # Sacamos una inicial para la mesa y 7 para el robot
    board = [all_dominoes.pop()]
    robot_hand = [all_dominoes.pop() for _ in range(7)]
    human_hand = [all_dominoes.pop() for _ in range(7)]
    
    # Asignamos posiciones físicas simuladas (X, Y, Theta) a las fichas del robot
    robot_hand_poses = {}
    for idx, t in enumerate(robot_hand):
        robot_hand_poses[f"{t[0]}_{t[1]}"] = {"x": 0.2 + (idx * 0.08), "y": 0.8, "theta": 0.0}

    # Asignamos una posición inicial a la primera ficha del tablero (Centro de la mesa)
    board_poses = {f"{board[0][0]}_{board[0][1]}": {"x": 0.5, "y": 0.3, "theta": 90.0}}

    # Asignamos posiciones a las fichas del pozo (boneyard) apiladas en una esquina
    boneyard_poses = {}
    for idx, t in enumerate(all_dominoes):
        boneyard_poses[f"{t[0]}_{t[1]}"] = {"x": 0.8 + ((idx % 3) * 0.05), "y": 0.1 + ((idx // 3) * 0.05), "theta": 0.0}

    print(f"[VISIÓN] Juego listo. Mesa: {board[0]}, Robot: 7, Humano: 7. Pozo: {len(all_dominoes)}.")

    poller = zmq.Poller()
    poller.register(socket_motor, zmq.POLLIN)
    poller.register(socket_control, zmq.POLLIN)
    
    while True:
        socks = dict(poller.poll())

        # 1. EL MOTOR PIDE EL ESTADO (Para dibujar la UI)
        if socket_motor in socks and socks[socket_motor] == zmq.POLLIN:
            message = socket_motor.recv_string()
            if message == "GET_STATE":
                state = {
                    "board": board,
                    "robot_hand": robot_hand,
                    "robot_hand_poses": robot_hand_poses,
                    "board_poses": board_poses,
                    "boneyard_poses": boneyard_poses,
                    "human_hand_count": len(human_hand),
                    "boneyard_empty": len(all_dominoes) == 0
                }
                socket_motor.send_string(json.dumps(state))
                
            elif message == "SIMULATE_HUMAN_MOVE":
                # --- SIMULACIÓN DEL MOVIMIENTO HUMANO ---
                played = False
                if board:
                    # Buscamos los extremos actuales en coordenadas físicas
                    min_x = min(p["x"] for p in board_poses.values()) if board_poses else 0.5
                    max_x = max(p["x"] for p in board_poses.values()) if board_poses else 0.5
                    
                    l_val, r_val = board[0][0], board[-1][1]
                    for t in human_hand:
                        if t[0] == l_val or t[1] == l_val:
                            human_hand.remove(t)
                            tile = t if t[1] == l_val else (t[1], t[0])
                            board.insert(0, tile)
                            # Posición simulada de la jugada humana (desplazada 6 cm en el tapete)
                            board_poses[f"{tile[0]}_{tile[1]}"] = {"x": min_x - 0.06, "y": 0.3, "theta": 90.0}
                            played = True
                            break
                        elif t[0] == r_val or t[1] == r_val:
                            human_hand.remove(t)
                            tile = t if t[0] == r_val else (t[1], t[0])
                            board.append(tile)
                            # Posición simulada de la jugada humana (desplazada 6 cm en el tapete)
                            board_poses[f"{tile[0]}_{tile[1]}"] = {"x": max_x + 0.06, "y": 0.3, "theta": 90.0}
                            played = True
                            break
                if not played and all_dominoes:
                    nueva = all_dominoes.pop()
                    human_hand.append(nueva)
                
                socket_motor.send_string(json.dumps({"status": "done"}))

        # 2. EL CONTROL AVISA QUE HA TERMINADO UNA ACCIÓN FÍSICA
        if socket_control in socks and socks[socket_control] == zmq.POLLIN:
            data = json.loads(socket_control.recv_string())
            accion = data["action"]
            
            if accion == "MOVE":
                tile = tuple(data["tile"]) # ZMQ envía listas, convertimos a tupla
                side = data["side"]
                # 1. Quitar de la mano
                robot_hand.remove(tile)
                # 2. Poner en la mesa (ajustando orientación)
                if side == "L":
                    l_val = board[0][0]
                    if tile[1] != l_val: tile = (tile[1], tile[0])
                    board.insert(0, tile)
                else:
                    r_val = board[-1][1]
                    if tile[0] != r_val: tile = (tile[1], tile[0])
                    board.append(tile)
                
                # Guardamos la posición destino donde el robot depositó la ficha
                board_poses[f"{tile[0]}_{tile[1]}"] = data.get("place_pose", {"x": 0.5, "y": 0.3, "theta": 90.0})

                # Eliminamos la pose de la ficha jugada de la mesa de trabajo
                pose_key = f"{tile[0]}_{tile[1]}"
                if pose_key in robot_hand_poses: del robot_hand_poses[pose_key]
                elif f"{tile[1]}_{tile[0]}" in robot_hand_poses: del robot_hand_poses[f"{tile[1]}_{tile[0]}"]
                print(f"[VISIÓN] Actualizado: Ficha {tile} jugada.")

            elif accion == "STEAL":
                if all_dominoes:
                    nueva = all_dominoes.pop()
                    robot_hand.append(nueva)
                    # Guardamos la ficha en la posición destino que nos indica el Motor
                    robot_hand_poses[f"{nueva[0]}_{nueva[1]}"] = data.get("place_pose", {"x": 0.1, "y": 0.8, "theta": 0.0})
                    pose_key = f"{nueva[0]}_{nueva[1]}"
                    if pose_key in boneyard_poses: del boneyard_poses[pose_key]
                    elif f"{nueva[1]}_{nueva[0]}" in boneyard_poses: del boneyard_poses[f"{nueva[1]}_{nueva[0]}"]
                    print(f"[VISIÓN] Actualizado: Robot roba ficha {nueva}.")
                else:
                    print("[VISIÓN] Alerta: Intentaron robar pero el pozo está vacío.")

            socket_control.send_string(json.dumps({"status": "updated"}))

if __name__ == "__main__":
    run_vision()