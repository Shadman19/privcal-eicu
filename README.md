# Encrypted pooled recalibration at low-event ICU hospitals: code

This repository holds the data-independent code behind the manuscript *Gains from encrypted pooled recalibration at eICU hospitals with few calibration deaths depended on base-model class weighting and comparator*. It contains **no eICU records and no record-level outputs**. Checksums for every file are in `SHA256SUMS.txt`.

## Data
The eICU Collaborative Research Database v2.0 is available only to credentialed PhysioNet users who have signed its data use agreement: https://physionet.org/content/eicu-crd/2.0/. Place `patient`, `diagnosis` and `treatment` tables (csv or csv.gz) in `./eicu` next to the notebook. The post hoc APACHE IVa analysis also reads `apachePatientResult`.

## Layout
| Folder | Contents |
|---|---|
| `analysis/` | Frozen analysis notebook `PrivCal_eICU_reviewer_sensitivities_v9.ipynb` (SHA-256 `23d0ca06…7b75`), the Slurm job that runs it and the pinned auditor, and the five-split robustness exporter. |
| `audit/` | Pinned aggregate auditor (`1e3126e2…6eb3`), row reconciliation, hospital win/loss summary, stay-selection audit, seed-7 calibration and CKKS-fidelity diagnostic, primary-stratum calibration check, the post-run driver, and the publication-extract tool for the five-split tables. All outputs are aggregate-only. |
| `governance/` | Pre-run analysis lock template, verifier (preflight/post-run timing checks) and its tests, and the approval helper used before the run. |
| `simulation/` | Protocol-fixed simulation (protocol and post hoc addendum with their checksums), drivers, summaries and figure script. It runs the same frozen notebook code on synthetic hospitals. |
| `manuscript/` | Scripts that fill every eICU number and figure in the manuscript from hash-checked aggregate JSONs, with tests on synthetic fixtures. |

## Reproducing the eICU analysis
1. Environment used: Python 3.11, numpy 2.4.4, pandas 2.3.3, scikit-learn 1.9.1, scipy 1.17.1, matplotlib 3.10.9, TenSEAL 0.3.18. Set `PYTHONHASHSEED=0`.
2. Before running, complete the lock file in `governance/` and run `verify_v9_analysis_lock.py preflight`.
3. Run `analysis/main_reviewer_v10_verified_source_job.sh`. The paths inside are those of the authors' cluster (`PRIVCAL_PROJECT_DIR`, `PRIVCAL_PYTHON_BIN` can be overridden in the audit scripts).
4. Run `audit/postrun_aggregates_v29_guardfix_codex.sh` with the four `PRIVCAL_V9_*` variables pointing at the audit, output folder, lock and receipt. It writes aggregate JSONs to `release_review_<time>/`.
5. `manuscript/build_v46.py` fills the current manuscript template (`PrivCal_SciRep_v46.template.tex`) from those JSONs after checking them against a SHA-256 manifest; it also pins the hashes of the five-split extract, the cohort table and the two post hoc outputs (sensitivity and APACHE IVa). `make_v43_template.py` to `make_v46_template.py` record how each template version was derived from the previous one; earlier `build_v4x.py` scripts are kept for provenance. `count_words.py` checks the journal word limits.

## Post hoc sensitivity analyses
`audit/sensitivity_v42.py` with `audit/run_v42_sensitivity_job.sh` first reproduces every primary hospital's scores from the frozen run (tolerance 1e-9) and the discharge-offset counts, then (i) removes stays with inconsistent discharge offsets from evaluation only or before refitting all models, and (ii) refits the base model without class weighting and refits every recalibration map. Output is aggregate-only; counts from 1 to 19 are banded.

`audit/apache_v46.py` with `audit/run_v46_apache_job.sh` first verifies the frozen run (approved JSON hashes, final cohort, seed-7 hospital partition and primary hospital set), then (iii) recalibrates the recorded APACHE IVa hospital-mortality prediction instead of the text model, refitting every recalibration method with each stay's frozen split assignment. Stays without exactly one APACHE IVa record, or whose prediction is missing or outside [0, 1], are removed after the frozen split; hospitals without eligible calibration or test stays are dropped; the 0-5-death stratum is redefined on eligible calibration stays. The release JSON is aggregate-only: stay counts from 1 to 19 and hospital counts from 1 to 9 are banded, counts that would reveal a banded count are withheld, and the exclusion breakdown and input fingerprints stay in a private receipt on the host.

## Reproducing the simulation
`python simulation/privcal_sim_v25.py` (40 replicates per scenario, resumable cache), then `privcal_sim_addendumA_v26.py`, `summarize_sim_v25.py`, `make_fig_v25.py`. The frozen notebook must sit next to the scripts; its hash is checked.

## Scope
The CKKS aggregation runs all roles in one process on one host. It demonstrates arithmetic fidelity, not a deployed multi-institution protocol, security against a malicious key holder, or differential privacy.

## License and citation
Released under the MIT License (`LICENSE`). Citation metadata is in `CITATION.cff`.
