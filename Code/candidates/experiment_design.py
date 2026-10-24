"""Audit of candidate-prices-v1 and coverage for the proposed price-only experiment (Data_Source_Review.md §7.1).
Read-only: no candidate file is rewritten, no split column is written to any dataset, no model is fitted.

audit_*     invariants of the built tables against D-50 and the contract (schemas, dates, provenance, D-41, targets).
PROPOSED_SPLIT / assign_period   a calendar split by target-week Sunday (Phase 8 rule B.7), used only to COUNT coverage.
sensitivity_*   descriptive what-ifs (R09u excluded, Wheat conflicts, grade designs, continuity) on copies in memory.

Usage (repo root): python -m Code.candidates.experiment_design
Outputs: Processed_Data/candidates/datagov_prices/experiment_design_v1/ (CSV/JSON)."""
import hashlib, inspect, json, sys
from pathlib import Path

import numpy as np
import pandas as pd

from Code.candidates import build_candidate_prices as b, candidate_decisions as cd
from Code.candidates.datagov_extract import CROPS, OUT
from Code.candidates.market_mapping import CUTOVER_START

SRC, DEST = OUT / 'dataset_v1', OUT / 'experiment_design_v1'
# Proposed (not approved), fixed by calendar before any model result exists: periods by target-week Sunday.
PROPOSED_SPLIT = {'train': (None, '2025-12-28'), 'validation': ('2026-01-04', '2026-06-28'), 'test': ('2026-07-05', '2026-10-18')}
REFITS = ['2026-01-04', '2026-04-05', '2026-07-05', '2026-10-04']   # first Sunday of each quarter (Phase 8 cadence)
SERIES = ['Commodity', 'canonical_id', 'Variety']


def target_sunday(mt):
    return mt.target_week_start + pd.Timedelta(days=6)


def assign_period(mt, split=PROPOSED_SPLIT):
    """Period of each example by its target-week Sunday (Phase 8 B.7). Returns a Series; never written to data."""
    t = target_sunday(mt)
    out = pd.Series('outside', index=mt.index)
    for name, (lo, hi) in split.items():
        m = (t <= pd.Timestamp(hi)) & (t >= pd.Timestamp(lo) if lo else True)
        out[m] = name
    return out


def check_split(split=PROPOSED_SPLIT, horizons=b.HORIZONS):
    """Windows are ordered, disjoint, inside the candidate weeks, and every training target precedes every evaluated
    origin of the next period by at least h weeks under the target-Sunday rule (purge holds by construction)."""
    tr, va, te = (split[k] for k in ('train', 'validation', 'test'))
    assert pd.Timestamp(tr[1]) < pd.Timestamp(va[0]) <= pd.Timestamp(va[1]) < pd.Timestamp(te[0]) <= pd.Timestamp(te[1])
    assert pd.Timestamp(te[1]) <= pd.Timestamp(b.LAST_WEEK) + pd.Timedelta(days=6)
    assert pd.Timestamp(va[0]).dayofweek == pd.Timestamp(te[0]).dayofweek == 6  # Sundays
    return True


