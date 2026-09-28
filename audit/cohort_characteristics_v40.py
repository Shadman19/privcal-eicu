#!/usr/bin/env python3
"""Aggregate cohort characteristics (Table 1) for the frozen v9 seed-7 partition (authorized host only).

Reruns the frozen v9 loader and seed-7 split in memory (same approach and provenance checks as the
pinned stratum-calibration script, including the exact primary hospital set) and summarizes the final
cohort for three public columns: all stays, source (development) hospitals, target (evaluation)
hospitals. The 0-5-death primary stratum is NOT tabulated here (it would allow recovery by subtraction).
Per column: stays, hospitals, vital status, age recorded (<90 / top-coded 90+ / missing), sex, unit type,
unit-stay type, and the length of the 24-hour text predictor in words. Descriptive only.

Reconciliation (fails closed): stays, deaths, hospitals and unit compositions of the all-stays column
must equal the approved v9 audit and approved seed-7 diagnostics; target test stays and deaths must
equal the approved diagnostics; the 0-5-death hospital set must equal the restricted primary pairs file;
the patient join must be one-to-one with no lost, duplicated or unmatched stays.

Disclosure rule (not a formal guarantee): every count is part of a composition that sums to the stay
count. A category is withheld in EVERY column if its count is 1 to MIN_CELL-1 in any column or in the
group implied by subtraction (all minus source minus target); if only one category of a composition
would be withheld, a second one is withheld too. Percentages are given only from released counts.
Age quartiles only for columns with at least 100 known ages; '> 89' is top-coded and any quartile at
the top code is reported as '90+'. No site identifier or record leaves the host. A responsible person
must approve any release.
"""
from __future__ import annotations
import argparse, hashlib, json, os
from pathlib import Path
import numpy as np
import pandas as pd

MIN_CELL = 20
# Bytes of the team-approved release (APPROVED_SHA256SUMS.txt, release_review_20260927T161413Z).
APPROVED_SHA256 = {
    "aggregate_publication_audit_v9.json": "cac5f258ba95d17a3e0574c798dd36cbd0898a3f13e2e32a20d153425cfd56ad",
    "aggregate_calibration_diagnostics_seed7.json": "671d2bfbd8bae4c8fb9207c99f473188870cadc9ac18c862ea2efd8cd51cfa00",
}
NOTEBOOK = Path("PrivCal_eICU_reviewer_sensitivities_v9.ipynb")
SHA256 = "23d0ca0666fd68e040bd6a39d6e3361b2ba0c0502b39cc01f88cfa4baa807b75"


def age_years(s: pd.Series) -> pd.Series:
    s = s.astype(str).str.strip().replace({"> 89": "90", ">89": "90", "": np.nan, "nan": np.nan})
    return pd.to_numeric(s, errors="coerce")


def raw_counts(df: pd.DataFrame) -> dict:
    """Exact counts for one group, as two-or-more-category compositions that sum to the stay count."""
    n = len(df); y = df["label"].astype(int); dead = int(y.sum())
    comp = {"vital_status": {"died_in_hospital": dead, "survived": n - dead}}
    if "age" in df:
        a = age_years(df["age"]); top = int((a >= 90).sum()); k = int(a.notna().sum())
        comp["age_recorded"] = {"under_90": k - top, "top_coded_90_plus": top, "missing": n - k}
    if "gender" in df:
        f = int((df["gender"].astype(str).str.lower() == "female").sum())
        comp["sex"] = {"female": f, "not_female_or_unknown": n - f}
    for col in ("unittype", "unitstaytype"):
        if col in df:
            vc = df[col].fillna("missing").astype(str).str.lower().value_counts()
            comp[col] = {k: int(v) for k, v in vc.items()}
    return {"stays": n, "comp": comp}


