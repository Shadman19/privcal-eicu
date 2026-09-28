#!/usr/bin/env python3
"""Primary-stratum held-out calibration check (v28a Codex review patch; host only).

Reruns the frozen seed-7 v9 split in memory (same approach as the pinned v23
diagnostic) and summarizes held-out calibration only for target hospitals with
0-5 calibration deaths, the stratum of the frozen v9 primary estimand. It does
not change the frozen notebook or its estimand.

Reported per method (pooled isotonic, penalty-2 local intercept, source-only
binned isotonic):
* hospital-macro observed-minus-predicted risk (mean over hospitals);
* patient-pooled calibration-in-the-large intercept with slope fixed at 1.

Requires the primary v9 run manifest and checks source file fingerprints,
notebook identity, software versions, and cohort size on the authorized host.
These restricted fields are never written to the transferable JSON.

Disclosure rule (not a formal guarantee): if the stratum has fewer than 2
hospitals, nothing is reported. If pooled stratum test deaths or survivors
number fewer than 20, the counts, the hospital-macro observed-minus-predicted,
and the patient-pooled intercept are all withheld. Uses held-out test labels only. A responsible person must approve any release.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path

import numpy as np
from scipy.optimize import minimize_scalar

from run_diagnostics_seed7_v23 import instrument_return

NOTEBOOK = Path("PrivCal_eICU_reviewer_sensitivities_v9.ipynb")
SHA256 = "23d0ca0666fd68e040bd6a39d6e3361b2ba0c0502b39cc01f88cfa4baa807b75"
MIN_CELL = 20


def verify_primary_provenance(scope: dict, manifest: dict) -> None:
    """Fail if the independent seed-7 rerun does not match the frozen v9 run."""
    checks = {
        "source_notebook_sha256": (manifest.get("source_notebook_sha256"), SHA256),
        "pythonhashseed": (manifest.get("pythonhashseed"), "0"),
        "input_fingerprints": (manifest.get("input_fingerprints"), scope.get("input_fingerprints")),
        "software_versions": (manifest.get("software_versions"), scope.get("software_versions")),
        "rows": (manifest.get("rows"), len(scope["data"])),
        "sites": (manifest.get("sites"), len(scope["SITES"])),
        "real_ckks": (manifest.get("real_ckks"), scope.get("REAL_CKKS")),
    }
    for field, (primary, rerun) in checks.items():
        if primary is None or primary != rerun:
            raise ValueError(f"Primary v9 and stratum rerun disagree on {field}; stop on authorized host")
    if manifest["real_ckks"] is not True:
        raise ValueError("Primary v9 did not use real CKKS")


def citl_intercept(p: np.ndarray, y: np.ndarray) -> float:
    z = np.log(np.clip(p, 1e-7, 1 - 1e-7) / np.clip(1 - p, 1e-7, 1))
    def loss(a):
        q = np.clip(1 / (1 + np.exp(-(z + a))), 1e-12, 1 - 1e-12)
        return -np.mean(y * np.log(q) + (1 - y) * np.log(1 - q))
    return float(minimize_scalar(loss, bounds=(-10, 10), method="bounded").x)


def stratum_metrics(result: dict, scope: dict, primary_sites: set | None = None) -> dict:
    parts, T_src = result["parts"], result["T_src"]
    sig, fri = scope["sigmoid"], scope["fit_regularized_intercept"]
    sites = [s for s in result["TARGET"] if int(parts[s]["y_calib"].sum()) <= 5]
    if primary_sites is not None and set(map(str, sites)) != set(map(str, primary_sites)):
        raise ValueError("Rerun stratum differs from the frozen v9 primary hospital set; stop and review on host")
    out = {"purpose": "exploratory held-out calibration in the frozen v9 primary stratum (seed 7, 0-5 calibration deaths)",
           "n_stratum_hospitals": len(sites)}
    if len(sites) < 2:
        out["status"] = "withheld_fewer_than_two_hospitals"
        return out
    methods = {
        "pooled_binned_isotonic": lambda s: result["predict_fn"]("PrivCal-B (secure-agg isotonic)", s, "test"),
        "local_intercept_penalty2": lambda s: sig(parts[s]["logit_test"] / T_src + fri(
            parts[s]["logit_calib"] / T_src, parts[s]["y_calib"], 2.0)),
        "source_only_binned_isotonic": lambda s: result["iso_source"].predict(sig(parts[s]["logit_test"])),
    }
    y_all = np.concatenate([np.asarray(parts[s]["y_test"], int) for s in sites])
    deaths, survivors = int(y_all.sum()), int(len(y_all) - y_all.sum())
    small = deaths < MIN_CELL or survivors < MIN_CELL
    out["pooled_test_counts"] = ("withheld_small_cell" if small else
                                 {"stays": int(len(y_all)), "deaths": deaths})
    for name, fn in methods.items():
        preds = [np.asarray(fn(s), float) for s in sites]
        macro = float(np.mean([np.asarray(parts[s]["y_test"]).mean() - p.mean() for s, p in zip(sites, preds)]))
        p_all = np.concatenate(preds)
        rec = {"hospital_macro_observed_minus_predicted": "withheld_small_cell" if small else macro,
               "patient_pooled_mean_predicted": float(p_all.mean())}
        rec["patient_pooled_calibration_in_the_large_intercept"] = (
            "withheld_small_cell" if small else citl_intercept(p_all, y_all))
        out[name] = rec
    out["notes"] = ["Intercept uses slope fixed at 1 (calibration-in-the-large); positive means under-prediction.",
                    "Hospital-macro observed-minus-predicted weights hospitals equally and is noisy with few deaths.",
                    "Exploratory; cannot change the frozen v9 Brier comparison."]
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--outdir", type=Path, required=True, help="fresh scratch dir for the in-memory rerun")
    ap.add_argument("--output", type=Path, required=True)
    ap.add_argument("--primary-pairs", type=Path, required=True,
                    help="restricted v9 primary_brier_site_pairs.csv; used only to verify the hospital set")
    ap.add_argument("--primary-manifest", type=Path, required=True,
                    help="restricted v9 run_manifest.json; never export its fingerprints")
    args = ap.parse_args()
    if args.output.exists():
        raise FileExistsError(args.output)
    raw = NOTEBOOK.read_bytes()
    if hashlib.sha256(raw).hexdigest() != SHA256:
        raise RuntimeError("Unexpected v9 notebook")
    src = "\n".join("".join(c["source"]) for c in json.loads(raw)["cells"] if c["cell_type"] == "code")
    before, sep, _ = src.partition("# 9. Run all backends and splits")
    if not sep:
        raise ValueError("Cannot isolate seed-7 v9 methods")
    before = instrument_return(before)
    old = "return dict(parts=parts,"
    if before.count(old) != 1:
        raise RuntimeError("Unexpected instrumented return")
    before = before.replace(old, "return dict(iso_source=iso_source, parts=parts,")
    os.environ["PRIVCAL_OUTDIR"] = str(args.outdir)
    scope = {"__name__": "__main__"}
    exec(compile(before, str(NOTEBOOK), "exec"), scope)
    verify_primary_provenance(scope, json.loads(args.primary_manifest.read_text()))
    result = scope["run_one_split"]("tfidf_lr", 7, make_figures=False)
    import pandas as pd
    primary_sites = set(pd.read_csv(args.primary_pairs)["site"].astype(str))
    report = stratum_metrics(result, scope, primary_sites)
    report["hospital_set_matches_frozen_v9_primary"] = True
    args.output.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n")
    print(f"Saved on authorized host (release requires human approval): {args.output}")


if __name__ == "__main__":
    main()
