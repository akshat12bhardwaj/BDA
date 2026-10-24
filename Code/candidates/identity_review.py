"""Market-identity review, cut-over de-duplication and grade assessment (Data_Source_Review.md §6.8). Nothing is merged
into production and no final weekly table is written.

1. validate_high: every high-confidence pair is checked individually (rule `identity-rule-v1`, below). A pair is
   `accepted_rule_v1` only if all hard checks pass; `rejected` if any hard check contradicts the mapping;
   otherwise `unresolved`. No pair is marked approved: acceptance is by a recorded rule, pending human sign-off.
2. medium_sample: a seeded, stratified review sample of medium pairs with the evidence a reviewer needs.
3. dedupe: only across ACCEPTED identities; exact duplicates (same canonical market, crop, variety, grade, date and
   identical min/max/modal) keep one record by a deterministic tie-break; differing values become an
   identity_conflict group (all excluded from targets). Every group is logged. Values are never averaged.
4. grade_assessment / series_key: all grades kept; FAQ-only and grade-aware designs measured.

Usage (repo root): python -m Code.candidates.identity_review
Outputs: Processed_Data/candidates/datagov_prices/identity_review_v1/."""
import hashlib, json, re, sys
from pathlib import Path

import numpy as np
import pandas as pd

from Code.candidates.datagov_extract import CROPS, OUT
from Code.candidates.market_mapping import CUTOVER_START, GO_LIVE, fold

SRC, MAP = OUT / 'analytical_v1', OUT / 'market_mapping'
DEST = OUT / 'identity_review_v1'
RULE = 'identity-rule-v1'
OLD_STOP_BY = '2025-11-20'            # old name may not report after this (cut-over end + 14 days)
MIN_FIELD_EQUAL = 0.95                # same-day min, max and modal agreement
LEVEL_RATIO = (0.5, 2.0)              # median modal, last 28 days old vs first 28 days new, same crop
SEED, SAMPLE_FRAC, SAMPLE_MIN = 20261024, 0.10, 2
SOURCE_FIELDS = ['State', 'District', 'Market', 'Commodity', 'Commodity_Code', 'Variety', 'Grade', 'Arrival_Date',
                 'Min_Price', 'Max_Price', 'Modal_Price']
EQUIV = ['Min_Price', 'Max_Price', 'Modal_Price']
STATE_ALIASES = {'Keralam': 'Kerala'}


def record_ref(df):
    """String-normalised record reference: SHA-256 of the 11 source fields as stored in the analytical table."""
    s = df[SOURCE_FIELDS].astype(str).agg('\x1f'.join, axis=1)
    return s.map(lambda x: hashlib.sha256(x.encode()).hexdigest()[:20])


def sid(state, district, market):
    return f'{state}|{district}|{market}'


