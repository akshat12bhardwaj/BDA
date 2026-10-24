"""Weather extension audit (Data_Source_Review.md §8.1). Read-only for the original weather data: nothing under
Processed_Data/weather or Processed_Data/integration is written, and Code/weather/collector.py is NOT used (its cache is
the original raw folder).

  audit     the original 46-location panel: identifiers, coverage, units, missing values, duplicates.
  fetch     Open-Meteo archive (historical reanalysis, never forecasts) for the same 46 points and the same 7 daily
            variables: the extension window 2024-02-03 .. 2026-10-20 (D-50: nothing before 2024-02-03) and a 2022
            re-fetch to test whether the source still reproduces the original panel. Raw JSON bytes + a manifest.
  validate  Open-Meteo (original 2022; extension 2024-02-03 .. 2025-12-31) against IMD gridded analyses (rain 0.25 deg,
            Tmax/Tmin 1 deg) at the nearest cell, all 46 points: bias, MAE, RMSE, correlation, by season and month.
            IMD gridded data are gauge-based analyses, not station observations; a point with no valid IMD cell is
            reported as unvalidated.

Usage (repo root): python -m Code.candidates.weather_extension audit|fetch|validate|coverage
Raw: Dataset_Candidates/openmeteo_ext/<date>/ (git-ignored). Reports: Processed_Data/candidates/weather_v1/."""
import hashlib, json, sys, time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from Code.weather.config import ARCHIVE_URL, DAILY_VARIABLES, TIMEZONE

RES = Path('Processed_Data/integration/weather_location_resolution.csv')
PANEL = Path('Processed_Data/integration/weather_daily_panel.parquet')
RAW = Path('Dataset_Candidates/openmeteo_ext/2026-10-24')
IMD = Path('Dataset_Candidates/imd_gridded/2026-10-24')
OUT = Path('Processed_Data/candidates/weather_v1')
EXT_WINDOW = ('2024-02-03', '2026-10-20')
REFETCH_WINDOW = ('2022-01-01', '2022-12-31')
UNITS = {'temperature_2m_mean': 'degC', 'temperature_2m_max': 'degC', 'temperature_2m_min': 'degC', 'rain_sum': 'mm',
         'relative_humidity_2m_mean': '%', 'wind_speed_10m_mean': 'km/h', 'et0_fao_evapotranspiration': 'mm'}
SEASONS = {1: 'winter', 2: 'winter', 3: 'pre_monsoon', 4: 'pre_monsoon', 5: 'pre_monsoon', 6: 'monsoon', 7: 'monsoon',
           8: 'monsoon', 9: 'monsoon', 10: 'post_monsoon', 11: 'post_monsoon', 12: 'post_monsoon'}   # IMD seasons


def locations():
    r = pd.read_csv(RES)
    return r[['state', 'district', 'crops', 'latitude', 'longitude', 'geocoder_name', 'geocoder_id', 'geocoder_admin1', 'geocoder_admin2',
              'resolution_status', 'weather_file']].reset_index(drop=True)


def slug(state, district):
    return f'{state}_{district}'.replace(' ', '_')


# ---------------------------------------------------------------- audit
def audit():
    loc = locations()
    p = pd.read_parquet(PANEL)
    g = p.groupby(['weather_state', 'weather_district'])
    cov = g.agg(first=('reported_date', 'min'), last=('reported_date', 'max'), rows=('reported_date', 'size'),
                distinct_dates=('reported_date', 'nunique')).reset_index()
    cov['expected_days'] = (cov['last'] - cov['first']).dt.days + 1
    cov['duplicate_dates'] = cov.rows - cov.distinct_dates
    cov['missing_dates'] = cov.expected_days - cov.distinct_dates
    nulls = p[DAILY_VARIABLES].isna().sum().to_dict()
    return loc, cov, {'locations': len(loc), 'panel_rows': len(p), 'null_values_by_variable': nulls,
                      'resolution_status': loc.resolution_status.value_counts().to_dict(), 'units': UNITS,
                      'superseded_raw_file': 'Processed_Data/weather/raw/Punjab_Ferozpur.csv (Phase 3 point in the wrong district; '
                                             'replaced by Punjab_Ferozpur_corrected.csv in Phase 4)'}


