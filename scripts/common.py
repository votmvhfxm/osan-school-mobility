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
    env = {}
    f = ROOT / ".env"
    if f.exists():
        for line in f.read_text(encoding="utf-8").splitlines():
            line = line.split("#", 1)[0].strip()
            if "=" in line:
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip()
    for k in ("NAVER_MAP_CLIENT_ID", "NAVER_MAP_CLIENT_SECRET", "DATA_GO_KR_KEY", "KOROAD_API_KEY", "TMAP_APP_KEY", "ODSAY_API_KEY"):
        env.setdefault(k, os.environ.get(k, ""))
    return env
