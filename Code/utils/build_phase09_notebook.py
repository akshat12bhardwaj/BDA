"""
Generator for Notebooks/Phase_09_Arrivals_Model_Experiments.ipynb.
Run `python Code/utils/build_phase09_notebook.py` from the project root, then execute it with
`python -m jupyter nbconvert --to notebook --execute --inplace Notebooks/Phase_09_Arrivals_Model_Experiments.ipynb`.
All logic lives in tested modules under Code/modelling/; the notebook calls them and explains the results.
"""

import nbformat as nbf

cells = []


def md(text):
    cells.append(nbf.v4.new_markdown_cell(text))


def code(text):
    cells.append(nbf.v4.new_code_cell(text))


md("""# Phase 9 — Arrivals Model Experiments

Learned forecasting of weekly mandi **arrivals** (supply-side market activity, **not demand**) for Onion, Potato and Wheat, under the accepted protocol D-43 and the experiment protocol `phase9-arrivals-protocol-v1` (`Documentation/Phase_09_Model_Protocol.md`), **approved 2026-10-22 as D-44** with the U2–U6 answers.

**Approval gate.** `fit_predict` runs only when `PROTOCOL_STATUS == "APPROVED"` **and** `Decision_Log.md` records D-44 as ACCEPTED. Otherwise the training, evaluation and selection cells skip with a message, and the steps that fit nothing still run:
- loading and validating the data
- building the time-aware features and checking them for leakage
- reproducing the frozen persistence baseline
- preparing the populations

**Fixed by the protocol** (no tuning, no added candidates): the candidates, features, populations, metric, practical threshold and selection rule.

**Never used here:** data after 2020-12-27 (the 2021–2022 test and 2023+ holdout periods are reserved), and no Phase 4–8 output is modified.

## INDEX
1. Setup and configuration
2. Inputs, hashes and the approved Phase 9 dataset
3. Data validation: target, keys, weeks, missing reports, eligibility
4. Time-aware features and the leakage probe
5. Reproducing the frozen persistence baseline
6. Evaluation populations (AQ-1 v1 primary, original as sensitivity)
7. Training candidates (gated)
8. Evaluation, paired uncertainty and the selection rule (gated)
9. Results by year, horizon and crop
10. Saved outputs
11. Summary""")

md("## 1. Setup and configuration")
code("""import os, sys, json, random
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

PROJECT_ROOT = Path.cwd().parent if Path.cwd().name == "Notebooks" else Path.cwd()
os.chdir(PROJECT_ROOT)
sys.path.insert(0, str(PROJECT_ROOT))
pd.set_option("display.width", 200)
pd.set_option("display.max_columns", 40)

from Code.modelling import dataset as d
from Code.modelling import arrivals as ar
from Code.modelling import arrivals_aq1 as a1
from Code.modelling import arrivals_models as am
from Code.integration.pipeline import file_sha256

random.seed(am.SEED)
np.random.seed(am.SEED)
CROPS = d.load_selected_crops()
FIG = am.OUT_DIR / "figures"
FIG.mkdir(parents=True, exist_ok=True)
print("Protocol:", am.PROTOCOL_VERSION, "| status:", am.PROTOCOL_STATUS, "| input cutoff:", ar.CUTOFF.date())
print("Environment:", am.environment(), "| interpreter:", sys.executable)
pd.Series(am.protocol(), dtype=object).to_frame("value")""")

md("""## 2. Inputs, hashes and the approved Phase 9 dataset

- **Inputs:** the Phase 6 feature tables, hash-checked against the Phase 7 record.
- **Truncation:** the builder truncates every input at 2020-12-27 before computing anything.
- **Prepared per crop:**
  - the weekly examples (D-43)
  - the origin features
  - the AQ-1 v1 flags, verified against their manifest
  - the primary-population target weeks
- **Leakage probe:** runs on a sample of series.""")
code("""reg = d.registry_columns(pd.read_csv(d.REGISTRY_PATH))
inputs = [d.FEATURE_DIR / f"features_{c.lower()}.parquet" for c in CROPS] + [d.REGISTRY_PATH]
hashes_before = d.check_inputs(inputs, d.phase7_expected_hashes())
manifest = pd.read_csv(a1.AQ_DIR / "aq1_flags_v1_manifest.csv")

DATA, PROBE = {}, []
for crop, path in zip(CROPS, inputs):
    df = pd.read_parquet(path)
    d.validate_schema(df, reg, crop)
    df = df[df["reported_date"] <= ar.CUTOFF]
    by_h, origins = ar.build_arrivals_examples(df)
    feats = am.origin_features(origins, df)
    fpath = a1.AQ_DIR / f"aq1_flags_v1_{crop.lower()}.parquet"
    row = manifest.set_index("crop").loc[crop]
    if not fpath.exists() or file_sha256(fpath) != row["file_sha256"]:
        raise RuntimeError(f"AQ-1 flags for {crop} missing or changed; rerun Code/modelling/arrivals_aq1.py:run_aq1()")
    flags = pd.read_parquet(fpath)
    PROBE.append(am.leakage_probe(df, "2019-06-30", n_series=30).assign(crop=crop))
    DATA[crop] = {"by_h": by_h, "origins": origins, "feats": feats,
                  "weeks": am.population_weeks(flags, am.PRIMARY_POPULATION),               # U2 primary
                  "weeks_mp": am.population_weeks(flags, am.MP_SENSITIVITY_POPULATION),     # U3 sensitivity
                  "pending": int(flags["provider_query_pending"].sum())}
    del df, flags
print("inputs unchanged:", d.check_inputs(inputs) == hashes_before)
pd.DataFrame({c: {f"examples h={h}": len(v["by_h"][h]) for h in d.HORIZONS} | {"series-weeks": len(v["origins"]),
              "provider_query_pending rows": v["pending"]} for c, v in DATA.items()})""")

