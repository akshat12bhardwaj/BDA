"""
Weather extension: IMD grid indexing, missing-cell handling, comparison metrics, and the D-50 window. Synthetic grids in a
temporary folder; no network call and no original weather file is touched.
"""

import numpy as np
import pandas as pd

from Code.candidates import weather_extension as we


def test_extension_window_respects_d50_and_ends_on_the_price_data():
    assert we.EXT_WINDOW == ("2024-02-03", "2026-10-20")
    assert we.RAW != we.Path("Processed_Data/weather/raw")  # never the original cache


def test_imd_rain_grid_index_and_missing_cells(tmp_path, monkeypatch):
    monkeypatch.setattr(we, "IMD", tmp_path)
    days = 365
    a = np.full((days, 129, 135), -999.0, dtype="<f4")
    i, j = round((20.0 - 6.5) / .25), round((74.0 - 66.5) / .25)
    a[:, i, j] = 5.0
    a.tofile(tmp_path / "rain_2025.grd")
    s = we.imd_series("rain", 2025, 20.0, 74.0)
    assert len(s) == 365 and (s == 5.0).all()
    assert we.imd_series("rain", 2025, 10.0, 70.0).isna().all()  # -999 cell -> missing, never zero


def test_imd_temperature_grid_marks_99_9_as_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(we, "IMD", tmp_path)
    a = np.full((366, 31, 31), 99.9, dtype="<f4"); a[:, round(28 - 7.5), round(77 - 67.5)] = 31.0
    a.tofile(tmp_path / "tmax_2024.grd")
    s = we.imd_series("tmax", 2024, 28.0, 77.0)
    assert len(s) == 366 and (s == 31.0).all() and we.imd_series("tmax", 2024, 8.0, 68.0).isna().all()


def test_compare_reports_unvalidated_without_enough_reference_days():
    d = pd.date_range("2025-01-01", periods=40)
    om, ref = pd.Series(np.arange(40.0), d), pd.Series(np.arange(40.0) + 1, d)
    r = we.compare(om, ref, "tmax")
    assert r["status"] == "compared" and r["bias"] == -1.0 and r["mae"] == 1.0 and r["daily_corr"] == 1.0
    assert we.compare(om, ref.where(ref < 10), "tmax")["status"].startswith("unvalidated")
