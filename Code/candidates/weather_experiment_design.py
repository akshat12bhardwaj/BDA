"""Pre-registration of the exploratory price + weather experiment `exp-candidate-weather-v1` (Data_Source_Review.md §8.7).
Nothing is trained or scored here. This module defines the weather features exactly (tested on synthetic data), counts
the restricted coverage from date and identifier columns of the guarded validation rows, and writes the protocol.

Weather input: the Open-Meteo extension fetched 2026-10-24 (Dataset_Candidates/openmeteo_ext/2026-10-24/ext, one same-day
vintage, identified by its manifest SHA-256). IMD gridded data are validation-only and refused as a feature input.

Usage (repo root): python -m Code.candidates.weather_experiment_design
Output: Processed_Data/candidates/datagov_prices/experiments/exp_candidate_weather_v1/ (protocol JSON + coverage CSV)."""
import hashlib, json, sys
from pathlib import Path

import numpy as np
import pandas as pd

from Code.candidates import baselines_candidate as bc, experiment_design as ed, learned_candidate as lc, weather_extension as we

EXP = bc.EXP_DIR.parent / 'exp_candidate_weather_v1'
WEATHER_SOURCE = we.RAW / 'ext'
FORBIDDEN_FEATURE_SOURCES = (str(we.IMD),)   # validation-only (IMD 2025 possibly provisional; §8.8)
WINDOW_END_LAG_DAYS = {'primary': 1, 'realtime_sensitivity': 6}   # window ends 1 day (or ~ERA5 delay + 1) before the origin Sunday
WEATHER_FEATURES = {
    'wx_rain_sum_7d': 'sum of rain_sum over the 7 days ending L days before the origin Sunday',
    'wx_rain_sum_28d': 'sum of rain_sum over the 28 days ending L days before the origin Sunday',
    'wx_tmax_mean_7d': 'mean of temperature_2m_max over the same 7 days',
    'wx_tmin_mean_7d': 'mean of temperature_2m_min over the same 7 days',
    'wx_rain_anom_28d': 'wx_rain_sum_28d minus the climatological mean 28-day sum for the same end day-of-year, fitted only on '
                        'weather dated <= the applicable refit date (NaN if no earlier year has that window)',
}
HIGH_BIAS_LOCATIONS = 'locations with |Tmax bias| > 2 C or |Tmin bias| > 2 C vs IMD in imd_validation.csv (extension, all seasons)'


def location_key(canonical_id):
    s, d, _ = canonical_id.split('|', 2)
    return s.lower(), d.lower()


def window_sum(daily, end, days, col, agg):
    """Aggregate `col` over the `days` days ending at `end` (inclusive). NaN unless every day is present and non-null."""
    w = daily.loc[end - pd.Timedelta(days=days - 1):end, col]
    if len(w) < days or w.isna().any():
        return np.nan
    return float(w.sum() if agg == 'sum' else w.mean())


def weather_features(rows, daily_by_loc, lag_days=1, refit_dates=None):
    """rows: model-table rows (canonical_id, origin_week_start). daily_by_loc: {(state, district) lowercase: daily frame indexed by
    date}. Every window ends origin Sunday - lag_days, so no weather on or after the origin Sunday is used.
    refit_dates (aligned with rows) bound the climatology to weather dated <= that refit."""
    out = {k: [] for k in WEATHER_FEATURES}
    for i, r in enumerate(rows.itertuples()):
        d = daily_by_loc.get(location_key(r.canonical_id))
        end = r.origin_week_start + pd.Timedelta(days=6 - lag_days)
        if d is None:
            for k in out: out[k].append(np.nan)
            continue
        for k, (n, col, agg) in {'wx_rain_sum_7d': (7, 'rain_sum', 'sum'), 'wx_rain_sum_28d': (28, 'rain_sum', 'sum'),
                                 'wx_tmax_mean_7d': (7, 'temperature_2m_max', 'mean'),
                                 'wx_tmin_mean_7d': (7, 'temperature_2m_min', 'mean')}.items():
            out[k].append(window_sum(d, end, n, col, agg))
        clim = np.nan
        if refit_dates is not None:
            cut = pd.Timestamp(refit_dates[i])
            past = [window_sum(d, end - pd.DateOffset(years=y), 28, 'rain_sum', 'sum') for y in (1, 2, 3)
                    if end - pd.DateOffset(years=y) <= cut]
            past = [p for p in past if not np.isnan(p)]
            clim = float(np.mean(past)) if past else np.nan
        out['wx_rain_anom_28d'].append(out['wx_rain_sum_28d'][-1] - clim)
    return pd.DataFrame(out, index=rows.index)


def restricted_coverage(root):
    """Counts only (identifier and date columns of guarded validation rows); no price or target is read."""
    loc = we.locations(); keys = set(zip(loc.state.str.lower(), loc.district.str.lower()))
    mt = bc.guarded_read(root / bc.DATASET / 'model_table_faq_only.parquet', 'target_week_start',
                         ['Commodity', 'canonical_id', 'origin_week_start', 'target_week_start', 'horizon_weeks', 'eligible_d41'])
    mt = mt[(mt.horizon_weeks == 1) & mt.eligible_d41].copy()
    mt['period'] = ed.assign_period(mt)
    v = mt[mt.period == 'validation'].copy()
    v['covered'] = [location_key(c) in keys for c in v.canonical_id]
    t = v.target_week_start + pd.Timedelta(days=6)
    v['quarter'] = np.where(t <= pd.Timestamp(bc.QUARTERS['2026Q1'][1]), '2026Q1', '2026Q2')
    v['state'] = v.canonical_id.str.split('|').str[0]
    rows = []
    for (c, q), g in v.groupby(['Commodity', 'quarter']):
        x = g[g.covered]
        sh = x.state.value_counts(normalize=True)
        rows.append({'crop': c, 'quarter': q, 'eligible_rows': len(g), 'weather_rows': len(x), 'weather_row_pct': round(100 * len(x) / len(g), 1),
                     'weather_markets': x.canonical_id.nunique(), 'weather_states': x.state.nunique(),
                     'top_state': sh.index[0] if len(sh) else None, 'top_state_share': round(float(sh.iloc[0]), 3) if len(sh) else None})
    return pd.DataFrame(rows)


