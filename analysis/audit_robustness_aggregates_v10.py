#!/usr/bin/env python3
"""Add checked, aggregate-only reviewer tables to a verified v9 eICU audit.

Run on the authorized data host after the existing v9 primary audit. No site
identifiers, patient records, per-site estimates, or data hashes are exported.
Subsets smaller than five hospitals are reported only as suppressed counts.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import numpy as np
import pandas as pd

from audit_publication_results_v9 import paired_summary, require_columns


STRATA = (
    "00-05 local deaths", "06-15 local deaths", "16-30 local deaths",
    "31+ local deaths",
)
METRICS = ("Brier", "NLL", "ECE", "aECE", "AUROC")


def build(input_dir: Path, base_audit: Path, output: Path) -> dict:
    report = json.loads(base_audit.read_text())
    primary = report["primary"]
    if not primary.get("site_scores_and_interval_verified"):
        raise ValueError("The independent primary paired-site audit has not passed")
    if int(primary["n_hospitals"]) < 5:
        raise ValueError("Primary subgroup has fewer than five hospitals; retain output locally")
    meta = report.get("run_metadata") or {}
    if meta.get("version") != "real_eicu_v9_reproducibility_rerun" or not meta.get("real_ckks"):
        raise ValueError("Expected audited v9 real-CKKS sensitivity run")
    scarcity = pd.read_csv(input_dir / "all_scarcity_site_level.csv")
    require_columns(scarcity, ["backend", "split_seed", "local_calib_cap", "site",
                               "calib_deaths_total", "secure_agg_Brier", "local_intercept_Brier",
                               "death_stratum", "n_test"], "v9 scarcity")
    main = scarcity.loc[(scarcity.backend == "tfidf_lr") &
                        (scarcity.local_calib_cap.astype(str) == "all")].copy()
    if main.duplicated(["split_seed", "site"]).any():
        raise ValueError("Duplicate hospital within a source/target split")
    splits = list(map(int, meta.get("splits", [])))
    if splits != [7, 11, 17, 23, 31] or set(main.split_seed.astype(int)) != set(splits):
        raise ValueError("The complete designated five splits are required")

    robustness = []
    for split in splits:
        frame = main.loc[main.split_seed.astype(int) == split]
        for stratum in ("all target hospitals",) + STRATA:
            sample = frame if stratum == "all target hospitals" else frame.loc[frame.death_stratum == stratum]
            entry = {"split_seed": split, "stratum": stratum,
                     "n_target_hospitals": int(len(sample)), "results_suppressed": len(sample) < 5}
            if len(sample) >= 5:
                if (sample.n_test.astype(int) <= 0).any():
                    raise ValueError("Empty test subset in reviewer robustness table")
                stats = paired_summary(sample, "secure_agg_Brier", "local_intercept_Brier",
                                       "pooled_binned_isotonic_vs_local_intercept",
                                       seed=14000 + split * 10 + (0 if stratum == "all target hospitals" else STRATA.index(stratum) + 1))
                entry.update(stats)
            robustness.append(entry)

    # Cross-check the same seed-7 subset and paired direction as the primary audit.
    first = next(x for x in robustness if x["split_seed"] == 7 and x["stratum"] == STRATA[0])
    if first["results_suppressed"] or first["n_target_hospitals"] != primary["n_hospitals"]:
        raise ValueError("The reviewer low-event stratum differs from the approved primary group")
    if abs(first["mean_comparator_minus_method_Brier"] -
           primary["mean_comparator_minus_method_Brier"]) > 1e-10:
        raise ValueError("Reviewer table disagrees with approved primary estimate")
    # Reviewer intervals use distinct deterministic seeds; the primary interval
    # remains the seed-971 interval in the independently audited primary JSON.

    scores = pd.read_csv(input_dir / "all_per_site_metrics.csv")
    require_columns(scores, ["backend", "split_seed", "method", "site_type", "site", "n_test"]
                               + list(METRICS), "v9 per-site metrics")
    target = scores.loc[(scores.backend == "tfidf_lr") & (scores.site_type == "TARGET")]
    if target.duplicated(["split_seed", "method", "site"]).any():
        raise ValueError("Duplicate target hospital and method")
    method_summaries = []
    for (split, method), group in target.groupby(["split_seed", "method"], sort=True):
        if len(group) < 5:
            method_summaries.append({"split_seed": int(split), "method": method,
                                     "n_target_hospitals": int(len(group)), "results_suppressed": True})
            continue
        vals = group[list(METRICS)].apply(pd.to_numeric, errors="coerce")
        entry = {"split_seed": int(split), "method": method,
                 "n_target_hospitals": int(len(group)), "results_suppressed": False}
        for name in METRICS:
            finite = vals[name].replace([np.inf, -np.inf], np.nan).dropna()
            entry[f"macro_{name}"] = float(finite.mean()) if len(finite) >= 5 else None
            entry[f"n_valid_{name}"] = int(len(finite))
        method_summaries.append(entry)

    result = {"scope": "aggregate-only internal reviewer audit; clear sharing under eICU terms",
              "primary": primary,
              "five_correlated_split_strata": robustness,
              "target_method_macro_metrics": method_summaries,
              "v9_controls": report["low_event_seed7_sensitivity"],
              "local_intercept_penalty_sensitivity": report["local_intercept_penalty_sensitivity"],
              "run_metadata": meta,
              "ckks_arithmetic": report.get("ckks_arithmetic"),
              "notes": ["All 95% intervals resample hospitals within a fixed split; splits are correlated.",
                        "The primary seed-7 0-5-death interval comes from the separate seed-971 verification.",
                        "Brier is overall probabilistic accuracy; calibration-specific diagnostics remain to be run.",
                        "Neither a raw eICU record nor a per-hospital score is exported."]}
    output.write_text(json.dumps(result, indent=2, allow_nan=False) + "\n")
    return result


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--input", type=Path, required=True)
    p.add_argument("--base-audit", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    a = p.parse_args()
    result = build(a.input, a.base_audit, a.output)
    print(f"Verified {len(result['five_correlated_split_strata'])} split/stratum records; aggregate-only output: {a.output}")


if __name__ == "__main__":
    main()
