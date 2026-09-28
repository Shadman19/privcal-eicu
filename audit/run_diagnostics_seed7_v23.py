#!/usr/bin/env python3
"""Seed-7 aggregate calibration and selected-unit audit on the authorized host.

Executes a reviewed v9 analysis in a fresh directory, injecting an in-memory
return of fitted predictions. No restricted record, hospital identifier, site
score, or source-data fingerprint is written to the transferable JSON.

This v23 supplementary copy adds an independent plaintext denominator check
for the pooled temperature curve and prevents exact small reliability-bin
counts from appearing in the aggregate export. It does not change the frozen
v9 notebook.
"""

from __future__ import annotations

import hashlib
import json
import os
import time
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.optimize import minimize
from sklearn.isotonic import IsotonicRegression


NOTEBOOK = Path("PrivCal_eICU_reviewer_sensitivities_v9.ipynb")
SHA256 = "23d0ca0666fd68e040bd6a39d6e3361b2ba0c0502b39cc01f88cfa4baa807b75"
OUTDIR = Path(os.environ.get("PRIVCAL_OUTDIR", "./privcal_eicu_diagnostics_" +
                             time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())))


def calibration_regression(p: np.ndarray, y: np.ndarray) -> dict:
    """Descriptive patient-pooled calibration intercept/slope, not site inference."""
    p = np.asarray(p, dtype=float)
    y = np.asarray(y, dtype=int)
    if p.ndim != 1 or len(p) != len(y) or not np.isfinite(p).all():
        raise ValueError("Invalid predictions or labels")
    if len(p) < 20 or np.unique(y).size != 2:
        return {"status": "insufficient pooled outcomes"}
    q = np.clip(p, 1e-6, 1 - 1e-6)
    logit = np.log(q / (1 - q))

    def loss(v):
        z = v[0] + v[1] * logit
        return float(np.sum(np.logaddexp(0, z) - y * z))

    fit = minimize(loss, x0=np.array([0., 1.]), method="L-BFGS-B",
                   bounds=[(-15, 15), (-10, 10)])
    if not fit.success or not np.isfinite(fit.x).all():
        return {"status": "optimization failed"}
    return {"status": "descriptive pooled fit", "intercept": float(fit.x[0]),
            "slope": float(fit.x[1]), "clipped_probabilities": int(np.sum(p != q)),
            "bounds": "intercept [-15,15], slope [-10,10], logit clip [1e-6,1-1e-6]"}


def reliability_bins(p: np.ndarray, y: np.ndarray, min_count: int = 20) -> list[dict]:
    """Fixed 12-bin diagram, with count and complementary suppression.

    If exactly one bin is small, hiding its count alone is ineffective because
    the exported total test count and the other 11 counts reveal it. Hide the
    smallest eligible large bin as well in that case. This limits direct
    subtraction, without claiming a formal disclosure guarantee.
    """
    p = np.asarray(p, dtype=float)
    y = np.asarray(y, dtype=int)
    ids = np.minimum((np.clip(p, 0, 1) * 12).astype(int), 11)
    counts = np.bincount(ids, minlength=12)
    if int(counts.sum()) != len(p):
        raise AssertionError("Test-prediction bin coverage failed")
    small = set(int(b) for b in np.flatnonzero(counts < min_count))
    hidden = set(small)
    if len(small) == 1:
        eligible = np.flatnonzero(counts >= min_count)
        if eligible.size:
            hidden.add(min(map(int, eligible), key=lambda b: (int(counts[b]), b)))
    entries = []
    for b in range(12):
        mask = ids == b
        count = int(counts[b])
        suppressed = b in hidden
        row = {"bin": b, "lower": b / 12, "upper": (b + 1) / 12,
               "n_target_test_stays": None if suppressed else count,
               "suppressed": suppressed}
        if suppressed:
            row["suppression_reason"] = "small_cell" if b in small else "complementary"
        else:
            row.update(mean_predicted=float(p[mask].mean()),
                       observed_death_fraction=float(y[mask].mean()))
        entries.append(row)
    return entries


def safe_unit_category_summary(counts: pd.Series, min_count: int = 20) -> dict:
    """Withhold a unit-type distribution if any category is small.

    The total selected cohort is included elsewhere in the diagnostic.
    Publishing every large category count plus a small-cell total can reveal
    the last category by subtraction. A responsible host reviewer may make
    broader, context-aware category groups before approving a later release.
    """
    if counts.empty or np.any(counts.to_numpy(dtype=int) < min_count):
        return {"status": "distribution_withheld_for_host_side_grouping",
                "category_counts_released": False}
    return {"status": "all_categories_at_least_threshold",
            "category_counts_released": True,
            "categories": {str(k): int(v) for k, v in counts.items()}}


