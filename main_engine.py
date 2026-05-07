from collections import deque
import random
import tkinter as tk # Viene por defecto en Python

class DominoGame:
    def __init__(self):
        self.game_zone = deque()
        self.player1 = []
        self.player2 = []
        self.dominoes = []
        # Variables para el render
        self.window = None
        self.canvas = None

    def render(self):
        # Si la ventana no existe, la creamos
        if self.window is None:
            self.window = tk.Tk()
            self.window.title("Domino Render")
            self.canvas = tk.Canvas(self.window, width=800, height=400, bg="#2d5a27")
            self.canvas.pack()
            # Botón para salir
            tk.Button(self.window, text="Stop & Close", command=self.window.destroy).pack()

        self.canvas.delete("all")

        # Dibujar Zona de Juego (Mesa)
        x_mesa = 50
        for t in self.game_zone:
            self._draw_tile(x_mesa, 150, t, "white")
            x_mesa += 50

        # Dibujar Mano Jugador 1
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
        """Método auxiliar para dibujar una ficha"""
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
        else:
            print(" -> Boneyard empty.")

    def put_dominoe(self, action):
        idx, side = action[0], action[1]
        t = self.player1[idx]
        if side == 'L':
            l_val = self.game_zone[0][0]
            if t[1] != l_val: t = (t[1], t[0])
            self.game_zone.appendleft(t) 
        elif side == 'R':
            r_val = self.game_zone[-1][1]
            if t[0] != r_val: t = (t[1], t[0])
            self.game_zone.append(t)
        self.player1[idx] = None

    def choose_action(self, options):
        if not options:
            self.steal()
            return 
        self.put_dominoe(options[0])

    def turn(self):
        options = self.check_possibilities()
        self.choose_action(options)

if __name__ == "__main__":
    juego = DominoGame()
    all_dominoes = [(i, j) for i in range(7) for j in range(i, 7)]
    random.shuffle(all_dominoes)
    juego.dominoes = all_dominoes
    
    # Setup inicial
    juego.game_zone.append(juego.dominoes.pop())
    for _ in range(7):
        juego.player1.append(juego.dominoes.pop())
    
    print("Press ENTER in the console to advance turn...")
    
    while any(tile is not None for tile in juego.player1):
        juego.render() # <-- LLAMADA AL RENDER
        
        # Pausa manual en consola para que puedas ver qué pasa
        input("Next step? (Press Enter)") 
        
        juego.turn()
        
        if not juego.check_possibilities() and not juego.dominoes:
            print("Game blocked!")
            break

    juego.render() # Render final
    print("--- GAME OVER ---")
    juego.window.mainloop() # Mantiene la ventana abierta al terminar