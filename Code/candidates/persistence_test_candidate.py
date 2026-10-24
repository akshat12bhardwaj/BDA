"""D-52: the single persistence-only evaluation of exp-candidate-v1 on the reserved candidate test window (target-week
Sundays 2026-07-05 -> 2026-10-18). Prediction = y_origin (origin-week median). Nothing is trained, refitted, tuned or
selected; metrics are baselines_candidate.metrics, the split is experiment_design.assign_period, and the existing guards
(baselines_candidate.preflight, candidate_decisions.CANDIDATE_START) are reused, never edited.

Commands (repo root):
  python -m Code.candidates.persistence_test_candidate freeze    write FREEZE once (file hashes only; no record is read)
  python -m Code.candidates.persistence_test_candidate verify    pre-run checks only (no record is read, no lock is taken)
  python -m Code.candidates.persistence_test_candidate run --confirm-single-test-run D-52    the one authorised run

One-time guard (D-52 item 8): run creates LOCK with an exclusive create before the first test row is read, and refuses
whenever LOCK, DONE or RUN_DIR exists, completed or not. There is no bypass: after an interruption the window counts as
used, and recovery needs a new owner decision in the decision log, never a deleted lock.
Reads: the protocol, dataset_v1_1 manifests and model tables (rows with target weeks 2026-06-29 .. 2026-10-12 only).
Outputs: Processed_Data/candidates/datagov_prices/experiments/exp_candidate_v1/persistence_test_d52/run/."""
import hashlib, json, os, re, subprocess, sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from Code.candidates import baselines_candidate as bc, candidate_decisions as cd, experiment_design as ed

DECISION = 'D-52'
APPROVER = 'Project owner'
AUTHORISED_TEST = ('2026-07-05', '2026-10-18')                                     # target-week Sundays (D-52 item 3)
FIRST_WEEK, LAST_WEEK = (pd.Timestamp(x) - pd.Timedelta(days=6) for x in AUTHORISED_TEST)   # their Mondays
PROTOCOL_LF_SHA256 = 'a6b1240c4c4f80da15a02fea946ca5f79f07617d9ccbabb7479ebb65193ae9ee'
DECISION_LOG = Path('Documentation/Decision_Log.md')
D52_DIR = bc.EXP_DIR / 'persistence_test_d52'
FREEZE, LOCK, DONE, RUN_DIR = (D52_DIR / n for n in ('freeze_manifest.json', 'RUN_LOCK.json', 'RUN_COMPLETED.json', 'run'))
TEST_FILE = Path('Code/tests/test_persistence_test_candidate.py')
RECORDED = [bc.OUT / 'experiment_design_v1_1' / 'audit_and_design.json', bc.OUT / 'experiment_design_v1_1' / 'approval_checklist.csv',
            bc.OUT / 'decisions_v1' / 'candidate_prices_v1_contract.json']          # manifests recorded, not read by the run
COLS = bc.S + ['origin_week_start', 'origin_date', 'target_week_start', 'horizon_weeks', 'y_origin', 'y_target', 'eligible_d41']
SEED, REPS = bc.SEED, bc.REPS
GuardError = bc.GuardError


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def decision_sha(log_text):
    """SHA-256 of the LF-normalised D-52 entry, up to the next '### ' heading (rule of arrivals_final.decision_section)."""
    m = re.search(rf'^### {re.escape(DECISION)} — \[ACCEPTED.*?(?=^### |\Z)', log_text.replace('\r\n', '\n'), re.M | re.S)
    if not m:
        raise GuardError(f'{DECISION} is not recorded as ACCEPTED in {DECISION_LOG}')
    return hashlib.sha256(m.group(0).encode('utf-8')).hexdigest()


def loaded_code(root):
    code = (Path(root).resolve() / 'Code')
    files = {Path(m.__file__).resolve() for m in list(sys.modules.values()) if getattr(m, '__file__', None)}
    return sorted(f.relative_to(code.parent).as_posix() for f in files if code in f.parents)


def code_closure(root):
    """Code/ files imported by this runner, from a fresh interpreter (so test-time imports do not enter the freeze)."""
    src = ('import json, sys; import Code.candidates.persistence_test_candidate as r; '
           'print(json.dumps(r.loaded_code(".")))')
    return json.loads(subprocess.run([sys.executable, '-B', '-c', src], cwd=root, check=True, capture_output=True, text=True).stdout)


def versions():
    import pyarrow
    return {'python': sys.version.split()[0], 'numpy': np.__version__, 'pandas': pd.__version__, 'pyarrow': pyarrow.__version__}


