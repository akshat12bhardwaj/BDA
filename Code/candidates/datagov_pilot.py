"""Authorised extraction pilot (Data_Source_Review.md §5.6): 30 crop-days in 2024-02-03 .. 2026-10-20, each fetched
twice with the single-call method (limit 5000, offset 0), plus state partitions of three crop-days.

Record identity: canonical JSON of every field as returned (`rid`), so comparisons never depend on row order.
A response is accepted only if count == API total == distinct records and total < limit (`single_call_ok`).
Retry policy: at most 3 attempts per request (waits 5 s, 15 s) on transport failure, HTTP 5xx or a non-JSON body;
the run stops at once on HTTP 401/403/429 or a rate-limit/key message. Every attempt counts against the budget,
and a partition is started only if the remaining budget covers all its states.

Usage (repo root): python -m Code.candidates.datagov_pilot [--budget 160] [--plan-only]
Raw responses (key redacted): Dataset_Candidates/datagov_pilot/<run>/; log and summary: Processed_Data/candidates/datagov_pilot/.
Exit codes: 0 every crop-day and partition passes, 1 a check failed, 2 no key, 3 stopped (access, rate limit or budget)."""
import argparse, csv, json, sys, time
from collections import Counter
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from Code.candidates.datagov_key_check import BASE, SOURCE_FLAGS, load_key, record_problems
from Code.candidates.datagov_partition_check import LIMIT, api_get, compare_partitions, rid, single_call_ok

START, END = date(2024, 2, 3), date(2026, 10, 20)
CROPS = ['Onion', 'Potato', 'Wheat']
# High-volume days from evidence: Onion 2025-06-18 had the largest API total seen (829, §5.5); existing 2022-23 data
# peaks Mon-Fri, Onion/Potato slightly in Feb/Jun, Wheat in April (procurement). Mondays in those months.
HIGH = {'Onion': ['2024-06-17', '2025-06-18'], 'Potato': ['2025-02-17', '2026-02-16'], 'Wheat': ['2024-04-15', '2025-04-21']}
PARTITION = {'Onion': '2025-06-18', 'Potato': '2026-02-16', 'Wheat': '2025-04-21'}
WAITS = (5, 15)


def select_dates():
    """10 crop-days per crop: 8 evenly spread over the window (staggered by crop so no two crops share a spread
    date) plus 2 high-volume days. Deterministic."""
    span = (END - START).days
    out = []
    for i, crop in enumerate(CROPS):
        for k in range(8):
            out.append((crop, (START + timedelta(days=round(k * span / 7) - (i if k else -i))).isoformat(), 'spread'))
        out += [(crop, d, 'high_volume') for d in HIGH[crop]]
    return out


def classify(code, body):
    """'ok', 'retry' or 'stop' for one raw response."""
    if code in ('401', '403', '429'):
        return 'stop'
    try:
        j = json.loads(body)
    except ValueError:
        return 'retry'
    msg = str(j.get('message', '')).lower()
    if any(w in msg for w in ('rate', 'limit exceeded', 'invalid key', 'api key', 'forbidden', 'quota')):
        return 'stop'
    if code == 'none' or code.startswith('5'):
        return 'retry'
    return 'ok' if code == '200' and isinstance(j.get('records'), list) else 'stop'


def crop_day_result(crop, d, fetches):
    """fetches: list of parsed responses (dicts) for one crop-day. Pure."""
    api_date = datetime.strptime(d, '%Y-%m-%d').strftime('%d/%m/%Y')
    checks = [single_call_ok(j) for j in fetches]
    sets = [{rid(r) for r in j['records']} for j in fetches]
    probs = Counter(p for r in fetches[0]['records'] for p in record_problems(r, crop, api_date))
    malformed = {k: v for k, v in probs.items() if k not in SOURCE_FLAGS}
    return {'commodity': crop, 'date': d, 'api_totals': [c['total'] for c in checks], 'returned': [c['count'] for c in checks],
            'distinct': [c['distinct'] for c in checks], 'duplicates': [c['count'] - c['distinct'] for c in checks],
            'repeat_sets_identical': len(sets) == 2 and sets[0] == sets[1],
            'source_flags': {k: v for k, v in probs.items() if k in SOURCE_FLAGS}, 'malformed': malformed,
            'pass': len(checks) == 2 and all(c['ok'] for c in checks) and sets[0] == sets[1] and not malformed}