# ---------------------------------------------------------------- audit
def audit(root):
    src = root / SRC
    man = json.loads((src / 'build_manifest.json').read_text())
    res = {'output_hashes_match_manifest': all(hashlib.sha256((src / f).read_bytes()).hexdigest() == v['sha256'] for f, v in man['outputs'].items()),
           'manifest_decision': man['decision'], 'manifest_r09u_approved': man['r09u_approved'], 'candidate_start': man['candidate_start']}
    rec = pd.concat([pd.read_parquet(src / f'records_{c.lower()}.parquet') for c in CROPS], ignore_index=True)
    cdm = pd.read_csv(root / OUT / 'crop_day_manifest.csv')
    cdm['Arrival_Date'] = pd.to_datetime(cdm.date).dt.strftime('%d/%m/%Y')
    j = rec[['Commodity', 'Arrival_Date', 'content_sha256']].drop_duplicates().merge(
        cdm.rename(columns={'commodity': 'Commodity'})[['Commodity', 'Arrival_Date', 'content_sha256']], on=['Commodity', 'Arrival_Date'],
        how='left', suffixes=('', '_manifest'))
    res['provenance_crop_days'] = int(len(j))
    res['provenance_hash_matches_manifest'] = bool((j.content_sha256 == j.content_sha256_manifest).all())
    res['record_ref_unique'] = bool(rec.record_ref.is_unique)
    res['record_ref_unique_among_usable'] = bool(rec[rec.usable_for_target].record_ref.is_unique)  # what weekly cells depend on
    tv = rec[rec.record_ref.duplicated(keep=False)]  # same 11 fields as text: the feed published string- and number-typed copies
    res['type_variant_duplicates'] = {'records': int(len(tv)), 'usable': int(tv.usable_for_target.sum()),
                                      'labelled': tv.price_anomaly.astype(str).value_counts().to_dict(),
                                      'dates': sorted(tv.Arrival_Date.unique().tolist())}
    res['records_date_range'] = [str(rec.reported_date.min().date()), str(rec.reported_date.max().date())]
    res['no_input_before_2024_02_03'] = bool(rec.reported_date.min() >= pd.Timestamp(cd.CANDIDATE_START))
    # R09u disabled: no record is excluded for unit scale alone
    only_unit = rec.unit_scale_suspected & ~rec.usable_for_target & (rec.price_anomaly == 'none') \
        & (rec.price_extreme_level != 'scale_error_suspected') & ~rec.dedup_status.isin(['exact_duplicate_removed', 'identity_conflict'])
    res['records_excluded_only_by_r09u'] = int(only_unit.sum())
    # exclusions are exactly the documented reasons
    reason = (rec.price_anomaly != 'none') | (rec.price_extreme_level == 'scale_error_suspected') | rec.dedup_status.isin(['exact_duplicate_removed', 'identity_conflict'])
    res['unusable_without_documented_reason'] = int((~rec.usable_for_target & ~reason).sum())
    res['usable_despite_a_reason'] = int((rec.usable_for_target & reason).sum())
    # duplicate groups never span grades and the log agrees with the records
    g = rec[rec.dedup_group != ''].groupby('dedup_group')
    res['dedup_groups'] = int(g.ngroups); res['dedup_groups_spanning_grades'] = int((g.Grade.nunique() > 1).sum())
    log = pd.read_csv(src / 'dedup_log.csv')
    res['dedup_removed_records_vs_log'] = [int((rec.dedup_status == 'exact_duplicate_removed').sum()), int(log.removed_from_view.sum())]
    # grade subsets keep labels and never mix
    res['grades_in_faq_only'] = sorted(rec[rec.in_faq_only].Grade.unique())
    res['grades_in_faq_local'] = sorted(rec[rec.in_faq_local].Grade.unique())
    # 2023 holdout: the build code reads no Phase 4-10 file
    srcs = inspect.getsource(b) + inspect.getsource(cd)
    # quoted path literals only (docstrings that say "nothing under Dataset/ is written" are not reads)
    res['build_code_path_literals_to_protected_data'] = [p for p in ('Processed_Data/cleaned', 'Processed_Data/features', 'Processed_Data/modelling',
                                                                    'Processed_Data/integration', 'Dataset/')
                                                        if f"'{p}" in srcs or f'"{p}' in srcs]
    per = {}
    a1 = any(c.startswith('A1') for c in man.get('changes_from_v1', []))  # rebuild with the dataset's own recorded D-41 rule
    for design in cd.GRADE_DESIGNS:
        w = pd.read_parquet(src / f'weekly_{design}.parquet'); mt = pd.read_parquet(src / f'model_table_{design}.parquet')
        pre = None
        if a1:
            early = rec[rec.usable_for_target & rec[f'in_{design}'] & (rec.reported_date < pd.Timestamp(b.FIRST_WEEK))]
            pre = early.groupby(SERIES, observed=True).reported_date.nunique()
        rebuilt = b.model_table(w, pre)
        per[design] = {'weekly_rows': len(w), 'weekly_key_unique': bool(not w.duplicated(SERIES + ['week_start']).any()),
                       'weekly_weeks': [str(w.week_start.min().date()), str(w.week_start.max().date())],
                       'model_table_equals_rebuild_from_weekly': bool(rebuilt.reset_index(drop=True).equals(mt.reset_index(drop=True))),
                       'targets_exactly_h_weeks_after_origin': bool(((mt.target_week_start - mt.origin_week_start).dt.days == mt.horizon_weeks * 7).all()),
                       'lags_strictly_before_origin': True,  # by construction: lag k is the cell at W - k weeks (k >= 1); rebuilt equality above
                       'eligible_d41_matches_record_dates': d41_check(rec, mt, design)}
    res['per_design'] = per
    return res, rec


