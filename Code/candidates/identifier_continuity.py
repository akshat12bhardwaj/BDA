"""Full-day pulls (paged, 10/call with the sample key) for one commodity on two dates, to measure market/variety
naming continuity across the Agmarknet 2.0 go-live (2025-11-07) against the existing mandi data.
Usage: python identifier_continuity.py <repo> <out_dir> <commodity> <dd/mm/yyyy> [<dd/mm/yyyy> ...]"""
import sys, json, time, subprocess, urllib.parse
from pathlib import Path
import pandas as pd

ROOT, OUT, CROP, DATES = Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3], sys.argv[4:]
KEY = '579b464db66ec23bdd000001cdd3946e44ce4aad7209ff7b23ac571b'
RES = '35985678-0d79-46b4-9ed6-6f13308a1d24'
(OUT / 'raw').mkdir(parents=True, exist_ok=True)


def page(ds, offset):
    path = OUT / 'raw' / f'{CROP}_{ds.replace("/", "-")}_{offset:05d}.json'
    if not path.exists():
        q = urllib.parse.urlencode({'api-key': KEY, 'format': 'json', 'limit': 10, 'offset': offset,
                                    'filters[Commodity]': CROP, 'filters[Arrival_Date]': ds}, safe='/')
        for _ in range(4):
            r = subprocess.run(['curl', '-s', '-f', '-m', '90', f'https://api.data.gov.in/resource/{RES}?{q}'], capture_output=True)
            if r.returncode == 0 and r.stdout.strip().startswith(b'{'):
                path.write_bytes(r.stdout); break
            time.sleep(5)
        time.sleep(0.8)
    return json.loads(path.read_text())


ours = pd.read_parquet(ROOT / f'Processed_Data/cleaned/mandi_cleaned_{CROP.lower()}.parquet', columns=['state', 'market', 'variety'])
known_mkt = set(zip(ours.state.str.lower(), ours.market.str.lower().str.strip()))
known_var = set(ours.variety.str.lower())
res = []
for ds in DATES:
    first = page(ds, 0); total = int(first['total']); recs = list(first['records'])
    for off in range(10, total, 10):
        recs += page(ds, off).get('records', [])
    df = pd.DataFrame(recs); df.to_csv(OUT / f'{CROP}_{ds.replace("/", "-")}_fullday.csv', index=False)
    m = [(s.lower(), k.lower().strip()) in known_mkt for s, k in zip(df.State, df.Market)]
    res.append({'date': ds, 'api_total': total, 'retrieved': len(df), 'dup_rows': int(df.duplicated().sum()),
                'market_name_in_existing_pct': round(100 * sum(m) / len(df), 1),
                'variety_in_existing_pct': round(100 * df.Variety.str.lower().isin(known_var).mean(), 1),
                'grades': df.Grade.value_counts().to_dict(), 'top_varieties': df.Variety.value_counts().head(5).to_dict(),
                'example_unmatched_markets': df.loc[[not x for x in m], ['State', 'Market']].head(8).values.tolist(),
                'modal_min_max': [float(pd.to_numeric(df.Modal_Price).min()), float(pd.to_numeric(df.Modal_Price).max())]})
print(json.dumps(res, indent=1))
(OUT / f'{CROP}_continuity.json').write_text(json.dumps(res, indent=1))