def main():
    ap = argparse.ArgumentParser(); ap.add_argument('--budget', type=int, default=160); ap.add_argument('--plan-only', action='store_true')
    a = ap.parse_args()
    root = Path.cwd()
    import pandas as pd
    hist_states = {}
    for crop in CROPS:
        o = pd.read_parquet(root / f'Processed_Data/cleaned/mandi_cleaned_{crop.lower()}.parquet', columns=['state', 'reported_date'])
        hist_states[crop] = set(o.loc[o.reported_date >= '2020-01-01', 'state'].astype(str).unique())
    plan = select_dates()
    est = 2 * len(plan) + sum(len(hist_states[c]) for c in PARTITION)
    print(json.dumps({'crop_days': plan, 'partition_days': PARTITION,
                      'estimated_calls_before_new_state_names': est}, indent=1))
    if a.plan_only:
        return 0
    key = load_key(root)
    if not key:
        print('No key: set DATAGOV_API_KEY or write it to .secrets/datagov_api_key (git-ignored). Not run.'); return 2

    run = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    raw = root / 'Dataset_Candidates' / 'datagov_pilot' / run; raw.mkdir(parents=True)
    out = root / 'Processed_Data' / 'candidates' / 'datagov_pilot'; out.mkdir(parents=True, exist_ok=True)
    log = {'run': run, 'retrieved_utc': run, 'source_url': BASE, 'limit': LIMIT, 'offset': 0, 'sort': 'none',
           'record_identity': 'canonical JSON (sorted keys) of all returned fields', 'budget': a.budget,
           'retry_policy': {'max_attempts': 1 + len(WAITS), 'waits_s': WAITS, 'stop_on': '401/403/429 or rate/key message'},
           'requests': [], 'crop_days': [], 'partitions': []}
    n = 0

    class Stop(Exception):
        pass

    def fetch(tag, **filters):
        nonlocal n
        for attempt, wait in enumerate((0,) + WAITS, 1):
            if n >= a.budget:
                raise Stop('request budget exhausted')
            time.sleep(wait or 0.8)
            n += 1
            code, body, secs = api_get(key, filters)
            (raw / f'{n:03d}_{tag}_a{attempt}.json').write_bytes(body)
            verdict = classify(code, body)
            log['requests'].append({'n': n, 'tag': tag, 'filters': filters, 'attempt': attempt, 'http': code,
                                    'seconds': secs, 'bytes': len(body), 'outcome': verdict})
            if verdict == 'ok':
                return json.loads(body)
            if verdict == 'stop':
                raise Stop(f'access restricted or rate limited at request {n} (HTTP {code})')
        raise Stop(f'{tag}: failed after {1 + len(WAITS)} attempts')

    def finish(code, verdict):
        log.update({'verdict': verdict, 'exit_code': code, 'calls_used': n,
                    'crop_days_passed': sum(c['pass'] for c in log['crop_days']), 'crop_days_run': len(log['crop_days'])})
        (out / f'{run}.json').write_text(json.dumps(log, indent=1, default=str))
        with open(out / f'{run}_crop_days.csv', 'w', newline='') as fh:
            w = csv.writer(fh); w.writerow(['commodity', 'date', 'api_total', 'returned', 'distinct', 'duplicates', 'repeat_identical', 'source_flags', 'malformed', 'pass'])
            for c in log['crop_days']:
                w.writerow([c['commodity'], c['date'], c['api_totals'], c['returned'], c['distinct'], c['duplicates'],
                            c['repeat_sets_identical'], json.dumps(c['source_flags']), json.dumps(c['malformed']), c['pass']])
        print(json.dumps({k: v for k, v in log.items() if k not in ('requests', 'crop_days')}, indent=1, default=str))
        print('log:', out / f'{run}.json')
        return code

    first = {}
    try:
        for crop, d, why in plan:
            api_date = datetime.strptime(d, '%Y-%m-%d').strftime('%d/%m/%Y')
            fs = [fetch(f'{crop}_{d}_f{i}', Commodity=crop, Arrival_Date=api_date) for i in (1, 2)]
            res = crop_day_result(crop, d, fs); res['selection'] = why
            log['crop_days'].append(res); first[(crop, d)] = fs[0]['records']
        for crop, d in PARTITION.items():
            coarse = first[(crop, d)]
            states = sorted({r['State'] for r in coarse} | hist_states[crop])
            if a.budget - n < len(states):
                log['partitions'].append({'commodity': crop, 'date': d, 'skipped': f'needs {len(states)} calls, {a.budget - n} left'})
                continue
            api_date = datetime.strptime(d, '%Y-%m-%d').strftime('%d/%m/%Y')
            parts, part_ok = {}, True
            for s in states:
                j = fetch(f'{crop}_{d}_state_{s}'.replace(' ', '_'), Commodity=crop, State=s, Arrival_Date=api_date)
                parts[s] = (int(j.get('total') or 0), j['records']); part_ok &= single_call_ok(j)['ok']
            log['partitions'].append({'commodity': crop, 'date': d, 'states_queried': len(states),
                                      'states_nonempty': sum(1 for t, _ in parts.values() if t),
                                      'all_state_calls_ok': part_ok, **compare_partitions(coarse, parts)})
    except Stop as e:
        return finish(3, f'stopped: {e}')

    ok = all(c['pass'] for c in log['crop_days']) and all(p.get('equal') and p.get('all_state_calls_ok') for p in log['partitions'])
    return finish(0 if ok else 1, 'pilot checks pass' if ok else 'a check failed or a partition was skipped')


if __name__ == '__main__':
    sys.exit(main())
