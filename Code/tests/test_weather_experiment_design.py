"""
Pre-registered weather features: windows end before the origin Sunday, missing days give NaN (never zero), the
climatology never sees weather after the refit, and IMD is not a feature source. Synthetic data only; nothing is trained.
"""

import numpy as np
import pandas as pd

from Code.candidates import weather_experiment_design as wd


def daily(start="2024-02-03", end="2026-10-20", rain=1.0):
    idx = pd.date_range(start, end)
    return pd.DataFrame({"rain_sum": rain, "temperature_2m_max": 30.0, "temperature_2m_min": 15.0}, index=idx)


def rows(origin_weeks, cid="S|D|M"):
    return pd.DataFrame({"canonical_id": cid, "origin_week_start": pd.to_datetime(origin_weeks)})


def test_windows_end_the_day_before_the_origin_sunday():
    d = daily()
    d.loc["2025-06-15", "rain_sum"] = 1000.0  # the origin Sunday itself (origin week starts 2025-06-09)
    f = wd.weather_features(rows(["2025-06-09"]), {("s", "d"): d})
    assert f.wx_rain_sum_7d.item() == 7.0 and f.wx_rain_sum_28d.item() == 28.0  # same-day value never enters
    d.loc["2025-06-14", "rain_sum"] = 101.0  # the Saturday before: inside the primary window, outside the 6-day-lag one
    assert wd.weather_features(rows(["2025-06-09"]), {("s", "d"): d}).wx_rain_sum_7d.item() == 107.0
    assert wd.weather_features(rows(["2025-06-09"]), {("s", "d"): d}, lag_days=6).wx_rain_sum_7d.item() == 7.0


def test_missing_day_or_location_gives_nan_never_zero():
    d = daily(); d.loc["2025-06-10", "rain_sum"] = np.nan
    f = wd.weather_features(rows(["2025-06-09", "2025-06-09"], cid="S|D|M"), {("s", "d"): d})
    assert f.wx_rain_sum_7d.isna().all() and f.wx_tmax_mean_7d.notna().all()
    assert wd.weather_features(rows(["2025-06-09"], cid="X|Y|M"), {("s", "d"): d}).isna().all(axis=None)


def test_climatology_uses_only_weather_dated_by_the_refit():
    d = daily(rain=1.0)
    d.loc["2025-05-01":"2025-06-30", "rain_sum"] = 3.0  # 2025 window wetter than 2024
    r = rows(["2026-06-08"])  # window ends 2026-06-13; one year earlier ends 2025-06-13, two years 2024-06-13
    early = wd.weather_features(r, {("s", "d"): d}, refit_dates=["2025-01-05"])  # only 2024 is before this refit
    late = wd.weather_features(r, {("s", "d"): d}, refit_dates=["2026-04-05"])  # 2024 and 2025 available
    assert early.wx_rain_anom_28d.item() == 28.0 - 28.0
    assert late.wx_rain_anom_28d.item() == 28.0 - (28.0 + 84.0) / 2


def test_imd_is_not_a_feature_source_and_features_are_the_registered_five():
    assert str(wd.we.IMD) in wd.FORBIDDEN_FEATURE_SOURCES and str(wd.WEATHER_SOURCE) not in wd.FORBIDDEN_FEATURE_SOURCES
    assert list(wd.WEATHER_FEATURES) == ["wx_rain_sum_7d", "wx_rain_sum_28d", "wx_tmax_mean_7d", "wx_tmin_mean_7d", "wx_rain_anom_28d"]
    assert wd.WINDOW_END_LAG_DAYS == {"primary": 1, "realtime_sensitivity": 6}
