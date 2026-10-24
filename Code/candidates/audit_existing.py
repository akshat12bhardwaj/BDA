"""Read-only audit of the existing BDA datasets. Writes CSVs to argv[2]; never touches the repo."""
import sys, json
from pathlib import Path
import pandas as pd

ROOT = Path(sys.argv[1]); OUT = Path(sys.argv[2]); OUT.mkdir(parents=True, exist_ok=True)
summary = {}

# ---- Mandi (Phase 5 cleaned = raw rows minus identical copies; status columns record raw state)
cols = ['crop', 'state', 'district', 'market', 'variety', 'arrivals_tonnes', 'min_price_rs_per_quintal',
        'max_price_rs_per_quintal', 'modal_price_rs_per_quintal', 'reported_date', 'dup_type', 'modal_price_status',
        'arrivals_status', 'min_gt_max', 'price_extreme_level', 'arrivals_extreme_level', 'usable_modal_price',
        'usable_arrivals', 'weather_match', 'apy_district_match']
by_year, by_state, per_crop, gaps = [], [], [], []
for crop in ['onion', 'potato', 'wheat']:
    d = pd.read_parquet(ROOT / f'Processed_Data/cleaned/mandi_cleaned_{crop}.parquet', columns=cols)
    d['year'] = d.reported_date.dt.year
    d['usable_modal_price'] = d.usable_modal_price.astype(bool); d['usable_arrivals'] = d.usable_arrivals.astype(bool)
    raw = sum(1 for _ in open(ROOT / f'Dataset/India Commodity Wise Mandi Dataset/{crop.title()}.csv', encoding='utf-8', errors='ignore')) - 1
    s = {
        'crop': crop.title(), 'raw_rows': raw, 'cleaned_rows': len(d), 'raw_columns': 10,
        'first_date': str(d.reported_date.min().date()), 'last_date': str(d.reported_date.max().date()),
        'states': d.state.nunique(), 'districts': d[['state', 'district']].drop_duplicates().shape[0],
        'markets': d[['state', 'district', 'market']].drop_duplicates().shape[0], 'varieties': d.variety.nunique(),
        'modal_missing_or_zero_pct': round(100 * (~d.usable_modal_price.astype(bool)).mean(), 3),
        'arrivals_unusable_pct': round(100 * (~d.usable_arrivals.astype(bool)).mean(), 3),
        'dup_type': d.dup_type.astype(str).value_counts().to_dict(),
        'arrivals_extreme_flagged': d.arrivals_extreme_level.astype(str).value_counts().to_dict(),
        'price_extreme_flagged': d.price_extreme_level.astype(str).value_counts().to_dict(),
        'weather_match_pct': round(100 * (d.weather_match == 'exact_district').mean(), 2),
        'apy_district_match_pct': round(100 * d.apy_district_match.isin(['exact_normalized', 'reviewed_alias', 'parenthetical_part']).mean(), 2),
    }
    for c in ['state', 'district', 'market', 'variety', 'arrivals_tonnes', 'min_price_rs_per_quintal',
              'max_price_rs_per_quintal', 'modal_price_rs_per_quintal', 'reported_date']:
        s[f'null_{c}_pct'] = round(100 * d[c].isna().mean(), 3)
    s['status_counts_modal'] = d.modal_price_status.value_counts().to_dict()
    s['status_counts_arrivals'] = d.arrivals_status.value_counts().to_dict()
    per_crop.append(s)

    y = d.groupby('year').agg(rows=('market', 'size'), markets=('market', 'nunique'), states=('state', 'nunique'),
                              modal_unusable_pct=('usable_modal_price', lambda x: round(100 * (~x.astype(bool)).mean(), 2)),
                              arrivals_unusable_pct=('usable_arrivals', lambda x: round(100 * (~x.astype(bool)).mean(), 2)),
                              weather_match_pct=('weather_match', lambda x: round(100 * (x == 'exact_district').mean(), 1)))
    y.insert(0, 'crop', crop.title()); by_year.append(y.reset_index())

    st = d.groupby('state').agg(rows=('market', 'size'), markets=('market', 'nunique'),
                                first=('reported_date', 'min'), last=('reported_date', 'max'),
                                modal_unusable_pct=('usable_modal_price', lambda x: round(100 * (~x.astype(bool)).mean(), 2)))
    st.insert(0, 'crop', crop.title()); by_state.append(st.reset_index())

    # Reporting density: for each market, share of calendar days with >=1 record between its first and last date
    md = d.groupby(['state', 'district', 'market']).reported_date.agg(['min', 'max', 'nunique'])
    md['span_days'] = (md['max'] - md['min']).dt.days + 1
    md['density'] = md['nunique'] / md['span_days']
    big = md[md.span_days >= 365]
    gaps.append({'crop': crop.title(), 'markets_span_ge_1y': len(big),
                 'median_daily_density': round(big.density.median(), 3),
                 'p25_daily_density': round(big.density.quantile(.25), 3),
                 'markets_density_lt_25pct': int((big.density < .25).sum()),
                 'markets_reporting_in_2023': int((md['max'] >= '2023-01-01').sum()),
                 'markets_reporting_after_2024_01_01': int((md['max'] >= '2024-01-01').sum())})
    del d

