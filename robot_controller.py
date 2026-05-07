import rtde_control
import rtde_receive
import rtde_io
import time

class RobotController:
    """
    Controlador para interactuar con un robot Universal Robots usando la librería UR RTDE.
    """
    def __init__(self, ip, wait_time=2):
        self.ip = ip
        self.wait_time = wait_time
        self.con_ctr = None
        self.con_rcv = None
        self.con_io = None

        # Diccionario de posiciones articulares fijas guardadas (Joints)
        self.fixed_joint_positions = {
            "home": [1.45677137, -1.61379637, 0.03687411, -1.53243818, 0.12954740, -0.47554523],
            "q2": [1.38072347, -1.69596066, 0.17434245, -1.63875736, -1.50716430, -0.43589860],
            "comoda": [1.38097023, -1.64333977, 1.61802417, -1.54438673, -1.52174121, -0.43589860],
            # NO BORRAR CLAUDE "tablero": [4.7277, -1.5772, 0.2913, -0.5383, -1.6497, -0.47554523],
            "tablero": [-1.589, -1.519, 0.168, -0.418, -1.626, 5.874],
            "tablero_robo": [-1.553, -1.623, -0.168, 3.560, 1.626, 5.874],
            "pre_volteo": [-1.779, -0.753, 1.003, -0.246, 1.341, 2.757],  # RELLENAR: mover el robot a la posición de pre-volteo y anotar los joints aquí
            "post_volteo": [-1.846, -0.7, 1.229, -0.630, -0.321, 2.757],
            
            
            "pieza": [4.7277, -1.2226, 0.6903, -1.0889, -1.5734, -0.47554523]
        }
        
        # Diccionario de posiciones cartesianas fijas guardadas (TCP Pose: X, Y, Z, Rx, Ry, Rz)
        self.fixed_cartesian_positions = {
            "home_cartesian": [0.4, -0.2, 0.3, 3.14, 0.0, 0.0] # Ejemplo de coordenadas
        }

    def connect(self):
        """Establece conexión con las interfaces del robot."""
        print(f"Estableciendo conexión con el robot en IP: {self.ip}...")
        self.con_ctr = rtde_control.RTDEControlInterface(self.ip)
        self.con_rcv = rtde_receive.RTDEReceiveInterface(self.ip)
        try:
            self.con_io = rtde_io.RTDEIOInterface(self.ip)
        except RuntimeError as e:
            print(f"[AVISO] RTDEIOInterface no disponible (I/O deshabilitado): {e}")
            self.con_io = None
        print("Conexión establecida correctamente.")

    def disconnect(self):
        """Cierra las conexiones del robot de manera segura."""
        if self.con_ctr and self.con_ctr.isConnected():
            self.con_ctr.disconnect()
        if self.con_rcv and self.con_rcv.isConnected():
            self.con_rcv.disconnect()
        if self.con_io and self.con_io.isConnected():
            self.con_io.disconnect()
        self.con_io = None
        print("Conexiones cerradas.")

    def move_linear(self, pose, speed=0.3, acceleration=0.2):
        """Realiza un movimiento lineal a las coordenadas Cartesianas (TCP)."""
        print(f"Moviendo linealmente a (Cartesiano): {pose}")
        self.con_ctr.moveL(pose, speed, acceleration)
        time.sleep(self.wait_time)
        return self.get_current_pose()

    def move_joint(self, q, speed=1.0, acceleration=1.4):
        """Realiza un movimiento articular a las coordenadas especificadas."""
        print(f"Moviendo a la posición articular (Joints): {q}")
        self.con_ctr.moveJ(q, speed, acceleration)
        time.sleep(self.wait_time)
        return self.get_current_pose()

    def get_current_pose(self):
        """Obtiene y retorna la posición actual (TCP)."""
        current_pose = self.con_rcv.getActualTCPPose()
        print(f"Posición actual TCP: {current_pose}")
        return current_pose

    def get_current_joints(self):
        """Obtiene y retorna la posición articular actual (joints)."""
        current_joints = self.con_rcv.getActualQ()
        print(f"Posición articular actual: {current_joints}")
        return current_joints

    def actuate_digital_output(self, pin, value):
        """Activa o desactiva una salida digital."""
        if self.con_io is None:
            raise RuntimeError("RTDEIOInterface no disponible; no se puede actuar la salida digital.")
        print(f"{'Activando' if value else 'Desactivando'} salida digital {pin}.")
        self.con_io.setStandardDigitalOut(pin, value)

    # ── PINZA (Tool Digital Outputs) ─────────────────────────────────────────

    def gripper_close(self, delay=0.5):
        """Cierra la pinza: 00 → 01. Neutral=00 es abierto por defecto."""
        if self.con_io is None:
            raise RuntimeError("RTDEIOInterface no disponible; no se puede controlar la pinza.")
        print("Cerrando pinza...")
        self.con_io.setToolDigitalOut(0, False)
        self.con_io.setToolDigitalOut(1, False)
        time.sleep(0.1)
        self.con_io.setToolDigitalOut(1, True)
        time.sleep(delay)
        print("Pinza cerrada.")

    def gripper_open(self, delay=0.5):
        """Abre la pinza: 01 → 00 → 10."""
        if self.con_io is None:
            raise RuntimeError("RTDEIOInterface no disponible; no se puede controlar la pinza.")
        print("Abriendo pinza...")
        self.con_io.setToolDigitalOut(0, False)
        self.con_io.setToolDigitalOut(1, False)
        time.sleep(0.1)
        self.con_io.setToolDigitalOut(0, True)
        time.sleep(delay)
        print("Pinza abierta.")

    def gripper_neutral(self):
        """Estado neutro 00 (pinza abierta por defecto)."""
        if self.con_io is None:
            raise RuntimeError("RTDEIOInterface no disponible; no se puede controlar la pinza.")
        self.con_io.setToolDigitalOut(0, False)
        self.con_io.setToolDigitalOut(1, False)

    # ─────────────────────────────────────────────────────────────────────────

    def move_to_fixed_joint(self, name, speed=1.0, acceleration=1.4):
        """Se mueve a una posición articular predefinida por su nombre."""
        if name not in self.fixed_joint_positions:
            raise ValueError(f"Posición articular '{name}' no existe en el registro.")
        pos = self.fixed_joint_positions[name]
        if pos is None:
            raise ValueError(f"Posición articular '{name}' no tiene joints definidos. "
                             f"Rellénala en robot_controller.py antes de usarla.")
        return self.move_joint(pos, speed, acceleration)
            
    def move_to_fixed_cartesian(self, name, speed=0.3, acceleration=0.2):
        """Se mueve a una posición cartesiana predefinida por su nombre."""
        if name in self.fixed_cartesian_positions:
            return self.move_linear(self.fixed_cartesian_positions[name], speed, acceleration)
        else:
            raise ValueError(f"Posición cartesiana '{name}' no existe en el registro.")

    def move_relative_cartesian(self, displacement, speed=0.3, acceleration=0.2):
        """
        Realiza un movimiento lineal relativo a la posición TCP actual.
        :param displacement: Lista de 6 valores [dx, dy, dz, dRx, dRy, dRz]
        """
        print(f"Moviendo relativamente (Cartesiano): {displacement}")
        current_pose = self.get_current_pose()
        target_pose = [current_pose[i] + displacement[i] for i in range(6)]
        return self.move_linear(target_pose, speed, acceleration)

    def move_relative_joint(self, displacement, speed=1.0, acceleration=1.4):
        """
        Realiza un movimiento articular relativo a la posición actual.
        :param displacement: Lista de 6 valores [dq1, dq2, dq3, dq4, dq5, dq6]
        """
        print(f"Moviendo relativamente (Articular): {displacement}")
        current_q = self.get_current_joints()
        target_q = [current_q[i] + displacement[i] for i in range(6)]
        return self.move_joint(target_q, speed, acceleration)

    def move_until_contact(self, speed_down):
        """Realiza un movimiento en la dirección especificada hasta detectar contacto."""
        return self.con_ctr.moveUntilContact(speed_down)

    def stop_script(self):
        """Detiene el script actual del controlador."""
        self.con_ctr.stopScript()