def selected_unit_types(data: pd.DataFrame, input_dir: str, file_locator) -> dict:
    patient_path = file_locator(input_dir, "patient")
    wanted = {"patientunitstayid", "unittype", "unitstaytype", "hospitaldischargestatus",
              "hospitaldischargeoffset", "unitdischargeoffset", "uniquepid",
              "patienthealthsystemstayid"}
    pat = pd.read_csv(patient_path, usecols=lambda col: col.lower() in wanted,
                      low_memory=False)
    pat.columns = pat.columns.str.lower()
    if "patientunitstayid" not in pat or pat.patientunitstayid.duplicated().any():
        raise ValueError("Patient stay ID absent or repeated")
    if "hospitaldischargestatus" not in pat:
        raise ValueError("Hospital-discharge outcome status is absent")
    available = [x for x in ("unittype", "unitstaytype") if x in pat.columns]
    if not available:
        raise ValueError("Neither eICU unitType nor unitStayType is present")
    optional = [x for x in ("hospitaldischargeoffset", "unitdischargeoffset",
                           "uniquepid", "patienthealthsystemstayid") if x in pat.columns]
    final = data[["patientunitstayid", "label"]].merge(
             pat[["patientunitstayid", "hospitaldischargestatus"] + optional + available],
             on="patientunitstayid", how="left", validate="one_to_one", indicator=True)
    if len(final) != len(data) or (final["_merge"] != "both").any():
        raise ValueError("Unit-type audit failed to cover the final eligible cohort")
    status = final["hospitaldischargestatus"].astype(str).str.strip().str.lower()
    if not status.isin(("alive", "expired")).all():
        raise ValueError("Unexpected outcome code in final eligible cohort; audit the primary label rule")
    if not (final["label"].to_numpy() == (status == "expired").to_numpy(dtype=int)).all():
        raise ValueError("The final analysis labels disagree with eICU outcome codes")
    result = {"denominator_selected_stays": int(len(final)),
              "selected_hospital_deaths": int((status == "expired").sum()),
              "outcome_code_audit_passed": True, "fields": {}}
    if {"hospitaldischargeoffset", "unitdischargeoffset"}.issubset(optional):
        hospital = pd.to_numeric(final["hospitaldischargeoffset"], errors="coerce")
        unit = pd.to_numeric(final["unitdischargeoffset"], errors="coerce")
        result["discharge_offset_audit"] = {
            "missing_hospital_or_unit_offset": int((hospital.isna() | unit.isna()).sum()),
            "hospital_discharge_before_24_hour_landmark": int((hospital < 1440).sum()),
            "hospital_discharge_before_unit_discharge": int((hospital < unit).sum()),
        }
    if {"uniquepid", "patienthealthsystemstayid"}.issubset(optional):
        n_admissions = pat.groupby("uniquepid")["patienthealthsystemstayid"].nunique()
        multiple_ids = set(n_admissions.index[n_admissions > 1])
        result["patients_with_multiple_recorded_hospital_admissions"] = {
            "among_all_raw_unique_patients": int(len(multiple_ids)),
            "selected_final_cohort_patients": int(final["uniquepid"].isin(multiple_ids).sum()),
            "limitation": "Admission IDs cannot be chronologically ordered across separate admissions.",
        }
    for col in available:
        counts = final[col].fillna("missing").astype(str).str.strip().str.lower().value_counts()
        result["fields"][col] = safe_unit_category_summary(counts)
    return result


