"""
Módulo de calibración automática pixel→TCP usando marcadores ArUco.

Uso:
    from aruco_calibrator import calibrar_con_arucos

    calib_model, n, debug_frame = calibrar_con_arucos(frame, config)
    # calib_model tiene el mismo formato que calibracion_juego.json
    # n           = número de marcadores detectados y usados
    # debug_frame = imagen 800×450 con los marcadores anotados

El modelo lineal se ajusta en cada llamada: no importa si la cámara se movió.
"""

import cv2
import numpy as np
import time
from sklearn.linear_model import LinearRegression

DICT_TYPE   = cv2.aruco.DICT_4X4_50
MIN_MARKERS = 3   # X = au·u + av·v + b  → 3 incógnitas, necesitamos ≥ 3 puntos


def _detectar_arucos(frame):
    """Devuelve {marker_id: (cx_px, cy_px)} en coordenadas del frame recibido."""
    aruco_dict = cv2.aruco.getPredefinedDictionary(DICT_TYPE)
    params     = cv2.aruco.DetectorParameters()
    try:
        detector        = cv2.aruco.ArucoDetector(aruco_dict, params)
        corners, ids, _ = detector.detectMarkers(frame)
    except AttributeError:
        # OpenCV < 4.7
        corners, ids, _ = cv2.aruco.detectMarkers(frame, aruco_dict, parameters=params)

    result = {}
    if ids is not None:
        for i, mid in enumerate(ids.flatten()):
            result[int(mid)] = (
                float(np.mean(corners[i][0][:, 0])),
                float(np.mean(corners[i][0][:, 1])),
            )
    return result


def calibrar_con_arucos(frame, config, cap=None):
    """
    Parámetros
    ----------
    frame  : imagen BGR en resolución nativa (ya rotada 180° si procede)
    config : dict cargado de arucos_config.json
    cap    : cv2.VideoCapture opcional; si se pasa, reintenta hasta 5 veces capturando nuevo frame

    Retorna
    -------
    calib_model : dict compatible con DominoDetector  (None si faltan marcadores)
    n_detectados: int
    debug_frame : imagen BGR 800×450 con los marcadores anotados
    """
    MAX_INTENTOS = 5

    for intento in range(1, MAX_INTENTOS + 1):
        orig_h, orig_w = frame.shape[:2]
        scale_u = 800.0 / orig_w
        scale_v = 450.0 / orig_h

        # Detectar en resolución nativa para máxima precisión
        detected = _detectar_arucos(frame)

        # Emparejar marcadores detectados con TCP conocidos
        used_ids = []
        puntos   = []   # [u_nat, v_nat, tcp_x, tcp_y]

        for id_str, tcp in config["markers"].items():
            mid = int(id_str)
            if mid in detected:
                u_nat, v_nat = detected[mid]
                puntos.append([u_nat, v_nat, tcp["tcp_x"], tcp["tcp_y"]])
                used_ids.append(mid)

        n = len(puntos)

        if n >= MIN_MARKERS:
            break

        if cap is not None and intento < MAX_INTENTOS:
            print(f"[ArUco] Solo {n} markers visibles, reintentando (intento {intento}/5)...")
            time.sleep(1)
            ret, new_frame = cap.read()
            if ret:
                frame = cv2.rotate(new_frame, cv2.ROTATE_180)
        else:
            break

    # ── Frame de debug ────────────────────────────────────────────────────────
    disp = cv2.resize(frame, (800, 450))

    for mid, (u_nat, v_nat) in detected.items():
        cx = int(u_nat * scale_u)
        cy = int(v_nat * scale_v)
        in_config = str(mid) in config["markers"]
        color = (0, 220, 0) if in_config else (0, 140, 255)
        cv2.circle(disp, (cx, cy), 10, color, 2)
        cv2.putText(disp, f"ID{mid}", (cx + 12, cy - 8),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.55, color, 1)

    color_e = (0, 220, 0) if n >= MIN_MARKERS else (0, 0, 200)
    cv2.putText(disp, f"ArUcos: {n}/{len(config['markers'])}",
                (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, color_e, 2)

    if n < MIN_MARKERS:
        cv2.putText(disp, f"FALTAN MARCADORES (min {MIN_MARKERS})",
                    (10, 62), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 200), 2)
        return None, n, disp

    # ── Ajustar modelo lineal ─────────────────────────────────────────────────
    data    = np.array(puntos)
    uv      = data[:, :2]
    model_x = LinearRegression().fit(uv, data[:, 2])
    model_y = LinearRegression().fit(uv, data[:, 3])

    errs = np.sqrt(
        (model_x.predict(uv) - data[:, 2]) ** 2 +
        (model_y.predict(uv) - data[:, 3]) ** 2
    )
    print(f"[ArUco] {n} marcadores  |  "
          f"error medio {np.mean(errs)*1000:.1f} mm  "
          f"máx {np.max(errs)*1000:.1f} mm")

    # Anotar error individual en el debug frame
    for i, mid in enumerate(used_ids):
        u_nat, v_nat = detected[mid]
        cx = int(u_nat * scale_u)
        cy = int(v_nat * scale_v)
        cv2.putText(disp, f"{errs[i]*1000:.1f}mm",
                    (cx + 12, cy + 14),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.4, (255, 255, 0), 1)

    # ── Construir calib_model ─────────────────────────────────────────────────
    calib_model = {
        "coef_x"     : model_x.coef_.tolist(),
        "intercept_x": float(model_x.intercept_),
        "coef_y"     : model_y.coef_.tolist(),
        "intercept_y": float(model_y.intercept_),
        "z_fija"     : config["z_fija"],
    }
    return calib_model, n, disp