md("""## 3. Data validation

- **Target:** the weekly median of usable daily arrivals in week W + h, in tonnes per reported day.
- **Series key:** (crop, state, district, market, variety).
- **Weeks:** Monday–Sunday, with the origin at the end of Sunday.
- **Missing reports:** a day without a record is *not reported*, never zero; a week without a usable record yields no example.
- **Eligibility:** ≥ 365 usable arrival dates on or before the origin.
- **Checks:** `validate_arrivals_examples` enforces all of these and the cutoff.""")
code("""rows = []
for crop, v in DATA.items():
    for h, ex in v["by_h"].items():
        ar.validate_arrivals_examples(ex)
        for period in ["train", "val_2019", "val_2020"]:
            sel = ex["period"] == period
            rows.append({"crop": crop, "h": h, "period": period, "examples": int(sel.sum()),
                         "origin_eligible": int((sel & ex["eligible_at_origin"]).sum()),
                         "max_target_sunday": ex.loc[sel, "target_sunday"].max().date()})
checks = pd.DataFrame(rows)
assert checks["max_target_sunday"].max() <= ar.CUTOFF.date()
checks.pivot_table(index=["crop", "h"], columns="period", values="origin_eligible")""")
code("""rep = pd.concat([v["origins"]["origin_week_reported_days"].value_counts(normalize=True).sort_index().rename(c)
                 for c, v in DATA.items()], axis=1)
print("Share of series-weeks by number of reported days (gaps are not zero):")
rep.round(3)""")

md("""## 4. Time-aware features and the leakage probe

Every feature is computed from weeks up to and including the origin week, on the Phase 5 usable view (`am.FEATURES`):
- origin level: log of the origin-week median, reported days, and the log count of usable dates;
- exact calendar-week lags (1, 2, 4 and 52 weeks) as log ratios to the origin; an unreported week stays missing;
- medians of the previous 4 and 13 reported weeks;
- the number of reported weeks in the last 13;
- price context: a usable price in the origin week, and the 4-week log change of the weekly median price;
- target-week calendar fields.

**The probe** replaces every value after a probe origin with 1e9 and recomputes the features. Features at origins on or before it must not change.""")
code("""probe = pd.concat(PROBE, ignore_index=True)
assert (probe["rows_changed"] == 0).all(), "future data changed an origin feature"
miss = pd.concat([v["feats"][am.FEATURES[:-3]].isna().mean().rename(c) for c, v in DATA.items()], axis=1)
print("Leakage probe: rows compared per crop", probe.groupby("crop")["rows_compared"].first().to_dict(), "- no changes")
print("Missing share per feature (missing = not reported or no history; never imputed here):")
miss.round(3)""")

md("""## 5. Reproducing the frozen persistence baseline

Persistence (the origin-week median) is recomputed with the same code and compared with the saved `Processed_Data/modelling/phase09/arrivals_baseline_metrics.csv`. Row counts must match exactly, and log MAE to within 1e-12, which allows only the last-bit change of a CSV float round-trip.""")
code("""saved = pd.read_csv(ar.OUT_DIR / "arrivals_baseline_metrics.csv")
BASE = {}
for crop, v in DATA.items():
    for h, ex in v["by_h"].items():
        BASE[(crop, h)], _ = ar.validation_predictions(ex, v["origins"], crop, h)
repro = am.reproduce_persistence(pd.concat(BASE.values(), ignore_index=True), saved)
assert repro["reproduced"].all(), "persistence does not reproduce the frozen baseline"
print("Persistence reproduced for", len(repro), "crop x horizon x period cells; identical counts; max |diff| =",
      repro["abs_diff_log_mae"].max(), "(CSV float round-trip)")
repro.pivot_table(index=["crop", "horizon_weeks"], columns="period", values="log_mae").round(4)""")

