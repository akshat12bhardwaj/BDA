"""Proposed market-identity mapping across the Agmarknet 2.0 cut-over (Data_Source_Review.md §6.5). Nothing is merged.

Inputs: the candidate policy tables (Processed_Data/candidates/datagov_prices/analytical_v1/prices_<crop>.parquet).
Source identity: (State, District, Market) exactly as published. Era: `pre` if last seen before CUTOVER_START,
`post` if first seen on/after it, else `spans`.

A name rule (case/punctuation folded, trailing " APMC" removed) only GENERATES candidate pairs (old -> new) inside
one state. A pair is proposed only on independent evidence, never on the name, the suffix or equal prices alone:
  same_district   district names equal after case/space folding
  one_to_one      the new market has exactly one candidate and that old market exactly one
  succession      old last seen <= CUTOVER_END + GRACE days and new first seen >= CUTOVER_START - GRACE days
  co_reported     records on the same date, crop, variety and grade under both names (usable prices only),
                  with the share whose modal price is identical
Confidence: high = all four with >= MIN_PAIRS co-reported records and >= MIN_EQUAL identical;
            medium = same_district + one_to_one + succession, co-reporting weaker or absent;
            low = anything else (kept, never mapped). review_status is never 'approved' here.

Usage (repo root): python -m Code.candidates.market_mapping
Outputs: Processed_Data/candidates/datagov_prices/market_mapping/ (CSV/JSON)."""
import json, re, sys
from pathlib import Path

import pandas as pd

from Code.candidates.datagov_extract import CROPS, OUT

SRC = OUT / 'analytical_v1'
DEST = OUT / 'market_mapping'
CUTOVER_START, CUTOVER_END, GO_LIVE = '2025-11-01', '2025-11-06', '2025-11-07'
GRACE, MIN_PAIRS, MIN_EQUAL = 14, 5, 0.95
ID = ['State', 'District', 'Market']


def fold(s):
    return re.sub(r'[^a-z0-9]', '', str(s).lower())


def base_name(m):
    return fold(re.sub(r'\s*APMC\s*$', '', str(m), flags=re.I))


def inventory(df):
    """One row per source market identity."""
    inv = df.groupby(ID, observed=True).agg(first_seen=('reported_date', 'min'), last_seen=('reported_date', 'max'),
                                            n_records=('Market', 'size'),
                                            crops=('Commodity', lambda s: ','.join(sorted(set(s)))),
                                            grades=('Grade', lambda s: ','.join(sorted(set(s))))).reset_index()
    inv['era'] = 'spans'
    inv.loc[inv.last_seen < CUTOVER_START, 'era'] = 'pre'
    inv.loc[inv.first_seen >= CUTOVER_START, 'era'] = 'post'
    inv['base'] = inv.Market.map(base_name)
    return inv


def candidates(inv):
    """Old (not post-only) x new (post-only) pairs in the same state sharing a folded base name."""
    old = inv[inv.era != 'post']; new = inv[inv.era == 'post']
    c = new.merge(old, on=['State', 'base'], suffixes=('_new', '_old'))
    return c[c.Market_new != c.Market_old].reset_index(drop=True)


def co_reporting(df, pairs):
    """Per pair: records reported on the same date/crop/variety/grade under both names, and the identical-modal share."""
    u = df[df['usable_modal_price']][ID + ['Commodity', 'Variety', 'Grade', 'reported_date', 'modal_price_rs_per_quintal']]
    keys = ['Commodity', 'Variety', 'Grade', 'reported_date']
    p = pairs[['State', 'District_old', 'Market_old', 'District_new', 'Market_new']].reset_index(names='pair')
    a = p.merge(u, left_on=['State', 'District_old', 'Market_old'], right_on=ID)
    b = p.merge(u, left_on=['State', 'District_new', 'Market_new'], right_on=ID)
    j = a[['pair'] + keys + ['modal_price_rs_per_quintal']].merge(b[['pair'] + keys + ['modal_price_rs_per_quintal']],
                                                                  on=['pair'] + keys, suffixes=('_o', '_n'))
    j['eq'] = j.modal_price_rs_per_quintal_o == j.modal_price_rs_per_quintal_n
    g = j.groupby('pair').eq.agg(['size', 'mean'])
    return [(int(g.at[i, 'size']), round(float(g.at[i, 'mean']), 4)) if i in g.index else (0, None) for i in p.pair]


