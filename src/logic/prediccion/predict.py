import rasterio
import numpy as np
import os
import torch
from glob import glob
from tqdm import tqdm

from logic.utils.config_manager import settings
from logic.modelo.model_architecture import BuildingRoadModel

from typing import TypeAlias, Callable

ProgressCallback: TypeAlias = Callable[[int, str, str, bool], None]

def predict_tiles_multiclase(tiles_dir: str, 
                             output_dir: str, 
                             model: BuildingRoadModel,
                             threshold: float = 0.5, 
                             progress_callback: ProgressCallback = None) -> None:
    """
    Se configura el modelo a modo evaluacion y a usar el dispositivo permitido 'CPU' o 'GPU',
    Predice las máscaras multiclase para todos los parches generados del ROI.

    Args
    ----------
    tiles_dir: str
        Ruta de la carpeta donde se almacenan los parches generados
    output_dir: str
        Ruta de salida de las mascaras inferidas
    mode: BuildingRoadModel
        Modelo de inferencia
    progress_callback: ProgressCallback
        Funcion para la actualizacion de la barra de progreso
    """
    os.makedirs(output_dir, exist_ok=True)
    tile_paths = glob(os.path.join(tiles_dir, "*.tif"))
    
    if not tile_paths:
        print("No se encontraron archivos .tif")
        return

    # Configuración de hardware
    device = settings.torch_device
    model.to(device)
    model.eval() # Modo evaluación
    
    print(f"Modo de ejecución: {device}")
    
    tile_count = 0
    total_tiles = len(tile_paths)

    for image_path in tqdm(tile_paths, desc="Prediciendo tiles"):
        filename = "mask_pred_" + os.path.basename(image_path)
        output_path = os.path.join(output_dir, filename)
        
        try:
            with rasterio.open(image_path) as src:
                img = src.read().astype(np.float32) # (Bands, H, W) -> PyTorch prefiere este orden
                meta = src.meta.copy()
                # Si read() ya da (C, H, W), no necesitamos mover ejes para el modelo,
                # pero sí para la normalización ImageNet si la haces con Numpy.
            
            # 1. Preprocesamiento
            img_rgb = img[:3] / 255.0   
            
            # 2. Preparar Tensor (H, W, C) -> (C, H, W)
            img_input = np.ascontiguousarray(img_rgb)
            image_t = torch.from_numpy(img_input).unsqueeze(0).to(device)

            # 3. Inferencia
            with torch.inference_mode():
                logits = model(image_t)
                if logits.shape[1] == 1:
                    probs = torch.sigmoid(logits).squeeze(0).squeeze(0)
                    mask_t = (probs > threshold).to(torch.uint8)
                else:
                    probs = torch.softmax(logits, dim=1)
                    mask_t = torch.argmax(probs, dim=1).squeeze(0).to(torch.uint8)
                mask_class = mask_t.cpu().numpy().astype(np.uint8)

            # 4. Guardar máscara con Rasterio
            meta.update({
                "driver": "GTiff",
                "count": 1,
                "dtype": "uint8",
                "nodata": 0,
                "compress": "lzw"
            })
            
            with rasterio.open(output_path, "w", **meta) as dst:
                dst.write(mask_class, 1)
            
            tile_count += 1
            if progress_callback:
                progress = int((tile_count / total_tiles) * 100)
                progress_callback(progress, f"Procesando {tile_count}/{total_tiles}")

        except Exception as e:
            print(f"Error procesando {os.path.basename(image_path)}: {str(e)}")
            continue
    
    print(f"\nPredicción completada. Máscaras en: {output_dir}")