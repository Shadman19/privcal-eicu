#!/usr/bin/env python3
"""Host-only, aggregate-output reconciliation of frozen-v9 site score tables.

Run where the restricted full-precision v9 CSVs live. This supplementary check
does not execute or alter v9, establish approval/timing, or replace the pinned
publication auditor. Human DUA review is required before any JSON leaves the
authorized host. Failure writes no report and deliberately names no hospital.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd


PENALTIES = (0.5, 1.0, 2.0, 4.0, 8.0)
TOLERANCE = 1e-10  # Frozen v9 exports full-precision values from identical arrays.
COUNTS = ("n_calib_total", "calib_deaths_total", "n_test")


def _need(frame: pd.DataFrame, names: set[str], label: str) -> None:
    absent = names - set(frame.columns)
    if absent:
        raise ValueError(f"{label}: required columns missing: {sorted(absent)}")


def _keyed(frame: pd.DataFrame, label: str) -> pd.DataFrame:
    if frame.empty or frame["site"].isna().any():
        raise ValueError(f"{label}: empty selection or missing hospital key")
    frame = frame.copy()
    frame["site"] = frame["site"].astype(str)
    if frame["site"].duplicated().any():
        raise ValueError(f"{label}: repeated hospital key")
    return frame.set_index("site", verify_integrity=True).sort_index()


def _same_sites(left: pd.DataFrame, right: pd.DataFrame, label: str) -> None:
    if not left.index.equals(right.index):
        raise ValueError(f"{label}: primary hospital set differs")


def _numeric(frame: pd.DataFrame, column: str, label: str, *, score: bool) -> np.ndarray:
    try:
        values = pd.to_numeric(frame[column], errors="raise").to_numpy(dtype=float)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{label}.{column}: nonnumeric value") from exc
    if not np.all(np.isfinite(values)):
        raise ValueError(f"{label}.{column}: nonfinite value")
    if score and (np.any(values < 0) or np.any(values > 1)):
        raise ValueError(f"{label}.{column}: Brier score outside [0,1]")
    return values


def _compare(left: pd.DataFrame, right: pd.DataFrame, left_col: str,
             right_col: str, label: str, *, score: bool = False) -> float:
    x = _numeric(left, left_col, label, score=score)
    y = _numeric(right, right_col, label, score=score)
    difference = float(np.max(np.abs(x - y)))
    if difference > TOLERANCE:
        raise ValueError(f"{label}: full-precision site rows differ; inspect on authorized host")
    return difference


def reconcile(input_dir: Path) -> dict[str, object]:
    pairs = pd.read_csv(input_dir / "primary_brier_site_pairs.csv")
    scarcity = pd.read_csv(input_dir / "all_scarcity_site_level.csv")
    penalty = pd.read_csv(input_dir / "all_local_intercept_penalty_sensitivity.csv")
    _need(pairs, {"site", "secure_agg_Brier", "local_intercept_Brier",
                  "secure_better_than_intercept_Brier", *COUNTS}, "primary pairs")
    _need(scarcity, {"site", "backend", "split_seed", "local_calib_cap",
                     "secure_agg_Brier", "local_intercept_Brier", *COUNTS}, "scarcity")
    _need(penalty, {"site", "backend", "split_seed", "penalty",
                    "pooled_isotonic_Brier", "local_intercept_Brier",
                    "local_minus_pooled_Brier", *COUNTS}, "penalty sensitivity")

    pairs = _keyed(pairs, "primary pairs")
    primary_events = _numeric(pairs, "calib_deaths_total", "primary", score=False)
    if np.any(primary_events < 0) or np.any(primary_events > 5):
        raise ValueError("primary pairs: outside designated 0-5-death stratum")
    main = scarcity.loc[(scarcity["backend"] == "tfidf_lr")
                        & (scarcity["split_seed"] == 7)
                        & (scarcity["local_calib_cap"].astype(str) == "all")
                        & (pd.to_numeric(scarcity["calib_deaths_total"], errors="coerce") <= 5)]
    main = _keyed(main, "seed-7 scarcity")
    _same_sites(pairs, main, "scarcity")

    maxima: list[float] = []
    for column in COUNTS:
        maxima.append(_compare(pairs, main, column, column, f"scarcity {column}"))
    for column in ("secure_agg_Brier", "local_intercept_Brier"):
        maxima.append(_compare(pairs, main, column, column, f"scarcity {column}", score=True))
    local = _numeric(pairs, "local_intercept_Brier", "primary", score=True)
    pooled = _numeric(pairs, "secure_agg_Brier", "primary", score=True)
    delta = _numeric(pairs, "secure_better_than_intercept_Brier", "primary", score=False)
    if np.max(np.abs(delta - (local - pooled))) > TOLERANCE:
        raise ValueError("primary pairs: Brier difference is inconsistent")

    selected = penalty.loc[(penalty["backend"] == "tfidf_lr")
                           & (penalty["split_seed"] == 7)
                           & (pd.to_numeric(penalty["calib_deaths_total"], errors="coerce") <= 5)]
    grid = pd.to_numeric(selected["penalty"], errors="coerce")
    if grid.isna().any() or set(grid.unique()) != set(PENALTIES):
        raise ValueError("penalty sensitivity: primary five-value grid incomplete or changed")
    for value in PENALTIES:
        rowset = _keyed(selected.loc[grid == value], f"penalty {value:g}")
        _same_sites(pairs, rowset, f"penalty {value:g}")
        for column in COUNTS:
            maxima.append(_compare(pairs, rowset, column, column,
                                   f"penalty {value:g} {column}"))
        maxima.append(_compare(pairs, rowset, "secure_agg_Brier",
                               "pooled_isotonic_Brier", f"penalty {value:g} pooled", score=True))
        p_local = _numeric(rowset, "local_intercept_Brier", f"penalty {value:g}", score=True)
        p_pool = _numeric(rowset, "pooled_isotonic_Brier", f"penalty {value:g}", score=True)
        p_delta = _numeric(rowset, "local_minus_pooled_Brier", f"penalty {value:g}", score=False)
        if float(np.max(np.abs(p_delta - (p_local - p_pool)))) > TOLERANCE:
            raise ValueError(f"penalty {value:g}: paired Brier difference inconsistent")
        if value == 2.0:
            maxima.append(_compare(pairs, rowset, "local_intercept_Brier",
                                   "local_intercept_Brier", "penalty 2 locked local", score=True))

    return {
        "purpose": "Internal, supplementary frozen-v9 row reconciliation; DUA review required",
        "n_hospitals": int(len(pairs)),
        "penalties_checked": list(PENALTIES),
        "max_abs_repeated_value_difference": max(maxima),
        "passed": True,
        "output_scope": "Aggregate diagnostics only; no site identifiers, site scores, or individual records.",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True, help="Restricted v9 output directory on the authorized host")
    parser.add_argument("--output", type=Path, required=True, help="New internal aggregate JSON; review DUA before release")
    args = parser.parse_args()
    if args.output.exists():
        parser.error("Refusing to overwrite an existing report")
    result = reconcile(args.input)
    args.output.write_text(json.dumps(result, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(f"Verified repeated method rows for {result['n_hospitals']} hospitals; internal audit only")


if __name__ == "__main__":
    main()
