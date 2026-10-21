"""
Phase 4 — Data Integration for the selected crops (Onion, Potato, Wheat).

Builds separate integrated outputs at their own verified grains instead of one
giant daily table (see Documentation/Decision_Log.md D-15..D-22):

  mandi_integrated_<crop>.parquet   one row per raw mandi record (row-preserving),
                                    plus geographic keys, APY year keys, market code
                                    and same-day weather (NaN where not matched)
  weather_daily_panel.parquet       one row per (weather location, date)
  weather_location_resolution.csv   one row per representative location (46)
  apy_season.csv                    one row per (crop, state, district, apy_year, season)
  apy_annual.csv                    one row per (crop, state, district, apy_year)
  mandi_apy_district_year.csv       one row per (crop, apy_state, apy_district, apy_year)
  district_crosswalk.csv            one row per (crop, mandi state, mandi district)
  agrimarket_wheat_crosscheck.csv   one row per Agri Market Wheat record
  audit/*.csv                       merge log, coverage, unmatched keys, duplicates,
                                    source fingerprints, output manifest

Nothing is ever written into Dataset/. No coordinate, price, production,
arrival or weather value is created: values only move between sources via
validated many-to-one joins, and unmatched values stay missing (NaN).
"""

from __future__ import annotations

import hashlib
import logging
import re
import time
import unicodedata
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import requests

from Code.utils.data_audit import MANDI_DIR, load_mandi_file, parse_dates_fast
from Code.weather.collector import collect_weather
from Code.weather.config import (DAILY_VARIABLES, DEFAULT_END_DATE, DEFAULT_START_DATE,
                                 GEOCODING_URL, MAPPING_CACHE_PATH, RAW_WEATHER_DIR)
from Code.weather.validator import validate_weather_dataset

log = logging.getLogger("phase4_integration")

# ---------------------------------------------------------------- paths
SELECTED_CROPS_PATH = Path("Processed_Data/selected_crops.csv")
APY_PATH = Path("Dataset/crop-wise-area-production-yield.csv")
AGRI_MARKET_PATH = Path("Dataset/Agri Market Dataset.csv")
MARKET_REF_PATH = Path("Dataset/final_data.csv")
DISTRICT_ALIAS_PATH = Path("Code/integration/district_aliases.csv")
OUT_DIR = Path("Processed_Data/integration")
GEOCODER_EVIDENCE_PATH = OUT_DIR / "geocoder_evidence_phase4.csv"

# ---------------------------------------------------------------- canonical schema
MANDI_COLUMNS = {
    "State Name": "state", "District Name": "district", "Market Name": "market",
    "Variety": "variety", "Group": "commodity_group",
    "Arrivals (Tonnes)": "arrivals_tonnes",
    "Min Price (Rs./Quintal)": "min_price_rs_per_quintal",
    "Max Price (Rs./Quintal)": "max_price_rs_per_quintal",
    "Modal Price (Rs./Quintal)": "modal_price_rs_per_quintal",
    "Reported Date": "reported_date",
}
MANDI_TEXT = ["state", "district", "market", "variety", "commodity_group"]
MANDI_VALUES = ["arrivals_tonnes", "min_price_rs_per_quintal",
                "max_price_rs_per_quintal", "modal_price_rs_per_quintal"]
MANDI_KEY = MANDI_TEXT + ["reported_date"]

APY_COLUMNS = {
    "crop_name": "crop", "state_name": "state", "state_code": "state_code",
    "district_name": "district", "district_code": "district_code", "year": "apy_year",
    "season": "season", "crop_code": "crop_code", "crop_type": "crop_type",
    "area": "area_ha", "production": "production_tonnes", "yield": "yield_t_per_ha",
}
APY_UNITS = {"area_unit": "Hectare", "production_unit": "Tonnes", "yield_unit": "Tonnes/Hectare"}
APY_SEASON_KEY = ["crop", "state", "district", "apy_year", "season"]
APY_ANNUAL_KEY = ["crop", "state", "district", "apy_year"]

# Mandi state spellings that differ from APY's (both verified present in APY).
STATE_ALIASES = {"chattisgarh": "chhattisgarh", "uttrakhand": "uttarakhand"}

# Extra geocoder search terms for the Phase 3 locations that failed or were
# mis-mapped: the official APY (DES, GoI) district spelling, or the district
# headquarters town when the district name itself returns no place. A search
# term never decides acceptance — the admin1/admin2 rule below does.
GEOCODER_QUERIES = {
    ("Punjab", "Bhatinda"): ["Bathinda"],
    ("Uttar Pradesh", "Bulandshahar"): ["Bulandshahr"],
    ("Kerala", "Palakad"): ["Palakkad"],
    ("Maharashtra", "Ahmednagar"): ["Ahilyanagar", "Ahmadnagar"],
    ("West Bengal", "Coochbehar"): ["Cooch Behar", "Koch Bihar"],
    ("Rajasthan", "Ganganagar"): ["Sri Ganganagar", "Shri Ganganagar"],
    ("Gujarat", "Sabarkantha"): ["Sabar Kantha", "Himatnagar"],
    ("Maharashtra", "Buldhana"): ["Buldana"],
    ("Gujarat", "Banaskanth"): ["Banas Kantha", "Banaskantha", "Palanpur"],
    ("Gujarat", "Junagarh"): ["Junagadh"],
    ("Punjab", "Ferozpur"): ["Ferozepur", "Firozpur"],
}
# Geocoder admin2 (district) names that are the same district under an older
# or official name, where the APY crosswalk does not already provide it.
ADMIN2_EQUIVALENTS = {
    ("Kerala", "Alappuzha"): "Alleppey",
    ("West Bengal", "Burdwan"): "Purba Bardhaman",  # point is Bardhaman town, the pre-split HQ
    ("Uttar Pradesh", "Kanpur"): "Kanpur Nagar",     # point is Kanpur city
    ("Punjab", "Ferozpur"): "Firozpur",
}

