import cv2
import numpy as np
import time
import json


class DominoDetector:
    def __init__(self, calib_model: dict = None):
        self.MIN_AREA_PUNTO = 10
        self.MAX_AREA_PUNTO = 500
        self.MAX_EXCENTRICIDAD_PUNTO = 0.85
        self.MIN_AREA_FICHA_ENTERA = 1
        self.MAX_AREA_FICHA_ENTERA = 35000   # descarta blobs grandes (mesa, pared)
        self.MIN_RATIO_ASPECTO = 1.5         # ficha dominó ~2:1
        self.MAX_RATIO_ASPECTO = 3.5
        self.UMBRAL_STDDEV_REVERSO = 10.0
        self.MARGEN_CENTRO_FACTOR = 0.08  # Fix #4: era 0.05, demasiado estrecho
        self.calib_model = calib_model   # Fix #1 y #2: modelo pixel→TCP

    # ── Conversión de coordenadas ──────────────────────────────────────────────

    def _pixel_to_tcp(self, u: float, v: float) -> tuple[float, float, float]:
        """Convierte coordenadas de píxel a TCP del robot (metros)."""
        if self.calib_model is None:
            return float(u), float(v), 0.0
        m = self.calib_model
        x = m["coef_x"][0] * u + m["coef_x"][1] * v + m["intercept_x"]
        y = m["coef_y"][0] * u + m["coef_y"][1] * v + m["intercept_y"]
        return float(x), float(y), float(m["z_fija"])

    def _angle_to_robot(self, angle_deg: float) -> float:
        """Convierte ángulo de imagen al espacio del robot via Jacobiano de calibración."""
        if self.calib_model is None:
            return angle_deg
        m = self.calib_model
        rad = np.deg2rad(angle_deg)
        dx_r = m["coef_x"][0] * np.cos(rad) + m["coef_x"][1] * np.sin(rad)
        dy_r = m["coef_y"][0] * np.cos(rad) + m["coef_y"][1] * np.sin(rad)
        return float(np.rad2deg(np.arctan2(dy_r, dx_r)))

    # ── Utilidades ────────────────────────────────────────────────────────────

    def calcular_excentricidad(self, contour):
        if len(contour) < 5:
            return 0
        (x, y), (MA, ma), angle = cv2.fitEllipse(contour)
        a = ma / 2
        b = MA / 2
        if a == 0:
            return 0
        return np.sqrt(1 - (b ** 2 / a ** 2))

    # ── Pipeline principal ────────────────────────────────────────────────────

    def procesar(self, frame):
        orig_h, orig_w = frame.shape[:2]
        frame = cv2.resize(frame, (800, 450))
        self._scale_u = orig_w / 800.0
        self._scale_v = orig_h / 450.0
        g_channel = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        res_frame = frame.copy()

        # --- 1. MÁSCARA BASE ---
        _, mask_base = cv2.threshold(g_channel, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        contours_externos, _ = cv2.findContours(mask_base, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        mask_solida = np.zeros_like(mask_base)

        for cnt in contours_externos:
            area = cv2.contourArea(cnt)
            # Excluir blobs demasiado pequeños O demasiado grandes (mesa, pared)
            # antes del watershed para que dist_transform.max() no quede dominado
            # por objetos ajenos a las fichas
            if self.MIN_AREA_FICHA_ENTERA * 0.4 <= area <= self.MAX_AREA_FICHA_ENTERA:
                cv2.drawContours(mask_solida, [cnt], -1, 255, -1)

        # --- 2. SEPARADOR GEOMÉTRICO (WATERSHED) ---
        kernel_limpieza = np.ones((3, 3), np.uint8)
        sure_bg = cv2.dilate(mask_solida, kernel_limpieza, iterations=2)
        dist_transform = cv2.distanceTransform(mask_solida, cv2.DIST_L2, 5)

        # Umbral fijo en píxeles en lugar de relativo al máximo global,
        # para que fichas pequeñas (cámara alta) siempre generen markers
        _, sure_fg = cv2.threshold(dist_transform, 5.0, 255, cv2.THRESH_BINARY)
        sure_fg = np.uint8(sure_fg)
        unknown = cv2.subtract(sure_bg, sure_fg)

        _, markers = cv2.connectedComponents(sure_fg)
        markers = markers + 1
        markers[unknown == 255] = 0

        frame_color_ws = cv2.cvtColor(g_channel, cv2.COLOR_GRAY2BGR)
        markers = cv2.watershed(frame_color_ws, markers)

        # --- 3. EXTRACCIÓN DE FICHAS ---
        fichas_a_procesar = []
        mask_solida = np.zeros_like(g_channel)

        for label in np.unique(markers):
            if label == 1 or label == -1:
                continue

            mask_ficha_aislada = np.zeros(g_channel.shape, dtype="uint8")
            mask_ficha_aislada[markers == label] = 255
            mask_solida = cv2.bitwise_or(mask_solida, mask_ficha_aislada)

            cnts, _ = cv2.findContours(mask_ficha_aislada, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            if not cnts:
                continue

            c = max(cnts, key=cv2.contourArea)
            area = cv2.contourArea(c)
            if area < self.MIN_AREA_FICHA_ENTERA * 0.4:
                continue
            if area > self.MAX_AREA_FICHA_ENTERA:
                continue

            rect = cv2.minAreaRect(c)
            (cx, cy), (w, h), angle_deg = rect

            lado_l = max(w, h)
            lado_c = min(w, h)
            if lado_c == 0:
                continue
            ratio = lado_l / lado_c
            if not (self.MIN_RATIO_ASPECTO <= ratio <= self.MAX_RATIO_ASPECTO):
                continue

            if w < h:
                angle_deg += 90

            fichas_a_procesar.append(((cx, cy), (lado_l, lado_c), angle_deg, area))

        # --- 4. CLASIFICACIÓN Y LECTURA DE PUNTOS ---
        mask_oscuras = cv2.adaptiveThreshold(
            g_channel, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY_INV, 21, 8
        )

        fichas_temporales = []
        for ficha_rect in fichas_a_procesar:
            (fcx, fcy), (f_lado_l, f_lado_c), fangle_deg, f_area = ficha_rect
            f_angle_rad = np.deg2rad(fangle_deg)
            vx, vy = np.cos(f_angle_rad), np.sin(f_angle_rad)

            rect_cv = ((fcx, fcy), ficha_rect[1], fangle_deg)
            box_ficha = np.int32(cv2.boxPoints(rect_cv))
            mask_ficha = np.zeros_like(g_channel)
            cv2.fillPoly(mask_ficha, [box_ficha], 255)

            mask_ficha_recortada = cv2.bitwise_and(mask_ficha, mask_solida)
            kernel_borde = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
            mask_ficha_segura = cv2.erode(mask_ficha_recortada, kernel_borde, iterations=1)

            _, stddev = cv2.meanStdDev(g_channel, mask=mask_ficha_segura)
            desviacion = stddev[0][0]

            val_primero = -1
            val_segundo = -1

            if desviacion < self.UMBRAL_STDDEV_REVERSO:
                texto_ficha = "[Reverso]"
                color = (255, 255, 0)
            else:
                puntos_en_ficha = cv2.bitwise_and(mask_oscuras, mask_ficha_segura)
                contours_puntos, _ = cv2.findContours(
                    puntos_en_ficha, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
                )

                val_1, val_2 = 0, 0
                sum_x1, sum_y1, sum_x2, sum_y2 = 0.0, 0.0, 0.0, 0.0
                margen_centro = f_lado_l * self.MARGEN_CENTRO_FACTOR

                for pt_cnt in contours_puntos:
                    area_pt = cv2.contourArea(pt_cnt)
                    if area_pt < self.MIN_AREA_PUNTO or area_pt > self.MAX_AREA_PUNTO:
                        continue
                    if self.calcular_excentricidad(pt_cnt) > self.MAX_EXCENTRICIDAD_PUNTO:
                        continue

                    M = cv2.moments(pt_cnt)
                    if M["m00"] == 0:
                        continue

                    px, py = int(M["m10"] / M["m00"]), int(M["m01"] / M["m00"])
                    proyeccion = (px - fcx) * vx + (py - fcy) * vy

                    if proyeccion > margen_centro:
                        val_1 += 1
                        sum_x1 += px
                        sum_y1 += py
                        cv2.circle(res_frame, (px, py), 3, (0, 0, 255), -1)
                    elif proyeccion < -margen_centro:
                        val_2 += 1
                        sum_x2 += px
                        sum_y2 += py
                        cv2.circle(res_frame, (px, py), 3, (0, 0, 255), -1)

                val_1, val_2 = min(val_1, 6), min(val_2, 6)

                # fangle_deg ∈ [-90°, 90°) ⟹ vx = cos(fangle_deg) ≥ 0 siempre;
                # el signo de vx/vy es código muerto o ambiguo. Se comparan
                # directamente los centroides medios de los puntos de cada mitad.
                if abs(vx) > abs(vy):
                    cx1 = sum_x1 / val_1 if val_1 > 0 else fcx
                    cx2 = sum_x2 / val_2 if val_2 > 0 else fcx
                    val_primero, val_segundo = (val_1, val_2) if cx1 < cx2 else (val_2, val_1)
                else:
                    cy1 = sum_y1 / val_1 if val_1 > 0 else fcy
                    cy2 = sum_y2 / val_2 if val_2 > 0 else fcy
                    val_primero, val_segundo = (val_1, val_2) if cy1 < cy2 else (val_2, val_1)

                texto_ficha = f"[{val_primero}:{val_segundo}]"
                color = (0, 255, 0)

            pos_x, pos_y = int(round(float(fcx))), int(round(float(fcy)))

            fichas_temporales.append({
                'val1': val_primero,
                'val2': val_segundo,
                'texto': texto_ficha,
                'x': pos_x,
                'y': pos_y,
                'angulo': round(float(fangle_deg), 2),
                'area': f_area,
            })

            cv2.polylines(res_frame, [box_ficha], True, (255, 0, 0), 2)
            cv2.putText(res_frame, texto_ficha, (pos_x - 30, pos_y + 5),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)

            # ── Visualización del ángulo detectado ────────────────────────────
            ang_rad = np.deg2rad(fangle_deg)
            L = int(f_lado_l * 0.45)   # longitud de la flecha = 45% del lado largo
            # Eje largo de la ficha (amarillo)
            ex = int(pos_x + L * np.cos(ang_rad))
            ey = int(pos_y + L * np.sin(ang_rad))
            cv2.arrowedLine(res_frame, (pos_x, pos_y), (ex, ey), (0, 255, 255), 2, tipLength=0.2)
            # Eje perpendicular / dirección de agarre del gripper (magenta)
            perp_rad = ang_rad + np.pi / 2
            Lp = int(f_lado_c * 0.45)
            px2 = int(pos_x + Lp * np.cos(perp_rad))
            py2 = int(pos_y + Lp * np.sin(perp_rad))
            cv2.arrowedLine(res_frame, (pos_x, pos_y), (px2, py2), (255, 0, 255), 2, tipLength=0.3)
            # Ángulo imagen (amarillo) y ángulo robot (cyan) sobre la ficha
            theta_rob = self._angle_to_robot(fangle_deg)
            cv2.putText(res_frame, f"img:{fangle_deg:.0f}", (pos_x - 28, pos_y - 22),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 255, 255), 1)
            cv2.putText(res_frame, f"rob:{theta_rob:.0f}", (pos_x - 28, pos_y - 8),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.4, (255, 255, 0), 1)

        fichas_temporales.sort(key=lambda f: f['y'] * 1000 + f['x'])

        # --- 5. CONSTRUCCIÓN DEL FORMATO TIPO JSON ---
        # Las fichas cara-arriba se deduplicand por clave; las de reverso se numeran.
        mejores: dict[str, dict] = {}
        reverso_idx = 0
        for f in fichas_temporales:
            if f['val1'] == -1:
                clave = f"reverso_{reverso_idx}"
                reverso_idx += 1
                mejores[clave] = f
            else:
                clave = f"{f['val1']}_{f['val2']}"
                if clave not in mejores or f['area'] > mejores[clave]['area']:
                    mejores[clave] = f

        array_fichas = []
        dict_poses = {}

        for clave, f in mejores.items():
            u_orig = f['x'] * getattr(self, '_scale_u', 1.0)
            v_orig = f['y'] * getattr(self, '_scale_v', 1.0)
            tcp_x, tcp_y, _ = self._pixel_to_tcp(u_orig, v_orig)
            theta_robot = self._angle_to_robot(f['angulo'])
            print(f"  [{clave}] pixel_800x600=({f['x']},{f['y']})  "
                  f"pixel_nativo=({u_orig:.0f},{v_orig:.0f})  "
                  f"TCP=({tcp_x:.4f}, {tcp_y:.4f})")
            dict_poses[clave] = {
                "x": round(tcp_x, 5),
                "y": round(tcp_y, 5),
                "theta": round(theta_robot, 2),
            }
            if not clave.startswith("reverso"):
                array_fichas.append([f['val1'], f['val2']])

        return res_frame, array_fichas, dict_poses


if __name__ == "__main__":
    try:
        with open("Domino/CameraCalibration/calibracion_juego.json") as f:
            calib_model = json.load(f)
        print(f"[OK] Calibración cargada: posición '{calib_model['position']}'")
    except FileNotFoundError:
        print("[AVISO] calibracion_juego.json no encontrado — poses se devuelven en píxeles")
        calib_model = None

    detector = DominoDetector(calib_model=calib_model)
    cap = cv2.VideoCapture(3, cv2.CAP_V4L2)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH,  9999)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 9999)
    time.sleep(2)

    if not cap.isOpened():
        print("Error: No se detecta la cámara.")
        exit()

    ret, test = cap.read()
    if ret:
        h, w = test.shape[:2]
        print(f"[INFO] Cámara abierta: {w}x{h} px")

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        frame = cv2.rotate(frame, cv2.ROTATE_180)
        resultado_img, fichas, poses = detector.procesar(frame)

        datos_salida = {
            "board": fichas,
            "board_poses": poses,
        }

        texto_info = f"Fichas: {len(fichas)} | Pulsa 'S' para capturar JSON"
        cv2.putText(resultado_img, texto_info, (10, 30),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
        cv2.imshow('Detector de Domino Definitivo', resultado_img)

        key = cv2.waitKey(1) & 0xFF

        if key == ord('s'):
            print("\n" + "=" * 40)
            print("DATOS CAPTURADOS:")
            print("=" * 40)
            print(json.dumps(datos_salida, indent=2))
            print("=" * 40 + "\n")

        elif key == 27:
            break

    cap.release()
    cv2.destroyAllWindows()
