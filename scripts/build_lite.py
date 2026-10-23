"""Build matching full/light browser snapshots without route coordinate duplication."""
import json
from pathlib import Path

HEAVY = {"path", "risk_segments", "shortest", "access_path", "egress_path", "ride_path",
         "walk_to_board", "walk_from_alight", "bus_path", "walk_paths"}

def lightweight(value):
    if isinstance(value, dict):
        return {k: lightweight(v) for k, v in value.items() if k not in HEAVY}
    if isinstance(value, list):
        return [lightweight(v) for v in value]
    return value

def write_indexes(directory, snapshot):
    directory = Path(directory)
    # Serialize both before replacing either; reject NaN and Infinity.
    full = json.dumps(snapshot, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
    lite = json.dumps(lightweight(snapshot), ensure_ascii=False, separators=(",", ":"), allow_nan=False)
    for name, text in (("index.json", full), ("index-lite.json", lite)):
        (directory / (name + ".tmp")).write_text(text, encoding="utf-8")
    for name in ("index.json", "index-lite.json"):
        (directory / (name + ".tmp")).replace(directory / name)

