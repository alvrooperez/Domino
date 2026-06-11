import tkinter as tk
from tkinter import messagebox
from collections import deque
import zmq
import json
from time import sleep

class DominoControlPanel:
    FICHAS_INICIALES = 3  # modificable para pruebas

    TABLERO_CENTRO_X  = 0.0     # X del centro del tablero en TCP (metros)
    TABLERO_CENTRO_Y  = 0.37   # Y del centro del tablero en TCP (metros)
    SEPARACION_FICHAS = 0.06    # distancia centro a centro entre fichas consecutivas (metros)

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
        self._rendering = False
        self.fichas_en_mano = 0
        self.partida_iniciada = False
        self._center_index = 0  # índice de la ficha central dentro de self.board
        self.slot_map = {}      # {clave_ficha: slot_index} — gestionado por el motor

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
        self.canvas.bind("<Configure>", self._on_configure)

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

        self.btn_comenzar = tk.Button(btn_frame, text="🎮 COMENZAR", command=self.comenzar_partida,
                  bg="#555", fg="#aaa", font=("Arial", 11, "bold"), width=18, state=tk.DISABLED)
        self.btn_comenzar.pack(side="left", padx=10)

        tk.Button(btn_frame, text="🛑 PARAR", command=self.emergency_stop,
                  bg="#dc3545", fg="white", font=("Arial", 10, "bold"), width=10).pack(side="right", padx=5)

    def _on_configure(self, event):
        if not self._rendering:
            self.root.after_idle(self._deferred_render)

    def _deferred_render(self):
        if not self._rendering:
            self.render()

    def render(self):
        if self._rendering:
            return
        self._rendering = True
        try:
            self.canvas.delete("all")
            c_w = self.canvas.winfo_width()
            c_h = self.canvas.winfo_height()
            if c_w < 100: c_w = 1150
            if c_h < 100: c_h = 600

            boneyard_n = len(self.boneyard_poses)
            self.canvas.create_text(c_w - 15, 15, text=f"Boneyard: {boneyard_n} fichas",
                                    fill="white", anchor="ne", font=("Arial", 11, "bold"))
            self.canvas.create_text(c_w - 15, 38, text=f"Mano humano: {self.human_hand_count} fichas",
                                    fill="yellow", anchor="ne", font=("Arial", 11, "bold"))
            self._draw_board_chain(c_w, c_h)
            self._draw_hand_slots(c_w, c_h)
        finally:
            self._rendering = False

    def _draw_board_chain(self, c_w, c_h):
        LABEL_Y = 65
        GAP = 3
        TW_H, TH_H = 80, 40
        TW_V, TH_V = 40, 80
        HAND_AREA_TOP = c_h - 120

        self.canvas.create_text(20, LABEL_Y, text="TABLERO:",
                                fill="white", anchor="w", font=("Arial", 10, "bold"))
        if not self.board:
            self.canvas.create_text(c_w / 2, (LABEL_Y + 20 + HAND_AREA_TOP) / 2, text="Tablero vacío",
                                    fill="#aaa", font=("Arial", 12, "italic"))
            return

        estimated_w = len(self.board) * (TW_H + GAP)
        start_x = max(20, c_w / 2 - estimated_w / 2)
        start_y = (LABEL_Y + 20 + HAND_AREA_TOP) / 2 - TH_H / 2
        x, y, row_h = start_x, start_y, 0
        for t in self.board:
            t_key = f"{t[0]}_{t[1]}"
            if t_key not in self.board_poses:
                t_key = f"{t[1]}_{t[0]}"
            theta = self.board_poses.get(t_key, {}).get("theta", 0.0)
            if t[0] == t[1]:
                horiz = False  # doble: perpendicular a la cadena → estrecho y alto
            else:
                horiz = not (abs(theta) == 90 or abs(theta) == 270)
            tw, th = (TW_H, TH_H) if horiz else (TW_V, TH_V)
            orient = "H" if horiz else "V"

            if x + tw > c_w - 20 and x > start_x:
                y += row_h + 12
                x, row_h = start_x, 0
            if y + th > HAND_AREA_TOP - 10:
                break
            row_h = max(row_h, th)

            cx, cy = x + tw / 2, y + th / 2
            self.canvas.create_rectangle(x, y, x + tw, y + th,
                                          fill="white", outline="black", width=2)
            if horiz:
                self.canvas.create_text(cx - tw / 4, cy, text=str(t[0]),
                                        font=("Arial", 10, "bold"), fill="black")
                self.canvas.create_line(cx, y + 4, cx, y + th - 4, fill="black")
                self.canvas.create_text(cx + tw / 4, cy, text=str(t[1]),
                                        font=("Arial", 10, "bold"), fill="black")
            else:
                self.canvas.create_text(cx, cy - th / 4, text=str(t[0]),
                                        font=("Arial", 10, "bold"), fill="black")
                self.canvas.create_line(x + 4, cy, x + tw - 4, cy, fill="black")
                self.canvas.create_text(cx, cy + th / 4, text=str(t[1]),
                                        font=("Arial", 10, "bold"), fill="black")
            self.canvas.create_text(cx, y + th - 6, text=f"({orient})",
                                    font=("Arial", 7), fill="#666")
            x += tw + GAP

    def _draw_hand_slots(self, c_w, c_h):
        NUM_SLOTS = 7
        SLOT_W = 110
        SLOT_H = 70
        MARGIN = 8
        total_w = NUM_SLOTS * SLOT_W + (NUM_SLOTS - 1) * MARGIN
        sx = max(10, (c_w - total_w) / 2)
        sy = c_h - SLOT_H - 15

        self.canvas.create_text(sx, sy - 16, text="MANO DEL ROBOT:",
                                fill="white", anchor="w", font=("Arial", 10, "bold"))

        slot_map = {}
        unslotted = []
        for t in self.hand:
            t_key = f"{t[0]}_{t[1]}"
            if t_key not in self.slot_map:
                t_key = f"{t[1]}_{t[0]}"
            pose = self.robot_hand_poses.get(t_key, {})
            idx = self.slot_map.get(t_key)
            theta = pose.get("theta", 0.0)
            if idx is not None and 0 <= idx < NUM_SLOTS:
                slot_map[idx] = (t, theta)
            else:
                unslotted.append((t, theta))
        for item in unslotted:
            for i in range(NUM_SLOTS):
                if i not in slot_map:
                    slot_map[i] = item
                    break

        for i in range(NUM_SLOTS):
            x = sx + i * (SLOT_W + MARGIN)
            if i in slot_map:
                t, theta = slot_map[i]
                orient = "H" if (abs(theta) == 90 or abs(theta) == 270) else "V"
                self.canvas.create_rectangle(x, sy, x + SLOT_W, sy + SLOT_H,
                                              fill="#d4e6f1", outline="#2c3e50", width=2)
                self.canvas.create_text(x + SLOT_W / 2, sy + SLOT_H / 2 - 10,
                                        text=f"[{t[0]}|{t[1]}]",
                                        font=("Arial", 13, "bold"), fill="#1a252f")
                self.canvas.create_text(x + SLOT_W / 2, sy + SLOT_H / 2 + 12,
                                        text=f"({orient})",
                                        font=("Arial", 9), fill="#555")
            else:
                self.canvas.create_rectangle(x, sy, x + SLOT_W, sy + SLOT_H,
                                              fill="#444", outline="#777", width=1)
                self.canvas.create_text(x + SLOT_W / 2, sy + SLOT_H / 2,
                                        text=str(i),
                                        font=("Arial", 11), fill="#999")

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
            
            self.root.after(0, self.render)
            return self.boneyard_empty
        except Exception as e:
            print(f"[MOTOR] Error escaneando {zone}: {e}")
            return True

    def update_from_vision(self):
        return self.scan_zone("BOARD")

    def check_win(self):
        if not self.partida_iniciada:
            return False
        if self.fichas_en_mano == 0:
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
        
        old_left = list(self.board[0]) if self.board else None
        old_len  = len(self.board)
        self.update_from_vision()
        if len(self.board) > old_len and old_left is not None:
            if list(self.board[0]) != old_left:
                self._center_index += 1
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
        try:
            if not self.is_running: return
            if self.turn == "HUMANO": return

            # ── FASE DE INICIO: robar FICHAS_INICIALES antes de empezar ──────────
            if not self.partida_iniciada and self.fichas_en_mano == 0:
                self.scan_zone("BONEYARD")
                if self.boneyard_empty:
                    print("[MOTOR] Error: boneyard vacío al inicio. Imposible iniciar.")
                    messagebox.showerror("Error de inicio",
                                         "El boneyard está vacío y el robot no tiene fichas.\n"
                                         "Imposible iniciar la partida.")
                    self.toggle_autoplay()
                    return
                for slot in range(self.FICHAS_INICIALES):
                    self.scan_zone("BONEYARD")
                    grab = list(self.boneyard_poses.values())[-1] if self.boneyard_poses else None
                    if not grab:
                        print(f"[MOTOR] Boneyard agotado tras {self.fichas_en_mano} fichas.")
                        break
                    print(f"[MOTOR] Robando ficha inicial → slot {slot}...")
                    self.control_sock.send_string(json.dumps({
                        "action": "STEAL",
                        "grab_pose": grab,
                        "slot_mano": slot
                    }))
                    self.control_sock.recv_string()
                    self.fichas_en_mano += 1
                self.update_from_vision()
                sorted_poses = sorted(self.robot_hand_poses.items(), key=lambda kv: kv[1]['y'], reverse=True)
                self.slot_map = {clave: idx for idx, (clave, _) in enumerate(sorted_poses)}
                print(f"[MOTOR] slot_map inicial: {self.slot_map}")
                self.is_running = False
                self.btn_play.config(text="▶️ CONTINUAR", bg="#28a745", fg="white")
                self.btn_comenzar.config(state=tk.NORMAL, bg="#17a2b8", fg="white")
                self.turn_var.set(f"✅ {self.fichas_en_mano} fichas recogidas. Pulsa COMENZAR para iniciar.")
                self.lbl_turn.config(fg="#ffc107")
                return
            # ─────────────────────────────────────────────────────────────────────

            # 1. Escanear y actualizar UI
            boneyard_empty = self.update_from_vision()

            if self.check_win(): return

            # 2. Lógica de juego normal
            move = self.calculate_logic()

            if move:
                t_key = f"{move['tile'][0]}_{move['tile'][1]}"
                if t_key not in self.slot_map: t_key = f"{move['tile'][1]}_{move['tile'][0]}"

                print(f"[UI] Decisión: Mover {move['tile']} al lado {move['side']}.")
                self.control_sock.send_string(json.dumps(move))
                self.control_sock.recv_string()
                self.slot_map.pop(t_key, None)
                self.fichas_en_mano -= 1
                if move["side"] == "L" and len(self.board) > 0:
                    self._center_index += 1
            elif not boneyard_empty:
                self.scan_zone("BONEYARD")
                grab = list(self.boneyard_poses.values())[-1] if self.boneyard_poses else None
                if grab:
                    next_slot = next((i for i in range(7) if i not in self.slot_map.values()), len(self.slot_map))
                    print(f"[UI] Decisión: Robar ficha a slot {next_slot}")
                    self.control_sock.send_string(json.dumps({
                        "action": "STEAL",
                        "grab_pose": grab,
                        "slot_mano": next_slot
                    }))
                    self.control_sock.recv_string()
                    self.fichas_en_mano += 1
                    old_keys = set(self.slot_map.keys())
                    self.update_from_vision()
                    for k in self.robot_hand_poses:
                        if k not in old_keys and "_".join(reversed(k.split("_"))) not in old_keys:
                            self.slot_map[k] = next_slot
                            break
                    move = self.calculate_logic()
                    if move:
                        t_key = f"{move['tile'][0]}_{move['tile'][1]}"
                        if t_key not in self.slot_map: t_key = f"{move['tile'][1]}_{move['tile'][0]}"
                        print(f"[UI] Ficha robada permite jugar {move['tile']} al lado {move['side']}.")
                        self.control_sock.send_string(json.dumps(move))
                        self.control_sock.recv_string()
                        self.slot_map.pop(t_key, None)
                        self.fichas_en_mano -= 1
                        if move["side"] == "L" and len(self.board) > 0:
                            self._center_index += 1
            else:
                print("[UI] Bloqueado. Fin.")
                self.toggle_autoplay()
                return

            # Actualizar UI inmediatamente después del movimiento del brazo
            self.update_from_vision()

            # --- PASAR TURNO AL HUMANO ---
            self.turn = "HUMANO"
            self.turn_var.set("🙋‍♂️ TURNO: JUGADOR 2")
            self.lbl_turn.config(fg="#007bff")
            self.btn_human.config(state=tk.NORMAL)
        except Exception as e:
            print(f"[MOTOR] Error en game_loop (ignorado): {e}")

    def calculate_logic(self):
        """
        Lógica mejorada: decide qué ficha jugar, en qué lado y con qué orientación.
        Si no hay fichas posibles, retorna None (para robar).
        """
        if not self.board: 
            print("[LÓGICA] Tablero vacío. Robot empieza con su primera ficha.")
            t = self.hand[0]
            t_key = f"{t[0]}_{t[1]}"
            if t_key not in self.slot_map: t_key = f"{t[1]}_{t[0]}"
            slot_real = self.slot_map.get(t_key, 0)
            
            # Orientación corregida: Normal = 0.0, Doble = 90.0
            target_theta = 90.0 if t[0] == t[1] else 0.0
            
            return {
                "action": "MOVE", "tile": t, "side": "L",
                "place_pose": {"x": self.TABLERO_CENTRO_X, "y": self.TABLERO_CENTRO_Y, "theta": target_theta},
                "slot_mano": slot_real, "slot_tablero": 0
            }

        l_v, r_v = self.board[0][0], self.board[-1][1]
        print(f"[LÓGICA] Tablero: {l_v} <---> {r_v}. Mano: {self.hand}")

        # Buscar en la mano
        for i, t in enumerate(self.hand):
            t_key = f"{t[0]}_{t[1]}"
            if t_key not in self.slot_map: t_key = f"{t[1]}_{t[0]}"
            slot_real = self.slot_map.get(t_key, i)

            # --- OPCIÓN 1: LADO IZQUIERDO ---
            if t[0] == l_v or t[1] == l_v:
                # Orientación: Doble = 90. Normal = 0 o 180.
                if t[0] == t[1]:
                    target_theta = 90.0
                else:
                    target_theta = 180.0 if t[0] == l_v else 0.0

                x_dest = self.TABLERO_CENTRO_X - (self._center_index + 1) * self.SEPARACION_FICHAS
                print(f"[LÓGICA] Juego {t} en LADO IZQUIERDO. Conecta {l_v}. Theta={target_theta}")
                return {
                    "action": "MOVE", "tile": t, "side": "L",
                    "place_pose": {"x": x_dest, "y": self.TABLERO_CENTRO_Y, "theta": target_theta},
                    "slot_mano": slot_real, "slot_tablero": 0
                }

            # --- OPCIÓN 2: LADO DERECHO ---
            if t[0] == r_v or t[1] == r_v:
                # Orientación: Doble = 90. Normal = 0 o 180.
                if t[0] == t[1]:
                    target_theta = 90.0
                else:
                    target_theta = 180.0 if t[1] == r_v else 0.0

                right_count = len(self.board) - 1 - self._center_index
                x_dest = self.TABLERO_CENTRO_X + (right_count + 1) * self.SEPARACION_FICHAS
                print(f"[LÓGICA] Juego {t} en LADO DERECHO. Conecta {r_v}. Theta={target_theta}")
                return {
                    "action": "MOVE", "tile": t, "side": "R",
                    "place_pose": {"x": x_dest, "y": self.TABLERO_CENTRO_Y, "theta": target_theta},
                    "slot_mano": slot_real, "slot_tablero": len(self.board)
                }

        print("[LÓGICA] No hay jugadas posibles en la mano.")
        return None

    def comenzar_partida(self):
        self.partida_iniciada = True
        self.btn_comenzar.config(state=tk.DISABLED, bg="#555", fg="#aaa")
        self.turn_var.set("🤖 TURNO: ROBOT")
        self.lbl_turn.config(fg="#00ff00")
        self.toggle_autoplay()

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