def build_freeze(root):
    root = Path(root)
    man = json.loads((root / bc.DATASET / 'build_manifest.json').read_text())
    prior = [p.relative_to(root) for p in sorted((root / bc.OUT / 'experiments').rglob('*'))
             if p.is_file() and (root / D52_DIR) not in p.parents]
    files = [bc.PROTOCOL_FILE, bc.DATASET / 'build_manifest.json', bc.DATASET / 'contract.json', TEST_FILE] \
        + [bc.DATASET / f for f in man['outputs']] + RECORDED + prior
    proto = json.loads((root / bc.PROTOCOL_FILE).read_text())
    return {'decision': DECISION, 'approver': APPROVER, 'experiment': proto['experiment'], 'dataset_version': man['version'],
            'model': 'persistence only: prediction = y_origin; no training, refit, tuning or selection',
            'authorised_test_target_sundays': list(AUTHORISED_TEST), 'test_target_weeks': [str(FIRST_WEEK.date()), str(LAST_WEEK.date())],
            'candidate_start': cd.CANDIDATE_START, 'protocol_lf_sha256': bc.protocol_hash(root / bc.PROTOCOL_FILE),
            'decision_section_lf_sha256': decision_sha((root / DECISION_LOG).read_text(encoding='utf-8')),
            'designs': [proto['designs']['primary']] + proto['designs']['sensitivity'],
            'horizons': [proto['horizons']['primary']] + proto['horizons']['secondary'],
            'seed': SEED, 'reps': REPS, 'mape_unstable_share': bc.MAPE_UNSTABLE_SHARE,
            'files': {p.as_posix(): sha(root / p) for p in files},
            'code': {p: sha(root / p) for p in code_closure(root)}, 'versions': versions()}


def freeze(root='.'):
    root = Path(root)
    if (root / FREEZE).exists():
        raise GuardError(f'{FREEZE} already exists; the D-52 freeze is written once')
    rec = build_freeze(root)
    if rec['protocol_lf_sha256'] != PROTOCOL_LF_SHA256:
        raise GuardError(f'protocol LF hash {rec["protocol_lf_sha256"]} != frozen {PROTOCOL_LF_SHA256}')
    (root / D52_DIR).mkdir(parents=True, exist_ok=True)
    with open(root / FREEZE, 'x', encoding='utf-8', newline='\n') as fh:
        json.dump(rec, fh, indent=1, sort_keys=True)
    return rec


def verify(root='.'):
    """Every pre-run check that needs no record (D-52 item 7). Returns the freeze record and the existing preflight."""
    root = Path(root)
    if not (root / FREEZE).exists():
        raise GuardError(f'no D-52 freeze manifest at {FREEZE}')
    rec = json.loads((root / FREEZE).read_text(encoding='utf-8'))
    if decision_sha((root / DECISION_LOG).read_text(encoding='utf-8')) != rec['decision_section_lf_sha256']:
        raise GuardError(f'the {DECISION} decision-log entry changed after the freeze')
    bad = [p for p, h in {**rec['files'], **rec['code']}.items() if not (root / p).is_file() or sha(root / p) != h]
    if bad:
        raise GuardError(f'{len(bad)} frozen file(s) missing or changed: {bad[:5]}')
    if rec['protocol_lf_sha256'] != PROTOCOL_LF_SHA256 or bc.protocol_hash(root / bc.PROTOCOL_FILE) != PROTOCOL_LF_SHA256:
        raise GuardError('protocol is not the frozen exp_candidate_v1 protocol')
    if versions() != rec['versions']:
        raise GuardError(f'package versions {versions()} != frozen {rec["versions"]}')
    split = json.loads((root / bc.PROTOCOL_FILE).read_text())['split_by_target_sunday']['test']
    if tuple(split) != AUTHORISED_TEST or tuple(ed.PROPOSED_SPLIT['test']) != AUTHORISED_TEST:
        raise GuardError(f'protocol test split {split} != authorised {AUTHORISED_TEST}')
    return rec, bc.preflight(root)


