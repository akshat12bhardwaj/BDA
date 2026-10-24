"""
Step 11a: the versioned, verified node table.

Nodes are only places with a sourced, verified coordinate. Today that is the 46 district reference points that passed
the D-16 rule (geocoder admin1 = state and admin2 = district), re-validated here against the stored Phase 4 geocoder
evidence. The 2,657 mandi markets are listed with their original names but stay `unresolved`: they have no verified
coordinate, and a market is never placed at its district point.

Run:  python -B -m Code.routing.nodes build     (deterministic: a rebuild is byte-identical)
      python -B -m Code.routing.nodes check     (rebuild in memory and compare with the files on disk)
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

from Code.integration.pipeline import file_sha256

VERSION = "v1"
RESOLUTION = Path("Processed_Data/integration/weather_location_resolution.csv")
EVIDENCE = Path("Processed_Data/integration/geocoder_evidence_phase4.csv")
MANDI = [Path(f"Processed_Data/integration/mandi_integrated_{c}.parquet") for c in ("onion", "potato", "wheat")]
OUT = Path("Processed_Data/routing")
NODES = OUT / f"nodes_{VERSION}.csv"
MARKETS = OUT / f"market_nodes_{VERSION}.csv"
MANIFEST = OUT / f"nodes_manifest_{VERSION}.csv"
INDIA_BBOX = (6.0, 38.0, 68.0, 98.0)                      # lat min, lat max, lon min, lon max (mainland + islands)


def node_id(kind: str, *parts: str) -> str:
    """Stable identifier from the original names: 'D:<state>|<district>' or 'M:<state>|<district>|<market>'."""
    if any("|" in p for p in parts):
        raise ValueError(f"'|' is reserved in node ids: {parts}")
    return f"{kind}:" + "|".join(parts)


def _require(cond: bool, msg: str) -> None:
    if not cond:
        raise ValueError(f"node validation failed: {msg}")


def district_nodes() -> pd.DataFrame:
    r = pd.read_csv(RESOLUTION)
    ev = pd.read_csv(EVIDENCE)
    r = r[r["weather_status"] == "ok"]
    # The same gazetteer entry can answer several queries (aliases); evidence is matched per (state, district, id).
    cand = ev.drop_duplicates(["state", "district", "id"])[["state", "district", "id", "latitude", "longitude",
                                                             "feature_code", "admin1", "admin2", "retrieved_at_utc"]]
    m = r.merge(cand, left_on=["state", "district", "geocoder_id"], right_on=["state", "district", "id"], how="left",
                suffixes=("", "_ev"), validate="1:1")
    lo, hi, wlo, whi = INDIA_BBOX
    _require(m["id"].notna().all(), "a point without stored geocoder evidence")
    _require(m[["latitude", "longitude"]].notna().all().all(), "a point without coordinates")
    _require(((m["latitude"] - m["latitude_ev"]).abs() < 1e-9).all() and ((m["longitude"] - m["longitude_ev"]).abs() < 1e-9).all(),
             "a coordinate differs from its geocoder evidence")
    _require(m["latitude"].between(lo, hi).all() and m["longitude"].between(wlo, whi).all(), "a coordinate outside India")
    _require((m["admin1"] == m["state"]).all(), "geocoder admin1 differs from the state (D-16)")
    # Ambiguity record: other stored candidates in the same state and admin2 as the chosen one (informational).
    same = ev.merge(m[["state", "district", "admin2"]], on=["state", "district"], suffixes=("", "_chosen"))
    amb = same[(same["admin1"] == same["state"]) & (same["admin2"] == same["admin2_chosen"])].groupby(["state", "district"]).size()
    out = pd.DataFrame({
        "node_id": [node_id("D", s, d) for s, d in zip(m["state"], m["district"])],
        "node_type": "district_point", "name": m["district"], "state": m["state"], "district": m["district"],
        "crops": m["crops"], "latitude": m["latitude"], "longitude": m["longitude"],
        "coord_source": "Open-Meteo geocoding API (GeoNames gazetteer, CC BY 4.0)",
        "geocoder_id": m["geocoder_id"].astype("int64"), "geocoder_name": m["geocoder_name"], "feature_code": m["feature_code"],
        "geocoder_admin1": m["admin1"], "geocoder_admin2": m["admin2"], "resolution_status": m["resolution_status"],
        "same_district_candidates": [int(amb.get((s, d), 1)) for s, d in zip(m["state"], m["district"])],
        "verification": "passed", "verified_on": m["retrieved_at_utc"].str[:10],
        "location_meaning": "district reference point (a named place in the district), not a market, warehouse or road address",
    })
    _require(out["node_id"].is_unique and not out.duplicated(["latitude", "longitude"]).any(), "duplicate node id or coordinate")
    return out.sort_values("node_id").reset_index(drop=True)


def market_nodes() -> pd.DataFrame:
    rows = []
    for p in MANDI:
        df = pd.read_parquet(p, columns=["crop", "state", "district", "market"]).drop_duplicates()
        rows.append(df)
    mk = (pd.concat(rows).groupby(["state", "district", "market"])["crop"]
          .agg(lambda c: ",".join(sorted(set(c)))).rename("crops").reset_index())
    _require(not mk[["state", "district", "market"]].isna().any().any(), "a market with a missing name part")
    mk.insert(0, "node_id", [node_id("M", s, d, k) for s, d, k in zip(mk["state"], mk["district"], mk["market"])])
    _require(mk["node_id"].is_unique, "duplicate market id")
    return mk.assign(node_type="market", latitude=pd.NA, longitude=pd.NA, verification="unresolved",
                     reason="no verified coordinate: markets are not geocoded yet; never placed at a district point"
                     ).sort_values("node_id").reset_index(drop=True)


def _csv(df: pd.DataFrame) -> str:
    return df.to_csv(index=False, lineterminator="\n")


def build_frames() -> dict[Path, str]:
    nodes, markets = district_nodes(), market_nodes()
    files = {NODES: _csv(nodes), MARKETS: _csv(markets)}
    import hashlib
    man = pd.DataFrame([{"file": str(p).replace("\\", "/"), "role": "output", "rows": t.count("\n") - 1,
                         "sha256": hashlib.sha256(t.encode()).hexdigest()} for p, t in files.items()]
                       + [{"file": str(p).replace("\\", "/"), "role": "input", "rows": "", "sha256": file_sha256(p)}
                          for p in [RESOLUTION, EVIDENCE, *MANDI]])
    files[MANIFEST] = _csv(man)
    return files


def build() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for p, text in build_frames().items():
        p.write_bytes(text.encode())
        print(f"wrote {p} ({text.count(chr(10)) - 1} rows)")


def check() -> None:
    for p, text in build_frames().items():
        _require(p.exists() and p.read_bytes() == text.encode(), f"{p} differs from a fresh rebuild")
    print("node table reproduces byte for byte")


def load_nodes() -> pd.DataFrame:
    return pd.read_csv(NODES)


if __name__ == "__main__":
    {"build": build, "check": check}.get(sys.argv[1] if len(sys.argv) > 1 else "", lambda: sys.exit("usage: build | check"))()
