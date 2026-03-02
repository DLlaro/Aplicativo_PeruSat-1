import json
import os
from typing import Callable, TypeAlias

import numpy as np
import rasterio
from rasterio.transform import Affine
from tqdm import tqdm

ProgressCallback: TypeAlias = Callable[[int, str, str, bool], None]


def stitch_tiles_by_class(
    tif_name: str,
    tiles_dir: str,
    pred_dir: str,
    output_dir: str,
    num_classes: int = 3,
    building_class: int = 1,
    progress_callback: ProgressCallback = None,
) -> None:
    """
    Reconstruye el ROI a partir de mascaras predichas por tile y exporta
    un unico raster binario de edificaciones (0=fondo, 1=edificacion).
    """
    metadata_path = os.path.join(tiles_dir, "tiles_metadata.json")
    with open(metadata_path, encoding="utf-8") as f:
        meta = json.load(f)

    h, w = meta["height"], meta["width"]
    tile_size = meta["tile_size"]
    stride = meta["stride"]
    margin = (tile_size - stride) // 2 if stride < tile_size else 0

    canvas_buildings = np.zeros((h, w), dtype=np.uint8)
    num_tiles = len(meta["tiles"])

    for i, tile in enumerate(tqdm(meta["tiles"], desc="Stitching tiles")):
        pred_path = os.path.join(pred_dir, f"mask_pred_patch_{tile['id']}.tif")

        if not os.path.exists(pred_path):
            print(f"Warning: Prediccion no encontrada para {tile['id']}")
            continue

        with rasterio.open(pred_path) as src:
            pred = src.read(1).astype(np.uint8)

        tx, ty = tile["x"], tile["y"]

        if margin > 0:
            valid_part = pred[margin : tile_size - margin, margin : tile_size - margin]
            y_start, x_start = ty + margin, tx + margin
        else:
            valid_part = pred
            y_start, x_start = ty, tx

        v_h, v_w = valid_part.shape
        y0, y1 = max(0, y_start), min(y_start + v_h, h)
        x0, x1 = max(0, x_start), min(x_start + v_w, w)

        if y1 > y0 and x1 > x0:
            crop_y0 = y0 - y_start
            crop_y1 = crop_y0 + (y1 - y0)
            crop_x0 = x0 - x_start
            crop_x1 = crop_x0 + (x1 - x0)

            final_valid = valid_part[crop_y0:crop_y1, crop_x0:crop_x1]
            pred_buildings = (final_valid == building_class).astype(np.uint8)

            canvas_buildings[y0:y1, x0:x1] = np.maximum(
                canvas_buildings[y0:y1, x0:x1], pred_buildings
            )

        if progress_callback:
            progress = int(((i + 1) / num_tiles) * 100)
            progress_callback(progress, "Reconstruyendo el ROI")

    transform = Affine(*meta["transform"][:6])
    os.makedirs(output_dir, exist_ok=True)
    out_path = os.path.join(output_dir, f"{tif_name}_buildings.tif")

    if progress_callback:
        progress_callback(0, "Guardando raster reconstruido...")

    with rasterio.open(
        out_path,
        "w",
        driver="GTiff",
        height=h,
        width=w,
        count=1,
        dtype="uint8",
        crs=meta["crs"],
        transform=transform,
        nodata=0,
        compress="lzw",
    ) as dst:
        dst.write(canvas_buildings, 1)

    print(f"Edificaciones guardadas en {out_path}")

    if progress_callback:
        progress_callback(100, "Guardando raster reconstruido...")
