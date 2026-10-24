"""Bounded live check of a personal data.gov.in API key on the variety-wise mandi price resource.

Reads the key from env DATAGOV_API_KEY or the git-ignored file .secrets/datagov_api_key; never prints or stores it.
Pages one commodity-day (default Onion, 17/01/2024: inside the existing data, ~556 records) and checks:
effective page size, duplicates across pages, repeated-page stability, gaps (distinct < total), malformed records,
dates/crop/market/modal-price validity, and modal-price agreement with the existing cleaned mandi data.

Usage (from the repo root): python Code/candidates/datagov_key_check.py [--commodity Onion] [--date 17/01/2024] [--budget 80]
Exit codes: 0 pass, 1 validation failed, 2 no key supplied, 3 access restricted or API unusable.
Raw responses (key redacted) go to Dataset_Candidates/datagov_key_check/<run>/, the run log to
Processed_Data/candidates/datagov_key_check/<run>.json."""
import argparse, hashlib, json, os, subprocess, sys, time, urllib.parse
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

RES = '35985678-0d79-46b4-9ed6-6f13308a1d24'
BASE = f'https://api.data.gov.in/resource/{RES}'
FIELDS = ['Arrival_Date', 'Commodity', 'Commodity_Code', 'District', 'Grade', 'Market', 'Max_Price', 'Min_Price', 'Modal_Price', 'State', 'Variety']
KEY_FIELDS = ['State', 'District', 'Market', 'Commodity', 'Variety', 'Grade', 'Arrival_Date']
# sha256 of the documented public sample key, so a run can say which kind of key it used without revealing it
SAMPLE_KEY_SHA = '149027a69a838520183f92d985e79c28ca979b79c4b7fa94a22230d819fe08a0'
# Value-level issues published as-is by the source (identical in the existing data, flagged there by Phase 5):
# reported, never a reason to reject retrieval
SOURCE_FLAGS = {'modal outside [min, max]', 'modal <= 0'}


def load_key(root):
    key = os.environ.get('DATAGOV_API_KEY', '').strip()
    f = root / '.secrets' / 'datagov_api_key'
    if not key and f.exists():
        key = f.read_text().strip()
    return key or None


def record_problems(r, commodity, date):
    """List what is wrong with one API record (empty list = valid)."""
    p = [f'missing {k}' for k in FIELDS if k not in r]
    if p:
        return p
    if r['Arrival_Date'] != date:
        p.append(f"date {r['Arrival_Date']} != {date}")
    if r['Commodity'] != commodity:
        p.append(f"commodity {r['Commodity']}")
    if not str(r['Market']).strip() or not str(r['State']).strip():
        p.append('empty market/state')
    try:
        lo, hi, mo = (float(r[k]) for k in ('Min_Price', 'Max_Price', 'Modal_Price'))
        if mo <= 0:
            p.append('modal <= 0')
        elif not lo <= mo <= hi:
            p.append('modal outside [min, max]')
    except (TypeError, ValueError):
        p.append('non-numeric price')
    return p