def descriptive_metrics(result: dict, scope: dict) -> dict:
    parts = result["parts"]
    predict = result["predict_fn"]
    sites = result["TARGET"]
    if len(sites) < 5:
        raise ValueError("At least five target hospitals required for aggregate diagnostics")
    methods = ("PrivCal-B (secure-agg isotonic)", "Global-Platt (source-only)",
               "Local-intercept (source-T)")
    output = {}
    for method in methods:
        site_means = []
        pred, labels = [], []
        for site in sites:
            y = np.asarray(parts[site]["y_test"], dtype=int)
            if method == "Local-intercept (source-T)":
                offset = scope["fit_regularized_intercept"](
                    parts[site]["logit_calib"] / result["T_src"],
                    parts[site]["y_calib"], 2.)
                p = scope["sigmoid"](parts[site]["logit_test"] / result["T_src"] + offset)
            else:
                p = predict(method, site, "test")
            p = np.asarray(p, dtype=float)
            if len(p) != len(y) or not np.isfinite(p).all() or np.any((p < 0) | (p > 1)):
                raise ValueError("Invalid held-out probabilities")
            site_means.append(float(y.mean() - p.mean()))
            pred.append(p)
            labels.append(y)
        p = np.concatenate(pred)
        y = np.concatenate(labels)
        zeros = int(np.sum(p == 0))
        ones = int(np.sum(p == 1))
        output[method] = {
            "n_target_hospitals": len(sites), "n_test_stays": len(y),
            "n_test_deaths": int(y.sum()),
            "patient_pooled_mean_predicted": float(p.mean()),
            "patient_pooled_observed_fraction": float(y.mean()),
            "hospital_macro_observed_minus_predicted": float(np.mean(site_means)),
            "patient_pooled_calibration_regression": calibration_regression(p, y),
            "exact_zero_count": zeros if zeros >= 5 else "suppressed if <5",
            "exact_one_count": ones if ones >= 5 else "suppressed if <5",
            "reliability_equal_width_bins": reliability_bins(p, y),
        }
    return output


def encrypted_plaintext_fidelity(result: dict, scope: dict) -> dict:
    """One-host arithmetic check; this is not a security proof."""
    bins = [result["site_bins_fn"](s) for s in scope["SITES"]]
    n = np.sum([x[0] for x in bins], axis=0)
    deaths = np.sum([x[1] for x in bins], axis=0)
    score_sums = np.sum([x[2] for x in bins], axis=0)
    encrypted_n = np.asarray(result["encrypted_N"], dtype=int)
    encrypted_deaths = np.asarray(result["encrypted_POS"], dtype=int)
    encrypted_scores = np.asarray(result["encrypted_CS"], dtype=float)
    if not (np.array_equal(encrypted_n, n) and np.array_equal(encrypted_deaths, deaths)):
        raise AssertionError("CKKS-rounded counts or deaths differ from the plaintext reference")
    if not np.isfinite(encrypted_scores).all():
        raise AssertionError("Nonfinite decrypted CKKS score sum")
    occupied = n > 0
    plain_map = IsotonicRegression(out_of_bounds="clip").fit(
        np.clip(score_sums[occupied] / n[occupied], 0, 1),
        deaths[occupied] / n[occupied], sample_weight=n[occupied])
    diffs = []
    for s in result["TARGET"]:
        p = scope["sigmoid"](result["parts"][s]["logit_test"])
        diffs.append(np.abs(result["encrypted_map"].predict(p) - plain_map.predict(p)))
    all_diffs = np.concatenate(diffs)
    return {"rounded_count_max_abs_error": int(np.max(np.abs(encrypted_n - n))),
            "rounded_death_max_abs_error": int(np.max(np.abs(encrypted_deaths - deaths))),
            "decrypted_score_sum_max_abs_error": float(np.max(np.abs(encrypted_scores - score_sums))),
            "held_out_map_prediction_max_abs_error": float(all_diffs.max()),
            "held_out_map_prediction_mean_abs_error": float(all_diffs.mean()),
            "n_held_out_target_predictions_compared": int(len(all_diffs)),
            "scope": "single-host plaintext comparison, not a distributed security or privacy guarantee"}


def independent_temperature_fidelity(result: dict) -> dict:
    """Compare CKKS normalization against an independently counted denominator.

    The frozen v9 HE-error scalar normalizes *both* curves by its decrypted
    count. It cannot reveal error in that count even when the loss sums match.
    The selected grid temperature is invariant to a common positive divisor;
    this extra scalar check concerns numerical fidelity, not fitted T.
    """
    exact = float(result["plaintext_temperature_count"])
    encrypted = float(result["encrypted_temperature_count"])
    encrypted_sum = np.asarray(result["encrypted_temperature_loss_sum"], dtype=float)
    plaintext_sum = np.asarray(result["plaintext_temperature_loss_sum"], dtype=float)
    if encrypted_sum.shape != plaintext_sum.shape or encrypted_sum.ndim != 1 or not encrypted_sum.size:
        raise ArithmeticError("Invalid pooled temperature loss curves")
    if not all(np.isfinite(x) for x in (exact, encrypted)) or not np.isfinite(encrypted_sum).all() or not np.isfinite(plaintext_sum).all():
        raise ArithmeticError("Nonfinite pooled temperature diagnostic")
    if exact <= 0 or encrypted <= 0:
        raise ArithmeticError("Invalid pooled temperature diagnostic")
    shared_count_error = float(np.max(np.abs(encrypted_sum / encrypted - plaintext_sum / encrypted)))
    curve_error = float(np.max(np.abs(encrypted_sum / encrypted - plaintext_sum / exact)))
    if not np.isclose(shared_count_error, float(result["he_err"]), rtol=1e-8, atol=1e-12):
        raise ArithmeticError("Recomputed frozen v9 loss error differs from its reported value")
    absolute_error = abs(encrypted - exact)
    return {
        "decrypted_count_absolute_error": absolute_error,
        "decrypted_count_relative_error": absolute_error / exact,
        "decrypted_count_rounds_to_exact_integer": bool(round(encrypted) == round(exact)),
        "legacy_shared_denominator_curve_max_abs_error": shared_count_error,
        "encrypted_vs_independently_normalized_plaintext_curve_max_abs_error": curve_error,
        "requires_review": bool(absolute_error > 1e-3 or curve_error > 1e-3),
        "scope": "seed-7 TF-IDF supplementary arithmetic check only; not five-split validation or a security proof",
    }


