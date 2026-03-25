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
            "tablero": [4.7277, -1.5772, 0.2913, -0.5383, -1.6497, -0.47554523]
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
        self.con_io = rtde_io.RTDEIOInterface(self.ip)
        print("Conexión establecida correctamente.")

    def disconnect(self):
        """Cierra las conexiones del robot de manera segura."""
        if self.con_ctr and self.con_ctr.isConnected():
            self.con_ctr.disconnect()
        if self.con_rcv and self.con_rcv.isConnected():
            self.con_rcv.disconnect()
        if self.con_io and self.con_io.isConnected():
            self.con_io.disconnect()
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
        print(f"{'Activando' if value else 'Desactivando'} salida digital {pin}.")
        self.con_io.setStandardDigitalOut(pin, value)

    def move_to_fixed_joint(self, name, speed=1.0, acceleration=1.4):
        """Se mueve a una posición articular predefinida por su nombre."""
        if name in self.fixed_joint_positions:
            return self.move_joint(self.fixed_joint_positions[name], speed, acceleration)
        else:
            raise ValueError(f"Posición articular '{name}' no existe en el registro.")
            
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