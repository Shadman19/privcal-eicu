"""Create an aggregate-only audit report for a PrivCal eICU v7 or v9 run.

This program must run on the authorized eICU host.  It reads restricted
per-hospital result tables locally, verifies the exact paired primary Brier
contrast, and emits only aggregate summaries.  Review the resulting JSON
under the applicable data-use agreement before transferring it anywhere.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd


PRIMARY_COLUMNS = [
    "n_hospitals",
    "mean_pooled_Brier",
    "mean_local_intercept_Brier",
    "mean_local_minus_pooled_Brier",
    "CI95_low",
    "CI95_high",
    "split_seed",
    "backend",
]
PAIR_COLUMNS = [
    "site",
    "calib_deaths_total",
    "secure_agg_Brier",
    "local_intercept_Brier",
    "secure_better_than_intercept_Brier",
]
SCARCITY_COLUMNS = [
    "site",
    "backend",
    "split_seed",
    "local_calib_cap",
    "calib_deaths_total",
    "secure_agg_Brier",
    "local_intercept_Brier",
    "secure_better_than_intercept_Brier",
]


def require_columns(frame: pd.DataFrame, names: list[str], source: str) -> None:
    missing = sorted(set(names).difference(frame.columns))
    if missing:
        raise ValueError(f"{source} lacks columns: {missing}")


def close_to(actual: float, expected: float, name: str, tolerance: float = 1e-9) -> None:
    if not np.isfinite(actual) or abs(actual - expected) > tolerance:
        raise ValueError(f"{name} failed verification; inspect the protected source output")


def paired_bootstrap(delta: np.ndarray, seed: int, resamples: int = 2000) -> tuple[float, float]:
    if len(delta) == 0 or not np.all(np.isfinite(delta)):
        raise ValueError("Cannot bootstrap an empty or nonfinite paired contrast")
    rng = np.random.default_rng(seed)
    draws = rng.choice(delta, size=(resamples, len(delta)), replace=True).mean(axis=1)
    return tuple(map(float, np.percentile(draws, [2.5, 97.5])))


def paired_summary(
    frame: pd.DataFrame,
    method_column: str,
    comparator_column: str,
    label: str,
    seed: int,
) -> dict[str, object]:
    """Summarize comparator minus method, so positive values favor method."""
    require_columns(frame, [method_column, comparator_column], label)
    method = frame[method_column].to_numpy(dtype=float)
    comparator = frame[comparator_column].to_numpy(dtype=float)
    delta = comparator - method
    low, high = paired_bootstrap(delta, seed)
    return {
        "comparison": label,
        "positive_delta_favors": method_column,
        "n_hospitals": int(len(delta)),
        "mean_method_Brier": float(np.mean(method)),
        "mean_comparator_Brier": float(np.mean(comparator)),
        "mean_comparator_minus_method_Brier": float(np.mean(delta)),
        "median_comparator_minus_method_Brier": float(np.median(delta)),
        "IQR_comparator_minus_method_Brier": [
            float(np.percentile(delta, 25)),
            float(np.percentile(delta, 75)),
        ],
        "method_lower_Brier_hospitals": int(np.sum(delta > 0)),
        "paired_hospital_bootstrap_95_CI": [low, high],
        "bootstrap_resamples": 2000,
        "bootstrap_seed": seed,
    }


def verify_primary(
    primary: pd.DataFrame,
    pairs: pd.DataFrame,
    scarcity: pd.DataFrame,
) -> tuple[pd.Series, pd.DataFrame, pd.DataFrame, dict[str, object]]:
    require_columns(primary, PRIMARY_COLUMNS, "primary table")
    require_columns(pairs, PAIR_COLUMNS, "primary site-pair table")
    require_columns(scarcity, SCARCITY_COLUMNS, "scarcity table")
    if len(primary) != 1:
        raise ValueError("Expected exactly one primary result row")
    if pairs["site"].astype(str).duplicated().any():
        raise ValueError("Primary site-pair table has duplicate hospitals")

    row = primary.iloc[0]
    if int(row["split_seed"]) != 7 or row["backend"] != "tfidf_lr":
        raise ValueError("Primary row is not the designated seed-7 TF-IDF analysis")
    if (pairs["calib_deaths_total"] > 5).any() or (pairs["calib_deaths_total"] < 0).any():
        raise ValueError("Primary hospital pairs are outside the 0–5-death stratum")
    if len(pairs) != int(row["n_hospitals"]):
        raise ValueError("Primary hospital count disagrees with the paired table")

    pooled = pairs["secure_agg_Brier"].to_numpy(dtype=float)
    local = pairs["local_intercept_Brier"].to_numpy(dtype=float)
    delta = pairs["secure_better_than_intercept_Brier"].to_numpy(dtype=float)
    if not np.all(np.isfinite(np.concatenate([pooled, local, delta]))):
        raise ValueError("Primary site-pair table contains a nonfinite score")
    if np.max(np.abs(delta - (local - pooled))) > 1e-10:
        raise ValueError("Primary paired difference has an incorrect sign or stale values")

    close_to(float(row["mean_pooled_Brier"]), float(np.mean(pooled)), "primary pooled mean")
    close_to(float(row["mean_local_intercept_Brier"]), float(np.mean(local)), "primary local mean")
    close_to(float(row["mean_local_minus_pooled_Brier"]), float(np.mean(delta)), "primary difference mean")
    ci_low, ci_high = paired_bootstrap(delta, seed=971)
    close_to(float(row["CI95_low"]), ci_low, "primary lower confidence bound")
    close_to(float(row["CI95_high"]), ci_high, "primary upper confidence bound")

    main = scarcity[
        (scarcity["backend"] == "tfidf_lr")
        & (scarcity["local_calib_cap"].astype(str) == "all")
    ].copy()
    if main.duplicated(["split_seed", "site"]).any():
        raise ValueError("Scarcity table has duplicate hospitals within a split")
    low_event = main[
        (main["split_seed"].astype(int) == 7)
        & (main["calib_deaths_total"].astype(float) <= 5)
    ].copy()
    low_event["site_key"] = low_event["site"].astype(str)
    pairs_check = pairs.copy()
    pairs_check["site_key"] = pairs_check["site"].astype(str)
    if set(low_event["site_key"]) != set(pairs_check["site_key"]):
        raise ValueError("Primary hospital list differs from the scarcity table")

    merged = pairs_check.merge(
        low_event[
            [
                "site_key",
                "secure_agg_Brier",
                "local_intercept_Brier",
                "secure_better_than_intercept_Brier",
            ]
        ],
        on="site_key",
        how="inner",
        validate="one_to_one",
        suffixes=("_pairs", "_scarcity"),
    )
    if len(merged) != len(pairs):
        raise ValueError("Site-key merge did not preserve every primary hospital")
    # v7 exported rounded scarcity rows; v9 retains full precision.
    for name in (
        "secure_agg_Brier",
        "local_intercept_Brier",
        "secure_better_than_intercept_Brier",
    ):
        if np.max(np.abs(merged[f"{name}_pairs"] - merged[f"{name}_scarcity"])) > 0.00006:
            raise ValueError(f"Primary and scarcity values disagree for matched site: {name}")

    primary_report = paired_summary(
        pairs,
        method_column="secure_agg_Brier",
        comparator_column="local_intercept_Brier",
        label="primary_self_including_pooled_binned_isotonic_vs_regularized_local_intercept",
        seed=971,
    )
    primary_report["site_scores_and_interval_verified"] = True
    return row, main, low_event, primary_report


def v9_sensitivity_report(low_event: pd.DataFrame) -> list[dict[str, object]]:
    comparisons = [
        (
            "secure_agg_Brier",
            "local_platt_intercept_Brier",
            "self_including_pooled_binned_isotonic_vs_source_platt_local_intercept",
            972,
        ),
        (
            "pooled_excluding_site_Brier",
            "local_intercept_Brier",
            "leave_one_target_hospital_out_pooled_binned_isotonic_vs_regularized_local_intercept",
            973,
        ),
        (
            "pooled_excluding_site_Brier",
            "local_platt_intercept_Brier",
            "leave_one_target_hospital_out_pooled_binned_isotonic_vs_source_platt_local_intercept",
            974,
        ),
        (
            "secure_agg_Brier",
            "source_binned_isotonic_Brier",
            "self_including_pooled_binned_isotonic_vs_source_only_binned_isotonic",
            975,
        ),
        (
            "secure_agg_Brier",
            "pooled_temperature_Brier",
            "pooled_binned_isotonic_vs_pooled_temperature",
            976,
        ),
        (
            "pooled_excluding_site_Brier",
            "secure_agg_Brier",
            "leave_one_target_hospital_out_pooled_binned_isotonic_vs_self_including_pooled_binned_isotonic",
            977,
        ),
    ]
    report = []
    for method, comparator, label, seed in comparisons:
        if {method, comparator}.issubset(low_event.columns):
            report.append(paired_summary(low_event, method, comparator, label, seed))
    return report


def penalty_sensitivity_report(input_dir: Path, primary_sites: set[str]) -> list[dict[str, object]]:
    path = input_dir / "all_local_intercept_penalty_sensitivity.csv"
    if not path.exists():
        return []
    penalty = pd.read_csv(path)
    require_columns(
        penalty,
        [
            "backend",
            "split_seed",
            "site",
            "calib_deaths_total",
            "penalty",
            "pooled_isotonic_Brier",
            "local_intercept_Brier",
        ],
        "penalty sensitivity",
    )
    subset = penalty[
        (penalty["backend"] == "tfidf_lr")
        & (penalty["split_seed"].astype(int) == 7)
        & (penalty["calib_deaths_total"].astype(float) <= 5)
    ].copy()
    subset["site_key"] = subset["site"].astype(str)
    report = []
    for penalty_value, group in subset.groupby("penalty", sort=True):
        if group["site_key"].duplicated().any() or set(group["site_key"]) != primary_sites:
            raise ValueError(f"Penalty {penalty_value} does not use the exact primary hospital set")
        entry = paired_summary(
            group,
            method_column="pooled_isotonic_Brier",
            comparator_column="local_intercept_Brier",
            label=f"pooled_binned_isotonic_vs_local_intercept_penalty_{float(penalty_value):g}",
            seed=980 + int(round(float(penalty_value) * 10)),
        )
        entry["local_intercept_penalty"] = float(penalty_value)
        report.append(entry)
    return report


def run_metadata(input_dir: Path) -> dict[str, object] | None:
    path = input_dir / "run_manifest.json"
    if not path.exists():
        return None
    raw = json.loads(path.read_text())
    permitted = (
        "version",
        "prediction_window_hours",
        "rows",
        "sites",
        "splits",
        "model_backends",
        "he_backend",
        "real_ckks",
        "privacy_scope",
        "run_started_utc",
        "pythonhashseed",
        "source_notebook_sha256",
        "reviewed_v8_source_sha256",
        "software_versions",
        "source_site_order",
    )
    result = {key: raw[key] for key in permitted if key in raw}
    result["input_fingerprints_recorded_on_authorized_host"] = "input_fingerprints" in raw
    return result


def audit(input_dir: Path, output: Path, require_v9_sensitivities: bool) -> None:
    primary = pd.read_csv(input_dir / "table_primary_brier_few_events.csv")
    pairs = pd.read_csv(input_dir / "primary_brier_site_pairs.csv")
    scarcity = pd.read_csv(input_dir / "all_scarcity_site_level.csv")
    _, main, low_event, primary_report = verify_primary(primary, pairs, scarcity)

    sensitivity = v9_sensitivity_report(low_event)
    if require_v9_sensitivities and len(sensitivity) != 6:
        raise ValueError("The v9 result is missing one or more required low-event sensitivity comparisons")

    he_report: dict[str, object] | None = None
    he_path = input_dir / "he_arithmetic_audit.csv"
    if he_path.exists():
        he = pd.read_csv(he_path)
        require_columns(
            he,
            ["pooled_loss_max_abs_error", "encrypted_temperature", "plaintext_temperature"],
            "CKKS arithmetic audit",
        )
        if not np.all(np.isfinite(he["pooled_loss_max_abs_error"])):
            raise ValueError("CKKS arithmetic audit contains a nonfinite error")
        he_report = {
            "runs": int(len(he)),
            "max_abs_pooled_loss_error": float(he["pooled_loss_max_abs_error"].max()),
            "temperature_matches_plaintext": bool(
                np.allclose(he["encrypted_temperature"], he["plaintext_temperature"])
            ),
        }

    result: dict[str, object] = {
        "purpose": "Internal aggregate-only review; confirm data-use terms before release",
        "primary": primary_report,
        "low_event_seed7_sensitivity": sensitivity,
        "local_intercept_penalty_sensitivity": penalty_sensitivity_report(
            input_dir, set(pairs["site"].astype(str))
        ),
        "run_metadata": run_metadata(input_dir),
        "ckks_arithmetic": he_report,
        "caveats": [
            "The primary interval is conditional on the fixed seed-7 split and fitted pipeline.",
            "The five hospital splits reuse patients and are correlated sensitivity runs, not independent replications.",
            "The CKKS implementation is a single-host arithmetic emulation, not a deployed multi-institution protocol or a differential-privacy guarantee.",
        ],
        "output_scope": "No individual records, predictions, site identifiers, or site-level scores are emitted.",
    }
    output.write_text(json.dumps(result, indent=2, allow_nan=False) + "\n")
    primary = result["primary"]
    print(f"Verified primary contrast at {primary['n_hospitals']} target hospitals")
    print(
        "Delta Brier (local intercept minus pooled): "
        f"{primary['mean_comparator_minus_method_Brier']:.6f}"
    )
    print(f"Aggregate-only internal review file: {output}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=Path("privcal_eicu_v9_sensitivities"))
    parser.add_argument("--output", type=Path, default=Path("aggregate_publication_audit_v9.json"))
    parser.add_argument(
        "--require-v9-sensitivities",
        action="store_true",
        help="Fail if the six v9 low-event sensitivity comparisons are unavailable.",
    )
    args = parser.parse_args()
    audit(args.input, args.output, args.require_v9_sensitivities)


if __name__ == "__main__":
    main()
