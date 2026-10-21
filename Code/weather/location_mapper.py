"""
Maps project geography (State, District) to a representative weather
coordinate, using the Open-Meteo Geocoding API (https://geocoding-api.open-meteo.com)
as the public, reproducible, key-less coordinate source.

No coordinate is ever invented: if the geocoding API returns no result, or
returns a result whose state does not match the requested state, the
location is recorded as unresolved rather than guessed.
"""

from __future__ import annotations

import time
import unicodedata

import requests

from Code.weather.config import GEOCODING_URL


def _normalize_state(name: str) -> str:
    s = unicodedata.normalize("NFKD", str(name)).lower().strip()
    return "".join(ch for ch in s if ch.isalnum())


def geocode_district(state: str, district: str, timeout: int = 15, retries: int = 2) -> dict:
    """
    Look up a representative coordinate for (state, district) via the
    Open-Meteo Geocoding API. Returns a dict with mapping_status one of
    "mapped" or "unresolved" — never fabricates a coordinate.
    """
    result = {
        "state": state, "district": district, "weather_location_name": None,
        "latitude": None, "longitude": None, "mapping_method": None,
        "mapping_source": "Open-Meteo Geocoding API (https://geocoding-api.open-meteo.com/v1/search)",
        "mapping_confidence": None, "mapping_status": "unresolved",
    }

    last_error = None
    for attempt in range(retries + 1):
        try:
            resp = requests.get(
                GEOCODING_URL,
                params={"name": district, "count": 5, "country": "IN"},
                timeout=timeout,
            )
            if resp.status_code != 200:
                last_error = f"HTTP {resp.status_code}"
                time.sleep(1)
                continue

            candidates = resp.json().get("results", [])
            if not candidates:
                result["mapping_method"] = "district name search — no results returned"
                return result

            state_norm = _normalize_state(state)
            exact_state_match = next(
                (c for c in candidates if _normalize_state(c.get("admin1", "")) == state_norm),
                None,
            )
            if exact_state_match:
                c = exact_state_match
                result.update({
                    "weather_location_name": c.get("name"), "latitude": c.get("latitude"),
                    "longitude": c.get("longitude"),
                    "mapping_method": "district name + state match (admin1 confirmed)",
                    "mapping_confidence": "high", "mapping_status": "mapped",
                })
                return result

            # No candidate's state matched — record as unresolved rather than
            # guessing which of several same-named places across India is meant.
            result["mapping_method"] = (
                f"district name search returned {len(candidates)} result(s) but none matched "
                f"state '{state}' (admin1 values seen: "
                f"{sorted({c.get('admin1') for c in candidates})})"
            )
            return result

        except requests.exceptions.RequestException as e:
            last_error = str(e)
            time.sleep(1)

    result["mapping_method"] = f"request failed after {retries + 1} attempts: {last_error}"
    return result


def top_districts_by_volume(mandi_df, n: int = 20) -> list[tuple[str, str, int]]:
    """Return the top-N (state, district) pairs by mandi record count for one crop's dataframe."""
    counts = mandi_df.groupby(["State Name", "District Name"]).size().sort_values(ascending=False)
    return [(state, district, int(count)) for (state, district), count in counts.head(n).items()]
