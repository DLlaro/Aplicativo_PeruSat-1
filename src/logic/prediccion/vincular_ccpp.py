import os
from typing import Callable, Optional, TypeAlias

import geopandas as gpd
import numpy as np
import pandas as pd
from pyproj import CRS
from shapely.strtree import STRtree

ProgressCallback: TypeAlias = Callable[[int, str], None]


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

    # Puede devolver empates; nos quedamos con el de distancia minima por building.
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


def link_buildings_to_ccpp(
    buildings_path: str,
    ccpp_points_path: str,
    output_dir: str,
    distance_threshold_m: float = 146.5,
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
    buildings_out["UBIGEO_CCPP_CONFIRMADO"] = np.where(
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
        buildings_out[["UBIGEO_CCPP_CONFIRMADO", "geometry"]]
        .dissolve(by="UBIGEO_CCPP_CONFIRMADO", as_index=False)
    )
    counts = (
        buildings_out.groupby("UBIGEO_CCPP_CONFIRMADO")
        .size()
        .rename("n_buildings")
        .reset_index()
    )
    dissolved = dissolved.merge(counts, on="UBIGEO_CCPP_CONFIRMADO", how="left")

    _emit(progress_callback, 88, "Exportando resultados...")
    os.makedirs(output_dir, exist_ok=True)
    output_gpkg = os.path.join(output_dir, "vinculacion_ccpp.gpkg")
    if os.path.exists(output_gpkg):
        os.remove(output_gpkg)

    buildings_out.to_file(output_gpkg, layer="buildings_vinculados", driver="GPKG")
    dissolved.to_file(output_gpkg, layer="ccpp_disueltos", driver="GPKG")
    dissolved.to_crs(distance_crs).to_file(
        output_gpkg,
        layer="ccpp_disueltos_dist_m",
        driver="GPKG",
    )

    _emit(progress_callback, 100, "Vinculacion completada.")
    return {
        "output_gpkg": output_gpkg,
        "buildings_layer": "buildings_vinculados",
        "dissolved_layer": "ccpp_disueltos",
        "dissolved_layer_distance": "ccpp_disueltos_dist_m",
        "distance_crs": str(distance_crs),
        "distance_threshold_m": float(distance_threshold_m),
    }