def linked_suppression(raw: dict, linked: list[str]) -> dict:
    """Return {composition: set(withheld categories)} applied to EVERY released column.

    `raw` holds exact counts for the released groups AND for the implied groups that released
    columns determine by subtraction (target minus 0-5 targets; all minus source minus target).
    A category is withheld in all columns if its count is 1..MIN_CELL-1 in any linked group.
    If exactly one category of a composition is withheld, the category with the smallest
    minimum count across linked groups is also withheld, so the stay total cannot recover it.
    """
    out = {}
    names = set().union(*(raw[g]["comp"].keys() for g in linked))
    for c in names:
        cats = sorted(set().union(*(raw[g]["comp"].get(c, {}).keys() for g in linked)))
        val = {k: [raw[g]["comp"].get(c, {}).get(k, 0) for g in linked] for k in cats}
        small = {k for k, v in val.items() if any(0 < x < MIN_CELL for x in v)}
        if len(small) == 1 and len(cats) > 1:
            # complementary cell: prefer a category present in every linked group, smallest total
            rest = sorted((min(val[k]) == 0, sum(val[k]), k) for k in cats if k not in small)
            small.add(rest[0][2])
        out[c] = small
    return out


def summarize(df: pd.DataFrame, n_hosp: int, withheld: dict, categories: dict) -> dict:
    """Every column lists the same categories (absent ones as 0), so a withheld cell never stands alone."""
    r = raw_counts(df)
    out = {"stays": r["stays"], "hospitals": n_hosp}
    for c, allcats in categories.items():
        cats = r["comp"].get(c, {})
        out[c] = {k: ("withheld_small_cell" if k in withheld.get(c, set()) else cats.get(k, 0)) for k in allcats}
    vs = out["vital_status"]
    if isinstance(vs.get("died_in_hospital"), int) and isinstance(vs.get("survived"), int):
        out["hospital_mortality_percent"] = round(100 * vs["died_in_hospital"] / r["stays"], 1)
    sx = out.get("sex", {})
    if isinstance(sx.get("female"), int) and isinstance(sx.get("not_female_or_unknown"), int):
        out["female_percent"] = round(100 * sx["female"] / r["stays"], 1)
    if "age" in df:
        known = age_years(df["age"]).dropna()
        if known.size >= 100:
            q = known.quantile([0.25, 0.5, 0.75], interpolation="lower")
            out["age_years_median_q1_q3"] = [("90+" if v >= 90 else int(v)) for v in (q[0.5], q[0.25], q[0.75])]
    if "text" in df and len(df) >= 100:
        w = df["text"].astype(str).str.split().str.len()
        q = w.quantile([0.25, 0.5, 0.75], interpolation="lower")
        out["predictor_text_words_median_q1_q3"] = [int(q[0.5]), int(q[0.25]), int(q[0.75])]
    for c in ("age", "gender", "unittype", "unitstaytype"):
        if c not in df:
            out[c] = "field_not_available"
    return out


def load_approved(path: Path, name: str, expected: dict = APPROVED_SHA256) -> dict:
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != expected[name]:
        raise RuntimeError(f"{path} is not the approved {name} (SHA-256 mismatch)")
    return json.loads(raw)