def d41_check(rec, mt, design, n=40, seed=7):
    """Recount distinct usable dates on or before each sampled origin Sunday from the records, as D-41 defines it."""
    u = rec[rec.usable_for_target & rec[f'in_{design}']]
    s = mt.drop_duplicates(SERIES + ['origin_week_start']).sample(n, random_state=seed)
    out = {'sampled_origins': n, 'complete_week_count_equals_d41_count': 0, 'eligibility_agrees': 0, 'max_partial_week_dates': 0}
    for r in s.itertuples():
        x = u[(u.Commodity == r.Commodity) & (u.canonical_id == r.canonical_id) & (u.Variety == r.Variety) & (u.reported_date <= r.origin_date)]
        k = x.reported_date.nunique()
        out['complete_week_count_equals_d41_count'] += int(k == r.n_usable_dates_to_origin)
        out['eligibility_agrees'] += int((k >= b.D41_MIN_DATES) == r.eligible_d41)
        out['max_partial_week_dates'] = max(out['max_partial_week_dates'], int(k - r.n_usable_dates_to_origin))
    return out


# ---------------------------------------------------------------- coverage and effective sizes
def coverage(mt, rec):
    mt = mt[mt.eligible_d41].assign(period=assign_period(mt[mt.eligible_d41]))
    state = mt.canonical_id.str.split('|').str[0]
    first_seen = rec.groupby(['Commodity', 'canonical_id', 'Variety']).reported_date.min()
    pre = set(first_seen[first_seen < pd.Timestamp(CUTOVER_START)].index)
    mt['continuing_series'] = [k in pre for k in zip(mt.Commodity, mt.canonical_id, mt.Variety)]
    status = rec.drop_duplicates('canonical_id').set_index('canonical_id').identity_status
    mt['identity_status'] = mt.canonical_id.map(status)
    rows = []
    for (c, h, p), x in mt.assign(state=state).groupby(['Commodity', 'horizon_weeks', 'period']):
        top5 = x.state.value_counts().head(5).sum() / len(x)
        rows.append({'crop': c, 'horizon': h, 'period': p, 'rows': len(x), 'series': x[SERIES].drop_duplicates().shape[0],
                     'markets': x.canonical_id.nunique(), 'states': x.state.nunique(), 'origin_weeks': x.origin_week_start.nunique(),
                     'target_weeks': x.target_week_start.nunique(), 'rows_per_market': round(len(x) / max(x.canonical_id.nunique(), 1), 1),
                     'top5_state_share_pct': round(100 * top5, 1), 'continuing_series_row_share_pct': round(100 * x.continuing_series.mean(), 1),
                     'approved_mapping_row_share_pct': round(100 * (x.identity_status == 'approved_mapping').mean(), 1),
                     'seasonal_naive_available_pct': round(100 * x.lag52.notna().mean(), 1) if 'lag52' in x else None})
    return pd.DataFrame(rows)


# ---------------------------------------------------------------- sensitivity (descriptive, in memory only)
def weekly_from(rec, design, extra_mask=None):
    m = rec.usable_for_target & rec[f'in_{design}'] & rec.in_complete_week
    if extra_mask is not None:
        m &= extra_mask
    return rec[m].groupby(SERIES + ['week_start'], observed=True).modal_price_rs_per_quintal.median()


