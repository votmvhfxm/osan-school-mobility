"""경기버스정보(GBIS) 수집 (DATA_GO_KR_KEY 필요).
단지·학교 주변 정류장 → 경유 노선 → 노선 정류장 순서·첨두 배차간격.
출력: data/raw/bus.json
"""
import json
import sys
import time
import xml.etree.ElementTree as ET
from hashlib import sha256

import pandas as pd
import requests

from common import DATA, RAW, load_env

KEY = load_env()["DATA_GO_KR_KEY"]
BASE = "https://apis.data.go.kr/6410000"
TARGET_CITY = "오산"
CACHE_FILE = RAW / "bus_api_cache.json"
REQUEST_GAP = 0.35
CACHE_TTL_SECONDS = 24 * 60 * 60
FAILURES = []
FAILURE_STREAK = 0
SESSION = requests.Session()
PERMANENT_CODES = {'20', '21', '22', '30', '31', '32', '33'}


def load_cache():
    try:
        return json.loads(CACHE_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def cache_key(path, params):
    encoded = json.dumps([path, sorted(params.items())], ensure_ascii=False, separators=(",", ":"))
    return sha256(encoded.encode("utf-8")).hexdigest()


API_CACHE = load_cache()


def save_cache():
    temporary = CACHE_FILE.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(API_CACHE, ensure_ascii=False, indent=1), encoding="utf-8")
    temporary.replace(CACHE_FILE)


def call(path, **params):
    global FAILURE_STREAK
    key = cache_key(path, params)
    cached = API_CACHE.get(key)
    if isinstance(cached, dict) and "fetched_at" in cached and time.time() - cached["fetched_at"] < CACHE_TTL_SECONDS:
        FAILURE_STREAK = 0
        return cached["body"]
    for i in range(4):
        try:
            r = SESSION.get(f"{BASE}/{path}", params={"serviceKey": KEY, "format": "json", **params}, timeout=12)
            if r.status_code in (401, 403):
                raise SystemExit("Bus API authorization denied; verify repository DATA_GO_KR_KEY and service approvals. Published data preserved.")
            if r.status_code == 429:
                delay = 3 * (i + 1)
                print(f"  rate limited {path}; retrying in {delay}s", flush=True)
                time.sleep(delay)
                continue
            r.raise_for_status()
            try:
                payload = r.json()
            except ValueError:
                try:
                    xml = ET.fromstring(r.content)
                    code = xml.findtext(".//returnReasonCode") or xml.findtext(".//resultCode")
                except ET.ParseError:
                    code = None
                if str(code) in PERMANENT_CODES:
                    raise SystemExit("Bus API permanent gateway error code " + str(code) + "; published data preserved.")
                raise ValueError("Invalid bus API response") from None
            gateway = payload.get("OpenAPI_ServiceResponse", {}).get("cmmMsgHeader", {})
            code = str(gateway.get("returnReasonCode", ""))
            if code in PERMANENT_CODES:
                raise SystemExit("Bus API permanent gateway error code " + code + "; published data preserved.")
            response = payload.get("response", {})
            if "msgHeader" in response and response["msgHeader"].get("resultCode") not in (0, "0", None):
                if str(response["msgHeader"].get("resultCode")) == "4":
                    FAILURE_STREAK = 0
                    return {}
                code = str(response["msgHeader"].get("resultCode"))
                if code in PERMANENT_CODES:
                    raise SystemExit("Bus API permanent error code " + code + "; published data preserved.")
                FAILURE_STREAK += 1
                if FAILURE_STREAK >= 3:
                    raise SystemExit("Three consecutive bus API failures; published data preserved.")
                FAILURES.append({"path": path, "code": code})
                print("  API unavailable", path, "code", response["msgHeader"].get("resultCode"), flush=True)
                return None
            FAILURE_STREAK = 0
            body = response.get("msgBody") or {}
            if body:
                API_CACHE[key] = {"fetched_at": time.time(), "body": body}
                save_cache()
            time.sleep(REQUEST_GAP)
            return body
        except Exception as e:  # noqa: BLE001
            print("  err", path, type(e).__name__)
            sys.stdout.flush()
            time.sleep(1 + i)
    FAILURE_STREAK += 1
    if FAILURE_STREAK >= 3:
        raise SystemExit("Three consecutive bus API failures; published data preserved.")
    FAILURES.append({"path": path, "code": "request_failed"})
    return None