def recoverability_check(table: dict, implied_stays: int, public_all: dict, raise_on_fail: bool = True) -> set:
    """Linear reconstruction screen: flag any withheld cell pinned down by the listed linear totals.

    Scope: only the constraints listed below; it is not a proof that cells are unrecoverable from other
    released information or outside knowledge.

    Unknowns: every withheld cell of the released columns, plus every category of the undisplayed group
    'all minus source minus target'. Constraints: each column's categories sum to its displayed stay
    count; for each category all = source + target + implied; cells already public for the all column
    (approved compositions) are fixed; all unknowns are >= 0. For each withheld cell the feasible range
    is found by linear programming. Any withheld cell must have a range of at least 1; a withheld cell
    whose true value is 1..MIN_CELL-1 must have a range of at least MIN_CELL.
    Returns the compositions that fail (raises instead if raise_on_fail).
    """
    failing = set()
    from scipy.optimize import linprog
    W = "withheld_small_cell"
    cols = list(table)
    assert cols == ["all_stays", "source_hospitals", "target_hospitals"]
    for comp in table["all_stays"]["_raw"]:
        cats = list(table["all_stays"][comp])
        var, x0 = {}, {}
        for g in cols:
            for k in cats:
                if table[g][comp][k] == W:
                    var[(g, k)] = len(var); x0[(g, k)] = table[g]["_raw"][comp].get(k, 0)
        if not var:
            continue
        for k in cats:
            var[("implied", k)] = len(var)
        A, b = [], []
        def row(terms, rhs):
            r = np.zeros(len(var)); c = rhs
            for (g, k), sign in terms:
                if (g, k) in var:
                    r[var[(g, k)]] += sign
                else:
                    c -= sign * table[g][comp][k]
            A.append(r); b.append(c)
        for g in cols:
            row([((g, k), 1) for k in cats], table[g]["stays"])
        row([(("implied", k), 1) for k in cats], implied_stays)
        for k in cats:
            row([(("all_stays", k), 1), (("source_hospitals", k), -1), (("target_hospitals", k), -1),
                 (("implied", k), -1)], 0)
            if k in public_all.get(comp, {}) and ("all_stays", k) in var:
                row([(("all_stays", k), 1)], public_all[comp][k])
        A, b = np.array(A), np.array(b, float)
        for key, i in var.items():
            if key[0] == "implied":
                continue
            c = np.zeros(len(var)); c[i] = 1
            lo = linprog(c, A_eq=A, b_eq=b, bounds=(0, None), method="highs")
            hi = linprog(-c, A_eq=A, b_eq=b, bounds=(0, None), method="highs")
            if lo.status != 0 or hi.status != 0:
                raise RuntimeError(f"recoverability check could not solve {comp}; stop and review on host")
            width = -hi.fun - lo.fun
            need = MIN_CELL if 0 < x0[key] < MIN_CELL else 1
            if width < need - 1e-9:
                if raise_on_fail:
                    raise RuntimeError(f"withheld {comp} cell is recoverable from displayed or public totals; "
                                       "stop and review on host")
                failing.add(comp)
                break
    return failing


def primary_low_sites(result: dict) -> list[str]:
    return [str(s) for s in result["TARGET"] if int(result["parts"][s]["y_calib"].sum()) <= 5]


def join_patient(data: pd.DataFrame, patient: pd.DataFrame) -> pd.DataFrame:
    """Strict one-to-one join; fields already in `data` must agree with the patient table."""
    if patient["patientunitstayid"].duplicated().any():
        raise RuntimeError("patient table has duplicated patientunitstayid")
    if data["patientunitstayid"].duplicated().any():
        raise RuntimeError("cohort has duplicated patientunitstayid")
    want = [c for c in ("age", "gender", "unittype", "unitstaytype") if c in patient.columns]
    missing = ~data["patientunitstayid"].isin(patient["patientunitstayid"])
    if missing.any():
        raise RuntimeError("cohort stays without a patient-table row")
    d = data.merge(patient[["patientunitstayid"] + want], on="patientunitstayid", how="left",
                   validate="one_to_one", suffixes=("", "_pt"))
    for c in want:
        if c + "_pt" in d:
            if not d[c].astype(str).equals(d[c + "_pt"].astype(str)):
                raise RuntimeError(f"cohort and patient table disagree on {c}")
            d = d.drop(columns=c + "_pt")
    if len(d) != len(data):
        raise RuntimeError("cohort join changed row count")
    return d


