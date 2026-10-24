"""Resumable, staged extraction of data.gov.in variety-wise daily prices (Data_Source_Review.md §6.1).

One request per crop-day (limit 5000, offset 0, no sort), fetched twice; a crop-day passes only if both fetches have
count == API total == distinct records, total < limit, identical record sets and no malformed records.
Record identity: canonical JSON of all returned fields (`rid`); content hash = SHA-256 of the sorted identities.

Stages are fixed below; only an approved stage may be run. Re-running a stage is idempotent: a crop-day already
`pass` in the manifest is skipped if its parameters match and both raw files re-hash to the recorded content hash;
otherwise it is fetched again. A crop-day that fails validation stops the run; it is retried on a later run, and is
`blocked` (needs a manual decision) after MAX_FAILS failed runs. Zero-record days are recorded as `zero_review`.

Usage (repo root): python -m Code.candidates.datagov_extract S1 [--dry-run]
Raw (key redacted, atomic writes): Dataset_Candidates/datagov_prices/raw/<crop>/<date>_f{1,2}.json
Manifest, request log, stage reports: Processed_Data/candidates/datagov_prices/
Exit codes: 0 stage accepted, 1 a check failed, 2 no key, 3 stopped (access, rate limit, budget)."""
import argparse, csv, hashlib, json, os, shutil, sys, time
from collections import Counter
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from Code.candidates.datagov_key_check import BASE, SOURCE_FLAGS, load_key, record_problems
from Code.candidates.datagov_partition_check import LIMIT, api_get, compare_partitions, rid, single_call_ok
from Code.candidates.datagov_pilot import WAITS, classify, crop_day_result

CROPS = ['Onion', 'Potato', 'Wheat']
# Only approved stages appear here. 'crop_days' is the approved count, checked before any request.
# S1 approved 2026-10-24: budget 600 = 528 fetches + 1 state partition + retries.
# S2 approved 2026-10-24: ~3,510 calls = 3,330 fetches + one state partition per calendar quarter touched
# (mid-quarter Wednesdays, crops rotating; ~181 state calls); budget 3,600 leaves headroom for transient retries.
STAGES = {
    'S1': {'start': '2024-02-03', 'end': '2024-04-30', 'crop_days': 264, 'budget': 600, 'partitions': [('Wheat', '2024-04-15')]},
    'S2': {'start': '2024-05-01', 'end': '2025-11-06', 'crop_days': 1665, 'budget': 3600,
           'partitions': [('Onion', '2024-06-12'), ('Potato', '2024-08-14'), ('Wheat', '2024-11-13'), ('Onion', '2025-02-12'),
                          ('Wheat', '2025-04-16'), ('Potato', '2025-08-13'), ('Onion', '2025-10-15')]},
    # S3 approved 2026-10-24 (post-relaunch): ~2,210 calls = 2,088 fetches + one state partition per calendar quarter
    # touched (~121 state calls); budget 2,300.
    'S3': {'start': '2025-11-07', 'end': '2026-10-20', 'crop_days': 1044, 'budget': 2300,
           'partitions': [('Wheat', '2025-12-10'), ('Onion', '2026-02-11'), ('Wheat', '2026-04-15'), ('Potato', '2026-08-12'),
                          ('Onion', '2026-10-14')]},
}
MAX_FAILS = 3
RAW = Path('Dataset_Candidates/datagov_prices/raw')
OUT = Path('Processed_Data/candidates/datagov_prices')
MANIFEST_COLS = ['commodity', 'date', 'filters', 'limit', 'offset', 'api_total', 'returned', 'distinct', 'content_sha256',
                 'retrieved_utc', 'status', 'fail_count', 'source_flags', 'malformed', 'detail']


class Stop(Exception):
    pass


def stage_days(start, end):
    d, e = date.fromisoformat(start), date.fromisoformat(end)
    return [(d + timedelta(days=i)).isoformat() for i in range((e - d).days + 1)]


def api_date(d):
    return datetime.strptime(d, '%Y-%m-%d').strftime('%d/%m/%Y')


def params(crop, d):
    return json.dumps({'Commodity': crop, 'Arrival_Date': api_date(d)}, sort_keys=True)


def content_hash(records):
    return hashlib.sha256('\n'.join(sorted(rid(r) for r in records)).encode()).hexdigest()


def atomic_write(path, data: bytes):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + '.tmp')
    tmp.write_bytes(data)
    os.replace(tmp, path)


def raw_paths(raw, crop, d):
    return [raw / crop / f'{d}_f{i}.json' for i in (1, 2)]


