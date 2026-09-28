"""Host-side aggregate summary of the frozen v9 primary hospital pairs (v24).

Internal, supplementary, post-run reporting helper. It reads the restricted
v9 output ``primary_brier_site_pairs.csv`` on the authorized host and writes
only hospital-count summaries that the pinned v9 auditor does not report:

* strict wins (local minus pooled Brier > 0), strict losses (< 0), and exact
  ties (== 0) for the designated seed-7, 0-5-death primary stratum;
* single-hospital deletion sign stability of the mean paired difference,
  reported as counts only.

It does not change the frozen v9 notebook, estimand, auditor, bootstrap, or
seed. It exports no site identifier, per-hospital score, per-hospital
difference, or leave-one-out mean: with n hospitals, n leave-one-out means
plus the overall mean reconstruct every hospital's difference, and even the
min/max endpoints reveal two hospitals' differences. Only a responsible team
member may approve release of the JSON under the eICU data-use terms.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

REQUIRED = ("site", "calib_deaths_total", "secure_agg_Brier", "local_intercept_Brier",
            "secure_better_than_intercept_Brier")


def summarize_primary_pairs(pairs: pd.DataFrame) -> dict:
    missing = [c for c in REQUIRED if c not in pairs.columns]
    if missing:
        raise ValueError(f"Primary site-pair table lacks columns: {missing}")
    if pairs.empty:
        raise ValueError("Primary site-pair table is empty")
    if pairs["site"].astype(str).duplicated().any():
        raise ValueError("Duplicate hospitals in primary site-pair table")
    deaths = pairs["calib_deaths_total"].to_numpy(dtype=float)
    if np.any(deaths < 0) or np.any(deaths > 5):
        raise ValueError("Rows fall outside the 0-5 calibration-death primary stratum")
    pooled = pairs["secure_agg_Brier"].to_numpy(dtype=float)
    local = pairs["local_intercept_Brier"].to_numpy(dtype=float)
    delta = pairs["secure_better_than_intercept_Brier"].to_numpy(dtype=float)
    if not np.all(np.isfinite(np.concatenate([pooled, local, delta]))):
        raise ValueError("Nonfinite primary score")
    if np.max(np.abs(delta - (local - pooled))) > 1e-10:
        raise ValueError("Paired difference is not local minus pooled Brier")

    n = int(len(delta))
    wins, losses = int(np.sum(delta > 0)), int(np.sum(delta < 0))
    ties = n - wins - losses
    mean = float(np.mean(delta))
    out = {
        "purpose": "supplementary aggregate reporting of frozen v9 primary pairs; not claim forming by itself",
        "estimand": "seed 7, tfidf_lr, all local labels, 0-5 calibration deaths; delta = local intercept Brier - pooled Brier",
        "n_hospitals": n,
        "pooled_lower_Brier_hospitals": wins,
        "local_intercept_lower_Brier_hospitals": losses,
        "exactly_tied_hospitals": ties,
        "tie_rule": "exact floating-point equality of the two hospital Brier scores; no tolerance chosen after results",
        "mean_sign": "positive" if mean > 0 else ("negative" if mean < 0 else "zero"),
    }
    if n < 2:
        out["single_hospital_deletion"] = "not_applicable_fewer_than_two_hospitals"
        return out
    loo = (delta.sum() - delta) / (n - 1)
    flips = int(np.sum(np.sign(loo) != np.sign(mean)))
    out["single_hospital_deletion"] = {
        "deletions_evaluated": n,
        "deletions_changing_sign_of_mean": flips,
        "sign_of_mean_stable_under_every_single_deletion": flips == 0,
        "note": "Counts only; leave-one-out means and their range are withheld because they reconstruct hospital-level differences.",
    }
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--input", type=Path, required=True,
                        help="restricted v9 primary_brier_site_pairs.csv on the authorized host")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(f"Refusing to overwrite {args.output}")
    report = summarize_primary_pairs(pd.read_csv(args.input))
    args.output.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n")
    print(f"Aggregate saved on authorized host (release requires human approval): {args.output}")


if __name__ == "__main__":
    main()
