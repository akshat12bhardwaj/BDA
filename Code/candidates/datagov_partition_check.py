"""Bounded experiments on extracting complete, unique records from the data.gov.in variety-wise price API
without offset paging (offset paging was shown unstable: Data_Source_Review.md §5.5).

Method under test: fetch each partition in ONE call with limit well above its total, and accept it only if
count == total, every record is distinct and total < limit. Completeness is then cross-checked, not assumed:
repeated calls must return the same set, and finer partitions (state, then market) must union to exactly the
coarse set with no overlap and with partition totals summing to the coarse total.

Usage (repo root): python Code/candidates/datagov_partition_check.py [--budget 70]
Key: env DATAGOV_API_KEY or .secrets/datagov_api_key (never printed or stored; redacted from saved responses).
Raw responses: Dataset_Candidates/datagov_partition_check/<run>/; log: Processed_Data/candidates/datagov_partition_check/<run>.json.
Exit codes: 0 all checks pass, 1 a check failed, 2 no key, 3 access restricted or budget exhausted."""
import argparse, json, subprocess, sys, time, urllib.parse
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from Code.candidates.datagov_key_check import BASE, KEY_FIELDS, load_key, record_problems, SOURCE_FLAGS

LIMIT = 5000  # far above any commodity-day total seen (max 829); a single-call partition must have total < LIMIT


def rid(r):
    """Full-record identity (all fields, canonical JSON)."""
    return json.dumps(r, sort_keys=True)


def single_call_ok(resp, limit=LIMIT):
    """Accept a one-call partition only if nothing can be missing or repeated."""
    recs = resp.get('records') or []
    total = int(resp.get('total') or 0)
    distinct = len({rid(r) for r in recs})
    return {'total': total, 'count': len(recs), 'distinct': distinct,
            'ok': len(recs) == total == distinct and total < limit}


def compare_partitions(coarse, parts):
    """coarse: records of the whole set; parts: {name: (api_total, records)}. Pure."""
    c = {rid(r) for r in coarse}
    seen, overlap = Counter(), 0
    for _, recs in parts.values():
        ids = {rid(r) for r in recs}
        overlap += sum(1 for i in ids if seen[i]); seen.update(ids)
    u = set(seen)
    return {'coarse': len(c), 'union': len(u), 'sum_part_totals': sum(t for t, _ in parts.values()),
            'missing_from_parts': len(c - u), 'extra_in_parts': len(u - c), 'overlap_between_parts': overlap,
            'equal': u == c and overlap == 0 and sum(t for t, _ in parts.values()) == len(c)}


def api_get(key, filters, limit=LIMIT):
    """One single-call request (offset 0). Returns (http_code, body with the key redacted, seconds)."""
    q = urllib.parse.urlencode({'api-key': key, 'format': 'json', 'limit': limit, 'offset': 0,
                                **{f'filters[{k}]': v for k, v in filters.items()}}, safe='/')
    t = time.monotonic()
    # curl, not urllib: the endpoint stalls on Python-urllib's User-Agent
    r = subprocess.run(['curl', '-s', '-m', '180', '-w', '\n%{http_code}', f'{BASE}?{q}'], capture_output=True)
    body, _, code = r.stdout.rpartition(b'\n')
    return code.decode() or 'none', body.replace(key.encode(), b'<redacted>'), round(time.monotonic() - t, 2)