def can_resume(row, crop, d, raw):
    """A manifest row is reusable only if it passed, its parameters match, and both raw files re-hash to it."""
    if not row or row['status'] not in ('pass', 'zero_review') or row['filters'] != params(crop, d) or int(row['limit']) != LIMIT:
        return False
    try:
        return all(content_hash(json.loads(p.read_bytes())['records']) == row['content_sha256'] for p in raw_paths(raw, crop, d))
    except (OSError, ValueError, KeyError):
        return False


def read_manifest(path):
    return {(r['commodity'], r['date']): r for r in csv.DictReader(open(path, newline=''))} if path.exists() else {}


def write_manifest(path, rows):
    body = [MANIFEST_COLS] + [[r.get(c, '') for c in MANIFEST_COLS] for _, r in sorted(rows.items(), key=lambda kv: (kv[0][1], kv[0][0]))]
    tmp = path.with_suffix('.tmp')
    with open(tmp, 'w', newline='') as fh:
        csv.writer(fh, lineterminator='\n').writerows(body)
    os.replace(tmp, path)


def main():
    ap = argparse.ArgumentParser(); ap.add_argument('stage', choices=sorted(STAGES)); ap.add_argument('--dry-run', action='store_true')
    a = ap.parse_args()
    root = Path.cwd(); st = STAGES[a.stage]
    raw, out = root / RAW, root / OUT; out.mkdir(parents=True, exist_ok=True)
    days = stage_days(st['start'], st['end'])
    if len(days) * len(CROPS) != st['crop_days'] or any(not st['start'] <= d <= st['end'] for _, d in st['partitions']):
        print(f'stage {a.stage} definition inconsistent: {len(days) * len(CROPS)} crop-days vs approved {st["crop_days"]}'); return 1
    man_path = out / 'crop_day_manifest.csv'
    man = read_manifest(man_path)
    todo = [(c, d) for d in days for c in CROPS if not can_resume(man.get((c, d)), c, d, raw)]
    blocked = [k for k in todo if man.get(k, {}).get('status') == 'blocked']
    need = 2 * (len(todo) - len(blocked)) + 40 * len(st['partitions'])
    free_gb = shutil.disk_usage(root).free / 1e9
    print(json.dumps({'stage': a.stage, 'days': len(days), 'crop_days': 3 * len(days), 'to_fetch': len(todo) - len(blocked),
                      'blocked': blocked, 'expected_calls_max': need, 'budget': st['budget'], 'free_disk_gb': round(free_gb, 1)}, indent=1))
    if a.dry_run:
        return 0
    key = load_key(root)
    if not key:
        print('No key: set DATAGOV_API_KEY or write it to .secrets/datagov_api_key (git-ignored). Not run.'); return 2

    run = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    req_path = out / 'requests.csv'
    new_log = not req_path.exists()
    req_fh = open(req_path, 'a', newline=''); req = csv.writer(req_fh, lineterminator='\n')
    if new_log:
        req.writerow(['run', 'stage', 'n', 'tag', 'filters', 'limit', 'offset', 'attempt', 'http', 'seconds', 'bytes', 'outcome', 'utc'])
    n = 0

    def fetch(tag, filters):
        nonlocal n
        for attempt, wait in enumerate((0,) + WAITS, 1):
            if n >= st['budget']:
                raise Stop('stage request budget exhausted')
            time.sleep(wait or 0.8)
            n += 1
            code, body, secs = api_get(key, filters)
            verdict = classify(code, body)
            req.writerow([run, a.stage, n, tag, json.dumps(filters, sort_keys=True), LIMIT, 0, attempt, code, secs, len(body),
                          verdict, datetime.now(timezone.utc).isoformat(timespec='seconds')]); req_fh.flush()
            if verdict == 'ok':
                return body
            if verdict == 'stop':
                raise Stop(f'access restricted or rate limited at request {n} (HTTP {code})')
        raise Stop(f'{tag}: transient failure persisted after {1 + len(WAITS)} attempts')

    status, report = 0, {'run': run, 'stage': a.stage, 'source_url': BASE, 'limit': LIMIT, 'offset': 0, 'sort': 'none',
                         'record_identity': 'canonical JSON (sorted keys) of all returned fields', 'partitions': []}
    try:
        for crop, d in todo:
            row = man.get((crop, d), {})
            if row.get('status') == 'blocked':
                continue
            f = json.loads(params(crop, d))
            bodies = [fetch(f'{crop}_{d}_f{i}', f) for i in (1, 2)]
            js = [json.loads(b) for b in bodies]
            res = crop_day_result(crop, d, js)
            ok = res['pass']
            fails = int(row.get('fail_count') or 0) + (0 if ok else 1)
            if ok:
                for p, b in zip(raw_paths(raw, crop, d), bodies):
                    atomic_write(p, b)
            man[(crop, d)] = {'commodity': crop, 'date': d, 'filters': params(crop, d), 'limit': LIMIT, 'offset': 0,
                              'api_total': res['api_totals'][0], 'returned': res['returned'][0], 'distinct': res['distinct'][0],
                              'content_sha256': content_hash(js[0]['records']) if ok else '',
                              'retrieved_utc': datetime.now(timezone.utc).isoformat(timespec='seconds'),
                              'status': ('zero_review' if res['api_totals'][0] == 0 else 'pass') if ok else ('blocked' if fails >= MAX_FAILS else 'fail'),
                              'fail_count': fails, 'source_flags': json.dumps(res['source_flags']), 'malformed': json.dumps(res['malformed']),
                              'detail': '' if ok else json.dumps({k: res[k] for k in ('api_totals', 'returned', 'distinct', 'repeat_sets_identical')})}
            write_manifest(man_path, man)
            if not ok:
                raise Stop(f'{crop} {d} failed validation: {man[(crop, d)]["detail"]}')

        for crop, d in st['partitions']:
            coarse = json.loads(raw_paths(raw, crop, d)[0].read_bytes())['records']
            states = sorted({r['State'] for r in coarse} | _history_states(root, crop))
            if st['budget'] - n < len(states):
                raise Stop(f'partition {crop} {d} needs {len(states)} calls, {st["budget"] - n} left')
            parts, all_ok = {}, True
            for s in states:
                body = fetch(f'{crop}_{d}_state_{s}', {'Commodity': crop, 'State': s, 'Arrival_Date': api_date(d)})
                atomic_write(raw / 'partitions' / crop / d / f'{s.replace(" ", "_")}.json', body)
                j = json.loads(body)
                parts[s] = (int(j.get('total') or 0), j['records']); all_ok &= single_call_ok(j)['ok']
            report['partitions'].append({'commodity': crop, 'date': d, 'states_queried': len(states),
                                         'states_nonempty': sum(1 for t, _ in parts.values() if t), 'all_state_calls_ok': all_ok,
                                         **compare_partitions(coarse, parts)})
    except Stop as e:
        report['stopped'] = str(e); status = 3
    finally:
        req_fh.close()

    report.update(stage_summary(man, days, a.stage, n))
    parts_ok = len(report['partitions']) == len(st['partitions']) and all(p['equal'] and p['all_state_calls_ok'] for p in report['partitions'])
    # zero-record crop-days are valid responses but hold acceptance until reviewed
    report['accepted'] = report['accepted'] and parts_ok and 'stopped' not in report and not report['zero_record_crop_days']
    if status == 0 and not report['accepted']:
        status = 1
    (out / f'stage_{a.stage}_report_{run}.json').write_text(json.dumps(report, indent=1, default=str))
    print(json.dumps(report, indent=1, default=str))
    return status


