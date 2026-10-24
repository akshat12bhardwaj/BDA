"""
Read-only routing and warehouse endpoints over the versioned Phase 11 outputs in Processed_Data/routing/.

Nothing is computed live: routes come from the precomputed OD matrix (Code/routing/pipeline.py), warehouses from the
contract table (Code/routing/storage.py). Missing outputs give an honest "not built" body, never invented numbers.
"""

from __future__ import annotations

import json
from functools import lru_cache
from typing import Any, Literal

import pandas as pd
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from Code.routing import nodes as nd, osm, pipeline as pl, storage as st

router = APIRouter(prefix="/api")
Objective = Literal["shortest", "fastest"]
Operator = Literal["cwc", "fci", "swc", "cold_storage"]
NODE_WAREHOUSE = pl.OUT / f"node_warehouse_{pl.VERSION}.csv"
ATTRIBUTION = "Road network and facility locations © OpenStreetMap contributors (ODbL 1.0), extracts by Geofabrik"


def _records(df: pd.DataFrame) -> list[dict[str, Any]]:
    return json.loads(df.to_json(orient="records"))


@lru_cache(maxsize=1)
def od() -> pd.DataFrame | None:
    return pd.read_csv(pl.OD) if pl.OD.exists() else None


@lru_cache(maxsize=1)
def geometry() -> pd.DataFrame | None:
    return pd.read_parquet(pl.GEOMETRY).set_index(["origin_id", "dest_id", "objective"]) if pl.GEOMETRY.exists() else None


@lru_cache(maxsize=1)
def routing_nodes() -> pd.DataFrame:
    n = nd.load_nodes()[["node_id", "name", "state", "district", "crops", "latitude", "longitude", "verification", "location_meaning"]]
    if pl.SNAP.exists():
        n = n.merge(pd.read_csv(pl.SNAP)[["node_id", "access_gap_km", "status"]], on="node_id", how="left")
    return n.rename(columns={"status": "network_status"})


@lru_cache(maxsize=1)
def warehouses() -> pd.DataFrame | None:
    return pd.read_csv(st.OUT) if st.OUT.exists() else None


@lru_cache(maxsize=1)
def node_warehouse() -> pd.DataFrame | None:
    return pd.read_csv(NODE_WAREHOUSE) if NODE_WAREHOUSE.exists() else None


def _snapshot_date() -> str:
    s = osm.SNAPSHOT
    return f"20{s[:2]}-{s[2:4]}-{s[4:]}"


class Capability(BaseModel):
    capability: str
    status: Literal["available", "estimate", "planned", "missing_data"]
    detail: str


class RoutingMeta(BaseModel):
    available: bool
    message: str
    provider: str
    snapshot_date: str
    attribution: str
    pairs: dict[str, int]
    speed_assumptions: list[dict[str, Any]]
    capabilities: list[Capability]


def _routing_capabilities(ready: bool) -> list[Capability]:
    return [
        Capability(capability="Verified district reference points", status="available", detail="46 points (Step 11a node table v1)"),
        Capability(capability="Road network and road distances", status="available" if ready else "planned",
                   detail=f"OSM motorway-to-tertiary roads, snapshot {_snapshot_date()}" if ready else "run Code.routing.pipeline build"),
        Capability(capability="Travel time", status="estimate" if ready else "planned",
                   detail="assumed free-flow goods-vehicle speeds by road class; no traffic or stops"),
        Capability(capability="Market coordinates", status="planned", detail="2,657 markets listed, none geocoded yet"),
        Capability(capability="Transport cost", status="missing_data", detail="no sourced Rs per tonne-km"),
        Capability(capability="Live traffic, closures, road condition", status="missing_data", detail="no free India-wide feed"),
        Capability(capability="Weather along the route", status="planned", detail="historical climatology is available for the 46 points only"),
    ]


