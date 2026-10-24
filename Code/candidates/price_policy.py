"""Price-anomaly policy for the candidate data.gov.in price feed (Data_Source_Review.md §6.3), aligned with Phase 5.

Reads only crop-days the extraction manifest marks `pass` (first fetch) for the named stages and never changes them.
Every source field is kept as received (strings); parsed copies get Phase 5 names. Rules, as in Code/cleaning:
  R04  zero / negative / non-finite price -> missing in the parsed copy (`value_status`, the Phase 5 function)
  R03  same key (state, district, market, commodity, variety, grade, date) with different values -> key_conflict
  R07  min > max -> min_gt_max
  R08  modal outside [min, max] -> modal_outside_range
Flagged records stay in the table with `price_anomaly` (first applicable reason) and are excluded from
`usable_modal_price`, the only column forecasting targets may use. Not applied yet: R09 (scale error against a
trailing reference); it needs the reconciled market history (migration step M3).

Usage (repo root): python -m Code.candidates.price_policy S1 [S2 ...]
Outputs: Processed_Data/candidates/datagov_prices/analytical_v1/ (parquet tables are git-ignored and regenerable)."""
import json, sys
from pathlib import Path

import pandas as pd

from Code.candidates.datagov_extract import CROPS, OUT, RAW, STAGES, raw_paths, read_manifest, stage_days
from Code.cleaning.pipeline import value_status

POLICY_VERSION = 'candidate-price-policy-v1'
KEY = ['State', 'District', 'Market', 'Commodity', 'Variety', 'Grade', 'Arrival_Date']
PARSED = {'Min_Price': 'min_price_rs_per_quintal', 'Max_Price': 'max_price_rs_per_quintal', 'Modal_Price': 'modal_price_rs_per_quintal'}
SOURCE_FIELDS = ['State', 'District', 'Market', 'Commodity', 'Commodity_Code', 'Variety', 'Grade', 'Arrival_Date',
                 'Min_Price', 'Max_Price', 'Modal_Price']
REASONS = ['none', 'modal_missing', 'key_conflict', 'min_gt_max', 'modal_outside_range']
DEST = OUT / 'analytical_v1'


def type_variant_duplicates(df):
    """Records identical in every source field once compared as text (the feed published the same record with string and
    with numeric JSON values). Returns a boolean Series marking the copy to drop: keep the string-typed (legacy-format)
    copy, then the lower raw position. Requires the raw_value_types / raw_index columns from load_accepted."""
    order = df.assign(_num=(df['raw_value_types'] != 'str').astype(int)).sort_values(['_num', 'raw_index'], kind='stable')
    return order.duplicated(SOURCE_FIELDS, keep='first').reindex(df.index)


def apply_policy(df, dedup_type_variants=False):
    """Add parsed prices, R03/R04/R07/R08 flags, `price_anomaly` and `usable_modal_price`. Source columns untouched.
    dedup_type_variants=True (policy v1.1): exact text-identical copies are marked `type_variant_duplicate` and excluded
    before R03, so they no longer appear as key conflicts. False reproduces policy v1 exactly."""
    out = df.copy()
    out['reported_date'] = pd.to_datetime(out['Arrival_Date'], format='%d/%m/%Y')
    for src, dst in PARSED.items():
        out[dst], out[dst.replace('_rs_per_quintal', '_status')] = value_status(pd.to_numeric(out[src], errors='coerce').astype('float64'), zero_is_missing=True)
    mn, mx, md = (out[c] for c in PARSED.values())
    tv = type_variant_duplicates(out) if dedup_type_variants else pd.Series(False, index=out.index)
    # records are otherwise distinct, so a shared key among the remaining records means differing values
    out['key_conflict'] = out[~tv].duplicated(KEY, keep=False).reindex(out.index, fill_value=False)
    out['min_gt_max'] = (mn > mx).fillna(False).astype(bool)
    out['modal_outside_range'] = ((md < mn) | (md > mx)).fillna(False).astype(bool)
    reason = pd.Series('none', index=out.index)
    for col, name in [('modal_outside_range', 'modal_outside_range'), ('min_gt_max', 'min_gt_max'), ('key_conflict', 'key_conflict')]:
        reason = reason.mask(out[col], name)
    reason = reason.mask(md.isna(), 'modal_missing')  # applied last, so it wins: no modal means no target at all
    if dedup_type_variants:
        reason = reason.mask(tv, 'type_variant_duplicate')
    out['price_anomaly'] = pd.Categorical(reason, categories=REASONS + (['type_variant_duplicate'] if dedup_type_variants else []))
    out['usable_modal_price'] = (reason == 'none').to_numpy()
    out['policy_version'] = POLICY_VERSION + ('.1' if dedup_type_variants else '')
    return out


