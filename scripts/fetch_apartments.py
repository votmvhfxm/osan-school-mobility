"""Collect every K-APT Osan apartment; resume retries without publishing partial data."""
import csv
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from http.client import HTTPException
from urllib.error import HTTPError, URLError

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
RAW = DATA / "raw"
API = "https://apis.data.go.kr/1613000/AptListService4/getSigunguAptList4"
DETAIL_API = "https://apis.data.go.kr/1613000/AptBasisInfoServiceV5/getAphusBassInfoV5"
GEOCODE_API = "https://api.vworld.kr/req/address"
FIELDS = ["complex_id", "name", "block", "address", "lat", "lon", "households",
          "move_in", "zone", "coord_source", "source_url"]


def load_env():
    values = {}
    if (ROOT / ".env").exists():
        for line in (ROOT / ".env").read_text(encoding="utf-8-sig").splitlines():
            if line.strip() and not line.lstrip().startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                values[key.strip()] = value.strip().strip("'\"")
    values.update(os.environ)
    return values


def atomic_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    temp.replace(path)


def request_json(url, params, tries=5):
    # Never log request URLs or exception text: they can contain API keys.
    for attempt in range(tries):
        try:
            time.sleep(0.4)
            request = Request(url + "?" + urlencode(params), headers={"User-Agent": "OsanSchoolMobility/1.0"})
            with urlopen(request, timeout=30) as response:
                body = json.load(response)
            header = body.get("response", {}).get("header", {})
            code = str(header.get("resultCode", "00"))
            if "OpenAPI_ServiceResponse" in body or code not in ("00", "0", "000", "NORMAL_SERVICE"):
                if code in ("22", "30", "31", "32"):
                    raise RuntimeError("API authorization or daily quota error; retry after checking access/quota.")
                raise ValueError("API result error")
            return body
        except HTTPError as exc:
            if exc.code not in (429, 500, 502, 503, 504):
                raise RuntimeError("API HTTP error " + str(exc.code)) from None
            delay = min(60, 2 ** (attempt + 1))
            retry_after = exc.headers.get("Retry-After", "")
            if retry_after.isdigit():
                delay = min(120, max(delay, int(retry_after)))
        except (URLError, TimeoutError, ValueError, HTTPException, OSError):
            delay = min(60, 2 ** (attempt + 1))
        if attempt + 1 < tries:
            time.sleep(delay)
    raise RuntimeError("API request failed after retries; saved data preserved.")


def as_list(value):
    if isinstance(value, dict) and "item" in value:
        value = value["item"]
    return value if isinstance(value, list) else ([value] if value else [])


def fetch_list(key):
    rows, seen, page, expected = [], set(), 1, None
    while True:
        result = request_json(API, dict(serviceKey=key, sigunguCode="41370",
                                       numOfRows=100, pageNo=page, _type="json"))
        body = result["response"]["body"]
        if body.get("totalCount") is not None:
            expected = int(body["totalCount"])
        items = as_list(body.get("items"))
        added = 0
        for item in items:
            code = item["kaptCode"]
            if code not in seen:
                rows.append(item)
                seen.add(code)
                added += 1
        if expected is not None and len(rows) >= expected:
            break
        if not items:
            if expected is not None and len(rows) < expected:
                raise RuntimeError("Incomplete apartment list; previous data preserved.")
            break
        if not added:
            raise RuntimeError("Repeated API page; refusing incomplete list.")
        page += 1
    if not rows:
        raise RuntimeError("Empty apartment list; previous data preserved.")
    return rows


def geocode(address, key, address_type):
    body = request_json(GEOCODE_API, dict(service="address", request="getcoord",
        version="2.0", crs="epsg:4326", address=address, refine="true",
        simple="false", format="json", type=address_type, key=key))
    response = body.get("response", {})
    if response.get("status") not in ("OK", "NOT_FOUND"):
        raise RuntimeError("VWorld API error; check key, permissions and quota.")
    point = (response.get("result") or {}).get("point") or {}
    try:
        lat, lon = float(point["y"]), float(point["x"])
        if 37.05 < lat < 37.25 and 126.90 < lon < 127.20:
            return lat, lon
    except (ValueError, TypeError, KeyError):
        pass
    return None


def read_previous_complexes():
    try:
        with (DATA / "complexes.csv").open(encoding="utf-8-sig", newline="") as stream:
            return {row["complex_id"]: row for row in csv.DictReader(stream)}
    except (OSError, ValueError, KeyError, csv.Error):
        return {}