WEATHER_START, WEATHER_END = pd.Timestamp(DEFAULT_START_DATE), pd.Timestamp(DEFAULT_END_DATE)


class IntegrationError(RuntimeError):
    """Raised when an integration validation rule is violated."""


# ---------------------------------------------------------------- helpers
def norm_place(name) -> str:
    """Accent-, case-, space- and punctuation-insensitive place key ('Hoshiārpur' -> 'hoshiarpur')."""
    s = unicodedata.normalize("NFKD", str(name)).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]", "", s.lower())


def norm_admin2(name) -> str:
    """Geocoder admin2 values carry suffixes like 'Ludhiana district'; drop them."""
    if pd.isna(name):
        return ""
    return norm_place(re.sub(r"\bdistrict\b", "", str(name), flags=re.I))


def agri_year_start(dates: pd.Series) -> pd.Series:
    """Agricultural year (July-June) start: 2022-07-01..2023-06-30 -> 2022, i.e. APY '2022-2023'."""
    return (dates.dt.year - (dates.dt.month < 7).astype("Int64")).astype("Int64")


def agri_year_label(start: pd.Series) -> pd.Series:
    labels = {y: f"{y}-{y + 1}" for y in start.dropna().unique()}
    return start.map(labels).astype("category")


def checked_merge(left: pd.DataFrame, right: pd.DataFrame, *, on, how: str, validate: str,
                  step: str, merge_log: list, **kwargs) -> pd.DataFrame:
    """pandas merge + cardinality validation + before/after row-count logging."""
    try:
        out = left.merge(right, on=on, how=how, validate=validate, **kwargs)
    except pd.errors.MergeError as e:
        raise IntegrationError(f"[{step}] join cardinality violated ({validate}) on {on}: {e}") from e
    if how == "left" and validate in ("m:1", "1:1") and len(out) != len(left):
        raise IntegrationError(f"[{step}] left join changed row count {len(left)} -> {len(out)}")
    merge_log.append({"step": step, "how": how, "validate": validate, "keys": ",".join(on),
                      "left_rows": len(left), "right_rows": len(right), "result_rows": len(out)})
    log.info("merge %-45s %s %s left=%d right=%d -> %d", step, how, validate,
             len(left), len(right), len(out))
    return out


def file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def frame_fingerprint(df: pd.DataFrame) -> str:
    """Order-sensitive content hash of a dataframe (for re-run consistency checks)."""
    return hashlib.sha256(pd.util.hash_pandas_object(df, index=False).values.tobytes()).hexdigest()


def load_selected_crops() -> list[str]:
    crops = pd.read_csv(SELECTED_CROPS_PATH)["crop"].tolist()
    if sorted(crops) != ["Onion", "Potato", "Wheat"]:
        raise IntegrationError(f"Phase 2 selection changed unexpectedly: {crops}")
    return crops


# ---------------------------------------------------------------- APY
def load_apy_season(crops: list[str], apy_path: Path = APY_PATH) -> pd.DataFrame:
    """APY rows for the selected crops at their native (crop, state, district, apy_year, season) grain."""
    raw = pd.read_csv(apy_path)
    raw = raw[raw["crop_name"].isin(crops)]
    for col, unit in APY_UNITS.items():
        units = set(raw[col].unique())
        if units != {unit}:
            raise IntegrationError(f"APY {col} expected only '{unit}', found {units}")
    if not raw["year"].str.fullmatch(r"\d{4}-\d{4}").all():
        raise IntegrationError("APY year values are not all of the form 'YYYY-YYYY'")
    df = raw.rename(columns=APY_COLUMNS)[list(APY_COLUMNS.values())]
    if df.duplicated(APY_SEASON_KEY).any():
        raise IntegrationError("APY season key (crop, state, district, apy_year, season) is not unique")
    return df.sort_values(APY_SEASON_KEY).reset_index(drop=True)


def apy_annual(season: pd.DataFrame) -> pd.DataFrame:
    """
    Annual district totals. APY publishes a 'Total' season row equal to the sum
    of the other seasons (verified on 99.9% of groups), so:
      - group has a Total row            -> use it as-is ("total_row")
      - group has exactly one season row -> that row is the annual figure ("single_season")
      - several seasons but no Total     -> left missing ("ambiguous_multi_season_no_total"),
        because Whole Year + Rabi/Kharif may overlap; summing could double count.
    The original apy_year label is preserved unchanged.
    """
    g = season.groupby(APY_ANNUAL_KEY, observed=True)
    seasons = g["season"].agg(lambda s: "|".join(sorted(s))).rename("seasons_reported")
    n = g.size().rename("n_season_rows")
    base = pd.concat([seasons, n], axis=1).reset_index()

    total = season[season["season"] == "Total"]
    single = season[season["season"] != "Total"].merge(base[base["n_season_rows"] == 1][APY_ANNUAL_KEY],
                                                       on=APY_ANNUAL_KEY)
    vals = pd.concat([total.assign(annual_method="total_row"),
                      single.assign(annual_method="single_season")])
    vals = vals[APY_ANNUAL_KEY + ["state_code", "district_code", "area_ha", "production_tonnes",
                                 "yield_t_per_ha", "annual_method"]]
    out = base.merge(vals, on=APY_ANNUAL_KEY, how="left", validate="1:1")
    out["annual_method"] = out["annual_method"].fillna("ambiguous_multi_season_no_total")
    return out.sort_values(APY_ANNUAL_KEY).reset_index(drop=True)


