"""
Read-only JSON API for the React frontend. Every value comes from the tested loaders in Code/app/data.py, which
enforce the project's data boundaries (market history <= 2020-06-30; price predictions = validation only; arrivals =
validation + the one-time 2021-2022 test; production values <= 2018-19 with reserved years as counts only; no 2023+).
Nothing here trains, re-scores or writes anything.

Run from the project root (project interpreter; requirements.txt has FastAPI and Uvicorn):
    C:\\Python313\\python.exe -m uvicorn Code.api.main:app --host 127.0.0.1 --port 8000
"""

from __future__ import annotations

import json
from functools import lru_cache
from typing import Any, Literal

import pandas as pd
from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel

from Code.api.logistics import router as logistics
from Code.app import data as d
from Code.bigdata.mapreduce_demo import LABEL as MR_LABEL

app = FastAPI(title="Mandi Insights API", version="1.0.0",
              description="Read-only access to validated BDA outputs. Historical data only; nothing is live.")
app.include_router(logistics)            # /api/routes*, /api/warehouses* (Phase 11 outputs)

Crop = Literal["Onion", "Potato", "Wheat"]
YEAR = r"^\d{4}-\d{4}$"
Records = list[dict[str, Any]]


def records(df: pd.DataFrame) -> Records:
    """JSON-safe rows: NaN -> null, timestamps -> ISO dates."""
    return json.loads(df.to_json(orient="records", date_format="iso", date_unit="s"))


# ---------------------------------------------------------------- cached loaders (read-only)
weekly = lru_cache(maxsize=1)(d.weekly_state)
top_districts = lru_cache(maxsize=1)(d.top_districts)
locations = lru_cache(maxsize=1)(d.verified_locations)
production = lru_cache(maxsize=1)(d.production_design)
reserved_counts = lru_cache(maxsize=1)(d.production_reserved_counts)
price_metrics = lru_cache(maxsize=1)(d.price_metrics)
arrivals_metrics = lru_cache(maxsize=1)(d.arrivals_metrics)
bigdata = lru_cache(maxsize=1)(d.bigdata)


def _crop_states(crop: str) -> list[str]:
    s = d.state_year_summary(weekly(), crop)
    return s[s["agri_year"] == d.LATEST_FULL_YEAR].sort_values("arrivals_tonnes", ascending=False)["state"].tolist()


def _require_predictions(kind: str) -> None:
    missing = d.missing_prediction_files(kind)
    if missing:
        raise HTTPException(503, detail={"message": "prediction files are not present in this checkout",
                                         "missing": missing, "see": "README.md (Data missing from a fresh clone)"})


def _horizon(h: int) -> int:
    if h not in d.HORIZONS:                         # query strings arrive as text, so check the value explicitly
        raise HTTPException(422, f"horizon must be one of {list(d.HORIZONS)}")
    return h


def _series(state: str, district: str, market: str, variety: str) -> tuple:
    return (state, district, market, variety)


# ---------------------------------------------------------------- schemas
class Health(BaseModel):
    status: str
    market_history_end: str
    production_values_end: str
    live_data: bool


class Meta(BaseModel):
    crops: list[str]
    horizons: list[int]
    states_by_crop: dict[str, list[str]]
    market_years: list[str]
    production_years: list[str]
    latest_full_year: str
    verified_locations: int
    predictions_available: dict[str, bool]


class Coverage(BaseModel):
    first_week: str
    last_week: str
    states_reporting: int
    pipeline_cross_check_passed: bool


class Overview(BaseModel):
    crop: str
    state: str
    kpis: dict[str, Any]
    reports_processed: int
    coverage: Coverage


# ---------------------------------------------------------------- endpoints
@app.get("/api/health", response_model=Health)
def health() -> Health:
    return Health(status="ok", market_history_end=d.SPARK_END.date().isoformat(), production_values_end=d.DESIGN_END,
                  live_data=False)


@app.get("/api/meta", response_model=Meta)
def meta() -> Meta:
    return Meta(crops=d.CROPS, horizons=list(d.HORIZONS), states_by_crop={c: _crop_states(c) for c in d.CROPS},
                market_years=sorted(weekly()["agri_year"].unique(), reverse=True),
                production_years=sorted(production()["source_apy_year"].unique(), reverse=True),
                latest_full_year=d.LATEST_FULL_YEAR, verified_locations=len(locations()),
                predictions_available={k: not d.missing_prediction_files(k) for k in ("price", "arrivals")})