# ---------------------------------------------------------------- 1. high-confidence validation
def pair_checks(p, df, official_new, official_old, targets):
    """Hard and soft checks for one pair (a row of candidate_pairs_scored). Returns a dict."""
    o = df[(df.State == p.State) & (df.District == p.District_old) & (df.Market == p.Market_old)]
    n = df[(df.State == p.State) & (df.District == p.District_new) & (df.Market == p.Market_new)]
    k = ['Commodity', 'Variety', 'Grade', 'reported_date']
    j = o[o.usable_modal_price].merge(n[n.usable_modal_price], on=k, suffixes=('_o', '_n'))
    eq = {f: round(float((pd.to_numeric(j[f + '_o']) == pd.to_numeric(j[f + '_n'])).mean()), 4) if len(j) else None for f in EQUIV}
    after_go_live = int((o.reported_date > pd.Timestamp(OLD_STOP_BY)).sum())
    ratios = {}
    for c in sorted(set(o.Commodity) & set(n.Commodity)):
        a = o[(o.Commodity == c) & o.usable_modal_price & (o.reported_date < CUTOVER_START)
              & (o.reported_date >= pd.Timestamp(CUTOVER_START) - pd.Timedelta(days=28))].modal_price_rs_per_quintal.median()
        b = n[(n.Commodity == c) & n.usable_modal_price & (n.reported_date >= GO_LIVE)
              & (n.reported_date < pd.Timestamp(GO_LIVE) + pd.Timedelta(days=28))].modal_price_rs_per_quintal.median()
        if pd.notna(a) and pd.notna(b) and a > 0:
            ratios[c] = round(float(b / a), 3)
    var_o, var_n = set(o.Variety), set(n.Variety)
    off_new = official_new.get((fold(p.State), fold(p.Market_new)))
    off_old = official_old.get((fold(p.State), fold(p.Market_old)))
    hard_fail = []
    if targets.get(sid(p.State, p.District_old, p.Market_old), 0) > 1:
        hard_fail.append('many_to_one_collision')
    if after_go_live > 0:
        hard_fail.append('old_name_active_after_cutover')
    if any(v is not None and v < MIN_FIELD_EQUAL for v in eq.values()):
        hard_fail.append('same_day_price_disagreement')
    if any(not LEVEL_RATIO[0] <= r <= LEVEL_RATIO[1] for r in ratios.values()):
        hard_fail.append('price_level_discontinuity')
    if not var_o & var_n:
        hard_fail.append('no_shared_variety')
    missing = []
    if not p.same_district:
        missing.append('district_differs')
    if len(j) < 5:
        missing.append('fewer_than_5_same_day_records')
    if off_new is None:
        missing.append('new_name_not_in_agmarknet2_market_list')
    if off_new is not None and fold(off_new['district']) != fold(p.District_new):
        missing.append('agmarknet2_district_differs_from_feed')
    status = 'rejected' if hard_fail else ('unresolved' if missing else 'accepted_rule_v1')
    return {'old_id': sid(p.State, p.District_old, p.Market_old), 'new_id': sid(p.State, p.District_new, p.Market_new),
            'same_day_records': len(j), **{f'equal_{f}': v for f, v in eq.items()},
            'old_records_after_' + OLD_STOP_BY: after_go_live, 'level_ratio_new_over_old': json.dumps(ratios),
            'shared_varieties': len(var_o & var_n), 'grades_old': ','.join(sorted(set(o.Grade))), 'grades_new': ','.join(sorted(set(n.Grade))),
            'agmarknet2_market_id': None if off_new is None else off_new['id'],
            'agmarknet2_district': None if off_new is None else off_new['district'],
            'legacy_market_code': None if off_old is None else off_old['code'],
            'legacy_district': None if off_old is None else off_old['district'],
            'hard_fail': ','.join(hard_fail), 'unmet': ','.join(missing), 'validation_status': status, 'rule': RULE}


def proposal_targets(scored):
    """How many proposed (high + medium) new names point at each old identity: >1 is a many-to-one collision."""
    prop = scored[scored.confidence.isin(['high', 'medium'])]
    return {sid(*k): int(n) for k, n in prop.groupby(['State', 'District_old', 'Market_old']).size().items()}


def validate_high(scored, df, official_new, official_old):
    targets = proposal_targets(scored)
    hi = scored[scored.confidence == 'high']
    return pd.DataFrame([pair_checks(p, df, official_new, official_old, targets) for p in hi.itertuples()])


# ---------------------------------------------------------------- 2. medium-confidence sample
def medium_strata(med, inv):
    m = med.copy()
    m['overlap_bucket'] = pd.cut(m.co_reported, [-1, 0, 2, 4], labels=['0', '1-2', '3-4']).astype(str)
    m['evidence_type'] = np.where(m.co_reported > 0, 'name+dates+same_day_prices', 'name+dates_only')
    m['crop_relevance'] = m.crops_new.where(~m.crops_new.str.contains(','), 'multi')
    big = m.State.value_counts()
    m['state_class'] = np.where(m.State.map(big) >= 50, m.State, 'other_states')
    m['reorganisation'] = np.where(m.same_district, 'relaunch_same_district', 'district_changed')
    m['stratum'] = m[['state_class', 'overlap_bucket', 'crop_relevance']].agg('|'.join, axis=1)
    return m


def medium_sample(med, inv, seed=SEED, frac=SAMPLE_FRAC, minimum=SAMPLE_MIN):
    """Deterministic stratified sample: per stratum max(minimum, round(frac*N)) capped at N, drawn with a seeded
    permutation of rows sorted by identity (so the result depends only on the data and the seed)."""
    m = medium_strata(med, inv).sort_values(['stratum', 'State', 'District_new', 'Market_new']).reset_index(drop=True)
    rng = np.random.RandomState(seed)
    picks = []
    for s, g in m.groupby('stratum', sort=True):
        k = min(len(g), max(minimum, int(round(frac * len(g)))))
        picks.extend(g.index[rng.permutation(len(g))[:k]])
    return m.loc[sorted(picks)].assign(sample_seed=seed, sample_rule=f'per stratum max({minimum}, round({frac}*N)), cap N')


