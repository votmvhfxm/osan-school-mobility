"""학교알리미 학교 기본정보를 오산시 초·중학교로 저장한다.

학교알리미 코드: 경기도 41, 오산시 41370, 초등 02, 중등 03.
인증키는 루트 .env의 SCHOOLINFO_API_KEY에서만 읽는다.
"""
import csv
import json
import os
import ssl
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
RAW = DATA / "raw"
KEY = os.getenv("SCHOOLINFO_API_KEY", "")
if not KEY and (ROOT / ".env").exists():
    for line in (ROOT / ".env").read_text(encoding="utf-8").splitlines():
        if line.startswith("SCHOOLINFO_API_KEY="):
            KEY = line.split("=", 1)[1].strip()

API = "http://www.schoolinfo.go.kr/openApi.do"
LEVELS = {"02": "초등학교", "03": "중학교"}
FIELDS = ["school_id", "name", "school_level", "address", "lat", "lon", "classes", "students", "opened", "coord_source", "stats_source"]


def fetch(level):
    query = urlencode({"apiKey": KEY, "apiType": "0", "sidoCode": "41", "sggCode": "41370", "schulKndCode": level})
    with urlopen(f"{API}?{query}", timeout=30, context=ssl._create_unverified_context()) as response:
        body = json.loads(response.read().decode("utf-8"))
    if body.get("resultCode") != "success":
        raise RuntimeError(f"학교알리미 {LEVELS[level]} 응답 오류: {body.get('resultMsg', 'unknown')}")
    return body.get("list", [])


def main():
    if not KEY:
        raise SystemExit(".env에 SCHOOLINFO_API_KEY가 없습니다.")
    rows = []
    for level, label in LEVELS.items():
        for item in fetch(level):
            if item.get("CLOSE_YN") == "Y" or item.get("SCHUL_KND_SC_CODE") != level:
                continue
            lat, lon = item.get("LTTUD"), item.get("LGTUD")
            if lat is None or lon is None:
                continue
            rows.append({
                "school_id": item["SCHUL_CODE"],
                "name": item["SCHUL_NM"],
                "school_level": label,
                "address": f"{item.get('SCHUL_RDNMA', '')} {item.get('SCHUL_RDNDA', '')}".strip(),
                "lat": lat, "lon": lon, "classes": None, "students": None,
                "opened": item.get("FOND_YMD", ""),
                "coord_source": "schoolinfo", "stats_source": "schoolinfo",
            })
    RAW.mkdir(parents=True, exist_ok=True)
    (RAW / "schoolinfo_osan.json").write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    with (DATA / "schools.csv").open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    print(f"saved {len(rows)} schools: {sum(r['school_level'] == '초등학교' for r in rows)} elementary, "
          f"{sum(r['school_level'] == '중학교' for r in rows)} middle")


if __name__ == "__main__":
    main()