def protocol(root):
    pre = bc.preflight(root)
    wman = WEATHER_SOURCE / 'manifest.csv'
    code = ['Code/candidates/weather_experiment_design.py', 'Code/candidates/learned_candidate.py', 'Code/candidates/baselines_candidate.py',
            'Code/candidates/weather_extension.py', 'Code/modelling/models.py']
    return {
        'experiment': 'exp-candidate-weather-v1', 'status': 'PRE-REGISTERED PROPOSAL; NOT EXECUTED; requires owner authorisation',
        'question': 'Does price plus appropriately lagged weather improve on persistence for the same eligible markets and forecast dates?',
        'nature': 'EXPLORATORY. The 2026 validation window already scored the failed price-only learned model (§7.5); this is a second '
                  'model on the same window, so a pass is an exploratory signal, not confirmation',
        'population': 'FAQ-only, h = 1, eligible_d41 at the origin, canonical market in one of the 46 weather districts (exact state + '
                      'district, as Phase 4); every weather feature non-null on the row',
        'split_refits_seed': {'split': ed.PROPOSED_SPLIT, 'refit_rule': 'phase8_quarterly', 'seed': bc.SEED, 'reps': bc.REPS},
        'weather_source': {'path': str(WEATHER_SOURCE), 'manifest_sha256': hashlib.sha256((root / wman).read_bytes()).hexdigest(),
                           'vintage': 'Open-Meteo archive as retrieved 2026-10-24 (no API version field exists)',
                           'forbidden_feature_sources': list(FORBIDDEN_FEATURE_SOURCES)},
        'weather_features': WEATHER_FEATURES, 'window_end': f'origin Sunday minus {WINDOW_END_LAG_DAYS["primary"]} day (primary)',
        'excluded': ['daily rain (fails IMD daily validation, §8.3)', 'same-day weather', 'observed future weather used as a forecast',
                     'any IMD gridded value'],
        'missing_values': 'a row is excluded from BOTH methods if any weather feature is NaN (identical rows); no imputation',
        'models': {'primary': 'hgb_conservative unchanged (estimator_params as §7.5) on the 9 registered price features + 5 weather features',
                   'diagnostic': 'the same estimator on the 9 price features only, trained and scored on the same restricted rows '
                                 '(isolates the weather contribution; not part of the acceptance rule)',
                   'baseline': 'persistence (y_origin)',
                   'training': 'per crop and refit: Phase 8 eligible_by_refit examples ended by the refit, restricted to weather-district '
                               'series with all weather features non-null'},
        'acceptance_rule': lc.SELECTION_RULE.replace('learned', 'price+weather'),
        'multiple_comparisons': 'reported, not used to relax: Bonferroni-adjusted (6 crop x quarter tests) 99.17% market-cluster '
                                'intervals beside the 95% ones; any pass requires confirmation on data after 2026-10-20 before any '
                                'test-window request',
        'sensitivity_analyses_reported_not_selected': [
            'realtime lag: windows ending origin Sunday minus 6 days (about the ERA5 delay)',
            '7-day features only (drop the two 28-day features)', f'excluding {HIGH_BIAS_LOCATIONS}',
            'state-cluster bootstrap; leave-one-state-out'],
        'disclosures': ['restricted geography: 46 district points cover about 18-23% of eligible validation rows (coverage CSV)',
                        'selection bias: the evaluable markets are reconciled, continuing, weather-district markets only',
                        'weather validation is 46 points against IMD gridded analyses, not national validation; Tmax/Tmin '
                        'location biases up to about 3-4 C are reported, not corrected'],
        'guards': ['protocol and dataset hashes (baselines_candidate.preflight)', 'test window never loaded (parquet filter)',
                   'no 2023 holdout or pre-2024-02-03 data', 'weather manifest hash must match', 'IMD refused as feature input',
                   'R09u disabled', 'no tuning, no alternative feature sets after results'],
        'hashes': {'protocol_lf_sha256': pre['protocol_sha256'], 'dataset_manifest_sha256': pre['dataset_manifest_sha256'],
                   'learned_preregistration_sha256': hashlib.sha256((root / lc.PREREG).read_bytes()).hexdigest(),
                   **{p: hashlib.sha256((root / p).read_bytes()).hexdigest() for p in code}},
    }


def main():
    root = Path.cwd(); dest = root / EXP; dest.mkdir(parents=True, exist_ok=True)
    cov = restricted_coverage(root); cov.to_csv(dest / 'restricted_coverage.csv', index=False, lineterminator='\n')
    p = protocol(root); p['restricted_coverage'] = cov.to_dict('records')
    blob = json.dumps(p, indent=1, sort_keys=True, default=str).encode()
    (dest / 'exp_candidate_weather_v1_protocol.json').write_bytes(blob)
    print('protocol sha256', hashlib.sha256(blob).hexdigest()); print(cov.to_string(index=False))
    return 0


if __name__ == '__main__':
    sys.exit(main())
