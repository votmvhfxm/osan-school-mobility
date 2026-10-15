"""구간(간선) 위험도 모델.

라벨: TAAS 사고다발지역이 간선 반경 30m 안에 있으면 1 (build_edges.py 의 acc_label).
양성 라벨이 MIN_POS 이상이면 로지스틱 회귀 / 그래디언트 부스팅을 오산시 전체 간선으로 학습(공간 그룹 교차검증),
더 좋은 쪽 확률을 0~1 위험도로 쓴다. 양성이 부족하면 규칙 기반 점수식으로 대체하고 그 사실을 metrics.json 에 남긴다.
※ 라벨 누설을 막기 위해 '인근 사고 건수'(acc_count_50m)는 모델 피처에서 제외한다.

출력: data/edge_risk.csv (u,v,key,risk,risk_source), model/metrics.json
"""
import json
import sys
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.inspection import permutation_importance
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score
from sklearn.model_selection import GroupKFold
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from common import DATA, MODEL  # noqa: E402

MIN_POS = 30
FEATURES = ["hw_rank", "ped_only", "major_road", "lanes_n", "length_m", "n_intersections",
            "n_crossings", "n_unsignal_crossings", "signal_ratio", "in_school_zone"]

# 규칙 기반 점수식(대체용). 각 항은 0~1 로 정규화한 뒤 가중합.
RULE_W = {
    "road": 0.40,        # 차량 위계(등급·차로 수)
    "unsignal": 0.25,    # 무신호 횡단 노출
    "intersection": 0.20,
    "no_zone": 0.15,     # 어린이보호구역 밖
}


def rule_score(e):
    road = (e["hw_rank"] / 5).clip(0, 1) * 0.7 + (e["lanes_n"].clip(1, 6) - 1) / 5 * 0.3
    road = road.where(e["ped_only"] == 0, 0.05)
    unsignal = (e["n_unsignal_crossings"].clip(0, 2) / 2)
    # 차도와 만나는 횡단 간선 자체도 노출로 본다
    unsignal = np.maximum(unsignal, e["is_crossing_edge"] * 0.5)
    inter = e["n_intersections"] / 2 * (e["hw_rank"] >= 1)
    no_zone = 1 - e["in_school_zone"]
    s = (RULE_W["road"] * road + RULE_W["unsignal"] * unsignal
         + RULE_W["intersection"] * inter + RULE_W["no_zone"] * no_zone * (e["ped_only"] == 0))
    return (s - s.min()) / (s.max() - s.min())


def main():
    e = gpd.read_file(DATA / "edges.gpkg", layer="edges")
    X = e[FEATURES].fillna({"signal_ratio": -1}).fillna(0).astype(float)
    y = e["acc_label"].astype(int)
    metrics = {"n_edges": int(len(e)), "n_pos": int(y.sum()), "features": FEATURES}

    e["rule"] = rule_score(e)
    if y.sum() < MIN_POS:
        metrics["mode"] = "rule"
        metrics["note"] = (f"사고다발지역 양성 간선이 {int(y.sum())}개로 {MIN_POS}개 미만이라 학습 모델 대신 "
                           "규칙 기반 점수식을 사용함.")
        if y.sum() > 0:
            metrics["rule_auc_vs_hotspot"] = round(float(roc_auc_score(y, e["rule"])), 3)
        e["risk"], e["risk_source"] = e["rule"], "rule"
    else:
        # 공간 그룹: 약 500m 격자
        cx, cy = e.geometry.centroid.x, e.geometry.centroid.y
        groups = (cx // 500).astype(int).astype(str) + "_" + (cy // 500).astype(int).astype(str)
        models = {
            "logistic": make_pipeline(StandardScaler(), LogisticRegression(max_iter=2000, class_weight="balanced")),
            "gbm": HistGradientBoostingClassifier(max_depth=4, learning_rate=0.05, max_iter=300, class_weight="balanced"),
        }
        oof = {}
        for name, m in models.items():
            p = np.zeros(len(e))
            for tr, te in GroupKFold(n_splits=5).split(X, y, groups):
                m.fit(X.iloc[tr], y.iloc[tr])
                p[te] = m.predict_proba(X.iloc[te])[:, 1]
            oof[name] = p
            metrics[f"auc_{name}"] = round(float(roc_auc_score(y, p)), 3)
        metrics["rule_auc_vs_hotspot"] = round(float(roc_auc_score(y, e["rule"])), 3)
        best = max(models, key=lambda k: metrics[f"auc_{k}"])
        m = models[best].fit(X, y)
        imp = permutation_importance(m, X, y, scoring="roc_auc", n_repeats=5, random_state=0)
        metrics["importance"] = dict(sorted(((f, round(float(v), 4)) for f, v in zip(FEATURES, imp.importances_mean)),
                                            key=lambda t: -t[1]))
        lr = models["logistic"].fit(X, y)
        metrics["logistic_coef"] = {f: round(float(c), 3) for f, c in zip(FEATURES, lr[-1].coef_[0])}
        prob = m.predict_proba(X)[:, 1]
        e["risk"] = pd.Series(prob).rank(pct=True).values  # 분위 → 0~1
        e["risk_source"] = best
        metrics["mode"] = best

    e["risk"] = e["risk"].round(4)
    e[["u", "v", "key", "risk", "risk_source"]].to_csv(DATA / "edge_risk.csv", index=False)
    metrics["risk_ge_0.6_share"] = round(float((e["risk"] >= 0.6).mean()), 3)
    (MODEL / "metrics.json").write_text(json.dumps(metrics, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(metrics, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
