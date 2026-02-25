import shutil
import os

def clean_temp_files(paths: dict) -> bool:
    """
    Limpia archivos creados durante la inferencia

    Args
    ----------
    paths: dict
        Diccionario con las rutas a las carpetas creadas durante la inferencia

    Return
    ----------
    :bool
        - True → Se limpio con exito
        - False → Error al limpiar las carpetas
    """
    try:
        for key, path in paths.items():
            if key != "gpkg":
                if os.path.exists(path):
                    shutil.rmtree(path)
        return True
    except Exception as e:
        print(f"Error al eliminar carpeta: {e}")
        return False