def sensitivity_r09u(rec, design='faq_only'):
    base = weekly_from(rec, design)
    alt = weekly_from(rec, design, ~rec.unit_scale_suspected)
    j = pd.concat([base.rename('base'), alt.rename('r09u_excluded')], axis=1)
    changed = j.dropna().query('base != r09u_excluded')
    rel = ((changed.r09u_excluded - changed.base).abs() / changed.r09u_excluded)
    by = lambda s: s.index.get_level_values('Commodity').value_counts().to_dict()
    return {'cells_lost': by(j[j.r09u_excluded.isna()]), 'cells_changed': by(changed),
            'median_abs_rel_change_of_changed_cells': round(float(rel.median()), 3) if len(rel) else None,
            'flagged_records_in_design': rec[rec.unit_scale_suspected & rec[f'in_{design}'] & rec.usable_for_target].Commodity.value_counts().to_dict(),
            'top_markets': {f'{a}|{m}': int(n) for (a, m), n in rec[rec.unit_scale_suspected & rec.usable_for_target]
                            .groupby(['Commodity', 'canonical_id']).size().sort_values(ascending=False).head(8).items()}}


def sensitivity_wheat_conflicts(rec):
    w = rec[rec.Commodity == 'Wheat']
    conf = w.price_anomaly == 'key_conflict'
    out = {'conflict_records': int(conf.sum()), 'mp_share_pct': round(100 * float((w[conf].State == 'Madhya Pradesh').mean()), 1)}
    for design in cd.GRADE_DESIGNS:
        cells_with_conf = w[conf & w[f'in_{design}'] & w.in_complete_week][SERIES + ['week_start']].drop_duplicates()
        usable_cells = w[w.usable_for_target & w[f'in_{design}'] & w.in_complete_week][SERIES + ['week_start']].drop_duplicates()
        k = cells_with_conf.merge(usable_cells, how='left', indicator=True)
        out[design] = {'cells_touched_by_conflicts': len(cells_with_conf), 'of_which_still_have_usable_records': int((k._merge == 'both').sum()),
                       'cells_lost_entirely': int((k._merge == 'left_only').sum()), 'usable_cells': len(usable_cells),
                       'lost_pct_of_usable': round(100 * (k._merge == 'left_only').sum() / max(len(usable_cells), 1), 2)}
    return out


PHASE8_SEED = 20261022


def learned_model_plan():
    """At most one exploratory learned model. Reusable settings are read from the frozen Phase 8 code, not copied by hand."""
    from Code.modelling import models as m8
    params = {k: v for k, v in m8.LEARNERS['hgb_conservative']().get_params().items()
              if k in ('max_iter', 'learning_rate', 'max_leaf_nodes', 'min_samples_leaf', 'l2_regularization', 'early_stopping', 'random_state')}
    return {'model': 'hgb_conservative (exploratory, at most one; never replaces the baselines as the primary result)',
            'reusable_unchanged': {'estimator_settings (Code/modelling/models.py LEARNERS)': params,
                                   'one model per crop x horizon': 'as Phase 8 run_models',
                                   'target': 'log(y_target / y_origin) (Phase 8 log_ratio), prediction = y_origin * exp(pred)',
                                   'scaling': 'price features divided by y_origin; y_origin itself as log (Phase 8 design_matrix)',
                                   'training population': 'D-41 at the refit date (clarification 2); targets ending <= refit date',
                                   'refits': 'quarterly, first Sunday of the quarter, preprocessing fitted per refit'},
            'requires_approval': {'feature_set': 'Phase 8 features are daily-level (prev obs, 7/30/90-day rolling stats) and do not exist '
                                                 'in the weekly candidate table. Proposed price-only set: lag1/lag2/lag4/lag52 ratios to '
                                                 'y_origin, weeks_since_prev_obs, n_weeks_history, month sin/cos of the target week. '
                                                 'This is a new feature set, not D-42 settings',
                                  'selection_rule': 'Phase 8 required beating persistence on MAE in both validation years (+ bootstrap); '
                                                    'proposed analogue: both validation quarters (2026 Q1 and Q2)',
                                  'scope': 'h = 1 only, FAQ-only only (proposed)'},
            'never': ['reuse or modify the frozen D-42/D-45 artefacts', 'tune on the test window', 'tune anything after seeing test results']}