# ---------------------------------------------------------------- geography
def build_district_crosswalk(mandi_districts: pd.DataFrame, apy: pd.DataFrame,
                             aliases: pd.DataFrame) -> pd.DataFrame:
    """
    Map each mandi (state, district) to an APY (state, district), in this order:
      reviewed_alias / excluded_by_review  (Code/integration/district_aliases.csv)
      exact_normalized                     (case/space/punctuation-insensitive equality)
      parenthetical_part                   ('Ropar (Rupnagar)' -> 'Rupnagar'), only if unique
      state_not_in_apy / unmatched
    No fuzzy similarity is auto-accepted.
    """
    apy_d = apy[["state", "district"]].drop_duplicates()
    apy_state_by_norm = {norm_place(s): s for s in apy_d["state"].unique()}
    apy_by_state: dict[str, dict[str, str]] = {}
    for s, d in apy_d.itertuples(index=False):
        apy_by_state.setdefault(s, {})[norm_place(d)] = d
    alias = {(r.mandi_state, r.mandi_district): r for r in aliases.itertuples(index=False)}

    rows = []
    for state, district in mandi_districts[["state", "district"]].drop_duplicates().itertuples(index=False):
        ns = norm_place(state)
        apy_state = apy_state_by_norm.get(STATE_ALIASES.get(ns, ns))
        target, method, basis = None, "unmatched", ""
        if apy_state is None:
            method = "state_not_in_apy"
        elif (state, district) in alias:
            a = alias[(state, district)]
            basis = a.basis
            if pd.isna(a.apy_district) or not str(a.apy_district).strip():
                method = "excluded_by_review"
            else:
                if norm_place(a.apy_district) not in apy_by_state[apy_state]:
                    raise IntegrationError(f"Alias target '{a.apy_district}' not found in APY {apy_state}")
                target, method = apy_by_state[apy_state][norm_place(a.apy_district)], "reviewed_alias"
        elif norm_place(district) in apy_by_state[apy_state]:
            target, method = apy_by_state[apy_state][norm_place(district)], "exact_normalized"
        else:
            parts = {norm_place(p) for p in re.split(r"[()/]", district) if p.strip()}
            hits = {apy_by_state[apy_state][p] for p in parts if p in apy_by_state[apy_state]}
            if len(hits) == 1:
                target, method = hits.pop(), "parenthetical_part"
        rows.append({"state": state, "district": district,
                     "apy_state": apy_state if target else None, "apy_district": target,
                     "apy_district_match": method, "alias_basis": basis})
    cw = pd.DataFrame(rows)
    if cw.duplicated(["state", "district"]).any():
        raise IntegrationError("district crosswalk is not unique on (state, district)")
    return cw


def capture_geocoder_evidence(locations: pd.DataFrame, out_path: Path = GEOCODER_EVIDENCE_PATH,
                              pause: float = 0.4) -> pd.DataFrame:
    """One-time network step: store every geocoder candidate for every search term, as evidence."""
    rows = []
    retrieved = datetime.now(timezone.utc).isoformat(timespec="seconds")
    for state, district in locations[["state", "district"]].itertuples(index=False):
        for q in [district] + GEOCODER_QUERIES.get((state, district), []):
            resp = requests.get(GEOCODING_URL, params={"name": q, "count": 10, "country": "IN"}, timeout=20)
            resp.raise_for_status()
            for c in resp.json().get("results", []):
                rows.append({"state": state, "district": district, "query": q,
                             **{k: c.get(k) for k in ["id", "name", "latitude", "longitude",
                                                      "feature_code", "admin1", "admin2", "population"]},
                             "retrieved_at_utc": retrieved})
            time.sleep(pause)
    ev = pd.DataFrame(rows)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    ev.to_csv(out_path, index=False)
    return ev


def haversine_km(lat1, lon1, lat2, lon2) -> float:
    p1, p2 = np.radians(lat1), np.radians(lat2)
    a = (np.sin((p2 - p1) / 2) ** 2
         + np.cos(p1) * np.cos(p2) * np.sin(np.radians(lon2 - lon1) / 2) ** 2)
    return float(6371.0 * 2 * np.arcsin(np.sqrt(a)))


