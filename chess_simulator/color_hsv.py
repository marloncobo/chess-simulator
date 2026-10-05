"""Clasificación compartida por la prueba HSV y la detección en vivo."""
import cv2
import numpy as np


def clasificar(hsv, poligono, negra_max=85, blanca_min=125, saturacion_max=110,
               erosion=3):
    """Medianas S/V de la máscara interior; H no distingue blanco de negro.

    blanca_min=125 (antes 150): en las fotos de referencia las negras dan
    V <= 28 y las blancas V >= 136; con contraluz, tres blancas de la cámara 2
    quedaban DUDOSAS con V entre 136 y 144. Un gris medio (V ~115) sigue en duda.
    """
    if not 0 <= negra_max < blanca_min <= 255:
        raise ValueError("V negra max debe ser menor que V blanca min")
    if not 0 <= saturacion_max <= 255 or not isinstance(erosion, int) or not 0 <= erosion <= 15:
        raise ValueError("S blanca max debe estar entre 0 y 255; erosión entre 0 y 15")
    # Recortar antes de crear la máscara evita recorrer toda la imagen por pieza.
    poligono = np.asarray(poligono, np.int32).reshape(-1, 2)
    if len(poligono) < 3:
        return {"color": "DUDOSA", "s": None, "v": None, "n": 0}
    x, y, w, h = cv2.boundingRect(poligono)
    x0, y0 = max(0, x), max(0, y)
    x1, y1 = min(hsv.shape[1], x+w), min(hsv.shape[0], y+h)
    if x1 <= x0 or y1 <= y0:
        return {"color": "DUDOSA", "s": None, "v": None, "n": 0}
    hsv = hsv[y0:y1, x0:x1]
    poligono = poligono - (x0, y0)
    mascara = np.zeros(hsv.shape[:2], np.uint8)
    cv2.fillPoly(mascara, [np.asarray(poligono, np.int32)], 255)
    if erosion:
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE,
                                          (2 * erosion + 1, 2 * erosion + 1))
        mascara = cv2.erode(mascara, kernel, borderType=cv2.BORDER_CONSTANT,
                            borderValue=0)
    pixeles = hsv[mascara > 0]
    if len(pixeles) < 20:
        return {"color": "DUDOSA", "s": None, "v": None, "n": len(pixeles)}
    s, v = np.median(pixeles[:, 1:], axis=0)
    color = "DUDOSA"
    if v <= negra_max:
        color = "NEGRA"
    elif v >= blanca_min and s <= saturacion_max:
        color = "BLANCA"
    return {"color": color, "s": float(s), "v": float(v), "n": len(pixeles)}
