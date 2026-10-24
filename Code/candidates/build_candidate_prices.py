"""Build `candidate-prices-v1` (decision D-50; contract decisions_v1/candidate_prices_v1_contract.json). Price-only and
separate from production: nothing under Dataset/ or the Phase 4-10 outputs is written.

Stages: raw (manifest-pass first fetches, S1-S3) -> anomaly policy (R03/R04/R07/R08) -> R09 per crop (R09u computed for
evidence, never excluding) -> approved identities (440 pairs) -> exact duplicates -> grade subsets (faq_only primary,
faq_local, pooled) -> weekly medians (Phase 8 Monday-Sunday weeks; complete weeks only) -> price-only model tables.

Every weekly cell keeps n_records and `cell_refs_sha` (SHA-256 of its sorted contributing record_refs); the records table
holds each record_ref with its canonical_id, week_start and flags, so any weekly value traces back to its source records.

Usage (repo root): python -m Code.candidates.build_candidate_prices --version v1.1 [--dest <folder>]
  (`--version v1` only rebuilds the frozen reference into a --dest folder, for byte comparison)
Outputs: Processed_Data/candidates/datagov_prices/dataset_v1/ (v1) and dataset_v1_1/ (v1.1); parquet git-ignored."""
import hashlib, json, sys
from pathlib import Path

import numpy as np
import pandas as pd

from Code.candidates import candidate_decisions as cd, identity_review as ir, price_policy as pp
from Code.candidates.datagov_extract import CROPS, OUT, STAGES
from Code.candidates.market_mapping import CUTOVER_START, GO_LIVE
from Code.modelling.dataset import week_start

DEST = OUT / 'dataset_v1'
VERSION = 'candidate-prices-v1'
# v1 is the frozen reproducibility reference: every v1.1 change is off for it, so `--version v1` rebuilds it byte-identically.
VERSIONS = {
    'v1': {'version': 'candidate-prices-v1', 'dest': 'dataset_v1', 'd41_full_count': False, 'dedup_type_variants': False, 'changes': []},
    'v1.1': {'version': 'candidate-prices-v1.1', 'dest': 'dataset_v1_1', 'd41_full_count': True, 'dedup_type_variants': True,
             'changes': ['A1: n_usable_dates_to_origin counts every usable date <= origin (D-41), including the partial first week '
                         '2024-02-03/04 that v1 skipped; weekly cells still use complete weeks only',
                         'A2: records identical in all 11 source fields as text (string- vs number-typed JSON copies from the feed) are '
                         'type_variant_duplicate: the string-typed copy is kept, the other excluded, before R03; they were mislabelled '
                         'key_conflict in v1']},
}
FIRST_WEEK, LAST_WEEK = '2024-02-05', '2026-10-12'   # complete Mon-Sun weeks inside 2024-02-03 .. 2026-10-20
HORIZONS = (1, 2, 4)
LAGS = (1, 2, 4, 52)
D41_MIN_DATES = 365


def identity_status(d, decisions):
    """approved_mapping | separate_<decision> (any non-approved candidate pair touching the identity) | own."""
    ok = decisions[decisions.decision == 'approved_candidate_experiment']
    approved = set(ok.old_id) | set(ok.new_id)
    other = decisions[decisions.decision != 'approved_candidate_experiment']
    sep = {}
    for col in ('old_id', 'new_id'):
        for i, dec in zip(other[col], other.decision):
            sep.setdefault(i, dec)
    return d.source_id.map(lambda s: 'approved_mapping' if s in approved else sep.get(s, 'own'))


def grade_membership(d):
    for name in cd.GRADE_DESIGNS:
        d[f'in_{name}'] = d.index.isin(cd.grade_subset(d, name).index)
    return d


def weekly(d, design):
    """Weekly median per (crop, canonical market, variety, week) over usable records in complete weeks."""
    u = d[d.usable_for_target & d[f'in_{design}'] & d.in_complete_week]
    key = ['Commodity', 'canonical_id', 'Variety', 'week_start']
    g = u.groupby(key, observed=True, sort=True)
    w = g.agg(target_median=('modal_price_rs_per_quintal', 'median'), n_records=('record_ref', 'size'),
              n_days=('reported_date', 'nunique'), first_date=('reported_date', 'min'), last_date=('reported_date', 'max'),
              grades=('Grade', lambda s: ','.join(sorted(set(s)))),
              cell_refs_sha=('record_ref', lambda s: hashlib.sha256('\n'.join(sorted(s)).encode()).hexdigest()[:24])).reset_index()
    w.insert(0, 'design', design)
    return w