pd.DataFrame(per_crop).to_csv(OUT / 'mandi_per_crop.csv', index=False)
pd.concat(by_year).to_csv(OUT / 'mandi_by_year.csv', index=False)
pd.concat(by_state).to_csv(OUT / 'mandi_by_state.csv', index=False)
pd.DataFrame(gaps).to_csv(OUT / 'mandi_reporting_density.csv', index=False)
summary['mandi'] = per_crop; summary['mandi_density'] = gaps

# ---- Weather panel
w = pd.read_parquet(ROOT / 'Processed_Data/integration/weather_daily_panel.parquet')
wv = [c for c in w.columns if c not in ('weather_state', 'weather_district', 'reported_date')]
summary['weather'] = {'rows': len(w), 'locations': w[['weather_state', 'weather_district']].drop_duplicates().shape[0],
                      'first': str(w.reported_date.min().date()), 'last': str(w.reported_date.max().date()),
                      'null_pct': {c: round(100 * w[c].isna().mean(), 3) for c in wv},
                      'dup_keys': int(w.duplicated(['weather_state', 'weather_district', 'reported_date']).sum()),
                      'tmax_lt_tmin': int((w.temperature_2m_max < w.temperature_2m_min).sum()),
                      'rain_negative': int((w.rain_sum < 0).sum()),
                      'tmax_gt_50': int((w.temperature_2m_max > 50).sum())}

# ---- APY for the three crops
a = pd.read_csv(ROOT / 'Dataset/crop-wise-area-production-yield.csv', low_memory=False)
a3 = a[a.crop_name.isin(['Onion', 'Potato', 'Wheat'])]
apy = []
for c, g in a3.groupby('crop_name'):
    apy.append({'crop': c, 'rows': len(g), 'years': g.year.nunique(), 'first': g.year.min(), 'last': g.year.max(),
                'states': g.state_name.nunique(), 'districts': g[['state_name', 'district_name']].drop_duplicates().shape[0],
                'area_null_pct': round(100 * g.area.isna().mean(), 2), 'production_null_pct': round(100 * g.production.isna().mean(), 2),
                'production_zero_pct': round(100 * (g.production == 0).mean(), 2), 'yield_null_pct': round(100 * g['yield'].isna().mean(), 2),
                'units': f"{g.area_unit.unique().tolist()} {g.production_unit.unique().tolist()}",
                'dup_keys': int(g.duplicated(['year', 'state_name', 'district_name', 'season']).sum())})
pd.DataFrame(apy).to_csv(OUT / 'apy_per_crop.csv', index=False)
apy_year = a3.groupby(['crop_name', 'year']).agg(districts=('district_name', 'nunique'),
                                                 prod_null_pct=('production', lambda x: round(100 * x.isna().mean(), 1))).reset_index()
apy_year.to_csv(OUT / 'apy_by_year.csv', index=False)
summary['apy'] = apy

# ---- Agri Market + final_data
am = pd.read_csv(ROOT / 'Dataset/Agri Market Dataset.csv')
summary['agri_market'] = {'rows': len(am), 'cols': am.shape[1], 'commodities': am.iloc[:, 0:12].nunique().to_dict()}
fd = pd.read_csv(ROOT / 'Dataset/final_data.csv')
summary['final_data'] = {'rows': len(fd), 'cols': fd.shape[1], 'null_pct': (fd.isna().mean() * 100).round(2).to_dict(),
                         'dup_market_code': int(fd.Market_code.duplicated().sum())}

(OUT / 'summary.json').write_text(json.dumps(summary, indent=1, default=str))
print(json.dumps(summary, indent=1, default=str))
