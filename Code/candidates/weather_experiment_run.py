"""Runner for the pre-registered exp-candidate-weather-v1 (protocol SHA-256 PROTOCOL_SHA256; Data_Source_Review.md §8.9, §8.11).
Executes exactly the registered design; nothing here may be tuned. Kept in a new file so that no protocol-hashed file changes.

Guards before any fitting (GuardError stops the run):
- the protocol file hashes to PROTOCOL_SHA256 AND regenerating it from the frozen code and data is byte-identical;
- every hash embedded in the protocol (price protocol, v1.1 manifest, learned pre-registration, weather manifest, 5 code files)
  matches the current files; baselines_candidate.preflight (D-50, R09u off, v1.1 outputs) passes;
- model rows are read through the validation-window parquet filter (no test-window or pre-2024-02-03 row can load);
- weather comes only from the registered extension folder; the IMD folder is refused.

Usage (repo root): python -m Code.candidates.weather_experiment_run [--dest <folder>]
Outputs: Processed_Data/candidates/datagov_prices/experiments/exp_candidate_weather_v1/run/."""
import hashlib, json, sys
from pathlib import Path

import numpy as np
import pandas as pd

from Code.candidates import baselines_candidate as bc, experiment_design as ed, learned_candidate as lc
from Code.candidates import weather_experiment_design as wd, weather_extension as we
from Code.modelling import models as m8

PROTOCOL_SHA256 = 'ac013ab7a3f7d6baeadbbfa9d6f7a8bf861c69b467d99ee228504380fae56c97'   # printed when the protocol was written
PROTOCOL = wd.EXP / 'exp_candidate_weather_v1_protocol.json'
BONFERRONI_TESTS = 6   # 3 crops x 2 quarters (protocol: 99.17% intervals reported, not used to relax)
WX = list(wd.WEATHER_FEATURES)


def verify(root):
    blob = (root / PROTOCOL).read_bytes()
    if hashlib.sha256(blob).hexdigest() != PROTOCOL_SHA256:
        raise bc.GuardError('protocol file does not match the registered digest')
    p = wd.protocol(root); p['restricted_coverage'] = wd.restricted_coverage(root).to_dict('records')
    if json.dumps(p, indent=1, sort_keys=True, default=str).encode() != blob:
        raise bc.GuardError('protocol no longer regenerates byte-identically from the frozen code and data')
    bc.preflight(root)
    if Path(wd.WEATHER_SOURCE).resolve() in {Path(s).resolve() for s in wd.FORBIDDEN_FEATURE_SOURCES}:
        raise bc.GuardError('weather source is a forbidden (validation-only) source')
    return json.loads(blob)


def weather_by_location(root):
    """Registered extension only (Dataset_Candidates/openmeteo_ext/2026-10-24/ext), keyed like the protocol's location join."""
    d = we.load_fetched('ext')
    return {(s.lower(), di.lower()): g.set_index('date').sort_index() for (s, di), g in d.groupby(['state', 'district'])}


def add_weather(df, wx, lag, refit_col):
    return pd.concat([df, wd.weather_features(df, wx, lag_days=lag, refit_dates=df[refit_col].tolist())], axis=1)


def bootstrap_both(df, model_col, reps=bc.REPS, seed=bc.SEED, tests=BONFERRONI_TESTS):
    """The registered market-cluster paired bootstrap (same draws as baselines_candidate.cluster_bootstrap) giving the 95%
    interval and, from the same replicates, the Bonferroni-adjusted interval."""
    a = df.assign(ae_m=(df[model_col] - df.y_target).abs(), ae_b=(df.pred_persistence - df.y_target).abs())
    g = a.groupby('canonical_id').agg(sm=('ae_m', 'sum'), sb=('ae_b', 'sum'), n=('ae_m', 'size'))
    rng = np.random.RandomState(seed)
    idx = rng.randint(0, len(g), size=(reps, len(g)))
    sm, sb = (g[c].to_numpy()[idx].sum(axis=1) for c in ('sm', 'sb'))
    skill = 1 - sm / sb
    lo = 100 * 0.05 / (2 * tests)
    return {'clusters': int(len(g)), 'skill_ci95': [float(np.percentile(skill, 2.5)), float(np.percentile(skill, 97.5))],
            'skill_ci_bonferroni': [float(np.percentile(skill, lo)), float(np.percentile(skill, 100 - lo))],
            'bonferroni_level_pct': round(100 - 2 * lo, 2), 'reps': reps, 'seed': seed}