def take_lock(root, freeze_sha):
    """The one-time guard: refuse if any trace of an earlier run exists, then create LOCK exclusively and flush it."""
    root = Path(root)
    if (root / DONE).exists():
        raise GuardError(f'{DECISION} already completed ({DONE}); the test window is used and a second run is refused')
    if (root / LOCK).exists():
        raise GuardError(f'an earlier {DECISION} run started ({LOCK}) and did not complete: the test window counts as accessed. '
                         'Recovery needs a new owner decision in the decision log; do not delete the lock to rerun')
    if (root / RUN_DIR).exists():
        raise GuardError(f'{RUN_DIR} exists without a lock; refusing')
    (root / D52_DIR).mkdir(parents=True, exist_ok=True)
    try:
        fh = open(root / LOCK, 'x', encoding='utf-8')
    except FileExistsError:
        raise GuardError(f'{LOCK} was created by a concurrent run; refusing') from None
    with fh:
        json.dump({'decision': DECISION, 'status': 'started; the test window is read after this file exists',
                   'utc': datetime.now(timezone.utc).isoformat(timespec='seconds'), 'freeze_manifest_sha256': freeze_sha}, fh, indent=1)
        fh.flush(); os.fsync(fh.fileno())


# ---------------------------------------------------------------- test rows
def check_availability(df):
    """No holdout-period input; origin, horizon and target agree; the origin's information ends before the target week."""
    if (df.origin_week_start < pd.Timestamp(cd.CANDIDATE_START)).any() or (df.origin_date < pd.Timestamp(cd.CANDIDATE_START)).any():
        raise GuardError(f'origin before {cd.CANDIDATE_START}: 2023 holdout-period data must not be read (D-50, D-52 item 4)')
    bad = (df.target_week_start != df.origin_week_start + pd.to_timedelta(7 * df.horizon_weeks, unit='D')) \
        | (df.origin_date != df.origin_week_start + pd.Timedelta(days=6)) | (df.origin_date >= df.target_week_start)
    if bad.any():
        raise GuardError(f'{int(bad.sum())} rows fail the origin / horizon / target availability check')


def read_test_rows(path):
    df = pd.read_parquet(path, columns=COLS, filters=[('target_week_start', '>=', FIRST_WEEK), ('target_week_start', '<=', LAST_WEEK)])
    if len(df) and (df.target_week_start.min() < FIRST_WEEK or df.target_week_start.max() > LAST_WEEK):
        raise GuardError(f'{Path(path).name}: row outside the authorised test window was loaded')
    if (ed.assign_period(df) != 'test').any():
        raise GuardError(f'{Path(path).name}: rows outside the protocol test period')
    check_availability(df)
    return df


# ---------------------------------------------------------------- persistence error
def mae_ci(df, cluster, reps=REPS, seed=SEED):
    """Cluster bootstrap of the MAE level (clusters resampled with replacement; bc.cluster_bootstrap's draw convention)."""
    g = df.assign(ae=(df.pred - df.y_target).abs()).groupby(cluster).ae.agg(['sum', 'size'])
    if len(g) < 2:
        return len(g), np.nan, np.nan
    idx = np.random.RandomState(seed).randint(0, len(g), size=(reps, len(g)))
    m = g['sum'].to_numpy()[idx].sum(axis=1) / g['size'].to_numpy()[idx].sum(axis=1)
    return len(g), float(np.percentile(m, 2.5)), float(np.percentile(m, 97.5))


def summarise(ev, by):
    rows = []
    for k, g in ev.groupby(by):
        r = {**dict(zip(by, k)), **bc.metrics(g.y_target.to_numpy(), g.pred.to_numpy()), 'markets': g.canonical_id.nunique(),
             'states': g.state.nunique(), 'series': g.groupby(bc.S).ngroups, 'target_weeks': g.target_week_start.nunique()}
        for name, col in (('market', 'canonical_id'), ('state', 'state')):
            r[f'{name}_clusters'], r[f'{name}_mae_ci95_lo'], r[f'{name}_mae_ci95_hi'] = mae_ci(g, col)
        rows.append(r)
    return pd.DataFrame(rows)


def evaluate(mt, h):
    """Persistence on the eligible test rows of one horizon; every other row is kept with its exclusion reason."""
    x = mt[mt.horizon_weeks == h].copy()
    x['exclusion'] = np.select([~x.eligible_d41.astype(bool), x.y_origin.isna(), x.y_target.isna() | (x.y_target <= 0)],
                               ['not_eligible_d41_at_origin', 'missing_origin_median', 'missing_or_non_positive_target'], '')
    x['state'] = x.canonical_id.str.split('|').str[0]
    x['month'] = (x.target_week_start + pd.Timedelta(days=3)).dt.strftime('%Y-%m')   # Thursday names the week's month (Phase 8)
    ev = x[x.exclusion == ''].assign(pred=lambda d: d.y_origin)
    return x, ev


