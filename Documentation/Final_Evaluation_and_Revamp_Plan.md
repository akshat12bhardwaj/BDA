# Final Evaluation and Revamp Plan (proposal for review, 2026-10-24)

**Status:** preparation only.
- No test window was opened, no run was executed, and nothing was deleted, moved, staged or committed.
- Records in force: D-50, D-51, and `Data_Source_Review.md` §7–§9.
- Persistence is the default forecast. Both failed learned-model experiments (§7.5 price-only, §8.11 price + weather) stand as findings.
- Weather stays out of the forecasting pipeline. CEDA and DMI access stay unresolved.

**Update (2026-10-24):** §1 has since been carried out. It was authorised as D-52, run once, and its result is recorded as D-53 (`Data_Source_Review.md` §7.6). The candidate test window is now consumed. The rest of this plan is unchanged.

**Revamp update (2026-10-24):**
- **Notebooks:** four read-only extension notebooks were added (`Code/utils/build_extension_notebooks.py`): `Research_Extension_01_Candidate_Price_Data`, `Research_Extension_02_Candidate_Forecast_Experiments` (§2 E2 + E3), `Research_Extension_03_Final_Persistence_Test` (D-52) and `Research_Extension_04_Conclusions_and_Project_Guide` (E4 content and the reading order).
- **Not added:** the proposed routing notebook (E1). The routing work is still uncommitted owner work; the routes are shown in the application.
- **Files and docs:** a root `README.md` and a pinned `requirements.txt` were added. The final report, checklist, setup guide, demo script and slides were refreshed.
- **§3 cleanup manifest:** no file was moved or deleted. Every "Keep" and "Owner decision" item stands.
- **Cleanup (later, 2026-10-24):**
  - **Renames:** the demonstration became `Overview_00_Project_Demonstration.ipynb`, and the extensions gained a `Research_` prefix, so a file listing sorts in reading order (Overview → Phase 01–10 → Research Extensions).
  - **Kept names:** `Phase_01` – `Phase_10` keep their names. They are already sequential, and `Phase_09`'s name is cited by the D-45-frozen `Phase_09_Model_Protocol.md`.
  - **Deleted:** the superseded Streamlit screenshots (`screenshots/app_1` … `app_6`, still in Git history at `498e677`) and the earlier sidebar-layout screenshots (`screenshots/redesign/`, which `react/` supersedes).
  - **Historical names:** the §2 table below is the original proposal; its file names are historical.

---

## 1. Persistence-only test evaluation: recommendation

**Can it run without changing anything frozen? Yes, but it needs authorisation.**

| Item | Evidence | Status |
|---|---|---|
| Model | persistence = origin-week median (`y_origin`); no parameters, training or refits | nothing to tune |
| Split | frozen protocol `exp_candidate_v1_protocol.json` (LF SHA-256 `a6b1240c4c4f80da…`): **test = target Sundays 2026-07-05 → 2026-10-18** | unchanged |
| Population and target | candidate-prices-v1.1 (D-50); FAQ-only primary; h = 1 primary, h = 2 / 4 secondary; `eligible_d41` at the origin; target = next-week median | unchanged |
| Metrics and uncertainty | MAE (primary), RMSE, MAPE with the instability diagnostic (`MAPE_UNSTABLE_SHARE` = 0.20), median APE; market-cluster bootstrap of the **MAE level**, 10,000 replicates, seed 20261022; state-level and leave-one-state-out | unchanged. Skill against persistence is trivially 0 and not reported |
| Test access | protocol leakage control: "test used once after a freeze manifest + run-once guard"; `approval_checklist.csv`: "test freeze + one-time test run — approver: project owner (to be named); **not authorised**" | **requires explicit owner authorisation and a named approver** |
| 2023 holdout | the D-50 guard refuses any input before 2024-02-03; Phase 8 §P holdout untouched | stays inaccessible |

**Would the reserved test window be accessed? Yes. That is the purpose of the run.** It would be the **single use** of the candidate test window.

**Consequences:**
- No later candidate model (for example, a future price + arrivals model) could be scored on 2026-07-05 → 10-18. It would need data after 2026-10-20, which is consistent with D-51 and §9.3 Path A.
- **No frozen decision needs to change.** The run executes an already-specified, not-yet-authorised step.

**Purpose:** an honest out-of-sample error level for the **default** forecast on unseen weeks, to report beside the validation figures (§7.4). It is **not** a model comparison; nothing is selected or tuned on it.