# ---------------------------------------------------------------- fetch (raw bytes + manifest)
def fetch(window, sub, only=None):
    import requests
    out = RAW / sub; out.mkdir(parents=True, exist_ok=True)
    rows = []
    loc = locations() if only is None else locations().iloc[only]
    for r in loc.itertuples():
        path = out / f'{slug(r.state, r.district)}.json'
        params = {'latitude': r.latitude, 'longitude': r.longitude, 'start_date': window[0], 'end_date': window[1],
                  'daily': ','.join(DAILY_VARIABLES), 'timezone': TIMEZONE}
        status, body = 'cached', None
        if not path.exists():
            last = ''
            for attempt in range(6):  # bounded: rate limits back off (65 s, then up to ~16 min), other failures 2**attempt s
                try:
                    resp = requests.get(ARCHIVE_URL, params=params, timeout=180)
                    ok = resp.status_code == 200 and 'daily' in json.loads(resp.content)
                except (requests.RequestException, ValueError) as e:  # non-JSON body (gateway page) or transport error
                    resp, ok, last = None, False, type(e).__name__
                if ok:
                    body = resp.content; path.write_bytes(body); status = 'fetched'; break
                if resp is not None:
                    last = f'HTTP {resp.status_code}'
                time.sleep(min(65 * 2 ** attempt, 960) if resp is not None and resp.status_code == 429 else 2 ** attempt)
            else:
                rows.append({'state': r.state, 'district': r.district, 'status': f'failed {last}'}); continue
            time.sleep(1.5)
        body = path.read_bytes(); j = json.loads(body); d = pd.DataFrame(j['daily'])
        rows.append({'state': r.state, 'district': r.district, 'status': status, 'url': ARCHIVE_URL, 'params': json.dumps(params),
                     'retrieved_utc': datetime.now(timezone.utc).isoformat(timespec='seconds') if status == 'fetched' else '',
                     'sha256': hashlib.sha256(body).hexdigest(), 'rows': len(d), 'first': d.time.min(), 'last': d.time.max(),
                     'grid_latitude': j.get('latitude'), 'grid_longitude': j.get('longitude'), 'elevation': j.get('elevation'),
                     'units': json.dumps(j.get('daily_units')), **{f'null_{v}': int(d[v].isna().sum()) for v in DAILY_VARIABLES}})
    m = pd.DataFrame(rows)
    m['retrieved_utc_source'] = np.where(m.retrieved_utc.fillna('') != '', 'request', '')
    prev = out / 'manifest.csv'
    if prev.exists():  # keep the first retrieval time of files fetched earlier
        old = pd.read_csv(prev).set_index(['state', 'district'])
        for i, (s, di) in enumerate(zip(m.state, m.district)):
            if not m.at[i, 'retrieved_utc'] and (s, di) in old.index and isinstance(old.at[(s, di), 'retrieved_utc'], str):
                m.at[i, 'retrieved_utc'] = old.at[(s, di), 'retrieved_utc']
                m.at[i, 'retrieved_utc_source'] = old.get('retrieved_utc_source', pd.Series('request', index=old.index)).get((s, di), 'request')
    for i, (s, di) in enumerate(zip(m.state, m.district)):  # cached file with no recorded request time (interrupted run)
        if not m.at[i, 'retrieved_utc'] and m.at[i, 'status'] == 'cached':
            f = out / f'{slug(s, di)}.json'
            m.at[i, 'retrieved_utc'] = datetime.fromtimestamp(f.stat().st_mtime, timezone.utc).isoformat(timespec='seconds')
            m.at[i, 'retrieved_utc_source'] = 'file_write_time (manifest lost when the first run was interrupted)'
    m.to_csv(prev, index=False, lineterminator='\n')
    return m


RECON_WINDOW = ('2001-01-01', '2022-12-31')   # the original panel's documented window (Code/weather/config.py)
REPRO_LOCATIONS = [0, 17, 45]                  # Nashik, Ferozpur (corrected point), Junagarh: fixed before fetching


def repro_check():
    """Same-day reproducibility: a second fetch of 3 fixed locations must be byte-identical to the first, for both windows."""
    rows = []
    for window, first, again in ((RECON_WINDOW, 'reconstruct_2001_2022', 'repro_reconstruct'), (EXT_WINDOW, 'ext', 'repro_ext')):
        fetch(window, again, REPRO_LOCATIONS)
        for r in locations().iloc[REPRO_LOCATIONS].itertuples():
            a, b = (json.loads((RAW / s / f'{slug(r.state, r.district)}.json').read_bytes()) for s in (first, again))
            # bytes always differ: every response carries its own generationtime_ms; compare the content instead
            keys = sorted((set(a) | set(b)) - {'generationtime_ms'})
            rows.append({'window': first, 'state': r.state, 'district': r.district,
                         'daily_values_identical': a['daily'] == b['daily'],
                         'grid_units_elevation_identical': all(a.get(k) == b.get(k) for k in keys if k != 'daily'),
                         'differing_top_level_keys': ','.join(k for k in sorted(set(a) | set(b)) if a.get(k) != b.get(k))})
    return pd.DataFrame(rows)


