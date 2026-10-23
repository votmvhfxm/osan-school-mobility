"""공공데이터포털 수집 (DATA_GO_KR_KEY 필요). 결과는 data/raw/ 에 원본 JSON 그대로 저장.

사용: python scripts/fetch_public.py [zones|crosswalks|accidents|all]
"""
import json
import sys
import time

import requests

from common import RAW, load_env

KEY = load_env()["DATA_GO_KR_KEY"]
# Fixed project scope: Gyeonggi-do, Osan-si.
SIDO, GUGUN = "41", "370"
OSAN_TOKENS = ("오산", "osan")


def get(url, params, tries=3):
    for i in range(tries):
        try:
            r = requests.get(url, params={"serviceKey": KEY, **params}, timeout=30)
            if r.status_code == 200:
                return r
            print("  HTTP", r.status_code)
        except requests.RequestException as e:
            print("  err", type(e).__name__)
        time.sleep(1 + i)
    return None


def standard_paged(api, out, keep):
    """표준데이터 API 전 페이지를 받아 keep(row) 인 행만 저장."""
    url = f"https://api.data.go.kr/openapi/{api}"
    rows, page = [], 1
    while True:
        r = get(url, {"pageNo": page, "numOfRows": 1000, "type": "json"})
        if r is None:
            raise RuntimeError("Public API page failed; existing data preserved.")
        try:
            body = r.json()["response"]["body"]
        except Exception:  # noqa: BLE001
            raise RuntimeError("Invalid public API response; existing data preserved.") from None
        items = body.get("items") or []
        if not items:
            break
        rows += [it for it in items if keep(it)]
        total = int(body.get("totalCount", 0))
        print(f"  {api} page {page} / {total // 1000 + 1}  kept={len(rows)}")
        if page * 1000 >= total:
            break
        page += 1
    (RAW / out).write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"-> data/raw/{out} ({len(rows)}행)")


def is_osan(it):
    s = " ".join(str(it.get(k, "")) for k in ("rdnmadr", "lnmadr", "institutionNm", "signguNm", "insttNm"))
    normalized = s.replace(" ", "").lower()
    return any(token in normalized for token in OSAN_TOKENS)


def zones():
    standard_paged("tn_pubr_public_child_safe_zone_api", "child_safe_zone.json", is_osan)


def crosswalks():
    standard_paged("tn_pubr_public_crosswalk_api", "crosswalk.json", is_osan)


# TAAS 사고다발지역 API 후보 (서비스명 표기가 문서마다 달라 순서대로 시도)
TAAS = {
    "child": ["frequentzoneChild/getRestFrequentzoneChild"],
    "pedestrian": ["frequentzonePdstrn/getRestFrequentzonePdstrn",
                   "frequentzonePedstrians/getRestFrequentzonePedstrians"],
    "jaywalk": ["frequentzoneJaywalking/getRestFrequentzoneJaywalking"],
    "oldman": ["frequentzoneOldman/getRestFrequentzoneOldman"],
    "lg": ["frequentzoneLg/getRestFrequentzoneLg"],
}


def accidents(years=range(2019, 2025)):
    out = {}
    for kind, paths in TAAS.items():
        out[kind] = []
        for path in paths:
            ok = False
            for y in years:
                r = get(f"https://apis.data.go.kr/B552061/{path}",
                        {"searchYearCd": y, "siDo": SIDO, "guGun": GUGUN,
                         "type": "json", "numOfRows": 100, "pageNo": 1})
                if r is None:
                    continue
                try:
                    j = r.json()
                except ValueError:
                    print(f"  {path} {y}: invalid JSON response")
                    continue
                items = (j.get("items") or {}).get("item") or []
                ok = ok or "resultCode" in j
                for it in items:
                    it["_year"] = y
                out[kind] += items
                print(f"  {kind} {y}: {len(items)}건 ({path})")
            if ok:
                break
    (RAW / "taas_frequentzone.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print("-> data/raw/taas_frequentzone.json", {k: len(v) for k, v in out.items()})


if __name__ == "__main__":
    if not KEY:
        sys.exit(".env 에 DATA_GO_KR_KEY 가 없습니다.")
    what = sys.argv[1] if len(sys.argv) > 1 else "all"
    for name, fn in (("zones", zones), ("crosswalks", crosswalks), ("accidents", accidents)):
        if what in (name, "all"):
            print("==", name)
            fn()
