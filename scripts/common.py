"""공통 경로·환경변수 로더."""
from pathlib import Path
import os

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
RAW = DATA / "raw"
FIELD = DATA / "field"
MODEL = ROOT / "model"
CACHE = ROOT / "cache"
for p in (RAW, FIELD, MODEL, CACHE):
    p.mkdir(parents=True, exist_ok=True)

# 미터 단위 계산용 투영 좌표계 (Korea 2000 / Central Belt 2010)
CRS_M = "EPSG:5186"
CRS_LL = "EPSG:4326"


def load_env():
    """Use the same BOM/quote-safe loader as the apartment collector."""
    from fetch_apartments import load_env as read_env
    env = read_env()
    for key in ("NAVER_MAP_CLIENT_ID", "NAVER_MAP_CLIENT_SECRET", "DATA_GO_KR_KEY",
                "KOROAD_API_KEY", "SCHOOLINFO_API_KEY", "VWORLD_API_KEY",
                "TMAP_APP_KEY", "ODSAY_API_KEY"):
        env.setdefault(key, "")
    return env
