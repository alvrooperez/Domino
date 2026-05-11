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
        self.boneyard_empty = False

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
            # Orientación HORIZONTAL (Reducida a 30x20 aprox)
            x1, y1 = px - 20, py - 12
            x2, y2 = px + 20, py + 12
            self.canvas.create_rectangle(x1, y1, x2, y2, fill=color, outline="black", width=1)
            self.canvas.create_text(px - 10, py, text=str(t[0]), font=("Arial", 8, "bold"), fill="black")
            self.canvas.create_line(px, py - 12, px, py + 12, fill="black")
            self.canvas.create_text(px + 10, py, text=str(t[1]), font=("Arial", 8, "bold"), fill="black")
        else:
            # Orientación VERTICAL (Reducida a 20x30 aprox)
            x1, y1 = px - 12, py - 20
            x2, y2 = px + 12, py + 20
            self.canvas.create_rectangle(x1, y1, x2, y2, fill=color, outline="black", width=1)
            self.canvas.create_text(px, py - 10, text=str(t[0]), font=("Arial", 8, "bold"), fill="black")
            self.canvas.create_line(px - 12, py, px + 12, py, fill="black")
            self.canvas.create_text(px, py + 10, text=str(t[1]), font=("Arial", 8, "bold"), fill="black")

    def render(self):
        self.canvas.delete("all")
        
        self.canvas.create_text(20, 20, text="MESA DE TRABAJO (Vista Superior):", fill="white", anchor="w", font=("Arial", 10, "bold"))
        
        c_w = self.canvas.winfo_width()
        c_h = self.canvas.winfo_height()
        if c_w < 100: c_w = 1150
        if c_h < 100: c_h = 600

        # Mapeo ajustado para el rango real del robot (Aprox X: -0.6 a 0.2, Y: 0.2 a 0.7)
        def map_coords(x_meters, y_meters):
            # Centramos X=-0.2 en el medio del canvas (c_w/2)
            # 1 metro = 800 píxeles aprox
            px = (c_w / 2) + (x_meters + 0.2) * 800
            # Centramos Y=0.45 en el medio del canvas (c_h/2)
            py = (c_h / 2) - (y_meters - 0.45) * 800
            return px, py

        # Dibujar Tablero (Fichas en juego)
        for t in self.board:
            t_str = f"{t[0]}_{t[1]}"
            if t_str not in self.board_poses: t_str = f"{t[1]}_{t[0]}"
            pose = self.board_poses.get(t_str, {"x": 0.0, "y": 0.45, "theta": 90.0})
            px, py = map_coords(pose["x"], pose["y"])
            self._draw_tile(px, py, t, "white", pose["theta"])

        # Dibujar Mano Robot
        for t in self.hand:
            t_key = f"{t[0]}_{t[1]}"
            if t_key not in self.robot_hand_poses: t_key = f"{t[1]}_{t[0]}"
            pose = self.robot_hand_poses.get(t_key, {"x": -0.4, "y": 0.45, "theta": 0.0})
            px, py = map_coords(pose["x"], pose["y"])
            self._draw_tile(px, py, t, "#cfcfcf", pose.get("theta", 0.0))

        # Dibujar Pozo (Reversos)
        for clave, pose in self.boneyard_poses.items():
            px, py = map_coords(pose["x"], pose["y"])
            self.canvas.create_rectangle(px-20, py-30, px+20, py+30, fill="#2c3e50", outline="white")
            self.canvas.create_text(px, py, text="?", fill="white", font=("Arial", 12, "bold"))
        
        self.canvas.create_text(20, c_h - 30, text=f"FICHAS JUGADOR 2: {self.human_hand_count}", fill="yellow", anchor="w", font=("Arial", 10, "bold"))
        
        self.root.update_idletasks()

    def scan_zone(self, zone):
        """Mueve el robot a la zona y actualiza el estado desde la visión."""
        try:
            # 1. Mover el robot a la posición de observación
            pos = "tablero" if zone == "BOARD" else "tablero_robo"
            print(f"[MOTOR] Moviendo robot a {pos} para escanear {zone}...")
            self.control_sock.send_string(json.dumps({"action": "MOVE_TO_POSITION", "position": pos}))
            self.control_sock.recv_string()

            # 2. Pedir estado a la visión
            print(f"[MOTOR] Pidiendo estado de zona {zone}...")
            self.vision_sock.send_string(f"GET_STATE:{zone}")
            data = json.loads(self.vision_sock.recv_string())
            
            if "error" in data:
                print(f"[MOTOR] Error de visión en {zone}: {data['error']}")
                return False

            # 3. Actualizar estado interno
            if zone == "BOARD":
                self.board = deque(data.get("board", []))
                self.hand = data.get("robot_hand", [])
                self.robot_hand_poses = data.get("robot_hand_poses", {})
                self.board_poses = data.get("board_poses", {})
                self.human_hand_count = data.get("human_hand_count", 0)
            else: # BONEYARD
                self.boneyard_poses = data.get("boneyard_poses", {})
                self.boneyard_empty = data.get("boneyard_empty", False)
            
            self.render()
            return self.boneyard_empty
        except Exception as e:
            print(f"[MOTOR] Error escaneando {zone}: {e}")
            return True

    def update_from_vision(self):
        return self.scan_zone("BOARD")

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
        if self.turn == "HUMANO": return 

        # 1. Escanear y actualizar UI
        boneyard_empty = self.update_from_vision()
        
        if self.check_win(): return

        # --- LÓGICA DE INICIO: Robar hasta tener fichas (ej. 2 para test) ---
        if len(self.hand) < 2 and not boneyard_empty:
            print(f"[MOTOR] Robando ficha inicial ({len(self.hand)+1}/2)...")
            
            # Escanear el pozo para encontrar fichas
            self.scan_zone("BONEYARD")
            
            # Coordenada origen: Cualquier ficha disponible en el pozo
            grab = list(self.boneyard_poses.values())[-1] if self.boneyard_poses else None
            if grab:
                next_slot = len(self.hand)
                self.control_sock.send_string(json.dumps({
                    "action": "STEAL",
                    "grab_pose": grab,
                    "slot_mano": next_slot
                }))
                self.control_sock.recv_string()
                self.update_from_vision()
                self.root.after(500, self.game_loop) # Continuar robando
                return
        # ---------------------------------------------------------

        # 2. Lógica de juego normal
        move = self.calculate_logic()
        
        if move:
            # Adjuntamos la posición física simulada de la ficha para que el brazo sepa a dónde ir
            t_key = f"{move['tile'][0]}_{move['tile'][1]}"
            if t_key not in self.robot_hand_poses: t_key = f"{move['tile'][1]}_{move['tile'][0]}"
            
            print(f"[UI] Decisión: Mover {move['tile']} al lado {move['side']}.")
            self.control_sock.send_string(json.dumps(move))
            self.control_sock.recv_string() # Esperar a que el UR3e termine
        elif not boneyard_empty:
            # Escanear el pozo para encontrar fichas
            self.scan_zone("BONEYARD")
            
            # Coordenada origen: Cualquier ficha disponible en el pozo
            grab = list(self.boneyard_poses.values())[-1] if self.boneyard_poses else None
            if grab:
                next_slot = len(self.hand)
                print(f"[UI] Decisión: Robar ficha a slot {next_slot}")
                self.control_sock.send_string(json.dumps({
                    "action": "STEAL",
                    "grab_pose": grab,
                    "slot_mano": next_slot
                }))
                self.control_sock.recv_string()
                self.update_from_vision()
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

    def calculate_logic(self):
        """
        Lógica mejorada: decide qué ficha jugar, en qué lado y con qué orientación.
        Si no hay fichas posibles, retorna None (para robar).
        """
        if not self.board: 
            print("[LÓGICA] Tablero vacío. Robot empieza con su primera ficha.")
            t = self.hand[0]
            # Usar slot_index real si está disponible
            t_key = f"{t[0]}_{t[1]}"
            if t_key not in self.robot_hand_poses: t_key = f"{t[1]}_{t[0]}"
            slot_real = self.robot_hand_poses.get(t_key, {}).get("slot_index", 0)
            
            # Orientación corregida: Normal = 0.0, Doble = 90.0
            target_theta = 90.0 if t[0] == t[1] else 0.0
            
            return {
                "action": "MOVE", "tile": t, "side": "L",
                "place_pose": {"x": 0.0, "y": 0.45, "theta": target_theta},
                "slot_mano": slot_real, "slot_tablero": 0
            }

        l_v, r_v = self.board[0][0], self.board[-1][1]
        print(f"[LÓGICA] Tablero: {l_v} <---> {r_v}. Mano: {self.hand}")

        # Buscar en la mano
        for i, t in enumerate(self.hand):
            t_key = f"{t[0]}_{t[1]}"
            if t_key not in self.robot_hand_poses: t_key = f"{t[1]}_{t[0]}"
            slot_real = self.robot_hand_poses.get(t_key, {}).get("slot_index", i)

            # --- OPCIÓN 1: LADO IZQUIERDO ---
            if t[0] == l_v or t[1] == l_v:
                l_tile_data = self.board[0]
                l_key = f"{l_tile_data[0]}_{l_tile_data[1]}"
                if l_key not in self.board_poses: l_key = f"{l_tile_data[1]}_{l_tile_data[0]}"
                l_pose = self.board_poses.get(l_key, {"x": 0.0, "y": 0.45, "theta": 0.0})
                
                # Orientación: Doble = 90. Normal = 0 o 180.
                if t[0] == t[1]:
                    target_theta = 90.0
                else:
                    # Si t[1] == l_v, la ficha está bien orientada (val1 a la izq, val2 a la derecha conectando con l_v)
                    # Si t[0] == l_v, hay que girarla 180.
                    target_theta = 180.0 if t[0] == l_v else 0.0
                
                print(f"[LÓGICA] Juego {t} en LADO IZQUIERDO. Conecta {l_v}. Theta={target_theta}")
                return {
                    "action": "MOVE", "tile": t, "side": "L",
                    "place_pose": {"x": l_pose["x"] - 0.06, "y": l_pose["y"], "theta": target_theta},
                    "slot_mano": slot_real, "slot_tablero": 0
                }

            # --- OPCIÓN 2: LADO DERECHO ---
            if t[0] == r_v or t[1] == r_v:
                r_tile_data = self.board[-1]
                r_key = f"{r_tile_data[0]}_{r_tile_data[1]}"
                if r_key not in self.board_poses: r_key = f"{r_tile_data[1]}_{r_tile_data[0]}"
                r_pose = self.board_poses.get(r_key, {"x": 0.0, "y": 0.45, "theta": 0.0})
                
                # Orientación: Doble = 90. Normal = 0 o 180.
                if t[0] == t[1]:
                    target_theta = 90.0
                else:
                    # Si t[0] == r_v, la ficha conecta t[0] con r_v, val2 queda a la derecha.
                    # Si t[1] == r_v, hay que girarla 180.
                    target_theta = 180.0 if t[1] == r_v else 0.0
                
                print(f"[LÓGICA] Juego {t} en LADO DERECHO. Conecta {r_v}. Theta={target_theta}")
                return {
                    "action": "MOVE", "tile": t, "side": "R",
                    "place_pose": {"x": r_pose["x"] + 0.06, "y": r_pose["y"], "theta": target_theta},
                    "slot_mano": slot_real, "slot_tablero": len(self.board)
                }

        print("[LÓGICA] No hay jugadas posibles en la mano.")
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
