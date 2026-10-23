"""통학 부담 지수 계산.
입력: data/complexes.csv, data/schools.csv, data/raw/osm_walk.graphml, data/edge_risk.csv, (선택) data/raw/bus.json
출력: data/index.json, data/priority.csv, data/priority_segments.csv
"""
import json
import math
from datetime import datetime
from functools import lru_cache

import networkx as nx
import numpy as np
import osmnx as ox
import pandas as pd
import geopandas as gpd

from common import DATA, RAW
from build_lite import write_indexes

# ---- 지수 가중치 (README 참고) ----
W_TIME, W_RISK, W_WAIT = 0.4, 0.4, 0.2
WALK_M_PER_MIN = 72          # 1km ≈ 13.9분 (중학생 평균 보행속도 약 1.2m/s 가정)
RISK_THRESHOLD = 0.6         # 위험 구간 기준
BUS_KMH = 20                 # 시내버스 표정속도 근사
BUS_STOP_DWELL_MIN = 0.3     # 정류장당 정차 시간
MAX_ACCESS_M = 600           # 정류장까지 최대 도보 거리
SAFE_ALPHA = 2.0             # 안전 경로 비용 = 길이 × (1 + α×위험도 + β×[위험 구간])
SAFE_BETA = 6.0              # 위험 구간(≥ RISK_THRESHOLD) 간선은 추가로 6배 길게 취급
SAFE_MAX_DETOUR = 1.2        # 안전 경로가 최단보다 20% 넘게 길면 추천하지 않음
DEMO = {"북측": "C01", "남측": "C05"}  # 시연 영상용 고정 단지 (에듀파크 / LH 21단지)


def hav(a, b):
    (la1, lo1), (la2, lo2) = a, b
    p = math.pi / 180
    h = math.sin((la2 - la1) * p / 2) ** 2 + math.cos(la1 * p) * math.cos(la2 * p) * math.sin((lo2 - lo1) * p / 2) ** 2
    return 2 * 6371000 * math.asin(math.sqrt(h))