def check_pages(pages, total, page_size, commodity, date):
    """Pure validation of a list of fetched pages (each a list of records). Returns a results dict."""
    recs = [r for pg in pages for r in pg]
    full = Counter(json.dumps(r, sort_keys=True) for r in recs)
    keys = Counter(tuple(str(r.get(k)) for k in KEY_FIELDS) for r in recs)
    short = [i for i, pg in enumerate(pages[:-1]) if len(pg) != page_size]
    bad = {}
    for r in recs:
        for prob in record_problems(r, commodity, date):
            bad[prob] = bad.get(prob, 0) + 1
    distinct = len(full)
    flags = {k: bad.pop(k) for k in SOURCE_FLAGS if k in bad}
    return {'retrieved': len(recs), 'distinct_records': distinct, 'api_total': total,
            'duplicate_rows': len(recs) - distinct,
            'key_conflicts': sum(1 for k, n in keys.items() if n > 1) - sum(1 for n in full.values() if n > 1),
            'gap_records': max(total - distinct, 0), 'short_non_final_pages': short,
            'malformed': bad, 'source_flags': flags, 'complete_and_unique': distinct == total == len(recs) and not bad}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--commodity', default='Onion'); ap.add_argument('--date', default='17/01/2024')
    ap.add_argument('--budget', type=int, default=80, help='maximum API calls')
    a = ap.parse_args()
    root = Path.cwd()
    key = load_key(root)
    if not key:
        print('No key: set DATAGOV_API_KEY or write it to .secrets/datagov_api_key (git-ignored). Live test not run.')
        return 2
    run = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    raw = root / 'Dataset_Candidates' / 'datagov_key_check' / run; raw.mkdir(parents=True)
    log = {'run': run, 'retrieved_utc': run, 'source_url': BASE, 'resource': RES,
           'key_kind': 'public_sample' if hashlib.sha256(key.encode()).hexdigest() == SAMPLE_KEY_SHA else 'personal',
           'filters': {'Commodity': a.commodity, 'Arrival_Date': a.date}, 'budget': a.budget, 'calls': []}
    calls = 0

    def get(limit, offset, tag):
        nonlocal calls
        if calls >= a.budget:
            raise RuntimeError('request budget exhausted')
        calls += 1
        q = urllib.parse.urlencode({'api-key': key, 'format': 'json', 'limit': limit, 'offset': offset,
                                    'filters[Commodity]': a.commodity, 'filters[Arrival_Date]': a.date}, safe='/')
        # curl, not urllib: the endpoint stalls on Python-urllib's User-Agent (Data_Source_Review.md §4)
        r = subprocess.run(['curl', '-s', '-m', '90', '-w', '\n%{http_code}', f'{BASE}?{q}'], capture_output=True)
        body, _, code = r.stdout.rpartition(b'\n')
        body = body.replace(key.encode(), b'<redacted>')
        (raw / f'{calls:03d}_{tag}_l{limit}_o{offset}.json').write_bytes(body)
        entry = {'n': calls, 'tag': tag, 'limit': limit, 'offset': offset, 'http': code.decode() or 'none'}
        log['calls'].append(entry)
        time.sleep(0.8)
        try:
            j = json.loads(body)
        except ValueError:
            entry['error'] = 'non-JSON response'; return None
        entry.update({'count': j.get('count'), 'total': j.get('total'), 'status': j.get('status'), 'message': j.get('message')})
        return j if isinstance(j.get('records'), list) else None

    def finish(code, verdict):
        log.update({'verdict': verdict, 'exit_code': code, 'calls_used': calls})
        out = root / 'Processed_Data' / 'candidates' / 'datagov_key_check'; out.mkdir(parents=True, exist_ok=True)
        (out / f'{run}.json').write_text(json.dumps(log, indent=1, default=str))
        print(json.dumps({k: v for k, v in log.items() if k != 'calls'}, indent=1, default=str))
        print('log:', out / f'{run}.json')
        return code

    # 1) access + effective page size
    j = get(1000, 0, 'probe')
    if j is None:
        return finish(3, f"access restricted or unusable: {log['calls'][-1]}")
    total, page = int(j.get('total') or 0), len(j['records'])
    log['effective_page_size'] = page
    if total == 0 or page == 0:
        return finish(3, 'no records returned for the filter')
    page_size = min(page, 100)  # keep several pages even if the key allows large pages
    needed = -(-total // page_size) + 2
    if needed > a.budget - calls:
        return finish(3, f'budget too small: {needed} calls needed for {total} records at page size {page_size}')

    # 2) full pagination, then two repeated pages for stability
    pages = []
    for off in range(0, total, page_size):
        pj = get(page_size, off, 'page')
        if pj is None:
            return finish(3, f'malformed or failed page at offset {off}')
        pages.append(pj['records'])
    mid = (len(pages) // 2) * page_size
    rep = [get(page_size, 0, 'repeat'), get(page_size, mid, 'repeat')]
    log['repeat_pages_identical'] = [r is not None and r['records'] == pages[o // page_size] for r, o in zip(rep, (0, mid))]
    res = check_pages(pages, total, page_size, a.commodity, a.date)
    log['pagination'] = res

    # 3) overlap with existing data (modal price on state + market + variety + date)
    try:
        import pandas as pd
        crop = a.commodity.lower()
        d = pd.to_datetime(a.date, format='%d/%m/%Y')
        ours = pd.read_parquet(root / f'Processed_Data/cleaned/mandi_cleaned_{crop}.parquet',
                               columns=['state', 'market', 'variety', 'modal_price_rs_per_quintal', 'reported_date'])
        ours = ours[ours.reported_date == d]
        api = pd.DataFrame([r for pg in pages for r in pg]).drop_duplicates()
        api['modal'] = pd.to_numeric(api.Modal_Price, errors='coerce')
        m = api.merge(ours, left_on=['State', 'Market', 'Variety'], right_on=['state', 'market', 'variety'])
        log['existing_overlap'] = {'existing_rows_that_day': len(ours), 'api_distinct_rows': len(api), 'matched_pairs': len(m),
                                   'modal_equal_share': round(float((m.modal == m.modal_price_rs_per_quintal).mean()), 4) if len(m) else None}
    except FileNotFoundError:
        log['existing_overlap'] = 'existing cleaned parquet not present (fresh clone)'

    ok = res['complete_and_unique'] and all(log['repeat_pages_identical'])
    return finish(0 if ok else 1, 'pass' if ok else 'pagination or content not reliable')


if __name__ == '__main__':
    sys.exit(main())
