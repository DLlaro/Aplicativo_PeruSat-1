import subprocess

def get_nvidia_info():
    try:
        result = subprocess.run(
            ["nvidia-smi", 
             "--query-gpu=name,memory.total,memory.free", 
             "--format=csv,noheader,nounits"],
            capture_output=True,
            text=True,
            check=True
        )

        name, total, free = result.stdout.strip().split(", ")
        return {
            "name": name,
            "vram_total_mb": int(total),
            "vram_free_mb": int(free)
        }
    except Exception:
        return None

print(get_nvidia_info())

import psutil

def get_ram_info():
    ram = psutil.virtual_memory()
    return {
        "total_mb": ram.total // (1024 * 1024),
        "available_mb": ram.available // (1024 * 1024)
    }

print(get_ram_info())