def reusable_coordinates(previous, address):
    """Only reuse verified coordinates when the published address is unchanged."""
    if not previous or previous.get("coord_source") != "vworld":
        return None
    normalize = lambda text: "".join(str(text or "").split())
    if not normalize(address) or normalize(previous.get("address")) != normalize(address):
        return None
    try:
        lat, lon = float(previous["lat"]), float(previous["lon"])
        return (lat, lon) if 37.05 < lat < 37.25 and 126.90 < lon < 127.20 else None
    except (ValueError, TypeError, KeyError):
        return None


def main():
    env = load_env()
    key, vkey = env.get("DATA_GO_KR_KEY"), env.get("VWORLD_API_KEY")
    if not key or not vkey:
        raise SystemExit("DATA_GO_KR_KEY and VWORLD_API_KEY are required; existing data preserved.")
    RAW.mkdir(parents=True, exist_ok=True)
    items = fetch_list(key)
    atomic_json(RAW / "apartments_osan.json",
                {"response": {"body": {"totalCount": len(items), "items": items}}})
    checkpoint = RAW / "apartments_checkpoint.json"
    try:
        cache = json.loads(checkpoint.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        cache = {}
    # A completed earlier run starts a new refresh; an interrupted one resumes.
    if cache.get("complete"):
        # Code pushes/retries on the same day must not spend the quota again.
        if time.time() - cache.get("started_at", 0) >= 6 * 3600:
            cache = {}
        else:
            cache["complete"] = False
    if time.time() - cache.get("started_at", time.time()) > 7 * 86400:
        cache = {}
    cache.setdefault("started_at", time.time())
    previous_complexes = read_previous_complexes()
    details = cache.setdefault("details", {})
    coords = cache.setdefault("coords", {})
    rows, pending = [], []
    for item in items:
        code = item["kaptCode"]
        try:
            if code not in details:
                body = request_json(DETAIL_API, dict(serviceKey=key, kaptCode=code, _type="json"))
                detail = body["response"]["body"].get("item") or {}
                if not detail:
                    raise RuntimeError("Empty apartment detail")
                details[code] = detail
                atomic_json(checkpoint, cache)
            detail = details[code]
            address = detail.get("doroJuso") or detail.get("kaptAddr") or ""
            if code not in coords:
                verified = reusable_coordinates(previous_complexes.get(code), address)
                if verified:
                    coords[code] = verified
                    atomic_json(checkpoint, cache)
            if code not in coords:
                for field, kind in (("doroJuso", "road"), ("kaptAddr", "parcel")):
                    if detail.get(field):
                        point = geocode(detail[field], vkey, kind)
                        if point:
                            coords[code] = point
                            atomic_json(checkpoint, cache)
                            break
            if code not in coords:
                raise RuntimeError("No verified coordinates for road/parcel address")
            rows.append(dict(complex_id=code, name=detail.get("kaptName") or item.get("kaptName"),
                block="", address=address, lat=coords[code][0], lon=coords[code][1],
                households=detail.get("kaptdaCnt") or detail.get("hoCnt"),
                move_in=detail.get("kaptUsedate"), zone="오산시", coord_source="vworld",
                source_url="https://www.data.go.kr/data/15058453/openapi.do"))
        except RuntimeError as exc:
            pending.append(dict(complex_id=code, name=item.get("kaptName"), reason=str(exc)))
        print(f"{len(rows)}/{len(items)} ready; {len(pending)} pending", flush=True)
    atomic_json(RAW / "apartments_osan_details.json", list(details.values()))
    atomic_json(DATA / "apartments_fetch_status.json", dict(
        updated_at=datetime.now(timezone.utc).isoformat(), total=len(items),
        mapped=len(rows), complete=not pending, pending=pending))
    if pending:
        raise SystemExit("Incomplete collection. Previous complexes.csv preserved; rerun to resume. See apartments_fetch_status.json.")
    temp = DATA / "complexes.csv.tmp"
    with temp.open("w", newline="", encoding="utf-8-sig") as stream:
        writer = csv.DictWriter(stream, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    temp.replace(DATA / "complexes.csv")
    cache["complete"] = True
    atomic_json(checkpoint, cache)
    print(f"Published all {len(rows)} apartments.")


if __name__ == "__main__":
    main()
