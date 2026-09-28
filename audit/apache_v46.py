#!/usr/bin/env python3
"""Post hoc secondary analysis: recalibrating the recorded APACHE IVa hospital-mortality prediction (authorized host only).

Aggregate-only outputs. The frozen v9 primary analysis is unchanged and remains primary; this analysis is secondary,
post hoc and reported regardless of direction.

Specification (fixed with the co-reviewer before any APACHE data were seen, 28 Sep 2026):
- Score: the recorded APACHE IVa predictedHospitalMortality in apachePatientResult. Exactly one row with apacheVersion
  'IVa' (compared case-insensitively after stripping) is required per selected stay; stays with more than one such row
  are excluded and counted. The distinct apacheVersion values found for cohort stays are reported (banded counts), and
  the run stops if no 'IVa' value exists. Values must be decimal probabilities in [0, 1]; missing, negative (for
  example -1, non-predictive) and >1 values are excluded and counted. Exact 0 or 1 values are kept and counted.
  Every method uses the probability clipped to [1e-6, 1 - 1e-6] (the frozen pipeline works from the logit and maps it
  back with the sigmoid), so exact 0 and 1 enter every branch as 1e-6 and 1 - 1e-6.
- Base score: logit(clip(p, 1e-6, 1 - 1e-6)). The text model is not trained or used.
- The frozen loader reads the same --eicu-dir, and the run must match the frozen v9 run's input fingerprints,
  software versions, cohort size and CKKS backend (restricted run manifest). The frozen seed-7 source/target hospital
  partition and every stay's development/calibration/test assignment are kept (checked against the restricted v9
  per-hospital output); ineligible stays are removed from those fixed groups after assignment (checked). Hospitals
  left with no eligible calibration or test stays are removed from all analyses and counted by role.
- Outcome: the study's own hospital-discharge mortality label (not APACHE's stored actual outcome).
- Every recalibration method of the frozen pipeline is refitted on the APACHE logits: source temperature scaling,
  CKKS-summed pooled 12-bin isotonic map, penalty-2 local intercept on the source-temperature scale, source-only binned
  isotonic map, source Platt scaling plus local intercept.
- Stratum: target hospitals with 0-5 deaths among their APACHE-eligible calibration stays.
- Reported regardless of direction: eligibility counts; hospital counts and overlap with the original primary
  hospitals; absolute hospital-macro Brier scores; local minus pooled, source binned minus pooled and source Platt plus
  local minus pooled (2,000 paired hospital resamples, bootstrap seeds 1001, 1002, 1003); mean predicted versus
  observed risk in the stratum's test stays before and after recalibration.
- Timing: no claim is made that the stored score was available at the 24-hour landmark. If an admissionDx table is
  present on the host, the number of eligible stays with at least one admission-diagnosis entry after 1,440 minutes is
  reported; this cannot identify which diagnosis APACHE used or when the stored score was produced.

Disclosure rule (not a formal guarantee): counts of stays from 1 to 19 are reported as "1-19"; counts of hospitals
from 1 to 9 are reported as "1-9"; stratum results are withheld if the stratum has fewer than 10 hospitals;
hospital-level values and site identifiers never leave the host; scratch output (which includes site-level files written
by the frozen code) must be a fresh, access-restricted directory outside any release folder; an exact-output
cross-release disclosure review is required before any release. The eligibility categories use linked complementary
suppression so that no banded count can be recovered by subtraction from released totals; the number of analysed target
hospitals is withheld whenever the number dropped is banded; the whole stratum metric block is withheld if the stratum's
test stays contain fewer than 20 deaths or 20 survivors. The exclusion breakdown by reason is kept only in the
private receipt; the overlap with the original primary hospitals is withheld whenever it would reveal a banded count by
subtraction. The APACHE (and admissionDx) input files are fingerprinted in a
private run receipt on the host, never in the releasable JSON.
"""
from __future__ import annotations
import argparse, hashlib, json, os
from pathlib import Path
import numpy as np
import pandas as pd