def _history_states(root, crop):
    import pandas as pd
    o = pd.read_parquet(root / f'Processed_Data/cleaned/mandi_cleaned_{crop.lower()}.parquet', columns=['state', 'reported_date'])
    return set(o.loc[o.reported_date >= '2020-01-01', 'state'].astype(str).unique())


def stage_summary(man, days, stage, calls):
    """Acceptance view of one stage from the manifest. Pure apart from its inputs."""
    rows = [man.get((c, d)) for d in days for c in CROPS]
    st = Counter(r['status'] if r else 'missing' for r in rows)
    done = [r for r in rows if r and r['status'] in ('pass', 'zero_review')]
    flags = Counter()
    for r in done:
        flags.update({f"{r['commodity']}: {k}": v for k, v in json.loads(r['source_flags'] or '{}').items()})
    return {'calls_this_run': calls, 'crop_days_expected': len(rows), 'status_counts': dict(st),
            'records_by_crop': {c: sum(int(r['api_total']) for r in done if r['commodity'] == c) for c in CROPS},
            'zero_record_crop_days': [(r['commodity'], r['date']) for r in done if r['status'] == 'zero_review'],
            'source_flags': dict(flags),
            'manifest_covers_period_exactly': {(r['commodity'], r['date']) for r in done} == {(c, d) for d in days for c in CROPS},
            'accepted': st.get('pass', 0) + st.get('zero_review', 0) == len(rows)}


if __name__ == '__main__':
    sys.exit(main())