def acceptance(q, boot, model='price_weather'):
    """The registered rule, unchanged: per crop, MAE < persistence in 2026Q1 AND 2026Q2, 95% CI of skill > 0 in each."""
    rows = []
    for crop in sorted(q.Commodity.unique()):
        r = {'crop': crop}
        for qt in ('2026Q1', '2026Q2'):
            m = q[(q.Commodity == crop) & (q.quarter == qt) & (q.model == model)].iloc[0]
            p = q[(q.Commodity == crop) & (q.quarter == qt) & (q.model == 'persistence')].iloc[0]
            b = boot[(boot.crop == crop) & (boot.period == qt) & (boot.model == model)].iloc[0]
            r.update({f'{qt}_mae_{model}': m.mae, f'{qt}_mae_persistence': p.mae, f'{qt}_skill': m.skill_vs_persistence,
                      f'{qt}_skill_ci95': b.skill_ci95, f'{qt}_skill_ci_bonferroni': b.skill_ci_bonferroni,
                      f'{qt}_pass': bool(m.mae < p.mae and b.skill_ci95[0] > 0)})
        r['passes_preregistered_rule'] = r['2026Q1_pass'] and r['2026Q2_pass']
        rows.append(r)
    return pd.DataFrame(rows)


def fit_score(pool, ev, wx, lag, feats, name):
    """Per crop and refit: the unchanged hgb_conservative on `feats`, trained on weather-district examples ended by the refit
    with every weather feature non-null (climatology bounded by that refit). Returns predictions for ev and a refit log."""
    pred, log = pd.Series(np.nan, index=ev.index), []
    for (crop, r), g in ev.groupby(['Commodity', 'refit']):
        tr = pool[(pool.Commodity == crop) & (pool.t_sun <= r) & (pool.eligible_from <= r)].assign(refit=r)
        tr = add_weather(tr, wx, lag, 'refit').dropna(subset=WX)
        assert len(tr) and tr.t_sun.max() <= r, 'training target after the refit'
        model = m8.LEARNERS['hgb_conservative']()
        X = pd.concat([lc.features(tr), tr[WX]], axis=1)[feats]
        model.fit(X, np.log(tr.y_target / tr.y_origin))
        Xe = pd.concat([lc.features(g), g[WX]], axis=1)[feats]
        pred[g.index] = g.y_origin * np.exp(model.predict(Xe))
        log.append({'model': name, 'crop': crop, 'refit_date': str(r.date()), 'n_train': len(tr), 'train_markets': tr.canonical_id.nunique(),
                    'train_last_target_sunday': str(tr.t_sun.max().date()), 'n_predicted': len(g)})
    if not np.isfinite(pred).all():
        raise bc.GuardError('non-finite predictions')
    return pred, pd.DataFrame(log)