NOTEBOOK = Path("PrivCal_eICU_reviewer_sensitivities_v9.ipynb")
SHA256 = "23d0ca0666fd68e040bd6a39d6e3361b2ba0c0502b39cc01f88cfa4baa807b75"
APPROVED_SHA256 = {
    "aggregate_publication_audit_v9.json": "cac5f258ba95d17a3e0574c798dd36cbd0898a3f13e2e32a20d153425cfd56ad",
    "aggregate_calibration_diagnostics_seed7.json": "671d2bfbd8bae4c8fb9207c99f473188870cadc9ac18c862ea2efd8cd51cfa00",
}
MIN_CELL = 20
MIN_HOSP = 10
B = 2000
EPS = 1e-6
SEEDS = {"local": 1001, "srcbin": 1002, "plattlocal": 1003}
WEIGHTED = 'class_weight="balanced", solver="liblinear"'
CFG_AT = 'if os.environ.get("PYTHONHASHSEED") != "0":'
CFG_HOOK = "CFG['eicu_dir'] = _APX_EICU_DIR  # bound to --eicu-dir before fingerprints and loading\n"
HOOK_AT = "    parts = train_backend_and_add_logits(backend, parts, SOURCE, split_seed)"
# Replaces the text-model training call. Runs after the frozen seed-7 partition and assignment, so both are unchanged.
APACHE_HOOK = (
    "    _APX_BEFORE = {_s: {_k: set(parts[_s][_k]['patientunitstayid']) for _k in ('train', 'calib', 'test')} for _s in SITES}\n"
    "    _APX_SRC0, _APX_TGT0 = tuple(SOURCE), list(TARGET)\n"
    "    for _s in SITES:\n"
    "        for _k in ('train', 'calib', 'test'):\n"
    "            _g = parts[_s][_k]\n"
    "            parts[_s][_k] = _g[_g['patientunitstayid'].isin(_APACHE_P.index)].copy()\n"
    "    _APX_DROP = [_s for _s in SITES if len(parts[_s]['calib']) == 0 or len(parts[_s]['test']) == 0]\n"
    "    SOURCE = tuple(_s for _s in SOURCE if _s not in _APX_DROP)\n"
    "    TARGET = [_s for _s in TARGET if _s not in _APX_DROP]\n"
    "    for _s in _APX_DROP:\n"
    "        del parts[_s]\n"
    "    SITES[:] = [_s for _s in SITES if _s not in _APX_DROP]\n"
    "    if len(SOURCE) < 2 or not TARGET:\n"
    "        raise RuntimeError('too few hospitals with eligible APACHE stays')\n"
    "    for _s in SITES:\n"
    "        for _k in ('calib', 'test'):\n"
    "            _p = np.clip(_APACHE_P.loc[parts[_s][_k]['patientunitstayid'].to_numpy()].to_numpy(float), _APX_EPS, 1 - _APX_EPS)\n"
    "            parts[_s][f'logit_{_k}'] = np.log(_p / (1 - _p))\n"
    "            parts[_s][f'y_{_k}'] = parts[_s][_k]['label'].values\n"
    "    globals()['_APX_INFO'] = dict(before=_APX_BEFORE, source0=_APX_SRC0, target0=_APX_TGT0, dropped=list(_APX_DROP))\n"
)


def load_approved(path: Path, name: str, expected: dict = APPROVED_SHA256) -> dict:
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != expected[name]:
        raise RuntimeError(f"{path} is not the approved {name} (SHA-256 mismatch)")
    return json.loads(raw)


def band(n: int):
    n = int(n)
    return n if (n == 0 or n >= MIN_CELL) else f"1-{MIN_CELL - 1}"


def band_h(n: int):
    n = int(n)
    return n if (n == 0 or n >= MIN_HOSP) else f"1-{MIN_HOSP - 1}"