md("""## 6. Evaluation populations

- **Primary population** (approved, U2): AQ-1 v1 `aq1_likely`.
  - Evaluation targets are cleaned retrospectively.
  - A training target is cleaned only if its flags were knowable by the refit date.
  - Origin inputs and eligibility stay on the Phase 5 view.
- **Sensitivity 1:** the original population (selection criterion 4).
- **Sensitivity 2** (U3): `aq1_likely_excl_mp_pending`, which also excludes every flagged Madhya Pradesh `provider_query_pending` row. Reported only.""")
code("""pop = pd.read_csv(ar.OUT_DIR / "arrivals_aq1_population_changes.csv")
pop[(pop["variant"] == am.PRIMARY_POPULATION) & (pop["period"] != "val_combined")].pivot_table(
    index=["crop", "horizon_weeks"], columns="period", values=["examples_dropped", "examples_target_changed"])""")

md("""## 7. Training candidates (gated)

**Candidates:** `am.CANDIDATES` (Ridge; conservative HistGradientBoosting with the Phase 8 settings and no tuning).
- **Training:** each candidate is trained separately per crop and horizon, with quarterly expanding refits (`fit_predict`), for all three populations.
- **Target:** the log ratio of the target to the origin-week median.
- **Evaluation rows:** origin-eligible 2019–2020 rows only.

`fit_predict` itself refuses to run unless the protocol is approved.""")
code("""RESULTS = {}
if am.PROTOCOL_STATUS != "APPROVED":
    print(f"{am.PROTOCOL_VERSION} is {am.PROTOCOL_STATUS}: no learned arrivals model is fitted. "
          "Approve the protocol (decision entry) and set PROTOCOL_STATUS = 'APPROVED' to run this cell.")
else:
    for crop, v in DATA.items():
        for h, ex in v["by_h"].items():
            for cand in am.CANDIDATES:
                for pop_name, weeks in [("primary", v["weeks"]), ("original", None), ("mp_excluded", v["weeks_mp"])]:
                    RESULTS[(crop, h, cand, pop_name)] = am.fit_predict(ex, v["origins"], v["feats"], weeks, cand, crop, h)
    print("fitted", len(RESULTS), "candidate x crop x horizon x population runs")""")

md("""## 8. Evaluation, paired uncertainty and the selection rule (gated)

**Evaluation:** each candidate is compared with persistence on **identical rows**, separately for 2019 and 2020, using log MAE and a paired bootstrap (whole series, with market clusters as a check; 10,000 replicates; seed 20261022).

**A candidate is proposed only if it:**
1. has 95% intervals above 0 in both years under both clusterings;
2. has estimate / SE above the Bonferroni cut-off for the 36-test family;
3. improves by at least **2%** in both years;
4. also improves on the original population.

**Not covered:** cluster resampling does not capture nationwide shocks.""")
code("""SELECTION = pd.DataFrame()
if RESULTS:
    def boot(pop_name):
        out = []
        for (crop, h, cand, p), pr in RESULTS.items():
            if p == pop_name:
                out.append(ar.bootstrap_log_mae(pr, candidate=cand).assign(candidate=cand))
        return pd.concat(out, ignore_index=True)
    BOOT_PRIMARY, BOOT_ORIGINAL, BOOT_MP = boot("primary"), boot("original"), boot("mp_excluded")
    SELECTION = am.select(BOOT_PRIMARY, BOOT_ORIGINAL)          # the D-44 rule: primary + original only
    display(SELECTION)
    mp_view = BOOT_MP[(BOOT_MP["cluster"] == "series") & (BOOT_MP["period"] != "val_combined")]
    print("U3 sensitivity (all flagged MP rows excluded; reported only): relative log-MAE improvement %")
    display(mp_view.pivot_table(index=["crop", "horizon_weeks", "candidate"], columns="period",
                                values="rel_log_mae_improvement_pct").round(2))
else:
    print("No candidate results: the selection rule is defined (am.select) and tested, but not applied.")
    print("Bonferroni family:", am.FAMILY, "tests, z cut-off", round(am.Z_BONFERRONI, 3), "| practical minimum", am.MIN_REL, "%")""")