def resolve_weather_locations(phase3: pd.DataFrame, evidence: pd.DataFrame,
                              crosswalk: pd.DataFrame) -> pd.DataFrame:
    """
    Accept a geocoder candidate for (state, district) only if its admin1 equals
    the state AND its admin2 equals the mandi district, its APY official name,
    or a documented ADMIN2_EQUIVALENTS name. Among accepted candidates prefer a
    district seat (PPLA/PPLA2), then the largest population.
      phase3_verified          Phase 3 coordinate is one of the accepted candidates
      phase3_rejected_corrected Phase 3 coordinate failed the rule; best accepted candidate used
      phase4_resolved_alias    unresolved in Phase 3; accepted candidate found via alias search
      unresolved               no candidate passes the rule (no coordinate assigned)
    """
    apy_name = {(r.state, r.district): r.apy_district for r in crosswalk.itertuples(index=False)
                if isinstance(r.apy_district, str)}
    out = []
    for r in phase3.itertuples(index=False):
        key = (r.state, r.district)
        accepted_names = {norm_place(r.district)}
        for extra in (apy_name.get(key), ADMIN2_EQUIVALENTS.get(key)):
            if extra:
                accepted_names.add(norm_place(extra))
        cand = evidence[(evidence["state"] == r.state) & (evidence["district"] == r.district)].copy()
        cand = cand[(cand["admin1"].map(norm_place) == norm_place(r.state))
                    & (cand["admin2"].map(norm_admin2).isin(accepted_names))]
        cand = cand.drop_duplicates("id")
        cand["_seat"] = cand["feature_code"].isin(["PPLA", "PPLA2"])
        cand = cand.sort_values(["_seat", "population"], ascending=False, na_position="last")

        row = {"state": r.state, "district": r.district, "crops": r.crops, "mandi_records_phase3": r.mandi_records,
               "phase3_status": r.mapping_status, "phase3_latitude": r.latitude, "phase3_longitude": r.longitude}
        p3_ok = (r.mapping_status == "mapped" and not cand.empty and
                 ((cand["latitude"] - r.latitude).abs().lt(1e-4)
                  & (cand["longitude"] - r.longitude).abs().lt(1e-4)).any())
        if p3_ok:
            best = cand[((cand["latitude"] - r.latitude).abs() < 1e-4)
                        & ((cand["longitude"] - r.longitude).abs() < 1e-4)].iloc[0]
            status = "phase3_verified"
        elif not cand.empty:
            best = cand.iloc[0]
            status = "phase3_rejected_corrected" if r.mapping_status == "mapped" else "phase4_resolved_alias"
        else:
            best, status = None, "unresolved"
        if best is not None:
            row.update({"latitude": best["latitude"], "longitude": best["longitude"],
                        "geocoder_name": best["name"], "geocoder_query": best["query"],
                        "geocoder_feature_code": best["feature_code"], "geocoder_admin1": best["admin1"],
                        "geocoder_admin2": best["admin2"], "geocoder_id": best["id"]})
        if r.mapping_status == "mapped" and status != "phase3_verified":
            p3 = evidence[(evidence["state"] == r.state) & (evidence["district"] == r.district)
                          & ((evidence["latitude"] - r.latitude).abs() < 1e-4)]
            row["phase3_point_admin2"] = p3["admin2"].iloc[0] if len(p3) else None
            if best is not None:
                row["correction_distance_km"] = round(haversine_km(r.latitude, r.longitude,
                                                                   best["latitude"], best["longitude"]), 1)
        row["resolution_status"] = status
        out.append(row)
    res = pd.DataFrame(out)
    res["weather_file"] = None
    return res


