"""One pre-registered exploratory learned model for exp-candidate-v1 (Data_Source_Review.md §7.5): FAQ-only, h = 1,
price-only, the frozen Phase 8 `hgb_conservative` estimator unchanged. Validation only; persistence stays the default.

Two steps, so nothing can be chosen after seeing results:
  --register   writes learned_preregistration.json (features, target, training rule, selection rule, seed, and the
               SHA-256 of the protocol, dataset manifest and every code file involved) and prints its hash.
  --run SHA    refuses to train unless the registration file hashes to SHA and every recorded input hash still matches;
               then runs the baseline guards (protocol, D-50, v1.1, test-window filter, refits) before fitting anything.

Usage (repo root): python -m Code.candidates.learned_candidate --register | --run <prereg sha256> [--dest <folder>]
Outputs: Processed_Data/candidates/datagov_prices/experiments/exp_candidate_v1/learned_hgb_conservative_faq_only_h1/."""
import hashlib, json, sys
from pathlib import Path

import numpy as np
import pandas as pd

from Code.candidates import baselines_candidate as bc, experiment_design as ed
from Code.modelling import models as m8

DESIGN, H, RULE = 'faq_only', 1, 'phase8_quarterly'
EXP = bc.EXP_DIR / 'learned_hgb_conservative_faq_only_h1'
PREREG = EXP / 'learned_preregistration.json'
HASHED_CODE = ['Code/candidates/learned_candidate.py', 'Code/candidates/baselines_candidate.py', 'Code/candidates/experiment_design.py',
               'Code/modelling/models.py', 'Code/modelling/dataset.py']
# Pre-registered price-only features: every input is a model-table column computed from weeks <= the origin week.
FEATURES = {
    'log_y_origin': 'log(y_origin): origin-week median modal (Phase 8 anchor, log scale as in design_matrix)',
    'r_lag1': 'lag1 / y_origin: median of the week before the origin week; NaN if that week has no cell',
    'r_lag2': 'lag2 / y_origin: two weeks before; NaN if absent',
    'r_lag4': 'lag4 / y_origin: four weeks before; NaN if absent',
    'r_lag52': 'lag52 / y_origin: 52 weeks before the ORIGIN week; NaN if absent (all series before 2025-02)',
    'weeks_since_prev_obs': 'weeks between the origin week and the series previous observed week; NaN for the first week',
    'log1p_n_weeks_history': 'log1p(number of observed weeks up to and including the origin week)',
    'month_sin': 'sin(2*pi*(month-1)/12), month of the origin week Thursday (Phase 8 calendar convention)',
    'month_cos': 'cos(2*pi*(month-1)/12), same month',
}
SELECTION_RULE = ('per crop: eligible for further consideration only if MAE(learned) < MAE(persistence) in 2026Q1 AND in 2026Q2, '
                  'AND the market-clustered 95% CI of skill vs persistence is entirely above 0 in each quarter; identical eligible rows; '
                  f'{bc.REPS} replicates, seed {bc.SEED}; fixed before any training, never relaxed')


def features(df):
    """Row-wise, no fitted state (Phase 8 design_matrix style). Missing values stay NaN: HGB handles them natively."""
    m = (df.origin_week_start + pd.Timedelta(days=3)).dt.month
    X = pd.DataFrame({'log_y_origin': np.log(df.y_origin),
                      **{f'r_lag{k}': df[f'lag{k}'] / df.y_origin for k in (1, 2, 4, 52)},
                      'weeks_since_prev_obs': df.weeks_since_prev_obs.astype('float64'),
                      'log1p_n_weeks_history': np.log1p(df.n_weeks_history.astype('float64')),
                      'month_sin': np.sin(2 * np.pi * (m - 1) / 12), 'month_cos': np.cos(2 * np.pi * (m - 1) / 12)}, index=df.index)
    assert list(X.columns) == list(FEATURES)
    return X


def estimator_params():
    keep = ('max_iter', 'learning_rate', 'max_leaf_nodes', 'min_samples_leaf', 'l2_regularization', 'early_stopping', 'random_state')
    return {k: v for k, v in m8.LEARNERS['hgb_conservative']().get_params().items() if k in keep}


