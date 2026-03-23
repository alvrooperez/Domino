# Sistema de Control de Domino con Brazo Robótico (UR3e)

Este proyecto implementa una arquitectura basada en microservicios para jugar al dominó contra un humano utilizando un brazo robótico UR3e y un sistema de visión artificial.

La comunicación entre los diferentes procesos se realiza de forma asíncrona mediante **ZeroMQ (ZMQ)** y el intercambio de mensajes en formato **JSON**.

---

## 1. Arquitectura y Flujo General

El sistema se divide en tres módulos principales orquestados por un lanzador (`launcher.py`):

1. **Motor Principal (main_engine.py)**: Es el cerebro del sistema y la Interfaz Hombre-Máquina (HMI). Decide los movimientos y controla la máquina de estados.
2. **Módulo de Visión**: Se encarga de capturar el estado del mundo real mediante una cámara y traducirlo a estructuras de datos lógicas.
3. **Módulo de Control**: Recibe las órdenes de movimiento del Motor y las ejecuta físicamente en el brazo robótico.

### Flujo de la Partida (Máquina de Estados)

El juego alterna entre el turno del Robot y el turno del Humano de la siguiente manera:

1. **Turno del Robot**:
   - El Motor pide a la Visión el estado actual de la mesa y las fichas disponibles.
   - El Motor calcula la jugada óptima.
   - El Motor envía el comando de movimiento y las coordenadas exactas al Control.
   - El brazo físico se mueve, recoge la ficha y la deposita.
   - El Control avisa a la Visión de que el entorno ha cambiado.
   - El Control responde al Motor que ha terminado.
   - El Motor cede el turno al Humano y pausa su lógica automática.

2. **Turno del Humano**:
   - El operario humano coloca físicamente su ficha en el tablero real.
   - El operario pulsa el botón "Confirmar Jugada" en la pantalla (HMI).
   - El Motor ordena a la cámara escanear de nuevo el tablero.
   - El Motor retoma el control y vuelve a empezar su turno.

El ciclo se repite hasta que uno de los jugadores se queda sin fichas.

---

## 2. Guía para implementar la Visión Real

El script actual `fake_vision.py` es un simulador. Para implementar el módulo real con OpenCV (por ejemplo, `real_vision.py`), el programa debe cumplir con los siguientes requisitos de red e interfaz:

### Requisitos de Conexión (ZeroMQ)
- Debe abrir un socket de tipo `zmq.REP` en el puerto `tcp://*:5555` para escuchar las peticiones del Motor.
- Debe abrir un socket de tipo `zmq.REP` en el puerto `tcp://*:5557` para escuchar las confirmaciones del módulo de Control.

### Estructura de Datos (Petición GET_STATE)
Cuando reciba el string `"GET_STATE"` por el puerto 5555, la Visión debe usar procesamiento de imagen (OpenCV) para:
1. Detectar los contornos de las fichas.
2. Clasificarlas según su región (ROI) en "Fichas de la Mano" y "Fichas de la Mesa".
3. Leer los puntos de cada ficha (mediante detección de círculos o plantillas).
4. **Ordenar las fichas de la mesa** basándose en la proximidad de sus coordenadas físicas, formando una lista lineal donde el primer elemento es el extremo izquierdo y el último el extremo derecho.

Debe responder enviando un JSON con la siguiente estructura exacta:

```json
{
  "board": [[6, 6], [6, 4], [4, 1]], 
  "robot_hand": [[1, 1], [3, 4], [5, 2]],
  "robot_hand_poses": {
    "1_1": {"x": 0.25, "y": 0.30, "theta": 0.0},
    "3_4": {"x": 0.30, "y": 0.30, "theta": 90.0}
  },
  "board_poses": {
    "6_6": {"x": 0.50, "y": 0.50, "theta": 0.0},
    "6_4": {"x": 0.55, "y": 0.50, "theta": 90.0}
  },
  "boneyard_poses": {
    "0_1": {"x": 0.80, "y": 0.10, "theta": 0.0},
    "2_3": {"x": 0.85, "y": 0.10, "theta": 0.0}
  },
  "human_hand_count": 5,
  "boneyard_empty": false
}
```
*Nota: Las claves de los diccionarios de posiciones deben ser strings con el formato `"Valor1_Valor2"`. Las coordenadas (x, y) deben estar en metros respecto a la base del robot.*

---

## 3. Guía para implementar el Control Real (UR3e)

El script actual `fake_control.py` simula esperas de tiempo. Para implementar el control físico del robot mediante librerías como `ur_rtde` o sockets TCP de Universal Robots, debes cumplir con lo siguiente:

### Requisitos de Conexión (ZeroMQ)
- Debe abrir un socket de tipo `zmq.REP` en el puerto `tcp://*:5556` para escuchar las órdenes del Motor.
- Debe abrir un socket de tipo `zmq.REQ` para conectarse a `tcp://localhost:5557` y avisar a la visión cuando termine un movimiento físico.

### Comandos Recibidos del Motor
El Motor te enviará un string JSON. Debes decodificarlo y actuar en consecuencia.

**Comando de Movimiento (MOVE):**
```json
{
  "action": "MOVE",
  "tile": [3, 4],
  "side": "L",
  "grab_pose": {"x": 0.30, "y": 0.30, "theta": 90.0},
  "place_pose": {"x": 0.55, "y": 0.60, "theta": 0.0}
}
```

**Lógica requerida para MOVE:**
1. Extraer `grab_pose`. Traducir `X`, `Y` y `Theta` a las coordenadas de TCP del UR3e.
2. Realizar trayectoria: Acercarse en Z, abrir pinza, bajar Z, cerrar pinza, subir Z.
3. Extraer `place_pose`. Traducir a coordenadas de destino.
4. Realizar trayectoria: Moverse encima del destino, bajar Z, abrir pinza, subir Z.
5. Una vez terminado todo el recorrido físico, notificar a Visión a través del puerto 5557 enviando el mismo JSON que recibiste.
6. Esperar el "OK" de Visión, y finalmente responder al Motor por el puerto 5556 con `{"status": "done"}`.

**Comando de Robo (STEAL):**
```json
{
  "action": "STEAL",
  "grab_pose": {"x": 0.80, "y": 0.10, "theta": 0.0},
  "place_pose": {"x": 0.70, "y": 0.80, "theta": 0.0}
}
```

**Lógica requerida para STEAL:**
1. Ejecutar una trayectoria programada (waypoints fijos) hacia la zona donde se apilan las fichas del pozo.
2. Recoger la ficha superior.
3. Mover el robot hacia la zona de "Fichas de la Mano" y depositarla en un espacio libre.
4. Notificar a visión por el puerto 5557 enviando `{"action": "STEAL"}`.
5. Responder al Motor por el puerto 5556 con `{"status": "done"}`.

---

## Notas Finales

Asegúrate de ejecutar siempre el sistema completo a través de `launcher.py` para garantizar que los procesos arrancan en el orden correcto y que los puertos de red se cierran limpiamente al terminar la aplicación.