def reconcile(rep_raw: dict, result: dict, approved: dict) -> None:
    """Fail closed unless the rerun matches every previously approved total it overlaps."""
    audit, diag = approved["audit"], approved["diag"]
    a = rep_raw["all_stays"]
    ut = diag["unit_types"]
    checks = {"stays": (a["stays"], audit["run_metadata"]["rows"]),
              "stays_vs_diagnostics": (a["stays"], ut["denominator_selected_stays"]),
              "deaths": (a["comp"]["vital_status"]["died_in_hospital"], ut["selected_hospital_deaths"]),
              "hospitals": (approved["n_all"], audit["run_metadata"]["sites"])}
    for f in ("unittype", "unitstaytype"):
        if f in a["comp"]:
            checks[f] = (a["comp"][f], ut["fields"][f]["categories"])
    m = next(iter(diag["target_seed7_methods"].values()))
    y = [np.asarray(result["parts"][s]["y_test"], int) for s in result["TARGET"]]
    checks["target_hospitals"] = (len(result["TARGET"]), m["n_target_hospitals"])
    checks["target_test_stays"] = (int(sum(len(v) for v in y)), m["n_test_stays"])
    checks["target_test_deaths"] = (int(sum(v.sum() for v in y)), m["n_test_deaths"])
    for k, (got, want) in checks.items():
        if got != want:
            raise RuntimeError(f"reconciliation failed on {k}; stop and review on host")