def review_evidence(sample, df):
    """Add what a human needs: last old and first new usable prices per shared crop-variety, varieties and grades."""
    rows = []
    for p in sample.itertuples():
        o = df[(df.State == p.State) & (df.District == p.District_old) & (df.Market == p.Market_old) & df.usable_modal_price]
        n = df[(df.State == p.State) & (df.District == p.District_new) & (df.Market == p.Market_new) & df.usable_modal_price]
        ev = []
        for (c, v) in sorted(set(zip(o.Commodity, o.Variety)) & set(zip(n.Commodity, n.Variety)))[:3]:
            lo = o[(o.Commodity == c) & (o.Variety == v)].nlargest(3, 'reported_date')
            fn = n[(n.Commodity == c) & (n.Variety == v)].nsmallest(3, 'reported_date')
            ev.append(f'{c}/{v}: old {list(zip(lo.reported_date.dt.date.astype(str), lo.Modal_Price))} '
                      f'new {list(zip(fn.reported_date.dt.date.astype(str), fn.Modal_Price))}')
        rows.append({'varieties_old': ','.join(sorted(set(o.Variety))), 'varieties_new': ','.join(sorted(set(n.Variety))),
                     'grades_old': ','.join(sorted(set(o.Grade))), 'grades_new': ','.join(sorted(set(n.Grade))),
                     'price_evidence': ' ; '.join(ev) or 'no shared crop-variety'})
    out = pd.concat([sample.reset_index(drop=True), pd.DataFrame(rows)], axis=1)
    for c in ['reviewer_decision', 'reviewer', 'review_date', 'review_notes']:
        out[c] = ''  # to be filled by a person: accept / reject / unsure
    return out


# ---------------------------------------------------------------- 3. de-duplication across accepted identities
def canonical_ids(df, accepted):
    """accepted: DataFrame with old_id, new_id. Records under a new_id take the old_id; all others keep their own."""
    m = dict(zip(accepted.new_id, accepted.old_id))
    own = df.State + '|' + df.District + '|' + df.Market
    return own.map(lambda x: m.get(x, x)), own


def dedupe(df, accepted):
    """Returns (df with canonical_id, source_id, dedup_status, dedup_group, retained), log DataFrame).
    dedup_status: unique | exact_duplicate_retained | exact_duplicate_removed | identity_conflict."""
    d = df.copy()
    d['canonical_id'], d['source_id'] = canonical_ids(d, accepted)
    d['record_ref'] = record_ref(d)
    key = ['canonical_id', 'Commodity', 'Variety', 'Grade', 'Arrival_Date']
    d['dedup_status'], d['dedup_group'] = 'unique', ''
    multi = d.groupby(key, observed=True).source_id.transform('nunique') > 1  # only groups spanning >1 source name
    logs = []
    for gk, g in d[multi].groupby(key, observed=True):
        gid = hashlib.sha256('|'.join(map(str, gk)).encode()).hexdigest()[:16]
        vals = g[EQUIV].apply(pd.to_numeric, errors='coerce').drop_duplicates()
        if len(vals) == 1:
            # tie-break: record under the canonical (old) name first, then smallest source_id, then smallest record_ref
            order = g.assign(_canon=(g.source_id != g.canonical_id).astype(int)).sort_values(['_canon', 'source_id', 'record_ref'])
            keep = order.index[0]
            d.loc[g.index, 'dedup_status'] = 'exact_duplicate_removed'; d.loc[keep, 'dedup_status'] = 'exact_duplicate_retained'
            reason = 'identical min/max/modal under accepted identity'
        else:
            keep = None
            d.loc[g.index, 'dedup_status'] = 'identity_conflict'
            reason = 'values differ under accepted identity: all excluded from targets'
        d.loc[g.index, 'dedup_group'] = gid
        logs.append({'group': gid, **dict(zip(key, gk)), 'equivalence_fields': ','.join(EQUIV), 'n_records': len(g),
                     'source_ids': json.dumps(sorted(set(g.source_id))), 'record_refs': json.dumps(sorted(g.record_ref)),
                     'retained_ref': None if keep is None else d.at[keep, 'record_ref'],
                     'removed_from_view': len(g) - 1 if keep is not None else 0, 'outcome': d.at[g.index[0], 'dedup_status'] if keep is None else 'deduplicated',
                     'tie_break': 'canonical-name record, then source_id, then record_ref (ascending)', 'reason': reason, 'rule': RULE})
    base = d['usable_for_target'] if 'usable_for_target' in d.columns else d['usable_modal_price']  # keep earlier exclusions (e.g. R09)
    d['usable_for_target'] = base & ~d.dedup_status.isin(['exact_duplicate_removed', 'identity_conflict'])
    return d, pd.DataFrame(logs)