class Net:
    def __init__(self):
        G = ox.load_graphml(RAW / "osm_walk.graphml")
        risk = pd.read_csv(DATA / "edge_risk.csv").set_index(["u", "v", "key"])["risk"].to_dict()
        edge_features = gpd.read_file(DATA / "edges.gpkg", layer="edges").set_index(["u", "v", "key"])
        for u, v, k, d in G.edges(keys=True, data=True):
            d["risk"] = float(risk.get((u, v, k), 0.0))
            if (u, v, k) in edge_features.index:
                feature = edge_features.loc[(u, v, k)]
                for name in ("hw", "hw_rank", "lanes_n", "n_intersections", "n_crossings",
                             "n_signal_crossings", "n_unsignal_crossings", "in_school_zone", "ped_only"):
                    d[name] = feature.get(name)
        self.G = nx.MultiDiGraph(G)
        self.Gu = ox.convert.to_undirected(G)  # 보행은 일방통행 무시
        self.node_ids = np.array(list(self.Gu.nodes))
        self.node_lat = np.radians([self.Gu.nodes[n]["y"] for n in self.node_ids])
        self.node_lon = np.radians([self.Gu.nodes[n]["x"] for n in self.node_ids])
        for u, v, k, d in self.Gu.edges(keys=True, data=True):
            r = d.get("risk", 0)
            d["safe_cost"] = d["length"] * (1 + SAFE_ALPHA * r + SAFE_BETA * (r >= RISK_THRESHOLD))

    @lru_cache(maxsize=4096)
    def nearest(self, lat, lon):
        # Reuse node arrays and exact spherical distance; no repeated BallTree construction.
        la, lo = np.radians([lat, lon])
        distance = np.sin((self.node_lat - la) / 2) ** 2 + np.cos(la) * np.cos(
            self.node_lat) * np.sin((self.node_lon - lo) / 2) ** 2
        return int(self.node_ids[np.argmin(distance)])

    def route(self, a, b, weight="safe_cost"):
        """a, b = (lat, lon). weight="length" 최단 경로, "safe_cost" 위험 회피 경로."""
        na, nb = self.nearest(*a), self.nearest(*b)
        try:
            nodes = nx.shortest_path(self.Gu, na, nb, weight=weight)
        except nx.NetworkXNoPath:
            return None
        segs = []
        for u, v in zip(nodes[:-1], nodes[1:]):
            d = min(self.Gu.get_edge_data(u, v).values(), key=lambda x: x[weight])
            if "geometry" in d:
                xs, ys = d["geometry"].xy
                coords = list(zip(ys, xs))
                if hav(coords[0], (self.Gu.nodes[u]["y"], self.Gu.nodes[u]["x"])) > 1:
                    coords = coords[::-1]
            else:
                coords = [(self.Gu.nodes[u]["y"], self.Gu.nodes[u]["x"]), (self.Gu.nodes[v]["y"], self.Gu.nodes[v]["x"])]
            segs.append({"len": float(d["length"]), "risk": float(d.get("risk", 0)), "coords": coords,
                         "name": d.get("name") if isinstance(d.get("name"), str) else None,
                         "hw": d.get("hw"), "hw_rank": float(d.get("hw_rank", 0) or 0),
                         "lanes_n": float(d.get("lanes_n", 0) or 0),
                         "n_intersections": float(d.get("n_intersections", 0) or 0),
                         "n_crossings": float(d.get("n_crossings", 0) or 0),
                         "n_signal_crossings": float(d.get("n_signal_crossings", 0) or 0),
                         "n_unsignal_crossings": float(d.get("n_unsignal_crossings", 0) or 0),
                         "in_school_zone": int(d.get("in_school_zone", 0) or 0),
                         "ped_only": int(d.get("ped_only", 0) or 0),
                         "uv": (min(u, v), max(u, v))})
        # 출발·도착 점에서 가장 가까운 노드까지의 접근 거리
        snap = hav(a, (self.Gu.nodes[na]["y"], self.Gu.nodes[na]["x"])) + hav(b, (self.Gu.nodes[nb]["y"], self.Gu.nodes[nb]["x"]))
        return summarize(segs, snap, a, b)


def r6(c):
    return [round(c[0], 6), round(c[1], 6)]


def summarize(segs, snap, a, b):
    dist = sum(s["len"] for s in segs) + snap
    path = [r6(a)]
    for s in segs:
        path += [r6(c) for c in s["coords"][1:]] if path[-1] == r6(s["coords"][0]) else [r6(c) for c in s["coords"]]
    path.append(r6(b))
    # 위험도 ≥ 기준인 연속 간선을 하나의 '위험 구간'으로 묶음
    runs, cur = [], None
    for s in segs:
        if s["risk"] >= RISK_THRESHOLD:
            if cur is None:
                cur = {"coords": list(s["coords"]), "len": 0, "risk_max": 0, "names": set(), "uvs": [],
                       "road_types": set(), "max_lanes": 0, "intersections": 0, "crossings": 0,
                       "signal_crossings": 0, "unsignal_crossings": 0, "school_zone_edges": 0,
                       "ped_only_edges": 0, "edge_count": 0}
            else:
                cur["coords"] += s["coords"][1:]
            cur["len"] += s["len"]
            cur["risk_max"] = max(cur["risk_max"], s["risk"])
            cur["uvs"].append(s["uv"])
            if s["name"]:
                cur["names"].add(s["name"])
            if s["hw"]:
                cur["road_types"].add(s["hw"])
            cur["max_lanes"] = max(cur["max_lanes"], s["lanes_n"])
            cur["intersections"] += s["n_intersections"]
            cur["crossings"] += s["n_crossings"]
            cur["signal_crossings"] += s["n_signal_crossings"]
            cur["unsignal_crossings"] += s["n_unsignal_crossings"]
            cur["school_zone_edges"] += s["in_school_zone"]
            cur["ped_only_edges"] += s["ped_only"]
            cur["edge_count"] += 1
        elif cur is not None:
            runs.append(cur)
            cur = None
    if cur is not None:
        runs.append(cur)
    risk_sum = sum(s["risk"] * s["len"] / 100 for s in segs)  # 위험도 × 100m 단위 길이
    return {
        "dist_m": round(dist), "walk_min": round(dist / WALK_M_PER_MIN, 1),
        "risk_sum": round(risk_sum, 2),
        "n_risk_segments": len(runs),
        "risk_len_m": round(sum(r["len"] for r in runs)),
        "path": path,
        "risk_segments": [{"coords": [r6(c) for c in r["coords"]], "len_m": round(r["len"]),
                           "risk": round(r["risk_max"], 2), "road": ", ".join(sorted(r["names"])) or None,
                           "road_types": ", ".join(sorted(r["road_types"])),
                           "max_lanes": round(r["max_lanes"]), "intersections": round(r["intersections"]),
                           "crossings": round(r["crossings"]), "signal_crossings": round(r["signal_crossings"]),
                           "unsignal_crossings": round(r["unsignal_crossings"]),
                           "school_zone_edges": round(r["school_zone_edges"]),
                           "ped_only_edges": round(r["ped_only_edges"]), "edge_count": r["edge_count"],
                           "key": "|".join(f"{u}-{v}" for u, v in r["uvs"])} for r in runs],
    }


