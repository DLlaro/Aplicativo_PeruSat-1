import psutil
import torch

def get_nvidia_info_torch():
    """
    Verifica si existe cuda en el computador y recolectar información de la gpu

    return
    ----------
    dict :dict
        - "gpu_name": Nombre de la GPU
        - "usado_mb": VRAM usada por torch
        - "total_mb": VRAM total
        - "libre_mg": VRAM libre
    """
    # Caso 1: No hay GPU o drivers no instalados
    if not torch.cuda.is_available():
        return {
            "gpu_name": "CPU",
            "usado_mb": 0,
            "total_mb": 0,
            "libre_mb": 0
        }
    
    try:
        device_id = 0
        gpu_name = torch.cuda.get_device_name(device_id)

        # Memoria reservada por los tensores de PyTorch
        usado_app = int(torch.cuda.memory_allocated(device_id) / (1024**2))

        # Propiedades del hardware
        total_mem = torch.cuda.get_device_properties(device_id).total_memory
        total_mb = int(total_mem / (1024**2))
        
        # Memoria libre real del sistema (VRAM no ocupada por Windows/Apps)
        free_bytes, _ = torch.cuda.mem_get_info(device_id)
        libre_mb = int(free_bytes / (1024**2))

        return {
            "gpu_name": gpu_name,
            "usado_mb": usado_app,
            "total_mb": total_mb,
            "libre_mb": libre_mb
        }
    except Exception as e:
        print(f"Error consultando GPU: {e}")
        return {
            "gpu_name": "CPU",
            "usado_mb": 0,
            "total_mb": 0,
            "libre_mb": 0
        }

def get_ram_info():
    """
    Recolecta información de la RAM del equipo

    return
    ----------
    dict :dict
        - "total_mb": RAM total
        - "available_mb": RAM disponible
    """
    ram = psutil.virtual_memory()
    return {
        "total_mb": ram.total // (1024 * 1024),
        "available_mb": ram.available // (1024 * 1024)
    }