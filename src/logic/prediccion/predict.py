import os
from glob import glob
from typing import Callable, TypeAlias

import numpy as np
import rasterio
import torch
from tqdm import tqdm

from logic.modelo.model_architecture import BuildingRoadModel
from logic.utils.config_manager import settings

ProgressCallback: TypeAlias = Callable[[int, str, str, bool], None]


def predict_tiles_multiclase(
    tiles_dir: str,
    output_dir: str,
    model: BuildingRoadModel,
    threshold: float = 0.5,
    progress_callback: ProgressCallback = None,
) -> None:
    """
    Ejecuta inferencia por tile para un modelo de segmentacion.
    - Si el modelo retorna 1 canal: flujo binario (sigmoid + threshold).
    - Si retorna mas de 1 canal: fallback multiclase (softmax + argmax).
    """
    os.makedirs(output_dir, exist_ok=True)
    tile_paths = sorted(glob(os.path.join(tiles_dir, "*.tif")))

    if not tile_paths:
        print("No se encontraron archivos .tif")
        return

    device = settings.torch_device
    model.to(device)
    model.eval()
    print(f"Modo de ejecucion: {device}")

    tile_count = 0
    total_tiles = len(tile_paths)

    for image_path in tqdm(tile_paths, desc="Prediciendo tiles"):
        filename = "mask_pred_" + os.path.basename(image_path)
        output_path = os.path.join(output_dir, filename)

        try:
            with rasterio.open(image_path) as src:
                img = src.read([1,2,3]).astype(np.float32)
                valid_mask = src.dataset_mask() > 0         # (H,W) boolean

                meta = src.meta.copy()

            img_rgb = img[:3] / 255.0
            image_t = torch.from_numpy(np.ascontiguousarray(img_rgb)).unsqueeze(0).to(device)

            with torch.inference_mode():
                logits = model(image_t)

                if logits.shape[1] == 1:
                    probs = torch.sigmoid(logits).squeeze(0).squeeze(0)
                    mask_t = (probs > threshold).to(torch.uint8)
                else:
                    probs = torch.softmax(logits, dim=1)
                    mask_t = torch.argmax(probs, dim=1).squeeze(0).to(torch.uint8)

                mask_class = mask_t.cpu().numpy().astype(np.uint8)
                pred_masked = mask_class.copy()
                pred_masked[~valid_mask] = 0

            meta.update(
                {
                    "driver": "GTiff",
                    "count": 1,
                    "dtype": "uint8",
                    "nodata": 0,
                    "compress": "lzw",
                }
            )

            with rasterio.open(output_path, "w", **meta) as dst:
                dst.write(pred_masked, 1)

            tile_count += 1
            if progress_callback:
                progress = int((tile_count / total_tiles) * 100)
                progress_callback(progress, f"Procesando {tile_count}/{total_tiles}")

        except Exception as e:
            print(f"Error procesando {os.path.basename(image_path)}: {str(e)}")
            continue

    print(f"\nPrediccion completada. Mascaras en: {output_dir}")