# ---------------------------------------------------------------- 4. grades and series keys
def series_key(grade_aware):
    """Weekly series identity: D-33 key with the canonical market id instead of source names (+ grade if grade-aware)."""
    return ['Commodity', 'canonical_id', 'Variety'] + (['Grade'] if grade_aware else [])


def series_stats(d, key):
    u = d[d.usable_for_target].assign(week=lambda x: x.reported_date.dt.to_period('W-SUN'))
    w = u[key + ['week']].drop_duplicates()
    g = w.groupby(key, observed=True).week
    span = (g.max() - g.min()).map(lambda x: x.n) + 1
    obs_weeks = g.nunique()
    return {'series': int(len(obs_weeks)), 'observations': int(len(u)), 'weekly_cells': int(len(w)),
            'series_lt_8_weeks': int((obs_weeks < 8).sum()),
            'median_missing_week_share_within_span': round(float((1 - obs_weeks / span).median()), 3)}


def grade_assessment(d):
    u = d[d.usable_for_target].copy()
    u['year'] = u.reported_date.dt.year
    u['era'] = np.where(u.reported_date >= GO_LIVE, 'post', np.where(u.reported_date < CUTOVER_START, 'pre', 'cutover'))
    faq = u[u.Grade == 'FAQ']
    cov = (u.groupby(['Commodity', 'year']).size().rename('usable').to_frame()
           .join(faq.groupby(['Commodity', 'year']).size().rename('faq'))
           .join(u.groupby(['Commodity', 'year']).canonical_id.nunique().rename('markets'))
           .join(faq.groupby(['Commodity', 'year']).canonical_id.nunique().rename('faq_markets')).fillna(0).astype(int))
    cov['faq_share_pct'] = (100 * cov.faq / cov.usable).round(1)
    # comparability: markets active both pre and post; did they keep reporting FAQ?
    both = u.groupby(['Commodity', 'canonical_id']).era.agg(lambda s: {'pre', 'post'} <= set(s))
    bm = both[both].index
    x = u.set_index(['Commodity', 'canonical_id']).loc[lambda t: t.index.isin(bm)].reset_index()
    sh = x.groupby(['Commodity', 'canonical_id', 'era']).Grade.apply(lambda s: (s == 'FAQ').mean()).unstack()
    comp = {c: {'markets_both_eras': int(len(g)), 'faq_pre_mostly(>=0.5)': int((g.pre >= .5).sum()),
                'of_those_faq_post_mostly': int(((g.pre >= .5) & (g.post >= .5)).sum()),
                'switched_away_from_faq': int(((g.pre >= .5) & (g.post < .5)).sum())}
            for c, g in sh.groupby(level=0)}
    # FAQ vs other grade, same market-variety-day: price ratio
    k = ['Commodity', 'canonical_id', 'Variety', 'reported_date']
    f = u[u.Grade == 'FAQ'].groupby(k).modal_price_rs_per_quintal.median()
    ratios = {}
    for gname in ['Local', 'Non-FAQ', 'Medium', 'Grade A']:
        o = u[u.Grade == gname].groupby(k).modal_price_rs_per_quintal.median()
        r = (o / f).dropna()
        if len(r):
            ratios[gname] = {'pairs': int(len(r)), 'median_ratio_to_faq': round(float(r.median()), 3)}
    designs = {}
    for name, sub, ga in [('pooled_all_grades', d, False), ('faq_only', d[d.Grade == 'FAQ'], False), ('grade_aware', d, True)]:
        designs[name] = {c: series_stats(sub[sub.Commodity == c], series_key(ga)) for c in CROPS}
    return cov.reset_index(), comp, ratios, designs


# ---------------------------------------------------------------- driver
def official_lists(root):
    f = json.loads((root / 'Dataset_Candidates/agmarknet2/2026-10-24/daily-price-arrival_filters.json').read_text())['data']
    # Agmarknet 2.0 spells the state "Keralam"; the data.gov.in feed keeps "Kerala". A state-name alias, not market identity.
    states = {s['state_id']: STATE_ALIASES.get(s['state_name'], s['state_name']) for s in f['state_data']}
    dists = {x['id']: x['district_name'] for x in f['district_data']}
    new = {(fold(states.get(m['state_id'], '')), fold(m['mkt_name'])): {'id': m['id'], 'district': dists.get(m['district_id'], '')}
           for m in f['market_data'] if m['state_id'] is not None}
    fd = pd.read_csv(root / 'Dataset/final_data.csv')
    old = {(fold(r.State), fold(r.Market)): {'code': int(r.Market_code), 'district': r.District} for r in fd.itertuples()}
    return new, old


