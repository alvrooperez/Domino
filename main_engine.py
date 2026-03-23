from collections import deque
import random
import tkinter as tk
import zmq
import json

class DominoGame:
    def __init__(self):
        self.game_zone = deque()
        self.player1 = []
        self.player2 = []
        self.dominoes = []
        self.window = None
        self.canvas = None

    def render(self):
        if self.window is None:
            self.window = tk.Tk()
            self.window.title("Domino Render")
            self.canvas = tk.Canvas(self.window, width=800, height=400, bg="#2d5a27")
            self.canvas.pack()
            tk.Button(self.window, text="Stop & Close", command=self.window.destroy).pack()

        self.canvas.delete("all")

        x_mesa = 50
        for t in self.game_zone:
            self._draw_tile(x_mesa, 150, t, "white")
            x_mesa += 50

        x_p1 = 50
        self.canvas.create_text(50, 280, text="PLAYER 1:", fill="white", anchor="w")
        for t in self.player1:
            if t is not None:
                self._draw_tile(x_p1, 300, t, "#eee")
            else:
                self.canvas.create_rectangle(x_p1, 300, x_p1+40, 360, outline="#3d7a37")
            x_p1 += 45
        
        self.window.update()

    def _draw_tile(self, x, y, t, color):
        self.canvas.create_rectangle(x, y, x+40, y+60, fill=color, outline="black")
        self.canvas.create_text(x+20, y+15, text=str(t[0]), font=("Arial", 10, "bold"))
        self.canvas.create_line(x+5, y+30, x+35, y+30)
        self.canvas.create_text(x+20, y+45, text=str(t[1]), font=("Arial", 10, "bold"))

    def check_possibilities(self):
        l_val = self.game_zone[0][0]
        r_val = self.game_zone[-1][1]
        options = []
        for i, t in enumerate(self.player1):
            if t is not None:
                if t[0] == l_val or t[1] == l_val:
                    options.append((i, 'L'))
                if t[0] == r_val or t[1] == r_val:
                    options.append((i, 'R'))
        return options

    def steal(self):
        if self.dominoes:
            stolen_domino = self.dominoes.pop()
            self.player1.append(stolen_domino)
            print(f" -> Stole tile: {stolen_domino}")
            return ("STEAL", stolen_domino)
        else:
            print(" -> Boneyard empty.")
            return ("PASS", None)

    def put_dominoe(self, action):
        idx, side = action[0], action[1]
        t = self.player1[idx]
        ficha_original = t # Guardamos la ficha para el log
        if side == 'L':
            l_val = self.game_zone[0][0]
            if t[1] != l_val: t = (t[1], t[0])
            self.game_zone.appendleft(t) 
        elif side == 'R':
            r_val = self.game_zone[-1][1]
            if t[0] != r_val: t = (t[1], t[0])
            self.game_zone.append(t)
        self.player1[idx] = None
        return ("MOVE", ficha_original, side) # Devolvemos lo que hicimos

    def choose_action(self, options):
        if not options:
            return self.steal()
        return self.put_dominoe(options[0])

    def turn(self):
        options = self.check_possibilities()
        return self.choose_action(options) # Retornamos la acción para enviarla al brazo

if __name__ == "__main__":
    # --- CONFIGURACIÓN ZMQ ---
    context = zmq.Context()
    
    print("[MOTOR] Conectando con Visión...")
    vision_socket = context.socket(zmq.REQ)
    vision_socket.connect("tcp://localhost:5555")
    
    print("[MOTOR] Conectando con UR3e Control...")
    control_socket = context.socket(zmq.REQ)
    control_socket.connect("tcp://localhost:5556")
    # -------------------------

    juego = DominoGame()
    all_dominoes = [(i, j) for i in range(7) for j in range(i, 7)]
    random.shuffle(all_dominoes)
    juego.dominoes = all_dominoes
    
    juego.game_zone.append(juego.dominoes.pop())
    for _ in range(7):
        juego.player1.append(juego.dominoes.pop())
    
    while any(tile is not None for tile in juego.player1):
        juego.render() 
        
        # 1. PIDE DATOS A LA VISIÓN
        print("\n[MOTOR] Pidiendo datos a la visión...")
        vision_socket.send_string("SCAN_TABLE")
        vision_response = json.loads(vision_socket.recv_string())
        print(f"[MOTOR] Visión responde: {vision_response['message']}")
        
        # 2. CALCULA LA JUGADA (El Cerebro)
        accion = juego.turn()
        
        # 3. ENVÍA LA ORDEN AL BRAZO
        if accion and accion[0] == "MOVE":
            _, ficha, lado = accion
            comando = {
                "action": "MOVE",
                "tile": ficha,
                "side": lado
            }
            print(f"[MOTOR] Ordenando al brazo mover la ficha {ficha}...")
            control_socket.send_string(json.dumps(comando))
            
            # El motor se congela aquí hasta que el brazo termine físicamente
            control_response = json.loads(control_socket.recv_string())
            if control_response["status"] == "success":
                print("[MOTOR] Brazo confirma que ha terminado. Siguiente turno.")
        
        if not juego.check_possibilities() and not juego.dominoes:
            print("Game blocked!")
            break

    juego.render() 
    print("--- GAME OVER ---")
    juego.window.mainloop()