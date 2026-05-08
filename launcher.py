import subprocess
import sys
import time

def main():
    print("🚀 Iniciando el sistema Domino...")

    # sys.executable asegura que usemos el mismo Python (y entorno virtual) 
    # con el que ejecutamos este launcher
    python_bin = sys.executable

    try:
        # 1. Lanzamos el servidor de Visión
        print("[LANZADOR] Arrancando Visión...")
        vision_process = subprocess.Popen([python_bin, "fake_vision.py"])
        time.sleep(1) # Le damos un segundo para que abra el puerto

        # 2. Lanzamos el servidor de Control (UR3e)
        print("[LANZADOR] Arrancando Control...")
        control_process = subprocess.Popen([python_bin, "fake_control.py"])
        time.sleep(1)

        # 3. Lanzamos el Motor (Tu juego)
        print("[LANZADOR] Arrancando Motor Principal...")
        engine_process = subprocess.Popen([python_bin, "main_engine.py"])

        # El lanzador se queda esperando a que el motor termine 
        # (es decir, a que cierres la ventana de Tkinter)
        engine_process.wait()

    except KeyboardInterrupt:
        # Por si pulsas Ctrl+C en la consola para abortar todo
        print("\n[LANZADOR] Interrupción manual detectada.")
    
    finally:
        print("\n🛑 Cerrando todos los módulos...")
        # Matamos los servidores de fondo para que los puertos 5555 y 5556 queden libres
        vision_process.terminate()
        control_process.terminate()
        print("✅ Sistema apagado correctamente.")

if __name__ == "__main__":
    main()