def verify_reconstruction():
    """Completeness, units, duplicates, grid cell vs the original raw files, and agreement with the original by year."""
    rec = load_fetched('reconstruct_2001_2022')
    man = pd.read_csv(RAW / 'reconstruct_2001_2022' / 'manifest.csv')
    days = pd.date_range(*RECON_WINDOW)
    chk = {'locations': int(rec[['state', 'district']].drop_duplicates().shape[0]), 'rows': len(rec),
           'expected_rows': 46 * len(days), 'duplicate_dates': int(rec.duplicated(['state', 'district', 'date']).sum()),
           'missing_dates': int(46 * len(days) - rec[['state', 'district', 'date']].drop_duplicates().shape[0]),
           'null_values': {v: int(rec[v].isna().sum()) for v in DAILY_VARIABLES},
           'units_identical_to_extension': bool(man.units.nunique() == 1 and man.units.iloc[0] == pd.read_csv(RAW / 'ext' / 'manifest.csv').units.iloc[0])}
    # same grid cell as the original? the original raw CSVs kept the API's returned grid latitude / longitude
    same_cell = []
    for r in locations().itertuples():
        o = pd.read_csv(r.weather_file.replace('\\', '/'), nrows=1)
        m = man[(man.state == r.state) & (man.district == r.district)].iloc[0]
        same_cell.append(abs(o.latitude.iloc[0] - m.grid_latitude) < 1e-4 and abs(o.longitude.iloc[0] - m.grid_longitude) < 1e-4)
    chk['same_grid_cell_as_original'] = int(sum(same_cell))
    orig = pd.read_parquet(PANEL).rename(columns={'weather_state': 'state', 'weather_district': 'district', 'reported_date': 'date'})
    j = orig.merge(rec, on=['state', 'district', 'date'], suffixes=('_orig', '_rec'))
    by_year = pd.DataFrame([{'year': y, 'variable': v, 'identical_share': round(float(((g[f'{v}_rec'] - g[f'{v}_orig']).abs() < 1e-9).mean()), 4),
                             'max_abs_diff': round(float((g[f'{v}_rec'] - g[f'{v}_orig']).abs().max()), 3)}
                            for y, g in j.groupby(j.date.dt.year) for v in DAILY_VARIABLES])
    return chk, by_year


def load_fetched(sub):
    frames = []
    for r in locations().itertuples():
        j = json.loads((RAW / sub / f'{slug(r.state, r.district)}.json').read_bytes())
        d = pd.DataFrame(j['daily']).rename(columns={'time': 'date'})
        d['date'] = pd.to_datetime(d.date); d.insert(0, 'state', r.state); d.insert(1, 'district', r.district)
        frames.append(d)
    return pd.concat(frames, ignore_index=True)


# ---------------------------------------------------------------- IMD gridded reference
def imd_series(var, year, lat, lon):
    days = pd.date_range(f'{year}-01-01', f'{year}-12-31')
    if var == 'rain':
        a = np.fromfile(IMD / f'rain_{year}.grd', dtype='<f4').reshape(len(days), 129, 135)
        v = a[:, round((lat - 6.5) / .25), round((lon - 66.5) / .25)]
        return pd.Series(np.where(v < -998, np.nan, v), days)
    a = np.fromfile(IMD / f'{var}_{year}.grd', dtype='<f4').reshape(len(days), 31, 31)
    v = a[:, round(lat - 7.5), round(lon - 67.5)]
    return pd.Series(np.where(v > 99, np.nan, v), days)


def compare(om, ref, kind):
    j = pd.concat([om.rename('om'), ref.rename('imd')], axis=1).dropna()
    if len(j) < 30:
        return {'days': len(j), 'status': 'unvalidated (no valid IMD cell)'}
    e = j.om - j.imd
    out = {'days': len(j), 'status': 'compared', 'bias': e.mean(), 'mae': e.abs().mean(), 'rmse': float(np.sqrt((e ** 2).mean())),
           'daily_corr': j.om.corr(j.imd)}
    mon = (j.resample('ME').sum() if kind == 'rain' else j.resample('ME').mean())
    out.update({'monthly_corr': mon.om.corr(mon.imd), 'monthly_bias': (mon.om - mon.imd).mean()})
    if kind == 'rain':
        out.update({'total_om': j.om.sum(), 'total_imd': j.imd.sum()})
    return out


