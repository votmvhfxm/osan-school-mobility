"""오산시 공동주택 단지 수집기.

국토교통부 공동주택 기본정보 API의 활용 승인이 된 DATA_GO_KR_KEY를 사용한다.
API 미승인 상태에서는 추정 단지를 만들지 않고 명시적으로 실패한다.
"""
import json
import os
import ssl
import time
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import urlopen

import pandas as pd
import requests

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
RAW = DATA / "raw"


def load_env():
    values = dict(os.environ)
    env = ROOT / ".env"
    if env.exists():
        for line in env.read_text(encoding="utf-8").splitlines():
            if line.strip() and not line.lstrip().startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                values.setdefault(key.strip(), value.strip())
    return values


ENV = load_env()
KEY = ENV.get("DATA_GO_KR_KEY", "")
VWORLD_KEY = ENV.get("VWORLD_API_KEY", "")

# The current K-APT list service is version 4. The older AptListService
# endpoint returns NO_OPENAPI_SERVICE_ERROR even when the data product is approved.
API = "https://apis.data.go.kr/1613000/AptListService4/getSigunguAptList4"
DETAIL_API = "https://apis.data.go.kr/1613000/AptBasisInfoServiceV5/getAphusBassInfoV5"
GEOCODE_API = "https://api.vworld.kr/req/address"


def geocode(address):
    if not VWORLD_KEY or not address:
        return None
    response = requests.get(
        GEOCODE_API,
        params={
            "service": "address", "request": "getcoord", "version": "2.0",
            "crs": "epsg:4326", "address": address, "refine": "true",
            "simple": "false", "format": "json", "type": "road", "key": VWORLD_KEY,
        },
        timeout=20,
    ).json().get("response", {})
    point = response.get("result", {}).get("point", {})
    try:
        return float(point["y"]), float(point["x"])
    except (KeyError, TypeError, ValueError):
        return None


def main():
    if not KEY:
        raise SystemExit(".env에 DATA_GO_KR_KEY가 없습니다.")
    body = None
    for page in range(1, 11):
        query = urlencode({
            "serviceKey": KEY, "sigunguCode": "41370", "numOfRows": "1000",
            "pageNo": str(page), "_type": "json",
        })
        with urlopen(f"{API}?{query}", timeout=30, context=ssl._create_unverified_context()) as response:
            current = json.loads(response.read().decode("utf-8"))
        if "OpenAPI_ServiceResponse" in current:
            raise RuntimeError("공동주택 단지 목록 API가 승인되지 않았거나 서비스키 권한이 갱신되지 않았습니다.")
        items = current.get("response", {}).get("body", {}).get("items", [])
        if isinstance(items, dict):
            items = [items]
        if body is None:
            body = current
            body.setdefault("response", {}).setdefault("body", {})["items"] = []
        body["response"]["body"]["items"].extend(items)
        if len(items) < 1000:
            break
    (RAW / "apartments_osan.json").write_text(json.dumps(body, ensure_ascii=False, indent=2), encoding="utf-8")

    items = body["response"]["body"]["items"]
    details, complexes = [], []
    for i, item in enumerate(items, start=1):
        query = urlencode({"serviceKey": KEY, "kaptCode": item["kaptCode"], "_type": "json"})
        with urlopen(f"{DETAIL_API}?{query}", timeout=30, context=ssl._create_unverified_context()) as response:
            detail_body = json.loads(response.read().decode("utf-8"))
        detail = detail_body.get("response", {}).get("body", {}).get("item") or {}
        details.append(detail)
        address = detail.get("doroJuso") or detail.get("kaptAddr")
        coords = geocode(address)
        if coords:
            complexes.append({
                "complex_id": item["kaptCode"],
                "name": detail.get("kaptName") or item.get("kaptName"),
                "block": "",
                "address": address,
                "lat": coords[0],
                "lon": coords[1],
                "households": detail.get("kaptdaCnt") or detail.get("hoCnt"),
                "move_in": detail.get("kaptUsedate"),
                "zone": "오산시",
                "coord_source": "vworld",
                "source_url": "https://www.data.go.kr/data/15058453/openapi.do",
            })
        print(f"{i}/{len(items)} {item.get('kaptName')} {'좌표완료' if coords else '좌표없음'}", flush=True)
        time.sleep(0.1)

    (RAW / "apartments_osan_details.json").write_text(
        json.dumps(details, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    pd.DataFrame(complexes).to_csv(DATA / "complexes.csv", index=False, encoding="utf-8-sig")
    print(f"Saved {len(complexes)}/{len(items)} apartment complexes to data/complexes.csv.")


if __name__ == "__main__":
    main()
