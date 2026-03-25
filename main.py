from robot_controller import RobotController
import time

# --- CONFIGURACIÓN ---
ROBOT_IP = "169.254.12.28"
DIGITAL_OUTPUT_PIN = 4

def main():
    # 1. Instanciar el controlador
    robot = RobotController(ROBOT_IP, wait_time=2)
    
    try:
        # 2. Conectar al robot
        robot.connect()
        robot.actuate_digital_output(DIGITAL_OUTPUT_PIN, False)
        
        # 3. Moverse secuencialmente por posiciones fijas (Articular)
        print("\n--- Ejecutando Rutina de Movimientos Articulares ---")
        robot.move_to_fixed_joint("home")
        time.sleep(0.2)
        robot.move_to_fixed_joint("tablero")
        
        
        # Ejemplo de bajar hasta hacer contacto (Comentado al igual que en tu original)
        #'''
        print("\n--- Buscando contacto en Z ---")
        speed_down = [0, 0, -0.05, 0, 0, 0]
        if robot.move_until_contact(speed_down):
            robot.actuate_digital_output(DIGITAL_OUTPUT_PIN, True)
            time.sleep(1.0)
        #'''

        # 4. Modificar la posición actual y usar MoveL
        print("\n--- Elevando 10 cm desde la posición actual ---")
        tcp_pose = robot.get_current_pose()
        tcp_pose[2] += 0.30  # Cambiando la altura en Z
        robot.move_linear(tcp_pose, speed=0.1, acceleration=0.5)
        
        print("\n--- Moviéndose Soltando pieza---")

        # 6. Actuar salida digital finalizando tarea
        time.sleep(3)
        robot.actuate_digital_output(DIGITAL_OUTPUT_PIN, False)
        # Detener
        robot.stop_script()
        print("\nPrograma terminado con éxito.")
        
    except Exception as e:
        print(f"\nOcurrió un error en la ejecución: {e}")
    finally:
        robot.disconnect()

if __name__ == "__main__":
    main()