def load_bus():
    f = RAW / "bus.json"
    if not f.exists():
        return None
    b = json.loads(f.read_text(encoding="utf-8"))
    valid_routes = 0
    for rt in b.get("routes", {}).values():
        rt["pos"] = {}
        for s in rt.get("stations", []):
            rt["pos"].setdefault(s["stationId"], []).append(s["seq"])
        if rt.get("stations"):
            valid_routes += 1
    return b if b.get("stops") else None


def load_bus_stop_count():
    f = RAW / "bus.json"
    if not f.exists():
        return 0
    try:
        return len(json.loads(f.read_text(encoding="utf-8")).get("stops", {}))
    except (OSError, ValueError):
        return 0


def bus_option(net, bus, cid, sid, c_ll, s_ll, walk_cache):
    best = None
    for rid, rt in bus["routes"].items():
        alloc = rt.get("peekAlloc") or rt.get("nPeekAlloc")
        try:
            alloc = float(alloc)
        except (TypeError, ValueError):
            continue
        if alloc <= 0:
            continue
        st = {s["seq"]: s for s in rt.get("stations", [])}
        for a in bus["near"].get(cid, []):
            for b in bus["near"].get(sid, []):
                for qa in rt["pos"].get(a, []):
                    for qb in rt["pos"].get(b, []):
                        if qb <= qa:
                            continue
                        sa, sb = st[qa], st[qb]
                        la = (float(sa["y"]), float(sa["x"]))
                        lb = (float(sb["y"]), float(sb["x"]))
                        if hav(c_ll, la) > MAX_ACCESS_M or hav(lb, s_ll) > MAX_ACCESS_M:
                            continue
                        ride_m = sum(hav((float(st[q]["y"]), float(st[q]["x"])), (float(st[q + 1]["y"]), float(st[q + 1]["x"])))
                                     for q in range(qa, qb) if q in st and q + 1 in st)
                        n_stops = qb - qa
                        ride = ride_m / (BUS_KMH * 1000 / 60) + n_stops * BUS_STOP_DWELL_MIN
                        wait = alloc / 2
                        est = hav(c_ll, la) / WALK_M_PER_MIN * 1.3 + wait + ride + hav(lb, s_ll) / WALK_M_PER_MIN * 1.3
                        if best is None or est < best["_est"]:
                            best = {"_est": est, "route_id": rid, "route_name": rt["name"], "alloc_min": alloc,
                                    "wait_min": round(wait, 1), "ride_min": round(ride, 1), "n_stops": n_stops,
                                    "board": {"name": sa["name"], "ll": r6(la)}, "alight": {"name": sb["name"], "ll": r6(lb)},
                                    "bus_path": [r6((float(st[q]["y"]), float(st[q]["x"]))) for q in range(qa, qb + 1) if q in st]}
    if best is None and bus.get("stops"):
        origin = min(bus["stops"].values(), key=lambda s: hav(c_ll, (float(s["y"]), float(s["x"]))))
        destination = min(bus["stops"].values(), key=lambda s: hav(s_ll, (float(s["y"]), float(s["x"]))))
        access_m = hav(c_ll, (float(origin["y"]), float(origin["x"])))
        egress_m = hav(s_ll, (float(destination["y"]), float(destination["x"])))
        road_route = net.route(
            (float(origin["y"]), float(origin["x"])),
            (float(destination["y"]), float(destination["x"])),
            weight="length",
        )
        road_m = road_route["dist_m"] if road_route else hav(
            (float(origin["y"]), float(origin["x"])),
            (float(destination["y"]), float(destination["x"])),
        ) * 1.25
        wait = 8.0
        ride = road_m / (BUS_KMH * 1000 / 60)
        best = {
            "_est": access_m / WALK_M_PER_MIN * 1.3 + wait + ride + egress_m / WALK_M_PER_MIN * 1.3,
            "route_id": None, "route_name": "정류장·도로망 기반 추정", "alloc_min": None,
            "wait_min": wait, "ride_min": round(ride, 1), "n_stops": None,
            "board": {"name": origin.get("stationName"), "ll": r6((float(origin["y"]), float(origin["x"])))},
            "alight": {"name": destination.get("stationName"), "ll": r6((float(destination["y"]), float(destination["x"])))},
            "bus_path": road_route["path"] if road_route else [
                r6((float(origin["y"]), float(origin["x"]))),
                r6((float(destination["y"]), float(destination["x"]))),
            ],
            "estimated": True,
        }
    if best is None:
        return None
    w1 = walk_cache(c_ll, tuple(best["board"]["ll"]))
    w2 = walk_cache(tuple(best["alight"]["ll"]), s_ll)
    if w1 is None or w2 is None:
        return None
    best.pop("_est")
    walk_min = w1["walk_min"] + w2["walk_min"]
    best.update({
        "time_min": round(walk_min + best["wait_min"] + best["ride_min"], 1),
        "walk_min": round(walk_min, 1), "dist_walk_m": w1["dist_m"] + w2["dist_m"],
        "risk_sum": round(w1["risk_sum"] + w2["risk_sum"], 2),
        "n_risk_segments": w1["n_risk_segments"] + w2["n_risk_segments"],
        "risk_len_m": w1["risk_len_m"] + w2["risk_len_m"],
        "walk_paths": [w1["path"], w2["path"]],
        "risk_segments": w1["risk_segments"] + w2["risk_segments"],
        "wait_transfer_min": best["wait_min"],
    })
    return best


