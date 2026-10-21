"""
Reusable, crop-agnostic Open-Meteo Historical Weather Archive collector.

Generalizes Code/test_openmeteo.py (Phase 1 finding: worked for one
hardcoded location/date range, no caching, minimal error handling) into a
batch collector with caching, retries, and response validation. Works for
any (state, district, latitude, longitude) location — nothing here is
specific to Onion/Potato/Wheat.
"""

from __future__ import annotations

import re
import time
from datetime import datetime, timezone

import pandas as pd
import requests

from Code.weather.config import ARCHIVE_URL, TIMEZONE, RAW_WEATHER_DIR


def _cache_path(state: str, district: str):
    safe = re.sub(r"[^A-Za-z0-9]+", "_", f"{state}_{district}").strip("_")
    return RAW_WEATHER_DIR / f"{safe}.csv"


def collect_weather(
    state: str,
    district: str,
    latitude: float,
    longitude: float,
    start_date: str,
    end_date: str,
    variables: list[str],
    timeout: int = 30,
    retries: int = 3,
    force_refresh: bool = False,
) -> dict:
    """
    Fetch (or load from cache) daily historical weather for one location.
    Returns a manifest dict; the dataframe itself is written to
    Processed_Data/weather/raw/<state>_<district>.csv and also returned
    under manifest["dataframe"] for immediate use in the same run.
    """
    RAW_WEATHER_DIR.mkdir(parents=True, exist_ok=True)
    cache_file = _cache_path(state, district)

    manifest = {
        "state": state, "district": district, "latitude": latitude, "longitude": longitude,
        "start_date": start_date, "end_date": end_date, "variables": ",".join(variables),
        "source": "Open-Meteo Historical Weather Archive API",
        "cache_file": str(cache_file), "from_cache": False,
        "status": None, "rows": 0, "retrieved_at_utc": None,
    }

    if cache_file.exists() and not force_refresh:
        df = pd.read_csv(cache_file, parse_dates=["date"])
        manifest.update({"from_cache": True, "status": "ok (cache)", "rows": len(df)})
        manifest["dataframe"] = df
        return manifest

    last_error = None
    for attempt in range(retries):
        try:
            resp = requests.get(
                ARCHIVE_URL,
                params={
                    "latitude": latitude, "longitude": longitude,
                    "start_date": start_date, "end_date": end_date,
                    "daily": variables, "timezone": TIMEZONE,
                },
                timeout=timeout,
            )
            if resp.status_code == 429:
                # Open-Meteo's free-tier per-minute request limit — wait out
                # the window rather than retrying immediately, which would
                # just fail again.
                last_error = f"HTTP 429: {resp.text[:200]}"
                time.sleep(65)
                continue
            if resp.status_code != 200:
                last_error = f"HTTP {resp.status_code}: {resp.text[:200]}"
                time.sleep(2 ** attempt)
                continue

            payload = resp.json()
            daily = payload.get("daily")
            if not daily or "time" not in daily:
                last_error = "response missing 'daily' block"
                time.sleep(2 ** attempt)
                continue

            df = pd.DataFrame(daily).rename(columns={"time": "date"})
            df["date"] = pd.to_datetime(df["date"])
            df.insert(1, "latitude", payload.get("latitude"))
            df.insert(2, "longitude", payload.get("longitude"))
            df.insert(0, "state", state)
            df.insert(1, "district", district)

            df.to_csv(cache_file, index=False)
            manifest.update({
                "status": "ok (fetched)", "rows": len(df),
                "retrieved_at_utc": datetime.now(timezone.utc).isoformat(),
            })
            manifest["dataframe"] = df
            return manifest

        except requests.exceptions.RequestException as e:
            last_error = str(e)
            time.sleep(2 ** attempt)

    manifest.update({"status": f"failed: {last_error}", "dataframe": pd.DataFrame()})
    return manifest
