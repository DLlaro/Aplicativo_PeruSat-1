from roi_tiler import roi_to_tiles
from tensorflow import keras
from prediccion import predict_tiles_multiclase
import numpy as np
import rasterio
from reconstruccion import stitch_tiles_by_class
from to_gpkg import raster_to_vector
import os

def Inferir(tif_path: str, out_dir: str, model_path: str):
    """
    Pipeline completo de inferencia: tiling -> predicción -> reconstrucción -> vectorización
    
    Args:
        tif_path: Ruta al archivo GeoTIFF de entrada
        out_dir: Directorio base de salida
        model_path: Ruta al modelo entrenado
    """
    # Configuración de rutas
    TIF_ID = os.path.basename(tif_path).split(".")[0]
    base_output = os.path.join(out_dir, TIF_ID)
    
    # Estructura de directorios
    paths = {
        'tiles': os.path.join(base_output, "Tiles"),
        'masks': os.path.join(base_output, "Masks_Pred"),
        'recons': os.path.join(base_output, "Reconstruccion"),
        'gpkg': os.path.join(base_output, "GPKG")
    }
    
    # Crear directorios si no existen
    for path in paths.values():
        os.makedirs(path, exist_ok=True)
    
    # Pipeline de procesamiento
    print("=" * 60)
    print(f"Iniciando procesamiento de: {TIF_ID}")
    print("=" * 60)
    
    # 1. Tiling
    print("\n[1/5] Dividiendo imagen en tiles...")
    roi_to_tiles(tif_path, out_dir=paths['tiles'], tile_size=512, overlap=0)
    print("Tiling completado")
    
    # 2. Carga del modelo
    print("\n[2/5] Cargando modelo...")
    model = keras.models.load_model(model_path, compile=False)
    print("Modelo cargado")
    
    # 3. Predicción
    print("\n[3/5] Generando predicciones...")
    predict_tiles_multiclase(paths['tiles'], paths['masks'], model)
    print("Predicción completada")
    
    # 4. Reconstrucción
    print("\n[4/5] Reconstruyendo imagen completa...")
    stitch_tiles_by_class(paths['tiles'], paths['masks'], paths['recons'])
    print("Reconstrucción completada")
    
    # 5. Vectorización
    print("\n[5/5] Vectorizando resultados...")
    raster_to_vector(paths['recons'], out_dir=paths['gpkg'])
    print("Vectorización completada")
    
    print("\n" + "=" * 60)
    print("PROCESO FINALIZADO EXITOSAMENTE")
    print(f"Resultados guardados en: {base_output}")
    print("=" * 60)
    
    return paths

if __name__ == "__main__":
    # Inferencia
    paths = Inferir(
        tif_path= r"C:\Diego\PI\Enero_2026\Etiquetando\Arequipa\extraccion_arequipa_20230531.tif",
        out_dir=r"C:\resultados",
        model_path=r"C:\Diego\PI\Enero_2026\Prediccion\best_unet_iou_building_TODO.keras"
    )