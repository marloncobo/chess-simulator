import cv2
import matplotlib.pyplot as plt

from chess_simulator.rutas import IMAGENES

def main():
    ruta_imagen = str(IMAGENES / "torres.jpeg")
    imagen = cv2.imread(ruta_imagen)

    if imagen is None:
        raise FileNotFoundError(f"No se pudo cargar: {ruta_imagen}")

    imagen_rgb = cv2.cvtColor(imagen, cv2.COLOR_BGR2RGB)

    # Escala de grises
    gris = cv2.cvtColor(imagen, cv2.COLOR_BGR2GRAY)

    # LAB
    lab = cv2.cvtColor(imagen, cv2.COLOR_BGR2LAB)
    L, A, B = cv2.split(lab)

    # HSV
    hsv = cv2.cvtColor(imagen, cv2.COLOR_BGR2HSV)
    H, S, V = cv2.split(hsv)

    fig, axes = plt.subplots(1, 4, figsize=(20, 5))

    axes[0].imshow(imagen_rgb)
    axes[0].set_title("Original")
    axes[0].axis("off")

    axes[1].imshow(gris, cmap="gray", vmin=0, vmax=255)
    axes[1].set_title("Escala de grises")
    axes[1].axis("off")

    axes[2].imshow(L, cmap="gray", vmin=0, vmax=255)
    axes[2].set_title("LAB - Canal L")
    axes[2].axis("off")

    axes[3].imshow(V, cmap="gray", vmin=0, vmax=255)
    axes[3].set_title("HSV - Canal V")
    axes[3].axis("off")

    plt.tight_layout()
    plt.show()


if __name__ == "__main__":
    main()