def anomaly_rates(df):
    """Counts and rates by crop x state x month."""
    g = df.assign(month=df['reported_date'].dt.to_period('M').astype(str)).groupby(['Commodity', 'State', 'month'], observed=True)
    r = g.agg(records=('Market', 'size'), modal_outside_range=('modal_outside_range', 'sum'), min_gt_max=('min_gt_max', 'sum'),
              key_conflict=('key_conflict', 'sum'), usable=('usable_modal_price', 'sum')).reset_index()
    r['modal_outside_range_pct'] = (100 * r['modal_outside_range'] / r['records']).round(2)
    r['excluded_pct'] = (100 * (1 - r['usable'] / r['records'])).round(2)
    return r


def policy_effect(df, by=('Commodity',)):
    """Usable observations and coverage with modal present only (before) vs after the exclusion policy.
    Coverage units: markets, and market x variety x week cells (the D-38 weekly target grain)."""
    d = df.assign(week=df['reported_date'].dt.to_period('W-SUN').astype(str))
    rows = []
    for k, g in d.groupby(list(by), observed=True):
        before, after = g[g['modal_price_rs_per_quintal'].notna()], g[g['usable_modal_price']]
        cells = lambda x: x[['State', 'Market', 'Variety', 'week']].drop_duplicates().shape[0]
        mkts = lambda x: x[['State', 'Market']].drop_duplicates().shape[0]
        rows.append({**dict(zip(by, k if isinstance(k, tuple) else (k,))), 'records': len(g),
                     'usable_before': len(before), 'usable_after': len(after),
                     'excluded_by_policy': len(before) - len(after),
                     'markets_before': mkts(before), 'markets_after': mkts(after),
                     'weekly_cells_before': cells(before), 'weekly_cells_after': cells(after),
                     'weekly_cells_lost_pct': round(100 * (1 - cells(after) / max(cells(before), 1)), 2)})
    return pd.DataFrame(rows)


def load_accepted(root, stages):
    man = read_manifest(root / OUT / 'crop_day_manifest.csv')
    frames, used = [], 0
    for s in stages:
        for d in stage_days(STAGES[s]['start'], STAGES[s]['end']):
            for c in CROPS:
                row = man.get((c, d))
                if not row or row['status'] != 'pass':
                    raise SystemExit(f'{c} {d} is not an accepted crop-day ({row["status"] if row else "missing"}); stage {s} incomplete')
                recs = json.loads(raw_paths(root / RAW, c, d)[0].read_bytes())['records']
                # raw_index / raw_value_types keep what dtype=str hides: position in the raw file and str vs numeric JSON
                frames.append(pd.DataFrame(recs, dtype=str).assign(
                    source_stage=s, content_sha256=row['content_sha256'], retrieved_utc=row['retrieved_utc'],
                    raw_index=range(len(recs)), raw_value_types=['str' if isinstance(r.get('Modal_Price'), str) else 'num' for r in recs]))
                used += 1
    return pd.concat(frames, ignore_index=True), used


def main():
    stages = sys.argv[1:]
    if not stages or any(s not in STAGES for s in stages):
        print(f'usage: python -m Code.candidates.price_policy {" ".join(sorted(STAGES))}'); return 2
    root = Path.cwd(); dest = root / DEST; dest.mkdir(parents=True, exist_ok=True)
    raw, n_days = load_accepted(root, stages)
    df = apply_policy(raw)
    for c in CROPS:
        df[df['Commodity'] == c].to_parquet(dest / f'prices_{c.lower()}.parquet', index=False)
    anomaly_rates(df).to_csv(dest / 'anomaly_rates_by_crop_state_month.csv', index=False)
    eff = policy_effect(df); eff.to_csv(dest / 'policy_effect_by_crop.csv', index=False)
    policy_effect(df, ('Commodity', 'State')).to_csv(dest / 'policy_effect_by_crop_state.csv', index=False)
    summary = {'policy_version': POLICY_VERSION, 'stages': stages, 'crop_days': n_days, 'records': len(df),
               'date_range': [str(df['reported_date'].min().date()), str(df['reported_date'].max().date())],
               'price_anomaly_counts': df.groupby(['Commodity', 'price_anomaly'], observed=True).size().unstack(fill_value=0).to_dict('index'),
               'effect_by_crop': eff.to_dict('records')}
    (dest / 'policy_summary.json').write_text(json.dumps(summary, indent=1, default=str))
    print(json.dumps(summary, indent=1, default=str))
    return 0


if __name__ == '__main__':
    sys.exit(main())
