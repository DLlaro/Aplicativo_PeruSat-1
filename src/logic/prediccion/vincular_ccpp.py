import math
import os
from typing import Callable, Optional, TypeAlias

import geopandas as gpd
import numpy as np
import pandas as pd
import rasterio
from pyproj import CRS
from rasterio.features import rasterize, shapes, sieve
from rasterio.transform import Affine
from shapely.geometry import MultiPolygon, Polygon, shape
from shapely.ops import unary_union
from shapely.strtree import STRtree

ProgressCallback: TypeAlias = Callable[[int, str], None]

UB_FIELD = "UBIGEO_CCPP_CONFIRMADO"
VORONOI_LAYER_NAME = "delimitaciones_voronoi_ccpp"


def _emit(progress_callback: Optional[ProgressCallback], value: int, msg: str) -> None:
    if progress_callback:
        progress_callback(value, msg)


def _repair_geometries(gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    out = gdf.copy()
    out = out[out.geometry.notna()].copy()
    out = out[~out.geometry.is_empty].copy()
    invalid = ~out.geometry.is_valid
    if invalid.any():
        try:
            out.loc[invalid, "geometry"] = out.loc[invalid, "geometry"].make_valid()
        except Exception:
            out.loc[invalid, "geometry"] = out.loc[invalid, "geometry"].buffer(0)
    out = out[out.geometry.notna()].copy()
    out = out[~out.geometry.is_empty].copy()
    return out


def _is_projected_meter(crs: CRS) -> bool:
    if crs is None or not crs.is_projected:
        return False
    axis_info = crs.axis_info
    if not axis_info:
        return False
    unit_name = (axis_info[0].unit_name or "").lower()
    return "metre" in unit_name or "meter" in unit_name


def _utm_from_centroid(gdf: gpd.GeoDataFrame) -> CRS:
    gdf_wgs = gdf.to_crs(epsg=4326)
    centroid = gdf_wgs.unary_union.centroid
    lon, lat = float(centroid.x), float(centroid.y)
    zone = int((lon + 180.0) // 6.0) + 1
    zone = max(1, min(zone, 60))
    epsg = 32600 + zone if lat >= 0 else 32700 + zone
    return CRS.from_epsg(epsg)


def choose_distance_crs(buildings: gpd.GeoDataFrame) -> CRS:
    if buildings.crs is None:
        raise ValueError("La capa de buildings no tiene CRS definido.")
    b_crs = CRS.from_user_input(buildings.crs)
    if _is_projected_meter(b_crs):
        return b_crs
    return _utm_from_centroid(buildings)


def _iter_polygons(geom):
    if geom is None or geom.is_empty:
        return
    if isinstance(geom, Polygon):
        yield geom
        return
    if isinstance(geom, MultiPolygon):
        for poly in geom.geoms:
            if not poly.is_empty:
                yield poly
        return
    if hasattr(geom, "geoms"):
        for subgeom in geom.geoms:
            yield from _iter_polygons(subgeom)


def _sample_boundary_points(geom, step: float = 10.0) -> list[tuple[float, float]]:
    step = max(float(step), 1.0)
    pts: list[tuple[float, float]] = []
    for poly in _iter_polygons(geom):
        ring = poly.exterior
        ring_length = ring.length
        if ring_length <= 0:
            continue
        n = max(12, int(math.ceil(ring_length / step)))
        ds = np.linspace(0, ring_length, n, endpoint=False)
        for d in ds:
            p = ring.interpolate(float(d))
            pts.append((p.x, p.y))
    return pts


def _aoi_from_valid_pixels(
    tif_path: str,
    valid_rule: str = "any_band_gt0",
    band_indexes: Optional[list[int]] = None,
    downsample: int = 4,
    simplify_tol: float = 10.0,
    min_area_px: int = 300,
) -> gpd.GeoDataFrame:
    downsample = max(1, int(downsample))

    with rasterio.open(tif_path) as src:
        if src.crs is None:
            raise ValueError("El raster de prediccion no tiene CRS.")

        if band_indexes is None:
            band_indexes = list(range(1, src.count + 1))

        out_h = max(1, int(math.ceil(src.height / downsample)))
        out_w = max(1, int(math.ceil(src.width / downsample)))

        data = src.read(
            band_indexes,
            out_shape=(len(band_indexes), out_h, out_w),
            resampling=rasterio.enums.Resampling.nearest,
        )

        scale_x = src.width / out_w
        scale_y = src.height / out_h
        transform = src.transform * Affine.scale(scale_x, scale_y)
        crs = src.crs
        nodata = src.nodata

    if valid_rule == "not_nodata" and nodata is not None:
        valid = np.any(data != nodata, axis=0)
    else:
        valid = np.any(data > 0, axis=0)

    valid = valid.astype(np.uint8)

    if min_area_px > 0:
        try:
            valid = sieve(valid, size=int(min_area_px), connectivity=8)
        except Exception:
            pass
        valid = (valid > 0).astype(np.uint8)

    geoms = [shape(geom) for geom, _ in shapes(valid, mask=(valid == 1), transform=transform)]
    if not geoms:
        raise RuntimeError("No se encontro AOI valido en el raster de prediccion.")

    aoi = unary_union(geoms).buffer(0)
    if simplify_tol > 0:
        aoi = aoi.simplify(float(simplify_tol), preserve_topology=True).buffer(0)
    if aoi.is_empty:
        raise RuntimeError("El AOI resultante quedo vacio tras simplificacion.")

    return gpd.GeoDataFrame({"id": [1]}, geometry=[aoi], crs=crs)


def _nearest_with_strtree(
    buildings_dist: gpd.GeoDataFrame,
    points_dist: gpd.GeoDataFrame,
    nearest_point_id_col: str,
) -> pd.DataFrame:
    left = buildings_dist.reset_index(drop=False).rename(columns={"index": "building_idx"})
    right = points_dist.reset_index(drop=False).rename(columns={"index": "point_row"})

    point_geoms = list(right.geometry.values)
    tree = STRtree(point_geoms)

    wkb_to_rows: dict[bytes, list[int]] = {}
    for i, geom in enumerate(point_geoms):
        wkb_to_rows.setdefault(geom.wkb, []).append(i)

    rows = []
    for _, brow in left.iterrows():
        bgeom = brow.geometry
        if bgeom is None or bgeom.is_empty:
            rows.append(
                {
                    "building_idx": brow["building_idx"],
                    "point_row": None,
                    "nearest_point_id": None,
                    "UBIGEO_CCPP": "",
                    "distance_m": np.nan,
                }
            )
            continue

        nearest_geom = tree.nearest(bgeom)
        if nearest_geom is None:
            rows.append(
                {
                    "building_idx": brow["building_idx"],
                    "point_row": None,
                    "nearest_point_id": None,
                    "UBIGEO_CCPP": "",
                    "distance_m": np.nan,
                }
            )
            continue

        candidate_pos = wkb_to_rows.get(nearest_geom.wkb, [])
        if not candidate_pos:
            rows.append(
                {
                    "building_idx": brow["building_idx"],
                    "point_row": None,
                    "nearest_point_id": None,
                    "UBIGEO_CCPP": "",
                    "distance_m": np.nan,
                }
            )
            continue

        best_pos = min(candidate_pos, key=lambda p: bgeom.distance(point_geoms[p]))
        point_row = right.iloc[best_pos]
        rows.append(
            {
                "building_idx": brow["building_idx"],
                "point_row": point_row["point_row"],
                "nearest_point_id": point_row[nearest_point_id_col],
                "UBIGEO_CCPP": point_row["UBIGEO_CCPP"],
                "distance_m": float(bgeom.distance(point_row.geometry)),
            }
        )

    return pd.DataFrame(rows)


def _nearest_with_sjoin(
    buildings_dist: gpd.GeoDataFrame,
    points_dist: gpd.GeoDataFrame,
    nearest_point_id_col: str,
) -> pd.DataFrame:
    left = buildings_dist.reset_index(drop=False).rename(columns={"index": "building_idx"})
    right = points_dist.reset_index(drop=False).rename(columns={"index": "point_row"})
    right = right[["point_row", nearest_point_id_col, "UBIGEO_CCPP", "geometry"]]

    nearest = gpd.sjoin_nearest(left, right, how="left", distance_col="distance_m")
    nearest = nearest.sort_values(["building_idx", "distance_m"], na_position="last")
    nearest = nearest.drop_duplicates(subset=["building_idx"], keep="first")

    point_geom_map = right.set_index("point_row").geometry
    nearest["pt_geom"] = nearest["point_row"].map(point_geom_map)
    nearest["distance_m"] = nearest.geometry.distance(
        gpd.GeoSeries(nearest["pt_geom"], index=nearest.index, crs=buildings_dist.crs)
    )

    nearest = nearest.rename(columns={nearest_point_id_col: "nearest_point_id"})
    return nearest[["building_idx", "point_row", "nearest_point_id", "UBIGEO_CCPP", "distance_m"]]


def _build_nearest_table(
    buildings_dist: gpd.GeoDataFrame,
    points_dist: gpd.GeoDataFrame,
    nearest_point_id_col: str,
) -> pd.DataFrame:
    try:
        return _nearest_with_sjoin(buildings_dist, points_dist, nearest_point_id_col)
    except Exception:
        return _nearest_with_strtree(buildings_dist, points_dist, nearest_point_id_col)


def _query_kdtree(tree, query: np.ndarray) -> np.ndarray:
    try:
        _, idx = tree.query(query, k=1, workers=-1)
    except TypeError:
        _, idx = tree.query(query, k=1)
    return idx


def _build_voronoi_from_dissolved(
    dissolved_dist: gpd.GeoDataFrame,
    aoi_dist: gpd.GeoDataFrame,
    ub_col: str,
    resolution_m: float = 5.0,
    seed_step_m: float = 10.0,
    progress_callback: Optional[ProgressCallback] = None,
    start_progress: int = 82,
    end_progress: int = 97,
) -> gpd.GeoDataFrame:
    try:
        from scipy.spatial import cKDTree
    except Exception as exc:
        raise RuntimeError(
            "No se pudo importar scipy.spatial.cKDTree para calcular Voronoi."
        ) from exc

    work = dissolved_dist.copy()
    work[ub_col] = work[ub_col].fillna("").astype(str).str.strip()
    work = work[work[ub_col] != "0"].copy()
    work = _repair_geometries(work)

    if work.empty:
        return gpd.GeoDataFrame(
            columns=[ub_col, "n_buildings", "geometry"],
            geometry="geometry",
            crs=dissolved_dist.crs,
        )

    aoi = unary_union(aoi_dist.geometry.values).buffer(0)
    if aoi.is_empty:
        raise RuntimeError("El AOI para Voronoi es vacio.")

    sampling_end = start_progress + max(1, (end_progress - start_progress) // 2)
    query_end = end_progress - 1

    seed_xy_list: list[tuple[float, float]] = []
    seed_code_list: list[int] = []
    label_to_code: dict[str, int] = {}

    total = len(work)
    update_every = max(1, total // 20)
    for i, row in enumerate(work.itertuples(index=False), start=1):
        label = str(getattr(row, ub_col))
        pts = _sample_boundary_points(row.geometry, step=seed_step_m)
        if pts:
            code = label_to_code.setdefault(label, len(label_to_code) + 1)
            seed_xy_list.extend(pts)
            seed_code_list.extend([code] * len(pts))

        if progress_callback and (i == 1 or i == total or i % update_every == 0):
            pct = start_progress + int(round((sampling_end - start_progress) * (i / total)))
            progress_callback(pct, f"Muestreando bordes CCPP ({i}/{total})...")

    if not seed_xy_list:
        return gpd.GeoDataFrame(
            columns=[ub_col, "n_buildings", "geometry"],
            geometry="geometry",
            crs=dissolved_dist.crs,
        )

    seed_xy = np.asarray(seed_xy_list, dtype=np.float32)
    seed_code = np.asarray(seed_code_list, dtype=np.int32)
    code_to_label = {v: k for k, v in label_to_code.items()}

    tree = cKDTree(seed_xy)
    _emit(progress_callback, sampling_end, "Rasterizando AOI para Voronoi...")

    resolution_m = float(resolution_m)
    if resolution_m <= 0:
        raise ValueError("La resolucion de Voronoi debe ser mayor a cero.")

    minx, miny, maxx, maxy = aoi.bounds
    width = max(1, int(math.ceil((maxx - minx) / resolution_m)))
    height = max(1, int(math.ceil((maxy - miny) / resolution_m)))

    max_grid_pixels = 25_000_000
    grid_pixels = width * height
    if grid_pixels > max_grid_pixels:
        scale = math.sqrt(grid_pixels / max_grid_pixels)
        resolution_m *= scale
        width = max(1, int(math.ceil((maxx - minx) / resolution_m)))
        height = max(1, int(math.ceil((maxy - miny) / resolution_m)))
        _emit(
            progress_callback,
            sampling_end,
            f"AOI grande; resolucion Voronoi ajustada a {resolution_m:.2f} m.",
        )

    transform = rasterio.transform.from_origin(minx, maxy, resolution_m, resolution_m)
    aoi_mask = rasterize(
        [(aoi, 1)],
        out_shape=(height, width),
        transform=transform,
        fill=0,
        dtype=np.uint8,
    )
    ys, xs = np.where(aoi_mask == 1)
    if xs.size == 0:
        raise RuntimeError("No hay pixeles validos dentro del AOI para Voronoi.")

    label_raster = np.zeros((height, width), dtype=np.int32)
    chunk_size = 250_000
    total_chunks = int(math.ceil(xs.size / chunk_size))

    for chunk_idx in range(total_chunks):
        i0 = chunk_idx * chunk_size
        i1 = min((chunk_idx + 1) * chunk_size, xs.size)

        xs_chunk = xs[i0:i1]
        ys_chunk = ys[i0:i1]
        qx = minx + (xs_chunk + 0.5) * resolution_m
        qy = maxy - (ys_chunk + 0.5) * resolution_m
        query = np.column_stack((qx, qy)).astype(np.float32)

        nearest_idx = _query_kdtree(tree, query)
        label_raster[ys_chunk, xs_chunk] = seed_code[nearest_idx]

        if progress_callback:
            pct = sampling_end + int(round((query_end - sampling_end) * ((chunk_idx + 1) / total_chunks)))
            progress_callback(
                pct,
                f"Asignando celdas Voronoi ({chunk_idx + 1}/{total_chunks})...",
            )

    _emit(progress_callback, end_progress, "Vectorizando delimitaciones Voronoi...")

    geoms = []
    values = []
    for geom, val in shapes(label_raster, mask=(label_raster > 0), transform=transform):
        geoms.append(shape(geom))
        values.append(int(val))

    if not geoms:
        return gpd.GeoDataFrame(
            columns=[ub_col, "n_buildings", "geometry"],
            geometry="geometry",
            crs=dissolved_dist.crs,
        )

    out = gpd.GeoDataFrame({"code": values, "geometry": geoms}, crs=dissolved_dist.crs)
    out[ub_col] = out["code"].map(code_to_label)
    out = out.drop(columns=["code"]).dissolve(by=ub_col, as_index=False)
    out = _repair_geometries(out)

    if "n_buildings" in work.columns:
        counts = work[[ub_col, "n_buildings"]].drop_duplicates(subset=[ub_col])
        out = out.merge(counts, on=ub_col, how="left")

    return out


def link_buildings_to_ccpp(
    buildings_path: str,
    ccpp_points_path: str,
    output_dir: str,
    distance_threshold_m: float = 146.5,
    prediction_raster_path: Optional[str] = None,
    progress_callback: Optional[ProgressCallback] = None,
) -> dict:
    _emit(progress_callback, 0, "Leyendo capas...")
    buildings = gpd.read_file(buildings_path)
    points = gpd.read_file(ccpp_points_path)

    if buildings.empty:
        raise ValueError("La capa de buildings esta vacia.")
    if points.empty:
        raise ValueError("La capa de centros poblados esta vacia.")
    if buildings.crs is None:
        raise ValueError("La capa de buildings no tiene CRS.")
    if points.crs is None:
        raise ValueError("La capa de centros poblados no tiene CRS.")
    if "UBIGEO" not in points.columns or "CODCCPP" not in points.columns:
        raise ValueError("La capa de centros poblados debe incluir UBIGEO y CODCCPP.")

    _emit(progress_callback, 10, "Validando y reparando geometrias...")
    buildings = _repair_geometries(buildings)
    points = _repair_geometries(points)
    points = points[points.geometry.geom_type == "Point"].copy()
    if buildings.empty:
        raise ValueError("No hay geometrias validas en buildings tras la limpieza.")
    if points.empty:
        raise ValueError("No hay puntos validos en centros poblados tras la limpieza.")

    points["UBIGEO_CCPP"] = (
        points["UBIGEO"].fillna("").astype(str).str.strip()
        + points["CODCCPP"].fillna("").astype(str).str.strip()
    )

    if "ID" in points.columns:
        nearest_point_id_col = "ID"
    elif "id" in points.columns:
        nearest_point_id_col = "id"
    else:
        points = points.reset_index(drop=False).rename(columns={"index": "point_idx"})
        nearest_point_id_col = "point_idx"

    _emit(progress_callback, 20, "Determinando CRS de distancias...")
    distance_crs = choose_distance_crs(buildings)

    _emit(progress_callback, 30, "Reproyectando capas para distancias en metros...")
    buildings_dist = buildings.to_crs(distance_crs)
    points_dist = points.to_crs(distance_crs)

    _emit(progress_callback, 45, "Buscando punto mas cercano por poligono...")
    nearest = _build_nearest_table(buildings_dist, points_dist, nearest_point_id_col)

    _emit(progress_callback, 65, "Uniendo atributos de vinculacion...")
    nearest = nearest[["building_idx", "nearest_point_id", "UBIGEO_CCPP", "distance_m"]]

    buildings_out = buildings.reset_index(drop=False).rename(columns={"index": "building_idx"})
    buildings_out = buildings_out.merge(nearest, on="building_idx", how="left")
    buildings_out["UBIGEO_CCPP"] = buildings_out["UBIGEO_CCPP"].fillna("")
    buildings_out["distance_m"] = buildings_out["distance_m"].astype(float)
    buildings_out[UB_FIELD] = np.where(
        (buildings_out["distance_m"].notna()) & (buildings_out["distance_m"] <= distance_threshold_m),
        buildings_out["UBIGEO_CCPP"],
        "0",
    )
    buildings_out = gpd.GeoDataFrame(
        buildings_out.drop(columns=["building_idx"]),
        geometry="geometry",
        crs=buildings.crs,
    )

    _emit(progress_callback, 78, "Disolviendo por UBIGEO_CCPP_CONFIRMADO...")
    dissolved = (
        buildings_out[[UB_FIELD, "geometry"]]
        .dissolve(by=UB_FIELD, as_index=False)
    )
    counts = (
        buildings_out.groupby(UB_FIELD)
        .size()
        .rename("n_buildings")
        .reset_index()
    )
    dissolved = dissolved.merge(counts, on=UB_FIELD, how="left")

    voronoi = gpd.GeoDataFrame(columns=[UB_FIELD, "n_buildings", "geometry"], geometry="geometry", crs=buildings.crs)
    if prediction_raster_path:
        if not os.path.exists(prediction_raster_path):
            raise FileNotFoundError(f"No se encontro raster de prediccion: {prediction_raster_path}")

        _emit(progress_callback, 82, "Construyendo AOI desde pixeles validos...")
        aoi_gdf = _aoi_from_valid_pixels(
            prediction_raster_path,
            valid_rule="any_band_gt0",
            downsample=4,
            simplify_tol=10.0,
            min_area_px=300,
        )

        _emit(progress_callback, 85, "Calculando delimitaciones Voronoi por CCPP...")
        dissolved_dist = dissolved.to_crs(distance_crs)
        aoi_dist = aoi_gdf.to_crs(distance_crs)
        voronoi_dist = _build_voronoi_from_dissolved(
            dissolved_dist=dissolved_dist,
            aoi_dist=aoi_dist,
            ub_col=UB_FIELD,
            resolution_m=5.0,
            seed_step_m=10.0,
            progress_callback=progress_callback,
            start_progress=86,
            end_progress=97,
        )
        if not voronoi_dist.empty:
            voronoi = voronoi_dist.to_crs(buildings.crs)
    else:
        _emit(progress_callback, 90, "Raster de prediccion no disponible; Voronoi omitido.")

    _emit(progress_callback, 98, "Exportando resultados...")
    os.makedirs(output_dir, exist_ok=True)
    output_gpkg = os.path.join(output_dir, "vinculacion_ccpp.gpkg")
    if os.path.exists(output_gpkg):
        os.remove(output_gpkg)

    buildings_out.to_file(output_gpkg, layer="buildings_vinculados", driver="GPKG")
    dissolved.to_file(output_gpkg, layer="ccpp_disueltos", driver="GPKG")
    voronoi.to_file(output_gpkg, layer=VORONOI_LAYER_NAME, driver="GPKG")

    _emit(progress_callback, 100, "Vinculacion completada.")
    return {
        "output_gpkg": output_gpkg,
        "buildings_layer": "buildings_vinculados",
        "dissolved_layer": "ccpp_disueltos",
        "voronoi_layer": VORONOI_LAYER_NAME,
        "distance_crs": str(distance_crs),
        "distance_threshold_m": float(distance_threshold_m),
    }