def build(scope: dict, result: dict, patient: pd.DataFrame, primary_sites: set | None = None,
          approved: dict | None = None) -> dict:
    data = scope["data"]
    target = [str(s) for s in result["TARGET"]]
    source = [str(s) for s in scope["SITES"] if str(s) not in set(target)]
    low = primary_low_sites(result)
    if primary_sites is not None and set(low) != set(map(str, primary_sites)):
        raise RuntimeError("rerun 0-5 stratum differs from the frozen v9 primary hospital set")
    d = join_patient(data, patient)
    d["site"] = d["site"].astype(str)
    released = {"all_stays": (d, d["site"].nunique()),
                "source_hospitals": (d[d.site.isin(source)], len(source)),
                "target_hospitals": (d[d.site.isin(target)], len(target))}
    implied = {"neither_source_nor_target_implied": d[~d.site.isin(source) & ~d.site.isin(target)]}
    raw = {k: raw_counts(g) for k, (g, _) in released.items()}
    raw.update({k: raw_counts(g) for k, g in implied.items()})
    if approved is not None:
        reconcile(raw, result, dict(approved, n_all=released["all_stays"][1]))
    linked = [k for k in raw if raw[k]["stays"] > 0]
    if any(raw[k]["stays"] < MIN_CELL for k in linked):
        raise RuntimeError(f"a released or implied group has 1-{MIN_CELL - 1} stays; refuse to release")
    withheld = linked_suppression(raw, linked)
    categories = {c: sorted(set().union(*(raw[g]["comp"].get(c, {}).keys() for g in linked)))
                  for c in set().union(*(raw[g]["comp"].keys() for g in linked))}
    groups = {k: summarize(g, n, withheld, categories) for k, (g, n) in released.items()}
    for k in groups:
        groups[k]["_raw"] = raw[k]["comp"]
    public_all = {}
    if approved is not None:
        ut = approved["diag"]["unit_types"]
        public_all = {f: ut["fields"][f]["categories"] for f in ("unittype", "unitstaytype")}
        public_all["vital_status"] = {"died_in_hospital": ut["selected_hospital_deaths"],
                                      "survived": ut["denominator_selected_stays"] - ut["selected_hospital_deaths"]}
    implied_n = raw["neither_source_nor_target_implied"]["stays"]
    # Widen suppression (next-smallest category, in all columns) until no withheld cell is recoverable.
    for _ in range(100):
        failing = recoverability_check(groups, implied_n, public_all, raise_on_fail=False)
        if not failing:
            break
        for comp in failing:
            left = [k for k in categories[comp] if k not in withheld[comp]]
            if not left:
                raise RuntimeError(f"{comp} cannot be protected; stop and review on host")
            withheld[comp].add(min(left, key=lambda k: sum(raw[g]["comp"].get(comp, {}).get(k, 0) for g in linked)))
        groups = {k: summarize(g, n, withheld, categories) for k, (g, n) in released.items()}
        for k in groups:
            groups[k]["_raw"] = raw[k]["comp"]
    recoverability_check(groups, implied_n, public_all)          # final check, fails closed
    for k in groups:
        del groups[k]["_raw"]
    return {"purpose": "descriptive cohort characteristics for the frozen v9 seed-7 partition",
            "min_cell": MIN_CELL,
            "reconciled_with_approved_v9_results": approved is not None,
            "primary_hospital_set_verified": primary_sites is not None,
            "linear_reconstruction_screen_passed": True,
            "groups": groups,
            "notes": [f"A category is withheld in every column if its count is 1-{MIN_CELL - 1} in any column or in the "
                      "group implied by subtraction (all minus source minus target); a second category is withheld "
                      "when only one would be. Not a formal privacy guarantee.",
                      "The 0-5-death primary stratum is not tabulated, to prevent recovery by subtraction.",
                      "eICU records age above 89 as '> 89'; it is counted as top-coded 90+, and a quartile at the "
                      "top code is shown as '90+'. Quartiles use observed values (lower interpolation).",
                      "Predictor text length counts words in the 24-hour diagnosis and treatment text used by the model.",
                      "linear_reconstruction_screen_passed means a linear program found no withheld cell pinned down by "
                      "the displayed column totals, the all = source + target + remainder identity, and the approved "
                      "all-stays compositions and deaths. It does not establish that cells cannot be recovered using "
                      "other released information or outside knowledge; a disclosure review of the exact output is required.",
                      "Descriptive only; does not change the frozen v9 analysis."]}


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--outdir", type=Path, required=True, help="fresh scratch dir for the in-memory rerun")
    ap.add_argument("--output", type=Path, required=True)
    ap.add_argument("--patient", type=Path, required=True, help="eICU patient table (restricted)")
    ap.add_argument("--primary-manifest", type=Path, required=True, help="restricted v9 run_manifest.json")
    ap.add_argument("--primary-pairs", type=Path, required=True,
                    help="restricted v9 primary_brier_site_pairs.csv; used only to verify the hospital set")
    ap.add_argument("--approved-audit", type=Path, required=True, help="approved aggregate_publication_audit_v9.json")
    ap.add_argument("--approved-diagnostics", type=Path, required=True,
                    help="approved aggregate_calibration_diagnostics_seed7.json")
    a = ap.parse_args()
    if a.output.exists():
        raise FileExistsError(a.output)
    approved = {"audit": load_approved(a.approved_audit, "aggregate_publication_audit_v9.json"),
                "diag": load_approved(a.approved_diagnostics, "aggregate_calibration_diagnostics_seed7.json")}
    raw = NOTEBOOK.read_bytes()
    if hashlib.sha256(raw).hexdigest() != SHA256:
        raise RuntimeError("Unexpected v9 notebook")
    from run_diagnostics_seed7_v23 import instrument_return
    from stratum_calibration_v28a_codex import verify_primary_provenance
    src = "\n".join("".join(c["source"]) for c in json.loads(raw)["cells"] if c["cell_type"] == "code")
    before, sep, _ = src.partition("# 9. Run all backends and splits")
    if not sep:
        raise ValueError("Cannot isolate the v9 loader and split")
    before = instrument_return(before)
    os.environ["PRIVCAL_OUTDIR"] = str(a.outdir)
    scope = {"__name__": "__main__"}
    exec(compile(before, str(NOTEBOOK), "exec"), scope)
    verify_primary_provenance(scope, json.loads(a.primary_manifest.read_text()))
    result = scope["run_one_split"]("tfidf_lr", 7, make_figures=False)
    primary_sites = set(pd.read_csv(a.primary_pairs)["site"].astype(str))
    if len(primary_sites) != approved["audit"]["primary"]["n_hospitals"]:
        raise RuntimeError("primary pairs file disagrees with the approved primary hospital count")
    patient = pd.read_csv(a.patient, low_memory=False)
    rep = build(scope, result, patient, primary_sites, approved)
    a.output.write_text(json.dumps(rep, indent=2, allow_nan=False) + "\n")
    print(f"Saved on authorized host (release requires human approval): {a.output}")


if __name__ == "__main__":
    main()
