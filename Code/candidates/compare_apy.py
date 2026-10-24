"""Compare the existing APY file with the March-2026 DES mirror and the UPAg district file (Onion/Potato/Wheat).
Usage: python compare_apy.py <existing_csv> <des_new_csv> <upag_csv> <out_dir>"""
import sys, json
from pathlib import Path
import numpy as np, pandas as pd

old, new, upag = (pd.read_csv(p, low_memory=False) for p in sys.argv[1:4]); OUT = Path(sys.argv[4]); OUT.mkdir(exist_ok=True)
CROPS = ['Onion', 'Potato', 'Wheat']
res = {'old_rows': len(old), 'new_rows': len(new), 'old_years': sorted(old.year.unique())[-3:], 'new_years': sorted(new.year.unique())[-3:],
       'old_cols': old.columns.tolist() == new.columns.tolist()}

key = ['year', 'state_name', 'district_name', 'crop_name', 'season']
o3, n3 = old[old.crop_name.isin(CROPS)], new[new.crop_name.isin(CROPS)]
res['per_crop'] = {c: {'old_rows': int((o3.crop_name == c).sum()), 'new_rows': int((n3.crop_name == c).sum()),
                       'new_years_added': sorted(set(n3[n3.crop_name == c].year) - set(o3[o3.crop_name == c].year))} for c in CROPS}
m = o3.merge(n3, on=key, how='outer', suffixes=('_old', '_new'), indicator=True)
res['merge'] = m._merge.value_counts().to_dict()
both = m[m._merge == 'both']
rel = (both.production_new - both.production_old).abs() / both.production_old.abs().replace(0, np.nan)
res['production_revised_rows'] = int((rel > 1e-6).sum()); res['production_revised_gt5pct'] = int((rel > .05).sum())
res['new_only_by_year'] = m[m._merge == 'right_only'].groupby(['crop_name', 'year']).size().to_dict()
res['old_only_by_year'] = m[m._merge == 'left_only'].groupby(['crop_name', 'year']).size().to_dict()

# UPAg: which of our crops exist, years, missingness, and unit inference against DES wheat
res['upag_crops_present'] = {c: int((upag.crop_name == c).sum()) for c in CROPS}
res['upag_years'] = sorted(upag.year.unique().tolist())
uw = upag[upag.crop_name == 'Wheat']
res['upag_wheat'] = {'rows': len(uw), 'districts': int(uw[['state_name', 'district_name']].drop_duplicates().shape[0]),
                     'null_pct': (uw[['area', 'production', 'yield']].isna().mean() * 100).round(2).to_dict(),
                     'rows_by_year': uw.groupby('year').size().to_dict(), 'seasons': uw.season.value_counts().to_dict()}
dw = new[(new.crop_name == 'Wheat')].copy()
for d in (uw, dw):
    d['st'] = d.state_name.str.lower().str.strip(); d['di'] = d.district_name.str.lower().str.strip()
j = uw.merge(dw, on=['year', 'st', 'di', 'season'], suffixes=('_upag', '_des'))
j = j[(j.area_des > 0) & (j.production_des > 0)]
res['upag_vs_des_wheat'] = {'matched_rows': len(j), 'years': sorted(j.year.unique().tolist()),
                            'area_ratio_median': round(float((j.area_upag / j.area_des).median()), 4),
                            'prod_ratio_median': round(float((j.production_upag / j.production_des).median()), 4),
                            'yield_ratio_median(kg/ha vs t/ha)': round(float((j.yield_upag / j.yield_des).median()), 2),
                            'share_prod_within_1pct_after_scaling': None}
s = (j.production_upag / j.production_des).median()
res['upag_vs_des_wheat']['share_prod_within_1pct_after_scaling'] = round(float(((j.production_upag / s - j.production_des).abs() / j.production_des < .01).mean()), 3)
(OUT / 'apy_comparison.json').write_text(json.dumps(res, indent=1, default=str)); print(json.dumps(res, indent=1, default=str))