def registration(root):
    pre = bc.preflight(root)
    return {'experiment': 'exp-candidate-v1 / learned', 'design': DESIGN, 'horizon': H, 'refit_rule': RULE,
            'estimator': "Code.modelling.models.LEARNERS['hgb_conservative'] (unchanged)", 'estimator_params': estimator_params(),
            'one_model_per': 'crop (h = 1 only)', 'features': FEATURES,
            'target': 'log(y_target / y_origin); prediction = y_origin * exp(model output) (Phase 8 log_ratio)',
            'training_rule': 'at refit T: all examples with target Sunday <= T whose series reached D-41 eligibility at an origin '
                             'Sunday <= T, including that series earlier weeks (Phase 8 training_examples, eligible_by_refit)',
            'evaluation_rows': 'validation (target Sundays 2026-01-04 .. 2026-06-28), eligible_d41 at the origin; identical rows '
                               'for learned and persistence',
            'selection_rule': SELECTION_RULE, 'seed': bc.SEED, 'reps': bc.REPS,
            'hashes': {'protocol_lf_sha256': pre['protocol_sha256'], 'dataset_manifest_sha256': pre['dataset_manifest_sha256'],
                       **{p: hashlib.sha256((root / p).read_bytes()).hexdigest() for p in HASHED_CODE}}}


def register(root):
    path = root / PREREG
    if path.exists():
        raise SystemExit(f'{path} already exists: the registration is written once')
    path.parent.mkdir(parents=True, exist_ok=True)
    blob = json.dumps(registration(root), indent=1, sort_keys=True).encode()
    path.write_bytes(blob)
    return hashlib.sha256(blob).hexdigest()


def verify_registration(root, sha):
    blob = (root / PREREG).read_bytes()
    if hashlib.sha256(blob).hexdigest() != sha:
        raise bc.GuardError('registration file does not match the recorded hash')
    if json.loads(blob) != json.loads(json.dumps(registration(root), sort_keys=True)):
        raise bc.GuardError('code, protocol, dataset or settings changed since registration')


def training_pool(mt):
    first_ok = mt[mt.eligible_d41].groupby(bc.S, observed=True).origin_week_start.min() + pd.Timedelta(days=6)
    p = mt.join(first_ok.rename('eligible_from'), on=bc.S)
    p['t_sun'] = p.target_week_start + pd.Timedelta(days=6)
    return p


def fit_predict(mt, ev):
    """Per crop and refit: fit the unchanged estimator on examples ended by the refit, predict that refit's origins."""
    pool = training_pool(mt)
    pred, log = pd.Series(np.nan, index=ev.index), []
    for (crop, r), g in ev.groupby(['Commodity', 'refit']):
        tr = pool[(pool.Commodity == crop) & (pool.t_sun <= r) & (pool.eligible_from <= r)]
        assert tr.t_sun.max() <= r < g.origin_week_start.min() + pd.Timedelta(days=7), 'training target after the refit'
        model = m8.LEARNERS['hgb_conservative']()
        model.fit(features(tr), np.log(tr.y_target / tr.y_origin))
        pred[g.index] = g.y_origin * np.exp(model.predict(features(g)))
        log.append({'crop': crop, 'refit_date': str(r.date()), 'n_train': len(tr), 'n_train_not_yet_origin_eligible': int((~tr.eligible_d41).sum()),
                    'train_last_target_sunday': str(tr.t_sun.max().date()), 'n_predicted': len(g)})
    if not np.isfinite(pred).all():
        raise bc.GuardError('non-finite predictions')
    return pred.to_numpy(), pd.DataFrame(log)


def selection(boot, q):
    rows = []
    for crop in sorted(q.Commodity.unique()):
        r = {'crop': crop}
        for qt in ('2026Q1', '2026Q2'):
            l = q[(q.Commodity == crop) & (q.quarter == qt) & (q.model == 'learned')].iloc[0]
            p = q[(q.Commodity == crop) & (q.quarter == qt) & (q.model == 'persistence')].iloc[0]
            ci = boot[(boot.crop == crop) & (boot.period == qt)].skill_ci95.iloc[0]
            r.update({f'{qt}_mae_learned': l.mae, f'{qt}_mae_persistence': p.mae, f'{qt}_skill': l.skill_vs_persistence,
                      f'{qt}_skill_ci95': ci, f'{qt}_pass': bool(l.mae < p.mae and ci[0] > 0)})
        r['passes_preregistered_rule'] = r['2026Q1_pass'] and r['2026Q2_pass']
        rows.append(r)
    return pd.DataFrame(rows)