**What is needed before it can run** (none of it done):
1. **Owner authorisation**, naming the approver, recorded as a decision entry (for example D-52).
2. **A test freeze manifest:** the protocol LF hash, v1.1 `build_manifest.json` hash, the hash of a new runner file, the split, seed and metric definitions, and the "persistence only" statement.
3. **A new runner** (`Code/candidates/persistence_test_candidate.py`, to be written and reviewed after authorisation). The existing guards deliberately refuse the test window, so they are **not** edited.
   - Reads only target weeks ≤ 2026-10-12 (Sunday 2026-10-18) and inputs ≥ 2024-02-03.
   - A **run-once guard**: refuses if the results file exists.
   - Verifies the freeze manifest before reading any test row.
   - Writes to `experiments/exp_candidate_v1/persistence_test/`.
4. **Expected outputs:**
   - `test_results.csv`: crop × horizon × design × test month and overall: rows, markets, states, target weeks, MAE, RMSE, MAPE, median APE, the MAPE-instability flag, and the 95% market-cluster CI of MAE;
   - state and leave-one-state-out tables;
   - `run_manifest.json`.
   - The validation persistence figures (§7.4) shown beside them as context.
5. **Scale (from §7.1.2, FAQ-only h = 1, v1):** about 1,048 / 1,137 / 2,589 eligible test rows (Onion / Potato / Wheat; v1.1 adds 2), 72 / 82 / 177 markets, 8 / 11 / 5 states, **16 target weeks**. Wheat is concentrated in 5 states. These counts come from the design-stage audit; no test label has been read.

**Optional, needs separate approval:** scoring the two frozen baselines (seasonal naive, climatology) on the same test rows. Not recommended: they lost by large margins in validation, and scoring them adds comparisons without changing the default.

---

## 2. Proposed final notebook sequence (completed work only)

Existing notebooks are kept and are read-only walkthroughs. `test_notebooks.py` covers Phase 8 and the demonstration.

| # | Notebook | Content | Status |
|---|---|---|---|
| 00 | `BDA_Project_Demonstration.ipynb` | Overview and teacher demonstration; to be updated last, with links | exists; update in revamp |
| 01–07 | `Phase_01` … `Phase_07` | Data understanding, crop selection, weather collection, integration, cleaning, features, EDA | exist; unchanged |
| 08 | `Phase_08_Price_Forecasting.ipynb` | D-38 – D-42; frozen test 2021–2022 | exists; unchanged |
| 09 | `Phase_09_Arrivals_Model_Experiments.ipynb` | D-43 – D-45, AQ-1 | exists; unchanged |
| 10 | `Phase_10_Production_Context.ipynb` | D-46 – D-48 | exists; unchanged |
| E1 | **new:** `Extension_01_Routing_and_Storage.ipynb` | Phase 11a/b/c/e outputs (nodes, OSM routes, warehouses), read-only | proposed |
| E2 | **new:** `Extension_02_Candidate_Price_Data.ipynb` | data.gov.in audit, pilot, S1–S3, market identity, anomaly policy, v1 → v1.1 build, audit (§5–§7.2), read-only | proposed |
| E3 | **new:** `Extension_03_Candidate_Forecast_Experiments.ipynb` | baselines (§7.4), failed price-only model (§7.5), failed price + weather model (§8.11), with intervals and limitations, read-only | proposed |
| E4 | **new:** `Extension_04_Data_Access_and_Limitations.ipynb` (or a section of E3) | weather vintages (§8.7), IMD validation (§8.3, §8.8), the arrivals gap, CEDA and DMI status (§9) | proposed |

**Naming:** "Extension" rather than "Phase 11–14". The roadmap reserves Phases 11–14 for logistics, MILP, feedback and evaluation, and D-49 (phase renaming) is still undecided.

**Rules:** each new notebook reads only existing outputs, never re-runs a build or experiment, and gets the same contract tests as Phase 8 and the demonstration (no absolute paths, no writes, no forbidden calls, executed clean).

---

## 3. Proposed cleanup and move manifest (nothing done)

**Reference checks:** `grep` across `Code/`, `Documentation/`, `Notebooks/`, `frontend/src`.

