"""Recorded decisions and the build contract for `candidate-prices-v1` (Data_Source_Review.md §6.10). No weekly table is
built here; the build stays blocked until the open decisions (medium review, grade design, U3) are recorded.

- mapping_decisions: the 2026-10-24 decisions per candidate pair (440 rule-accepted pairs approved for the candidate
  experiment only; all other pairs stay separate identities).
- review_worksheet: the human worksheet for the reproducible 160-pair medium sample; decision fields are left blank.
- scale_flags: Phase 5 R09 unchanged (trailing 30-day crop-national median; review >= 10x, scale error >= 50x) plus
  R09u (unit scale): modal <= ref/10 AND 100 x modal inside [ref/3, 3 ref] -> `unit_scale_suspected`. The 1/10 is
  R09's own review threshold; [1/3, 3] holds 95.6-100% of ordinary S1 prices (§6.10). Fixed on S1, never tuned later.
- grade designs: FAQ-only, FAQ+Local and pooled, each a separate experiment; grade stays a column.
- assert_no_holdout_inputs: the build reads no row dated before CANDIDATE_START until U3 is decided.

Usage (repo root): python -m Code.candidates.candidate_decisions
Outputs: Processed_Data/candidates/datagov_prices/decisions_v1/."""
import json, sys
from pathlib import Path

import numpy as np
import pandas as pd

from Code.candidates.datagov_extract import CROPS, OUT
from Code.candidates.market_mapping import CUTOVER_START, GO_LIVE
from Code.cleaning.pipeline import PRICE_REVIEW_RATIO, PRICE_SCALE_RATIO, trailing_price_reference

DEST = OUT / 'decisions_v1'
MAP_VERSION = 'candidate-market-map-v1'
DECIDED = '2026-10-24 (project owner: rule-accepted pairs approved for the candidate experiment only)'
CANDIDATE_START = '2024-02-03'   # D-50: no 2023 / 2024-01 (holdout-period) rows may enter the candidate build
# D-50: R09u is NOT approved; it is computed for evidence only and never excludes a record.
R09U_APPROVED = False
UNIT_BAND = (1 / 3, 3.0)
PRICES = ['min_price_rs_per_quintal', 'max_price_rs_per_quintal', 'modal_price_rs_per_quintal']
GRADE_DESIGNS = {'faq_only': ['FAQ'], 'faq_local': ['FAQ', 'Local'], 'pooled': None}
DECISION_CHOICES = ['ACCEPT', 'REJECT', 'UNSURE']
REASON_CODES = ['same_market_renamed', 'different_market', 'price_evidence_conflicts', 'district_question', 'insufficient_evidence']


# ---------------------------------------------------------------- mapping decisions
def mapping_decisions(scored, hv):
    """One row per candidate pair with the recorded decision. Only accepted_rule_v1 pairs are approved, and only for
    the candidate experiment; everything else is a separate identity."""
    s = scored.copy()
    s['old_id'] = s.State + '|' + s.District_old + '|' + s.Market_old
    s['new_id'] = s.State + '|' + s.District_new + '|' + s.Market_new
    s = s.merge(hv[['old_id', 'new_id', 'validation_status', 'hard_fail', 'unmet', 'same_day_records', 'equal_Modal_Price',
                    'agmarknet2_market_id', 'legacy_market_code']], on=['old_id', 'new_id'], how='left', validate='1:1')
    dec = np.select([s.validation_status == 'accepted_rule_v1', s.validation_status == 'rejected',
                     s.validation_status == 'unresolved', s.confidence == 'medium'],
                    ['approved_candidate_experiment', 'separate_rejected', 'separate_unresolved', 'separate_pending_review'],
                    'separate_not_mapped')
    s['decision'] = dec
    s['decision_scope'] = np.where(dec == 'approved_candidate_experiment', 'candidate-prices-v1 only; not production', '')
    s['decision_basis'] = np.where(dec == 'approved_candidate_experiment', DECIDED, 'kept separate: identity not established')
    s['mapping_version'] = MAP_VERSION
    return s


def approved_pairs(decisions):
    a = decisions[decisions.decision == 'approved_candidate_experiment']
    assert a.new_id.is_unique and a.old_id.is_unique, 'approved mapping must be one-to-one'
    return a[['old_id', 'new_id']]