def suppress_partition(cats: dict) -> dict:
    """Linked complementary suppression for categories that, with released totals, partition the cohort."""
    supp = {k for k, v in cats.items() if 0 < v < MIN_CELL}
    while supp and sum(cats[k] for k in supp) < MIN_CELL:
        rest = [k for k, v in cats.items() if k not in supp and v > 0]
        if not rest:
            break
        supp.add(min(rest, key=lambda k: (cats[k], k)))
    return {k: (v if k not in supp else (f"1-{MIN_CELL - 1}" if v < MIN_CELL else "suppressed (complementary)"))
            for k, v in cats.items()}


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def boot(delta: np.ndarray, seed: int) -> dict:
    rr = np.random.default_rng(seed)
    reps = rr.choice(delta, size=(B, len(delta)), replace=True).mean(axis=1)
    return {"n_hospitals": int(len(delta)), "mean": float(delta.mean()),
            "ci95": [float(np.percentile(reps, 2.5)), float(np.percentile(reps, 97.5))], "bootstrap_seed": seed}


def instrument(src: str) -> str:
    old = "return dict(backend=backend, split_seed=split_seed, SOURCE=SOURCE, TARGET=TARGET,"
    if src.count(old) != 1:
        raise RuntimeError("Unexpected frozen v9 return statement")
    return src.replace(old, "return dict(parts=parts, predict_fn=predict, platt_slope=platt_slope, "
                            "platt_intercept=platt_intercept, backend=backend, split_seed=split_seed, SOURCE=SOURCE, TARGET=TARGET,")


def frozen_source_apache() -> str:
    raw = NOTEBOOK.read_bytes()
    if hashlib.sha256(raw).hexdigest() != SHA256:
        raise RuntimeError("Unexpected v9 notebook")
    src = "\n".join("".join(c["source"]) for c in json.loads(raw)["cells"] if c["cell_type"] == "code")
    before, sep, _ = src.partition("# 9. Run all backends and splits")
    if not sep:
        raise ValueError("Cannot isolate the v9 loader and split")
    if before.count(WEIGHTED) != 1:
        raise RuntimeError("Expected exactly one class-weighted TF-IDF logistic regression (frozen source changed?)")
    if before.count(HOOK_AT) != 1 or before.count(CFG_AT) != 1:
        raise RuntimeError("Cannot place the APACHE hooks uniquely")
    before = before.replace(CFG_AT, CFG_HOOK + CFG_AT)
    return instrument(before.replace(HOOK_AT, APACHE_HOOK))