def norm(vals):
    """최댓값 대비 비율(0~1). 최솟값을 0으로 만들지 않아 단지 간 '몇 배' 비교가 가능하다."""
    v = np.array(vals, dtype=float)
    hi = np.nanmax(v)
    return v / hi if hi > 0 else np.zeros_like(v)


def main():
    cx = pd.read_csv(DATA / "complexes.csv")
    sc = pd.read_csv(DATA / "schools.csv")
    if "school_level" not in sc:
        sc["school_level"] = "중학교"
    net = Net()
    bus = load_bus()
    cache = {}

    def walk_cache(a, b):
        k = (tuple(r6(a)), tuple(r6(b)))
        if k not in cache:
            cache[k] = net.route(a, b)
        return cache[k]

    def make_combo(c, s):
        c_ll, s_ll = (c.lat, c.lon), (s.lat, s.lon)
        sp = net.route(c_ll, s_ll, weight="length")  # 최단 경로
        if sp is None:
            print("경로 없음", c.complex_id, s.school_id)
            return None
        sf = walk_cache(c_ll, s_ll)                    # 위험 회피 경로
        # 우회가 과하거나 위험이 줄지 않으면 최단 경로를 그대로 추천
        safe_ok = sf is not None and sf["dist_m"] <= sp["dist_m"] * SAFE_MAX_DETOUR and sf["risk_len_m"] < sp["risk_len_m"]
        w = dict(sf if safe_ok else sp)
        w.update({"time_min": w["walk_min"], "wait_transfer_min": 0.0, "is_safe_detour": bool(safe_ok)})
        w["shortest"] = {k: sp[k] for k in ("dist_m", "walk_min", "risk_sum", "n_risk_segments", "risk_len_m",
                                             "path", "risk_segments")}
        b = bus_option(net, bus, c.complex_id, s.school_id, c_ll, s_ll, walk_cache) if bus else None
        print(f"{c['name']:<24} → {s['name']}: 직선 {hav(c_ll, s_ll)/1000:.2f}km / 도보 {w['dist_m']/1000:.2f}km "
              f"{w['walk_min']}분 위험구간 {w['n_risk_segments']} (최단 {w['shortest']['dist_m']}m 위험구간 "
              f"{w['shortest']['n_risk_segments']})" + (f" / 버스 {b['route_name']} {b['time_min']}분" if b else ""))
        return {"cid": c.complex_id, "sid": s.school_id, "straight_m": round(hav(c_ll, s_ll)), "walk": w, "bus": b}

    combos = [cb for _, c in cx.iterrows() for _, s in sc.iterrows() if (cb := make_combo(c, s))]
    # 개교 예정 학교(세교2-1 등): 같은 기준으로 계산해 전후 비교에만 사용
    fut = pd.read_csv(DATA / "schools_future.csv") if (DATA / "schools_future.csv").exists() else sc.iloc[0:0]
    fut = fut.dropna(subset=["lat", "lon"])
    fcombos = [cb for _, c in cx.iterrows() for _, s in fut.iterrows() if (cb := make_combo(c, s))]

    # 정규화는 모든 조합·시나리오를 한 풀로
    allc = combos + fcombos
    scen = [(i, k) for i, cb in enumerate(allc) for k in ("walk", "bus") if cb[k]]
    nt = norm([allc[i][k]["time_min"] for i, k in scen])
    nr = norm([allc[i][k]["risk_sum"] for i, k in scen])
    nw = norm([allc[i][k]["wait_transfer_min"] for i, k in scen])
    for j, (i, k) in enumerate(scen):
        allc[i][k]["index"] = round(100 * (W_TIME * nt[j] + W_RISK * nr[j] + W_WAIT * nw[j]), 1)
    for cb in allc:
        opts = [k for k in ("walk", "bus") if cb[k]]
        cb["rep"] = min(opts, key=lambda k: cb[k]["index"])
        cb["index"] = cb[cb["rep"]]["index"]

    out_cx = []
    for _, c in cx.iterrows():
        res = {cb["sid"]: cb for cb in combos if cb["cid"] == c.complex_id}
        if not res:
            continue
        best = min(res.values(), key=lambda x: x["index"])
        worst = max(res.values(), key=lambda x: x["index"])
        out_cx.append({
            "id": c.complex_id, "name": c["name"], "lat": c.lat, "lon": c.lon, "zone": c.zone,
            "households": None if pd.isna(c.get("households")) else int(c.households),
            "best_school": best["sid"], "worst_school": worst["sid"],
            "worst_best_ratio": round(worst["index"] / best["index"], 2) if best["index"] > 0 else None,
            "worst_best_time_ratio": round(worst[worst["rep"]]["time_min"] / best[best["rep"]]["time_min"], 2),
            "mean_index": round(float(np.mean([r["index"] for r in res.values()])), 1),
            "results": {sid: {k: v for k, v in r.items() if k not in ("cid", "sid")} for sid, r in res.items()},
        })
        fres = {cb["sid"]: cb for cb in fcombos if cb["cid"] == c.complex_id}
        if fres:
            now_t = [r[r["rep"]]["time_min"] for r in res.values()]
            aft_t = now_t + [r[r["rep"]]["time_min"] for r in fres.values()]
            now_i = [r["index"] for r in res.values()]
            aft_i = now_i + [r["index"] for r in fres.values()]
            out_cx[-1]["future"] = {
                "results": {sid: {k: v for k, v in r.items() if k not in ("cid", "sid")} for sid, r in fres.items()},
                # 추첨이 학교별 균등하다고 단순 가정한 기대값 / 가장 가까운 학교 기준
                "mean_time_now": round(float(np.mean(now_t)), 1), "mean_time_after": round(float(np.mean(aft_t)), 1),
                "mean_index_now": round(float(np.mean(now_i)), 1), "mean_index_after": round(float(np.mean(aft_i)), 1),
                "min_time_now": min(now_t), "min_time_after": min(aft_t),
            }

    sname = dict(zip(sc.school_id, sc.name))
    bus_has_routes = bool(bus and any(rt.get("stations") for rt in bus.get("routes", {}).values()))
    bus_recommendations = []
    if bus and bus.get("stops"):
        for c in sorted(out_cx, key=lambda x: -(x["mean_index"] or 0))[:12]:
            stop = min(bus["stops"].values(), key=lambda s: hav((c["lat"], c["lon"]), (float(s["y"]), float(s["x"]))))
            bus_recommendations.append({
                "complex": c["name"], "lat": float(stop["y"]), "lon": float(stop["x"]),
                "stop": stop.get("stationName") or "정류장", "distance_m": round(hav((c["lat"], c["lon"]), (float(stop["y"]), float(stop["x"])))),
                "reason": "통학 부담이 큰 단지의 최근접 정류장"
            })
    school_recommendations = []
    for c in sorted(out_cx, key=lambda x: -(x["mean_index"] or 0))[:10]:
        worst = c["worst_school"]
        school_recommendations.append({
            "area": c["name"], "lat": c["lat"], "lon": c["lon"],
            "reason": f"{sname[worst]} 통학 부담이 큰 권역", "mean_index": c["mean_index"]
        })
    meta = {
        "generated": datetime.now().isoformat(timespec="seconds"),
        "weights": {"time": W_TIME, "risk": W_RISK, "wait": W_WAIT},
        "walk_m_per_min": WALK_M_PER_MIN, "risk_threshold": RISK_THRESHOLD,
        "bus_available": bus_has_routes,
        "bus_estimate_available": bool(bus and bus.get("stops")),
        "bus_stop_count": load_bus_stop_count(),
        "bus_collection": bus.get("collection") if bus else None,
        "bus_recommendations": bus_recommendations,
        "school_recommendations": school_recommendations,
        "risk_model": json.loads((DATA.parent / "model" / "metrics.json").read_text(encoding="utf-8")).get("mode"),
        "school_district": "오산시 초·중학교(학교알리미 기준)",
        "demo": DEMO,
    }
    # Cast to object before replacing missing values; otherwise pandas keeps
    # floating columns as NaN, which is not valid JSON for browser fetch().
    schools = sc.astype(object).where(pd.notna(sc), None).to_dict("records")
    future_schools = fut.astype(object).where(pd.notna(fut), None).to_dict("records")
    write_indexes(DATA, {"meta": meta, "schools": schools,
                         "future_schools": future_schools, "complexes": out_cx})

    # ---- 우선순위 표 ----
    rows = []
    for c in out_cx:
        for sid, r in c["results"].items():
            rep = r[r["rep"]]
            rows.append({"단지": c["name"], "구역": c["zone"], "학교": sname[sid], "통학부담지수": r["index"],
                         "대표시나리오": "도보" if r["rep"] == "walk" else "버스",
                         "소요시간_분": rep["time_min"], "도보거리_m": r["walk"]["dist_m"], "직선거리_m": r["straight_m"],
                         "위험구간수": rep["n_risk_segments"], "위험구간길이_m": rep["risk_len_m"],
                         "버스대기_분": r["bus"]["wait_min"] if r["bus"] else None,
                         "버스노선": r["bus"]["route_name"] if r["bus"] else None})
    pr = pd.DataFrame(rows).sort_values("통학부담지수", ascending=False)
    pr.insert(0, "순위", range(1, len(pr) + 1))
    pr.to_csv(DATA / "priority.csv", index=False, encoding="utf-8-sig")

    seg = {}
    for c in out_cx:
        for sid, r in c["results"].items():
            for rs in r["walk"]["risk_segments"]:
                d = seg.setdefault(rs["key"], {"도로명": rs["road"], "길이_m": rs["len_m"], "위험도": rs["risk"],
                                               "도로유형": rs.get("road_types"), "최대차로수": rs.get("max_lanes"),
                                               "교차로수": rs.get("intersections"), "횡단보도수": rs.get("crossings"),
                                               "신호횡단보도수": rs.get("signal_crossings"),
                                               "무신호횡단보도수": rs.get("unsignal_crossings"),
                                               "보호구역구간수": rs.get("school_zone_edges"),
                                               "보행전용구간수": rs.get("ped_only_edges"),
                                               "통과경로수": 0, "관련단지": set(), "관련학교": set(),
                                               "lat": rs["coords"][len(rs["coords"]) // 2][0],
                                               "lon": rs["coords"][len(rs["coords"]) // 2][1]})
                d["통과경로수"] += 1
                d["관련단지"].add(c["name"])
                d["관련학교"].add(sname[sid])
    sg = pd.DataFrame(seg.values())
    if len(sg):
        sg["관련단지수"] = sg["관련단지"].map(len)
        sg["관련단지"] = sg["관련단지"].map(lambda s: ", ".join(sorted(s)))
        sg["관련학교"] = sg["관련학교"].map(lambda s: ", ".join(sorted(s)))
        sg["우선점수"] = (sg["위험도"] * sg["통과경로수"] * np.log1p(sg["길이_m"])).round(2)
        sg = sg.sort_values("우선점수", ascending=False)
        sg.insert(0, "순위", range(1, len(sg) + 1))
    sg.to_csv(DATA / "priority_segments.csv", index=False, encoding="utf-8-sig")

    # ---- 등교시간 버스 공백 (정류장·노선 검토 우선순위) ----
    if bus:
        stops = [(float(v["y"]), float(v["x"]), v.get("stationName")) for v in bus["stops"].values()]
        hh = dict(zip(cx.complex_id, cx.households))
        brows = []
        for c in out_cx:
            near = min(stops, key=lambda st: hav((c["lat"], c["lon"]), st[:2])) if stops else None
            for sid, r in c["results"].items():
                w, b = r["walk"], r["bus"]
                gap = b is None or b["time_min"] >= w["time_min"]  # 직행 버스가 없거나 걷는 것보다 느림
                brows.append({"단지": c["name"], "세대수": hh.get(c["id"]), "학교": sname[sid],
                              "도보_분": w["time_min"], "버스_분": b["time_min"] if b else None,
                              "직행노선": b["route_name"] if b else "없음", "첨두배차_분": b["alloc_min"] if b else None,
                              "최근접정류장": near[2] if near else None,
                              "최근접정류장_m": round(hav((c["lat"], c["lon"]), near[:2])) if near else None,
                              "버스공백": "예" if gap else "아니오"})
        bp = pd.DataFrame(brows)
        # 공백이면서 걷기 먼 조합, 세대수가 많은 단지부터 (세대수 미상은 500으로 가정)
        bp["검토점수"] = np.where(bp["버스공백"] == "예", bp["도보_분"] * bp["세대수"].fillna(500) / 1000, 0).round(1)
        bp = bp.sort_values("검토점수", ascending=False)
        bp.insert(0, "순위", range(1, len(bp) + 1))
        bp.to_csv(DATA / "priority_bus.csv", index=False, encoding="utf-8-sig")
        print("버스 공백 조합:", int((bp["버스공백"] == "예").sum()), "/", len(bp))

    print("\n== 단지별 최악/최선 학교 지수 비율")
    for c in sorted(out_cx, key=lambda c: -(c["worst_best_ratio"] or 0)):
        print(f"{c['name']:<24} {c['zone']}  최선 {sname[c['best_school']]} / 최악 {sname[c['worst_school']]}  "
              f"지수비 {c['worst_best_ratio']}  시간비 {c['worst_best_time_ratio']}")


if __name__ == "__main__":
    main()
