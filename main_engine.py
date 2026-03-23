import tkinter as tk
from tkinter import messagebox
from collections import deque
import zmq
import json

class DominoControlPanel:
    def __init__(self, vision_url, control_url):
        # --- Conexiones ZMQ ---
        context = zmq.Context()
        self.vision_sock = context.socket(zmq.REQ)
        self.vision_sock.connect(vision_url)
        self.control_sock = context.socket(zmq.REQ)
        self.control_sock.connect(control_url)

        # --- Estado del Juego ---
        self.board = deque()
        self.hand = []
        self.robot_hand_poses = {}
        self.board_poses = {}
        self.boneyard_poses = {}
        self.turn = "ROBOT" # Puede ser "ROBOT" o "HUMANO"
        self.human_hand_count = 0
        self.is_running = False

        # --- Interfaz Tkinter ---
        self.root = tk.Tk()
        self.root.title("UR3e Domino Controller")
        self.root.geometry("1200x800")
        self.root.configure(bg="#1e1e1e")

        self._setup_ui()
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)
        # Escaneo inicial para no ver la pantalla vacía
        self.update_from_vision() 

    def _setup_ui(self):
        # Indicador de Turno Superior
        self.turn_var = tk.StringVar()
        self.turn_var.set("🤖 TURNO: ROBOT")
        self.lbl_turn = tk.Label(self.root, textvariable=self.turn_var, bg="#1e1e1e", fg="#00ff00", font=("Arial", 18, "bold"))
        self.lbl_turn.pack(pady=10)

        # Canvas principal
        self.canvas = tk.Canvas(self.root, width=1150, height=600, bg="#2d5a27", highlightthickness=0)
        self.canvas.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        self.canvas.bind("<Configure>", lambda e: self.render())

        # Panel de Botones
        btn_frame = tk.Frame(self.root, bg="#1e1e1e")
        btn_frame.pack(side=tk.BOTTOM, fill="x", padx=20, pady=20)

        tk.Button(btn_frame, text="🔍 ESCANEAR MESA", command=self.update_from_vision, 
                  bg="#4a4a4a", fg="white", font=("Arial", 10, "bold"), width=16).pack(side="left", padx=5)
        
        self.btn_human = tk.Button(btn_frame, text="🙋‍♂️ CONFIRMAR JUGADA", command=self.human_played, 
                  bg="#007bff", fg="white", font=("Arial", 10, "bold"), width=22, state=tk.DISABLED)
        self.btn_human.pack(side="left", padx=10)
        
        self.btn_play = tk.Button(btn_frame, text="▶️ INICIAR AUTOMÁTICO", command=self.toggle_autoplay, 
                  bg="#28a745", fg="white", font=("Arial", 11, "bold"), width=22)
        self.btn_play.pack(side="left", padx=10)

        tk.Button(btn_frame, text="🛑 PARAR", command=self.emergency_stop, 
                  bg="#dc3545", fg="white", font=("Arial", 10, "bold"), width=10).pack(side="right", padx=5)

    def _draw_tile(self, px, py, t, color="#eee", theta=0.0):
        # px, py representan el centro geométrico de la ficha en la pantalla
        if abs(theta) == 90 or abs(theta) == 270:
            # Orientación HORIZONTAL
            x1, y1 = px - 30, py - 20
            x2, y2 = px + 30, py + 20
            self.canvas.create_rectangle(x1, y1, x2, y2, fill=color, outline="black", width=2)
            self.canvas.create_text(px - 15, py, text=str(t[0]), font=("Arial", 12, "bold"), fill="black")
            self.canvas.create_line(px, py - 20, px, py + 20, fill="black")
            self.canvas.create_text(px + 15, py, text=str(t[1]), font=("Arial", 12, "bold"), fill="black")
        else:
            # Orientación VERTICAL
            x1, y1 = px - 20, py - 30
            x2, y2 = px + 20, py + 30
            self.canvas.create_rectangle(x1, y1, x2, y2, fill=color, outline="black", width=2)
            self.canvas.create_text(px, py - 15, text=str(t[0]), font=("Arial", 12, "bold"), fill="black")
            self.canvas.create_line(px - 20, py, px + 20, py, fill="black")
            self.canvas.create_text(px, py + 15, text=str(t[1]), font=("Arial", 12, "bold"), fill="black")

    def render(self):
        self.canvas.delete("all")
        
        self.canvas.create_text(20, 20, text="MESA DE TRABAJO (Vista Superior):", fill="white", anchor="w", font=("Arial", 10, "bold"))
        
        # Obtenemos el tamaño real actual del canvas en la pantalla
        c_w = self.canvas.winfo_width()
        c_h = self.canvas.winfo_height()
        if c_w < 100: c_w = 1150 # Prevención antes de que la ventana cargue
        if c_h < 100: c_h = 600

        # Función para mapear metros físicos a píxeles del Canvas
        def map_coords(x_meters, y_meters):
            return 50 + (x_meters * (c_w - 100)), 50 + (y_meters * (c_h - 100))

        for t in self.board:
            t_str = f"{t[0]}_{t[1]}"
            if t_str not in self.board_poses: t_str = f"{t[1]}_{t[0]}"
            pose = self.board_poses.get(t_str, {"x": 0.5, "y": 0.3, "theta": 90.0})
            px, py = map_coords(pose["x"], pose["y"])
            self._draw_tile(px, py, t, "white", pose["theta"])

        for t in self.hand:
            t_str = f"{t[0]}_{t[1]}"
            if t_str not in self.robot_hand_poses: t_str = f"{t[1]}_{t[0]}"
            pose = self.robot_hand_poses.get(t_str, {"x": 0.1, "y": 0.8, "theta": 0.0})
            px, py = map_coords(pose["x"], pose["y"])
            self._draw_tile(px, py, t, "#cfcfcf", pose["theta"])
        
        self.canvas.create_text(20, c_h - 30, text=f"FICHAS JUGADOR 2: {self.human_hand_count}", fill="yellow", anchor="w", font=("Arial", 10, "bold"))
        
        self.root.update_idletasks() # Forzar dibujado antes de seguir

    def update_from_vision(self):
        self.vision_sock.send_string("GET_STATE")
        data = json.loads(self.vision_sock.recv_string())
        self.board = deque(data["board"])
        self.hand = data["robot_hand"]
        self.robot_hand_poses = data.get("robot_hand_poses", {})
        self.board_poses = data.get("board_poses", {})
        self.boneyard_poses = data.get("boneyard_poses", {})
        self.human_hand_count = data.get("human_hand_count", 0)
        self.render()
        return data["boneyard_empty"]

    def check_win(self):
        if len(self.hand) == 0:
            self.emergency_stop()
            messagebox.showinfo("🏆 FIN DEL JUEGO", "¡El ROBOT ha ganado! Se ha quedado sin fichas.")
            return True
        elif self.human_hand_count == 0:
            self.emergency_stop()
            messagebox.showinfo("🏆 FIN DEL JUEGO", "¡El JUGADOR 2 ha ganado! Se ha quedado sin fichas.")
            return True
        return False

    def human_played(self):
        if self.turn != "HUMANO": return
        
        # Simulamos que la cámara lee el nuevo tablero con la jugada del humano.
        # En el proyecto real, aquí solo llamarías a update_from_vision().
        self.vision_sock.send_string("SIMULATE_HUMAN_MOVE")
        self.vision_sock.recv_string() # Esperamos confirmación

        # Pasamos turno al robot
        self.turn = "ROBOT"
        self.turn_var.set("🤖 TURNO: ROBOT")
        self.lbl_turn.config(fg="#00ff00")
        self.btn_human.config(state=tk.DISABLED)
        
        self.update_from_vision()
        if self.check_win(): return

        if self.is_running:
            self.root.after(500, self.game_loop)

    def toggle_autoplay(self):
        self.is_running = not self.is_running
        if self.is_running:
            self.btn_play.config(text="⏸️ PAUSAR", bg="#ffc107", fg="black")
            if self.turn == "ROBOT":
                self.root.after(100, self.game_loop)
        else:
            self.btn_play.config(text="▶️ CONTINUAR", bg="#28a745", fg="white")

    def game_loop(self):
        if not self.is_running: return
        if self.turn == "HUMANO": return # Detiene el bucle hasta que el humano pulse el botón

        # 1. Escanear y actualizar UI
        boneyard_empty = self.update_from_vision()
        
        if self.check_win(): return

        # 2. Lógica
        move = self.calculate_logic()
        
        if move:
            # Adjuntamos la posición física simulada de la ficha para que el brazo sepa a dónde ir
            t_key = f"{move['tile'][0]}_{move['tile'][1]}"
            if t_key not in self.robot_hand_poses: t_key = f"{move['tile'][1]}_{move['tile'][0]}"
            move["grab_pose"] = self.robot_hand_poses.get(t_key, {"x": 0, "y": 0, "theta": 0})
            
            print(f"[UI] Decisión: Mover {move['tile']} al lado {move['side']}.")
            self.control_sock.send_string(json.dumps(move))
            self.control_sock.recv_string() # Esperar a que el UR3e termine (congelará UI 2seg)
        elif not boneyard_empty:
            # Coordenada origen: Cualquier ficha disponible en el pozo
            grab = list(self.boneyard_poses.values())[-1] if self.boneyard_poses else {"x": 0.8, "y": 0.1, "theta": 0.0}
            
            # Coordenada destino: Buscamos el primer hueco libre en la mano del robot
            occupied_x = [p["x"] for p in self.robot_hand_poses.values()]
            target_x = 0.2
            for i in range(20): # Límite máximo de 20 fichas en mano
                candidate_x = 0.2 + (i * 0.08)
                # Si ningún valor X ocupado está cerca (margen de 2cm), hemos encontrado el hueco
                if not any(abs(ox - candidate_x) < 0.02 for ox in occupied_x):
                    target_x = candidate_x
                    break
            
            place = {"x": target_x, "y": 0.8, "theta": 0.0}
            
            print(f"[UI] Decisión: Robar. Ir a X:{grab['x']:.2f}, dejar en X:{place['x']:.2f}")
            self.control_sock.send_string(json.dumps({
                "action": "STEAL",
                "grab_pose": grab,
                "place_pose": place
            }))
            self.control_sock.recv_string() # Esperar (congelará UI 3seg)
        else:
            print("[UI] Bloqueado. Fin.")
            self.toggle_autoplay() # Parar bucle
            return

        # Actualizar UI inmediatamente después del movimiento del brazo
        self.update_from_vision()
        
        # --- PASAR TURNO AL HUMANO ---
        self.turn = "HUMANO"
        self.turn_var.set("🙋‍♂️ TURNO: JUGADOR 2")
        self.lbl_turn.config(fg="#007bff") # Azul para el humano
        self.btn_human.config(state=tk.NORMAL) # Habilitamos el botón
        # Ya no llamamos a self.root.after(). El bucle se reanuda en human_played()

    def calculate_logic(self):
        if not self.board: return None
        l_v, r_v = self.board[0][0], self.board[-1][1]
        
        # Extraemos las coordenadas de las fichas en los extremos del tablero
        l_tile = f"{self.board[0][0]}_{self.board[0][1]}"
        r_tile = f"{self.board[-1][0]}_{self.board[-1][1]}"
        l_pose = self.board_poses.get(l_tile, {"x": 0.5, "y": 0.3, "theta": 90.0})
        r_pose = self.board_poses.get(r_tile, {"x": 0.5, "y": 0.3, "theta": 90.0})
        
        for i, t in enumerate(self.hand):
            if t[0] == l_v or t[1] == l_v: 
                # Calculamos destino basándonos en el extremo izquierdo (-6 cm en X)
                place = {"x": l_pose["x"] - 0.06, "y": l_pose["y"], "theta": 90.0}
                return {"action": "MOVE", "tile": t, "side": "L", "place_pose": place}
            if t[0] == r_v or t[1] == r_v: 
                # Calculamos destino basándonos en el extremo derecho (+6 cm en X)
                place = {"x": r_pose["x"] + 0.06, "y": r_pose["y"], "theta": 90.0}
                return {"action": "MOVE", "tile": t, "side": "R", "place_pose": place}
        return None

    def emergency_stop(self):
        self.is_running = False
        messagebox.showwarning("STOP", "Lógica del motor detenida.")

    def on_closing(self):
        print("[UI] Cerrando motor y conexiones ZMQ...")
        self.is_running = False
        self.vision_sock.close()
        self.control_sock.close()
        self.root.destroy()

    def run(self):
        self.root.mainloop()

if __name__ == "__main__":
    app = DominoControlPanel("tcp://localhost:5555", "tcp://localhost:5556")
    app.run()