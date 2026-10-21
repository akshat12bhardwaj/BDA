"""
Non-secret configuration for the Open-Meteo weather collection pipeline.

Open-Meteo's Historical Weather Archive API and Geocoding API do not require
an API key for the request volume this project needs (confirmed by direct
test call in Phase 1 and re-confirmed in Phase 3 — see
Documentation/Weather_Data_Collection.md). Consequently there are no
credentials to manage here: no .env file, no config/weather_config.example.env,
and nothing secret is read, stored, or printed by this package. If a future
phase needs a different weather provider that does require a key, add a
`Code/config/weather_config.example.env` placeholder file and read the real
key only from an environment variable at that time — never hardcode it here.
"""

from __future__ import annotations

from pathlib import Path

GEOCODING_URL = "https://geocoding-api.open-meteo.com/v1/search"
ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"

# Chosen after comparing mandi date coverage (Onion/Potato: ~2000-10 to 2024-02;
# Wheat: ~2001-03 to 2024-02) against APY year coverage (1997-98 to 2022-23
# agricultural years). 2001-01-01 is the first calendar year in which all three
# crops' mandi reporting is already active; 2022-12-31 is the last calendar
# year fully inside APY's coverage (the 2022-2023 agricultural year straddles
# calendar 2022/2023 — Phase 4 will need to decide how to align agricultural
# vs. calendar years; Phase 3 stays on the safe, fully-covered side).
DEFAULT_START_DATE = "2001-01-01"
DEFAULT_END_DATE = "2022-12-31"

# Selected because: (a) directly relevant to price/production per the future
# Phase 8/10 specifications (temperature and rainfall drive yield and harvest
# timing; humidity/wind affect post-harvest storage losses, relevant to
# perishable Onion/Potato), (b) already validated as returning real data in
# Phase 1's test call, and (c) available as clean daily aggregates (unlike
# soil moisture, investigated in Phase 3 and found to return null/undefined
# values in the daily archive endpoint — excluded for that reason).
DAILY_VARIABLES = [
    "temperature_2m_mean",
    "temperature_2m_max",
    "temperature_2m_min",
    "rain_sum",
    "relative_humidity_2m_mean",
    "wind_speed_10m_mean",
    "et0_fao_evapotranspiration",
]

TIMEZONE = "Asia/Kolkata"

RAW_WEATHER_DIR = Path("Processed_Data/weather/raw")
VALIDATED_WEATHER_DIR = Path("Processed_Data/weather/validated")
MAPPING_CACHE_PATH = Path("Processed_Data/weather/weather_location_mapping.csv")
MANIFEST_PATH = Path("Processed_Data/weather/weather_collection_manifest.csv")