def load_apache(path: Path, cohort_ids: pd.Index) -> tuple[pd.Series, dict, dict]:
    """Return (valid IVa probabilities indexed by stay, releasable eligibility counts, private exclusion breakdown)."""
    ap = pd.read_csv(path, low_memory=False)
    ap.columns = [c.lower() for c in ap.columns]
    need = {"patientunitstayid", "apacheversion", "predictedhospitalmortality"}
    if need - set(ap.columns):
        raise RuntimeError(f"apachePatientResult lacks columns: {sorted(need - set(ap.columns))}")
    ap = ap[ap["patientunitstayid"].isin(cohort_ids)].copy()
    ver = ap["apacheversion"].astype(str).str.strip()
    versions = sorted(ver.unique().tolist())
    is_iva = ver.str.lower() == "iva"
    if not is_iva.any():
        raise RuntimeError(f"no apacheVersion 'IVa' rows for cohort stays; versions found: {versions}")
    iva = ap[is_iva]
    dup = iva["patientunitstayid"].duplicated(keep=False)
    one = iva[~dup]
    p = pd.to_numeric(one["predictedhospitalmortality"], errors="coerce")
    missing, negative, above1 = p.isna(), p < 0, p > 1
    valid = ~(missing | negative | above1)
    exact01 = valid & ((p == 0) | (p == 1))
    P = pd.Series(p[valid].to_numpy(float), index=pd.Index(one.loc[valid, "patientunitstayid"].to_numpy(), name="patientunitstayid"))
    if P.index.duplicated().any():
        raise AssertionError("duplicate stays survived the one-row rule")
    n = len(cohort_ids)
    cats = {"stays_without_IVa_row": int(n - iva["patientunitstayid"].nunique()),
            "stays_with_more_than_one_IVa_row": int(iva.loc[dup, "patientunitstayid"].nunique()),
            "IVa_prediction_missing": int(missing.sum()),
            "IVa_prediction_negative": int(negative.sum()),
            "IVa_prediction_above_1": int(above1.sum())}
    if len(P) + sum(cats.values()) != n:
        raise AssertionError("eligibility categories do not partition the cohort")
    counts = {"final_cohort_stays": int(n), "apache_versions_present_for_cohort_stays": versions,
              "exclusion_breakdown": "kept in the private receipt on the host (not releasable)"}
    if 0 < n - len(P) < MIN_CELL:
        counts.update(excluded_stays=f"1-{MIN_CELL - 1}", eligible_stays="withheld (fewer than 20 exclusions in total)")
    else:
        counts.update(excluded_stays=int(n - len(P)), eligible_stays=int(len(P)))
    counts.update(eligible_percent_of_cohort=round(100 * len(P) / n, 1),
                  eligible_exact_0_or_1_kept=band(int(exact01.sum())), probability_clip_all_methods=[EPS, 1 - EPS])
    private = {"exclusion_breakdown_exact": cats, "exact_0_or_1_kept_exact": int(exact01.sum())}
    return P, counts, private


def admission_dx_audit(path: Path | None, eligible_ids: pd.Index) -> dict:
    if path is None:
        return {"available_on_host": False}
    ad = pd.read_csv(path, low_memory=False)
    ad.columns = [c.lower() for c in ad.columns]
    if not {"patientunitstayid", "admitdxenteredoffset"} <= set(ad.columns):
        return {"available_on_host": True, "usable": False}
    ad = ad[ad["patientunitstayid"].isin(eligible_ids)]
    off = pd.to_numeric(ad["admitdxenteredoffset"], errors="coerce")
    late = ad.loc[off > 1440, "patientunitstayid"].nunique()
    none_recorded = len(eligible_ids) - ad["patientunitstayid"].nunique()
    return {"available_on_host": True, "usable": True,
            "eligible_stays_with_at_least_one_admission_diagnosis_entry_after_1440_min": band(late),
            "note": "cannot identify which admission diagnosis APACHE used or when the stored score was produced",
            "eligible_stays_without_any_admission_diagnosis_row": band(none_recorded)}


def overlap_release(ov: int, n_primary: int, n_stratum: int):
    """Withhold the overlap if it would reveal a banded count by subtraction. Filtering can only lower calibration
    deaths, so every retained original primary hospital stays in the stratum: n_primary - ov is the dropped count and
    n_stratum - ov is the number of newly qualifying hospitals."""
    if 0 < n_primary - ov < MIN_HOSP or 0 < n_stratum - ov < MIN_HOSP:
        return "withheld (would reveal a banded count by subtraction)"
    return band_h(ov)


def coverage(data: pd.DataFrame, eligible_ids: pd.Index, groups: dict) -> dict:
    """APACHE-eligible share of all final-cohort stays (all split groups) in each hospital group."""
    out = {}
    for name, sites in groups.items():
        g = data[data["site"].astype(str).isin(set(map(str, sites)))]
        tot, el = len(g), int(g["patientunitstayid"].isin(eligible_ids).sum())
        out[name] = {"n_hospitals": band_h(len(sites)), "stays": band(tot),
                     "eligible_percent": round(100 * el / tot, 1) if tot >= MIN_CELL else "withheld"}
    return out


