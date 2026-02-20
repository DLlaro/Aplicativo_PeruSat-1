import tensorflow as tf

# 1. Ejecuta esto SOLO UNA VEZ al inicio de tu programa
def inicializar_gpu():
    gpus = tf.config.list_physical_devices('GPU')
    if gpus:
        try:
            for gpu in gpus:
                tf.config.experimental.set_memory_growth(gpu, True)
            print("Crecimiento de memoria activado")
        except RuntimeError as e:
            # Si ya se inicializó, aquí verás el error
            print(f"Nota: La GPU ya estaba inicializada: {e}")

