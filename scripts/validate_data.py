"""Validate public snapshots before publishing. Never reads or prints API keys."""
import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def reject_constant(value):
    raise ValueError("Non-finite JSON number")

def validate():
    data = ROOT / "data"
    full = json.loads((data / "index.json").read_text(encoding="utf-8"), parse_constant=reject_constant)
    lite = json.loads((data / "index-lite.json").read_text(encoding="utf-8"), parse_constant=reject_constant)
    with (data / "complexes.csv").open(encoding="utf-8-sig", newline="") as f:
        expected = {row["complex_id"] for row in csv.DictReader(f)}
    assert full["meta"]["generated"] == lite["meta"]["generated"], "Snapshot generation mismatch"
    assert {c["id"] for c in full["complexes"]} == expected, "Missing complex in full snapshot"
    assert {c["id"] for c in lite["complexes"]} == expected, "Missing complex in light snapshot"
    schools = {s["school_id"] for s in full["schools"]}
    assert len(schools) == len(full["schools"]), "Duplicate schools"
    combinations = 0
    for complex_ in full["complexes"]:
        assert set(complex_["results"]) == schools, "Missing school route"
        for result in complex_["results"].values():
            assert result["walk"]["path"], "Empty walking route"
            assert result["walk"]["time_min"] >= 0, "Negative route time"
            assert 0 <= result["index"] <= 100, "Invalid index"
            combinations += 1
    assert (data / "index-lite.json").stat().st_size < (data / "index.json").stat().st_size / 3, "Light snapshot too large"
    print(f"Validated {len(expected)} apartments, {len(schools)} schools, {combinations} walking routes; matching light/full snapshots.")

if __name__ == "__main__":
    validate()