@app.get("/api/overview", response_model=Overview)
def overview(crop: Crop, state: str | None = None) -> Overview:
    states = _crop_states(crop)
    state = state or states[0]
    if state not in states:
        raise HTTPException(404, f"no {crop} arrivals for '{state}' in {d.LATEST_FULL_YEAR}")
    w = weekly()
    hist = w[(w["crop"] == crop) & (w["state"] == state)]
    qc = bigdata()["quality_checks"]
    reports = int(qc[(qc["check"] == "rows_read_all_years") & (qc["crop"] == crop)]["value"].astype(int).iloc[0])
    return Overview(crop=crop, state=state, kpis=d.overview_kpis(w, crop, state), reports_processed=reports,
                    coverage=Coverage(first_week=hist["week_start"].min().date().isoformat(),
                                      last_week=hist["week_start"].max().date().isoformat(),
                                      states_reporting=int(w[w["crop"] == crop]["state"].nunique()),
                                      pipeline_cross_check_passed=int(bigdata()["parity_report"]["mismatches"].sum()) == 0))


@app.get("/api/markets/weekly")
def market_weekly(crop: Crop, state: str) -> Records:
    """Weekly median modal price (Rs/quintal), arrivals (t) and markets reporting for one crop and state."""
    w = weekly()
    out = w[(w["crop"] == crop) & (w["state"] == state)]
    if out.empty:
        raise HTTPException(404, f"no weekly {crop} data for '{state}'")
    return records(out[["week_start", "records", "markets", "arrivals_tonnes_sum", "modal_price_median"]])


@app.get("/api/markets/states")
def market_states(crop: Crop, year: str = Query(d.LATEST_FULL_YEAR, pattern=YEAR)) -> Records:
    s = d.state_year_summary(weekly(), crop)
    out = s[s["agri_year"] == year].sort_values("arrivals_tonnes", ascending=False)
    if out.empty:
        raise HTTPException(404, f"no {crop} market data for {year}")
    return records(out)


@app.get("/api/markets/yearly")
def market_yearly(crop: Crop, states: str = Query(..., description="comma-separated state names")) -> Records:
    wanted = [x.strip() for x in states.split(",") if x.strip()]
    s = d.state_year_summary(weekly(), crop)
    return records(s[s["state"].isin(wanted)].sort_values(["state", "agri_year"]))


@app.get("/api/markets/top-districts")
def market_top_districts(crop: Crop, year: str = Query(d.LATEST_FULL_YEAR, pattern=YEAR)) -> Records:
    q = top_districts()
    return records(q[(q["crop"] == crop) & (q["apy_year"] == year)].sort_values("arrivals_rank"))


@app.get("/api/production")
def production_rows(crop: Crop, year: str = Query(..., pattern=YEAR),
                    basis: Literal["verified_total", "whole_year_row", "single_named_season"] = "verified_total",
                    quality: str = "ok,annotated") -> dict[str, Any]:
    """District production as published, design window only (source years <= 2018-19)."""
    if year > d.DESIGN_END:
        raise HTTPException(403, f"source year {year} is reserved: only counts are published (see /api/production/reserved)")
    classes = [q for q in quality.split(",") if q in ("ok", "annotated", "review")]
    p = production()
    rows = p[(p["crop"] == crop) & (p["source_apy_year"] == year)]
    sub = rows[(rows["annual_comparability"] == basis) & rows["pq_class"].isin(classes)]
    cols = ["apy_state", "apy_district", "production_tonnes", "area_ha", "yield_t_per_ha", "pq_class", "pq_reasons"]
    return {"year": year, "basis": basis, "provider_query_pending": bool(rows["pq_reasons"].fillna("")
                                                                       .str.contains("provider_query_pending").any()),
            "rows": records(sub[cols].sort_values("production_tonnes", ascending=False))}


@app.get("/api/production/reserved")
def production_reserved() -> dict[str, Any]:
    return {"message": "Reserved source years: counts per quality class only; values are not published.",
            "counts": records(reserved_counts())}


@app.get("/api/outlook/prices/summary")
def price_summary() -> dict[str, Any]:
    m = price_metrics()
    t = m["test"]
    onion = t[(t["crop"] == "Onion") & (t["horizon_weeks"] == 1) & (t["period"] == "test_combined")]
    return {"baseline_kept": int((t.drop_duplicates(["crop", "horizon_weeks"])["approach"] == "persistence").sum()),
            "cases": int(len(t.drop_duplicates(["crop", "horizon_weeks"]))),
            "onion_1w_test_change_pct": float(onion["rel_mae_improvement_pct"].iloc[0]),
            "test": records(t), "validation": records(m["validation"])}