def cell_tables(mt, h):
    x, ev = evaluate(mt, h)
    cov = [{'Commodity': c, 'test_rows': len(g), 'excluded_rows': int((g.exclusion != '').sum()), 'evaluated_rows': int((g.exclusion == '').sum()),
            'markets': g[g.exclusion == ''].canonical_id.nunique(), 'states': g[g.exclusion == ''].state.nunique(),
            'series': g[g.exclusion == ''].groupby(bc.S).ngroups, 'target_weeks': g[g.exclusion == ''].target_week_start.nunique(),
            'first_target_week': str(g.target_week_start.min().date()), 'last_target_week': str(g.target_week_start.max().date())}
           for c, g in x.groupby('Commodity')]
    loso = []
    for c, g in ev.groupby('Commodity'):
        if g.state.nunique() < 2:
            continue
        mae_all = float((g.pred - g.y_target).abs().mean())
        for s in sorted(g.state.unique()):
            r = g[g.state != s]
            loso.append({'Commodity': c, 'left_out_state': s, 'rows': len(r), 'markets': r.canonical_id.nunique(),
                         'mae': float((r.pred - r.y_target).abs().mean()), 'mae_all_states': mae_all})
    excl = x[x.exclusion != ''].groupby(['Commodity', 'exclusion']).size().rename('rows').reset_index()
    return {'coverage': pd.DataFrame(cov), 'by_crop': summarise(ev, ['Commodity']), 'by_crop_month': summarise(ev, ['Commodity', 'month']),
            'by_crop_state': summarise(ev, ['Commodity', 'state']), 'leave_one_state_out': pd.DataFrame(loso), 'exclusions': excl}


def run(root='.', confirm=None):
    if confirm != DECISION:
        raise GuardError(f'final execution gate: pass --confirm-single-test-run {DECISION}')
    root = Path(root)
    rec, pre = verify(root)
    extra = sorted(set(loaded_code(root)) - set(rec['code']))
    if extra:
        raise GuardError(f'Code/ modules loaded that are not in the freeze: {extra[:5]}')
    freeze_sha = sha(root / FREEZE)
    take_lock(root, freeze_sha)
    start = datetime.now(timezone.utc).isoformat(timespec='seconds')
    out = {}
    for design in rec['designs']:
        mt = read_test_rows(root / bc.DATASET / f'model_table_{design}.parquet')
        for h in rec['horizons']:
            for k, t in cell_tables(mt, h).items():
                out.setdefault(k, []).append(t.assign(design=design, horizon=h)[['design', 'horizon'] + list(t.columns)])
    (root / RUN_DIR).mkdir()
    for k, ts in out.items():
        pd.concat(ts, ignore_index=True).to_csv(root / RUN_DIR / f'{k}.csv', index=False, float_format='%.6f', lineterminator='\n')
    man = {'decision': DECISION, 'approver': APPROVER, 'freeze_manifest_sha256': freeze_sha, 'preflight': pre, 'utc_start': start,
           'utc_end': datetime.now(timezone.utc).isoformat(timespec='seconds'), 'designs': rec['designs'], 'horizons': rec['horizons'],
           'seed': SEED, 'reps': REPS, 'loaded_code': loaded_code(root),
           'note': 'persistence only; skill vs persistence is 0 and not reported; reporting only, never for tuning or selection (D-52 item 10)',
           'outputs_sha256': {f'{k}.csv': sha(root / RUN_DIR / f'{k}.csv') for k in out}}
    (root / RUN_DIR / 'run_manifest.json').write_bytes(json.dumps(man, indent=1, default=str).encode())
    with open(root / DONE, 'x', encoding='utf-8') as fh:
        json.dump({'decision': DECISION, 'utc': man['utc_end'], 'run_manifest_sha256': sha(root / RUN_DIR / 'run_manifest.json')}, fh, indent=1)
    return man


def main(argv=None):
    import argparse
    ap = argparse.ArgumentParser(); ap.add_argument('command', choices=['freeze', 'verify', 'run'])
    ap.add_argument('--confirm-single-test-run'); a = ap.parse_args(argv)
    if a.command == 'freeze':
        rec = freeze(); print(json.dumps({k: v for k, v in rec.items() if k not in ('files', 'code')}, indent=1))
    elif a.command == 'verify':
        rec, pre = verify(); print(json.dumps({'verified': True, 'files': len(rec['files']), 'code': len(rec['code']), 'preflight': pre}, indent=1))
    else:
        print(json.dumps(run('.', a.confirm_single_test_run), indent=1, default=str))
    return 0


if __name__ == '__main__':
    sys.exit(main())
