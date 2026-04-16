#!/usr/bin/env python3
"""
Calibración extrínseca cámara-robot para el proyecto Dominó.
Mapea coordenadas de píxel (u, v) a coordenadas TCP del robot (X, Y).

Uso:
    python calibrate_extrinsic.py --position juego
    python calibrate_extrinsic.py --position robo

Controles en ventana:
    Clic izquierdo  → congela imagen y pide TCP en terminal
    T               → entrenar modelo y guardar JSON (mínimo 15 puntos)
    D               → eliminar el último punto registrado
    V               → modo verificación: clic muestra TCP predicho
    Q / ESC         → salir sin guardar
"""

import argparse
import sys
import json
import threading

import cv2
import numpy as np
from sklearn.linear_model import LinearRegression

# ── Configuración ─────────────────────────────────────────────────────────────
INTRINSIC_PATH  = "intrinsic_calibration_data.json"
CAMERA_INDEX    = 2
MIN_POINTS      = 15
OUTPUT_TEMPLATE = "calibracion_{position}.json"
DISPLAY_WIDTH   = 800
# ─────────────────────────────────────────────────────────────────────────────


def load_intrinsics(path: str):
    with open(path) as f:
        data = json.load(f)
    return np.array(data["camera_matrix"]), np.array(data["dist_coeffs"])


def undistort_frame(frame, K, dist):
    return frame  # distorsión mínima (k1=-0.008), no se aplica corrección


def to_display(frame):
    """Redimensiona para mostrar en ventana sin modificar el frame original."""
    h, w = frame.shape[:2]
    scale = DISPLAY_WIDTH / w
    return cv2.resize(frame, (DISPLAY_WIDTH, int(h * scale))), scale


def draw_overlay(frame, calibration_data, pending_pixel, n, position, verify_mode):
    display = frame.copy()
    for i, (u, v, x, y) in enumerate(calibration_data):
        cv2.circle(display, (int(u), int(v)), 6, (0, 220, 0), -1)
        cv2.putText(display, str(i + 1), (int(u) + 8, int(v) - 8),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 220, 0), 1)
    if pending_pixel:
        cv2.circle(display, pending_pixel, 9, (0, 140, 255), 2)
    hud_color = (0, 220, 0) if n >= MIN_POINTS else (0, 140, 255)
    label = f"pos:{position}  puntos:{n}/{MIN_POINTS}"
    if verify_mode:
        label += "  [VERIFICACION]"
    cv2.putText(display, label, (10, 26),
                cv2.FONT_HERSHEY_SIMPLEX, 0.65, hud_color, 2)
    return display


def train(calibration_data):
    data  = np.array(calibration_data)
    uv    = data[:, :2]
    model_x = LinearRegression().fit(uv, data[:, 2])
    model_y = LinearRegression().fit(uv, data[:, 3])
    return model_x, model_y


def evaluate(calibration_data, model_x, model_y):
    data   = np.array(calibration_data)
    uv     = data[:, :2]
    pred_x = model_x.predict(uv)
    pred_y = model_y.predict(uv)
    errors = np.sqrt((data[:, 2] - pred_x) ** 2 + (data[:, 3] - pred_y) ** 2)
    print("\n── Estadísticas de calibración ──────────────────────")
    print(f"  Puntos usados  : {len(calibration_data)}")
    print(f"  Error medio    : {np.mean(errors) * 1000:.2f} mm")
    print(f"  Error mediana  : {np.median(errors) * 1000:.2f} mm")
    print(f"  Error máximo   : {np.max(errors) * 1000:.2f} mm")
    print(f"  Error mínimo   : {np.min(errors) * 1000:.2f} mm")
    print("─────────────────────────────────────────────────────\n")


def save_calibration(model_x, model_y, z_fija, position):
    path = OUTPUT_TEMPLATE.format(position=position)
    json.dump({
        "position"    : position,
        "coef_x"      : model_x.coef_.tolist(),
        "intercept_x" : float(model_x.intercept_),
        "coef_y"      : model_y.coef_.tolist(),
        "intercept_y" : float(model_y.intercept_),
        "z_fija"      : float(z_fija),
    }, open(path, "w"), indent=4)
    print(f"  Guardado en: {path}")


def ask_tcp_threaded(n, pixel):
    """
    Pide coordenadas TCP en un hilo secundario para no bloquear OpenCV.
    Devuelve (resultado, evento) — espera el evento en el bucle principal
    llamando a evento.wait(timeout) mientras sigues llamando a cv2.waitKey().
    """
    print(f"\n[Punto {n}] Píxel registrado: u={pixel[0]}  v={pixel[1]}")
    print("  Mueve el TCP del robot a ese punto a la altura de recogida.")
    print("  Introduce  X Y Z  en metros (ej: 0.15 -0.30 0.05):")
    print("  > ", end="", flush=True)

    result = [None]
    done   = threading.Event()

    def _read():
        try:
            raw = input().strip().split()
            if len(raw) >= 2:
                x = float(raw[0])
                y = float(raw[1])
                z = float(raw[2]) if len(raw) >= 3 else None
                result[0] = (x, y, z)
            else:
                print("  [!] Entrada no válida — punto descartado")
        except (ValueError, EOFError):
            print("  [!] Entrada no válida — punto descartado")
        finally:
            done.set()

    threading.Thread(target=_read, daemon=True).start()
    return result, done


# ── Callback de ratón ─────────────────────────────────────────────────────────
_clicked = None
_scale   = 1.0

def _mouse_cb(event, x, y, flags, param):
    global _clicked
    if event == cv2.EVENT_LBUTTONDOWN:
        _clicked = (int(x / _scale), int(y / _scale))


# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    global _clicked, _scale

    parser = argparse.ArgumentParser()
    parser.add_argument("--position", choices=["juego", "robo"], required=True)
    parser.add_argument("--camera",   type=int, default=CAMERA_INDEX)
    args = parser.parse_args()

    print(f"\n=== Calibración extrínseca — posición: {args.position.upper()} ===")
    print(f"  Mínimo recomendado : {MIN_POINTS} puntos")
    print(f"  Salida             : {OUTPUT_TEMPLATE.format(position=args.position)}")
    print("\n  Clic → congela imagen y pide TCP")
    print("  T → entrenar y guardar  |  D → borrar último  |  V → verificar  |  Q → salir\n")

    try:
        K, dist = load_intrinsics(INTRINSIC_PATH)
    except FileNotFoundError:
        print(f"[ERROR] No se encuentra {INTRINSIC_PATH}")
        sys.exit(1)

    cap = cv2.VideoCapture(args.camera)
    if not cap.isOpened():
        print(f"[ERROR] No se puede abrir cámara (índice {args.camera})")
        sys.exit(1)

    # Imprimir resolución para confirmar que es la cámara correcta
    ret, test = cap.read()
    if ret:
        h, w = test.shape[:2]
        print(f"  Cámara {args.camera} abierta: {w}x{h} px\n")

    cv2.namedWindow("Calibracion Extrinseca", cv2.WINDOW_NORMAL)
    cv2.setMouseCallback("Calibracion Extrinseca", _mouse_cb)

    calibration_data = []
    z_fija           = None
    verify_mode      = False
    model_x = model_y = None
    frozen           = None   # frame congelado mientras se espera input
    waiting_input    = False  # True mientras el hilo de input está activo
    input_result_ref = None   # [resultado] del hilo
    input_done_event = None   # threading.Event del hilo
    pending_pixel    = None   # píxel clicado pendiente de TCP

    while True:
        # ── Leer cámara solo si no estamos esperando input ─────────────────
        if not waiting_input:
            ret, frame = cap.read()
            if not ret:
                continue
            frame   = undistort_frame(frame, K, dist)
            current = frame
        else:
            current = frozen

        n       = len(calibration_data)
        display = draw_overlay(current, calibration_data, pending_pixel, n,
                               args.position, verify_mode)
        disp_small, _scale = to_display(display)
        cv2.imshow("Calibracion Extrinseca", disp_small)
        key = cv2.waitKey(30) & 0xFF

        # ── Comprobar si el hilo de input terminó ─────────────────────────
        if waiting_input and input_done_event.is_set():
            waiting_input = False
            frozen        = None
            result        = input_result_ref[0]

            if result is not None:
                x_tcp, y_tcp, z_tcp = result
                if z_fija is None and z_tcp is not None:
                    z_fija = z_tcp
                    print(f"  Z fija establecida: {z_fija:.5f} m")
                elif z_tcp is not None and z_fija is not None \
                        and abs(z_tcp - z_fija) > 0.005:
                    print(f"  [AVISO] Z difiere {abs(z_tcp-z_fija)*1000:.1f} mm"
                          f" de z_fija — se usa z_fija")
                calibration_data.append([pending_pixel[0], pending_pixel[1],
                                         x_tcp, y_tcp])
                print(f"  OK punto {len(calibration_data)}: "
                      f"({pending_pixel[0]},{pending_pixel[1]}) → "
                      f"X={x_tcp:.4f} Y={y_tcp:.4f}")
            pending_pixel = None

        # ── Clic: lanzar hilo de input ─────────────────────────────────────
        if _clicked and not verify_mode and not waiting_input:
            pending_pixel    = _clicked
            _clicked         = None
            frozen           = current.copy()
            waiting_input    = True
            input_result_ref, input_done_event = ask_tcp_threaded(
                n + 1, pending_pixel)

        # ── Clic en modo verificación ──────────────────────────────────────
        elif _clicked and verify_mode and model_x is not None:
            u_v, v_v = _clicked
            _clicked  = None
            uv        = np.array([[u_v, v_v]])
            x_p = model_x.predict(uv)[0]
            y_p = model_y.predict(uv)[0]
            print(f"  [VERIF] ({u_v},{v_v}) → X={x_p:.4f}  Y={y_p:.4f}  Z={z_fija:.4f}")

        # ── Teclas (ignorar mientras se espera input) ──────────────────────
        if waiting_input:
            continue

        if key in (ord('q'), 27):
            print("\n[!] Saliendo sin guardar.")
            break

        elif key == ord('d') and calibration_data:
            removed = calibration_data.pop()
            print(f"  [D] Eliminado punto {len(calibration_data)+1}: {removed}")

        elif key == ord('v'):
            if model_x is None and len(calibration_data) >= MIN_POINTS:
                model_x, model_y = train(calibration_data)
            verify_mode = not verify_mode
            print(f"  [V] Verificación: {'ON' if verify_mode else 'OFF'}")

        elif key == ord('t'):
            if len(calibration_data) < MIN_POINTS:
                print(f"  [!] Necesitas {MIN_POINTS} puntos (tienes {len(calibration_data)})")
                continue
            if z_fija is None:
                print("  Introduce Z fija (m): ", end="", flush=True)
                try:
                    z_fija = float(input().strip())
                except ValueError:
                    print("  [!] Valor no válido")
                    continue
            model_x, model_y = train(calibration_data)
            evaluate(calibration_data, model_x, model_y)
            save_calibration(model_x, model_y, z_fija, args.position)
            break

    cap.release()
    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