def main():
    ap = argparse.ArgumentParser(); ap.add_argument('--budget', type=int, default=70)
    a = ap.parse_args()
    root = Path.cwd(); key = load_key(root)
    if not key:
        print('No key: set DATAGOV_API_KEY or write it to .secrets/datagov_api_key (git-ignored). Not run.'); return 2
    run = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    raw = root / 'Dataset_Candidates' / 'datagov_partition_check' / run; raw.mkdir(parents=True)
    log = {'run': run, 'retrieved_utc': run, 'source_url': BASE, 'limit': LIMIT, 'offset': 0, 'sort': 'none (no documented ordering parameter)',
           'budget': a.budget, 'calls': [], 'experiments': {}}
    n = 0

    def fetch(tag, **filters):
        nonlocal n
        if n >= a.budget:
            raise RuntimeError('request budget exhausted')
        n += 1
        code, body, _ = api_get(key, filters)
        (raw / f'{n:03d}_{tag}.json').write_bytes(body)
        time.sleep(0.8)
        try:
            j = json.loads(body)
        except ValueError:
            j = {}
        chk = single_call_ok(j) if isinstance(j.get('records'), list) else {'ok': False, 'error': 'malformed or refused'}
        log['calls'].append({'n': n, 'tag': tag, 'filters': filters, 'http': code, **chk})
        if 'error' in chk:
            raise RuntimeError(f'call {n} ({tag}): HTTP {code} {j.get("message", "")}')
        return j

    def finish(code, verdict):
        log.update({'verdict': verdict, 'exit_code': code, 'calls_used': n})
        out = root / 'Processed_Data' / 'candidates' / 'datagov_partition_check'; out.mkdir(parents=True, exist_ok=True)
        (out / f'{run}.json').write_text(json.dumps(log, indent=1, default=str))
        print(json.dumps({k: v for k, v in log.items() if k != 'calls'}, indent=1, default=str)); print('log:', out / f'{run}.json')
        return code

    try:
        import pandas as pd
        ex = log['experiments']
        # X0 server cap on records per call: an unfiltered commodity query has millions of rows
        cap = fetch('cap_onion_all', Commodity='Onion')
        ex['X0_cap'] = {'requested_limit': LIMIT, 'returned': len(cap.get('records') or []), 'total': cap.get('total')}

        # X1 commodity-day in one call, three times
        day = {'Commodity': 'Onion', 'Arrival_Date': '17/01/2024'}
        reps = [fetch(f'onion_day_rep{i}', **day) for i in range(3)]
        sets = [{rid(r) for r in j['records']} for j in reps]
        coarse = reps[0]['records']
        ex['X1_commodity_day'] = {'calls': [single_call_ok(j) for j in reps], 'repeats_set_equal': all(s == sets[0] for s in sets)}

        # X2 state partition: states from the coarse set plus every state the existing data ever reported for Onion,
        # so a state silently absent from the coarse call would still be queried
        ours = pd.read_parquet(root / 'Processed_Data/cleaned/mandi_cleaned_onion.parquet', columns=['state', 'market', 'variety', 'modal_price_rs_per_quintal', 'reported_date'])
        states = sorted({r['State'] for r in coarse} | set(ours.state.astype(str).unique()))
        parts = {}
        for s in states:
            j = fetch(f'state_{s}'.replace(' ', '_'), State=s, **day)
            parts[s] = (int(j.get('total') or 0), j['records'])
        ex['X2_state_partition'] = {'states_queried': len(states), 'states_nonempty': sum(1 for t, _ in parts.values() if t),
                                    'all_single_calls_ok': all(c['ok'] for c in log['calls'] if c['tag'].startswith('state_')),
                                    **compare_partitions(coarse, parts)}

        # X3 market partition in one state with several varieties per market and the range-flagged records:
        # markets from the state call plus those the existing data has for that state on the same day
        st = 'Madhya Pradesh'
        same_day = ours[(ours.state == st) & (ours.reported_date == '2024-01-17')]
        markets = sorted({r['Market'] for r in parts[st][1]} | set(same_day.market.astype(str).unique()))
        mparts = {}
        for m in markets:
            j = fetch(f'market_{st}_{m}'.replace(' ', '_').replace('/', '-'), State=st, Market=m, **day)
            mparts[m] = (int(j.get('total') or 0), j['records'])
        ex['X3_market_partition'] = {'state': st, 'markets_queried': len(markets), **compare_partitions(parts[st][1], mparts)}

        # X4 other crops/days: one call twice each; overlap with existing data where it exists (≤ 2024-02-02)
        first = {'Onion': coarse}
        for crop, d in [('Potato', '17/01/2024'), ('Wheat', '17/01/2024'), ('Onion', '18/06/2025')]:
            js = [fetch(f'{crop}_{d.replace("/", "-")}_rep{i}', Commodity=crop, Arrival_Date=d) for i in range(2)]
            ex[f'X4_{crop}_{d}'] = {'calls': [single_call_ok(j) for j in js],
                                    'repeats_set_equal': {rid(r) for r in js[0]['records']} == {rid(r) for r in js[1]['records']}}
            first.setdefault(crop, js[0]['records'])

        # Price agreement and value flags for the 2024 coarse sets against the existing cleaned data
        for crop, recs in first.items():
            o = ours if crop == 'Onion' else pd.read_parquet(root / f'Processed_Data/cleaned/mandi_cleaned_{crop.lower()}.parquet', columns=ours.columns.tolist())
            o = o[o.reported_date == '2024-01-17']
            api = pd.DataFrame(recs); api['modal'] = pd.to_numeric(api.Modal_Price, errors='coerce')
            mm = api.merge(o, left_on=['State', 'Market', 'Variety'], right_on=['state', 'market', 'variety'])
            flags = Counter(p for r in recs for p in record_problems(r, crop, '17/01/2024'))
            ex[f'agreement_{crop}_2024-01-17'] = {'api_records': len(api), 'existing_rows': len(o), 'matched_pairs': len(mm),
                                                  'modal_equal_share': round(float((mm.modal == mm.modal_price_rs_per_quintal).mean()), 4) if len(mm) else None,
                                                  'source_flags': {k: v for k, v in flags.items() if k in SOURCE_FLAGS},
                                                  'malformed': {k: v for k, v in flags.items() if k not in SOURCE_FLAGS}}
    except RuntimeError as e:
        return finish(3, f'stopped: {e}')

    ok = (all(c['ok'] for c in log['calls'] if not c['tag'].startswith('cap_'))
          and ex['X1_commodity_day']['repeats_set_equal'] and ex['X2_state_partition']['equal'] and ex['X3_market_partition']['equal']
          and all(v['repeats_set_equal'] for k, v in ex.items() if k.startswith('X4_')))
    return finish(0 if ok else 1, 'all checks pass' if ok else 'a check failed (see experiments)')


if __name__ == '__main__':
    sys.exit(main())