# ---------------------------------------------------------------- human review worksheet
def review_worksheet(sample):
    cols = ['State', 'District_old', 'Market_old', 'District_new', 'Market_new', 'first_seen_old', 'last_seen_old',
            'first_seen_new', 'last_seen_new', 'n_records_old', 'n_records_new', 'crops_new', 'co_reported', 'identical_share',
            'evidence_type', 'overlap_bucket', 'stratum', 'varieties_old', 'varieties_new', 'grades_old', 'grades_new', 'price_evidence']
    w = sample[cols].copy()
    w.insert(0, 'review_id', [f'MR{i:03d}' for i in range(1, len(w) + 1)])
    w['decision'] = ''          # ACCEPT / REJECT / UNSURE, filled by a person only
    w['reason_code'] = ''       # one of REASON_CODES
    w['reviewer'] = ''; w['review_date'] = ''; w['notes'] = ''
    return w


def same_sample(saved, recomputed):
    k = ['State', 'District_new', 'Market_new', 'District_old', 'Market_old']
    return saved[k].reset_index(drop=True).equals(recomputed[k].reset_index(drop=True))


# ---------------------------------------------------------------- scale rule
def scale_flags(df, r09u_active=None):
    """R09 exactly as Phase 5, plus R09u. Adds price_ref, price_ratio_to_ref, price_extreme_level and unit_scale_suspected;
    `usable_for_target` excludes scale_error_suspected, and unit_scale_suspected only when R09u is approved
    (r09u_active defaults to R09U_APPROVED). Values are never changed."""
    r09u_active = R09U_APPROVED if r09u_active is None else r09u_active
    d = df.copy()
    for c in PRICES:
        d[c] = d[c].astype('float64')
    d['price_ref'] = trailing_price_reference(d)
    d['price_ratio_to_ref'] = pd.concat([np.maximum(d[c] / d.price_ref, d.price_ref / d[c]) for c in PRICES], axis=1).max(axis=1, skipna=True)
    d['price_extreme_level'] = np.select([d.price_ref.isna() | (d.price_ref <= 0), d.price_ratio_to_ref >= PRICE_SCALE_RATIO,
                                          d.price_ratio_to_ref >= PRICE_REVIEW_RATIO], ['no_reference', 'scale_error_suspected', 'review'], 'none')
    md = d['modal_price_rs_per_quintal']
    d['unit_scale_suspected'] = ((md <= d.price_ref / PRICE_REVIEW_RATIO) & (100 * md / d.price_ref).between(*UNIT_BAND)).fillna(False).astype(bool)
    base = d['usable_for_target'] if 'usable_for_target' in d else d['usable_modal_price']
    d['usable_for_target'] = base & (d.price_extreme_level != 'scale_error_suspected') & ~(d.unit_scale_suspected & r09u_active)
    return d


# ---------------------------------------------------------------- grade experiments
def grade_subset(d, design):
    g = GRADE_DESIGNS[design]
    return d if g is None else d[d.Grade.isin(g)]


def grade_experiment_stats(d):
    """Per design x crop: weekly cells by year, series, markets, and continuity across the relaunch
    (series with usable weeks both before CUTOVER_START and on/after GO_LIVE)."""
    rows = []
    for design in GRADE_DESIGNS:
        u = grade_subset(d[d.usable_for_target], design).assign(week=lambda x: x.reported_date.dt.to_period('W-SUN'),
                                                                 year=lambda x: x.reported_date.dt.year)
        for c in CROPS:
            x = u[u.Commodity == c]
            key = ['canonical_id', 'Variety']
            pre = set(map(tuple, x[x.reported_date < CUTOVER_START][key].drop_duplicates().values))
            post = set(map(tuple, x[x.reported_date >= GO_LIVE][key].drop_duplicates().values))
            cells = x[key + ['week', 'year']].drop_duplicates()
            rows.append({'design': design, 'crop': c, 'series': len(x[key].drop_duplicates()),
                         'markets': x.canonical_id.nunique(), 'weekly_cells': len(cells),
                         **{f'cells_{y}': int((cells.year == y).sum()) for y in (2024, 2025, 2026)},
                         'pre_series': len(pre), 'continuing_series': len(pre & post),
                         'continuity_pct': round(100 * len(pre & post) / max(len(pre), 1), 1)})
    return pd.DataFrame(rows)


