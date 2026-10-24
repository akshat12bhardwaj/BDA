"""
Step 11e (storage part): the versioned warehouse table and its data contract (Documentation/Warehouse_Data_Contract.md).

Every attribute carries a status:
  verified            checked against an authoritative source on `verified_on`
  reported_unverified stated by a source (here OpenStreetMap contributors), not independently checked
  derived             computed by a documented rule (the rule is named in `derivation`)
  unknown             no credible source; the value is empty and must be shown as unknown

Sources in v1:
  * OpenStreetMap (pinned Geofabrik snapshot, ODbL): named public-sector storage operators (Central Warehousing
    Corporation, Food Corporation of India, state warehousing corporations) and polygon features named as cold stores.
    Location and name are `reported_unverified`; capacity, charges, availability and crop suitability are `unknown`.
  * Optional curated files Dataset/warehouses/*.csv in the contract's column layout (e.g. a licensed official list),
    validated by the same rules. None exist yet.
No contact details are collected (personal phone numbers in public registers are not republished).

Run:  python -B -m Code.routing.storage build | check
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from shapely.geometry import Polygon

from Code.routing import nodes as nd, osm
from Code.routing.router import haversine_km

VERSION = "v1"
OUT = nd.OUT / f"warehouses_{VERSION}.csv"
CURATED = Path("Dataset/warehouses")
STATUSES = {"verified", "reported_unverified", "derived", "unknown"}
CROPS = ("onion", "potato", "wheat")

# Column -> (value columns governed by the status column). Order is the published column order.
CONTRACT = {
    "name": ["name"],
    "location": ["latitude", "longitude"],
    "operator": ["operator_class"],
    "facility": ["facility_type", "storage_method"],
    "suitability": [f"suits_{c}" for c in CROPS],
    "capacity": ["capacity_total_t", "capacity_available_t", "capacity_as_of"],
    "charges": ["storage_charge_rs_per_t_month", "handling_charge_rs_per_t", "charges_as_of"],
    "availability": ["available_from"],
}
COLUMNS = (["warehouse_id"] + [c for cols in CONTRACT.values() for c in cols] + [f"{k}_status" for k in CONTRACT]
           + ["derivation", "coord_method", "source", "source_record", "licence", "retrieved_utc", "verified_on"])
OPERATORS = {"cwc", "fci", "swc", "cold_storage"}

# Keyword rules (derived values). A name must name the operator; generic "godown"/"warehouse" names are not used.
RULES = [("cwc", re.compile(r"central\s+ware\s*housing|\bcwc\b", re.I)),
         ("fci", re.compile(r"food\s+corporation\s+of\s+india|\bfci\b", re.I)),
         ("swc", re.compile(r"state\s+ware\s*hous|\b[a-z]{1,3}swc\b", re.I)),        # not "<private> Warehousing Corp."
         ("cold_storage", re.compile(r"cold\s*stor(?:e|age)", re.I))]
# Places that carry an operator's name but are not storage (staff housing, offices, roads, schools ...).
NOT_STORAGE = re.compile(r"colony|quarter|qtrs|office|road|\bmarg\b|nagar|school|hospital|park|bus\s*stop|gate|chowk|"
                         r"residen|society|apartment|flat|camp|guest\s*house|canteen|stadium|club|temple|mandir|library|auditorium|\bhall\b|palika", re.I)
NON_STORAGE_FCLASS = {"residential", "park", "school", "hospital", "playground", "recreation_ground", "cemetery"}
LAYERS = {"pois": (1,), "pois_a": (5,), "landuse_a": (5,)}     # point POIs, POI areas, landuse areas
DEDUP_KM = 0.3


def classify(name: str, layer: str) -> str | None:
    if not name or NOT_STORAGE.search(name):
        return None
    for op, rx in RULES:
        if rx.search(name):
            # cold-store names on point POIs are mostly shops (e.g. "... Cold Storage and General Store"): areas only
            return None if op == "cold_storage" and layer == "pois" else op
    return None


def _centroid(ring: np.ndarray) -> tuple[float, float]:
    c = Polygon(ring).centroid if len(ring) >= 4 else None
    return (float(c.y), float(c.x)) if c is not None and not c.is_empty else (float(ring[:, 1].mean()), float(ring[:, 0].mean()))


def osm_candidates(zones=osm.ZONES) -> pd.DataFrame:
    snap = {(r["zone"], r["member"]): r for r in osm.read_snapshot(osm.STORAGE_SNAPSHOT_FILE)}
    rows = []
    for zone in zones:
        z = osm.zone_dir(zone)
        layers = dict(LAYERS, **({"buildings_a": (5,)} if osm.buildings_subset_path(zone).exists() else {}))
        for layer, types in layers.items():
            base = f"gis_osm_{layer}_free_1"
            a = osm.read_dbf(z / f"{base}.dbf", ["osm_id", "fclass", "name"])
            ops = np.array([classify(n, layer) if f not in NON_STORAGE_FCLASS else None for n, f in zip(a["name"], a["fclass"])], object)
            keep = ops != None  # noqa: E711  (elementwise on an object array)
            first = {}
            if layer == "buildings_a":                                   # pre-filtered centroids (osm.fetch_buildings_subset)
                sub = pd.read_csv(osm.buildings_subset_path(zone))
                first = {int(r): np.array([[lon, lat]]) for r, lat, lon in sub.itertuples(index=False) if keep[int(r)]}
                types = (1,)                                             # already a single point per record
            else:
                for i, pts in osm.read_polylines(z / f"{base}.shp", keep, types):
                    first.setdefault(i, pts)                             # outer ring / the point
            rec = snap[(zone, f"{base}.shp")]
            coords = {i: ((float(p[0, 1]), float(p[0, 0])) if types == (1,) else _centroid(p)) for i, p in first.items()}
            method = {"pois": "OSM point", "buildings_a": "mean of OSM building outline vertices"}.get(layer, "centroid of OSM area")
            for i, (lat, lon) in coords.items():
                op = ops[i]
                rows.append({"warehouse_id": f"W:osm:{layer}:{a['osm_id'][i]}", "name": a["name"][i], "latitude": round(lat, 6),
                             "longitude": round(lon, 6), "operator_class": op,
                             "facility_type": "cold_storage" if op == "cold_storage" else "warehouse",
                             "storage_method": "refrigerated" if op == "cold_storage" else None,
                             "osm_fclass": a["fclass"][i], "coord_method": method,
                             "source": f"OpenStreetMap via Geofabrik {zone}-zone snapshot {osm.SNAPSHOT}",
                             "source_record": f"{layer} osm_id {a['osm_id'][i]}", "retrieved_utc": rec["retrieved_utc"]})
    df = pd.DataFrame(rows).drop_duplicates("warehouse_id")         # zones overlap at their borders
    return _dedupe(df)


def _dedupe(df: pd.DataFrame) -> pd.DataFrame:
    """One facility is often mapped twice (an area and a point, or landuse and POI area): same operator class within
    DEDUP_KM -> keep the area, then the lowest id. Distinct sites of the same operator farther apart are kept."""
    df = df.assign(_rank=(df["coord_method"] == "OSM point").astype(int)).sort_values(["_rank", "warehouse_id"]).reset_index(drop=True)
    drop = set()
    for op, g in df.groupby("operator_class"):
        idx = g.index.to_numpy()
        lat, lon = g["latitude"].to_numpy(), g["longitude"].to_numpy()
        for k, i in enumerate(idx):
            if i in drop:
                continue
            near = haversine_km(lat[k], lon[k], lat[k + 1:], lon[k + 1:]) <= DEDUP_KM
            drop.update(idx[k + 1:][near].tolist())
    return df.drop(index=list(drop)).drop(columns="_rank")


def to_contract(df: pd.DataFrame) -> pd.DataFrame:
    out = pd.DataFrame({c: df.get(c) for c in COLUMNS})
    out["name_status"] = out["location_status"] = "reported_unverified"
    out["operator_status"] = out["facility_status"] = "derived"
    out["derivation"] = ("operator, facility type and storage method from the name by keyword rules "
                         "(Code/routing/storage.py RULES); cold-store names on point POIs excluded")
    for k in ("suitability", "capacity", "charges", "availability"):
        out[f"{k}_status"] = "unknown"
    out["licence"] = osm.LICENCE
    return out[COLUMNS]


def curated() -> pd.DataFrame:
    """Curated, licensed files already in contract layout (Dataset/warehouses/*.csv). Validated, never altered."""
    files = sorted(CURATED.glob("*.csv")) if CURATED.exists() else []
    return pd.concat([pd.read_csv(f) for f in files], ignore_index=True) if files else pd.DataFrame(columns=COLUMNS)


def validate(df: pd.DataFrame) -> pd.DataFrame:
    """Raise on any contract violation; return the frame unchanged."""
    errs = []
    if list(df.columns) != COLUMNS:
        errs.append(f"columns differ from the contract: {sorted(set(df.columns) ^ set(COLUMNS))}")
    else:
        if not df["warehouse_id"].is_unique or df["warehouse_id"].isna().any():
            errs.append("warehouse_id missing or duplicated")
        lo, hi, wlo, whi = nd.INDIA_BBOX
        located = df["location_status"] != "unknown"
        if not (df.loc[located, "latitude"].between(lo, hi).all() and df.loc[located, "longitude"].between(wlo, whi).all()):
            errs.append("a coordinate outside India")
        for k, cols in CONTRACT.items():
            st = df[f"{k}_status"]
            if not st.isin(STATUSES).all():
                errs.append(f"{k}_status has values outside {STATUSES}")
            unknown = st == "unknown"
            if df.loc[unknown, cols].notna().any().any():
                errs.append(f"{k}: a value is present although its status is unknown")
            if df.loc[~unknown, cols[:1]].isna().any().any():
                errs.append(f"{k}: status says known but the value is missing")
        if (df["verified_on"].isna() & df[[f"{k}_status" for k in CONTRACT]].eq("verified").any(axis=1)).any():
            errs.append("a verified value without verified_on")
        if df["source"].isna().any() or df["licence"].isna().any():
            errs.append("a record without source or licence")
        if not df["operator_class"].dropna().isin(OPERATORS).all():
            errs.append("operator_class outside the vocabulary")
        for c in ("capacity_total_t", "capacity_available_t", "storage_charge_rs_per_t_month", "handling_charge_rs_per_t"):
            v = pd.to_numeric(df[c], errors="coerce")
            if (v < 0).any() or (df[c].notna() & v.isna()).any():
                errs.append(f"{c}: non-numeric or negative")
        cap = pd.to_numeric(df["capacity_available_t"], errors="coerce") > pd.to_numeric(df["capacity_total_t"], errors="coerce")
        if cap.any():
            errs.append("available capacity exceeds total capacity")
    if errs:
        raise ValueError("warehouse contract: " + "; ".join(errs))
    return df


def build_frame() -> pd.DataFrame:
    extra = curated()
    df = pd.concat([to_contract(osm_candidates()), extra], ignore_index=True) if len(extra) else to_contract(osm_candidates())
    return validate(df.sort_values("warehouse_id").reset_index(drop=True))


def build() -> None:
    df = build_frame()
    OUT.write_bytes(df.to_csv(index=False, lineterminator="\n").encode())
    print(f"wrote {OUT} ({len(df)} records)", df["operator_class"].value_counts().to_dict())


def check() -> None:
    osm.verify_snapshot(osm.STORAGE_SNAPSHOT_FILE)
    if OUT.read_bytes() != build_frame().to_csv(index=False, lineterminator="\n").encode():
        raise ValueError(f"{OUT} does not reproduce from the pinned snapshot")
    print("warehouse table reproduces byte for byte")


if __name__ == "__main__":
    {"build": build, "check": check}.get(sys.argv[1] if len(sys.argv) > 1 else "", lambda: sys.exit("usage: build | check"))()