def score(pairs, co):
    p = pairs.copy()
    p['co_reported'], p['identical_share'] = zip(*co) if len(co) else ([], [])
    p['same_district'] = p.District_old.map(fold) == p.District_new.map(fold)
    n_new = p.groupby(ID[:1] + ['District_new', 'Market_new']).Market_old.transform('size')
    n_old = p.groupby(ID[:1] + ['District_old', 'Market_old']).Market_new.transform('size')
    p['one_to_one'] = (n_new == 1) & (n_old == 1)
    lim_old = pd.Timestamp(CUTOVER_END) + pd.Timedelta(days=GRACE)
    lim_new = pd.Timestamp(CUTOVER_START) - pd.Timedelta(days=GRACE)
    p['succession'] = (p.last_seen_old <= lim_old) & (p.first_seen_new >= lim_new)
    strong = (p.co_reported >= MIN_PAIRS) & (pd.to_numeric(p.identical_share, errors='coerce').fillna(0) >= MIN_EQUAL)
    base = p.same_district & p.one_to_one & p.succession
    p['confidence'] = 'low'
    p.loc[base, 'confidence'] = 'medium'
    p.loc[base & strong, 'confidence'] = 'high'
    p['review_status'] = p.confidence.map({'high': 'proposed', 'medium': 'proposed_needs_review', 'low': 'ambiguous_not_mapped'})
    return p


def mapping_table(inv, scored):
    """One row per source identity, with its proposed canonical identity (pre-relaunch name) where justified."""
    t = inv.copy()
    t['canonical_market_id'] = t.State + '|' + t.District + '|' + t.Market
    t['mapping_type'] = t.era.map({'pre': 'pre_relaunch_only', 'spans': 'continuous', 'post': 'post_relaunch_unmatched'})
    t['effective_from'] = ''
    t['confidence'] = ''; t['review_status'] = ''; t['evidence'] = ''
    for r in scored.itertuples():
        i = t.index[(t.State == r.State) & (t.District == r.District_new) & (t.Market == r.Market_new)][0]
        ev = json.dumps({'old': [r.State, r.District_old, r.Market_old], 'same_district': bool(r.same_district),
                         'one_to_one': bool(r.one_to_one), 'succession': bool(r.succession), 'co_reported': int(r.co_reported),
                         'identical_share': r.identical_share, 'old_last_seen': str(r.last_seen_old.date()),
                         'new_first_seen': str(r.first_seen_new.date())})
        t.at[i, 'evidence'] = ev if not t.at[i, 'evidence'] else t.at[i, 'evidence'] + ' || ' + ev
        t.at[i, 'confidence'], t.at[i, 'review_status'] = r.confidence, r.review_status
        if r.confidence != 'low':
            t.at[i, 'canonical_market_id'] = f'{r.State}|{r.District_old}|{r.Market_old}'
            t.at[i, 'mapping_type'] = 'renamed_successor'
            t.at[i, 'effective_from'] = str(r.first_seen_new.date())
        else:
            t.at[i, 'mapping_type'] = 'ambiguous_candidate'
    return t.drop(columns='base')


