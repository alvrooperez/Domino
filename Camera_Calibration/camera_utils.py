"""
Utilidades de cámara para el proyecto Dominó.
Cargadas por el módulo de visión en tiempo de ejecución.
"""

import json
import cv2
import numpy as np


def load_intrinsics(path: str = "intrinsic_calibration_data.json"):
    with open(path) as f:
        data = json.load(f)
    return np.array(data["camera_matrix"]), np.array(data["dist_coeffs"])


def undistort_frame(frame, K, dist):
    h, w = frame.shape[:2]
    new_K, _ = cv2.getOptimalNewCameraMatrix(K, dist, (w, h), 1)
    return cv2.undistort(frame, K, dist, None, new_K)


def load_extrinsic(path: str):
    """Carga el modelo de calibración extrínseca desde JSON."""
    with open(path) as f:
        return json.load(f)


def pixel_to_tcp(model: dict, u: float, v: float) -> tuple[float, float, float]:
    """
    Convierte coordenadas de píxel a coordenadas TCP del robot.

    Args:
        model : diccionario cargado desde calibracion_juego.json / calibracion_robo.json
        u, v  : coordenadas del píxel (imagen ya desdistorsionada)

    Returns:
        (X, Y, Z) en metros en el marco de referencia del robot
    """
    x = model["coef_x"][0] * u + model["coef_x"][1] * v + model["intercept_x"]
    y = model["coef_y"][0] * u + model["coef_y"][1] * v + model["intercept_y"]
    z = model["z_fija"]
    return float(x), float(y), float(z)