| Path | Proposal | Reason | Dependency check |
|---|---|---|---|
| `Code/inspect_agriculture.py`, `Code/inspect_top.py`, `Code/test_openmeteo.py` | **Keep** (optionally move to `Code/legacy/` later) | Legacy reference, superseded | Referenced by `build_phase01/03_notebook.py`, `data_audit.py`, `weather/collector.py` (comment) and the docs. A move needs those updated and the notebooks regenerated, which is not worth it now |
| `Code/app/streamlit_app.py` (deleted, **unstaged**) | **Owner decision** | Pre-existing user change; the React/FastAPI app replaced it | Mentioned only in historical docs (`BigData_and_Dashboard_Spec.md` §6, marked superseded). Not touched |
| `Documentation/Final/screenshots/app_1 … app_6.png` (Streamlit) | Move to `screenshots/streamlit_legacy/` **or** keep | Superseded by `react/` and `redesign/` | Referenced only by `Master_Project_Context.md` (historical). A move needs that reference updated |
| `Documentation/BigData_and_Dashboard_Spec.md` Streamlit sections | **Keep** | Historical spec, already marked superseded | — |
| `Documentation/Final/Final_Report.md`, `README_Setup.md`, `Final_Presentation.pptx` | **Update**, not delete | Test counts out of date (279 / 268 against 414 now); no candidate-data, D-50 or D-51 content | The `.pptx` is generated by `Code/utils/build_final_slides.py`; regenerate, never hand-edit |
| `Documentation/Master_Project_Context.md` | **Update** | Has only a one-line pointer to the candidate work | — |
| `Processed_Data/candidates/datagov_prices/analytical_v1/` | **Keep** | Input to `market_mapping`, `identity_review`, `candidate_decisions` | Parquet ignored and regenerable; CSV reports cited in §6.4 |
| `…/dataset_v1/`, `…/experiment_design_v1/` | **Keep** | Frozen v1 reproducibility reference and its audit | Hashes in `build_manifest.json` |
| `…/experiment_design_v1_1/approval_checklist.csv` | **Keep unchanged** (evidence); supersede by documentation | Several "pending" items were later approved (split, baselines, learned scope, all recorded in §7.3–§7.5) | Editing a recorded artefact would rewrite history |
| `Dataset_Candidates/openmeteo_ext/2026-10-24/repro_*` | **Keep** | Same-day reproducibility evidence (§8.7) | Ignored by git |
| `Processed_Data/weather/raw/Punjab_Ferozpur.csv` | **Keep** | Superseded point, but one of the **573 protected files** and documented | Deleting it would break the protected snapshot |
| `Code/candidates/{audit_existing,validate_datagov,identifier_continuity,compare_weather,compare_apy}.py` | **Keep** (optional move to `Code/candidates/evidence/`) | One-off evidence generators | Cited by path in `Data_Source_Review.md` §1–§5; a move needs the doc paths updated |
| `.pytest_cache/`, `**/__pycache__/` | Safe to delete at any time | Regenerable caches | Ignored by git |
| **Missing:** a Python dependency file (`requirements.txt` or `pyproject.toml`) and a root `README.md` | **Add in the revamp** | A fresh clone cannot reproduce the environment from the repository alone | Versions to be taken from the project interpreter and the venv in `README_Setup.md` |

---

## 4. Outstanding blockers

1. **DMI arrivals request:** draft only (`Documentation/Requests/`), needing an authorised sender and real details.
2. **CEDA:** portal unreachable from this environment. End date, granularity and bulk licence unverified; the verified terms are non-commercial with a CC BY-ND conflict (§9.1).
3. **Persistence test run:** resolved. It was authorised (D-52), run once, and recorded (D-53).
4. **R09u:** independent review pack prepared, 0 reviewed; stays disabled.
5. **Pre-existing uncommitted work** needs the owner's decision before any commit: the app and data changes, the deleted `streamlit_app.py`, the `Documentation/Final/*` edits, the routing plan, and the untracked `Code/api/`, `Code/routing/` and `frontend/`.
6. **D-49** (phase renaming) is still undecided, which affects notebook naming.

---

## 5. Recommended next step

1. **Decide the persistence-only test run.** Recommended: authorise it, record D-52 with a named approver, then write, review and run the single run under a freeze manifest and run-once guard.
2. **Review this cleanup manifest and the notebook sequence.** Only then start the revamp: E1–E4 read-only notebooks, documentation updates, a dependency file, and the README.
3. **Separately decide what happens to the pre-existing uncommitted work** before anything is committed.