def validate():
    loc = locations()
    orig = pd.read_parquet(PANEL).rename(columns={'weather_state': 'state', 'weather_district': 'district', 'reported_date': 'date'})
    ext = load_fetched('ext')
    pairs = [('rain', 'rain_sum'), ('tmax', 'temperature_2m_max'), ('tmin', 'temperature_2m_min')]
    rows = []
    for r in loc.itertuples():
        for label, src, years, start in [('original_2022', orig, [2022], '2022-01-01'), ('extension_2024_2025', ext, [2024, 2025], EXT_WINDOW[0])]:
            s = src[(src.state == r.state) & (src.district == r.district)].set_index('date').sort_index()
            for kind, col in pairs:
                ref = pd.concat([imd_series(kind, y, r.latitude, r.longitude) for y in years])
                ref = ref[ref.index >= pd.Timestamp(start)]
                om = s[col].reindex(ref.index)
                rows.append({'state': r.state, 'district': r.district, 'period': label, 'variable': kind, 'season': 'all', **compare(om, ref, kind)})
                for season in sorted(set(SEASONS.values())):
                    m = ref.index.month.map(SEASONS) == season
                    rows.append({'state': r.state, 'district': r.district, 'period': label, 'variable': kind, 'season': season,
                                 **compare(om[m], ref[m], kind)})
    return pd.DataFrame(rows)


def refetch_check():
    """Does the source reproduce the original panel for 2022 at the same points?"""
    orig = pd.read_parquet(PANEL).rename(columns={'weather_state': 'state', 'weather_district': 'district', 'reported_date': 'date'})
    new = load_fetched('refetch_2022')
    j = orig.merge(new, on=['state', 'district', 'date'], suffixes=('_orig', '_new'))
    rows = []
    for v in DAILY_VARIABLES:
        d = (j[f'{v}_new'] - j[f'{v}_orig']).abs()
        rows.append({'variable': v, 'rows': len(j), 'identical_share': round(float((d < 1e-9).mean()), 4),
                     'max_abs_diff': round(float(d.max()), 3), 'mean_abs_diff': round(float(d.mean()), 4)})
    return pd.DataFrame(rows)


def coverage():
    """Share of candidate-prices-v1.1 usable records in the 46 weather districts (exact state + district, as Phase 4)."""
    loc = locations()
    keys = set(zip(loc.state.str.lower(), loc.district.str.lower()))
    rows = []
    for c in ('onion', 'potato', 'wheat'):
        r = pd.read_parquet(Path('Processed_Data/candidates/datagov_prices/dataset_v1_1') / f'records_{c}.parquet',
                            columns=['State', 'District', 'usable_for_target', 'in_faq_only'])
        u = r[r.usable_for_target]
        hit = [(s.lower(), d.lower()) in keys for s, d in zip(u.State, u.District)]
        rows.append({'crop': c.title(), 'usable_records': len(u), 'in_weather_districts_pct': round(100 * float(np.mean(hit)), 1),
                     'faq_only_in_weather_districts_pct': round(100 * float(np.mean([h for h, f in zip(hit, u.in_faq_only) if f])), 1)})
    return pd.DataFrame(rows)


def main(argv=None):
    cmd = (argv or sys.argv[1:] or ['audit'])[0]
    OUT.mkdir(parents=True, exist_ok=True)
    if cmd == 'audit':
        loc, cov, s = audit()
        loc.to_csv(OUT / 'locations.csv', index=False); cov.to_csv(OUT / 'original_panel_coverage.csv', index=False)
        (OUT / 'original_audit.json').write_text(json.dumps(s, indent=1, default=str)); print(json.dumps(s, indent=1, default=str))
    elif cmd == 'fetch':
        for window, sub in ((EXT_WINDOW, 'ext'), (REFETCH_WINDOW, 'refetch_2022')):
            m = fetch(window, sub); print(sub, m.status.value_counts().to_dict(), 'rows', m.rows.unique().tolist())
    elif cmd == 'validate':
        v = validate(); v.to_csv(OUT / 'imd_validation.csv', index=False, float_format='%.4f')
        rc = refetch_check(); rc.to_csv(OUT / 'refetch_2022_vs_original.csv', index=False); print(rc.to_string(index=False))
    elif cmd == 'reconstruct':
        m = fetch(RECON_WINDOW, 'reconstruct_2001_2022'); print(m.status.value_counts().to_dict(), 'rows', m.rows.unique().tolist())
    elif cmd == 'repro':
        r = repro_check(); r.to_csv(OUT / 'same_day_reproducibility.csv', index=False); print(r.to_string(index=False))
    elif cmd == 'verify_reconstruction':
        chk, by_year = verify_reconstruction()
        (OUT / 'reconstruction_checks.json').write_text(json.dumps(chk, indent=1)); by_year.to_csv(OUT / 'reconstruction_vs_original_by_year.csv', index=False)
        print(json.dumps(chk, indent=1))
    elif cmd == 'coverage':
        c = coverage(); c.to_csv(OUT / 'candidate_price_coverage.csv', index=False); print(c.to_string(index=False))
    return 0


if __name__ == '__main__':
    sys.exit(main())