md("## 9. Results by year, horizon and crop")
code("""m = saved[(saved["segment"] == "all") & (saved["period"] != "val_combined")
          & saved["baseline"].isin(["persistence", "calendar_adjusted_persistence"])]
fig, axes = plt.subplots(1, 3, figsize=(15, 4), sharey=False)
for ax, crop in zip(axes, CROPS):
    t = m[m["crop"] == crop].pivot_table(index=["horizon_weeks", "period"], columns="baseline", values="log_mae")
    t.plot(kind="bar", ax=ax, rot=45, title=f"{crop}: validation log MAE")
    ax.set_xlabel("horizon (weeks), validation year"); ax.set_ylabel("log MAE")
fig.tight_layout()
fig.savefig(FIG / "phase09_arrivals_baselines.png", dpi=110)
plt.show()
METRICS = pd.DataFrame()
if RESULTS:
    rows = []
    for (crop, h, cand, p), pr in RESULTS.items():
        for period in ["val_2019", "val_2020"]:
            part = pr[pr["period"] == period]
            for name in [cand, "persistence"]:
                rows.append({"crop": crop, "h": h, "candidate": cand, "population": p, "period": period, "model": name,
                             **ar.metrics(part["y"], part[name])})
    METRICS = pd.DataFrame(rows)
    display(METRICS[METRICS["population"] == "primary"].pivot_table(
        index=["crop", "h", "candidate", "model"], columns="period", values="log_mae").round(4))""")

md("""## 10. Saved outputs

**Written to `Processed_Data/modelling/phase09_models/`:**
- the experiment configuration
- the persistence reproduction
- the leakage probe
- the feature missingness

Candidate predictions and metrics are added there only after approval. **No earlier output is overwritten.**""")
code("""am.write_config()
repro.to_csv(am.OUT_DIR / "persistence_reproduction.csv", index=False)
probe.to_csv(am.OUT_DIR / "feature_leakage_probe.csv", index=False)
miss.to_csv(am.OUT_DIR / "feature_missingness.csv")
if RESULTS:
    pd.concat([pr.assign(candidate=k[2], population=k[3]) for k, pr in RESULTS.items()]).to_parquet(am.OUT_DIR / "candidate_predictions.parquet", index=False)
    BOOT_PRIMARY.to_csv(am.OUT_DIR / "candidate_bootstrap_primary.csv", index=False)
    BOOT_ORIGINAL.to_csv(am.OUT_DIR / "candidate_bootstrap_original.csv", index=False)
    BOOT_MP.to_csv(am.OUT_DIR / "candidate_bootstrap_mp_excluded.csv", index=False)
    METRICS.to_csv(am.OUT_DIR / "candidate_metrics.csv", index=False)
    SELECTION.to_csv(am.OUT_DIR / "candidate_selection.csv", index=False)
print("inputs unchanged:", d.check_inputs(inputs) == hashes_before)
sorted(p.name for p in am.OUT_DIR.iterdir())""")

md("## 11. Summary")
code("""print("Protocol", am.PROTOCOL_VERSION, "status:", am.PROTOCOL_STATUS)
print("Data: examples built and validated for", ", ".join(CROPS), "with input cutoff", ar.CUTOFF.date())
print("Leakage probe: no feature at or before the probe origin changed when later data changed.")
print("Persistence baseline reproduced (counts identical, |diff| <= 1e-12):", bool(repro["reproduced"].all()))
if SELECTION.empty:
    print("No learned candidate has been fitted: every cell keeps persistence (D-43) until the protocol is approved.")
else:
    for r in SELECTION.itertuples():
        why = [n for n, ok in [("CI both years", r.c1_ci_both_years_both_clusterings), ("Bonferroni", r.c2_bonferroni),
                               ("2% practical", r.c3_practical), ("original population", r.c4_original_population)] if not ok]
        print(f"{r.crop} h={r.horizon_weeks} {r.candidate}: {'PASSES' if r.passes else 'fails: ' + ', '.join(why)}"
              f" ({r.rel_2019_pct:+.2f}% / {r.rel_2020_pct:+.2f}%)")
    print("Candidates passing every criterion:", int(SELECTION["passes"].sum()), "| proposed:",
          SELECTION.loc[SELECTION["proposed"], ["crop", "horizon_weeks", "candidate"]].values.tolist() or "none (persistence kept)")""")

nb = nbf.v4.new_notebook()
nb["cells"] = cells
nb["metadata"] = {"kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
                  "language_info": {"name": "python", "version": "3.13"}}
out_path = "Notebooks/Phase_09_Arrivals_Model_Experiments.ipynb"
with open(out_path, "w", encoding="utf-8") as f:
    nbf.write(nb, f)
print("Notebook written to", out_path, "with", len(cells), "cells")