def site_scores(scope: dict, res: dict, sites: list[str]) -> pd.DataFrame:
    """Per-hospital test Brier scores for the primary and control methods (host only)."""
    sig, fri, brier, nll = scope["sigmoid"], scope["fit_regularized_intercept"], scope["brier"], scope["nll"]
    from scipy.optimize import minimize_scalar
    parts, T = res["parts"], res["T_src"]
    ps, pi = res["platt_slope"], res["platt_intercept"]
    rows = []
    for s in sites:
        P = parts[s]; y = np.asarray(P["y_test"], float)
        zc, yc = P["logit_calib"] / T, P["y_calib"]
        off = fri(zc, yc, 2.0)
        off_pl = float(minimize_scalar(lambda a: len(yc) * nll(sig(ps * zc * T + pi + a), yc) + 2 * a * a,
                                       bounds=(-8, 8), method="bounded").x)
        p_pool = np.asarray(res["predict_fn"]("PrivCal-B (secure-agg isotonic)", s, "test"))
        p_loc = sig(P["logit_test"] / T + off)
        p_srcbin = np.asarray(res["predict_fn"]("Global-BinnedIsotonic (source-only)", s, "test"))
        p_plloc = sig(ps * P["logit_test"] + pi + off_pl)
        p_raw = sig(P["logit_test"])
        rows.append({"site": str(s), "pooled": brier(p_pool, y), "local": brier(p_loc, y),
                     "srcbin": brier(p_srcbin, y), "plattlocal": brier(p_plloc, y),
                     "raw_pred_sum": float(p_raw.sum()), "pool_pred_sum": float(p_pool.sum()),
                     "loc_pred_sum": float(p_loc.sum()), "y_sum": float(y.sum()), "n": int(len(y))})
    return pd.DataFrame(rows)


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--outdir", type=Path, required=True, help="fresh scratch dir")
    ap.add_argument("--output", type=Path, required=True)
    ap.add_argument("--eicu-dir", type=Path, required=True)
    ap.add_argument("--apache-file", type=Path, required=True, help="the one apachePatientResult file used")
    ap.add_argument("--admissiondx-file", type=Path, default=None, help="optional admissionDx file for the timing audit")
    ap.add_argument("--receipt", type=Path, required=True, help="private host-only receipt with input fingerprints")
    ap.add_argument("--primary-manifest", type=Path, required=True, help="restricted run_manifest.json of the frozen v9 run")
    ap.add_argument("--primary-pairs", type=Path, required=True)
    ap.add_argument("--approved-audit", type=Path, required=True)
    ap.add_argument("--approved-diagnostics", type=Path, required=True)
    a = ap.parse_args()
    if a.output.exists():
        raise FileExistsError(a.output)
    if a.outdir.exists():
        raise FileExistsError(f"scratch directory must be fresh: {a.outdir}")
    if a.outdir.resolve().is_relative_to(a.output.parent.resolve()):
        raise RuntimeError("scratch directory must be outside the release folder")
    if a.receipt.exists() or a.receipt.resolve().is_relative_to(a.output.parent.resolve()):
        raise RuntimeError("private receipt must be new and outside the release folder")
    if not a.apache_file.is_file() or (a.admissiondx_file is not None and not a.admissiondx_file.is_file()):
        raise FileNotFoundError("APACHE or admissionDx input file not found")
    receipt = {"apache_file": str(a.apache_file.resolve()), "apache_sha256": sha256_file(a.apache_file),
               "admissiondx_file": None if a.admissiondx_file is None else str(a.admissiondx_file.resolve()),
               "admissiondx_sha256": None if a.admissiondx_file is None else sha256_file(a.admissiondx_file),
               "script_sha256": sha256_file(Path(__file__)), "notebook_sha256": SHA256}
    run_dir = a.primary_manifest.parent
    if a.primary_pairs.parent.resolve() != run_dir.resolve():
        raise RuntimeError("pairs file and manifest must come from the same frozen v9 output folder")
    manifest = json.loads(a.primary_manifest.read_text())
    audit = load_approved(a.approved_audit, "aggregate_publication_audit_v9.json")
    diag = load_approved(a.approved_diagnostics, "aggregate_calibration_diagnostics_seed7.json")
    md = audit["run_metadata"]
    n_target_approved = diag["target_seed7_methods"]["PrivCal-B (secure-agg isotonic)"]["n_target_hospitals"]
    pairs = pd.read_csv(a.primary_pairs); pairs["site"] = pairs["site"].astype(str)
    if pairs["site"].duplicated().any():
        raise RuntimeError("duplicate hospitals in the primary pairs file")
    primary_sites = set(pairs["site"])
    if len(primary_sites) != audit["primary"]["n_hospitals"]:
        raise RuntimeError("primary pairs file disagrees with the approved primary hospital count")
    ps7 = pd.read_csv(run_dir / "all_per_site_metrics.csv")
    ps7 = ps7[(ps7["backend"] == "tfidf_lr") & (ps7["split_seed"] == 7) & (ps7["method"] == "Uncalibrated")]
    ps7 = ps7.assign(site=ps7["site"].astype(str))
    if ps7["site"].duplicated().any():
        raise RuntimeError("restricted per-hospital output has duplicate seed-7 rows")
    v9_source = set(ps7.loc[ps7["site_type"] == "source", "site"]); v9_target = set(ps7.loc[ps7["site_type"] == "TARGET", "site"])
    if {s for s in v9_target if int(ps7.set_index("site").loc[s, "calib_deaths"]) <= 5} != primary_sites:
        raise RuntimeError("pairs file is not the frozen run's 0-5-death target set")

    os.environ["PRIVCAL_OUTDIR"] = str(a.outdir)
    scope = {"__name__": "__main__", "_APX_EICU_DIR": str(a.eicu_dir)}
    exec(compile(frozen_source_apache(), str(NOTEBOOK), "exec"), scope)   # loads the frozen final cohort from --eicu-dir
    from stratum_calibration_v28a_codex import verify_primary_provenance
    verify_primary_provenance(scope, manifest)          # input fingerprints, software, rows, sites, real CKKS
    data = scope["data"]
    if len(data) != md["rows"] or len(scope["SITES"]) != md["sites"]:
        raise RuntimeError("final cohort differs from the approved run (rows or hospitals)")
    cohort_ids = pd.Index(data["patientunitstayid"].unique())
    if len(cohort_ids) != len(data):
        raise RuntimeError("duplicated stays in the final cohort")
    P, elig, private_counts = load_apache(a.apache_file, cohort_ids)
    receipt["private_counts"] = private_counts
    scope["_APACHE_P"], scope["_APX_EPS"] = P, EPS
    res = scope["run_one_split"]("tfidf_lr", 7, make_figures=False)
    info = scope["_APX_INFO"]

    # ---- gates: the frozen partition and assignments are unchanged ----
    if len(info["target0"]) != n_target_approved or len(info["source0"]) + len(info["target0"]) != md["sites"]:
        raise RuntimeError("seed-7 source/target partition differs from the approved run")
    if set(map(str, info["source0"])) != v9_source or set(map(str, info["target0"])) != v9_target:
        raise RuntimeError("seed-7 source/target hospital sets differ from the restricted v9 output")
    lab = data.set_index("patientunitstayid")["label"]
    low0 = {str(s) for s in info["target0"] if int(lab.loc[list(info["before"][s]["calib"])].sum()) <= 5}
    if low0 != primary_sites:
        raise RuntimeError("original 0-5-death target set, rebuilt from the frozen split, differs from the pairs file")
    elig_ids = set(P.index)
    for s in scope["SITES"]:
        for k in ("train", "calib", "test"):
            if set(res["parts"][s][k]["patientunitstayid"]) != info["before"][s][k] & elig_ids:
                raise RuntimeError("an eligible stay changed its split assignment; stop")
    dropped = set(map(str, info["dropped"]))
    low = [str(s) for s in res["TARGET"] if int(res["parts"][s]["y_calib"].sum()) <= 5]
    hosp = {"hospitals_in_frozen_partition": {"source": len(info["source0"]), "target": len(info["target0"])},
            "hospitals_dropped_no_eligible_calibration_or_test_stays": {
                "source": band_h(len(dropped & set(map(str, info["source0"])))),
                "target": band_h(len(dropped & set(map(str, info["target0"]))))},
            "target_hospitals_analysed": (len(res["TARGET"]) if not 0 < len(dropped & set(map(str, info["target0"]))) < MIN_HOSP
                                          else "withheld (linked to a banded dropped count)"),
            "stratum_hospitals_0_5_eligible_calibration_deaths": band_h(len(low)),
            "stratum_overlap_with_original_primary_hospitals": overlap_release(len(set(low) & primary_sites), len(primary_sites), len(low)),
            "original_primary_hospitals_dropped": band_h(len(primary_sites & dropped))}
    out = {"purpose": "post hoc secondary analysis: recalibration of the recorded APACHE IVa hospital-mortality prediction; "
                      "frozen v9 primary unchanged",
           "eligibility": elig, "hospitals": hosp,
           "admission_diagnosis_timing_audit": admission_dx_audit(a.admissiondx_file, P.index),
           "selection_coverage": coverage(data, P.index, {"original_primary_hospitals": primary_sites,
                                                          "apache_stratum_hospitals": set(low)}),
           "input_receipt": "input fingerprints recorded in a private receipt on the authorized host"}
    if len(low) >= MIN_HOSP:
        W = site_scores(scope, res, low)
        ys, n = float(W.y_sum.sum()), int(W.n.sum())
    if len(low) >= MIN_HOSP and ys >= MIN_CELL and n - ys >= MIN_CELL:
        out["stratum"] = {
            "n_hospitals": int(len(W)), "test_stays": band(n),
            "observed_mortality_percent": round(100 * ys / n, 1),
            "mean_predicted_percent": {"apache_uncalibrated": round(100 * W.raw_pred_sum.sum() / n, 1),
                                       "pooled_map": round(100 * W.pool_pred_sum.sum() / n, 1),
                                       "local_intercept": round(100 * W.loc_pred_sum.sum() / n, 1)},
            "mean_Brier": {k: float(W[k].mean()) for k in ("pooled", "local", "srcbin", "plattlocal")},
            "contrast_local_minus_pooled": boot((W.local - W.pooled).to_numpy(float), SEEDS["local"]),
            "contrast_source_binned_minus_pooled": boot((W.srcbin - W.pooled).to_numpy(float), SEEDS["srcbin"]),
            "contrast_source_platt_local_minus_pooled": boot((W.plattlocal - W.pooled).to_numpy(float), SEEDS["plattlocal"])}
    else:
        out["stratum"] = {"n_hospitals": band_h(len(low)),
                          "note": f"fewer than {MIN_HOSP} stratum hospitals, or fewer than {MIN_CELL} deaths or survivors "
                                  "in its test stays; metrics withheld"}
    out["notes"] = ["Differences are comparator Brier minus pooled Brier; positive favors pooling.",
                    "Secondary and post hoc; the eligible population and hospital set differ from the primary analysis, "
                    "so differences from it are not a controlled effect of the base model.",
                    "No claim that the stored APACHE IVa score was available at the 24-hour landmark.",
                    f"Stay counts 1-{MIN_CELL - 1} and hospital counts 1-{MIN_HOSP - 1} are banded. No hospital-level values are included. "
                    "Not a formal privacy guarantee. "
                    "Exact-output cross-release disclosure review is required before release."]
    a.output.write_text(json.dumps(out, indent=2, allow_nan=False) + "\n")
    receipt.update(output=str(a.output.resolve()), output_sha256=sha256_file(a.output))
    a.receipt.write_text(json.dumps(receipt, indent=2) + "\n")
    print(f"Saved on authorized host (release requires human approval): {a.output}")


if __name__ == "__main__":
    main()