@router.get("/routes", response_model=RoutingMeta)
def routes_meta() -> RoutingMeta:
    m = od()
    ready = m is not None
    pairs = (m[m["objective"] == "shortest"]["status"].value_counts().to_dict() if ready else {})
    speeds = _records(pd.read_csv(pl.SPEEDS)) if pl.SPEEDS.exists() else []
    msg = ("Road routes between verified district points, computed on the OpenStreetMap road network (motorway to tertiary). Distances are "
           "network distances; travel times are estimates from assumed speeds. Costs, traffic and road condition are not "
           "available." if ready else "Road routes have not been built in this checkout (python -B -m Code.routing.pipeline build).")
    return RoutingMeta(available=ready, message=msg, provider=pl.PROVIDER, snapshot_date=_snapshot_date(), attribution=ATTRIBUTION,
                       pairs={k: int(v) for k, v in pairs.items()}, speed_assumptions=speeds, capabilities=_routing_capabilities(ready))


@router.get("/routes/nodes")
def route_nodes() -> list[dict[str, Any]]:
    return _records(routing_nodes())


def _nearby(node_id: str, limit: int = 5) -> list[dict[str, Any]]:
    nw_ = node_warehouse()
    wh = warehouses()
    if nw_ is None or wh is None:
        return []
    near = nw_[nw_["node_id"] == node_id].sort_values("road_distance_km").head(limit)
    return _records(near.merge(wh[["warehouse_id", "name", "operator_class", "facility_type", "location_status"]], on="warehouse_id"))


@router.get("/routes/route")
def route(origin: str, dest: str, objective: Objective = "shortest") -> dict[str, Any]:
    m = od()
    ids = set(routing_nodes()["node_id"])
    for nid in (origin, dest):
        if nid not in ids:
            raise HTTPException(404, f"unknown or unverified node '{nid}'")
    if origin == dest:
        raise HTTPException(422, "origin and destination are the same node")
    if m is None:
        raise HTTPException(503, detail={"message": "routing outputs are not built in this checkout",
                                         "see": "python -B -m Code.routing.pipeline build"})
    rows = m[(m["origin_id"] == origin) & (m["dest_id"] == dest)].set_index("objective")
    r = rows.loc[objective]
    body = {k: (None if pd.isna(v) else v) for k, v in r.items()}
    body.update(origin_id=origin, dest_id=dest, objective=objective, snapshot_date=_snapshot_date(), attribution=ATTRIBUTION,
                labels={"road_distance_km": "network distance between the points' nearest two-way road vertices",
                        "travel_time_h": "estimate from assumed speeds (see speed assumptions); no traffic or stops",
                        "straight_line_km": "great-circle distance; NOT a road distance",
                        "access_gap_km": "straight-line gap from the point to the road network; not included in the road distance"},
                alternatives={o: {"road_distance_km": None if pd.isna(x["road_distance_km"]) else x["road_distance_km"],
                                  "travel_time_h": None if pd.isna(x["travel_time_h"]) else x["travel_time_h"]}
                              for o, x in rows.iterrows()},
                transport_cost={"available": False, "reason": "no sourced transport cost (Rs per tonne-km) in the project"},
                geometry=None, geometry_note=None,
                nearby_warehouses={"origin": _nearby(origin), "dest": _nearby(dest)})
    if r["status"] == "ok":
        g = geometry()
        if g is None:
            body["geometry_note"] = "route geometry file not built in this checkout; distances are still valid"
        else:
            body["geometry"] = json.loads(g.loc[(origin, dest, objective), "coordinates"])
    return body


# ---------------------------------------------------------------- warehouses
class WarehouseMeta(BaseModel):
    available: bool
    message: str
    records: int
    by_operator: dict[str, int]
    field_status: dict[str, dict[str, int]]
    sources: list[str]
    attribution: str
    capabilities: list[Capability]