PROTOCOL = {
    'experiment': 'exp-candidate-v1', 'dataset': 'candidate-prices-v1.1 (dataset_v1_1, build_manifest.json)', 'decision': 'D-50',
    'status': 'specified; frozen for approval; NOT executed',
    'designs': {'primary': 'faq_only', 'sensitivity': ['faq_local', 'pooled']},
    'horizons': {'primary': 1, 'secondary': [2, 4]},
    'population': 'eligible_d41 at the origin for evaluation; at the refit date for training',
    'split_by_target_sunday': PROPOSED_SPLIT, 'refits': REFITS,
    'baselines': {'persistence': 'y_origin (origin-week median) for every horizon (primary baseline)',
                  'seasonal_naive': 'series weekly median 52 weeks before the TARGET week (weekly table at W + h - 52), scored where it '
                                    'exists, coverage reported (Phase 8 definition; not lag52, which is relative to the origin)',
                  'calendar_climatology': 'median training target of the target-week month, crop level, refitted with each refit'},
    'metrics': {'primary': 'MAE (Rs/quintal)', 'also': ['RMSE (Rs/quintal)', 'MAPE % (targets > 0 after R04)',
                                                        'skill = 1 - MAE_model / MAE_persistence on identical rows'],
                'reporting': 'crop x horizon x period; each validation quarter separately and combined'},
    'uncertainty': {'paired_bootstrap': f'market (canonical_id) clusters, 10,000 replicates, seed {PHASE8_SEED} (Phase 8 §K)',
                    'robustness': ['state-cluster bootstrap', 'leave-one-state-out'], 'inconclusive_rule': 'difference inside the 95% interval'},
    'leakage_controls': ['period by target-week Sunday (Phase 8 B.7)', 'training targets end <= refit date', 'features dated <= origin',
                         'no input before 2024-02-03; 2023 holdout never read (D-50)', 'R09 thresholds fixed; R09u disabled',
                         'test used once after a freeze manifest + run-once guard'],
    'comparison_with_phase8': 'skill vs persistence only, side by side with Phase 8 validation (2019, 2020) and test (2021-2022) skills '
                              'as context; absolute MAE/MAPE never compared across datasets',
    'learned_model': 'see learned_model_plan (requires approval)',
}


def r09u_review_pack(rec, seed=PHASE8_SEED, n_random=30, per_market=5):
    """Read-only review pack: every R09u-flagged record with provenance and evidence, plus a seeded sample to review."""
    f = rec[rec.unit_scale_suspected].copy()
    u = rec[rec.usable_for_target]
    # evidence: the same market-crop's median usable modal over the surrounding 14 days (excluding the record's own day)
    mk = u.groupby(['Commodity', 'canonical_id', 'reported_date']).modal_price_rs_per_quintal.median().rename('m').reset_index()
    rows = []
    for r in f.itertuples():
        x = mk[(mk.Commodity == r.Commodity) & (mk.canonical_id == r.canonical_id) & (mk.reported_date != r.reported_date)
               & ((mk.reported_date - r.reported_date).abs() <= pd.Timedelta(days=7))]
        rows.append(x.m.median() if len(x) else np.nan)
    f['same_market_median_pm7d'] = rows
    f['modal_x100_over_market_median'] = 100 * f.modal_price_rs_per_quintal / f.same_market_median_pm7d
    f['raw_file'] = 'Dataset_Candidates/datagov_prices/raw/' + f.Commodity + '/' + f.reported_date.dt.strftime('%Y-%m-%d') + '_f1.json'
    cols = ['record_ref', 'raw_file', 'content_sha256', 'Commodity', 'State', 'District', 'Market', 'Variety', 'Grade', 'Arrival_Date',
            'Min_Price', 'Max_Price', 'Modal_Price', 'price_extreme_level', 'usable_for_target', 'same_market_median_pm7d',
            'modal_x100_over_market_median', 'source_stage']
    f = f[cols].sort_values(['Commodity', 'State', 'Market', 'Arrival_Date', 'record_ref']).reset_index(drop=True)
    rng = np.random.RandomState(seed)
    s1 = f[f.source_stage == 'S1']
    top = f.groupby(['Commodity', 'Market']).size().sort_values(ascending=False).head(10).index
    by_mkt = pd.concat([g.iloc[sorted(rng.permutation(len(g))[:per_market])] for k, g in f.groupby(['Commodity', 'Market']) if k in set(top)])
    rest = f.drop(s1.index.union(by_mkt.index))
    rand = rest.iloc[sorted(rng.permutation(len(rest))[:n_random])]
    sample = pd.concat([s1.assign(sample_reason='all S1'), by_mkt.assign(sample_reason='top-10 market'),
                        rand.assign(sample_reason='random')]).drop_duplicates('record_ref')
    for c in ['reviewer_label', 'reviewer', 'review_date', 'notes']:
        sample[c] = ''  # likely_rs_per_kg / genuine / unclear, filled by an independent person only
    return f, sample.reset_index(drop=True)


