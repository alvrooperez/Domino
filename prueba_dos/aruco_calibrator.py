"""
Módulo de calibración automática pixel→TCP usando marcadores ArUco.

Uso:
    from aruco_calibrator import calibrar_con_arucos

    calib_model, n, debug_frame = calibrar_con_arucos(frame, config)
    # calib_model = {"H": [[3×3]], "z_fija": float}  (homografía + RANSAC)
    #             compatible con modelo lineal antiguo en DominoDetector
    # n           = número de marcadores detectados y usados
    # debug_frame = imagen 800×450 con los marcadores anotados

La homografía se ajusta en cada llamada: no importa si la cámara se movió.
"""

import cv2
import numpy as np
import time
from sklearn.linear_model import LinearRegression

DICT_TYPE   = cv2.aruco.DICT_4X4_50
MIN_MARKERS = 3   # homografía: 8 DOF → min 4 pares; 3 markers = 12 esquinas, más que suficiente


def _detectar_arucos(frame):
    """Devuelve {marker_id: {"center": (cx_px, cy_px), "corners": ndarray(4,2)}}."""
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
            c = corners[i][0].astype(float)   # (4, 2)  orden: TL TR BR BL
            result[int(mid)] = {
                "center":  (float(c[:, 0].mean()), float(c[:, 1].mean())),
                "corners": c,
            }
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
    intento = 0
    while True:
        intento += 1
        orig_h, orig_w = frame.shape[:2]
        scale_u = 800.0 / orig_w
        scale_v = 450.0 / orig_h

        detected = _detectar_arucos(frame)

        # Emparejar marcadores detectados con TCP conocidos
        used_ids      = []
        center_puntos = []   # [u_nat, v_nat, tcp_x, tcp_y] — centros para ajuste rugoso

        for id_str, tcp in config["markers"].items():
            mid = int(id_str)
            if mid in detected:
                u_nat, v_nat = detected[mid]["center"]
                center_puntos.append([u_nat, v_nat, tcp["tcp_x"], tcp["tcp_y"]])
                used_ids.append(mid)

        n = len(center_puntos)

        if n >= MIN_MARKERS:
            break

        if cap is None:
            break

        print(f"[ArUco] Solo {n} markers visibles, reintentando (intento {intento})...")
        time.sleep(1)
        ret, new_frame = cap.read()
        if ret:
            frame = cv2.rotate(new_frame, cv2.ROTATE_180)

    # ── Frame de debug ────────────────────────────────────────────────────────
    disp = cv2.resize(frame, (800, 450))

    for mid, det in detected.items():
        u_nat, v_nat = det["center"]
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

    # ── Paso 1: ajuste lineal rugoso con los centros (n puntos) ──────────────
    data_c  = np.array(center_puntos)
    rough_x = LinearRegression().fit(data_c[:, :2], data_c[:, 2])
    rough_y = LinearRegression().fit(data_c[:, :2], data_c[:, 3])
    J = np.array([rough_x.coef_, rough_y.coef_])   # Jacobiano 2×2: pixel→TCP

    # ── Paso 2: calcular TCPs de las 4 esquinas por marker vía Jacobiano ─────
    corner_puntos = []   # [u_nat, v_nat, tcp_x, tcp_y] — 4 esquinas × n markers
    for id_str, tcp in config["markers"].items():
        mid = int(id_str)
        if mid not in detected:
            continue
        px_center  = np.array(detected[mid]["center"])
        tcp_center = np.array([tcp["tcp_x"], tcp["tcp_y"]])
        for k in range(4):
            px_corner  = detected[mid]["corners"][k]
            tcp_corner = tcp_center + J @ (px_corner - px_center)
            corner_puntos.append([px_corner[0], px_corner[1],
                                   tcp_corner[0], tcp_corner[1]])

    # ── Paso 3: homografía con RANSAC sobre los puntos de esquinas ────────────
    pts      = np.array(corner_puntos, dtype=np.float32)
    src_pts  = pts[:, :2]   # píxeles  (N×2)
    dst_pts  = pts[:, 2:]   # TCP      (N×2)
    H, hmask = cv2.findHomography(src_pts, dst_pts, cv2.RANSAC, 0.003)

    if H is None:
        print("[ArUco] findHomography falló — no se genera calibración")
        return None, n, disp

    # ── Calcular y mostrar errores de reproyección ────────────────────────────
    n_pts   = len(src_pts)
    src_h   = np.hstack([src_pts, np.ones((n_pts, 1), dtype=np.float32)])   # (N,3)
    proj    = (H @ src_h.T).T                                                # (N,3)
    proj_xy = proj[:, :2] / proj[:, 2:3]                                    # (N,2)
    errs    = np.linalg.norm(proj_xy - dst_pts, axis=1)
    inliers = hmask.flatten().astype(bool) if hmask is not None else np.ones(n_pts, bool)
    print(f"[ArUco] {n} marcadores ({n_pts} esquinas)  |  "
          f"inliers {inliers.sum()}/{n_pts}  |  "
          f"error medio {np.mean(errs[inliers])*1000:.1f} mm  "
          f"máx {np.max(errs[inliers])*1000:.1f} mm")

    # Anotar error del centro de cada marker en el debug frame
    for mid in used_ids:
        u_nat, v_nat = detected[mid]["center"]
        cx_d = int(u_nat * scale_u)
        cy_d = int(v_nat * scale_v)
        src_c = np.array([[[u_nat, v_nat]]], dtype=np.float32)
        pred  = cv2.perspectiveTransform(src_c, H)[0, 0]
        ref   = config["markers"][str(mid)]
        err_c = np.linalg.norm(pred - [ref["tcp_x"], ref["tcp_y"]])
        cv2.putText(disp, f"{err_c*1000:.1f}mm",
                    (cx_d + 12, cy_d + 14),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.4, (255, 255, 0), 1)

    # ── Construir calib_model ──────────────────────────────────────────────────
    calib_model = {
        "H":      H.tolist(),
        "z_fija": config["z_fija"],
    }
    return calib_model, n, disp