def faq_local_evidence(d):
    """Evidence (not a rule): grade transitions at the relaunch and same-day FAQ-vs-Local agreement."""
    u = d[d.usable_for_target].copy()
    u['era'] = np.where(u.reported_date >= GO_LIVE, 'post', np.where(u.reported_date < CUTOVER_START, 'pre', 'cut'))
    dom = u[u.era != 'cut'].groupby(['Commodity', 'canonical_id', 'era']).Grade.agg(lambda s: s.value_counts().idxmax()).unstack()
    trans = dom.dropna().groupby(['pre', 'post']).size().sort_values(ascending=False)
    k = ['Commodity', 'canonical_id', 'Variety', 'reported_date']
    f = u[u.Grade == 'FAQ'].groupby(k).modal_price_rs_per_quintal.median()
    l = u[u.Grade == 'Local'].groupby(k).modal_price_rs_per_quintal.median()
    j = pd.concat([f.rename('faq'), l.rename('local')], axis=1).dropna()
    return {'dominant_grade_transitions_pre_to_post': {f'{a}->{b}': int(n) for (a, b), n in trans.head(8).items()},
            'faq_local_same_day_pairs': int(len(j)), 'exactly_equal_share': round(float((j.faq == j.local).mean()), 3) if len(j) else None,
            'median_abs_rel_diff': round(float(((j.local - j.faq).abs() / j.faq).median()), 4) if len(j) else None,
            'pairs_by_state_top': j.reset_index().assign(state=lambda t: t.canonical_id.str.split('|').str[0]).state.value_counts().head(5).to_dict()}


# ---------------------------------------------------------------- U3 guard
def assert_no_holdout_inputs(df, start=CANDIDATE_START):
    first = df['reported_date'].min()
    if pd.notna(first) and first < pd.Timestamp(start):
        raise ValueError(f'input dated {first.date()} precedes {start}: 2023 / 2024-01 rows are holdout-period data (U3 undecided)')


CONTRACT = {
    'version': 'candidate-prices-v1', 'status': 'authorised for the candidate build by D-50 (2026-10-24)',
    'decision': 'D-50 (Documentation/Decision_Log.md)',
    'approvals': {'mapping_440_pairs': 'recorded D-50: 440 one-to-one pairs, candidate experiment only',
                  'medium_review': 'recorded D-50: build proceeds with 0 of 160 worksheet decisions; all 1,053 medium pairs stay separate',
                  'primary_grade_design': 'recorded D-50: faq_only primary; faq_local and pooled as sensitivity experiments',
                  'r09u_unit_scale': 'recorded D-50: NOT approved, disabled (R09U_APPROVED = False); evidence kept for a future review',
                  'u3_holdout_as_history': 'recorded D-50: no data before 2024-02-03; section P holdout not run; 2023 not ordinary history',
                  'mar_apr_2026_dual_reporting': 'recorded D-50: kept separate (identity not established)'},
    'inputs': {'raw': 'Dataset_Candidates/datagov_prices/raw/<crop>/<date>_f1.json (manifest status pass)',
               'date_range': [CANDIDATE_START, '2026-10-20'], 'history_before_start': 'never read (D-50)'},
    'market_mapping': {'version': MAP_VERSION, 'approved_pairs': 'decisions_v1/mapping_decisions.csv decision=approved_candidate_experiment',
                       'others': 'own source identity (State|District|Market)'},
    'anomaly_rules': ['R03 key_conflict', 'R04 zero->missing', 'R07 min_gt_max', 'R08 modal_outside_range',
                      f'R09 review>={PRICE_REVIEW_RATIO}x kept, scale_error>={PRICE_SCALE_RATIO}x excluded (Phase 5 unchanged)',
                      f'R09u unit_scale (NOT approved, D-50; flag computed for evidence, never excludes): modal<=ref/{PRICE_REVIEW_RATIO} '
                      f'and 100*modal in [{UNIT_BAND[0]:.3f}, {UNIT_BAND[1]}]*ref'],
    'stage_order': ['raw', 'anomaly flags (R03/R04/R07/R08)', 'R09 scale (per crop, trailing national reference)',
                    'approved identities', 'exact duplicates (combined with earlier exclusions)', 'grade subsets', 'weekly medians',
                    'price-only model tables'],
    'duplicates': 'exact min/max/modal equality under an approved identity, same crop/variety/grade/date; tie-break canonical name, '
                  'source_id, record_ref; differing values -> identity_conflict excluded; never across grades; never averaged',
    'grade_designs': GRADE_DESIGNS, 'primary_design': 'faq_only (recorded 2026-10-24); faq_local and pooled are sensitivity experiments',
    'weekly': {'key': ['Commodity', 'canonical_id', 'Variety', '(Grade if grade-aware)', 'week Mon-Sun'],
               'target': 'median modal of usable_for_target records', 'cell_fields': ['n_records', 'n_days', 'grades', 'first_date', 'last_date']},
    'coverage_reports': 'by crop x state x month: records, usable, each exclusion reason, markets, series, weekly cells, unresolved-identity share',
    'leakage_checks': ['no input before candidate start', 'features dated <= origin', 'transforms fit on training window only',
                       'thresholds fixed on S1 (<= 2024-04-30)', 'no production or holdout file read for writing'],
}