WAREHOUSE_CAPABILITIES = [
    Capability(capability="Facility identity and location", status="available",
               detail="OpenStreetMap, reported by contributors; not independently verified"),
    Capability(capability="Operator and facility type", status="estimate", detail="derived from the facility name by documented keyword rules"),
    Capability(capability="Capacity (total / available)", status="missing_data", detail="no licensed source with capacities"),
    Capability(capability="Storage and handling charges", status="missing_data", detail="no published tariffs collected"),
    Capability(capability="Crop suitability", status="missing_data", detail="not stated by any source in the table"),
    Capability(capability="Availability dates and contacts", status="missing_data", detail="not collected"),
    Capability(capability="Official registers (WDRA)", status="missing_data",
               detail="public lists are dated (2016-2019) and marked 'All rights reserved': reuse permission needed"),
]


@router.get("/warehouses", response_model=WarehouseMeta)
def warehouses_meta() -> WarehouseMeta:
    wh = warehouses()
    if wh is None:
        return WarehouseMeta(available=False, message="The warehouse table is not built (python -B -m Code.routing.storage build).",
                             records=0, by_operator={}, field_status={}, sources=[], attribution=ATTRIBUTION,
                             capabilities=WAREHOUSE_CAPABILITIES)
    status = {k: {s: int(v) for s, v in wh[f"{k}_status"].value_counts().items()} for k in st.CONTRACT}
    return WarehouseMeta(
        available=len(wh) > 0, records=len(wh), by_operator={k: int(v) for k, v in wh["operator_class"].value_counts().items()},
        message=(f"{len(wh)} storage facilities mapped in OpenStreetMap. Names and locations are reported by OSM contributors "
                 "and not verified; capacity, charges, availability and crop suitability are unknown."),
        field_status=status, sources=sorted(wh["source"].str.replace(r" via Geofabrik .*", "", regex=True).unique()),
        attribution=ATTRIBUTION, capabilities=WAREHOUSE_CAPABILITIES)


@router.get("/warehouses/list")
def warehouse_list(q: str = Query("", max_length=80), operator: Operator | None = None,
                   crop: Literal["onion", "potato", "wheat"] | None = None,
                   near: str | None = None, radius_km: float = Query(100, gt=0, le=500)) -> dict[str, Any]:
    wh = warehouses()
    if wh is None:
        return {"records": [], "note": "warehouse table not built"}
    out = wh
    if q.strip():
        out = out[out["name"].str.contains(q.strip(), case=False, regex=False)]
    if operator:
        out = out[out["operator_class"] == operator]
    note = None
    if crop:
        known = out["suitability_status"] != "unknown"
        out = out[known & (out[f"suits_{crop}"] == True)]  # noqa: E712
        if out.empty:
            note = f"no facility has a sourced {crop} suitability; suitability is unknown for every record"
    if near:
        if near not in set(routing_nodes()["node_id"]):
            raise HTTPException(404, f"unknown node '{near}'")
        nw_ = node_warehouse()
        if nw_ is None:
            raise HTTPException(503, "road distances to warehouses are not built (python -B -m Code.routing.pipeline build)")
        d = nw_[(nw_["node_id"] == near) & (nw_["road_distance_km"] <= radius_km)]
        out = out.merge(d[["warehouse_id", "road_distance_km", "travel_time_h", "warehouse_access_gap_km"]], on="warehouse_id")
        out = out.sort_values("road_distance_km")
    cols = ["warehouse_id", "name", "latitude", "longitude", "operator_class", "facility_type", "location_status",
            "capacity_status", "charges_status"] + [c for c in ("road_distance_km", "travel_time_h", "warehouse_access_gap_km") if c in out]
    return {"records": _records(out[cols]), "note": note}


@router.get("/warehouses/{warehouse_id}")
def warehouse_detail(warehouse_id: str) -> dict[str, Any]:
    wh = warehouses()
    if wh is None:
        raise HTTPException(503, "warehouse table not built")
    r = wh[wh["warehouse_id"] == warehouse_id]
    if r.empty:
        raise HTTPException(404, "unknown warehouse id")
    rec = _records(r)[0]
    rec["fields"] = {k: {"status": rec[f"{k}_status"], "values": {c: rec[c] for c in cols}} for k, cols in st.CONTRACT.items()}
    return rec