def weekly_effect(df, table):
    """Series fragmentation and cut-over double reporting at the D-33 series grain (crop, state, district, market,
    variety; weekly median), before vs after applying only the high/medium proposed mappings."""
    d = df[df['usable_modal_price']].copy()
    d['week_start'] = d.reported_date.dt.to_period('W-SUN').dt.start_time
    canon = table.set_index(ID)['canonical_market_id']
    mapped = table[table.mapping_type == 'renamed_successor'].set_index(ID)['canonical_market_id']
    d['source_id'] = d.State + '|' + d.District + '|' + d.Market
    d['canon_id'] = [mapped.get((s, di, m), sid) for s, di, m, sid in zip(d.State, d.District, d.Market, d.source_id)]
    res = {}
    for name, col in [('source_names', 'source_id'), ('proposed_mapping', 'canon_id')]:
        s = d.groupby(['Commodity', col, 'Variety'], observed=True)
        res[name] = {'series': int(s.ngroups), 'weekly_cells': int(d[['Commodity', col, 'Variety', 'week_start']].drop_duplicates().shape[0])}
    # records duplicated across names once mapped: same canonical market, crop, variety, grade, date and identical prices
    k = ['Commodity', 'canon_id', 'Variety', 'Grade', 'reported_date', 'Min_Price', 'Max_Price', 'Modal_Price']
    dup = d[d.source_id != d.canon_id].merge(d[d.source_id == d.canon_id][k], on=k)
    res['cross_name_identical_records_after_mapping'] = int(len(dup))
    res['cross_name_identical_by_date'] = dup.groupby(dup.reported_date.dt.date.astype(str)).size().to_dict()
    w = d[(d.reported_date >= '2025-10-27') & (d.reported_date <= '2025-11-09')]
    res['cutover_weeks_cells'] = {n: int(w[['Commodity', c, 'Variety', 'week_start']].drop_duplicates().shape[0])
                                  for n, c in [('source_names', 'source_id'), ('proposed_mapping', 'canon_id')]}
    return res


def grade_profile(df):
    g = df.assign(month=df.reported_date.dt.to_period('M').astype(str)).groupby(['month', 'Grade']).size().unstack(fill_value=0)
    # market-variety-days with more than one grade: pooled into one weekly median under the D-33 series key
    k = ['Commodity', 'State', 'District', 'Market', 'Variety', 'reported_date']
    multi = df.groupby(k, observed=True).Grade.nunique()
    m = multi.reset_index().assign(month=lambda x: x.reported_date.dt.to_period('M').astype(str)).groupby('month').Grade.apply(lambda s: round(100 * (s > 1).mean(), 2))
    return g, m.rename('pct_market_variety_days_multi_grade')


def main():
    root = Path.cwd(); dest = root / DEST; dest.mkdir(parents=True, exist_ok=True)
    df = pd.concat([pd.read_parquet(root / SRC / f'prices_{c.lower()}.parquet') for c in CROPS], ignore_index=True)
    inv = inventory(df)
    pairs = candidates(inv)
    scored = score(pairs, co_reporting(df, pairs))
    table = mapping_table(inv, scored)
    table.to_csv(dest / 'market_mapping_proposed.csv', index=False)
    scored[scored.confidence == 'low'].to_csv(dest / 'ambiguous_candidates.csv', index=False)
    scored.to_csv(dest / 'candidate_pairs_scored.csv', index=False)
    g, m = grade_profile(df)
    pd.concat([g, m], axis=1).to_csv(dest / 'grades_by_month.csv')
    eff = weekly_effect(df, table)
    summary = {'records': len(df), 'date_range': [str(df.reported_date.min().date()), str(df.reported_date.max().date())],
               'source_identities': len(inv), 'era_counts': inv.era.value_counts().to_dict(),
               'candidate_pairs': len(scored), 'confidence_counts': scored.confidence.value_counts().to_dict(),
               'post_relaunch_without_candidate': int(((table.era == 'post') & (table.mapping_type == 'post_relaunch_unmatched')).sum()),
               'pre_relaunch_only_identities': int((table.era == 'pre').sum()),
               'weekly_effect': eff,
               'rules': {'cutover': [CUTOVER_START, CUTOVER_END], 'go_live': GO_LIVE, 'grace_days': GRACE,
                         'min_pairs': MIN_PAIRS, 'min_identical_share': MIN_EQUAL}}
    (dest / 'mapping_summary.json').write_text(json.dumps(summary, indent=1, default=str))
    print(json.dumps(summary, indent=1, default=str))
    return 0


if __name__ == '__main__':
    sys.exit(main())