@app.get("/api/outlook/prices/series-options")
def price_series_options(crop: Crop, horizon: int) -> Records:
    _horizon(horizon)
    _require_predictions("price")
    return records(d.price_series(crop, horizon))


@app.get("/api/outlook/prices/series")
def price_series(crop: Crop, horizon: int, state: str, district: str, market: str, variety: str,
                 config: Literal["no_weather", "weather"] = "no_weather") -> Records:
    _horizon(horizon)
    _require_predictions("price")
    out = d.price_predictions(crop, horizon, _series(state, district, market, variety), config)
    if out.empty:
        raise HTTPException(404, "no validation predictions for that series")
    return records(out)


@app.get("/api/outlook/arrivals/summary")
def arrivals_summary() -> dict[str, Any]:
    m = arrivals_metrics()
    t = m["test"]
    cells = t[(t["population"] == "primary") & (t["period"] != "test_combined")]["rel_log_mae_improvement_pct"]
    return {"cells": int(len(cells)), "cells_better": int((cells > 0).sum()), "min_improvement_pct": float(cells.min()),
            "max_improvement_pct": float(cells.max()), "test": records(t[t["population"] == "primary"]),
            "selection": records(m["selection"])}


@app.get("/api/outlook/arrivals/series-options")
def arrivals_series_options(crop: Crop, horizon: int) -> Records:
    _horizon(horizon)
    _require_predictions("arrivals")
    return records(d.arrivals_series(crop, horizon))


@app.get("/api/outlook/arrivals/series")
def arrivals_series(crop: Crop, horizon: int, state: str, district: str, market: str, variety: str,
                    period: Literal["val_2019", "val_2020", "test_2021", "test_2022"] = "test_2022") -> Records:
    _horizon(horizon)
    _require_predictions("arrivals")
    out = d.arrivals_predictions(crop, horizon, _series(state, district, market, variety))
    out = out[out["period"] == period].reset_index(drop=True).reset_index(names="week_no")
    if out.empty:
        raise HTTPException(404, "no predictions for that series and period")
    return records(out[["week_no", "period", "observed", "persistence", "hgb_conservative"]])


@app.get("/api/locations")
def location_list() -> Records:
    """The 46 verified district reference points. District centres, not market, warehouse or route locations."""
    return records(locations().reset_index(names="id")[["id", "state", "district", "crops", "latitude", "longitude",
                                                        "resolution_status"]])


@app.get("/api/locations/activity")
def location_activity(crop: Crop) -> Records:
    """Verified points with the crop's 2019-20 district activity (arrivals t, reports, markets, median price)."""
    return records(d.location_activity(crop))


@app.get("/api/locations/{location_id}/climate")
def location_climate(location_id: int) -> dict[str, Any]:
    locs = locations()
    if not 0 <= location_id < len(locs):
        raise HTTPException(404, "unknown location id")
    r = locs.iloc[location_id]
    return {"state": r["state"], "district": r["district"], "kind": "historical", "period": "2001-2022",
            "source": "Open-Meteo historical archive (CC BY 4.0)", "months": records(d.location_climate(r["weather_file"]))}


@app.get("/api/about")
def about() -> dict[str, Any]:
    bd = bigdata()
    man = bd["run_manifest"].set_index("name")["value"]
    log = bd["run_log"]
    qc = bd["quality_checks"]
    return {"sources": [
                {"data": "Mandi prices and arrivals", "source": "Daily market reports (open government data)",
                 "coverage": "Oct 2000 - Jun 2020 shown here"},
                {"data": "District production (APY)", "source": "Directorate of Economics & Statistics",
                 "coverage": "Values to 2018-19; later years counts only"},
                {"data": "Historical weather", "source": "Open-Meteo archive (CC BY 4.0)",
                 "coverage": "2001-2022 at 46 verified district points"},
                {"data": "Forecast results", "source": "Stored project outputs",
                 "coverage": "Validation 2019-2020; one-time test 2021-2022"}],
            "spark": {"version": man["spark"], "java": man["java"], "window": man["window"], "note": man["note"],
                      "mapreduce_label": MR_LABEL, "rows_read": int(qc[qc["check"] == "rows_read_all_years"]["value"].astype(int).sum()),
                      "last_run_seconds": float(log[log["stage"] == "total"]["seconds"].iloc[-1]),
                      "parity": records(bd["parity_report"]),
                      "quality": records(qc.pivot(index="check", columns="crop", values="value").reset_index())},
            "reserved_production": production_reserved()}