def as_list(x):
    return x if isinstance(x, list) else ([x] if x else [])


def main():
    previous = {}
    try:
        previous = json.loads((RAW / "bus.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        pass
    pts = pd.concat([
        pd.read_csv(DATA / "complexes.csv").assign(kind="complex", pid=lambda d: d.complex_id),
        pd.read_csv(DATA / "schools.csv").assign(kind="school", pid=lambda d: d.school_id),
    ])
    stops, near = {}, {}
    for _, p in pts.iterrows():
        body = call("busstationservice/v2/getBusStationAroundListv2", x=p.lon, y=p.lat)
        if body is None:
            near[p.pid] = previous.get("near", {}).get(str(p.pid), [])
            for sid in near[p.pid]:
                if sid in previous.get("stops", {}):
                    stops[sid] = previous["stops"][sid]
            print(p.pid, "주변 정류장 조회 실패 · 기존 캐시 유지", flush=True)
            continue
        lst = as_list(body.get("busStationAroundList"))
        near[p.pid] = [s["stationId"] for s in lst]
        for s in lst:
            stops[str(s["stationId"])] = s
        print(p.pid, "주변 정류장", len(lst), flush=True)

    routes = {}
    for sid in list(stops):
        body = call("busstationservice/v2/getBusStationViaRouteListv2", stationId=sid)
        if body is None:
            continue
        for rt in as_list(body.get("busRouteList")):
            routes.setdefault(str(rt["routeId"]), {"name": rt.get("routeName"), "type": rt.get("routeTypeName")})

    for rid, rt in routes.items():
        detail = call("busrouteservice/v2/getBusRouteInfoItemv2", routeId=rid)
        info = (detail or {}).get("busRouteInfoItem") or {}
        if not info:
            # Station lookup may be approved while route-detail lookup is not.
            # Keep station data and report the partial state instead of looping.
            continue
        rt["peekAlloc"] = info.get("peekAlloc")      # 첨두 배차(분)
        rt["nPeekAlloc"] = info.get("nPeekAlloc")    # 비첨두 배차(분)
        rt["upFirstTime"] = info.get("upFirstTime")
        station_body = call("busrouteservice/v2/getBusRouteStationListv2", routeId=rid)
        seq = as_list((station_body or {}).get("busRouteStationList"))
        if not seq:
            continue
        line_body = call("busrouteservice/v2/getBusRouteLineListv2", routeId=rid)
        line = as_list((line_body or {}).get("busRouteLineList"))
        try:
            shape = [[float(p["y"]), float(p["x"])] for p in sorted(line, key=lambda p: int(p["lineSeq"]))]
            if len(shape) >= 2 and all(33 < p[0] < 39 and 124 < p[1] < 132 for p in shape):
                rt["shape"] = shape
                rt["shape_source"] = "gbis_route_line"
        except (ValueError, TypeError, KeyError):
            FAILURES.append({"path": "route_geometry", "code": "invalid_coordinates"})
        rt["stations"] = [{"stationId": str(s["stationId"]), "seq": int(s["stationSeq"]),
                           "name": s.get("stationName"), "x": s.get("x"), "y": s.get("y"),
                           "turn": s.get("turnYn")} for s in seq]
        print("노선", rt["name"], "배차", rt["peekAlloc"], "정류장", len(rt["stations"]), flush=True)

    if not any(rt.get("stations") for rt in routes.values()) and any(
        rt.get("stations") for rt in previous.get("routes", {}).values()
    ):
        routes = previous["routes"]
        print("노선 상세 응답이 없어 기존 정상 노선 데이터를 보존합니다.", flush=True)
    out = {"near": {k: [str(v) for v in vs] for k, vs in near.items()}, "stops": stops, "routes": routes}
    if not stops:
        raise SystemExit("No bus stops collected; previous data preserved.")
    out["collection"] = {"updated_at": time.time(), "complete": not FAILURES,
                         "failed_calls": len(FAILURES),
                         "routes_with_stations": sum(bool(r.get("stations")) for r in routes.values()),
                         "routes_with_geometry": sum(bool(r.get("shape")) for r in routes.values())}
    temporary = RAW / "bus.json.tmp"
    temporary.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    temporary.replace(RAW / "bus.json")
    print("-> data/raw/bus.json", len(stops), "정류장", len(routes), "노선", flush=True)


if __name__ == "__main__":
    if not KEY:
        sys.exit(".env 에 DATA_GO_KR_KEY 가 없습니다.")
    main()