def instrument_return(source: str) -> str:
    """Add in-memory diagnostics to the exact reviewed seed-7 return."""
    old = "return dict(backend=backend, split_seed=split_seed, SOURCE=SOURCE, TARGET=TARGET,"
    if source.count(old) != 1:
        raise RuntimeError("Unexpected frozen v9 return statement")
    return source.replace(old,
        "return dict(parts=parts, predict_fn=predict, site_bins_fn=site_bins, "
        "encrypted_N=N, encrypted_POS=POS, encrypted_CS=CS, encrypted_map=iso_he, "
        "encrypted_temperature_count=float(tot), "
        "plaintext_temperature_count=float(np.sum([c[0] for c in counts])), "
        "encrypted_temperature_loss_sum=agg, "
        "plaintext_temperature_loss_sum=np.sum(np.stack(curves), axis=0), "
        "backend=backend, split_seed=split_seed, SOURCE=SOURCE, TARGET=TARGET,")


def main() -> None:
    raw = NOTEBOOK.read_bytes()
    if hashlib.sha256(raw).hexdigest() != SHA256:
        raise RuntimeError("Unexpected v9 notebook; use the frozen verified source package")
    source = "\n".join("".join(c["source"]) for c in json.loads(raw)["cells"]
                       if c["cell_type"] == "code")
    before, boundary, _ = source.partition("# 9. Run all backends and splits")
    if not boundary:
        raise ValueError("Cannot isolate seed-7 v9 methods")
    before = instrument_return(before)
    if OUTDIR.exists():
        raise FileExistsError(f"Refusing to mix results in {OUTDIR}")
    os.environ["PRIVCAL_OUTDIR"] = str(OUTDIR)
    scope = {"__name__": "__main__"}
    exec(compile(before, str(NOTEBOOK), "exec"), scope)
    result = scope["run_one_split"]("tfidf_lr", 7, make_figures=False)
    (OUTDIR / "restricted_input_provenance_do_not_transfer.json").write_text(json.dumps({
        "notebook_sha256": SHA256,
        "input_fingerprints": scope["input_fingerprints"],
        "software_versions": scope["software_versions"],
        "source_site_order": "frozen v9 sorted tuple",
    }, indent=2) + "\n")
    unit_types = selected_unit_types(scope["data"], scope["CFG"]["eicu_dir"],
                                     scope["required_input_path"])
    report = {"purpose": "exploratory diagnostic, independent seed-7 rerun",
              "frozen_notebook_sha256": SHA256,
              "input_fingerprints_recorded_only_on_authorized_host": True,
              "population": "final eligible selected stays, 24h recorded-entry landmark",
              "unit_types": unit_types,
              "target_seed7_methods": descriptive_metrics(result, scope),
              "encrypted_plaintext_map_fidelity": encrypted_plaintext_fidelity(result, scope),
              "ckks_temperature_curve_max_abs_error": float(result["he_err"]),
              "independent_temperature_denominator_fidelity": independent_temperature_fidelity(result),
              "real_ckks": bool(scope["REAL_CKKS"]),
              "limitations": ["Patient-pooled calibration regressions are descriptive and weight large hospitals more.",
                              "Hospital-macro observed-minus-predicted summaries are descriptive and do not establish a calibration slope by site.",
                              "Source/target partition and TF-IDF backend match frozen v9; verify cohort fingerprints on host against the primary run.",
                              "No site identifier, individual prediction, record, or source hash appears in this aggregate JSON."]}
    output = OUTDIR / "aggregate_calibration_diagnostics_seed7.json"
    output.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n")
    print(f"Diagnostic aggregate saved on authorized host: {output}")


if __name__ == "__main__":
    main()
