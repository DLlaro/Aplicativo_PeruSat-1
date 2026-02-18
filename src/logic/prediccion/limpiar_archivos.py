import shutil
import os

def clean_temp_files(paths: dict) -> bool:
    try:
        for key, path in paths.items():
            if key != "gpkg":
                if os.path.exists(path):
                    shutil.rmtree(path)
        return True
    except Exception as e:
        print(f"Error al eliminar carpeta: {e}")
        return False