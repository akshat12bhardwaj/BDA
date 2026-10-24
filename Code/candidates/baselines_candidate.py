"""Baselines for exp-candidate-v1 on candidate-prices-v1.1 (Data_Source_Review.md §7.3): persistence, seasonal naive and
calendar climatology, scored on TRAIN-TIME and VALIDATION rows only. No learned model.

Guards (preflight refuses to run if any fails):
- protocol: SHA-256 of the LF-normalised protocol file must start with APPROVED_PROTOCOL (the file is written with CRLF
  on Windows; the recorded hash is of the canonical LF text).
- dataset: v1.1 build manifest output hashes; D-50 contract approvals; R09u disabled.
- refits: every scored origin must have a refit on or before it under the APPROVED refit rule (Phase 8 refit_date_for).
- test window: model rows and weekly cells are read with a parquet filter that stops at the last validation target
  week, then asserted; the test window is never loaded, scored, summarised or printed. Only dataset_v1_1 files are
  opened, so no pre-2024-02-03 or 2023-holdout data can enter.

Usage (repo root): python -m Code.candidates.baselines_candidate --refit-rule <approved rule>
Outputs: Processed_Data/candidates/datagov_prices/experiments/exp_candidate_v1/baselines_faq_only_h1/."""
import hashlib, json, sys
from pathlib import Path

import numpy as np
import pandas as pd

from Code.candidates import candidate_decisions as cd, experiment_design as ed
from Code.candidates.datagov_extract import OUT
from Code.modelling.dataset import refit_date_for, refit_schedule

DATASET = OUT / 'dataset_v1_1'
PROTOCOL_FILE = OUT / 'experiment_design_v1_1' / 'exp_candidate_v1_protocol.json'
APPROVED_PROTOCOL = 'a6b1240c'
EXP_DIR = OUT / 'experiments' / 'exp_candidate_v1'
VAL_START, VAL_END = (pd.Timestamp(x) for x in ed.PROPOSED_SPLIT['validation'])    # target Sundays
LAST_ALLOWED_TARGET_WEEK = VAL_END - pd.Timedelta(days=6)                          # Monday of the last validation week
QUARTERS = {'2026Q1': ('2026-01-04', '2026-03-29'), '2026Q2': ('2026-04-05', '2026-06-28')}
SEED, REPS = ed.PHASE8_SEED, 10_000
S = ['Commodity', 'canonical_id', 'Variety']
# Refit rules: 'approved_list' = the protocol list only (cannot score origins before 2026-01-04);
# 'phase8_quarterly' = Phase 8 refit_schedule (first Sunday of every quarter), which the protocol list is a subset of.
REFIT_RULES = {'approved_list': lambda: pd.DatetimeIndex(pd.to_datetime(ed.REFITS)),
               'phase8_quarterly': lambda: refit_schedule('2024-01-01', '2026-12-31')}


class GuardError(RuntimeError):
    pass


def protocol_hash(path=PROTOCOL_FILE):
    return hashlib.sha256(Path(path).read_bytes().replace(b'\r\n', b'\n')).hexdigest()


def preflight(root):
    checks = {'protocol_sha256': protocol_hash(root / PROTOCOL_FILE)}
    if not checks['protocol_sha256'].startswith(APPROVED_PROTOCOL):
        raise GuardError(f'protocol hash {checks["protocol_sha256"][:16]} != approved {APPROVED_PROTOCOL}')
    contract = json.loads((root / DATASET / 'contract.json').read_text())
    if not all(v.startswith('recorded D-50') for v in contract['approvals'].values()) or cd.R09U_APPROVED:
        raise GuardError('D-50 approvals not all recorded, or R09u enabled')
    man = json.loads((root / DATASET / 'build_manifest.json').read_text())
    bad = [f for f, v in man['outputs'].items() if hashlib.sha256((root / DATASET / f).read_bytes()).hexdigest() != v['sha256']]
    if man['version'] != 'candidate-prices-v1.1' or bad:
        raise GuardError(f'dataset is not the recorded v1.1 build: {bad}')
    checks.update({'dataset_version': man['version'], 'dataset_manifest_sha256': hashlib.sha256((root / DATASET / 'build_manifest.json').read_bytes()).hexdigest()})
    return checks