CHECKLIST = [
    ('v1.1 validation', 'see validation_status in audit_and_design.json'),
    ('split and refit schedule', 'proposed in PROTOCOL; pending approval'),
    ('baselines and metrics', 'proposed in PROTOCOL; pending approval'),
    ('learned model scope', 'plan prepared (learned_model_plan); feature set + selection rule pending approval'),
    ('R09u independent review', 'review pack prepared; 0 reviewed; R09u stays disabled'),
    ('Wheat median-of-versions sensitivity', 'deferred (not activated)'),
    ('test freeze + one-time test run', 'approver: project owner (to be named); not authorised'),
]


def main(argv=None):
    import argparse
    ap = argparse.ArgumentParser(); ap.add_argument('--dataset', default='dataset_v1_1')
    a = ap.parse_args(argv)
    global SRC
    SRC = OUT / a.dataset
    root = Path.cwd(); dest = root / OUT / f'experiment_design_{a.dataset.replace("dataset_", "")}'; dest.mkdir(parents=True, exist_ok=True)
    check_split()
    res, rec = audit(root)
    cov = []
    for design in cd.GRADE_DESIGNS:
        mt = pd.read_parquet(root / SRC / f'model_table_{design}.parquet')
        cov.append(coverage(mt, rec).assign(design=design))
    cov = pd.concat(cov, ignore_index=True); cov.to_csv(dest / 'coverage_by_period.csv', index=False)
    sens = {'r09u': sensitivity_r09u(rec), 'wheat_conflicts': sensitivity_wheat_conflicts(rec)}
    out = {'audit': res, 'proposed_split': PROPOSED_SPLIT, 'refits': REFITS, 'sensitivity': sens}
    if a.dataset != 'dataset_v1':  # protocol freeze, review pack and checklist belong to the current version only
        protocol = {**PROTOCOL, 'learned_model': learned_model_plan()}
        blob = json.dumps(protocol, indent=1, sort_keys=True, default=str)
        (dest / 'exp_candidate_v1_protocol.json').write_text(blob)
        out['protocol_sha256'] = hashlib.sha256(blob.encode()).hexdigest()
        pack, sample = r09u_review_pack(rec)
        rp = root / OUT / 'review_packs' / 'r09u_v1'; rp.mkdir(parents=True, exist_ok=True)
        pack.to_csv(rp / 'r09u_flagged_records.csv', index=False); sample.to_csv(rp / 'r09u_review_sample.csv', index=False)
        out['r09u_review_pack'] = {'flagged': len(pack), 'sample': len(sample), 'sample_reasons': sample.sample_reason.value_counts().to_dict(),
                                   'seed': PHASE8_SEED, 'reviewed': 0}
        pd.DataFrame(CHECKLIST, columns=['item', 'status']).to_csv(dest / 'approval_checklist.csv', index=False)
    (dest / 'audit_and_design.json').write_text(json.dumps(out, indent=1, default=str))
    print(json.dumps(out, indent=1, default=str))
    print(cov[cov.design == 'faq_only'].to_string(index=False))
    return 0


if __name__ == '__main__':
    sys.exit(main())