def collect_resolved_weather(resolution: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Reuse Phase 3 cache files for verified locations; fetch (or reuse the Phase 4
    cache for) resolved/corrected ones via the existing collector + validator.
    A corrected location gets a new cache file so the Phase 3 file stays untouched.
    Returns (resolution with weather_file/weather_status, validation report).
    """
    reports = []
    res = resolution.copy()
    res["weather_status"] = None
    for i, r in res.iterrows():
        if r["resolution_status"] == "unresolved":
            res.at[i, "weather_status"] = "no_coordinate"
            continue
        cache_district = r["district"] + (" corrected" if r["resolution_status"] == "phase3_rejected_corrected" else "")
        m = collect_weather(r["state"], cache_district, r["latitude"], r["longitude"],
                            DEFAULT_START_DATE, DEFAULT_END_DATE, DAILY_VARIABLES)
        df = m.pop("dataframe")
        if not m["status"].startswith("ok"):
            res.at[i, "weather_status"] = m["status"]
            continue
        rep = validate_weather_dataset(df, DEFAULT_START_DATE, DEFAULT_END_DATE, DAILY_VARIABLES)
        ok = (rep["date_range_ok"] and rep["duplicate_dates"] == 0 and rep["missing_dates_count"] == 0
              and not rep["missing_variable_columns"])
        reports.append({"state": r["state"], "district": r["district"], "cache_file": m["cache_file"],
                        "from_cache": m["from_cache"], "rows": rep["rows"],
                        "missing_dates": rep["missing_dates_count"], "duplicate_dates": rep["duplicate_dates"],
                        "missing_values": sum(rep["missing_value_counts"].values()),
                        "out_of_range_counts": str(rep["out_of_range_counts"]), "passed": ok})
        res.at[i, "weather_file"] = m["cache_file"]
        res.at[i, "weather_status"] = "ok" if ok else "failed_validation"
    return res, pd.DataFrame(reports)


def build_weather_panel(resolution: pd.DataFrame) -> pd.DataFrame:
    """Daily weather at (weather_state, weather_district, date) grain for usable locations."""
    frames = []
    for r in resolution[resolution["weather_status"] == "ok"].itertuples(index=False):
        w = pd.read_csv(r.weather_file, parse_dates=["date"])[["date"] + DAILY_VARIABLES]
        w.insert(0, "weather_district", r.district)
        w.insert(0, "weather_state", r.state)
        frames.append(w)
    panel = pd.concat(frames, ignore_index=True)
    if panel.duplicated(["weather_state", "weather_district", "date"]).any():
        raise IntegrationError("weather panel key (weather_state, weather_district, date) is not unique")
    return panel.rename(columns={"date": "reported_date"})


# ---------------------------------------------------------------- mandi
def load_mandi_crop(crop: str, mandi_dir: Path = MANDI_DIR) -> pd.DataFrame:
    """Load one crop file with categorical text columns; one row per raw record, source_row kept."""
    text_raw = [k for k, v in MANDI_COLUMNS.items() if v in MANDI_TEXT + ["reported_date"]]
    df = load_mandi_file(f"{crop}.csv", mandi_dir=mandi_dir, dtype={c: "category" for c in text_raw})
    missing = set(MANDI_COLUMNS) - set(df.columns)
    if missing:
        raise IntegrationError(f"{crop}.csv is missing expected columns {sorted(missing)}")
    df = df[list(MANDI_COLUMNS)].rename(columns=MANDI_COLUMNS)
    # Parse each distinct date string once (format detected per file; see D-09).
    cats = df["reported_date"].cat.categories
    parsed = parse_dates_fast(pd.Series(cats.astype(str))).to_numpy()
    codes = df["reported_date"].cat.codes.to_numpy()
    dates = parsed[codes]
    dates[codes < 0] = np.datetime64("NaT")  # missing raw date stays missing
    df["reported_date"] = pd.Series(dates, index=df.index)
    df.insert(0, "source_row", np.arange(len(df), dtype="int64"))
    df.insert(1, "crop", pd.Categorical([crop] * len(df)))
    return df


def flag_duplicate_keys(df: pd.DataFrame) -> pd.DataFrame:
    """
    Mark (not drop) rows that share the record key (state, district, market,
    variety, group, date). exact_duplicate = all copies carry identical values;
    conflicting = copies disagree. Treatment is left to Phase 5.
    """
    vhash = pd.util.hash_pandas_object(df[MANDI_VALUES], index=False)
    g = df.assign(_v=vhash.values).groupby(MANDI_KEY, observed=True, dropna=False)["_v"]
    count = g.transform("size")
    nvals = g.transform("nunique")
    df["dup_key_count"] = count.astype("int32").values
    df["dup_type"] = pd.Categorical(np.select([count == 1, nvals == 1],
                                              ["unique", "exact_duplicate"], "conflicting"))
    return df


def market_codes(df: pd.DataFrame, ref_path: Path = MARKET_REF_PATH) -> pd.DataFrame:
    """Market_code from final_data.csv on normalized (state, district, market); ambiguous keys stay uncoded."""
    ref = pd.read_csv(ref_path)
    ref["_k"] = ref["State"].map(norm_place) + "|" + ref["District"].map(norm_place) + "|" + ref["Market"].map(norm_place)
    n = ref["_k"].value_counts()
    uniq = ref[ref["_k"].map(n) == 1].set_index("_k")["Market_code"]
    m = df[["state", "district", "market"]].drop_duplicates().astype(str)
    m["_k"] = m["state"].map(norm_place) + "|" + m["district"].map(norm_place) + "|" + m["market"].map(norm_place)
    m["market_code"] = m["_k"].map(uniq).astype("Int64")
    m["market_code_status"] = np.where(m["market_code"].notna(), "unique_match",
                                       np.where(m["_k"].map(n).fillna(0) > 1, "ambiguous_in_reference", "unmatched"))
    return m.drop(columns="_k")


def integrate_mandi_crop(crop: str, crosswalk: pd.DataFrame, apy_ann: pd.DataFrame,
                         resolution: pd.DataFrame, panel: pd.DataFrame, merge_log: list,
                         mandi_dir: Path = MANDI_DIR) -> pd.DataFrame:
    df = flag_duplicate_keys(load_mandi_crop(crop, mandi_dir))
    n0 = len(df)

    # Temporal keys: July-June agricultural year (APY label) and the previous one
    # (the latest APY year that could have been completed before the record date).
    start = agri_year_start(df["reported_date"])
    df["apy_year"] = agri_year_label(start)
    df["apy_year_lag1"] = agri_year_label(start - 1)

    keys = ["state", "district"]
    for c in keys + ["market"]:
        df[c] = df[c].astype(str)

    cw = crosswalk[crosswalk["crop"] == crop][keys + ["apy_state", "apy_district", "apy_district_match"]]
    df = checked_merge(df, cw, on=keys, how="left", validate="m:1",
                       step=f"{crop}: mandi x district_crosswalk", merge_log=merge_log)

    avail = apy_ann[(apy_ann["crop"] == crop) & apy_ann["production_tonnes"].notna()][["state", "district", "apy_year"]]
    avail = avail.rename(columns={"state": "apy_state", "district": "apy_district"}).assign(apy_annual_available=True)
    df["apy_year"] = df["apy_year"].astype(str).replace("nan", np.nan)
    df = checked_merge(df, avail, on=["apy_state", "apy_district", "apy_year"], how="left", validate="m:1",
                       step=f"{crop}: mandi x apy_annual (availability flag)", merge_log=merge_log)
    df["apy_annual_available"] = df["apy_annual_available"].eq(True)

    df = checked_merge(df, market_codes(df), on=["state", "district", "market"], how="left", validate="m:1",
                       step=f"{crop}: mandi x final_data market reference", merge_log=merge_log)

    loc = resolution[resolution["weather_status"] == "ok"][keys + ["resolution_status"]]
    loc = loc.rename(columns={"resolution_status": "weather_location_method"})
    loc = loc.assign(weather_state=loc["state"], weather_district=loc["district"])
    df = checked_merge(df, loc, on=keys, how="left", validate="m:1",
                       step=f"{crop}: mandi x weather_location (exact state+district)", merge_log=merge_log)
    df = checked_merge(df, panel, on=["weather_state", "weather_district", "reported_date"], how="left",
                       validate="m:1", step=f"{crop}: mandi x weather_daily_panel (same day)", merge_log=merge_log)

    located = df["weather_location_method"].notna()
    in_window = df["reported_date"].between(WEATHER_START, WEATHER_END)
    df["weather_match"] = np.select(
        [located & in_window, located & ~in_window],
        ["exact_district", "exact_district_outside_weather_window"], "no_weather_location")
    if df.loc[df["weather_match"] == "exact_district", DAILY_VARIABLES].isna().any().any():
        raise IntegrationError(f"{crop}: matched weather rows have missing weather values")
    if df.loc[df["weather_match"] != "exact_district", DAILY_VARIABLES].notna().any().any():
        raise IntegrationError(f"{crop}: weather values present on rows without a weather match")

    if len(df) != n0:
        raise IntegrationError(f"{crop}: row count changed during integration {n0} -> {len(df)}")
    for c in ["state", "district", "market", "apy_state", "apy_district", "apy_district_match", "apy_year",
              "market_code_status", "weather_location_method", "weather_state", "weather_district", "weather_match"]:
        df[c] = df[c].astype("category")
    return df.sort_values("source_row").reset_index(drop=True)


def mandi_district_year(df: pd.DataFrame, crop_min: pd.Timestamp, crop_max: pd.Timestamp) -> pd.DataFrame:
    """Mandi activity aggregated to the APY grain (crop, apy_state, apy_district, apy_year)."""
    sub = df[df["apy_district"].notna() & df["apy_year"].notna()]
    g = sub.groupby(["crop", "apy_state", "apy_district", "apy_year"], observed=True)
    out = g.agg(mandi_records=("source_row", "size"), mandi_markets=("market", "nunique"),
                mandi_arrivals_tonnes_sum=("arrivals_tonnes", "sum"),
                mandi_modal_price_median=("modal_price_rs_per_quintal", "median"),
                mandi_first_date=("reported_date", "min"), mandi_last_date=("reported_date", "max"),
                mandi_duplicate_key_rows=("dup_type", lambda s: int((s != "unique").sum()))).reset_index()
    ystart = out["apy_year"].astype(str).str[:4].astype(int)
    out["mandi_partial_year"] = ((pd.to_datetime(ystart.astype(str) + "-07-01") < crop_min)
                                 | (pd.to_datetime((ystart + 1).astype(str) + "-06-30") > crop_max))
    for c in ["crop", "apy_state", "apy_district", "apy_year"]:
        out[c] = out[c].astype(str)
    return out


# ---------------------------------------------------------------- Agri Market cross-check
def agrimarket_wheat_crosscheck(wheat: pd.DataFrame, merge_log: list,
                                path: Path = AGRI_MARKET_PATH) -> tuple[pd.DataFrame, dict]:
    """
    Agri Market Wheat rows (Maharashtra / Amravati division only) compared with
    national-mandi Wheat rows on the same (district, market, variety, date).
    Only mandi keys with a single record (dup_type == unique) are compared.
    """
    raw = pd.read_csv(path, dtype={"Arrivals (Tonnes)": str})
    am = raw[raw["Commodity"] == "Wheat"].rename(columns={c: MANDI_COLUMNS[c] for c in MANDI_COLUMNS})
    am = am.rename(columns={"Commodity": "commodity"})
    am["reported_date"] = pd.to_datetime(am["reported_date"], format="%m/%d/%Y", errors="raise")
    am["arrivals_raw"] = am["arrivals_tonnes"]
    am["arrivals_tonnes"] = pd.to_numeric(am["arrivals_raw"].str.replace(",", "", regex=False), errors="coerce")
    am_key = ["district", "market", "variety", "reported_date"]
    if am.duplicated(am_key).any():
        raise IntegrationError("Agri Market Wheat key (district, market, variety, date) is not unique")
    for c in ["district", "market", "variety"]:
        am["_" + c] = am[c].map(norm_place)

    m = wheat[(wheat["state"] == "Maharashtra") & (wheat["dup_type"] == "unique")
              & (wheat["reported_date"] >= am["reported_date"].min())]
    m = m[["district", "market", "variety", "reported_date"] + MANDI_VALUES + ["source_row"]].copy()
    for c in ["district", "market", "variety"]:
        m["_" + c] = m[c].astype(str).map(norm_place)
    m = m.drop(columns=["district", "market", "variety"]).add_prefix("mandi_")
    m = m.rename(columns={"mandi__district": "_district", "mandi__market": "_market",
                          "mandi__variety": "_variety", "mandi_reported_date": "reported_date"})
    out = checked_merge(am, m, on=["_district", "_market", "_variety", "reported_date"], how="left",
                        validate="1:1", step="Wheat: agri_market x mandi (district, market, variety, date)",
                        merge_log=merge_log)
    out = out.drop(columns=["_district", "_market", "_variety"])
    out["source"] = "Agri Market Dataset (Maharashtra, Amravati division only)"
    mandi_max = wheat["reported_date"].max()
    out["within_mandi_coverage"] = out["reported_date"] <= mandi_max
    out["matched_in_mandi"] = out["mandi_source_row"].notna()
    out["modal_price_diff"] = out["modal_price_rs_per_quintal"] - out["mandi_modal_price_rs_per_quintal"]
    cov = out[out["within_mandi_coverage"]]
    mt = cov[cov["matched_in_mandi"]]
    summary = {
        "agri_market_wheat_rows": len(out), "agri_market_other_commodity_rows_out_of_scope": int(len(raw) - len(out)),
        "rows_within_mandi_date_coverage": len(cov), "rows_matched_in_mandi": len(mt),
        "match_rate_within_coverage": round(len(mt) / len(cov), 4) if len(cov) else np.nan,
        "modal_price_exact_equal_share": round(float((mt["modal_price_diff"] == 0).mean()), 4) if len(mt) else np.nan,
        "modal_price_median_abs_diff": float(mt["modal_price_diff"].abs().median()) if len(mt) else np.nan,
        "arrivals_exact_equal_share": round(float((mt["arrivals_tonnes"] == mt["mandi_arrivals_tonnes"]).mean()), 4)
        if len(mt) else np.nan,
        "arrivals_unparseable_raw_values": int(out["arrivals_tonnes"].isna().sum()),
        "arrivals_parsed_by_removing_thousands_separator": int(
            out["arrivals_raw"].str.contains(",", na=False).sum()),
    }
    return out, summary


# ---------------------------------------------------------------- orchestration
def source_paths(crops: list[str], mandi_dir: Path = MANDI_DIR) -> list[Path]:
    return ([mandi_dir / f"{c}.csv" for c in crops] + [APY_PATH, AGRI_MARKET_PATH, MARKET_REF_PATH,
                                                     MAPPING_CACHE_PATH, SELECTED_CROPS_PATH]
            + sorted(RAW_WEATHER_DIR.glob("*.csv")))


def run_pipeline(out_dir: Path = OUT_DIR, crops: list[str] | None = None,
                 mandi_dir: Path = MANDI_DIR) -> dict:
    """Run Phase 4 end-to-end; returns a dict of in-memory summary tables."""
    t0 = time.time()
    out_dir = Path(out_dir)
    audit_dir = out_dir / "audit"
    audit_dir.mkdir(parents=True, exist_ok=True)
    fh = logging.FileHandler(audit_dir / "integration_run.log", mode="w", encoding="utf-8")
    fh.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    log.addHandler(fh)
    log.setLevel(logging.INFO)
    try:
        return _run(out_dir, audit_dir, crops or load_selected_crops(), mandi_dir, t0)
    finally:
        log.removeHandler(fh)
        fh.close()


def _run(out_dir, audit_dir, crops, mandi_dir, t0) -> dict:
    merge_log: list[dict] = []
    if not set(crops) <= {"Onion", "Potato", "Wheat"}:
        raise IntegrationError(f"Only Onion/Potato/Wheat are in scope, got {crops}")
    srcs = source_paths(crops, mandi_dir)
    before = {str(p): file_sha256(p) for p in srcs}
    log.info("Decision: crops in scope = %s (Phase 2 selection)", crops)

    # --- APY
    apy_all = load_apy_season(load_selected_crops())  # district universe must not depend on a crop subset
    apy_s = apy_all[apy_all["crop"].isin(crops)].reset_index(drop=True)
    apy_a = apy_annual(apy_s)
    log.info("APY season rows=%d, annual rows=%d; annual_method counts=%s",
             len(apy_s), len(apy_a), apy_a["annual_method"].value_counts().to_dict())

    # --- district crosswalk (per crop: mandi districts differ by crop file)
    aliases = pd.read_csv(DISTRICT_ALIAS_PATH)
    if aliases.duplicated(["mandi_state", "mandi_district"]).any():
        raise IntegrationError("district_aliases.csv has duplicate (mandi_state, mandi_district) rows")
    district_lists = {}
    for crop in crops:
        d = pd.read_csv(mandi_dir / f"{crop}.csv", usecols=["State Name", "District Name"])
        district_lists[crop] = d.value_counts().rename("mandi_records").reset_index().rename(
            columns={"State Name": "state", "District Name": "district"})
    # District identity is geographic, so match against APY districts of all selected crops;
    # crop-specific APY absence is captured later by apy_annual_available.
    crosswalk = pd.concat([build_district_crosswalk(district_lists[c], apy_all, aliases)
                           .assign(crop=c) for c in crops], ignore_index=True)
    crosswalk = crosswalk.merge(pd.concat([v.assign(crop=k) for k, v in district_lists.items()]),
                                on=["crop", "state", "district"], how="left", validate="1:1")

    # --- weather locations
    phase3 = pd.read_csv(MAPPING_CACHE_PATH)
    evidence = (pd.read_csv(GEOCODER_EVIDENCE_PATH) if GEOCODER_EVIDENCE_PATH.exists()
                else capture_geocoder_evidence(phase3))
    union_cw = crosswalk.drop_duplicates(["state", "district"])
    resolution = resolve_weather_locations(phase3, evidence, union_cw)
    resolution, wx_validation = collect_resolved_weather(resolution)
    panel = build_weather_panel(resolution)
    log.info("Weather locations: %s", resolution["resolution_status"].value_counts().to_dict())

    # --- mandi per crop
    summaries, dy_frames, cov_rows, dup_rows, unmatched = {}, [], [], [], []
    wheat_df = None
    for crop in crops:
        df = integrate_mandi_crop(crop, crosswalk, apy_a, resolution, panel, merge_log, mandi_dir)
        df.to_parquet(out_dir / f"mandi_integrated_{crop.lower()}.parquet", index=False)
        dy_frames.append(mandi_district_year(df, df["reported_date"].min(), df["reported_date"].max()))
        n = len(df)
        for dim in ["weather_match", "weather_location_method", "apy_district_match",
                    "apy_annual_available", "market_code_status", "dup_type"]:
            vc = df[dim].astype(str).value_counts(dropna=False)
            cov_rows += [{"crop": crop, "dimension": dim, "value": k, "records": int(v),
                          "share": round(v / n, 6)} for k, v in vc.items()]
        dup_rows.append({"crop": crop, "records": n,
                         **{f"rows_{k}": int(v) for k, v in df["dup_type"].value_counts().items()},
                         "duplicate_key_groups": int(df.loc[df["dup_key_count"] > 1, MANDI_KEY]
                                                     .drop_duplicates().shape[0]),
                         "unparsed_dates": int(df["reported_date"].isna().sum()),
                         "first_date": df["reported_date"].min(), "last_date": df["reported_date"].max()})
        nowx = df[df["weather_match"] == "no_weather_location"]
        states_with_loc = set(resolution.loc[resolution["weather_status"] == "ok", "state"])
        cov_rows.append({"crop": crop, "dimension": "no_weather_location_in_state_with_a_weather_location",
                         "value": "count", "records": int(nowx["state"].isin(states_with_loc).sum()),
                         "share": round(nowx["state"].isin(states_with_loc).sum() / n, 6)})
        for key_type, mask, cols in [
            ("apy_district", df["apy_district"].isna(), ["state", "district", "apy_district_match"]),
            ("weather_location", df["weather_match"] == "no_weather_location", ["state", "district"]),
            ("market_code", df["market_code"].isna(), ["state", "district", "market", "market_code_status"]),
        ]:
            u = df[mask].groupby(cols, observed=True).size().rename("records").reset_index()
            unmatched.append(u.assign(crop=crop, key_type=key_type))
        if crop == "Wheat":
            wheat_df = df
        del df

    # --- APY x mandi at the APY grain (1:1, outer: keeps APY-only and mandi-only years)
    dy = pd.concat(dy_frames, ignore_index=True)
    apy_link = apy_a.rename(columns={"state": "apy_state", "district": "apy_district"})
    mandi_apy = checked_merge(dy, apy_link, on=["crop", "apy_state", "apy_district", "apy_year"], how="outer",
                              validate="1:1", step="mandi_district_year x apy_annual", merge_log=merge_log,
                              indicator="link_status")
    mandi_apy["link_status"] = mandi_apy["link_status"].map(
        {"both": "mandi_and_apy", "left_only": "mandi_only", "right_only": "apy_only"})
    mandi_apy = mandi_apy.sort_values(["crop", "apy_state", "apy_district", "apy_year"]).reset_index(drop=True)

    # --- Agri Market cross-check (Wheat only)
    agri, agri_summary = (agrimarket_wheat_crosscheck(wheat_df, merge_log) if wheat_df is not None
                          else (pd.DataFrame(), {}))
    del wheat_df

    # --- write outputs
    outputs = {
        "weather_daily_panel.parquet": (panel, "weather_state, weather_district, reported_date"),
        "weather_location_resolution.csv": (resolution, "state, district"),
        "apy_season.csv": (apy_s, ", ".join(APY_SEASON_KEY)),
        "apy_annual.csv": (apy_a, ", ".join(APY_ANNUAL_KEY)),
        "mandi_apy_district_year.csv": (mandi_apy, "crop, apy_state, apy_district, apy_year"),
        "district_crosswalk.csv": (crosswalk, "crop, state, district"),
    }
    if len(agri):
        outputs["agrimarket_wheat_crosscheck.csv"] = (agri, "district, market, variety, reported_date")
    for name, (frame, _) in outputs.items():
        p = out_dir / name
        frame.to_parquet(p, index=False) if name.endswith(".parquet") else frame.to_csv(p, index=False)

    audits = {
        "merge_log.csv": pd.DataFrame(merge_log),
        "coverage_summary.csv": pd.DataFrame(cov_rows),
        "duplicate_key_summary.csv": pd.DataFrame(dup_rows),
        "unmatched_keys.csv": pd.concat(unmatched, ignore_index=True).sort_values(
            ["key_type", "crop", "records"], ascending=[True, True, False]),
        "weather_resolution_validation.csv": wx_validation,
        "agrimarket_crosscheck_summary.csv": pd.DataFrame([agri_summary]),
    }
    for name, frame in audits.items():
        frame.to_csv(audit_dir / name, index=False)

    # --- output manifest (grain, rows, content hash for re-run consistency)
    manifest = []
    for crop in crops:
        p = out_dir / f"mandi_integrated_{crop.lower()}.parquet"
        f = pd.read_parquet(p)
        manifest.append({"file": p.name, "grain": "one row per raw mandi record (source_row)",
                         "rows": len(f), "columns": f.shape[1], "content_sha256": frame_fingerprint(f)})
    for name, (frame, grain) in outputs.items():
        f = pd.read_parquet(out_dir / name) if name.endswith(".parquet") else pd.read_csv(out_dir / name)
        manifest.append({"file": name, "grain": grain, "rows": len(f), "columns": f.shape[1],
                         "content_sha256": frame_fingerprint(frame)})
    pd.DataFrame(manifest).to_csv(audit_dir / "output_manifest.csv", index=False)

    after = {p: file_sha256(Path(p)) for p in before}
    fp = pd.DataFrame([{"path": p, "sha256_before": before[p], "sha256_after": after[p],
                        "unchanged": before[p] == after[p]} for p in before])
    fp.to_csv(audit_dir / "source_fingerprints.csv", index=False)
    if not fp["unchanged"].all():
        raise IntegrationError(f"Source files changed during the run: {fp.loc[~fp['unchanged'], 'path'].tolist()}")
    log.info("Phase 4 pipeline finished in %.1fs", time.time() - t0)
    return {"merge_log": audits["merge_log.csv"], "coverage": audits["coverage_summary.csv"],
            "duplicates": audits["duplicate_key_summary.csv"], "resolution": resolution,
            "crosswalk": crosswalk, "apy_annual": apy_a, "mandi_apy": mandi_apy,
            "agri_summary": agri_summary, "manifest": pd.DataFrame(manifest), "fingerprints": fp,
            "seconds": round(time.time() - t0, 1)}