def main():
    root = Path.cwd(); dest = root / DEST; dest.mkdir(parents=True, exist_ok=True)
    from Code.candidates import identity_review as ir
    rev = root / ir.DEST
    scored = pd.read_csv(root / ir.MAP / 'candidate_pairs_scored.csv')
    hv = pd.read_csv(rev / 'high_confidence_validation.csv')
    dec = mapping_decisions(scored, hv); dec.to_csv(dest / 'mapping_decisions.csv', index=False)
    approved = approved_pairs(dec)

    saved = pd.read_csv(rev / 'medium_review_sample.csv')
    recomputed = ir.medium_sample(scored[scored.confidence == 'medium'], None)
    sample_ok = same_sample(saved, recomputed)
    review_worksheet(saved).to_csv(dest / 'medium_review_worksheet.csv', index=False)

    df = pd.concat([pd.read_parquet(root / ir.SRC / f'prices_{c.lower()}.parquet') for c in CROPS], ignore_index=True)
    assert_no_holdout_inputs(df)
    d, _ = ir.dedupe(df, approved)
    d = pd.concat([scale_flags(d[d.Commodity == c]) for c in CROPS])
    s1 = d[d.reported_date <= '2024-04-30']
    s1[s1.unit_scale_suspected][['Commodity', 'State', 'District', 'Market', 'Variety', 'Grade', 'Arrival_Date', 'Min_Price', 'Max_Price',
                                 'Modal_Price', 'price_ref', 'price_ratio_to_ref', 'price_extreme_level', 'record_ref']] \
        .sort_values(['Commodity', 'State', 'Market', 'Arrival_Date']).to_csv(dest / 'r09u_s1_evidence.csv', index=False)
    pd.DataFrame([{'item': k, 'status': v} for k, v in CONTRACT['approvals'].items()]).to_csv(dest / 'approval_checklist.csv', index=False)
    scale = {c: {'S1_review': int(((s1.Commodity == c) & (s1.price_extreme_level == 'review')).sum()),
                 'S1_scale_error': int(((s1.Commodity == c) & (s1.price_extreme_level == 'scale_error_suspected')).sum()),
                 'S1_unit_scale': int(((s1.Commodity == c) & s1.unit_scale_suspected).sum()),
                 'all_scale_error': int(((d.Commodity == c) & (d.price_extreme_level == 'scale_error_suspected')).sum()),
                 'all_unit_scale': int(((d.Commodity == c) & d.unit_scale_suspected).sum())} for c in CROPS}
    g = grade_experiment_stats(d); g.to_csv(dest / 'grade_experiments.csv', index=False)
    summary = {'decisions': dec.decision.value_counts().to_dict(), 'approved_pairs': int(len(approved)),
               'medium_sample_reproducible': bool(sample_ok), 'worksheet_rows': int(len(saved)),
               'worksheet_decisions_filled': 0, 'scale_rule': scale, 'faq_local_evidence': faq_local_evidence(d),
               'usable_for_target_by_crop': d[d.usable_for_target].Commodity.value_counts().to_dict()}
    (dest / 'decisions_summary.json').write_text(json.dumps(summary, indent=1, default=str))
    (dest / 'candidate_prices_v1_contract.json').write_text(json.dumps(CONTRACT, indent=1))
    print(json.dumps(summary, indent=1, default=str)); print(g.to_string(index=False))
    return 0


if __name__ == '__main__':
    sys.exit(main())