def guarded_read(path, week_col, columns=None):
    """Read rows whose week <= the last validation target week only; the test window never enters memory."""
    df = pd.read_parquet(path, columns=columns, filters=[(week_col, '<=', LAST_ALLOWED_TARGET_WEEK)])
    if len(df) and df[week_col].max() > LAST_ALLOWED_TARGET_WEEK:
        raise GuardError(f'{path.name}: row beyond the validation window was loaded')
    return df


def refits_for(origin_sundays, rule):
    """Phase 8 refit_date_for under the approved rule; raises if any scored origin precedes the first refit."""
    try:
        return refit_date_for(origin_sundays, REFIT_RULES[rule]())
    except Exception as e:
        raise GuardError(f'refit rule {rule!r}: {e}') from e


# ---------------------------------------------------------------- baselines
def seasonal_naive(rows, weekly):
    """Series weekly median 52 weeks before the TARGET week (Phase 8 definition); NaN where it does not exist."""
    look = weekly[S + ['week_start', 'target_median']].rename(columns={'target_median': 'pred_seasonal_naive'})
    look['target_week_start'] = look.week_start + pd.Timedelta(weeks=52)
    return rows.merge(look.drop(columns='week_start'), on=S + ['target_week_start'], how='left').pred_seasonal_naive.to_numpy()


def climatology(rows, train_pool, rule):
    """Per refit: crop-level median training target of the target-week month, from examples whose target Sunday is <= refit
    and whose series was D-41 eligible by the refit (Phase 8 CalendarClimatology + D-41 clarification 2). train_pool is
    every guarded example (train AND earlier validation targets): Phase 8 refits are expanding windows over all targets
    that ended by the refit date."""
    rows = rows.assign(refit=refits_for(rows.origin_week_start + pd.Timedelta(days=6), rule).to_numpy(),
                       month=(rows.target_week_start + pd.Timedelta(days=3)).dt.month)
    first_ok = train_pool[train_pool.eligible_d41].groupby(S, observed=True).origin_week_start.min() + pd.Timedelta(days=6)
    pool = train_pool.join(first_ok.rename('eligible_from'), on=S)
    pool['t_sun'] = pool.target_week_start + pd.Timedelta(days=6)
    pool['month'] = (pool.target_week_start + pd.Timedelta(days=3)).dt.month   # Thursday names the week's month (Phase 8)
    out = pd.Series(np.nan, index=rows.index)
    for r, g in rows.groupby('refit'):
        tr = pool[(pool.t_sun <= r) & (pool.eligible_from <= r)]
        med = tr.groupby(['Commodity', 'month']).y_target.median()
        out[g.index] = [med.get((c, m), np.nan) for c, m in zip(g.Commodity, g.month)]
    return out.to_numpy(), rows.refit


# ---------------------------------------------------------------- metrics and uncertainty
MAPE_UNSTABLE_SHARE = 0.20   # fixed before any result: MAPE flagged unstable if the top 1% of rows carry >= 20% of total APE


