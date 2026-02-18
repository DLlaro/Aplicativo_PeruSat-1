import os
import json
import numpy as np
import rasterio
from rasterio.transform import Affine
from tqdm import tqdm

def stitch_tiles_by_class(tif_name: str,
                          tiles_dir: str, 
                          pred_dir: str, 
                          output_dir: str, 
                          num_classes=3, progress_callback=None):
    
    metadata_path = os.path.join(tiles_dir, "tiles_metadata.json")
    with open(metadata_path) as f:
        meta = json.load(f)
    
    # H y W aquí deben ser x_end y y_end calculados en el paso de tiling
    H, W = meta["height"], meta["width"]
    tile_size = meta["tile_size"]
    stride = meta["stride"]
    
    # El margen se usa para evitar artefactos de borde en las predicciones
    margin = (tile_size - stride) // 2 if stride < tile_size else 0

    # Inicializar lienzos (uno por cada clase)
    canvases = [np.zeros((H, W), dtype=np.uint8) for _ in range(num_classes)]

    num_tiles = len(meta["tiles"])
    
    for i, tile in enumerate(tqdm(meta["tiles"], desc="Stitching tiles")):
        # Construir ruta de la máscara predicha
        # Asegúrate de que el nombre coincida con cómo guardas tus predicciones
        pred_path = os.path.join(pred_dir, f"mask_pred_patch_{tile['id']}.tif")
        
        if not os.path.exists(pred_path):
            print(f"Warning: Predicción no encontrada para {tile['id']}")
            continue

        with rasterio.open(pred_path) as src:
            pred = src.read(1).astype(np.uint8)
        
        # Coordenadas de origen del tile
        tx, ty = tile["x"], tile["y"]

        # 1. Extraer la parte "válida" (sin márgenes de solape)
        # Si no hay solape, margin es 0 y se toma el tile completo
        if margin > 0:
            valid_part = pred[margin:tile_size-margin, margin:tile_size-margin]
            y_start, x_start = ty + margin, tx + margin
        else:
            valid_part = pred
            y_start, x_start = ty, tx

        # 2. Calcular límites de pegado en el canvas
        # Esto previene errores si y_start o x_start son negativos o exceden H, W
        v_h, v_w = valid_part.shape
        
        # Coordenadas finales en el canvas
        y0, y1 = max(0, y_start), min(y_start + v_h, H)
        x0, x1 = max(0, x_start), min(x_start + v_w, W)

        # 3. Ajustar el recorte de la máscara (por si acaso toca el borde del canvas)
        # Esto sincroniza la parte de valid_part que realmente cabe en el canvas
        if y1 > y0 and x1 > x0:
            crop_y0 = y0 - y_start
            crop_y1 = crop_y0 + (y1 - y0)
            crop_x0 = x0 - x_start
            crop_x1 = crop_x0 + (x1 - x0)
            
            final_valid = valid_part[crop_y0:crop_y1, crop_x0:crop_x1]

            # 4. Pegar en los canvases por clase
            for c in range(num_classes):
                # Usamos maximum para no sobrescribir si hay micro-solapes
                canvases[c][y0:y1, x0:x1] = np.maximum(
                    canvases[c][y0:y1, x0:x1], 
                    (final_valid == c).astype(np.uint8)
                )

        if progress_callback:
            progress = int(((i + 1) / num_tiles) * 100)
            progress_callback(progress, 100, f"Reconstruyendo el ROI")

    # Reconstruir la transformación de Rasterio
    transform = Affine(*meta["transform"][:6])

    # Guardar cada clase por separado
    progress_callback(0, 100, "Separando clases (TIFF):")
    os.makedirs(output_dir, exist_ok=True)
    count = 1
    for c in range(1,num_classes):# clases de 1 al 2 (solo roads y buildings)
        out_path = os.path.join(output_dir, f"{tif_name}_class_{c}.tif")
        with rasterio.open(
            out_path, "w",
            driver="GTiff",
            height=H, width=W,
            count=1, dtype="uint8",
            crs=meta["crs"],
            transform=transform,
            compress="lzw"
        ) as dst:
            dst.write(canvases[c], 1)
        print(f"Clase {c} guardada en {out_path}")
        
        count += 1

        if progress_callback:
            progress = int((count / len(range(1,num_classes))) * 100)
            progress_callback(progress, 100, f"Separando clases (TIFF):")
