#!/usr/bin/env python3
"""Two reviewer-requested sensitivity analyses on the frozen v9 seed-7 split (authorized host only).

Aggregate-only outputs; the frozen v9 primary analysis is unchanged and remains primary.

Gate (fails closed): the in-memory rerun must reproduce the approved primary: the same 26-hospital
set as the restricted pairs file, each hospital's pooled and local Brier score within 1e-9 of that
file, and the same mean and 95% interval (2,000 paired
hospital resamples, bootstrap seed 971) within 1e-9. A fresh run re-encrypts with new CKKS
randomness, so pooled score sums (and hence Brier scores) differ from the frozen run by about 1e-11;
1e-9 is far above that noise and far below the reported precision (0.1e-3). The discharge-offset flags must reproduce
the approved counts (43 and 962).

A. Discharge-offset audit. Stays with recorded hospital discharge before the 24-hour landmark
   ("early") or before unit discharge ("order") are counted within the 0-5-death primary
   hospitals, overall and in their test sets. Two sensitivities of the primary contrast (local
   intercept minus pooled binned isotonic, Brier), both on the original 26 hospitals:
   A1 evaluation-only: flagged stays removed from test sets; model and maps unchanged (seed 990);
   A2 full pipeline: each stay keeps its original seed-7 development/calibration/test group;
      flagged stays are dropped from those fixed groups before the predictor and every calibrator
      are refitted (checked: all unaffected stays keep their groups) (seed 994); low-event
      membership changes are reported separately.
   Each also reports the paired change from the frozen contrast (seeds 995, 996).
B. Unweighted base model. The same TF-IDF logistic regression is refitted without class
   weighting (only change: class_weight="balanced" -> None), then the same pipeline runs for
   seed 7. For the same 0-5-death hospitals: the primary contrast and the two source-based
   controls (source-only binned isotonic; source Platt plus local intercept), with bootstrap
   seeds 991, 992 and 993; absolute hospital-macro Brier scores; the paired change in the
   pooled-versus-local contrast between weighted and unweighted pipelines (seed 997); and mean
   predicted versus observed risk of the uncalibrated model. Every calibrator is refitted.

Disclosure rule (not a formal guarantee): counts of flagged stays from 1 to 19 are reported
as "1-19"; hospital-level values never leave the host. A responsible person must approve release.
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
B = 2000
TOL = 1e-9
WEIGHTED = 'class_weight="balanced", solver="liblinear"'
UNWEIGHTED = 'class_weight=None, solver="liblinear"'


def load_approved(path: Path, name: str, expected: dict = APPROVED_SHA256) -> dict:
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != expected[name]:
        raise RuntimeError(f"{path} is not the approved {name} (SHA-256 mismatch)")
    return json.loads(raw)


def band(n: int):
    return n if (n == 0 or n >= MIN_CELL) else f"1-{MIN_CELL - 1}"


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


HOOK_AT = "    parts = train_backend_and_add_logits(backend, parts, SOURCE, split_seed)"
HOOK = ("    if '_EXCLUDE_IDS' in globals():\n"
        "        for _s in SITES:\n"
        "            for _k in ('train', 'calib', 'test'):\n"
        "                _g = parts[_s][_k]\n"
        "                parts[_s][_k] = _g[~_g['patientunitstayid'].isin(_EXCLUDE_IDS)].copy()\n")


def frozen_source(unweighted: bool, exclusion_hook: bool = False) -> str:
    raw = NOTEBOOK.read_bytes()
    if hashlib.sha256(raw).hexdigest() != SHA256:
        raise RuntimeError("Unexpected v9 notebook")
    src = "\n".join("".join(c["source"]) for c in json.loads(raw)["cells"] if c["cell_type"] == "code")
    before, sep, _ = src.partition("# 9. Run all backends and splits")
    if not sep:
        raise ValueError("Cannot isolate the v9 loader and split")
    if before.count(WEIGHTED) != 1:
        raise RuntimeError("Expected exactly one class-weighted TF-IDF logistic regression")
    if unweighted:
        before = before.replace(WEIGHTED, UNWEIGHTED)
    if exclusion_hook:
        if before.count(HOOK_AT) != 1:
            raise RuntimeError("Cannot place the exclusion hook uniquely")
        before = before.replace(HOOK_AT, HOOK + HOOK_AT)
    return instrument(before)


def run(src: str, outdir: Path) -> tuple[dict, dict]:
    os.environ["PRIVCAL_OUTDIR"] = str(outdir)
    scope = {"__name__": "__main__"}
    exec(compile(src, str(NOTEBOOK), "exec"), scope)
    return scope, scope["run_one_split"]("tfidf_lr", 7, make_figures=False)


def site_scores(scope: dict, res: dict, sites: list[str], keep=None) -> pd.DataFrame:
    """Per-hospital test Brier scores for the primary and control methods (host only)."""
    sig, fri, brier, nll = scope["sigmoid"], scope["fit_regularized_intercept"], scope["brier"], scope["nll"]
    from scipy.optimize import minimize_scalar
    parts, T = res["parts"], res["T_src"]
    ps, pi = res["platt_slope"], res["platt_intercept"]
    rows = []
    for s in sites:
        P = parts[s]; y = np.asarray(P["y_test"], float)
        m = np.ones(len(y), bool) if keep is None else keep(s)
        if m.sum() == 0:
            continue
        zc, yc = P["logit_calib"] / T, P["y_calib"]
        off = fri(zc, yc, 2.0)
        off_pl = float(minimize_scalar(lambda a: len(yc) * nll(sig(ps * zc * T + pi + a), yc) + 2 * a * a,
                                       bounds=(-8, 8), method="bounded").x)
        p_pool = np.asarray(res["predict_fn"]("PrivCal-B (secure-agg isotonic)", s, "test"))
        p_loc = sig(P["logit_test"] / T + off)
        p_srcbin = np.asarray(res["predict_fn"]("Global-BinnedIsotonic (source-only)", s, "test"))
        p_plloc = sig(ps * P["logit_test"] + pi + off_pl)
        p_raw = sig(P["logit_test"])
        rows.append({"site": str(s), "pooled": brier(p_pool[m], y[m]), "local": brier(p_loc[m], y[m]),
                     "srcbin": brier(p_srcbin[m], y[m]), "plattlocal": brier(p_plloc[m], y[m]),
                     "raw_pred_sum": float(p_raw[m].sum()), "pool_pred_sum": float(p_pool[m].sum()),
                     "loc_pred_sum": float(p_loc[m].sum()), "y_sum": float(y[m].sum()), "n": int(m.sum())})
    return pd.DataFrame(rows)


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--outdir", type=Path, required=True, help="fresh scratch dir (two subfolders are created)")
    ap.add_argument("--output", type=Path, required=True)
    ap.add_argument("--patient", type=Path, required=True)
    ap.add_argument("--primary-manifest", type=Path, required=True)
    ap.add_argument("--primary-pairs", type=Path, required=True)
    ap.add_argument("--approved-audit", type=Path, required=True)
    ap.add_argument("--approved-diagnostics", type=Path, required=True)
    a = ap.parse_args()
    if a.output.exists():
        raise FileExistsError(a.output)
    audit = load_approved(a.approved_audit, "aggregate_publication_audit_v9.json")
    diag = load_approved(a.approved_diagnostics, "aggregate_calibration_diagnostics_seed7.json")
    AP = audit["primary"]
    from stratum_calibration_v28a_codex import verify_primary_provenance
    pairs = pd.read_csv(a.primary_pairs); pairs["site"] = pairs["site"].astype(str)
    primary_sites = set(pairs["site"])
    if len(primary_sites) != AP["n_hospitals"]:
        raise RuntimeError("primary pairs file disagrees with the approved primary hospital count")

    # ---- frozen weighted model: reproduce the approved primary exactly ----
    scope, res = run(frozen_source(False), a.outdir / "weighted")
    verify_primary_provenance(scope, json.loads(a.primary_manifest.read_text()))
    low = [str(s) for s in res["TARGET"] if int(res["parts"][s]["y_calib"].sum()) <= 5]
    if set(low) != primary_sites:
        raise RuntimeError("rerun 0-5 stratum differs from the frozen primary hospital set")
    W = site_scores(scope, res, low)
    rep = boot((W.local - W.pooled).to_numpy(float), 971)
    if rep["n_hospitals"] != AP["n_hospitals"] or abs(rep["mean"] - AP["mean_comparator_minus_method_Brier"]) > TOL or \
            any(abs(x - y) > TOL for x, y in zip(rep["ci95"], AP["paired_hospital_bootstrap_95_CI"])):
        raise RuntimeError("rerun does not reproduce the approved primary estimate; stop: "
                           + repr((rep, AP["mean_comparator_minus_method_Brier"], AP["paired_hospital_bootstrap_95_CI"])))
    chk = W.merge(pairs[["site", "secure_agg_Brier", "local_intercept_Brier"]], on="site", validate="one_to_one")
    if len(chk) != len(W) or (chk.pooled - chk.secure_agg_Brier).abs().max() > TOL or (chk.local - chk.local_intercept_Brier).abs().max() > TOL:
        raise RuntimeError("rerun hospital scores differ from the restricted primary pairs file; stop")
    reproduction = {"per_hospital_scores_match_pairs_file": True,"max_abs_difference_from_approved_summary": max([abs(rep["mean"] - AP["mean_comparator_minus_method_Brier"])]
                    + [abs(x - y) for x, y in zip(rep["ci95"], AP["paired_hospital_bootstrap_95_CI"])]), "tolerance": TOL}

    # ---- A. discharge-offset audit ----
    pt = pd.read_csv(a.patient, low_memory=False)
    if pt["patientunitstayid"].duplicated().any():
        raise RuntimeError("patient table has duplicated patientunitstayid")
    off = pt.set_index("patientunitstayid")[["hospitaldischargeoffset", "unitdischargeoffset"]]
    data = scope["data"]
    d = data[["patientunitstayid", "site"]].join(off, on="patientunitstayid")
    if d[["hospitaldischargeoffset", "unitdischargeoffset"]].isna().any().any():
        raise RuntimeError("missing discharge offsets in the final cohort")
    early = d.hospitaldischargeoffset < 1440
    order = d.hospitaldischargeoffset < d.unitdischargeoffset
    doa = diag["unit_types"]["discharge_offset_audit"]
    if int(early.sum()) != doa["hospital_discharge_before_24_hour_landmark"] or \
            int(order.sum()) != doa["hospital_discharge_before_unit_discharge"]:
        raise RuntimeError(f"discharge-offset flags do not reproduce the approved counts: {int(early.sum())}, {int(order.sum())}")
    flagged = set(d.loc[early | order, "patientunitstayid"])
    in_low = d.site.astype(str).isin(low)
    test_ids = set(np.concatenate([res["parts"][s]["test"]["patientunitstayid"].values for s in low]))
    in_test = d.patientunitstayid.isin(test_ids)
    keep = lambda s: ~res["parts"][s]["test"]["patientunitstayid"].isin(flagged).to_numpy()
    WA = site_scores(scope, res, low, keep)
    lost = len(low) - len(WA)
    base = (W.set_index("site").local - W.set_index("site").pooled)
    dA1 = (WA.set_index("site").local - WA.set_index("site").pooled)
    # A2: full pipeline without flagged stays (same hospitals and seed; splits change because rows change)
    # A2 keeps every stay's original seed-7 development/calibration/test assignment, drops flagged
    # stays from those fixed groups, then refits the predictor and every calibrator.
    scopeF = {"__name__": "__main__"}
    os.environ["PRIVCAL_OUTDIR"] = str(a.outdir / "flagged_removed")
    exec(compile(frozen_source(False, exclusion_hook=True), str(NOTEBOOK), "exec"), scopeF)
    scopeF["_EXCLUDE_IDS"] = set(flagged)
    resF = scopeF["run_one_split"]("tfidf_lr", 7, make_figures=False)
    if [str(x) for x in resF["TARGET"]] != [str(x) for x in res["TARGET"]]:
        raise RuntimeError("source/target partition changed; stop")
    for s_ in scope["SITES"]:
        for k in ("train", "calib", "test"):
            before_ids = set(res["parts"][s_][k]["patientunitstayid"]) - flagged
            if set(resF["parts"][s_][k]["patientunitstayid"]) != before_ids:
                raise RuntimeError("an unaffected stay changed its split assignment; stop")
            if len(resF["parts"][s_][k]) == 0:
                raise RuntimeError("a hospital lost an entire split group; stop and review")
    WF = site_scores(scopeF, resF, low)
    dA2 = (WF.set_index("site").local - WF.set_index("site").pooled)
    lowF = {str(s) for s in resF["TARGET"] if int(resF["parts"][s]["y_calib"].sum()) <= 5}
    A = {"flag_counts_final_cohort": {"early_hospital_discharge": int(early.sum()), "discharge_before_unit_discharge": int(order.sum()),
                                      "either": int((early | order).sum())},
         "flag_counts_primary_hospitals_all_stays": {"early": band(int((early & in_low).sum())), "order": band(int((order & in_low).sum())),
                                                    "either": band(int(((early | order) & in_low).sum()))},
         "flag_counts_primary_hospitals_test_stays": {"early": band(int((early & in_test).sum())), "order": band(int((order & in_test).sum())),
                                                     "either": band(int(((early | order) & in_test).sum()))},
         "A1_evaluation_only": {"primary_contrast": boot(dA1.to_numpy(float), 990),
                                "paired_change_from_frozen": boot((dA1 - base.loc[dA1.index]).to_numpy(float), 995),
                                "hospitals_losing_entire_test_set": lost},
         "A2_full_pipeline": {"primary_contrast_original_26": boot(dA2.loc[low].to_numpy(float), 994),
                              "paired_change_from_frozen": boot((dA2.loc[low] - base.loc[low]).to_numpy(float), 996),
                              "mean_Brier_original_26": {"pooled": float(WF.pooled.mean()), "local": float(WF.local.mean())},
                              "low_event_membership": {"n_low_event_after_removal": len(lowF), "n_original_still_low_event": len(lowF & set(low)),
                                                       "n_new_low_event": len(lowF - set(low))}},
         "note": "A1 removes flagged stays from evaluation only; A2 keeps original split assignments, drops flagged stays from them, and refits the predictor and all calibrators."}

    # ---- B. unweighted base model ----
    scopeU, resU = run(frozen_source(True), a.outdir / "unweighted")
    lowU = [str(s) for s in resU["TARGET"] if int(resU["parts"][s]["y_calib"].sum()) <= 5]
    if set(lowU) != primary_sites:
        raise RuntimeError("unweighted run changed the 0-5 hospital set (split should be identical)")
    U = site_scores(scopeU, resU, lowU)
    ys, n = float(U.y_sum.sum()), int(U.n.sum())
    Bres = {"n_hospitals": int(len(U)), "test_stays": n,
            "observed_mortality_percent": round(100 * ys / n, 1) if ys >= MIN_CELL and n - ys >= MIN_CELL else "withheld",
            "mean_predicted_percent": {"uncalibrated": round(100 * U.raw_pred_sum.sum() / n, 1),
                                       "pooled_map": round(100 * U.pool_pred_sum.sum() / n, 1),
                                       "local_intercept": round(100 * U.loc_pred_sum.sum() / n, 1)},
            "mean_Brier": {k: float(U[k].mean()) for k in ("pooled", "local", "srcbin", "plattlocal")},
            "contrast_local_minus_pooled": boot((U.local - U.pooled).to_numpy(float), 991),
            "contrast_source_binned_minus_pooled": boot((U.srcbin - U.pooled).to_numpy(float), 992),
            "contrast_source_platt_local_minus_pooled": boot((U.plattlocal - U.pooled).to_numpy(float), 993),
            "paired_change_in_local_minus_pooled_unweighted_minus_weighted": boot(
                ((U.set_index("site").local - U.set_index("site").pooled).loc[low] - base.loc[low]).to_numpy(float), 997),
            "weighted_reference_same_code": {"local_minus_pooled": rep,
                                             "mean_Brier": {k: float(W[k].mean()) for k in ("pooled", "local", "srcbin", "plattlocal")},
                                             "source_binned_minus_pooled_mean": float((W.srcbin - W.pooled).mean()),
                                             "source_platt_local_minus_pooled_mean": float((W.plattlocal - W.pooled).mean())}}
    out = {"purpose": "reviewer-requested sensitivity analyses (secondary, post hoc); frozen v9 primary unchanged",
           "primary_reproduced": reproduction, "discharge_audit": A, "unweighted_base_model": Bres,
           "notes": ["Differences are local-or-source comparator Brier minus pooled Brier; positive favors pooling.",
                     f"Counts 1-{MIN_CELL - 1} are banded. No hospital-level values are included. Not a formal privacy guarantee."]}
    a.output.write_text(json.dumps(out, indent=2, allow_nan=False) + "\n")
    print(f"Saved on authorized host (release requires human approval): {a.output}")


if __name__ == "__main__":
    main()
