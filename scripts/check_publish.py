"""Fail closed if automated publication contains anything outside public analysis outputs."""
import os
import subprocess
from urllib.parse import quote, quote_plus

PUBLIC = {"data/complexes.csv", "data/schools.csv", "data/index.json", "data/index-lite.json",
          "data/priority.csv", "data/priority_bus.csv", "data/priority_segments.csv",
          "data/apartments_fetch_status.json", "data/schools_fetch_status.json", "data/raw/bus.json"}

def check():
    paths = subprocess.check_output(["git", "diff", "--cached", "--name-only"], text=True).splitlines()
    if not set(paths) <= PUBLIC:
        raise SystemExit("Publication blocked: unexpected file path.")
    values = [v for k, v in os.environ.items()
              if any(word in k.upper() for word in ("KEY", "SECRET", "TOKEN")) and len(v) >= 8]
    variants = {value.encode() for v in values for value in (v, quote(v, safe=""), quote_plus(v))}
    for path in paths:
        blob = subprocess.check_output(["git", "show", ":" + path])
        if any(secret in blob for secret in variants) or b"-----BEGIN PRIVATE KEY" in blob:
            raise SystemExit("Publication blocked: credential-like content detected.")
    print("Public file allowlist and credential checks passed.")

if __name__ == "__main__":
    check()

