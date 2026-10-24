"""Compare existing Open-Meteo daily weather with NASA POWER and IMD gridded data at the same points (2022).
Usage: python compare_weather.py <repo> <imd_dir> <nasa_power_dir> <out_csv>"""
import sys
from pathlib import Path
import numpy as np, pandas as pd

ROOT, IMD, NASA, OUT = (Path(a) for a in sys.argv[1:5])
PTS = {'Nashik': ('Maharashtra_Nashik', 19.99727, 73.79096), 'Ludhiana': ('Punjab_Ludhiana', 30.91204, 75.85379),
       'Agra': ('Uttar_Pradesh_Agra', 27.18333, 78.01667)}
days = pd.date_range('2022-01-01', '2022-12-31')

# IMD 0.25 deg rainfall: 135 lon (66.5..100.0) x 129 lat (6.5..38.5), float32, -999 missing; IMD 1 deg Tmax: 31x31 (lon 67.5.., lat 7.5..), 99.9 missing
rain = np.fromfile(IMD / 'rain_2022.grd', dtype='<f4').reshape(len(days), 129, 135)
tmax = np.fromfile(IMD / 'tmax_2022.grd', dtype='<f4').reshape(len(days), 31, 31)
assert rain.size == 365 * 129 * 135 and tmax.size == 365 * 31 * 31

rows = []
for name, (f, lat, lon) in PTS.items():
    om = pd.read_csv(ROOT / f'Processed_Data/weather/raw/{f}.csv', parse_dates=['date']).set_index('date').loc['2022']
    np_ = pd.read_csv(NASA / f'{name}_2015_2022.csv', skiprows=lambda i: i < 14)
    np_.index = pd.to_datetime(np_.YEAR.astype(str), format='%Y') + pd.to_timedelta(np_.DOY - 1, 'D')
    np_ = np_.loc['2022'].replace(-999, np.nan)
    i_r, j_r = round((lat - 6.5) / .25), round((lon - 66.5) / .25)
    i_t, j_t = round(lat - 7.5), round(lon - 67.5)
    imd_r = pd.Series(rain[:, i_r, j_r], days).where(lambda s: s > -998)
    imd_t = pd.Series(tmax[:, i_t, j_t], days).where(lambda s: s < 99)
    for var, a, b, label in [('rain_mm', om.rain_sum, imd_r, 'Open-Meteo vs IMD'),
                             ('rain_mm', np_.PRECTOTCORR, imd_r, 'NASA POWER vs IMD'),
                             ('rain_mm', om.rain_sum, np_.PRECTOTCORR, 'Open-Meteo vs NASA POWER'),
                             ('tmax_c', om.temperature_2m_max, imd_t, 'Open-Meteo vs IMD'),
                             ('tmax_c', np_.T2M_MAX, imd_t, 'NASA POWER vs IMD'),
                             ('tmax_c', om.temperature_2m_max, np_.T2M_MAX, 'Open-Meteo vs NASA POWER')]:
        j = pd.concat([a.rename('a'), b.rename('b')], axis=1).dropna()
        rows.append({'point': name, 'variable': var, 'pair': label, 'days': len(j),
                     'a_missing_days': int(a.reindex(days).isna().sum()), 'b_missing_days': int(b.reindex(days).isna().sum()),
                     'a_annual_or_mean': round(j.a.sum() if var == 'rain_mm' else j.a.mean(), 1),
                     'b_annual_or_mean': round(j.b.sum() if var == 'rain_mm' else j.b.mean(), 1),
                     'daily_corr': round(j.a.corr(j.b), 3), 'daily_mae': round((j.a - j.b).abs().mean(), 2),
                     'monthly_corr': round(j.resample('ME').sum().pipe(lambda m: m.a.corr(m.b)) if var == 'rain_mm'
                                           else j.resample('ME').mean().pipe(lambda m: m.a.corr(m.b)), 3)})
r = pd.DataFrame(rows); r.to_csv(OUT, index=False); print(r.to_string())