def run(root):
    verify(root)
    wx = weather_by_location(root)
    cols = bc.S + ['origin_week_start', 'target_week_start', 'horizon_weeks', 'y_origin', 'y_target', 'eligible_d41',
                   'lag1', 'lag2', 'lag4', 'lag52', 'weeks_since_prev_obs', 'n_weeks_history']
    mt = bc.guarded_read(root / bc.DATASET / 'model_table_faq_only.parquet', 'target_week_start', cols)
    mt = mt[mt.horizon_weeks == 1].copy()
    mt['period'] = ed.assign_period(mt)
    if mt.period.isin(['test', 'outside']).any() or mt.origin_week_start.min() < pd.Timestamp(bc.cd.CANDIDATE_START):
        raise bc.GuardError('a test-window, out-of-window or pre-2024-02-03 row is present')
    mt = mt[[wd.location_key(c) in wx for c in mt.canonical_id]]          # 46 weather districts only (exact state + district)
    pool = lc.training_pool(mt)
    ev = mt[(mt.period == 'validation') & mt.eligible_d41].copy()
    ev['refit'] = bc.refits_for(ev.origin_week_start + pd.Timedelta(days=6), 'phase8_quarterly').to_numpy()
    ev = add_weather(ev, wx, wd.WINDOW_END_LAG_DAYS['primary'], 'refit')
    n_before = ev.groupby('Commodity').size().to_dict()
    ev = ev.dropna(subset=WX).copy()                                         # identical rows: every weather feature present
    ev['pred_persistence'] = ev.y_origin
    price = list(lc.FEATURES)
    ev['pred_price_weather'], log_pw = fit_score(pool, ev, wx, 1, price + WX, 'price_weather')
    ev['pred_price_only'], log_po = fit_score(pool, ev, wx, 1, price, 'price_only_diagnostic')
    ev['state'] = ev.canonical_id.str.split('|').str[0]
    t = ev.target_week_start + pd.Timedelta(days=6)
    ev['quarter'] = np.where(t <= pd.Timestamp(bc.QUARTERS['2026Q1'][1]), '2026Q1', '2026Q2')
    models = ['pred_persistence', 'pred_price_weather', 'pred_price_only']
    tables = {'by_crop': bc.score(ev, models, ['Commodity']), 'by_crop_quarter': bc.score(ev, models, ['Commodity', 'quarter']),
              'by_crop_state': bc.score(ev, models, ['Commodity', 'state']), 'refit_log': pd.concat([log_pw, log_po], ignore_index=True)}
    boot = [{'crop': c, 'period': p, 'model': m.replace('pred_', ''), **bootstrap_both(g, m)}
            for m in models[1:] for (c, p), g in list(ev.groupby(['Commodity', 'quarter'])) + [((c, 'combined'), g) for c, g in ev.groupby('Commodity')]]
    tables['bootstrap'] = pd.DataFrame(boot)
    tables['acceptance'] = acceptance(tables['by_crop_quarter'], tables['bootstrap'])
    # pre-registered sensitivity analyses: reported, never used to select
    sens = []
    ev6 = add_weather(ev[mt.columns.tolist() + ['refit', 'state', 'quarter', 'pred_persistence']].copy(), wx, wd.WINDOW_END_LAG_DAYS['realtime_sensitivity'], 'refit')
    ev6 = ev6.dropna(subset=WX)
    ev6['pred_realtime_lag6'], _ = fit_score(pool, ev6, wx, 6, price + WX, 'realtime_lag6')
    seven = price + ['wx_rain_sum_7d', 'wx_tmax_mean_7d', 'wx_tmin_mean_7d']
    ev['pred_7day_only'], _ = fit_score(pool, ev, wx, 1, seven, '7day_only')
    v = pd.read_csv(root / we.OUT / 'imd_validation.csv')
    v = v[(v.period == 'extension_2024_2025') & (v.season == 'all') & v.variable.isin(['tmax', 'tmin']) & (v.bias.abs() > 2)]
    high = set(zip(v.state.str.lower(), v.district.str.lower()))
    low_bias = ev[[wd.location_key(c) not in high for c in ev.canonical_id]]
    for name, df, col in [('realtime_lag6', ev6, 'pred_realtime_lag6'), ('7day_only', ev, 'pred_7day_only'),
                          ('excluding_high_bias_locations', low_bias, 'pred_price_weather')]:
        for (c, q), g in df.groupby(['Commodity', 'quarter']):
            r = bc.metrics(g.y_target.to_numpy(), g[col].to_numpy()); p = bc.metrics(g.y_target.to_numpy(), g.pred_persistence.to_numpy())
            sens.append({'sensitivity': name, 'crop': c, 'quarter': q, 'rows': len(g), 'mae': r['mae'], 'persistence_mae': p['mae'],
                         'skill_vs_persistence': 1 - r['mae'] / p['mae'], **{f'ci95_{k}': v_ for k, v_ in zip(('lo', 'hi'), bootstrap_both(g, col)['skill_ci95'])}})
    tables['sensitivity'] = pd.DataFrame(sens)
    tables['state_cluster_bootstrap'] = pd.DataFrame([{'crop': c, 'period': p, **{k: v_ for k, v_ in bootstrap_both(g.assign(canonical_id=g.state), 'pred_price_weather').items()}}
                                                      for (c, p), g in list(ev.groupby(['Commodity', 'quarter']))])
    tables['leave_one_state_out'] = pd.DataFrame([{'crop': c, 'left_out_state': s, 'rows': int((g.state != s).sum()),
                                                   'skill_vs_persistence': 1 - (g[g.state != s].pred_price_weather - g[g.state != s].y_target).abs().mean()
                                                   / (g[g.state != s].pred_persistence - g[g.state != s].y_target).abs().mean()}
                                                  for c, g in ev.groupby('Commodity') for s in sorted(g.state.unique())])
    tables['composition'] = ev.groupby(['Commodity', 'quarter', 'state']).agg(rows=('y_target', 'size'), markets=('canonical_id', 'nunique')).reset_index()
    cov = {'eligible_weather_district_rows_before_missing_feature_drop': n_before, 'scored_rows': ev.groupby('Commodity').size().to_dict(),
           'max_target_week_loaded': str(mt.target_week_start.max().date()), 'min_origin_week_loaded': str(mt.origin_week_start.min().date())}
    preds = ev[bc.S + ['origin_week_start', 'target_week_start', 'quarter', 'refit', 'state', 'y_target'] + models + ['pred_7day_only']]
    return tables, preds, cov


def main(argv=None):
    import argparse
    ap = argparse.ArgumentParser(); ap.add_argument('--dest'); a = ap.parse_args(argv)
    root = Path.cwd()
    tables, preds, cov = run(root)
    dest = Path(a.dest) if a.dest else root / wd.EXP / 'run'; dest.mkdir(parents=True, exist_ok=True)
    for k, t in tables.items():
        t.to_csv(dest / f'{k}.csv', index=False, float_format='%.6f', lineterminator='\n')
    preds.to_parquet(dest / 'validation_predictions.parquet', index=False)
    man = {'protocol_sha256': PROTOCOL_SHA256, 'coverage': cov, 'runner_sha256': hashlib.sha256((root / 'Code/candidates/weather_experiment_run.py').read_bytes()).hexdigest(),
           'outputs_sha256': {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(dest.iterdir()) if p.name != 'run_manifest.json'}}
    (dest / 'run_manifest.json').write_bytes(json.dumps(man, indent=1, default=str).encode())
    print(tables['acceptance'].to_string(index=False)); print(json.dumps(cov, indent=1, default=str))
    return 0


if __name__ == '__main__':
    sys.exit(main())
