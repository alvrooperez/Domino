import socket
import struct
import time

ROBOT_IP = "192.168.56.101"

def get_joint_positions(sock):
    """Lee las 6 articulaciones (base, shoulder, elbow, wrist1, wrist2, wrist3)"""
    # El paquete del puerto 30003 es de 1116 bytes.
    # Las posiciones articulares (Actual joint positions) están en los bytes 252 a 299.
    data = sock.recv(1116)
    joints = struct.unpack('!6d', data[252:300])
    return list(joints)

def move_robot_joints(sock, joints, vel=0.05, acc=0.1):
    """Envía comando movej al robot (usa lista de radianes, NO lleva 'p[]')"""
    # Importante: movej para joints NO usa el prefijo 'p', va directo: [q1, q2, q3, q4, q5, q6]
    cmd = f"movej([{joints[0]},{joints[1]},{joints[2]},{joints[3]},{joints[4]},{joints[5]}], a={acc}, v={vel})\n"
    sock.send(cmd.encode('utf-8'))

# --- CONFIGURACIÓN DE CONEXIÓN ---
print("Conectando con el controlador...")
# Usamos el puerto 30003 para leer estado y enviar comandos (Secondary Interface)
sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
sock.connect((ROBOT_IP, 30003))
print("¡Conectado!")

home=[3.14, -1.57, 0, -1.57, 0.0, 0.0] 
target=[3.14, -1.57, 1.57, -1.57, -1.5, 0.0]  # Posición de home (en radianes)
try:
    move_robot_joints(sock, home, vel=0.5, acc=0.3)
    time.sleep(10)  # Espera a que el robot llegue a home
    # 1. Leer articulaciones actuales
    joints_actual = get_joint_positions(sock)
    print(f"Joints actuales (rad): {joints_actual}")

    # 2. Crear objetivo: Mover la base (index 0) 0.2 radianes (~11 grados)
    joints_objetivo = joints_actual[:]
    joints_objetivo[0] += 0.0
    joints_objetivo[4] -= 1.5
    joints_objetivo[2] += 1.5
    
    print(f"Moviendo la base a: {joints_objetivo[0]} rad...")
    #move_robot_joints(sock, joints_objetivo,vel=0.5,acc=0.3)
    
    # Espera manual ya que el socket no bloquea el hilo
    time.sleep(10)

    # 3. Volver a la posición inicial
    print("Volviendo a la posición original...")
    #move_robot_joints(sock, joints_actual)
    time.sleep(4)

finally:
    print("Cerrando socket.")
    sock.close()