def model_table(w, pre_dates=None):
    """Long table: one row per (series, origin week W, horizon h) with a target at W+h. Features use weeks <= W only.
    pre_dates (v1.1): usable dates per series before FIRST_WEEK, added so the D-41 count covers every date <= origin."""
    s = ['Commodity', 'canonical_id', 'Variety']
    w = w.sort_values(s + ['week_start']).reset_index(drop=True)
    base = w[['design'] + s + ['week_start', 'target_median', 'n_days']].rename(columns={'target_median': 'y_origin'})
    base['n_weeks_history'] = base.groupby(s, observed=True).cumcount() + 1
    base['n_usable_dates_to_origin'] = base.groupby(s, observed=True).n_days.cumsum()
    if pre_dates is not None:
        base['n_usable_dates_to_origin'] += base.set_index(s).index.map(pre_dates).fillna(0).astype(int).to_numpy()
    base['eligible_d41'] = base.n_usable_dates_to_origin >= D41_MIN_DATES
    prev = base.groupby(s, observed=True).week_start.shift(1)
    base['weeks_since_prev_obs'] = ((base.week_start - prev).dt.days // 7).astype('Int64')
    vals = w[s + ['week_start', 'target_median']]
    for k in LAGS:
        lag = vals.assign(week_start=vals.week_start + pd.Timedelta(weeks=k)).rename(columns={'target_median': f'lag{k}'})
        base = base.merge(lag, on=s + ['week_start'], how='left')
    out = []
    for h in HORIZONS:
        t = vals.assign(week_start=vals.week_start - pd.Timedelta(weeks=h)).rename(columns={'target_median': 'y_target'})
        m = base.merge(t, on=s + ['week_start'], how='inner').assign(horizon_weeks=h)
        m['target_week_start'] = m.week_start + pd.Timedelta(weeks=h)
        out.append(m)
    mt = pd.concat(out, ignore_index=True).rename(columns={'week_start': 'origin_week_start'})
    mt['origin_date'] = mt.origin_week_start + pd.Timedelta(days=6)
    return mt.drop(columns='n_days').sort_values(s + ['horizon_weeks', 'origin_week_start']).reset_index(drop=True)


def check_leakage(mt, records):
    """Hard invariants: no input before the D-50 start, targets strictly after origin, features never after origin."""
    cd.assert_no_holdout_inputs(records)
    assert (mt.target_week_start == mt.origin_week_start + pd.to_timedelta(mt.horizon_weeks * 7, unit='D')).all()
    assert (mt.target_week_start > mt.origin_week_start).all()
    assert mt.origin_week_start.min() >= pd.Timestamp(FIRST_WEEK) and mt.target_week_start.max() <= pd.Timestamp(LAST_WEEK)
    assert not {'arrivals_tonnes', 'rain_sum', 'temperature_2m_mean'} & set(mt.columns)  # price-only


def missing_weeks(w):
    all_weeks = pd.date_range(FIRST_WEEK, LAST_WEEK, freq='7D')
    s = ['Commodity', 'canonical_id', 'Variety']
    g = w.groupby(s, observed=True).week_start
    span = ((g.max() - g.min()).dt.days // 7 + 1)
    obs = g.size()
    gaps = w.sort_values(s + ['week_start']).groupby(s, observed=True).week_start.diff().dt.days.div(7).sub(1)
    big_gap = gaps.ge(4).groupby([w.sort_values(s + ['week_start'])[c] for c in s], observed=True).any()
    return {'weeks_in_window': len(all_weeks), 'weeks_with_no_cell': int(len(set(all_weeks) - set(w.week_start))),
            'series': int(len(obs)), 'median_observed_weeks': float(obs.median()),
            'median_missing_share_within_span': round(float((1 - obs / span).median()), 3),
            'p90_missing_share_within_span': round(float((1 - obs / span).quantile(.9)), 3),
            'series_with_gap_ge_4_weeks': int(big_gap.sum()), 'series_lt_8_weeks': int((obs < 8).sum())}


def continuity(w):
    s = ['Commodity', 'canonical_id', 'Variety']
    pre = set(map(tuple, w[w.week_start < pd.Timestamp(CUTOVER_START) - pd.Timedelta(days=6)][s].drop_duplicates().values))
    post = set(map(tuple, w[w.week_start >= pd.Timestamp(GO_LIVE)][s].drop_duplicates().values))
    return {'pre_relaunch_series': len(pre), 'post_relaunch_series': len(post), 'continuing': len(pre & post),
            'continuity_pct': round(100 * len(pre & post) / max(len(pre), 1), 1), 'ended_at_relaunch': len(pre - post),
            'new_after_relaunch': len(post - pre)}


def file_sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def main(argv=None):
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument('--version', required=True, choices=sorted(VERSIONS))
    ap.add_argument('--dest', help='override output folder (e.g. a scratch folder to re-verify v1 without touching it)')
    a = ap.parse_args(argv)
    cfg = VERSIONS[a.version]
    root = Path.cwd(); dest = Path(a.dest) if a.dest else root / OUT / cfg['dest']
    if a.version == 'v1' and not a.dest and (dest / 'build_manifest.json').exists():
        raise SystemExit('v1 is the frozen reference: rebuild it only into a --dest folder')
    dest.mkdir(parents=True, exist_ok=True)
    assert cd.R09U_APPROVED is False, 'D-50: R09u must stay disabled'
    counts = []
    raw, n_days = pp.load_accepted(root, sorted(STAGES))                     # 1. raw
    raw['reported_date'] = pd.to_datetime(raw.Arrival_Date, format='%d/%m/%Y')
    cd.assert_no_holdout_inputs(raw)
    counts += [{'stage': '1_raw', 'crop': c, 'records': int((raw.Commodity == c).sum())} for c in CROPS]
    d = pp.apply_policy(raw.drop(columns='reported_date'), dedup_type_variants=cfg['dedup_type_variants'])   # 2. anomaly policy
    counts += [{'stage': '2_anomaly_policy', 'crop': c, 'usable': int((d.usable_modal_price & (d.Commodity == c)).sum())} for c in CROPS]
    d = pd.concat([cd.scale_flags(d[d.Commodity == c]) for c in CROPS])      # 3. R09 (R09u evidence only)
    counts += [{'stage': '3_r09', 'crop': c, 'usable': int((d.usable_for_target & (d.Commodity == c)).sum()),
                'r09_scale_error': int(((d.Commodity == c) & (d.price_extreme_level == 'scale_error_suspected')).sum()),
                'r09_review_kept': int(((d.Commodity == c) & (d.price_extreme_level == 'review')).sum()),
                'r09u_flag_not_applied': int(((d.Commodity == c) & d.unit_scale_suspected).sum())} for c in CROPS]
    decisions = pd.read_csv(root / cd.DEST / 'mapping_decisions.csv')
    approved = cd.approved_pairs(decisions)                                  # 4-5. identities and duplicates
    assert len(approved) == 440
    d, dlog = ir.dedupe(d.reset_index(drop=True), approved)
    d['identity_status'] = identity_status(d, decisions)
    counts += [{'stage': '4_5_identity_dedup', 'crop': c, 'usable': int((d.usable_for_target & (d.Commodity == c)).sum()),
                'exact_duplicate_removed': int(((d.Commodity == c) & (d.dedup_status == 'exact_duplicate_removed')).sum()),
                'identity_conflict': int(((d.Commodity == c) & (d.dedup_status == 'identity_conflict')).sum())} for c in CROPS]
    d['week_start'] = week_start(d.reported_date)                            # 6-7. grades and weeks
    d['in_complete_week'] = d.week_start.between(pd.Timestamp(FIRST_WEEK), pd.Timestamp(LAST_WEEK))
    d = grade_membership(d)
    for g in cd.GRADE_DESIGNS:
        counts += [{'stage': f'6_grade_{g}', 'crop': c,
                    'usable': int((d.usable_for_target & d[f'in_{g}'] & d.in_complete_week & (d.Commodity == c)).sum())} for c in CROPS]

    rec_cols = ['record_ref', 'source_stage', 'content_sha256', 'retrieved_utc', 'State', 'District', 'Market', 'Commodity', 'Variety', 'Grade',
                'Arrival_Date', 'Min_Price', 'Max_Price', 'Modal_Price', 'reported_date', 'week_start', 'in_complete_week',
                'modal_price_rs_per_quintal', 'price_anomaly', 'price_extreme_level', 'unit_scale_suspected', 'source_id', 'canonical_id',
                'identity_status', 'dedup_status', 'dedup_group', 'usable_for_target'] + [f'in_{g}' for g in cd.GRADE_DESIGNS]
    order = ['Commodity', 'reported_date', 'source_id', 'Variety', 'Grade', 'record_ref']
    if cfg['dedup_type_variants']:  # v1.1 keeps raw position and value type, so type-variant copies stay traceable
        rec_cols += ['raw_index', 'raw_value_types']; order += ['raw_value_types', 'raw_index']
    d = d[rec_cols].sort_values(order, kind='stable').reset_index(drop=True)
    outputs = {}
    for c in CROPS:
        p = dest / f'records_{c.lower()}.parquet'; d[d.Commodity == c].to_parquet(p, index=False); outputs[p.name] = len(d[d.Commodity == c])
    dlog.to_csv(dest / 'dedup_log.csv', index=False)

    rep = {'coverage': [], 'missing_weeks': {}, 'continuity': {}, 'model_tables': {}}
    for g in cd.GRADE_DESIGNS:
        w = weekly(d, g)
        pre = None
        if cfg['d41_full_count']:
            early = d[d.usable_for_target & d[f'in_{g}'] & (d.reported_date < pd.Timestamp(FIRST_WEEK))]
            pre = early.groupby(['Commodity', 'canonical_id', 'Variety'], observed=True).reported_date.nunique()
        mt = model_table(w, pre)
        check_leakage(mt, d)
        p = dest / f'weekly_{g}.parquet'; w.to_parquet(p, index=False); outputs[p.name] = len(w)
        p = dest / f'model_table_{g}.parquet'; mt.to_parquet(p, index=False); outputs[p.name] = len(mt)
        wy = w.assign(year=w.week_start.dt.year)
        for (c, y), x in wy.groupby(['Commodity', 'year']):
            rep['coverage'].append({'design': g, 'crop': c, 'year': y, 'weekly_cells': len(x), 'series': x[['canonical_id', 'Variety']].drop_duplicates().shape[0],
                                    'markets': x.canonical_id.nunique(), 'records_in_cells': int(x.n_records.sum())})
        for c in CROPS:
            x = w[w.Commodity == c]
            rep['missing_weeks'][f'{g}|{c}'] = missing_weeks(x)
            rep['continuity'][f'{g}|{c}'] = continuity(x)
            m = mt[mt.Commodity == c]
            rep['model_tables'][f'{g}|{c}'] = {h: {'rows': int((m.horizon_weeks == h).sum()), 'eligible_d41': int(((m.horizon_weeks == h) & m.eligible_d41).sum()),
                                                   'first_eligible_origin': str(m[(m.horizon_weeks == h) & m.eligible_d41].origin_week_start.min().date())
                                                   if ((m.horizon_weeks == h) & m.eligible_d41).any() else None} for h in HORIZONS}
    pd.DataFrame(rep['coverage']).to_csv(dest / 'coverage_by_design_crop_year.csv', index=False)
    pd.DataFrame(counts).to_csv(dest / 'stage_counts.csv', index=False)

    ids = d.drop_duplicates('source_id')
    rep['identities'] = ids.identity_status.value_counts().to_dict()
    rep['identity_records'] = d.groupby('identity_status').size().to_dict()
    rep['identity_usable_records'] = d[d.usable_for_target].groupby('identity_status').size().to_dict()
    flat = lambda s: {f'{a}|{b}': int(n) for (a, b), n in s.items()}
    rep['exclusions_by_reason'] = {'price_anomaly': flat(d[d.price_anomaly != 'none'].groupby(['Commodity', 'price_anomaly'], observed=True).size()),
                                   'r09_scale_error': d[d.price_extreme_level == 'scale_error_suspected'].Commodity.value_counts().to_dict(),
                                   'dedup': flat(d[d.dedup_status != 'unique'].groupby(['Commodity', 'dedup_status']).size()),
                                   'partial_week_records': d[~d.in_complete_week].Commodity.value_counts().to_dict()}
    rep['r09u'] = {'approved': cd.R09U_APPROVED, 'flagged_not_excluded': d[d.unit_scale_suspected].Commodity.value_counts().to_dict()}
    rep['date_range'] = {'records': [str(d.reported_date.min().date()), str(d.reported_date.max().date())],
                         'weeks': [FIRST_WEEK, LAST_WEEK]}
    if cfg['changes']:  # v1.1+: the contract is v1's plus the recorded changes, written next to the outputs
        contract = {**cd.CONTRACT, 'version': cfg['version'], 'changes_from_v1': cfg['changes'],
                    'status': 'built under D-50; fixes A1/A2 from the v1 audit (Data_Source_Review.md §7.1.1)'}
        (dest / 'contract.json').write_text(json.dumps(contract, indent=1))
    manifest = {'version': cfg['version'], 'decision': 'D-50', 'crop_days': n_days, 'stages': sorted(STAGES),
                'inputs': {'crop_day_manifest': file_sha(root / OUT / 'crop_day_manifest.csv'),
                           'mapping_decisions': file_sha(root / cd.DEST / 'mapping_decisions.csv'),
                           'contract_sha256': hashlib.sha256(json.dumps(cd.CONTRACT, sort_keys=True).encode()).hexdigest()},
                'outputs': {k: {'rows': v, 'sha256': file_sha(dest / k)} for k, v in sorted(outputs.items())},
                'r09u_approved': cd.R09U_APPROVED, 'candidate_start': cd.CANDIDATE_START,
                **({'changes_from_v1': cfg['changes']} if cfg['changes'] else {})}
    (dest / 'build_manifest.json').write_text(json.dumps(manifest, indent=1, default=str))
    (dest / 'build_report.json').write_text(json.dumps(rep, indent=1, default=str))
    print(json.dumps({'stage_counts': counts, 'identities': rep['identities'], 'r09u': rep['r09u'],
                      'continuity': rep['continuity'], 'missing_weeks': rep['missing_weeks'],
                      'model_tables': rep['model_tables']}, indent=1, default=str))
    return 0


if __name__ == '__main__':
    sys.exit(main())