def metrics(y, p):
    e = p - y
    ape = np.abs(e) / y
    top = float(np.sort(ape)[-max(1, len(ape) // 100):].sum() / ape.sum()) if ape.sum() else 0.0
    return {'n': int(len(y)), 'mae': float(np.mean(np.abs(e))), 'rmse': float(np.sqrt(np.mean(e ** 2))),
            'mape_pct': float(100 * ape.mean()), 'median_ape_pct': float(100 * np.median(ape)),
            'mape_top1pct_share': top, 'targets_below_100': int((y < 100).sum()), 'mape_unstable': bool(top >= MAPE_UNSTABLE_SHARE)}


def cluster_bootstrap(df, model_col, base_col='pred_persistence', cluster='canonical_id', reps=REPS, seed=SEED):
    """Paired cluster bootstrap of the MAE difference (model - persistence) and skill; markets resampled with replacement."""
    a = df.assign(ae_m=(df[model_col] - df.y_target).abs(), ae_b=(df[base_col] - df.y_target).abs())
    g = a.groupby(cluster).agg(sm=('ae_m', 'sum'), sb=('ae_b', 'sum'), n=('ae_m', 'size'))
    if len(g) < 2:
        return {'clusters': int(len(g)), 'note': 'too few clusters'}
    rng = np.random.RandomState(seed)
    idx = rng.randint(0, len(g), size=(reps, len(g)))
    sm, sb, n = (g[c].to_numpy()[idx].sum(axis=1) for c in ('sm', 'sb', 'n'))
    diff, skill = (sm - sb) / n, 1 - sm / sb
    q = lambda x: [float(np.percentile(x, 2.5)), float(np.percentile(x, 97.5))]
    return {'clusters': int(len(g)), 'mae_diff_ci95': q(diff), 'skill_ci95': q(skill), 'reps': reps, 'seed': seed}


def score(df, models, by=()):
    rows = []
    groups = df.groupby(list(by)) if by else [((), df)]
    for k, g in groups:
        base = metrics(g.y_target.to_numpy(), g.pred_persistence.to_numpy())
        for m in models:
            r = metrics(g.y_target.to_numpy(), g[m].to_numpy())
            rows.append({**dict(zip(by, k if isinstance(k, tuple) else (k,))), 'model': m.replace('pred_', ''), **r,
                         'skill_vs_persistence': 1 - r['mae'] / base['mae'] if base['mae'] else None,
                         'markets': g.canonical_id.nunique(), 'states': g.state.nunique(), 'target_weeks': g.target_week_start.nunique()})
    return pd.DataFrame(rows)


def run(root, rule, design='faq_only', h=1):
    pre = preflight(root)
    cols = S + ['origin_week_start', 'target_week_start', 'horizon_weeks', 'y_origin', 'y_target', 'eligible_d41']
    mt = guarded_read(root / DATASET / f'model_table_{design}.parquet', 'target_week_start', cols)
    mt = mt[mt.horizon_weeks == h]
    weekly = guarded_read(root / DATASET / f'weekly_{design}.parquet', 'week_start', S + ['week_start', 'target_median'])
    mt['period'] = ed.assign_period(mt)
    if (mt.period == 'test').any() or (mt.period == 'outside').any():
        raise GuardError('test-window or out-of-window rows present after the guarded read')
    ev = mt[(mt.period == 'validation') & mt.eligible_d41].copy()
    if (ev.y_target <= 0).any():
        raise GuardError('non-positive target: MAPE undefined')
    ev['pred_persistence'] = ev.y_origin
    ev['pred_seasonal_naive'] = seasonal_naive(ev, weekly)
    ev['pred_calendar_climatology'], ev['refit'] = climatology(ev, mt, rule)   # expanding window; filtered by refit inside
    ev['state'] = ev.canonical_id.str.split('|').str[0]
    t = ev.target_week_start + pd.Timedelta(days=6)
    ev['quarter'] = np.select([t <= pd.Timestamp(QUARTERS['2026Q1'][1])], ['2026Q1'], '2026Q2')
    models = ['pred_seasonal_naive', 'pred_calendar_climatology']
    ident = ev.dropna(subset=['pred_persistence'] + models)               # identical rows for every baseline
    cov = {c: {'eligible_validation_rows': int((ev.Commodity == c).sum()),
               'seasonal_naive_available': int(((ev.Commodity == c) & ev.pred_seasonal_naive.notna()).sum()),
               'climatology_available': int(((ev.Commodity == c) & ev.pred_calendar_climatology.notna()).sum()),
               'identical_rows': int((ident.Commodity == c).sum()),
               'targets_below_100_rs_per_q': int(((ev.Commodity == c) & (ev.y_target < 100)).sum())} for c in sorted(ev.Commodity.unique())}
    res = {'preflight': pre, 'refit_rule': rule, 'refits_used': {str(k.date()): int(v) for k, v in ev.refit.value_counts().sort_index().items()},
           'coverage': cov}
    tables = {'by_crop': score(ident, ['pred_persistence'] + models, ['Commodity']),
              'by_crop_quarter': score(ident, ['pred_persistence'] + models, ['Commodity', 'quarter']),
              'by_crop_state': score(ident, ['pred_persistence'] + models, ['Commodity', 'state']),
              'persistence_all_eligible_rows': score(ev, ['pred_persistence'], ['Commodity', 'quarter'])}
    boot, loso = [], []
    for (c, q), g in list(ident.groupby(['Commodity', 'quarter'])) + [((c, 'combined'), g) for c, g in ident.groupby('Commodity')]:
        for m in models:
            boot.append({'crop': c, 'period': q, 'model': m.replace('pred_', ''), **cluster_bootstrap(g, m)})
    for c, g in ident.groupby('Commodity'):
        for s in sorted(g.state.unique()):
            x = g[g.state != s]
            for m in models:
                loso.append({'crop': c, 'left_out_state': s, 'model': m.replace('pred_', ''), 'rows': len(x),
                             'skill_vs_persistence': 1 - (x[m] - x.y_target).abs().mean() / (x.pred_persistence - x.y_target).abs().mean()})
    tables['bootstrap'] = pd.DataFrame(boot); tables['leave_one_state_out'] = pd.DataFrame(loso)
    return res, tables


def main(argv=None):
    import argparse
    ap = argparse.ArgumentParser(); ap.add_argument('--refit-rule', required=True, choices=sorted(REFIT_RULES))
    ap.add_argument('--dest'); a = ap.parse_args(argv)
    root = Path.cwd()
    base = Path(a.dest) if a.dest else root / EXP_DIR / f'baselines_{a.refit_rule}'
    code = {p: hashlib.sha256((root / p).read_bytes()).hexdigest() for p in
            ['Code/candidates/baselines_candidate.py', 'Code/candidates/experiment_design.py', 'Code/modelling/dataset.py']}
    runs = {}
    # primary first (faq_only, h = 1), then the protocol's secondary horizons and sensitivity designs
    for design, h in [('faq_only', 1), ('faq_only', 2), ('faq_only', 4)] + [(d, k) for d in ('faq_local', 'pooled') for k in (1, 2, 4)]:
        res, tables = run(root, a.refit_rule, design, h)
        dest = base / f'{design}_h{h}'; dest.mkdir(parents=True, exist_ok=True)
        for k, t in tables.items():
            t.to_csv(dest / f'{k}.csv', index=False, float_format='%.6f', lineterminator='\n')
        res.update({'experiment': 'exp-candidate-v1', 'design': design, 'horizon': h, 'periods_scored': ['validation'],
                    'seed': SEED, 'reps': REPS, 'code_sha256': code,
                    'outputs_sha256': {f'{k}.csv': hashlib.sha256((dest / f'{k}.csv').read_bytes()).hexdigest() for k in tables}})
        (dest / 'run_manifest.json').write_bytes(json.dumps(res, indent=1, default=str).encode())
        runs[f'{design}_h{h}'] = {'refits_used': res['refits_used'], 'coverage': res['coverage']}
    (base / 'run_index.json').write_bytes(json.dumps({'protocol_sha256': res['preflight']['protocol_sha256'], 'refit_rule': a.refit_rule,
                                                      'runs': runs}, indent=1, default=str).encode())
    print(json.dumps(runs, indent=1, default=str))
    return 0


if __name__ == '__main__':
    sys.exit(main())
