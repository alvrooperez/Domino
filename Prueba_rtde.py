import rtde_control
import rtde_receive
import rtde_io
import time

# --- CONFIGURACIÓN ---
ROBOT_IP = "169.254.12.28"  # Reemplaza con la IP real de tu robot
DIGITAL_OUTPUT_PIN = 4  # Salida digital a activar al detectar contacto

# Parámetros de movimiento
SPEED = 0.3  # m/s
ACCELERATION = 0.2  # m/s^2
WAIT_TIME = 2  # Tiempo de espera entre movimientos (segundos)

# --- FUNCIONES ---
def move_linear(con_ctr, con_rcv, pose, speed, acceleration):
    """Realiza un movimiento lineal a las coordenadas especificadas y muestra la posición actual."""
    print(f"Moviendo linealmente a: {pose}")
    con_ctr.moveL(pose, speed, acceleration)  # Movimiento lineal
    time.sleep(WAIT_TIME)  # Esperar para estabilización
    current_pose = con_rcv.getActualTCPPose()  # Obtener la posición actual
    print(f"Posición actual del robot: {current_pose}")
    return current_pose  # Retorna la posición actual

def move_joint(con_ctr, con_rcv, q, speed, acceleration):
    """Realiza un movimiento articular a las coordenadas especificadas y muestra la posición actual."""
    print(f"Moviendo a la posición articular: {q}")
    con_ctr.moveJ(q, speed, acceleration)  # Movimiento articular
    time.sleep(WAIT_TIME)  # Esperar para estabilización
    current_pose = con_rcv.getActualTCPPose()  # Obtener la posición actual
    print(f"Posición actual del robot: {current_pose}")
    return current_pose  # Retorna la posición actual

# --- MAIN ---
if __name__ == "__main__":
    try:
        print("Estableciendo conexión con el robot...")
        con_ctr = rtde_control.RTDEControlInterface(ROBOT_IP)
        con_rcv = rtde_receive.RTDEReceiveInterface(ROBOT_IP)
        con_io = rtde_io.RTDEIOInterface(ROBOT_IP)
        print("Conexión establecida.")

        # 1️⃣ Realizar los 3 movimientos MoveJ al principio
        # Primera posición articular
        q1 = [1.4567713737487793, -1.6137963734068812, 0.03687411943544561, 
              -1.5324381862631817, 0.12954740226268768, -0.4755452314959925]
        current_pose = move_joint(con_ctr, con_rcv, q1, 1.0, 1.4)
        
        # Segunda posición articular
        q2 = [1.380723476409912, -1.6959606609740199, 0.17434245744814092, 
              -1.6387573681273402, -1.5071643034564417, -0.43589860597719365]
        current_pose = move_joint(con_ctr, con_rcv, q2, 1.0, 1.4)
        
        # Tercera posición articular (posición cómoda)
        comfortable_q = [1.3809702396392822, -1.6433397732176722, 1.6180241743670862, 
                       -1.544386738245823, -1.5217412153827112, -0.43589860597719365]
        current_pose = move_joint(con_ctr, con_rcv, comfortable_q, 1.0, 1.4)
        if current_pose is None:
            raise Exception("No se pudo mover a la posición cómoda. Abortando.")

        # 2️⃣ Bajar hasta detectar contacto
        '''
        print("Descendiendo hasta contacto...")
        speed_down = [0, 0, -0.05, 0, 0, 0]  # Velocidad en Z negativa (bajar)
        contact_detected = con_ctr.moveUntilContact(speed_down)

        if contact_detected:
            con_io.setStandardDigitalOut(DIGITAL_OUTPUT_PIN, True)  # Activar salida digital
            print("Contacto detectado, salida digital activada.")
            time.sleep(1.0)  # Esperar 1s antes de subir
        '''
        
        # 3️⃣ Subir en línea recta
        tcp_pose = con_rcv.getActualTCPPose()
        tcp_pose[2] += -0.10  # Subir 10 cm
        current_pose = move_linear(con_ctr, con_rcv, tcp_pose, 0.1, 0.5)
        if current_pose is None:
            raise Exception("No se pudo mover a la posición deseada después de contacto. Abortando.")

        # 4️⃣ Moverse a una nueva posición lateral
        new_q = comfortable_q[:]
        new_q[0] -= 3.14159  # Cambiar la orientación del brazo
        current_pose = move_joint(con_ctr, con_rcv, new_q, 1.0, 1.4)
        if current_pose is None:
            raise Exception("No se pudo mover a la nueva posición lateral. Abortando.")

        # 5️⃣ Apagar la salida digital 4 al finalizar
        con_io.setStandardDigitalOut(DIGITAL_OUTPUT_PIN, False)
        print("Salida digital desactivada.")
        time.sleep(0.2)  # Pequeña espera antes de finalizar

        # 6️⃣ Terminar el programa
        con_ctr.stopScript()
        print("Programa terminado.")

    except Exception as e:
        print(f"Ocurrió un error: {e}")

    finally:
        if 'con_ctr' in locals() and con_ctr.isConnected():
            con_ctr.disconnect()
        if 'con_rcv' in locals() and con_rcv.isConnected():
            con_rcv.disconnect()
        if 'con_io' in locals() and con_io.isConnected():
            con_io.disconnect()
        print("Conexión cerrada.")