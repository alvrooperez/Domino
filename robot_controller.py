import rtde_control
import rtde_receive
import rtde_io
import time
import math

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
            "tablero": [-1.5891, -1.7881, 0.0989, -0.2342, -1.5904, 5.8943],
            "tablero_robo": [1.5928, -1.9335, 0.3604, -0.3199, -1.6258, -0.4093],
            "centro_robo":[1.2493, -1.1963, 1.2690, -1.5500, -1.6455, -0.3917],
            "pre_volteo": [-1.779, -0.753, 1.003, -0.246, 1.341, 2.757],
            "post_volteo": [-1.846, -0.7, 1.229, -0.630, -0.321, 2.757],
            "intermedio_volteo": [-0.1998, -1.5025, 1.5685, -1.5495, -1.6455, -0.3917],
            # RELLENAR: Mover el robot a una posición segura sobre el primer hueco de la mano
            # y anotar aquí los valores de las articulaciones.
            "mano_jugador_base": [-2.37, -1.57, -1.57, -1.57, 1.57, 0.0], # ¡¡¡ VALOR DE EJEMPLO !!!
            "mano_jugador_arriba": [-1.281, -0.849, 0.900, -1.644, -1.471, 4.560], # ¡COPIA AQUÍ LOS JOINTS CON LA MUÑECA ARRIBA!
            "centro": [-1.9160, -1.3523, 1.5849, -1.8373, -1.5636, -0.7264],
            "aprox_mano": [-1.4352, -0.8280, 0.9346, -1.6986, -1.4704, 4.3464]
            
        }
        
        # Distancia entre los centros de los huecos de la mano del jugador (en metros)
        self.MANO_SEPARACION_SLOT = 0.04 # Ejemplo: 5 cm

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
        self.con_ctr.moveL(pose, speed, acceleration)
        time.sleep(self.wait_time)
        return self.get_current_pose()

    def move_joint(self, q, speed=1.0, acceleration=1.4):
        """Realiza un movimiento articular a las coordenadas especificadas."""
        self.con_ctr.moveJ(q, speed, acceleration)
        time.sleep(self.wait_time)
        return self.get_current_pose()

    def move_joint_IK(self, pose, speed=2.0, acceleration=1.4):
        """
        Realiza un movimiento articular (MoveJ) hacia unas coordenadas Cartesianas (TCP Pose).
        El controlador calcula la cinemática inversa automáticamente.
        """
        self.con_ctr.moveJ_IK(pose, speed, acceleration)
        time.sleep(self.wait_time)
        return self.get_current_pose()

    def get_current_pose(self):
        """Obtiene y retorna la posición actual (TCP)."""
        current_pose = self.con_rcv.getActualTCPPose()
        return current_pose

    def get_current_joints(self):
        """Obtiene y retorna la posición articular actual (joints)."""
        current_joints = self.con_rcv.getActualQ()
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
        self.con_io.setToolDigitalOut(0, False)
        self.con_io.setToolDigitalOut(1, False)
        time.sleep(0.1)
        self.con_io.setToolDigitalOut(1, True)
        time.sleep(delay)

    def gripper_open(self, delay=0.5):
        """Abre la pinza: 01 → 00 → 10."""
        if self.con_io is None:
            raise RuntimeError("RTDEIOInterface no disponible; no se puede controlar la pinza.")
        self.con_io.setToolDigitalOut(0, False)
        self.con_io.setToolDigitalOut(1, False)
        time.sleep(0.1)
        self.con_io.setToolDigitalOut(0, True)
        time.sleep(delay)

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
        current_pose = self.get_current_pose()
        target_pose = [current_pose[i] + displacement[i] for i in range(6)]
        return self.move_linear(target_pose, speed, acceleration)

    def move_relative_joint(self, displacement, speed=1.0, acceleration=1.4):
        """
        Realiza un movimiento articular relativo a la posición actual.
        :param displacement: Lista de 6 valores [dq1, dq2, dq3, dq4, dq5, dq6]
        """
        current_q = self.get_current_joints()
        target_q = [current_q[i] + displacement[i] for i in range(6)]
        return self.move_joint(target_q, speed, acceleration)

    def move_until_contact(self, speed_down):
        """Realiza un movimiento en la dirección especificada hasta detectar contacto."""
        return self.con_ctr.moveUntilContact(speed_down)

    def stop_script(self):
        """Detiene el script actual del controlador."""
        self.con_ctr.stopScript()

    def pre_rotate_gripper(self, target_angle_rad, speed=0.5, acceleration=0.5):
        """
        Pre-rota la articulación 6 (muñeca) para alinearla con un ángulo deseado,
        tomando siempre el camino más corto para evitar vueltas innecesarias.

        :param target_angle_rad: Ángulo final deseado para la muñeca, en radianes.
        """
        tcp_actual = self.get_current_pose()
        q_actual   = list(self.get_current_joints())
        alpha      = 2.0 * math.atan2(tcp_actual[4], tcp_actual[3])
        delta_j6   = target_angle_rad - alpha
        delta_j6   = (delta_j6 + math.pi) % (2 * math.pi) - math.pi
        q_actual[5] += delta_j6
        self.move_joint(q_actual, speed=speed, acceleration=acceleration)

    def recoger_voltear_y_colocar(self, pose_ficha, slot_index, config):
        """
        Secuencia completa: recoge una ficha, la voltea y la coloca en un hueco de la mano.

        :param pose_ficha: dict con {'x', 'y', 'theta'} de la ficha a recoger.
        :param slot_index: int, índice del hueco en la mano del jugador (0, 1, 2...).
        :param config: dict con parámetros de movimiento:
                       'Z_APROXIMACION', 'Z_RECOGIDA', 'CORRECCION_GRIPPER',
                       'DESCENSO_VOLTEO', 'POSICION_BASE'.
        """
        print(f"\n[CONTROL] Recogiendo ficha en X={pose_ficha['x']:.3f}, Y={pose_ficha['y']:.3f} para mano slot {slot_index}")

        # --- 1. Recoger la ficha ------------------------------------------------
        self.move_to_fixed_joint(config['POSICION_BASE'])

        self.gripper_neutral()

        angulo_deseado = (math.radians(pose_ficha['theta'])
                          + math.pi / 2
                          + math.radians(config['CORRECCION_GRIPPER']))
        orient = [
            math.pi * math.cos(angulo_deseado / 2),
            math.pi * math.sin(angulo_deseado / 2),
            0.0,
        ]

        self.gripper_open()
        self.move_to_fixed_joint("centro_robo")
        self.pre_rotate_gripper(angulo_deseado, speed=0.5, acceleration=0.5)
        self.move_joint_IK([pose_ficha['x'], pose_ficha['y'], config['Z_APROXIMACION']] + orient, speed=0.15, acceleration=0.1)
        self.move_until_contact([0.0, 0.0, -0.02, 0.0, 0.0, 0.0])

        self.gripper_neutral()
        self.gripper_close(delay=1.0)
        self.move_linear([pose_ficha['x'], pose_ficha['y'], config['Z_APROXIMACION']] + orient, speed=0.1, acceleration=0.1)
        #-----2.0 Ir a zona de volteo -----------------
        self.move_to_fixed_joint("centro_robo")
        self.move_to_fixed_joint("intermedio_volteo")
        self.move_to_fixed_joint("centro")
        # --- 2.1 Voltear la ficha ------------------------------------------------
        print("    [CONTROL] Volteando ficha...")
        self.move_to_fixed_joint("pre_volteo")
        self.move_relative_cartesian([0.0, 0.0, -config['DESCENSO_VOLTEO'], 0.0, 0.0, 0.0], speed=0.05, acceleration=0.05)
        self.move_relative_cartesian([0.0, -0.045, 0.0, 0.0, 0.0, 0.0], speed=0.05, acceleration=0.05)
        time.sleep(0.5)
        self.move_relative_cartesian([0.0, 0.0, 0.15, 0.0, 0.0, 0.0], speed=0.05, acceleration=0.05)

        # --- 3. Colocar en la mano del jugador ----------------------------------
        print(f"    [CONTROL] Colocando en hueco mano {slot_index}...")
        self.move_to_fixed_joint("post_volteo")
        time.sleep(0.5)

        pose_base_mano = self.get_current_pose()
        pose_hueco = pose_base_mano[:]
        # "Bajar en Y" para separar las fichas según el hueco
        pose_hueco[1] -=  slot_index * self.MANO_SEPARACION_SLOT

        if slot_index > 0:
            self.move_linear(pose_hueco, speed=0.1, acceleration=0.1)

        self.move_relative_cartesian([-0.02, 0.0, 0, 0.0, 0.0, 0.0], speed=0.05, acceleration=0.05)
        self.move_relative_cartesian([0.0, 0.0, -0.03, 0.0, 0.0, 0.0], speed=0.05, acceleration=0.05)
        self.gripper_open(delay=0.5)
        self.gripper_neutral()

        # --- 4. Volver a posición segura ----------------------------------------
        self.move_relative_cartesian([0.0, 0.0, 0.072, 0.0, 0.0, 0.0], speed=0.1, acceleration=0.1)
        self.move_to_fixed_joint("pre_volteo")
        print("    [CONTROL] Ficha en mano.")

    def mover_mano_a_tablero(self, slot_mano, place_pose, config):
        """
        Recoge una ficha de un hueco de la mano del jugador y la coloca en el tablero
        usando la pose de destino calculada por el motor.
        """
        print(f"\n[CONTROL] Moviendo ficha: Mano Slot {slot_mano} -> Tablero X={place_pose['x']:.3f}, Y={place_pose['y']:.3f}, Theta={place_pose['theta']:.1f}")

        # --- 1. Recoger de la mano ---
        self.move_to_fixed_joint(config['POSICION_BASE'])
        self.gripper_open()
        
        self.move_to_fixed_joint("mano_jugador_arriba")
        time.sleep(0.5)
        self.move_relative_cartesian([0.01, 0.00, 0.0, 0.0, 0.0, 0.0], speed=0.05, acceleration=0.05)

        pose_base_mano = self.get_current_pose()
        pose_hueco = pose_base_mano[:]
        pose_hueco[1] -= slot_mano * self.MANO_SEPARACION_SLOT

        if slot_mano > 0:
            self.move_linear(pose_hueco, speed=0.1, acceleration=0.1)

        self.move_relative_cartesian([0.0, 0.0, -0.04, 0.0, 0.0, 0.0], speed=0.05, acceleration=0.05)
        
        self.gripper_close(delay=1.0)
        self.move_relative_cartesian([0.0, 0.0, 0.072, 0.0, 0.0, 0.0], speed=0.1, acceleration=0.1)

        # --- 2. Colocar en el tablero ---
        self.move_to_fixed_joint("centro")

        # Calcular orientación final
        # La mano está orientada en una pose fija. Para girar la ficha en el tablero:
        angulo_deseado = math.radians(place_pose['theta']) + math.pi / 2 + math.radians(config['CORRECCION_GRIPPER'])
        orient = [
            math.pi * math.cos(angulo_deseado / 2),
            math.pi * math.sin(angulo_deseado / 2),
            0.0,
        ]

        print(f"    [CONTROL] Posicionando en tablero con rotación...")
        #self.pre_rotate_gripper(angulo_deseado, speed=0.5, acceleration=0.5)
        # Nos movemos sobre el destino
        self.move_joint_IK([place_pose['x'], place_pose['y'], 0.12] + orient, speed=0.15, acceleration=0.1)
        
        # Bajamos hasta contacto
        self.move_until_contact([0.0, 0.0, -0.03, 0.0, 0.0, 0.0])
        self.move_relative_cartesian([0.0, 0.0, 0.005, 0.0, 0.0, 0.0], speed=0.1, acceleration=0.1)
        self.gripper_open(delay=0.5)
        self.gripper_neutral()

        # Salida segura
        self.move_relative_cartesian([0.0, 0.0, 0.04, 0.0, 0.0, 0.0], speed=0.1, acceleration=0.1)
        self.move_to_fixed_joint(config['POSICION_BASE'])
        print("    [CONTROL] Ficha colocada con éxito.")
