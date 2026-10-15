"""OSM 보행 도로망 추출 (오산시 전역). 키 불필요.
출력: data/raw/osm_walk.graphml, data/raw/osm_edges.geojson
"""
from pathlib import Path
import osmnx as ox

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
RAW.mkdir(parents=True, exist_ok=True)

ox.settings.useful_tags_way = list(set(ox.settings.useful_tags_way + [
    "sidewalk", "sidewalk:left", "sidewalk:right", "sidewalk:both",
    "footway", "crossing", "maxspeed", "lanes", "lit",
]))
ox.settings.useful_tags_node = list(set(ox.settings.useful_tags_node + [
    "crossing", "crossing:signals", "traffic_signals",
]))

PLACE = "Osan-si, Gyeonggi-do, South Korea"
# 오산시 경계 조회 실패 시 사용할 bbox (left, bottom, right, top)
BBOX = (127.00, 37.12, 127.11, 37.22)

try:
    G = ox.graph_from_place(PLACE, network_type="walk", simplify=True)
    src = PLACE
except Exception as e:  # noqa: BLE001
    print("place 조회 실패, bbox로 대체:", e)
    G = ox.graph_from_bbox(BBOX, network_type="walk", simplify=True)
    src = f"bbox {BBOX}"

ox.save_graphml(G, RAW / "osm_walk.graphml")
nodes, edges = ox.graph_to_gdfs(G)
for col in edges.columns:
    if edges[col].dtype == object:
        edges[col] = edges[col].apply(lambda v: ",".join(map(str, v)) if isinstance(v, list) else v)
edges.reset_index().to_file(RAW / "osm_edges.geojson", driver="GeoJSON")
print(f"source={src} nodes={len(nodes)} edges={len(edges)}")
print("highway top:", edges["highway"].value_counts().head(8).to_dict())
