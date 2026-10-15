"""간선(edge) 단위 피처 생성.
입력: data/raw/osm_walk.graphml (+ 있으면 crosswalk.json, child_safe_zone.json, taas_frequentzone.json)
출력: data/edges.gpkg  (layer=edges, EPSG:5186)
"""
import json

import geopandas as gpd
import numpy as np
import osmnx as ox
import pandas as pd
from shapely.geometry import Point, shape

from common import CRS_LL, CRS_M, DATA, RAW

HW_RANK = {  # 차량 위계 (높을수록 차량 통행 많고 빠름)
    "trunk": 5, "trunk_link": 5, "primary": 4, "primary_link": 4,
    "secondary": 3, "secondary_link": 3, "tertiary": 2.5, "tertiary_link": 2.5,
    "unclassified": 1.5, "residential": 1, "living_street": 0.5, "service": 1,
    "footway": 0, "pedestrian": 0, "path": 0, "steps": 0, "cycleway": 0, "track": 0.5,
}
PED_ONLY = {"footway", "pedestrian", "path", "steps", "cycleway", "corridor"}


def first(v):
    if isinstance(v, list):
        return v[0]
    if isinstance(v, str) and v.startswith("["):
        return v.strip("[]").split(",")[0].strip(" '\"")
    return v


def num(v):
    try:
        return float(str(first(v)).split()[0])
    except (TypeError, ValueError):
        return np.nan


def load_points(fname, lat="latitude", lon="longitude"):
    f = RAW / fname
    if not f.exists():
        return None
    rows = json.loads(f.read_text(encoding="utf-8"))
    df = pd.DataFrame(rows)
    df[lat] = pd.to_numeric(df[lat], errors="coerce")
    df[lon] = pd.to_numeric(df[lon], errors="coerce")
    df = df.dropna(subset=[lat, lon])
    return gpd.GeoDataFrame(df, geometry=gpd.points_from_xy(df[lon], df[lat]), crs=CRS_LL).to_crs(CRS_M)


def load_hotspots():
    """TAAS 사고다발지역 → 점(중심) + 폴리곤, 사고건수."""
    f = RAW / "taas_frequentzone.json"
    if not f.exists():
        return None
    recs = []
    for kind, items in json.loads(f.read_text(encoding="utf-8")).items():
        for it in items:
            try:
                geom = shape(json.loads(it["geom_json"])) if it.get("geom_json") else Point(float(it["lo_crd"]), float(it["la_crd"]))
            except Exception:  # noqa: BLE001
                continue
            recs.append({"kind": kind, "year": it.get("_year"), "spot": it.get("spot_nm"),
                         "occ": int(it.get("occrrnc_cnt", 1) or 1), "geometry": geom})
    if not recs:
        return None
    return gpd.GeoDataFrame(recs, crs=CRS_LL).to_crs(CRS_M)


def count_near(edges, pts, radius, weight=None):
    if pts is None or len(pts) == 0:
        return pd.Series(0, index=edges.index, dtype=float)
    buf = edges[["geometry"]].copy()
    buf["geometry"] = buf.buffer(radius)
    j = gpd.sjoin(buf, pts, predicate="intersects", how="inner")
    if weight:
        return j.groupby(level=0)[weight].sum().reindex(edges.index, fill_value=0).astype(float)
    return j.groupby(level=0).size().reindex(edges.index, fill_value=0).astype(float)


def main():
    G = ox.load_graphml(RAW / "osm_walk.graphml")
    nodes, edges = ox.graph_to_gdfs(G)
    edges = edges.reset_index()  # u, v, key
    edges = edges.to_crs(CRS_M)
    nodes_m = nodes.to_crs(CRS_M)

    hw = edges["highway"].map(first)
    edges["hw"] = hw
    edges["hw_rank"] = hw.map(HW_RANK).fillna(1.0)
    edges["ped_only"] = hw.isin(PED_ONLY).astype(int)
    edges["major_road"] = hw.isin({"trunk", "trunk_link", "primary", "primary_link"}).astype(int)
    edges["lanes_n"] = edges["lanes"].map(num) if "lanes" in edges else np.nan
    edges["maxspeed_n"] = edges["maxspeed"].map(num) if "maxspeed" in edges else np.nan
    # 차선 정보 결측은 도로 등급별 중앙값으로 보간
    edges["lanes_n"] = edges["lanes_n"].fillna(edges.groupby("hw")["lanes_n"].transform("median")).fillna(1)
    edges["length_m"] = edges["length"].astype(float)
    edges["is_crossing_edge"] = (edges.get("footway").map(first) == "crossing").astype(int) if "footway" in edges else 0

    # 교차로 수: 간선 양 끝 노드 중 3갈래 이상
    deg = nodes["street_count"].astype(float)
    edges["n_intersections"] = (edges["u"].map(deg).fillna(0) >= 3).astype(int) + (edges["v"].map(deg).fillna(0) >= 3).astype(int)

    # 횡단보도: 공공데이터 우선, 없으면 OSM crossing 노드
    cw = load_points("crosswalk.json")
    if cw is not None and len(cw):
        cw["signal"] = (cw.get("tfclghtYn", "N").astype(str).str.upper() == "Y").astype(int)
        src = "public"
    else:
        osm_cw = nodes_m[(nodes_m["highway"].astype(str) == "crossing") | nodes_m["crossing"].notna()].copy()
        osm_cw["signal"] = (osm_cw["crossing"].astype(str).str.contains("traffic_signals")
                            | osm_cw["traffic_signals"].notna()).astype(int)
        cw = osm_cw[["signal", "geometry"]]
        src = "osm"
    edges["n_crossings"] = count_near(edges, cw, 15)
    edges["n_signal_crossings"] = count_near(edges, cw, 15, weight="signal")
    edges["signal_ratio"] = np.where(edges["n_crossings"] > 0, edges["n_signal_crossings"] / edges["n_crossings"].clip(lower=1), np.nan)
    edges["n_unsignal_crossings"] = edges["n_crossings"] - edges["n_signal_crossings"]

    # 어린이보호구역: 지정 시설 좌표 반경 300m (도로교통법상 주출입문 기준 300m 이내 지정 가능)
    zones = load_points("child_safe_zone.json")
    edges["in_school_zone"] = (count_near(edges, zones, 300) > 0).astype(int)

    # 사고다발지역: 반경 30m 라벨 / 반경 50m 건수
    hs = load_hotspots()
    edges["acc_label"] = (count_near(edges, hs, 30) > 0).astype(int)
    edges["acc_count_50m"] = count_near(edges, hs, 50, weight="occ") if hs is not None else 0.0

    keep = ["u", "v", "key", "osmid", "name", "hw", "hw_rank", "ped_only", "major_road", "lanes_n", "maxspeed_n",
            "length_m", "is_crossing_edge", "n_intersections", "n_crossings", "n_signal_crossings",
            "n_unsignal_crossings", "signal_ratio", "in_school_zone", "acc_label", "acc_count_50m", "geometry"]
    out = edges[[c for c in keep if c in edges]].copy()
    for c in ("osmid", "name"):
        out[c] = out[c].map(lambda v: ",".join(map(str, v)) if isinstance(v, list) else (None if pd.isna(v) else str(v)))
    out.to_file(DATA / "edges.gpkg", layer="edges", driver="GPKG")
    print(f"edges={len(out)} crossing_src={src} crossings={len(cw)} zones={0 if zones is None else len(zones)} "
          f"hotspots={0 if hs is None else len(hs)} acc_label_pos={int(out.acc_label.sum())}")


if __name__ == "__main__":
    main()
