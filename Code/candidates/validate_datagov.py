"""Small, rate-limited sample from the data.gov.in variety-wise mandi price API, compared with the
existing cleaned mandi data. Raw responses are kept as-is under OUT/raw; nothing in the repo is written.
Usage: python validate_datagov.py <repo> <out_dir>"""
import sys, json, time, subprocess, urllib.parse
from pathlib import Path
import pandas as pd

ROOT, OUT = Path(sys.argv[1]), Path(sys.argv[2]); (OUT / 'raw').mkdir(parents=True, exist_ok=True)
KEY = '579b464db66ec23bdd000001cdd3946e44ce4aad7209ff7b23ac571b'  # data.gov.in public sample key (10 records/call)
RES = '35985678-0d79-46b4-9ed6-6f13308a1d24'


def call(name, **filters):
    q = {'api-key': KEY, 'format': 'json', 'limit': 10}
    q.update({f'filters[{k}]': v for k, v in filters.items()})
    url = f'https://api.data.gov.in/resource/{RES}?' + urllib.parse.urlencode(q, safe='/')
    path = OUT / 'raw' / f'{name}.json'
    if not path.exists():
        # the endpoint stalls on Python-urllib's User-Agent; curl works
        for attempt in range(3):
            r = subprocess.run(['curl', '-s', '-f', '-m', '90', url], capture_output=True)
            if r.returncode == 0 and r.stdout.strip().startswith(b'{'):
                path.write_bytes(r.stdout); break
            print('retry', name, r.returncode); time.sleep(5)
        time.sleep(1.0)
    return json.loads(path.read_text()) if path.exists() else {}


ours = {c: pd.read_parquet(ROOT / f'Processed_Data/cleaned/mandi_cleaned_{c.lower()}.parquet',
                           columns=['state', 'district', 'market', 'variety', 'modal_price_rs_per_quintal',
                                    'min_price_rs_per_quintal', 'max_price_rs_per_quintal', 'arrivals_tonnes', 'reported_date'])
        for c in ['Onion', 'Potato', 'Wheat']}

# 1) Daily record counts: API total vs our rows, same commodity and date
dates = ['2005-06-15', '2010-01-15', '2013-08-14', '2016-01-15', '2018-11-14', '2020-04-15',
         '2021-07-14', '2022-12-14', '2023-06-14', '2024-01-17']
counts = []
for crop, d in ours.items():
    for ds in dates:
        dt = pd.Timestamp(ds)
        j = call(f'count_{crop}_{ds}', Commodity=crop, Arrival_Date=dt.strftime('%d/%m/%Y'))
        counts.append({'crop': crop, 'date': ds, 'api_total': int(j.get('total') or 0),
                       'ours_rows': int((d.reported_date == dt).sum()),
                       'ours_markets': d.loc[d.reported_date == dt, 'market'].nunique()})
counts = pd.DataFrame(counts); counts['api_minus_ours'] = counts.api_total - counts.ours_rows
counts.to_csv(OUT / 'daily_count_comparison.csv', index=False)
print(counts.to_string())

# 2) Record-level match: market-days sampled from our data (stratified by year), looked up in the API
rows = []
for crop, d in ours.items():
    pool = d[d.reported_date.dt.year.isin([2008, 2014, 2019, 2023])]
    samp = pool.groupby(pool.reported_date.dt.year, group_keys=False).apply(lambda g: g.sample(3, random_state=7))
    for _, r in samp.iterrows():
        ds = r.reported_date.strftime('%d/%m/%Y')
        j = call(f'rec_{crop}_{r.market}_{r.reported_date.date()}'.replace('/', '-').replace(' ', '_'),
                 Commodity=crop, State=r.state, Market=r.market, Arrival_Date=ds)
        recs = j.get('records', [])
        same_var = [x for x in recs if x['Variety'] == r.variety]
        api_modal = [float(x['Modal_Price']) for x in same_var]
        rows.append({'crop': crop, 'date': str(r.reported_date.date()), 'state': r.state, 'market': r.market,
                     'variety': r.variety, 'ours_modal': r.modal_price_rs_per_quintal, 'ours_arrivals_t': r.arrivals_tonnes,
                     'api_records_market_day': len(recs), 'api_same_variety': len(same_var),
                     'api_modal_same_variety': api_modal, 'api_grades': sorted({x['Grade'] for x in recs}),
                     'modal_match': (r.modal_price_rs_per_quintal in api_modal) if api_modal else None})
rec = pd.DataFrame(rows); rec.to_csv(OUT / 'record_match_sample.csv', index=False)
print(rec.to_string())
print('match rate (where API has same variety):', rec.modal_match.dropna().mean(), 'n=', rec.modal_match.notna().sum(),
      '| API found market-day:', (rec.api_records_market_day > 0).mean())

# 3) Post-February-2024 sample (no overlap): schema/plausibility only
post = []
for crop in ours:
    j = call(f'post_{crop}_2026-10-20', Commodity=crop, Arrival_Date='20/10/2026')
    post.append({'crop': crop, 'date': '2026-10-20', 'api_total': j.get('total'), 'sample': j.get('records', [])[:3]})
(OUT / 'post_2024_sample.json').write_text(json.dumps(post, indent=1))
print(json.dumps(post, indent=1)[:2500])