def run(root, sha):
    verify_registration(root, sha)
    bc.preflight(root)
    cols = bc.S + ['origin_week_start', 'target_week_start', 'horizon_weeks', 'y_origin', 'y_target', 'eligible_d41',
                   'lag1', 'lag2', 'lag4', 'lag52', 'weeks_since_prev_obs', 'n_weeks_history']
    mt = bc.guarded_read(root / bc.DATASET / f'model_table_{DESIGN}.parquet', 'target_week_start', cols)
    mt = mt[mt.horizon_weeks == H].copy()
    mt['period'] = ed.assign_period(mt)
    if mt.period.isin(['test', 'outside']).any():
        raise bc.GuardError('test-window or out-of-window rows present after the guarded read')
    ev = mt[(mt.period == 'validation') & mt.eligible_d41].copy()
    ev['refit'] = bc.refits_for(ev.origin_week_start + pd.Timedelta(days=6), RULE).to_numpy()
    ev['pred_persistence'] = ev.y_origin
    ev['pred_learned'], refit_log = fit_predict(mt, ev)
    ev['state'] = ev.canonical_id.str.split('|').str[0]
    t = ev.target_week_start + pd.Timedelta(days=6)
    ev['quarter'] = np.select([t <= pd.Timestamp(bc.QUARTERS['2026Q1'][1])], ['2026Q1'], '2026Q2')
    tables = {'by_crop': bc.score(ev, ['pred_persistence', 'pred_learned'], ['Commodity']),
              'by_crop_quarter': bc.score(ev, ['pred_persistence', 'pred_learned'], ['Commodity', 'quarter']),
              'by_crop_state': bc.score(ev, ['pred_persistence', 'pred_learned'], ['Commodity', 'state']), 'refit_log': refit_log}
    boot = [{'crop': c, 'period': p, **bc.cluster_bootstrap(g, 'pred_learned')}
            for (c, p), g in list(ev.groupby(['Commodity', 'quarter'])) + [((c, 'combined'), g) for c, g in ev.groupby('Commodity')]]
    tables['bootstrap'] = pd.DataFrame(boot)
    tables['leave_one_state_out'] = pd.DataFrame([{'crop': c, 'left_out_state': s, 'rows': int((g.state != s).sum()),
                                                   'skill_vs_persistence': 1 - (g[g.state != s].pred_learned - g[g.state != s].y_target).abs().mean()
                                                   / (g[g.state != s].pred_persistence - g[g.state != s].y_target).abs().mean()}
                                                  for c, g in ev.groupby('Commodity') for s in sorted(g.state.unique())])
    tables['selection'] = selection(tables['bootstrap'], tables['by_crop_quarter'])
    preds = ev[bc.S + ['origin_week_start', 'target_week_start', 'quarter', 'refit', 'y_target', 'pred_persistence', 'pred_learned']]
    return tables, preds


def main(argv=None):
    import argparse
    ap = argparse.ArgumentParser(); g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument('--register', action='store_true'); g.add_argument('--run', metavar='PREREG_SHA256'); ap.add_argument('--dest')
    a = ap.parse_args(argv); root = Path.cwd()
    if a.register:
        print('registered:', register(root)); return 0
    tables, preds = run(root, a.run)
    dest = Path(a.dest) if a.dest else root / EXP / 'run'; dest.mkdir(parents=True, exist_ok=True)
    for k, t in tables.items():
        t.to_csv(dest / f'{k}.csv', index=False, float_format='%.6f', lineterminator='\n')
    preds.to_parquet(dest / 'validation_predictions.parquet', index=False)
    man = {'prereg_sha256': a.run, 'outputs_sha256': {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(dest.iterdir())
                                                      if p.name != 'run_manifest.json'}}
    (dest / 'run_manifest.json').write_bytes(json.dumps(man, indent=1).encode())
    print(tables['selection'].to_string(index=False))
    return 0


if __name__ == '__main__':
    sys.exit(main())