def main():
    root = Path.cwd(); dest = root / DEST; dest.mkdir(parents=True, exist_ok=True)
    df = pd.concat([pd.read_parquet(root / SRC / f'prices_{c.lower()}.parquet') for c in CROPS], ignore_index=True)
    scored = pd.read_csv(root / MAP / 'candidate_pairs_scored.csv', parse_dates=['first_seen_new', 'last_seen_new', 'first_seen_old', 'last_seen_old'])
    new_off, old_off = official_lists(root)

    hv = validate_high(scored, df, new_off, old_off); hv.to_csv(dest / 'high_confidence_validation.csv', index=False)
    med = scored[scored.confidence == 'medium']
    samp = medium_sample(med, None)
    review_evidence(samp, df).to_csv(dest / 'medium_review_sample.csv', index=False)
    medium_strata(med, None).groupby('stratum').size().rename('N').to_frame().join(samp.groupby('stratum').size().rename('n')).fillna(0).astype(int).to_csv(dest / 'medium_sample_strata.csv')

    accepted = hv[hv.validation_status == 'accepted_rule_v1'][['old_id', 'new_id']]
    d, log = dedupe(df, accepted)
    log.to_csv(dest / 'dedup_log.csv', index=False)
    cov, comp, ratios, designs = grade_assessment(d)
    cov.to_csv(dest / 'faq_coverage_by_crop_year.csv', index=False)

    # unresolved dual reporting (pairs not accepted): what de-duplication would remove if identity were established
    low_dual = scored[(scored.confidence == 'low') & ~scored.succession]
    ld = pd.DataFrame({'old_id': [sid(p.State, p.District_old, p.Market_old) for p in low_dual.itertuples()],
                       'new_id': [sid(p.State, p.District_new, p.Market_new) for p in low_dual.itertuples()]})
    ld = ld[~ld.new_id.duplicated(keep=False) & ~ld.old_id.duplicated(keep=False)]  # hypothetical 1:1 only
    hyp, hyp_log = dedupe(df, ld)
    wk = lambda x: x[x.usable_for_target].assign(w=lambda t: t.reported_date.dt.to_period('W-SUN'))[['Commodity', 'canonical_id', 'Variety', 'w']].drop_duplicates().shape[0]
    summary = {
        'rule': RULE, 'thresholds': {'old_stop_by': OLD_STOP_BY, 'min_field_equal': MIN_FIELD_EQUAL, 'level_ratio': LEVEL_RATIO},
        'high_validation': hv.validation_status.value_counts().to_dict(),
        'high_hard_fail_reasons': hv.hard_fail[hv.hard_fail != ''].str.split(',').explode().value_counts().to_dict(),
        'high_unmet_reasons': hv.unmet[hv.unmet != ''].str.split(',').explode().value_counts().to_dict(),
        'medium_total': int(len(med)), 'medium_sample': int(len(samp)), 'medium_seed': SEED,
        'dedup_accepted_identities': {'groups': int(len(log)), 'outcomes': log.outcome.value_counts().to_dict() if len(log) else {},
                                      'records_removed_from_view': int(log.removed_from_view.sum()) if len(log) else 0,
                                      'by_date': log.groupby('Arrival_Date').removed_from_view.sum().sort_index().to_dict() if len(log) else {},
                                      'identity_conflict_records': int((d.dedup_status == 'identity_conflict').sum())},
        'unresolved_dual_reporting_hypothetical': {'pairs_1to1': int(len(ld)), 'groups': int(len(hyp_log)),
                                                   'records_that_would_be_removed': int(hyp_log.removed_from_view.sum()) if len(hyp_log) else 0,
                                                   'weekly_cells_now_vs_if_resolved': [wk(df.assign(usable_for_target=df.usable_modal_price, canonical_id=df.State + '|' + df.District + '|' + df.Market)), wk(hyp)]},
        'faq_comparability_through_relaunch': comp, 'grade_price_ratio_to_faq_same_market_day': ratios, 'series_designs': designs}
    (dest / 'identity_review_summary.json').write_text(json.dumps(summary, indent=1, default=str))
    print(json.dumps(summary, indent=1, default=str))
    return 0


if __name__ == '__main__':
    sys.exit(main())
