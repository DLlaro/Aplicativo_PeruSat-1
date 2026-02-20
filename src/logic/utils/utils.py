import subprocess
import psutil
import tensorflow as tf

def get_nvidia_info_tensorflow():
    gpu_devices = tf.config.list_physical_devices('GPU')
    if not gpu_devices:
        return None
    
    # 1. Nombre (vía TF)
    details = tf.config.experimental.get_device_details(gpu_devices[0])
    gpu_name = details.get('device_name', 'Unknown GPU')

    # 2. Memoria usada por la APP (vía TF)
    # Importante: get_memory_info solo funciona si ya hubo alguna operación de tensores
    try:
        mem = tf.config.experimental.get_memory_info('GPU:0')
        usado_app = int(mem['current'] / (1024**2))
    except ValueError:
        usado_app = 0 # Aún no se ha usado la memoria

    # 3. Memoria Total y Libre del Sistema (vía nvidia-smi)
    try:
        res = subprocess.run(
            ["nvidia-smi", "--query-gpu=memory.total,memory.free", "--format=csv,nounits,noheader"],
            capture_output=True, text=True, check=True
        )
        total, free = res.stdout.strip().split(", ")
        return {
            "gpu_name": gpu_name,
            "usado_mb": usado_app,
            "total_mb": int(total),
            "libre_mb": int(free)
        }
    except Exception as e:
        print(f"Error al ejecutar nvidia-smi: {e}")
        return {"gpu_name": gpu_name, "total_mb": 0, "libre_mb": 0}

def get_ram_info():
    ram = psutil.virtual_memory()
    return {
        "total_mb": ram.total // (1024 * 1024),
        "available_mb": ram.available // (1024 * 1024)
    }